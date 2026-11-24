"""Logica de negocio para el alta de usuarios por el admin general (Escenario 22 y 31)."""
import logging
import re
from typing import NoReturn
from src.core.models import Rol, Usuario
from src.core.repos import medico_repo, usuario_repo
from src.core.services.excepciones import (
    ErrorConflicto,
    ErrorDatosInvalidos,
    ErrorDominio,
    ErrorSinPermiso,
)
from src.core.services.seguridad import hashear_password, validar_politica_password


logger = logging.getLogger(__name__)
_REGEX_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_REGEX_TELEFONO = re.compile(r"^\+?[\d\s\-()]{7,20}$")  # mismo criterio que medico_service

def _validar_alta_por_admin(
    *,
    admin: Usuario,
    nombre: str,
    apellido: str,
    telefono: str,
    email: str,
    password: str,
) -> tuple[str, str, str, str]:
    """STEP 1 comun a las altas hechas por el admin general (Escenarios 22 y 31).

    Devuelve (nombre, apellido, telefono, email) normalizados.
    """
    # STEP 1a: solo el admin general puede dar de alta
    if admin.rol != Rol.ADMIN_GENERAL:
        raise ErrorSinPermiso(
            "Solo el admin general puede dar de alta usuarios.",
            codigo="SOLO_ADMIN_GENERAL",
        )

    # STEP 1b: limpiar y validar datos
    nombre, apellido, telefono = nombre.strip(), apellido.strip(), telefono.strip()
    email = email.strip().lower()
    if not all([nombre, apellido, telefono, email, password]):
        raise ErrorDatosInvalidos("Todos los campos son obligatorios.")
    if len(nombre) > 100:
        raise ErrorDatosInvalidos("El nombre no puede superar los 100 caracteres.")
    if len(apellido) > 100:
        raise ErrorDatosInvalidos("El apellido no puede superar los 100 caracteres.")
    if len(telefono) > 30:
        raise ErrorDatosInvalidos("El teléfono no puede superar los 30 caracteres.")
    if len(email) > 255:
        raise ErrorDatosInvalidos("El correo electrónico no puede superar los 255 caracteres.")
    if not _REGEX_TELEFONO.match(telefono):
        raise ErrorDatosInvalidos("El teléfono no tiene un formato válido.")
    if not _REGEX_EMAIL.match(email):
        raise ErrorDatosInvalidos("El correo electrónico no tiene un formato válido.")
    try:
        validar_politica_password(password)
    except ErrorDominio as exc:  # esa funcion lanza ErrorDominio con 400; la spec pide 422
        raise ErrorDatosInvalidos(exc.mensaje) from exc

    return nombre, apellido, telefono, email

def registrar_gerente_medico(
    *,
    admin: Usuario,
    nombre: str,
    apellido: str,
    telefono: str,
    email: str,
    password: str,
    matricula: str,
    especialidades_ids: list[int],
) -> dict:
    """Registra un gerente médico (Rol.GERENTE_MEDICO) con su perfil Medico y especialidades."""
    nombre, apellido, telefono, email = _validar_alta_por_admin(
        admin=admin,
        nombre=nombre,
        apellido=apellido,
        telefono=telefono,
        email=email,
        password=password,
    )
    # STEP 1c: datos propios del gerente medico
    matricula = matricula.strip()
    if not matricula:
        raise ErrorDatosInvalidos("Todos los campos son obligatorios.")
    if len(matricula) > 50:
        raise ErrorDatosInvalidos("La matrícula no puede superar los 50 caracteres.")
    ids_unicos = list(dict.fromkeys(especialidades_ids))  # saca repetidos
    if not ids_unicos:
        raise ErrorDatosInvalidos("Debe seleccionar al menos una especialidad.")
    logger.info("step=1_validacion_alta_gerente admin_id=%s email=%s matricula=%s",
                admin.id, email, matricula)

    # STEP 2: unicidad y existencia


    if usuario_repo.buscar_por_email(email) is not None:
        raise ErrorConflicto("El correo electrónico ya se encuentra registrado.",
                             codigo="EMAIL_YA_REGISTRADO")
    if medico_repo.buscar_medico_por_matricula(matricula) is not None:
        raise ErrorConflicto(
            "La matrícula profesional ingresada ya se encuentra registrada en el sistema.",
            codigo="MATRICULA_YA_REGISTRADA",
        )
    especialidades = medico_repo.buscar_especialidades_por_ids(ids_unicos)
    faltantes = set(ids_unicos) - {e.id for e in especialidades}
    if faltantes:
        raise ErrorDatosInvalidos(f"Especialidades inexistentes: {sorted(faltantes)}",
                                  codigo="ESPECIALIDAD_INEXISTENTE")
    # STEP 3: hashear y guardar en una transaccion
    usuario, medico = medico_repo.crear_gerente_medico_completo(
        nombre=nombre,
        apellido=apellido,
        telefono=telefono,
        email=email,
        password_hash=hashear_password(password),
        matricula=matricula,
        especialidades_ids=ids_unicos,
    )
    return {
        "usuario_id": usuario.id,
        "medico_id": medico.id,
        "rol": usuario.rol.value,
        "nombre": usuario.nombre,
        "apellido": usuario.apellido,
        "telefono": usuario.telefono,
        "email": usuario.email,
        "matricula": medico.matricula,
        "especialidades": [{"id": e.id, "nombre": e.nombre} for e in especialidades],
        "created_at": usuario.created_at.isoformat() if usuario.created_at else None,
    }

def registrar_administrativo(
    *,
    admin: Usuario,
    nombre: str,
    apellido: str,
    telefono: str,
    email: str,
    password: str,
) -> dict:
    """Registra un administrativo (Rol.ADMINISTRATIVO) (Escenario 22)."""
    # STEP 1: rol + validacion de datos (comun con el Escenario 31)
    nombre, apellido, telefono, email = _validar_alta_por_admin(
        admin=admin,
        nombre=nombre,
        apellido=apellido,
        telefono=telefono,
        email=email,
        password=password,
    )
    logger.info("step=1_validacion_alta_administrativo admin_id=%s email=%s",
                admin.id, email)

    # STEP 2: el email no puede estar usado por ningun usuario
    if usuario_repo.buscar_por_email(email) is not None:
        raise ErrorConflicto("El correo electrónico ya se encuentra registrado.",
                             codigo="EMAIL_YA_REGISTRADO")

    # STEP 3: hashear y guardar
    usuario = usuario_repo.crear_administrativo(
        nombre=nombre,
        apellido=apellido,
        telefono=telefono,
        email=email,
        password_hash=hashear_password(password),
    )
    return {
        "usuario_id": usuario.id,
        "rol": usuario.rol.value,
        "nombre": usuario.nombre,
        "apellido": usuario.apellido,
        "telefono": usuario.telefono,
        "email": usuario.email,
        "debe_cambiar_password": usuario.debe_cambiar_password,
        "created_at": usuario.created_at.isoformat() if usuario.created_at else None,
    }

def rechazar_baja_administrativo(*, admin: Usuario, usuario_id: int) -> NoReturn:
    """Regla LEL: el administrativo no puede darse de baja ni borrar su informacion."""
    logger.warning("intento_baja_solicitante admin_id=%s usuario_id=%s",
                   admin.id, usuario_id)
    raise ErrorSinPermiso(
        "El administrativo no puede darse de baja ni borrar su información.",
        codigo="BAJA_NO_PERMITIDA",
    )