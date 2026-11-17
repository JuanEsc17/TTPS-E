"""Logica de negocio para el alta de pacientes (Escenarios 1 y 19)."""
import secrets
from datetime import date
from pathlib import Path

from src.clients.email_client import EmailClient
from src.clients.exceptions import ClienteError
from src.clients.familiograma_client import PARENTESCOS_POR_NOMBRE, FamiliogramaClient
from src.core.repos import clinica_repo, paciente_repo, usuario_repo
from src.core.services import clinica_service
from src.core.services.excepciones import ErrorDominio
from src.core.services.seguridad import hashear_password

_STORAGE_FAMILIOGRAMAS = Path("storage/familiogramas")


def _calcular_edad(fecha_nacimiento: date) -> int:
    hoy = date.today()
    return hoy.year - fecha_nacimiento.year - (
        (hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day)
    )


def _generar_password_temporal() -> str:
    # Sufijo "A1" garantiza que cumpla la politica de al menos una letra y un numero
    return f"{secrets.token_urlsafe(8)}A1"


def listar_pacientes_medico(usuario_actual_id: int) -> list[dict]:
    """Lista los pacientes registrados por el medico autenticado."""
    medico = paciente_repo.buscar_medico_por_usuario_id(usuario_actual_id)
    if medico is None:
        raise ErrorDominio(
            "Solo un medico tratante o gerente medico puede consultar pacientes.",
            codigo="FORBIDDEN_ROLE",
            http_status=403,
        )

    pacientes = paciente_repo.listar_pacientes_por_medico(medico.id)
    return [
        {
            "paciente_id": p.id,
            "dni": p.dni,
            "nombre": p.usuario.nombre,
            "apellido": p.usuario.apellido,
            "email": p.usuario.email,
            "diagnostico_presuntivo_id": p.diagnostico_presuntivo_id,
            "patologia_nombre": p.diagnostico_presuntivo.nombre,
            "tipo_sospecha": p.tipo_sospecha,
            "familiograma_pdf_path": p.familiograma_pdf_path,
        }
        for p in pacientes
    ]


