"""Logica de negocio para pacientes, familiares y autorizaciones de historia clinica (Esc. 1, 18, 19, 40)."""
import logging
import secrets
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from src.clients.email_client import EmailClient
from src.clients.exceptions import ClienteError
from src.clients.familiograma_client import PARENTESCOS_POR_NOMBRE, FamiliogramaClient
from src.clients.transcriptor_client import TranscriptorClient
from src.core.models import (
    EntidadAuditable,
    Medico,
    Paciente,
    PacienteMedicoAutorizado,
    TipoAccionAuditoria,
)
from src.core.repos import clinica_repo, medico_repo, paciente_repo, usuario_repo
from src.core.services import auditoria_service, clinica_service
from src.core.services.excepciones import (
    ErrorBaseDatos,
    ErrorConflicto,
    ErrorDatosInvalidos,
    ErrorDominio,
    ErrorNoEncontrado,
    ErrorSinPermiso,
)
from src.core.services.formato_correo import asunto_correo, formatear_correo
from src.core.services.seguridad import hashear_password

logger = logging.getLogger(__name__)
_STORAGE_FAMILIOGRAMAS = Path("storage/familiogramas")


def _ahora_utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _calcular_edad(fecha_nacimiento: date) -> int:
    hoy = date.today()
    return hoy.year - fecha_nacimiento.year - (
        (hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day)
    )


def _generar_password_temporal() -> str:
    # Sufijo "A1" garantiza que cumpla la politica de al menos una letra y un numero
    return f"{secrets.token_urlsafe(8)}A1"

def _inferir_sexo_parentesco(parentesco: str) -> str | None:
    p = parentesco.strip().lower()
    if any(k in p for k in ("padre", "abuelo", "tio", "tío", "primo", "hermano", "hijo")):
        return "hombre"
    if any(k in p for k in ("madre", "abuela", "tia", "tía", "prima", "hermana", "hija")):
        return "mujer"
    return None


def _extraer_detalle_familiograma(respuesta: object) -> str:
    if isinstance(respuesta, dict):
        err = respuesta.get("error")
        if isinstance(err, dict):
            detalles = err.get("detalles")
            if isinstance(detalles, list) and detalles:
                msgs = [d.get("mensaje") for d in detalles if isinstance(d, dict) and d.get("mensaje")]
                if msgs:
                    return " ".join(msgs)
            if err.get("mensaje"):
                return str(err["mensaje"])
    return ""


def _generar_svg_familiograma(
    *,
    nombre_paciente: str,
    apellido_paciente: str,
    edad_paciente: int,
    patologia_nombre: str,
    familiares_input: list[dict],
    archivo_nombre: str,
    familiograma_client: FamiliogramaClient | None = None,
) -> str | None:
    """Invoca la API externa de familiograma y guarda el SVG resultante en disco."""
    cliente_fam = familiograma_client or FamiliogramaClient(timeout=10.0)
    personas = [
        {
            "parentesco": 0,  # 0 representa al paciente en la API de familiograma
            "nombre": nombre_paciente,
            "apellido": apellido_paciente,
            "edad": edad_paciente,
            "diagnosticos": [{"codigo": patologia_nombre.upper(), "nombre": patologia_nombre}],
        }
    ]
    for fam in familiares_input:
        clave_par = fam["parentesco"].strip().lower().replace("í", "i").replace("ó", "o")
        parentesco_id = PARENTESCOS_POR_NOMBRE.get(clave_par, 1)
        persona_fam: dict = {
            "parentesco": parentesco_id,
            "nombre": fam["nombre"],
            "apellido": apellido_paciente,
        }
        sexo = _inferir_sexo_parentesco(clave_par)
        if sexo:
            persona_fam["sexo"] = sexo
        if fam.get("diagnostico_previo"):
            diag = fam["diagnostico_previo"].strip()
            persona_fam["diagnosticos"] = [{"codigo": diag.upper()[:30], "nombre": diag}]
        personas.append(persona_fam)

    try:
        resp_fam = cliente_fam.generar_familiograma(personas)
        base64_img = (resp_fam.get("imagen") or {}).get("base64")
        if not base64_img:
            return None
        destino = _STORAGE_FAMILIOGRAMAS / archivo_nombre
        cliente_fam.guardar_svg(base64_img, destino)
        return str(destino).replace("\\", "/")
    except ClienteError as exc:
        detalle = _extraer_detalle_familiograma(exc.respuesta)
        mensaje = (
            f"No se pudo generar el familiograma: {detalle}"
            if detalle
            else f"No se pudo generar el familiograma del paciente: {exc}"
        )
        raise ErrorDominio(
            mensaje,
            codigo="FAMILIOGRAMA_SERVICE_ERROR",
            http_status=422 if exc.codigo_http == 422 else 502,
            reintentable=exc.codigo_http != 422,
        ) from exc

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
            "es_medico_alta": p.medico_id == medico.id,
        }
        for p in pacientes
    ]


