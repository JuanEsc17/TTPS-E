"""Repositorio de acceso a datos para pacientes y familiares."""
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import selectinload
from src.core.database import db
from src.core.models import (
    Aviso,
    CanalAviso,
    EntidadAuditable,
    Familiar,
    FamiliarSintoma,
    Medico,
    Paciente,
    PacienteSintoma,
    Rol,
    TipoAccionAuditoria,
    Usuario,
)
from src.core.services import auditoria_service
from src.core.services.excepciones import ErrorDominio


def buscar_medico_por_usuario_id(usuario_id: int) -> Medico | None:
    """Obtiene el perfil Medico asociado a un Usuario."""
    stmt = select(Medico).where(Medico.usuario_id == usuario_id)
    return db.session.scalar(stmt)


def buscar_paciente_por_dni(dni: str) -> Paciente | None:
    """Busca un paciente por su DNI."""
    stmt = select(Paciente).where(Paciente.dni == dni)
    return db.session.scalar(stmt)


def listar_pacientes_por_medico(medico_id: int) -> list[Paciente]:
    """Lista los pacientes dados de alta por un medico."""
    stmt = (
        select(Paciente)
        .options(selectinload(Paciente.usuario), selectinload(Paciente.diagnostico_presuntivo))
        .where(Paciente.medico_id == medico_id)
        .order_by(Paciente.id.desc())
    )
    return list(db.session.scalars(stmt).all())


def crear_paciente_completo(
    *,
    medico_id: int,
    dni: str,
    nombre: str,
    apellido: str,
    telefono: str,
    email: str,
    password_hash: str,
    fecha_nacimiento: date,
    diagnostico_presuntivo_id: int,
    historia_clinica: str,
    tipo_sospecha: str,
    responsable_nombre: str | None,
    responsable_dni: str | None,
    sintomas_ids: list[int],
    familiares_data: list[dict],
    familiograma_pdf_path: str | None,
    mensaje_aviso: str,
) -> tuple[Usuario, Paciente]:
    """Crea Usuario, Paciente, sintomas, familiares y Aviso en una sola transaccion."""
    try:
        usuario = Usuario(
            email=email,
            password_hash=password_hash,
            rol=Rol.PACIENTE,
            nombre=nombre,
            apellido=apellido,
            telefono=telefono,
            # El paciente debe cambiar la clave temporal en su primer ingreso (E20)
            debe_cambiar_password=True,
        )
        db.session.add(usuario)
        db.session.flush()

        paciente = Paciente(
            usuario_id=usuario.id,
            medico_id=medico_id,
            dni=dni,
            fecha_nacimiento=fecha_nacimiento,
            diagnostico_presuntivo_id=diagnostico_presuntivo_id,
            historia_clinica=historia_clinica,
            tipo_sospecha=tipo_sospecha,
            familiograma_pdf_path=familiograma_pdf_path,
            responsable_nombre=responsable_nombre,
            responsable_dni=responsable_dni,
        )
        db.session.add(paciente)
        db.session.flush()

        for sintoma_id in sintomas_ids:
            db.session.add(PacienteSintoma(paciente_id=paciente.id, sintoma_id=sintoma_id))

        # Si hay familiares (E1), los inserta junto con sus sintomas; si esta vacio (E19), lo omite
        for fam in familiares_data:
            familiar = Familiar(
                paciente_id=paciente.id,
                parentesco=fam["parentesco"],
                nombre=fam["nombre"],
                diagnostico_previo=fam.get("diagnostico_previo"),
            )
            db.session.add(familiar)
            db.session.flush()
            for sid in fam.get("sintomas_ids", []):
                db.session.add(FamiliarSintoma(familiar_id=familiar.id, sintoma_id=sid))

        db.session.add(
            Aviso(
                usuario_id=usuario.id,
                mensaje=mensaje_aviso[:500],
                leido=False,
                canal=CanalAviso.MAIL,
                enviado=True,
                enviado_en=datetime.now(UTC).replace(tzinfo=None),
            )
        )

        db.session.commit()
        return usuario, paciente
    except IntegrityError as exc:
        db.session.rollback()
        raise ErrorDominio(
            "Ya existe un paciente registrado con ese DNI o correo electronico.",
            codigo="PACIENTE_DUPLICADO",
            http_status=409,
        ) from exc
    except SQLAlchemyError as exc:
        db.session.rollback()
        raise ErrorDominio(
            "Error temporal al registrar el paciente. Intente nuevamente.",
            codigo="ERROR_BASE_DATOS",
            http_status=503,
            reintentable=True,
        ) from exc

def buscar_paciente_por_id(paciente_id: int) -> Paciente | None:
    """Obtiene un paciente por ID junto con usuario, patologia, familiares y sus sintomas."""
    stmt = (
        select(Paciente)
        .options(
            selectinload(Paciente.usuario),
            selectinload(Paciente.diagnostico_presuntivo),
            selectinload(Paciente.familiares).selectinload(Familiar.sintomas),
        )
        .where(Paciente.id == paciente_id)
    )
    return db.session.scalar(stmt)


def reemplazar_familiares(
    paciente: Paciente,
    familiares_data: list[dict],
    familiograma_pdf_path: str | None,
) -> Paciente:
    """Reemplaza la nomina de familiares del paciente y actualiza la ruta del familiograma."""
    try:
        # cascade="all, delete-orphan" elimina los familiares previos al limpiar la lista
        paciente.familiares.clear()
        db.session.flush()

        for fam in familiares_data:
            familiar = Familiar(
                paciente_id=paciente.id,
                parentesco=fam["parentesco"],
                nombre=fam["nombre"],
                diagnostico_previo=fam.get("diagnostico_previo"),
            )
            db.session.add(familiar)
            db.session.flush()
            for sid in fam.get("sintomas_ids", []):
                db.session.add(FamiliarSintoma(familiar_id=familiar.id, sintoma_id=sid))

        paciente.familiograma_pdf_path = familiograma_pdf_path
        db.session.commit()
        return paciente
    except SQLAlchemyError as exc:
        db.session.rollback()
        raise ErrorDominio(
            "Error temporal al actualizar la informacion familiar. Intente nuevamente.",
            codigo="ERROR_BASE_DATOS",
            http_status=503,
            reintentable=True,
        ) from exc

def actualizar_historia_clinica(
    paciente: Paciente,
    nueva_historia: str,
    *,
    usuario_id: int,
) -> Paciente:
    """Actualiza historia_clinica del paciente y registra auditoria en la misma transaccion."""
    try:
        anterior = paciente.historia_clinica
        paciente.historia_clinica = nueva_historia
        auditoria_service.registrar_modificacion(
            entidad_tipo=EntidadAuditable.PACIENTE,
            entidad_id=paciente.id,
            accion=TipoAccionAuditoria.MODIFICACION,
            cambios={"historia_clinica": {"anterior": anterior, "nuevo": nueva_historia}},
            usuario_id=usuario_id,
        )
        db.session.commit()
        return paciente
    except SQLAlchemyError as exc:
        db.session.rollback()
        raise ErrorDominio(
            "Error temporal al guardar la historia clinica. Intente nuevamente.",
            codigo="ERROR_BASE_DATOS",
            http_status=503,
            reintentable=True,
        ) from exc