def dar_de_alta_paciente(
    *,
    usuario_actual_id: int,
    datos: dict,
    familiograma_client: FamiliogramaClient | None = None,
    email_client: EmailClient | None = None,
) -> dict:
    """Registra un paciente (con familiares en E1 o sin ellos en E19)."""
    medico = paciente_repo.buscar_medico_por_usuario_id(usuario_actual_id)
    if medico is None:
        raise ErrorDominio(
            "Solo un medico tratante o gerente medico puede dar de alta pacientes.",
            codigo="FORBIDDEN_ROLE",
            http_status=403,
        )

    fecha_nac: date = datos["fecha_nacimiento"]
    if fecha_nac >= date.today():
        raise ErrorDominio(
            "La fecha de nacimiento debe ser anterior a hoy.",
            codigo="DATOS_PACIENTE_INVALIDOS",
            http_status=400,
        )

    edad = _calcular_edad(fecha_nac)
    responsable_nombre = (datos.get("responsable_nombre") or "").strip() or None
    responsable_dni = (datos.get("responsable_dni") or "").strip() or None
    if edad < 18 and (not responsable_nombre or not responsable_dni):
        raise ErrorDominio(
            "Para pacientes menores de 18 anos es obligatorio informar nombre y DNI del responsable.",
            codigo="DATOS_PACIENTE_INVALIDOS",
            http_status=400,
        )

    familiares_input = datos.get("familiares") or []
    sin_info_familiar = bool(datos.get("sin_informacion_familiar", False))
    if sin_info_familiar and familiares_input:
        raise ErrorDominio(
            "No puede marcar 'sin informacion familiar' y enviar familiares al mismo tiempo.",
            codigo="DATOS_PACIENTE_INVALIDOS",
            http_status=400,
        )

    dni = datos["dni"]
    email = datos["email"].lower()

    if paciente_repo.buscar_paciente_por_dni(dni) is not None or usuario_repo.buscar_por_email(email) is not None:
        raise ErrorDominio(
            "Ya existe un paciente registrado con ese DNI o email.",
            codigo="PACIENTE_DUPLICADO",
            http_status=409,
        )

    # Valida sintomas contra la patologia sospechada (regla cardinal o >= 2 secundarios)
    patologia, sintomas_paciente = clinica_service.validar_sintomas_contra_patologia(
        patologia_id=datos["diagnostico_presuntivo_id"],
        sintomas_snomed_ids=datos["sintomas_snomed_ids"],
    )

    # Prepara familiares y resuelve sus sintomas SNOMED locales si existen
    familiares_data: list[dict] = []
    for fam in familiares_input:
        sids = fam.get("sintomas_snomed_ids") or []
        sintomas_fam = clinica_repo.buscar_sintomas_por_snomed_ids(sids)
        familiares_data.append(
            {
                "parentesco": fam["parentesco"],
                "nombre": fam["nombre"],
                "diagnostico_previo": fam.get("diagnostico_previo"),
                "sintomas_ids": [s.id for s in sintomas_fam],
            }
        )

    # E1: solo si hay familiares genera el familiograma antes de confirmar el alta
    familiograma_path: str | None = None
    if familiares_input:
        cliente_fam = familiograma_client or FamiliogramaClient(timeout=10.0)
        personas = [
            {
                "parentesco": 0,  # 0 representa al paciente en la API de familiograma
                "nombre": datos["nombre"],
                "apellido": datos["apellido"],
                "edad": edad,
                "diagnosticos": [{"nombre": patologia.nombre}],
            }
        ]
        for fam in familiares_input:
            parentesco_id = PARENTESCOS_POR_NOMBRE.get(fam["parentesco"].strip().lower(), 1)
            personas.append(
                {
                    "parentesco": parentesco_id,
                    "nombre": fam["nombre"],
                    "apellido": datos["apellido"],
                    "diagnosticos": [{"nombre": fam["diagnostico_previo"]}] if fam.get("diagnostico_previo") else [],
                }
            )
        try:
            resp_fam = cliente_fam.generar_familiograma(personas)
            base64_img = (resp_fam.get("imagen") or {}).get("base64")
            if base64_img:
                destino = _STORAGE_FAMILIOGRAMAS / f"paciente_dni_{dni}.svg"
                cliente_fam.guardar_svg(base64_img, destino)
                familiograma_path = str(destino).replace("\\", "/")
        except ClienteError as exc:
            raise ErrorDominio(
                "No se pudo generar el familiograma del paciente. Intente nuevamente.",
                codigo="FAMILIOGRAMA_SERVICE_ERROR",
                http_status=502,
                reintentable=True,
            ) from exc

    password_temporal = _generar_password_temporal()
    password_hash = hashear_password(password_temporal)
    mensaje_aviso = (
        f"Bienvenido/a {datos['nombre']}. Sus credenciales iniciales son "
        f"Usuario: {email} | Contrasena temporal: {password_temporal}"
    )

    usuario, paciente = paciente_repo.crear_paciente_completo(
        medico_id=medico.id,
        dni=dni,
        nombre=datos["nombre"],
        apellido=datos["apellido"],
        telefono=datos["telefono"],
        email=email,
        password_hash=password_hash,
        fecha_nacimiento=fecha_nac,
        diagnostico_presuntivo_id=patologia.id,
        historia_clinica=datos["historia_clinica"],
        tipo_sospecha=datos["tipo_sospecha"],
        responsable_nombre=responsable_nombre,
        responsable_dni=responsable_dni,
        sintomas_ids=[s.id for s in sintomas_paciente],
        familiares_data=familiares_data,
        familiograma_pdf_path=familiograma_path,
        mensaje_aviso=mensaje_aviso,
    )

    # Envia credenciales iniciales por mail (si falla la red externa no revierte el alta)
    try:
        cliente_mail = email_client or EmailClient(timeout=5.0)
        cliente_mail.enviar_aviso(
            asunto="Alta de paciente - Credenciales iniciales",
            mensaje=mensaje_aviso,
            destinatarios=[email],
            referencia=f"paciente-{paciente.id}",
        )
    except ClienteError:
        pass

    return {
        "paciente_id": paciente.id,
        "usuario_id": usuario.id,
        "dni": paciente.dni,
        "nombre": usuario.nombre,
        "apellido": usuario.apellido,
        "email": usuario.email,
        "diagnostico_presuntivo_id": paciente.diagnostico_presuntivo_id,
        "tipo_sospecha": paciente.tipo_sospecha,
        "familiograma_pdf_path": paciente.familiograma_pdf_path,
        "debe_cambiar_password": usuario.debe_cambiar_password,
    }