def dar_de_alta_paciente(
    *,
    usuario_actual_id: int,
    datos: dict,
    familiograma_client: FamiliogramaClient | None = None,
    email_client: EmailClient | None = None,
    ip_origen: str | None = None,
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
        familiograma_path = _generar_svg_familiograma(
            nombre_paciente=datos["nombre"],
            apellido_paciente=datos["apellido"],
            edad_paciente=edad,
            patologia_nombre=patologia.nombre,
            familiares_input=familiares_input,
            archivo_nombre=f"paciente_dni_{dni}.svg",
            familiograma_client=familiograma_client,
        )

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
        otorgada_por_usuario_id=usuario_actual_id,
        ip_origen=ip_origen,
    )

    # Envia credenciales iniciales por mail (si falla la red externa no revierte el alta)
    cuerpo_mail = formatear_correo(
        titulo="Bienvenido/a al portal de pacientes",
        saludo=f"Hola {datos['nombre']} {datos['apellido']},",
        introduccion=(
            "Tu médico tratante registró tu cuenta en el Sistema de Seguimiento "
            "de Estudios de Exoma Clínico."
        ),
        destacado=[
            f"Usuario: {email}",
            f"Contraseña temporal: {password_temporal}",
        ],
        secciones=[
            (
                "Próximos pasos",
                [
                    "Ingresá al portal utilizando tu correo electrónico y la contraseña temporal.",
                    "En tu primer inicio de sesión deberás establecer una contraseña personal.",
                ],
            )
        ],
        cierre="Ante cualquier consulta, comunicate con tu médico tratante.",
    )
    try:
        cliente_mail = email_client or EmailClient(timeout=5.0)
        cliente_mail.enviar_aviso(
            asunto=asunto_correo("Alta de paciente · Credenciales iniciales"),
            mensaje=cuerpo_mail,
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

def _serializar_familiares(familiares: list) -> list[dict]:
    return [
        {
            "id": f.id,
            "nombre": f.nombre,
            "parentesco": f.parentesco,
            "diagnostico_previo": f.diagnostico_previo,
            "sintomas": [
                {"id": s.id, "snomed_id": s.snomed_id, "descripcion": s.descripcion}
                for s in f.sintomas
            ],
        }
        for f in familiares
    ]


def obtener_familiares_paciente(*, usuario_actual_id: int, paciente_id: int) -> dict:
    """Devuelve los familiares registrados de un paciente y la URL del familiograma."""
    medico = paciente_repo.buscar_medico_por_usuario_id(usuario_actual_id)
    if medico is None:
        raise ErrorDominio(
            "Solo un medico tratante o gerente medico puede consultar familiares.",
            codigo="FORBIDDEN_ROLE",
            http_status=403,
        )

    paciente = paciente_repo.buscar_paciente_por_id(paciente_id)
    if paciente is None:
        raise ErrorDominio(
            "El paciente indicado no existe.",
            codigo="PACIENTE_NO_ENCONTRADO",
            http_status=404,
        )
    if not paciente_repo.medico_esta_autorizado_historia_clinica(paciente, medico.id):
        raise ErrorSinPermiso(
            "No posee autorizacion vigente para consultar la informacion clinica de este paciente.",
            codigo="HISTORIA_CLINICA_NO_AUTORIZADA",
        )

    return {
        "paciente_id": paciente.id,
        "nombre_completo": f"{paciente.usuario.nombre} {paciente.usuario.apellido}",
        "familiares": _serializar_familiares(paciente.familiares),
        "familiograma_generado": bool(paciente.familiograma_pdf_path),
        "familiograma_pdf_path": paciente.familiograma_pdf_path,
        "familiograma_url": f"/api/v1/pacientes/{paciente.id}/familiograma"
        if paciente.familiograma_pdf_path
        else None,
    }


def gestionar_informacion_familiar(
    *,
    usuario_actual_id: int,
    paciente_id: int,
    familiares_input: list[dict],
    familiograma_client: FamiliogramaClient | None = None,
) -> dict:
    """Registra o actualiza los familiares de un paciente y regenera el familiograma (E18)."""
    medico = paciente_repo.buscar_medico_por_usuario_id(usuario_actual_id)
    if medico is None:
        raise ErrorDominio(
            "Solo un medico tratante o gerente medico puede gestionar informacion familiar.",
            codigo="FORBIDDEN_ROLE",
            http_status=403,
        )

    paciente = paciente_repo.buscar_paciente_por_id(paciente_id)
    if paciente is None:
        raise ErrorDominio(
            "El paciente indicado no existe.",
            codigo="PACIENTE_NO_ENCONTRADO",
            http_status=404,
        )
    if not paciente_repo.medico_esta_autorizado_historia_clinica(paciente, medico.id):
        raise ErrorSinPermiso(
            "No posee autorizacion vigente para gestionar informacion familiar de este paciente.",
            codigo="HISTORIA_CLINICA_NO_AUTORIZADA",
        )

    familiares_data: list[dict] = []
    for fam in familiares_input:
        nombre_fam = (fam.get("nombre") or "").strip()
        parentesco_fam = (fam.get("parentesco") or "").strip()
        diag_fam = (fam.get("diagnostico_previo") or "").strip() or None
        if not nombre_fam or not parentesco_fam:
            raise ErrorDominio(
                "Cada familiar debe tener nombre y parentesco.",
                codigo="DATOS_FAMILIARES_INVALIDOS",
                http_status=400,
            )

        sids = list(dict.fromkeys(str(s).strip() for s in (fam.get("sintomas_snomed_ids") or []) if str(s).strip()))
        sintomas_fam = clinica_repo.buscar_sintomas_por_snomed_ids(sids)
        if len(sintomas_fam) != len(sids):
            raise ErrorDominio(
                "Uno o mas sintomas SNOMED indicados para el familiar no existen en el catalogo.",
                codigo="DATOS_FAMILIARES_INVALIDOS",
                http_status=400,
            )

        familiares_data.append(
            {
                "parentesco": parentesco_fam,
                "nombre": nombre_fam,
                "diagnostico_previo": diag_fam,
                "sintomas_ids": [s.id for s in sintomas_fam],
            }
        )

    familiograma_path: str | None = None
    if familiares_input:
        familiograma_path = _generar_svg_familiograma(
            nombre_paciente=paciente.usuario.nombre,
            apellido_paciente=paciente.usuario.apellido,
            edad_paciente=_calcular_edad(paciente.fecha_nacimiento),
            patologia_nombre=paciente.diagnostico_presuntivo.nombre,
            familiares_input=familiares_input,
            archivo_nombre=f"paciente_{paciente.id}.svg",
            familiograma_client=familiograma_client,
        )

    paciente_repo.reemplazar_familiares(paciente, familiares_data, familiograma_path)
    paciente_actualizado = paciente_repo.buscar_paciente_por_id(paciente.id)

    return {
        "paciente_id": paciente.id,
        "familiares": _serializar_familiares(paciente_actualizado.familiares if paciente_actualizado else []),
        "familiograma_generado": bool(familiograma_path),
        "familiograma_pdf_path": familiograma_path,
        "familiograma_url": f"/api/v1/pacientes/{paciente.id}/familiograma" if familiograma_path else None,
    }


def obtener_archivo_familiograma(*, usuario_actual_id: int, paciente_id: int) -> Path:
    """Devuelve la ruta en disco del SVG del familiograma de un paciente."""
    medico = paciente_repo.buscar_medico_por_usuario_id(usuario_actual_id)
    if medico is None:
        raise ErrorDominio(
            "Solo un medico tratante o gerente medico puede ver el familiograma.",
            codigo="FORBIDDEN_ROLE",
            http_status=403,
        )

    paciente = paciente_repo.buscar_paciente_por_id(paciente_id)
    if paciente is None:
        raise ErrorDominio(
            "El paciente indicado no existe.",
            codigo="PACIENTE_NO_ENCONTRADO",
            http_status=404,
        )
    if not paciente_repo.medico_esta_autorizado_historia_clinica(paciente, medico.id):
        raise ErrorSinPermiso(
            "No posee autorizacion vigente para consultar el familiograma de este paciente.",
            codigo="HISTORIA_CLINICA_NO_AUTORIZADA",
        )

    if not paciente.familiograma_pdf_path:
        raise ErrorDominio(
            "El paciente no tiene un familiograma generado.",
            codigo="FAMILIOGRAMA_NO_DISPONIBLE",
            http_status=404,
        )

    ruta = Path(paciente.familiograma_pdf_path).resolve()
    if not ruta.is_file():
        raise ErrorDominio(
            "El archivo del familiograma no se encontro en el servidor.",
            codigo="FAMILIOGRAMA_NO_DISPONIBLE",
            http_status=404,
        )
    return ruta

_MAX_AUDIO_BYTES = 15 * 1024 * 1024
_AUDIO_MIMES_PERMITIDOS = {
    "audio/webm",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/ogg",
}


def transcribir_historia_clinica(
    *,
    usuario_actual_id: int,
    audio_bytes: bytes,
    content_type: str,
    filename: str = "historia_clinica.webm",
    paciente_id: int | None = None,
    transcriptor_client: TranscriptorClient | None = None,
) -> dict:
    """Valida un archivo de audio, lo transcribe a texto y opcionalmente lo guarda (E35)."""
    medico = paciente_repo.buscar_medico_por_usuario_id(usuario_actual_id)
    if medico is None:
        raise ErrorDominio(
            "Solo un medico tratante o gerente medico puede grabar historias clinicas.",
            codigo="ROL_NO_AUTORIZADO",
            http_status=403,
        )

    if not audio_bytes:
        raise ErrorDominio(
            "El archivo de audio esta vacio.",
            codigo="AUDIO_VACIO",
            http_status=422,
        )

    if len(audio_bytes) > _MAX_AUDIO_BYTES:
        raise ErrorDominio(
            "La grabacion supera el limite maximo de 15 MB.",
            codigo="AUDIO_EXCEDE_LIMITE",
            http_status=413,
        )

    mime_base = (content_type or "").split(";", 1)[0].strip().lower()
    if mime_base not in _AUDIO_MIMES_PERMITIDOS:
        raise ErrorDominio(
            "Formato de audio no soportado. Use webm, wav, mp3, mp4 u ogg.",
            codigo="FORMATO_AUDIO_NO_SOPORTADO",
            http_status=415,
        )

    paciente = None
    if paciente_id is not None:
        paciente = paciente_repo.buscar_paciente_por_id(paciente_id)
        if paciente is None:
            raise ErrorDominio(
                "El paciente indicado no existe.",
                codigo="PACIENTE_NO_ENCONTRADO",
                http_status=404,
            )
        if paciente.medico_id != medico.id:
            raise ErrorDominio(
                "No tiene permiso para modificar la historia clinica de este paciente.",
                codigo="PACIENTE_AJENO",
                http_status=403,
            )

    cliente = transcriptor_client or TranscriptorClient()
    try:
        texto = cliente.transcribir(
            audio_bytes=audio_bytes,
            content_type=mime_base,
            filename=filename,
        )
    except ClienteError as exc:
        raise ErrorDominio(
            f"El transcriptor de audio no se encuentra disponible: {exc}",
            codigo="TRANSCRIPTOR_NO_DISPONIBLE",
            http_status=502,
            reintentable=True,
        ) from exc

    texto_limpio = " ".join(texto.split())
    if not texto_limpio:
        raise ErrorDominio(
            "No se detecto voz clara en la grabacion enviada. Intente grabar nuevamente.",
            codigo="AUDIO_SIN_VOZ_DETECTADA",
            http_status=422,
            reintentable=True,
        )

    guardado = False
    if paciente is not None:
        paciente_repo.actualizar_historia_clinica(
            paciente,
            texto_limpio,
            usuario_id=usuario_actual_id,
        )
        guardado = True

    return {
        "paciente_id": paciente.id if paciente else None,
        "historia_clinica": texto_limpio,
        "guardado_en_bd": guardado,
    }


def actualizar_historia_clinica_paciente(
    *,
    usuario_actual_id: int,
    paciente_id: int,
    historia_clinica: str,
) -> dict:
    """Guarda o actualiza la historia clinica de un paciente existente (E35)."""
    medico = paciente_repo.buscar_medico_por_usuario_id(usuario_actual_id)
    if medico is None:
        raise ErrorDominio(
            "Solo un medico tratante o gerente medico puede actualizar la historia clinica.",
            codigo="ROL_NO_AUTORIZADO",
            http_status=403,
        )

    paciente = paciente_repo.buscar_paciente_por_id(paciente_id)
    if paciente is None:
        raise ErrorDominio(
            "El paciente indicado no existe.",
            codigo="PACIENTE_NO_ENCONTRADO",
            http_status=404,
        )
    if paciente.medico_id != medico.id:
        raise ErrorDominio(
            "No tiene permiso para modificar la historia clinica de este paciente.",
            codigo="PACIENTE_AJENO",
            http_status=403,
        )

    texto_limpio = (historia_clinica or "").strip()
    if not texto_limpio:
        raise ErrorDominio(
            "La historia clinica no puede estar vacia.",
            codigo="HISTORIA_CLINICA_OBLIGATORIA",
            http_status=422,
        )

    paciente_repo.actualizar_historia_clinica(
        paciente,
        texto_limpio,
        usuario_id=usuario_actual_id,
    )

    return {
        "paciente_id": paciente.id,
        "historia_clinica": paciente.historia_clinica,
        "guardado_en_bd": True,
    }


def _serializar_datos_publicos_medico(medico: Medico, *, es_medico_alta: bool) -> dict:
    """Expone unicamente datos profesionales publicos del medico."""
    return {
        "medico_id": medico.id,
        "nombre": medico.usuario.nombre,
        "apellido": medico.usuario.apellido,
        "nombre_completo": f"{medico.usuario.nombre} {medico.usuario.apellido}".strip(),
        "matricula": medico.matricula,
        "especialidades": [
            {"id": esp.id, "nombre": esp.nombre}
            for esp in sorted(medico.especialidades, key=lambda e: e.nombre.lower())
        ],
        "es_medico_alta": es_medico_alta,
    }


def _serializar_autorizacion(
    autorizacion: PacienteMedicoAutorizado,
    *,
    medico_alta_id: int,
) -> dict:
    return {
        "autorizacion_id": autorizacion.id,
        **_serializar_datos_publicos_medico(
            autorizacion.medico,
            es_medico_alta=autorizacion.medico_id == medico_alta_id,
        ),
        "activa": bool(autorizacion.activa),
        "otorgada_en": autorizacion.otorgada_en.isoformat() if autorizacion.otorgada_en else None,
        "revocada_en": autorizacion.revocada_en.isoformat() if autorizacion.revocada_en else None,
    }


def _obtener_nomina_autorizados_efectiva(paciente: Paciente) -> tuple[list[dict], list[int]]:
    """Retorna la lista serializada de medicos con permiso activo y sus IDs ordenados."""
    activas = paciente_repo.listar_autorizaciones_activas(paciente.id)
    if activas or paciente_repo.tiene_historial_autorizaciones(paciente.id):
        items = [_serializar_autorizacion(a, medico_alta_id=paciente.medico_id) for a in activas]
        return items, sorted(a.medico_id for a in activas)

    # Compatibilidad transitoria para pacientes previos a la migracion sin filas sembradas
    if paciente.medico is not None:
        item = {
            "autorizacion_id": None,
            **_serializar_datos_publicos_medico(paciente.medico, es_medico_alta=True),
            "activa": True,
            "otorgada_en": None,
            "revocada_en": None,
        }
        return [item], [paciente.medico_id]
    return [], []


def listar_medicos_autorizados_paciente(*, usuario_actual_id: int) -> dict:
    """Lista los medicos que cuentan con autorizacion activa para ver la historia clinica del paciente."""
    paciente = paciente_repo.buscar_paciente_por_usuario_id(usuario_actual_id)
    if paciente is None:
        raise ErrorNoEncontrado(
            "No se encontro un perfil de paciente asociado a su cuenta.",
            codigo="PACIENTE_NO_ENCONTRADO",
        )

    autorizados, ids_activos = _obtener_nomina_autorizados_efectiva(paciente)
    return {
        "paciente_id": paciente.id,
        "medicos_autorizados_activos_ids": ids_activos,
        "medicos_autorizados": autorizados,
    }


def autorizar_medicos_historia_clinica(
    *,
    usuario_actual_id: int,
    medicos_ids: list[int],
    motivo: str | None = None,
    ip_origen: str | None = None,
) -> tuple[dict, int]:
    """Otorga autorizacion de historia clinica a uno o varios medicos de forma idempotente y atomica (Esc. 40)."""
    ids_unicos = list(dict.fromkeys(medicos_ids))
    if not ids_unicos:
        raise ErrorDatosInvalidos(
            "Debe seleccionar al menos un medico para autorizar.",
            codigo="LISTA_MEDICOS_VACIA",
        )
    if any(mid <= 0 for mid in ids_unicos):
        raise ErrorDatosInvalidos(
            "Todos los identificadores de medicos deben ser enteros positivos.",
            codigo="DATOS_INVALIDOS",
        )

    paciente = paciente_repo.buscar_paciente_por_usuario_id(usuario_actual_id, bloquear=True)
    if paciente is None:
        raise ErrorNoEncontrado(
            "No se encontro un perfil de paciente asociado a su cuenta.",
            codigo="PACIENTE_NO_ENCONTRADO",
        )

    medicos_encontrados = medico_repo.buscar_medicos_por_ids(ids_unicos)
    if len(medicos_encontrados) != len(ids_unicos):
        paciente_repo.deshacer_cambios()
        raise ErrorNoEncontrado(
            "Uno o mas medicos indicados no existen o no estan habilitados.",
            codigo="MEDICO_NO_ENCONTRADO",
        )
    medicos_por_id = {m.id: m for m in medicos_encontrados}

    ahora = _ahora_utc_naive()
    nombre_paciente = f"{paciente.usuario.nombre} {paciente.usuario.apellido}".strip()

    def _armar_respuesta(
        activas: list[PacienteMedicoAutorizado],
        nuevos: list[int],
        existentes: list[int],
        mensaje: str,
    ) -> dict:
        return {
            "paciente_id": paciente.id,
            "nuevos_autorizados_ids": nuevos,
            "ya_autorizados_ids": existentes,
            "medicos_autorizados_activos_ids": sorted(a.medico_id for a in activas),
            "medicos_autorizados": [
                _serializar_autorizacion(a, medico_alta_id=paciente.medico_id) for a in activas
            ],
            "mensaje": mensaje,
        }

    try:
        materializo_inicial = (
            paciente_repo.asegurar_autorizacion_inicial_si_vacio(paciente, otorgada_en=ahora)
            is not None
        )
        activas_previas = paciente_repo.listar_autorizaciones_activas(paciente.id)
        ids_anteriores = sorted(a.medico_id for a in activas_previas)
        anteriores_set = set(ids_anteriores)

        nuevos_ids = [mid for mid in ids_unicos if mid not in anteriores_set]
        ya_autorizados_ids = [mid for mid in ids_unicos if mid in anteriores_set]

        if not nuevos_ids:
            if materializo_inicial:
                paciente_repo.guardar_cambios()
            activas_finales = paciente_repo.listar_autorizaciones_activas(paciente.id)
            return (
                _armar_respuesta(
                    activas_finales,
                    [],
                    ya_autorizados_ids,
                    "Los medicos seleccionados ya contaban con autorizacion activa.",
                ),
                200,
            )

        for mid in nuevos_ids:
            medico = medicos_por_id[mid]
            paciente_repo.crear_autorizacion_medico(
                paciente_id=paciente.id,
                medico_id=mid,
                otorgada_por_usuario_id=usuario_actual_id,
                otorgada_en=ahora,
            )
            paciente_repo.crear_aviso_app(
                usuario_id=medico.usuario_id,
                mensaje=(
                    f"El paciente {nombre_paciente} le otorgo autorizacion para consultar "
                    "su historia clinica."
                ),
                enviado_en=ahora,
            )

        ids_finales = sorted(anteriores_set | set(nuevos_ids))
        auditoria_service.registrar_modificacion(
            entidad_tipo=EntidadAuditable.PACIENTE,
            entidad_id=paciente.id,
            accion=TipoAccionAuditoria.MODIFICACION,
            usuario_id=usuario_actual_id,
            origen="usuario",
            cambios={
                "medicos_autorizados_ids": {
                    "anterior": ids_anteriores,
                    "nuevo": ids_finales,
                }
            },
            motivo=motivo or "Autorización de médicos por paciente",
            ip_origen=ip_origen,
        )
        paciente_repo.guardar_cambios()
    except IntegrityError as exc:
        paciente_repo.deshacer_cambios()
        activas_actuales = paciente_repo.listar_autorizaciones_activas(paciente.id)
        if set(ids_unicos).issubset(a.medico_id for a in activas_actuales):
            return (
                _armar_respuesta(
                    activas_actuales,
                    [],
                    ids_unicos,
                    "Los medicos seleccionados ya contaban con autorizacion activa.",
                ),
                200,
            )
        raise ErrorConflicto(
            "Conflicto concurrente al registrar autorizaciones medicas.",
            codigo="CONFLICTO_AUTORIZACION",
        ) from exc
    except SQLAlchemyError as exc:
        paciente_repo.deshacer_cambios()
        raise ErrorBaseDatos(
            "Error temporal al otorgar las autorizaciones de historia clinica. Intente nuevamente.",
        ) from exc

    logger.info(
        "[paciente_service] STEP 2 medicos_autorizados paciente_id=%s nuevos=%s",
        paciente.id,
        nuevos_ids,
    )
    activas_finales = paciente_repo.listar_autorizaciones_activas(paciente.id)
    return (
        _armar_respuesta(
            activas_finales,
            nuevos_ids,
            ya_autorizados_ids,
            f"Se autorizo a {len(nuevos_ids)} medico(s) a visualizar su historia clinica.",
        ),
        201,
    )


def revocar_autorizacion_medico(
    *,
    usuario_actual_id: int,
    medico_id: int,
    motivo: str | None = None,
    ip_origen: str | None = None,
) -> dict:
    """Revoca logicamente la autorizacion activa de un medico preservando trazabilidad (Esc. 40)."""
    paciente = paciente_repo.buscar_paciente_por_usuario_id(usuario_actual_id, bloquear=True)
    if paciente is None:
        raise ErrorNoEncontrado(
            "No se encontro un perfil de paciente asociado a su cuenta.",
            codigo="PACIENTE_NO_ENCONTRADO",
        )

    ahora = _ahora_utc_naive()
    nombre_paciente = f"{paciente.usuario.nombre} {paciente.usuario.apellido}".strip()

    try:
        paciente_repo.asegurar_autorizacion_inicial_si_vacio(paciente, otorgada_en=ahora)
        autorizacion = paciente_repo.buscar_autorizacion_activa(
            paciente.id,
            medico_id,
            bloquear=True,
        )
        if autorizacion is None:
            paciente_repo.deshacer_cambios()
            raise ErrorNoEncontrado(
                "No existe una autorizacion activa para el medico indicado.",
                codigo="AUTORIZACION_NO_ACTIVA",
            )

        activas_previas = paciente_repo.listar_autorizaciones_activas(paciente.id)
        ids_anteriores = sorted(a.medico_id for a in activas_previas)

        autorizacion.activa = False
        autorizacion.revocada_en = ahora
        ids_finales = [mid for mid in ids_anteriores if mid != medico_id]

        auditoria_service.registrar_modificacion(
            entidad_tipo=EntidadAuditable.PACIENTE,
            entidad_id=paciente.id,
            accion=TipoAccionAuditoria.MODIFICACION,
            usuario_id=usuario_actual_id,
            origen="usuario",
            cambios={
                "medicos_autorizados_ids": {
                    "anterior": ids_anteriores,
                    "nuevo": ids_finales,
                }
            },
            motivo=motivo or "Revocación de autorización de historia clínica",
            ip_origen=ip_origen,
        )

        if autorizacion.medico is not None:
            paciente_repo.crear_aviso_app(
                usuario_id=autorizacion.medico.usuario_id,
                mensaje=(
                    f"El paciente {nombre_paciente} revoco su autorizacion para consultar "
                    "su historia clinica."
                ),
                enviado_en=ahora,
            )

        autorizacion_serializada = _serializar_autorizacion(
            autorizacion,
            medico_alta_id=paciente.medico_id,
        )
        paciente_repo.guardar_cambios()
    except ErrorDominio:
        raise
    except SQLAlchemyError as exc:
        paciente_repo.deshacer_cambios()
        raise ErrorBaseDatos(
            "Error temporal al revocar la autorizacion de historia clinica. Intente nuevamente.",
        ) from exc

    logger.info(
        "[paciente_service] STEP 3 autorizacion_revocada paciente_id=%s medico_id=%s",
        paciente.id,
        medico_id,
    )
    activas_restantes = paciente_repo.listar_autorizaciones_activas(paciente.id)
    return {
        "paciente_id": paciente.id,
        "autorizacion_revocada": autorizacion_serializada,
        "medicos_autorizados_activos_ids": sorted(a.medico_id for a in activas_restantes),
        "medicos_autorizados": [
            _serializar_autorizacion(a, medico_alta_id=paciente.medico_id)
            for a in activas_restantes
        ],
    }


def obtener_historia_clinica_paciente(*, usuario_actual_id: int, paciente_id: int) -> dict:
    """Retorna la historia clinica completa de un paciente a un medico con autorizacion activa (Esc. 40)."""
    medico = paciente_repo.buscar_medico_por_usuario_id(usuario_actual_id)
    if medico is None:
        raise ErrorSinPermiso(
            "Solo un medico tratante o gerente medico puede consultar historias clinicas.",
            codigo="FORBIDDEN_ROLE",
        )

    paciente = paciente_repo.buscar_paciente_con_historia_clinica(paciente_id)
    if paciente is None:
        raise ErrorNoEncontrado(
            "El paciente indicado no existe.",
            codigo="PACIENTE_NO_ENCONTRADO",
        )

    if not paciente_repo.medico_esta_autorizado_historia_clinica(paciente, medico.id):
        logger.warning(
            "[paciente_service] acceso_denegado_historia_clinica paciente_id=%s medico_id=%s",
            paciente.id,
            medico.id,
        )
        raise ErrorSinPermiso(
            "No posee autorizacion vigente para consultar la historia clinica de este paciente.",
            codigo="HISTORIA_CLINICA_NO_AUTORIZADA",
        )

    medicos_autorizados, _ = _obtener_nomina_autorizados_efectiva(paciente)
    logger.info(
        "[paciente_service] STEP 4 historia_clinica_consultada paciente_id=%s medico_id=%s",
        paciente.id,
        medico.id,
    )
    return {
        "paciente_id": paciente.id,
        "dni": paciente.dni,
        "nombre": paciente.usuario.nombre,
        "apellido": paciente.usuario.apellido,
        "nombre_completo": f"{paciente.usuario.nombre} {paciente.usuario.apellido}".strip(),
        "fecha_nacimiento": paciente.fecha_nacimiento.isoformat(),
        "responsable_nombre": paciente.responsable_nombre,
        "responsable_dni": paciente.responsable_dni,
        "historia_clinica": paciente.historia_clinica,
        "diagnostico_presuntivo": {
            "id": paciente.diagnostico_presuntivo.id,
            "nombre": paciente.diagnostico_presuntivo.nombre,
            "descripcion": paciente.diagnostico_presuntivo.descripcion,
        },
        "tipo_sospecha": paciente.tipo_sospecha,
        "sintomas": [
            {"id": s.id, "snomed_id": s.snomed_id, "descripcion": s.descripcion}
            for s in sorted(paciente.sintomas, key=lambda x: x.id)
        ],
        "familiares": _serializar_familiares(paciente.familiares),
        "familiograma_generado": bool(paciente.familiograma_pdf_path),
        "familiograma_pdf_path": paciente.familiograma_pdf_path,
        "familiograma_url": (
            f"/api/v1/pacientes/{paciente.id}/familiograma"
            if paciente.familiograma_pdf_path
            else None
        ),
        "medicos_autorizados": medicos_autorizados,
    }