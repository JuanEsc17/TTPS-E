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
from src.core.services.formato_correo import asunto_correo, formatear_correo
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