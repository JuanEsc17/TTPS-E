"""Logica de negocio para el registro de medicos y consulta de especialidades."""
import re

from src.core.repos import medico_repo, usuario_repo
from src.core.services.excepciones import ErrorDominio
from src.core.services.seguridad import (
    hashear_password,
    sha256_hex,
    validar_politica_password,
)

_REGEX_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def listar_especialidades() -> list[dict]:
    """Retorna el catalogo de especialidades disponibles."""
    especialidades = medico_repo.listar_especialidades()
    return [{"id": esp.id, "nombre": esp.nombre} for esp in especialidades]


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