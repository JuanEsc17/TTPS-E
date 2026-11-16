"""Repositorio de acceso a datos para medicos y especialidades."""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from src.core.database import db
from src.core.models import (Especialidad, Medico, MedicoEspecialidad, Rol, Usuario,)
from src.core.repos import usuario_repo
from src.core.services.excepciones import ErrorDominio


def listar_especialidades() -> list[Especialidad]:
    """Devuelve todas las especialidades ordenadas alfabeticamente."""
    stmt = select(Especialidad).order_by(Especialidad.nombre.asc())
    return list(db.session.scalars(stmt).all())


def buscar_especialidades_por_ids(especialidades_ids: list[int]) -> list[Especialidad]:
    """Busca especialidades existentes cuyos IDs esten en la lista."""
    if not especialidades_ids:
        return []
    stmt = select(Especialidad).where(Especialidad.id.in_(especialidades_ids))
    return list(db.session.scalars(stmt).all())


def buscar_medico_por_matricula(matricula: str) -> Medico | None:
    """Busca un medico por su numero de matricula."""
    stmt = select(Medico).where(Medico.matricula == matricula)
    return db.session.scalar(stmt)


def crear_medico_completo(
    *,
    nombre: str,
    apellido: str,
    telefono: str,
    email: str,
    password_hash: str,
    matricula: str,
    especialidades_ids: list[int],
    dispositivo_hash: str | None = None,
) -> tuple[Usuario, Medico]:
    """Crea Usuario (Rol.MEDICO), Medico y sus especialidades en una transaccion."""
    try:
        usuario = Usuario(
            email=email,
            password_hash=password_hash,
            rol=Rol.MEDICO,
            nombre=nombre,
            apellido=apellido,
            telefono=telefono,
            debe_cambiar_password=False,
        )
        # flush() envia el INSERT sin cerrar la transaccion para obtener usuario.id
        db.session.add(usuario)
        db.session.flush()

        medico = Medico(
            usuario_id=usuario.id,
            matricula=matricula,
        )
        # flush() genera medico.id antes de insertar la tabla intermedia
        db.session.add(medico)
        db.session.flush()

        for especialidad_id in especialidades_ids:
            db.session.add(
                MedicoEspecialidad(
                    medico_id=medico.id,
                    especialidad_id=especialidad_id,
                )
            )

        # Si viene huella de dispositivo, se marca como conocida en la misma transaccion
        if dispositivo_hash:
            usuario_repo.registrar_dispositivo(usuario.id, dispositivo_hash)

        db.session.commit()
        return usuario, medico
    except IntegrityError as exc:
        # Cualquier conflicto UNIQUE concurrente revierte todo (no quedan usuarios huerfanos)
        db.session.rollback()
        raise ErrorDominio(
            "Ya existe un medico registrado con ese correo electronico o matricula.",
            codigo="REGISTRO_MEDICO_DUPLICADO",
            http_status=409,
        ) from exc
    except SQLAlchemyError as exc:
        db.session.rollback()
        raise ErrorDominio(
            "Error temporal al registrar el medico. Intente nuevamente.",
            codigo="ERROR_BASE_DATOS",
            http_status=503,
            reintentable=True,
        ) from exc