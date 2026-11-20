"""Logica de negocio para el alta de usuarios por el admin general (Escenario 31)."""
import logging
import re

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
    # STEP 1a: solo el admin general puede dar de alta
    if admin.rol != Rol.ADMIN_GENERAL:
        raise ErrorSinPermiso(
            "Solo el admin general puede registrar gerentes médicos.",
            codigo="SOLO_ADMIN_GENERAL",
        )

    # STEP 1b: limpiar y validar datos
    nombre, apellido, telefono = nombre.strip(), apellido.strip(), telefono.strip()
    email = email.strip().lower()
    matricula = matricula.strip()
    if not all([nombre, apellido, telefono, email, password, matricula]):
        raise ErrorDatosInvalidos("Todos los campos son obligatorios.")
    if not _REGEX_EMAIL.match(email):
        raise ErrorDatosInvalidos("El correo electrónico no tiene un formato válido.")
    if len(matricula) > 50:
        raise ErrorDatosInvalidos("La matrícula no puede superar los 50 caracteres.")
    try:
        validar_politica_password(password)
    except ErrorDominio as exc:  # esa funcion lanza ErrorDominio con 400; la spec pide 422
        raise ErrorDatosInvalidos(exc.mensaje) from exc
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
