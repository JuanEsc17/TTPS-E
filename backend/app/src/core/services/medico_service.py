"""Logica de negocio para medicos, directorio y consulta de especialidades."""
import logging
import re

from src.core.repos import medico_repo, paciente_repo, usuario_repo
from src.core.services.excepciones import ErrorDominio, ErrorNoEncontrado
from src.core.services.seguridad import (
    hashear_password,
    sha256_hex,
    validar_politica_password,
)

logger = logging.getLogger(__name__)
_REGEX_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_REGEX_TELEFONO = re.compile(r"^\+?[\d\s\-()]{7,20}$")


def listar_especialidades() -> list[dict]:
    """Retorna el catalogo de especialidades disponibles."""
    especialidades = medico_repo.listar_especialidades()
    return [{"id": esp.id, "nombre": esp.nombre} for esp in especialidades]


def listar_directorio_medicos_paciente(
    *,
    usuario_actual_id: int,
    q: str | None = None,
    especialidad_id: int | None = None,
) -> dict:
    """Retorna el directorio publico de medicos habilitados con estado de autorizacion del paciente."""
    paciente = paciente_repo.buscar_paciente_por_usuario_id(usuario_actual_id)
    if paciente is None:
        raise ErrorNoEncontrado(
            "No se encontro un perfil de paciente asociado a su cuenta.",
            codigo="PACIENTE_NO_ENCONTRADO",
        )

    activas = paciente_repo.listar_autorizaciones_activas(paciente.id)
    if activas or paciente_repo.tiene_historial_autorizaciones(paciente.id):
        ids_autorizados = sorted(a.medico_id for a in activas)
    elif paciente.medico_id is not None:
        ids_autorizados = [paciente.medico_id]
    else:
        ids_autorizados = []

    autorizados_set = set(ids_autorizados)
    filtro_q = (q or "").strip() or None
    medicos = medico_repo.listar_directorio_medicos(q=filtro_q, especialidad_id=especialidad_id)

    logger.info(
        "[paciente_service] STEP 1 directorio_medicos_consultado paciente_id=%s",
        paciente.id,
    )
    # Solo se exponen datos profesionales publicos (nunca email, telefono ni credenciales)
    return {
        "medicos": [
            {
                "medico_id": m.id,
                "nombre": m.usuario.nombre,
                "apellido": m.usuario.apellido,
                "nombre_completo": f"{m.usuario.nombre} {m.usuario.apellido}".strip(),
                "matricula": m.matricula,
                "especialidades": [
                    {"id": esp.id, "nombre": esp.nombre}
                    for esp in sorted(m.especialidades, key=lambda e: e.nombre.lower())
                ],
                "autorizado": m.id in autorizados_set,
                "es_medico_alta": m.id == paciente.medico_id,
            }
            for m in medicos
        ],
        "medicos_autorizados_activos_ids": ids_autorizados,
    }


