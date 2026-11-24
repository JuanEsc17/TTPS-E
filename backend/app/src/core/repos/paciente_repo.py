"""Repositorio de acceso a datos para pacientes, familiares y autorizaciones medicas."""
from datetime import UTC, date, datetime

from sqlalchemy import exists, select
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
    PacienteMedicoAutorizado,
    PacienteSintoma,
    Rol,
    TipoAccionAuditoria,
    Usuario,
)
from src.core.repos import auditoria_repo
from src.core.services.excepciones import ErrorDominio


def buscar_medico_por_usuario_id(usuario_id: int) -> Medico | None:
    """Obtiene el perfil Medico asociado a un Usuario."""
    stmt = select(Medico).where(Medico.usuario_id == usuario_id)
    return db.session.scalar(stmt)


def buscar_paciente_por_usuario_id(
    usuario_id: int,
    *,
    bloquear: bool = False,
) -> Paciente | None:
    """Obtiene el perfil Paciente asociado a un Usuario."""
    stmt = (
        select(Paciente)
        .options(
            selectinload(Paciente.usuario),
            selectinload(Paciente.medico).selectinload(Medico.usuario),
            selectinload(Paciente.medico).selectinload(Medico.especialidades),
        )
        .where(Paciente.usuario_id == usuario_id)
    )
    if bloquear:
        stmt = stmt.with_for_update()
    return db.session.scalar(stmt)


def buscar_paciente_por_dni(dni: str) -> Paciente | None:
    """Busca un paciente por su DNI."""
    stmt = select(Paciente).where(Paciente.dni == dni)
    return db.session.scalar(stmt)