def _validar_datos_medico(
    *,
    nombre: str,
    apellido: str,
    telefono: str,
    email: str,
    password: str,
    matricula: str,
    especialidades_ids: list[int],
) -> tuple[str, str, str, str, str, list[int]]:
    nombre_limpio = nombre.strip()
    apellido_limpio = apellido.strip()
    telefono_limpio = telefono.strip()
    email_limpio = email.strip().lower()
    matricula_limpia = matricula.strip()

    if not all([nombre_limpio, apellido_limpio, telefono_limpio, email_limpio, password, matricula_limpia]):
        raise ErrorDominio(
            "Todos los campos obligatorios del medico deben estar completos.",
            codigo="DATOS_MEDICO_INVALIDOS",
            http_status=400,
        )

    if not _REGEX_EMAIL.match(email_limpio):
        raise ErrorDominio(
            "El formato del correo electronico es invalido.",
            codigo="DATOS_MEDICO_INVALIDOS",
            http_status=400,
        )

    digitos_telefono = sum(c.isdigit() for c in telefono_limpio)
    if not _REGEX_TELEFONO.match(telefono_limpio) or digitos_telefono < 7:
        raise ErrorDominio(
            "El teléfono ingresado no es válido. Debe contener al menos 7 dígitos.",
            codigo="DATOS_MEDICO_INVALIDOS",
            http_status=400,
        )

    if len(matricula_limpia) > 50:
        raise ErrorDominio(
            "La matricula no puede superar los 50 caracteres.",
            codigo="DATOS_MEDICO_INVALIDOS",
            http_status=400,
        )

    # Exige >= 8 chars, al menos una letra y un numero (definido en seguridad.py)
    validar_politica_password(password, codigo="DATOS_MEDICO_INVALIDOS")

    # dict.fromkeys elimina IDs repetidos manteniendo el orden original
    ids_unicos = list(dict.fromkeys(especialidades_ids))
    if not ids_unicos:
        raise ErrorDominio(
            "Debe seleccionar al menos una especialidad medica.",
            codigo="DATOS_MEDICO_INVALIDOS",
            http_status=400,
        )

    return (
        nombre_limpio,
        apellido_limpio,
        telefono_limpio,
        email_limpio,
        matricula_limpia,
        ids_unicos,
    )


def registrar_medico(
    *,
    nombre: str,
    apellido: str,
    telefono: str,
    email: str,
    password: str,
    matricula: str,
    especialidades_ids: list[int],
    dispositivo_identificador: str | None = None,
) -> dict:
    """Registra un nuevo medico (Rol.MEDICO) con sus especialidades."""
    # STEP 1: Validacion de formato y campos obligatorios
    (
        nombre_limpio,
        apellido_limpio,
        telefono_limpio,
        email_limpio,
        matricula_limpia,
        ids_unicos,
    ) = _validar_datos_medico(
        nombre=nombre,
        apellido=apellido,
        telefono=telefono,
        email=email,
        password=password,
        matricula=matricula,
        especialidades_ids=especialidades_ids,
    )

    # STEP 2: Unicidad de email y matricula + existencia de especialidades
    if usuario_repo.buscar_por_email(email_limpio) is not None:
        raise ErrorDominio(
            "El correo electronico ya se encuentra registrado.",
            codigo="EMAIL_YA_REGISTRADO",
            http_status=409,
        )

    if medico_repo.buscar_medico_por_matricula(matricula_limpia) is not None:
        raise ErrorDominio(
            "La matricula ingresada ya pertenece a un medico registrado.",
            codigo="MATRICULA_YA_REGISTRADA",
            http_status=409,
        )

    # Comprueba que todos los IDs enviados existan realmente en el catalogo
    especialidades = medico_repo.buscar_especialidades_por_ids(ids_unicos)
    if len(especialidades) != len(ids_unicos):
        raise ErrorDominio(
            "Una o mas especialidades seleccionadas no existen.",
            codigo="ESPECIALIDAD_INEXISTENTE",
            http_status=422,
        )

    # STEP 3: Persistencia transaccional (hashea password y dispositivo antes de guardar)
    password_hash = hashear_password(password)
    dispositivo_hash = (
        sha256_hex(dispositivo_identificador)
        if dispositivo_identificador and dispositivo_identificador.strip()
        else None
    )

    usuario, medico = medico_repo.crear_medico_completo(
        nombre=nombre_limpio,
        apellido=apellido_limpio,
        telefono=telefono_limpio,
        email=email_limpio,
        password_hash=password_hash,
        matricula=matricula_limpia,
        especialidades_ids=ids_unicos,
        dispositivo_hash=dispositivo_hash,
    )

    return {
        "medico_id": medico.id,
        "usuario_id": usuario.id,
        "nombre": usuario.nombre,
        "apellido": usuario.apellido,
        "telefono": usuario.telefono,
        "email": usuario.email,
        "rol": usuario.rol.value,
        "matricula": medico.matricula,
        "especialidades": [{"id": esp.id, "nombre": esp.nombre} for esp in especialidades],
    }