def listar_pacientes_por_medico(medico_id: int) -> list[Paciente]:
    """Lista los pacientes cuya historia clinica el medico tiene autorizacion vigente para ver."""
    tiene_autorizacion_activa = exists(
        select(1).where(
            PacienteMedicoAutorizado.paciente_id == Paciente.id,
            PacienteMedicoAutorizado.medico_id == medico_id,
            PacienteMedicoAutorizado.activa,
        )
    )
    sin_registros_autorizacion = ~exists(
        select(1).where(PacienteMedicoAutorizado.paciente_id == Paciente.id)
    )
    stmt = (
        select(Paciente)
        .options(selectinload(Paciente.usuario), selectinload(Paciente.diagnostico_presuntivo))
        .where(
            tiene_autorizacion_activa
            | ((Paciente.medico_id == medico_id) & sin_registros_autorizacion)
        )
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
    otorgada_por_usuario_id: int | None = None,
    ip_origen: str | None = None,
) -> tuple[Usuario, Paciente]:
    """Crea Usuario, Paciente, autorizacion inicial, sintomas, familiares, auditoria y Aviso."""
    try:
        ahora = datetime.now(UTC).replace(tzinfo=None)
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

        responsable_uid = otorgada_por_usuario_id
        if responsable_uid is None:
            medico = db.session.get(Medico, medico_id)
            responsable_uid = medico.usuario_id if medico is not None else usuario.id

        # Siembra la autorizacion inicial del medico tratante que realiza el alta (ADR-002 / Esc. 40)
        db.session.add(
            PacienteMedicoAutorizado(
                paciente_id=paciente.id,
                medico_id=medico_id,
                otorgada_por_usuario_id=responsable_uid,
                activa=True,
                otorgada_en=ahora,
                revocada_en=None,
            )
        )

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

        auditoria_repo.registrar_modificacion(
            entidad_tipo=EntidadAuditable.PACIENTE,
            entidad_id=paciente.id,
            accion=TipoAccionAuditoria.CREACION,
            usuario_id=responsable_uid,
            origen="usuario",
            cambios={
                "dni": {"anterior": None, "nuevo": dni},
                "medico_id": {"anterior": None, "nuevo": medico_id},
                "medicos_autorizados_ids": {"anterior": [], "nuevo": [medico_id]},
            },
            motivo="Alta de paciente",
            ip_origen=ip_origen,
        )

        db.session.add(
            Aviso(
                usuario_id=usuario.id,
                mensaje=mensaje_aviso[:500],
                leido=False,
                canal=CanalAviso.MAIL,
                enviado=True,
                enviado_en=ahora,
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


def buscar_paciente_con_historia_clinica(paciente_id: int) -> Paciente | None:
    """Obtiene el paciente con toda la informacion clinica para consulta medica autorizada."""
    stmt = (
        select(Paciente)
        .options(
            selectinload(Paciente.usuario),
            selectinload(Paciente.diagnostico_presuntivo),
            selectinload(Paciente.sintomas),
            selectinload(Paciente.familiares).selectinload(Familiar.sintomas),
            selectinload(Paciente.medico).selectinload(Medico.usuario),
            selectinload(Paciente.medico).selectinload(Medico.especialidades),
        )
        .where(Paciente.id == paciente_id)
    )
    return db.session.scalar(stmt)


def tiene_historial_autorizaciones(paciente_id: int) -> bool:
    """Indica si el paciente ya posee al menos una fila (activa o revocada) en autorizaciones."""
    stmt = select(exists().where(PacienteMedicoAutorizado.paciente_id == paciente_id))
    return bool(db.session.scalar(stmt))


def medico_tiene_autorizacion_activa(paciente_id: int, medico_id: int) -> bool:
    """Indica si existe una autorizacion activa para el par (paciente_id, medico_id)."""
    stmt = select(
        exists().where(
            PacienteMedicoAutorizado.paciente_id == paciente_id,
            PacienteMedicoAutorizado.medico_id == medico_id,
            PacienteMedicoAutorizado.activa,
        )
    )
    return bool(db.session.scalar(stmt))


def medico_esta_autorizado_historia_clinica(paciente: Paciente, medico_id: int) -> bool:
    """Valida autorizacion activa con compatibilidad transitoria si aun no hay filas sembradas."""
    if medico_tiene_autorizacion_activa(paciente.id, medico_id):
        return True
    if tiene_historial_autorizaciones(paciente.id):
        return False
    return paciente.medico_id == medico_id


def listar_autorizaciones_activas(paciente_id: int) -> list[PacienteMedicoAutorizado]:
    """Devuelve las autorizaciones vigentes de un paciente con perfil y especialidades del medico."""
    stmt = (
        select(PacienteMedicoAutorizado)
        .options(
            selectinload(PacienteMedicoAutorizado.medico).selectinload(Medico.usuario),
            selectinload(PacienteMedicoAutorizado.medico).selectinload(Medico.especialidades),
        )
        .where(
            PacienteMedicoAutorizado.paciente_id == paciente_id,
            PacienteMedicoAutorizado.activa,
        )
        .order_by(PacienteMedicoAutorizado.otorgada_en.asc(), PacienteMedicoAutorizado.id.asc())
    )
    return list(db.session.scalars(stmt).all())


def buscar_autorizacion_activa(
    paciente_id: int,
    medico_id: int,
    *,
    bloquear: bool = False,
) -> PacienteMedicoAutorizado | None:
    """Obtiene la autorizacion activa puntual de un medico sobre un paciente."""
    stmt = (
        select(PacienteMedicoAutorizado)
        .options(
            selectinload(PacienteMedicoAutorizado.medico).selectinload(Medico.usuario),
            selectinload(PacienteMedicoAutorizado.medico).selectinload(Medico.especialidades),
        )
        .where(
            PacienteMedicoAutorizado.paciente_id == paciente_id,
            PacienteMedicoAutorizado.medico_id == medico_id,
            PacienteMedicoAutorizado.activa,
        )
    )
    if bloquear:
        stmt = stmt.with_for_update()
    return db.session.scalar(stmt)


def asegurar_autorizacion_inicial_si_vacio(
    paciente: Paciente,
    *,
    otorgada_en: datetime,
) -> PacienteMedicoAutorizado | None:
    """Materializa la autorizacion inicial del medico de alta en pacientes anteriores a la migracion."""
    if tiene_historial_autorizaciones(paciente.id) or paciente.medico_id is None:
        return None
    otorgada_por_uid = (
        paciente.medico.usuario_id if paciente.medico is not None else paciente.usuario_id
    )
    autorizacion = PacienteMedicoAutorizado(
        paciente_id=paciente.id,
        medico_id=paciente.medico_id,
        otorgada_por_usuario_id=otorgada_por_uid,
        activa=True,
        otorgada_en=otorgada_en,
        revocada_en=None,
    )
    db.session.add(autorizacion)
    db.session.flush()
    return autorizacion


def crear_autorizacion_medico(
    *,
    paciente_id: int,
    medico_id: int,
    otorgada_por_usuario_id: int,
    otorgada_en: datetime,
) -> PacienteMedicoAutorizado:
    """Inserta una nueva autorizacion activa dentro de la transaccion en curso."""
    autorizacion = PacienteMedicoAutorizado(
        paciente_id=paciente_id,
        medico_id=medico_id,
        otorgada_por_usuario_id=otorgada_por_usuario_id,
        activa=True,
        otorgada_en=otorgada_en,
        revocada_en=None,
    )
    db.session.add(autorizacion)
    db.session.flush()
    return autorizacion


def crear_aviso_app(
    *,
    usuario_id: int,
    mensaje: str,
    enviado_en: datetime,
) -> Aviso:
    """Registra un aviso in-app en la sesion actual."""
    aviso = Aviso(
        usuario_id=usuario_id,
        mensaje=mensaje[:500],
        leido=False,
        canal=CanalAviso.APP,
        enviado=True,
        enviado_en=enviado_en,
    )
    db.session.add(aviso)
    db.session.flush()
    return aviso


def guardar_cambios() -> None:
    """Confirma la transaccion activa."""
    db.session.commit()


def deshacer_cambios() -> None:
    """Revierte la transaccion activa."""
    db.session.rollback()


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