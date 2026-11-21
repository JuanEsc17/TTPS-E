"""Servicio de logica de negocio para analisis bioinformatico y reanalisis (Escenarios 15, 17 y 24)."""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

import httpx
from flask import current_app, has_app_context
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from src.clients import (
    ApigenClient,
    ClienteConexionError,
    ClienteError,
    ClienteServicioError,
    EmailClient,
)
from src.core.models import (
    Analisis,
    Aviso,
    CanalAviso,
    ClasificacionVariante,
    EntidadAuditable,
    EstadoEstudio,
    Estudio,
    Gen,
    OrigenGen,
    Rol,
    TipoAccionAuditoria,
    TipoAnalisis,
    Usuario,
    Variante,
)
from src.core.repos import bioinformatica_repo, clinica_repo, usuario_repo
from src.core.services import auditoria_service, resultado_service
from src.core.services.excepciones import ErrorDominio
from src.core.services.formato_correo import asunto_correo, formatear_correo

logger = logging.getLogger(__name__)
_EMAIL_CLIENT_ORIGINAL = EmailClient

MAX_BYTES_DATOS_CRUDOS = 5 * 1024 * 1024  # 5 MB
_BACKOFFS_BIOINFORMATICA = (0.5, 1.0)
_PATRON_SIMBOLO_GEN = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,29}$")

_MAPA_CLASIFICACION: dict[str, ClasificacionVariante] = {
    "patogenica": ClasificacionVariante.PATOGENICA,
    "patogénica": ClasificacionVariante.PATOGENICA,
    "benigna": ClasificacionVariante.BENIGNA,
    "inocua": ClasificacionVariante.INOCUA,
    "vus": ClasificacionVariante.VUS,
    # shortcut: Apigen devuelve 'probablemente_patogenica' (y confirma_diagnostico=False); actualizar si el LEL agrega una 5ta clasificacion
    "probablemente_patogenica": ClasificacionVariante.VUS,
}


def _resolver_bioinformatica_client(client: Any | None = None, *, timeout: float = 5.0) -> Any:
    if client is not None:
        return client
    if has_app_context():
        configurado = (
            current_app.config.get("BIOINFORMATICA_CLIENT")
            or current_app.extensions.get("bioinformatica_client")
        )
        if configurado is not None:
            return configurado
        instancia = ApigenClient(timeout=timeout)
        current_app.extensions["bioinformatica_client"] = instancia
        return instancia
    return ApigenClient(timeout=timeout)


def _validar_y_normalizar_actg(
    *,
    contenido_actg: str | None = None,
    archivo_bytes: bytes | None = None,
) -> str:
    """Valida que los datos crudos no esten vacios y contengan solo bases A, C, T, G."""
    if archivo_bytes is not None:
        if len(archivo_bytes) > MAX_BYTES_DATOS_CRUDOS:
            raise ErrorDominio(
                "El archivo de datos crudos supera el tamano maximo permitido (5 MB).",
                codigo="ARCHIVO_DATOS_CRUDOS_INVALIDO",
                http_status=400,
            )
        try:
            texto = archivo_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ErrorDominio(
                "El archivo de datos crudos debe estar codificado en texto UTF-8 valido.",
                codigo="ARCHIVO_DATOS_CRUDOS_INVALIDO",
                http_status=400,
            ) from exc
    else:
        texto = contenido_actg if isinstance(contenido_actg, str) else ""

    if len(texto.encode("utf-8")) > MAX_BYTES_DATOS_CRUDOS:
        raise ErrorDominio(
            "El contenido de datos crudos supera el tamano maximo permitido (5 MB).",
            codigo="ARCHIVO_DATOS_CRUDOS_INVALIDO",
            http_status=400,
        )

    bases_totales = 0
    lineas_normalizadas: list[str] = []
    for linea in texto.splitlines():
        linea_strip = linea.strip()
        if not linea_strip:
            continue
        if linea_strip.startswith(">"):
            lineas_normalizadas.append(linea_strip)
            continue
        limpia = re.sub(r"[ \t]+", "", linea_strip).upper()
        if not limpia or any(c not in {"A", "C", "T", "G"} for c in limpia):
            raise ErrorDominio(
                "El archivo de datos crudos solo puede contener bases nucleotidicas A, C, T, G.",
                codigo="ARCHIVO_DATOS_CRUDOS_INVALIDO",
                http_status=400,
            )
        bases_totales += len(limpia)
        lineas_normalizadas.append(limpia)

    if bases_totales == 0:
        raise ErrorDominio(
            "El archivo de datos crudos esta vacio o no contiene bases A, C, T, G.",
            codigo="ARCHIVO_DATOS_CRUDOS_INVALIDO",
            http_status=400,
        )

    return "\n".join(lineas_normalizadas) + "\n"


def _analisis_activo(estudio: Estudio) -> Analisis | None:
    pendientes = [a for a in estudio.analisis if a.resultado is None]
    return pendientes[-1] if pendientes else None


def _mapa_origen_genes(estudio: Estudio) -> dict[int, str]:
    return {eg.gen_id: eg.origen.value for eg in estudio.genes}


def _serializar_genes_analisis(estudio: Estudio, analisis: Analisis | None) -> list[dict[str, Any]]:
    origenes = _mapa_origen_genes(estudio)
    if analisis and analisis.genes:
        return [
            {
                "gen_id": ag.gen_id,
                "simbolo": ag.gen.simbolo if ag.gen else "",
                "nombre": ag.gen.nombre if ag.gen else None,
                "es_hallazgo_secundario": bool(ag.gen.es_hallazgo_secundario) if ag.gen else False,
                "origen": origenes.get(ag.gen_id, "patologia"),
            }
            for ag in analisis.genes
        ]
    return [
        {
            "gen_id": eg.gen_id,
            "simbolo": eg.gen.simbolo if eg.gen else "",
            "nombre": eg.gen.nombre if eg.gen else None,
            "es_hallazgo_secundario": bool(eg.gen.es_hallazgo_secundario) if eg.gen else False,
            "origen": eg.origen.value,
        }
        for eg in estudio.genes
    ]


def _serializar_estudio_bandeja(
    estudio: Estudio,
    *,
    nombres_usuarios: dict[int, str],
    usuario_actual_id: int | None = None,
) -> dict[str, Any]:
    activo = _analisis_activo(estudio)
    bio_id = activo.bioinformatico_id if activo else None
    paciente_u = estudio.paciente.usuario if estudio.paciente else None
    medico_u = estudio.medico.usuario if estudio.medico else None

    return {
        "estudio_id": estudio.id,
        "estado": estudio.estado.value,
        "es_pompe_urgente": bool(estudio.es_pompe_urgente),
        "updated_at": estudio.updated_at.isoformat() if estudio.updated_at else None,
        "created_at": estudio.created_at.isoformat() if estudio.created_at else None,
        "paciente": {
            "id": estudio.paciente_id,
            "nombre": f"{paciente_u.nombre} {paciente_u.apellido}".strip() if paciente_u else "",
            "dni": estudio.paciente.dni if estudio.paciente else "",
        },
        "medico_nombre": f"{medico_u.nombre} {medico_u.apellido}".strip() if medico_u else "",
        "patologia_nombre": estudio.patologia_sospechada.nombre if estudio.patologia_sospechada else "",
        "analisis_id": activo.id if activo else None,
        "tipo_analisis": activo.tipo.value if activo else None,
        "bioinformatico_id": bio_id,
        "bioinformatico_nombre": nombres_usuarios.get(bio_id) if bio_id else None,
        "es_mio": bool(usuario_actual_id and bio_id == usuario_actual_id),
        "datos_crudos_cargados": estudio.datos_crudos is not None,
        "genes": _serializar_genes_analisis(estudio, activo),
    }


def listar_pendientes_datos_crudos() -> list[dict[str, Any]]:
    """Lista estudios en viaje a Corea aguardando carga de datos crudos ACTG."""
    estudios = bioinformatica_repo.listar_estudios_por_estado(EstadoEstudio.EN_VIAJE_COREA)
    return [
        _serializar_estudio_bandeja(estudio, nombres_usuarios={})
        for estudio in estudios
    ]


def cargar_datos_crudos(
    *,
    estudio_id: int,
    usuario_id: int,
    contenido_actg: str | None = None,
    archivo_bytes: bytes | None = None,
    email_client: EmailClient | None = None,
    ip_origen: str | None = None,
) -> dict[str, Any]:
    """STEP 1: Valida secuencia ACTG, persiste DatosCrudos/Analisis(INICIAL) y avisa a bioinformatica."""
    secuencia_normalizada = _validar_y_normalizar_actg(
        contenido_actg=contenido_actg,
        archivo_bytes=archivo_bytes,
    )

    estudio = bioinformatica_repo.buscar_estudio_por_id(estudio_id, bloquear=True)
    if estudio is None:
        raise ErrorDominio("Estudio no encontrado.", codigo="ESTUDIO_NO_ENCONTRADO", http_status=404)

    if estudio.datos_crudos is not None:
        raise ErrorDominio(
            "Los datos crudos de este estudio ya fueron cargados.",
            codigo="DATOS_CRUDOS_YA_CARGADOS",
            http_status=409,
        )

    if estudio.estado != EstadoEstudio.EN_VIAJE_COREA:
        raise ErrorDominio(
            "El estudio debe estar en estado 'En viaje a Corea' para cargar datos crudos.",
            codigo="ESTUDIO_NO_ESTA_EN_VIAJE_A_COREA",
            http_status=409,
        )

    archivo_path_rel = f"storage/datos_crudos/estudio_{estudio.id}.txt"
    ruta_fisica = resultado_service.resolver_ruta_storage(archivo_path_rel)

    try:
        ruta_fisica.parent.mkdir(parents=True, exist_ok=True)
        ruta_fisica.write_text(secuencia_normalizada, encoding="utf-8")
    except OSError as exc:
        ruta_fisica.unlink(missing_ok=True)
        raise ErrorDominio(
            "No se pudo guardar el archivo de datos crudos en el almacenamiento.",
            codigo="ERROR_ESCRITURA_DATOS_CRUDOS",
            http_status=500,
            reintentable=True,
        ) from exc

    ahora = resultado_service.ahora_utc_naive()
    bioinformaticos = usuario_repo.listar_por_rol(Rol.BIOINFORMATICO)
    aviso_msg = (
        f"Nuevo estudio #{estudio.id} disponible para analisis bioinformatico"
        + (" [POMPE URGENTE]." if estudio.es_pompe_urgente else ".")
    )
    avisos_mail: list[Aviso] = []
    destinatarios: list[str] = []

    try:
        datos_crudos = bioinformatica_repo.crear_datos_crudos(
            estudio_id=estudio.id,
            cargado_por_id=usuario_id,
            archivo_path=archivo_path_rel,
        )
        genes_ids = [eg.gen_id for eg in estudio.genes]
        analisis = bioinformatica_repo.crear_analisis_inicial(estudio.id, genes_ids)

        estado_anterior = estudio.estado.value
        estudio.estado = EstadoEstudio.EN_ANALISIS_BIOINFORMATICA

        auditoria_service.registrar_modificacion(
            entidad_tipo=EntidadAuditable.ESTUDIO,
            entidad_id=estudio.id,
            accion=TipoAccionAuditoria.CAMBIO_ESTADO,
            usuario_id=usuario_id,
            origen="usuario",
            cambios={
                "estado": {
                    "anterior": estado_anterior,
                    "nuevo": EstadoEstudio.EN_ANALISIS_BIOINFORMATICA.value,
                },
                "datos_crudos_id": {"anterior": None, "nuevo": datos_crudos.id},
            },
            motivo="Carga de datos crudos provenientes de Corea",
            ip_origen=ip_origen,
        )

        for bio_u in bioinformaticos:
            bioinformatica_repo.crear_aviso(
                usuario_id=bio_u.id,
                mensaje=aviso_msg,
                canal=CanalAviso.APP,
                enviado=True,
                enviado_en=ahora,
            )
            avisos_mail.append(
                bioinformatica_repo.crear_aviso(
                    usuario_id=bio_u.id,
                    mensaje=aviso_msg,
                    canal=CanalAviso.MAIL,
                    enviado=False,
                )
            )
            if bio_u.email and bio_u.email not in destinatarios:
                destinatarios.append(bio_u.email)

        bioinformatica_repo.guardar_cambios()
    except IntegrityError as exc:
        bioinformatica_repo.deshacer_cambios()
        ruta_fisica.unlink(missing_ok=True)
        raise ErrorDominio(
            "Los datos crudos de este estudio ya fueron cargados.",
            codigo="DATOS_CRUDOS_YA_CARGADOS",
            http_status=409,
        ) from exc
    except SQLAlchemyError as exc:
        bioinformatica_repo.deshacer_cambios()
        ruta_fisica.unlink(missing_ok=True)
        raise ErrorDominio(
            "Error al persistir los datos crudos del estudio. Intente nuevamente.",
            codigo="DB_ERROR",
            http_status=500,
            reintentable=True,
        ) from exc

    mail_equipo = os.environ.get("BIOINFORMATICA_EQUIPO_EMAIL", "").strip()
    if mail_equipo and mail_equipo not in destinatarios:
        destinatarios.append(mail_equipo)

    cliente_email = resultado_service.resolver_email_client(email_client, cliente_cls=EmailClient)
    if destinatarios and cliente_email is not None:
        simbolos_estudio = sorted({eg.gen.simbolo for eg in estudio.genes if eg.gen is not None})
        detalles_estudio = [
            f"Estudio: #{estudio.id} (Análisis #{analisis.id} · Inicial)",
            f"Prioridad: {'POMPE URGENTE' if estudio.es_pompe_urgente else 'Estándar'}",
        ]
        if estudio.patologia_sospechada is not None:
            detalles_estudio.append(f"Patología sospechada: {estudio.patologia_sospechada.nombre}")
        if simbolos_estudio:
            detalles_estudio.append(f"Genes a analizar: {', '.join(simbolos_estudio)}")
        cuerpo_bio = formatear_correo(
            titulo="Nuevo estudio disponible para bioinformática",
            introduccion=(
                f"Se cargaron los datos crudos provenientes de Corea para el estudio #{estudio.id} "
                "y ya se encuentra disponible en la bandeja de análisis."
            ),
            destacado=["PRIORIDAD ALTA · POMPE URGENTE"] if estudio.es_pompe_urgente else None,
            secciones=[("Resumen del estudio", detalles_estudio)],
            cierre="Ingresá a la bandeja de bioinformática para tomar el estudio y comenzar el análisis.",
        )
        enviado = resultado_service.enviar_email_resiliente(
            cliente_email,
            asunto=asunto_correo(
                f"Estudio #{estudio.id} listo para análisis bioinformático"
                + (" [POMPE URGENTE]" if estudio.es_pompe_urgente else "")
            ),
            mensaje=cuerpo_bio,
            destinatarios=destinatarios,
            referencia=f"DATOS-CRUDOS-{estudio.id}",
            idempotency_key=f"datos-crudos-{estudio.id}-{datos_crudos.id}",
        )
        if enviado and avisos_mail:
            bioinformatica_repo.marcar_avisos_enviados(avisos_mail, resultado_service.ahora_utc_naive())
            bioinformatica_repo.guardar_cambios()

    logger.info(
        "[bioinformatica_service] datos_crudos_cargados estudio_id=%s datos_crudos_id=%s analisis_id=%s",
        estudio.id,
        datos_crudos.id,
        analisis.id,
    )
    return {
        "estudio_id": estudio.id,
        "datos_crudos_id": datos_crudos.id,
        "analisis_id": analisis.id,
        "archivo_path": archivo_path_rel,
        "estado_estudio": estudio.estado.value,
    }


def listar_bandeja_bioinformatica(usuario_id: int) -> dict[str, Any]:
    """STEP 2: Lista estudios pendientes (Pompe urgente primero) y estudios ya tomados."""
    pendientes = bioinformatica_repo.listar_estudios_por_estado(
        EstadoEstudio.EN_ANALISIS_BIOINFORMATICA
    )
    en_curso = bioinformatica_repo.listar_estudios_por_estado(
        EstadoEstudio.EN_ANALISIS_BIOINFORMATICO
    )

    bio_ids = [
        activo.bioinformatico_id
        for est in en_curso
        if (activo := _analisis_activo(est)) is not None and activo.bioinformatico_id is not None
    ]
    usuarios_map = usuario_repo.buscar_por_ids(bio_ids)
    nombres = {
        uid: f"{u.nombre} {u.apellido}".strip()
        for uid, u in usuarios_map.items()
    }

    return {
        "estudios": [
            _serializar_estudio_bandeja(est, nombres_usuarios=nombres, usuario_actual_id=usuario_id)
            for est in pendientes
        ],
        "en_curso": [
            _serializar_estudio_bandeja(est, nombres_usuarios=nombres, usuario_actual_id=usuario_id)
            for est in en_curso
        ],
    }


def obtener_datos_crudos_estudio(estudio_id: int, usuario_id: int) -> dict[str, Any]:
    """Permite al bioinformatico asignado inspeccionar la secuencia ACTG del estudio tomado."""
    estudio = bioinformatica_repo.buscar_estudio_por_id(estudio_id)
    if estudio is None:
        raise ErrorDominio("Estudio no encontrado.", codigo="ESTUDIO_NO_ENCONTRADO", http_status=404)

    activo = _analisis_activo(estudio)
    if (
        estudio.estado != EstadoEstudio.EN_ANALISIS_BIOINFORMATICO
        or activo is None
        or activo.bioinformatico_id != usuario_id
    ):
        raise ErrorDominio(
            "Solo el bioinformatico asignado puede consultar los datos crudos de este estudio.",
            codigo="ESTUDIO_ASIGNADO_A_OTRO_BIOINFORMATICO",
            http_status=403,
        )

    if estudio.datos_crudos is None:
        raise ErrorDominio(
            "El estudio no posee datos crudos cargados.",
            codigo="DATOS_CRUDOS_NO_ENCONTRADOS",
            http_status=404,
        )

    ruta_fisica = resultado_service.resolver_ruta_storage(estudio.datos_crudos.archivo_path)
    contenido = ruta_fisica.read_text(encoding="utf-8") if ruta_fisica.is_file() else ""
    bases_count = sum(
        len(line.strip())
        for line in contenido.splitlines()
        if line.strip() and not line.strip().startswith(">")
    )
    return {
        "estudio_id": estudio.id,
        "archivo_path": estudio.datos_crudos.archivo_path,
        "cargado_en": estudio.datos_crudos.cargado_en.isoformat(),
        "total_bases": bases_count,
        "preview": contenido[:2000],
        "truncado": len(contenido) > 2000,
    }


def tomar_estudio(
    *,
    estudio_id: int,
    usuario_id: int,
    ip_origen: str | None = None,
) -> dict[str, Any]:
    """STEP 2: Asigna exclusivamente el estudio al bioinformatico y pasa a En analisis de un bioinformatico."""
    estudio = bioinformatica_repo.buscar_estudio_por_id(estudio_id, bloquear=True)
    if estudio is None:
        raise ErrorDominio("Estudio no encontrado.", codigo="ESTUDIO_NO_ENCONTRADO", http_status=404)

    activo = _analisis_activo(estudio)

    if estudio.estado == EstadoEstudio.EN_ANALISIS_BIOINFORMATICO:
        if activo is not None and activo.bioinformatico_id != usuario_id:
            raise ErrorDominio(
                "El estudio ya fue tomado por otro bioinformatico.",
                codigo="ESTUDIO_YA_TOMADO_POR_OTRO_BIOINFORMATICO",
                http_status=409,
            )
        raise ErrorDominio(
            "El estudio ya se encuentra tomado para analisis.",
            codigo="ESTUDIO_YA_TOMADO",
            http_status=409,
        )

    if estudio.estado != EstadoEstudio.EN_ANALISIS_BIOINFORMATICA:
        raise ErrorDominio(
            "El estudio no se encuentra en estado 'En analisis por bioinformatica'.",
            codigo="ESTUDIO_NO_DISPONIBLE_PARA_TOMAR",
            http_status=409,
        )

    try:
        if activo is None:
            activo = bioinformatica_repo.crear_analisis_inicial(
                estudio.id,
                [eg.gen_id for eg in estudio.genes],
            )
        elif not activo.genes and estudio.genes:
            bioinformatica_repo.copiar_genes_a_analisis(
                activo.id,
                [eg.gen_id for eg in estudio.genes],
            )

        bio_anterior = activo.bioinformatico_id
        activo.bioinformatico_id = usuario_id
        estado_anterior = estudio.estado.value
        estudio.estado = EstadoEstudio.EN_ANALISIS_BIOINFORMATICO

        auditoria_service.registrar_modificacion(
            entidad_tipo=EntidadAuditable.ESTUDIO,
            entidad_id=estudio.id,
            accion=TipoAccionAuditoria.CAMBIO_ESTADO,
            usuario_id=usuario_id,
            origen="usuario",
            cambios={
                "estado": {
                    "anterior": estado_anterior,
                    "nuevo": EstadoEstudio.EN_ANALISIS_BIOINFORMATICO.value,
                },
                "bioinformatico_id": {"anterior": bio_anterior, "nuevo": usuario_id},
            },
            motivo="Estudio tomado por bioinformatico",
            ip_origen=ip_origen,
        )
        bioinformatica_repo.guardar_cambios()
    except SQLAlchemyError as exc:
        bioinformatica_repo.deshacer_cambios()
        raise ErrorDominio(
            "Error al asignar el estudio al bioinformatico. Intente nuevamente.",
            codigo="DB_ERROR",
            http_status=500,
            reintentable=True,
        ) from exc

    evento_toma = "reanalisis_tomado" if activo.tipo == TipoAnalisis.REANALISIS else "estudio_tomado"
    logger.info(
        "[bioinformatica_service] %s estudio_id=%s analisis_id=%s bioinformatico_id=%s",
        evento_toma,
        estudio.id,
        activo.id,
        usuario_id,
    )
    estudio_actualizado = bioinformatica_repo.buscar_estudio_por_id(estudio.id) or estudio
    analisis_final = _analisis_activo(estudio_actualizado) or activo
    return {
        "estudio_id": estudio_actualizado.id,
        "analisis_id": analisis_final.id,
        "bioinformatico_id": usuario_id,
        "estado_estudio": estudio_actualizado.estado.value,
        "es_pompe_urgente": bool(estudio_actualizado.es_pompe_urgente),
        "genes": _serializar_genes_analisis(estudio_actualizado, analisis_final),
    }


def _normalizar_variantes_externas(crudos: Any, *, estricto: bool = False) -> list[dict[str, Any]]:
    def _error_payload(motivo: str) -> ErrorDominio:
        logger.warning("[bioinformatica_client] payload invalido de Apigen: %s", motivo)
        return ErrorDominio(
            "La API de bioinformatica devolvio una respuesta invalida.",
            codigo="RESPUESTA_INVALIDA_API_BIOINFORMATICA",
            http_status=502,
        )

    if isinstance(crudos, dict):
        if estricto and (crudos.get("ok") is False or not isinstance(crudos.get("variantes"), list)):
            raise _error_payload("dict sin ok/variantes")
        lista = crudos.get("variantes", [])
        if not isinstance(lista, list):
            return []
    elif isinstance(crudos, list):
        lista = crudos
    else:
        if estricto:
            raise _error_payload(f"tipo raiz inesperado: {type(crudos).__name__}")
        return []

    normalizadas: list[dict[str, Any]] = []
    vistas: set[str] = set()
    for item in lista:
        if not isinstance(item, dict):
            if estricto:
                raise _error_payload(f"item no es dict: {type(item).__name__}")
            continue
        notacion = str(item.get("notacion") or item.get("hgvs_c") or "").strip()[:120]
        if not notacion:
            if estricto:
                raise _error_payload("item sin notacion/hgvs_c")
            continue
        if notacion in vistas:
            continue
        clas_raw = str(item.get("clasificacion") or "").strip().lower()
        clasificacion = _MAPA_CLASIFICACION.get(clas_raw)
        if clasificacion is None:
            if estricto:
                raise _error_payload(f"clasificacion desconocida: {clas_raw!r}")
            continue
        clinvar_raw = item.get("clinvar_id") or item.get("id")
        clinvar_id = str(clinvar_raw).strip()[:30] if clinvar_raw else None
        vistas.add(notacion)
        normalizadas.append(
            {
                "notacion": notacion,
                "clinvar_id": clinvar_id,
                "clasificacion": clasificacion,
            }
        )
    return normalizadas


def _serializar_variante(v: Variante) -> dict[str, Any]:
    return {
        "id": v.id,
        "gen_id": v.gen_id,
        "notacion": v.notacion,
        "clinvar_id": v.clinvar_id,
        "clasificacion": v.clasificacion.value,
    }


def _obtener_y_sincronizar_variantes(
    *,
    gen: Gen,
    q: str | None = None,
    clasificacion: str | None = None,
    limite: int | None = None,
    offset: int = 0,
    bioinformatica_client: Any | None = None,
    estricto: bool = False,
    codigo_no_disponible: str = "BIOINFORMATICS_API_UNAVAILABLE",
    status_no_disponible: int = 502,
    codigo_error_externo: str = "BIOINFORMATICS_API_ERROR",
    status_error_bd: int = 500,
    estudio_id: int | None = None,
) -> tuple[list[Variante], str]:
    """Consulta la API de bioinformatica con reintentos, sincroniza en BD y usa cache ante caida."""
    clasificacion_enum: ClasificacionVariante | None = None
    if clasificacion:
        clas_limpia = clasificacion.strip().lower()
        try:
            clasificacion_enum = ClasificacionVariante(clas_limpia)
        except ValueError as exc:
            raise ErrorDominio(
                "Clasificacion de variante invalida.",
                codigo="CLASIFICACION_INVALIDA",
                http_status=400,
            ) from exc

    if limite is not None and (limite <= 0 or limite > 500) or offset < 0:
        raise ErrorDominio(
            "Parametros de paginacion invalidos.",
            codigo="PAGINACION_INVALIDA",
            http_status=400,
        )

    cliente = _resolver_bioinformatica_client(bioinformatica_client)
    crudos: Any = None
    fallo_transitorio = False

    for intento in range(3):
        try:
            if q or clasificacion or limite is not None or offset:
                crudos = cliente.obtener_variantes(
                    gen.simbolo,
                    hgvs_c=q.strip() if q else None,
                    clasificacion=clasificacion_enum.value if clasificacion_enum else None,
                    limite=limite or 50,
                    offset=offset,
                )
            else:
                crudos = cliente.obtener_variantes(gen.simbolo)
            fallo_transitorio = False
            break
        except (ClienteConexionError, ClienteServicioError) as exc:
            fallo_transitorio = True
            logger.warning(
                "[bioinformatica_client] fallo transitorio gen_id=%s simbolo=%s intento=%s err=%s",
                gen.id,
                gen.simbolo,
                intento + 1,
                exc,
            )
            if intento < len(_BACKOFFS_BIOINFORMATICA):
                time.sleep(_BACKOFFS_BIOINFORMATICA[intento])
        except (ClienteError, httpx.HTTPStatusError, ValueError) as exc:
            logger.warning(
                "[bioinformatica_client] error permanente gen_id=%s simbolo=%s err=%s",
                gen.id,
                gen.simbolo,
                exc,
            )
            raise ErrorDominio(
                "Error al consultar la API de bioinformatica.",
                codigo=codigo_error_externo,
                http_status=502,
            ) from exc

    if fallo_transitorio:
        cacheadas = bioinformatica_repo.listar_variantes_por_gen(
            gen.id,
            q=q,
            clasificacion=clasificacion_enum,
            limite=limite,
            offset=offset,
        )
        if cacheadas:
            return cacheadas, "cache_local_contingencia"
        raise ErrorDominio(
            "Servicio de bioinformatica no disponible.",
            codigo=codigo_no_disponible,
            http_status=status_no_disponible,
            reintentable=True,
        )

    normalizadas = _normalizar_variantes_externas(crudos, estricto=estricto)
    logger.info(
        "[bioinformatica_client] step_2_consultar_variantes_gen simbolo=%s status=200 variantes_recibidas=%s",
        gen.simbolo,
        len(normalizadas),
    )

    try:
        variantes = bioinformatica_repo.sincronizar_variantes_gen(gen.id, normalizadas)
    except SQLAlchemyError as exc:
        bioinformatica_repo.deshacer_cambios()
        logger.error(
            "[bioinformatica_service] abort_cleanup_variantes estudio_id=%s gen_id=%s err=%s",
            estudio_id,
            gen.id,
            exc,
        )
        raise ErrorDominio(
            "Error al sincronizar el catalogo local de variantes.",
            codigo="DB_ERROR",
            http_status=status_error_bd,
            reintentable=True,
        ) from exc

    logger.info(
        "[clinica_repo] step_3_sincronizar_variantes_ok gen_id=%s total_variantes=%s",
        gen.id,
        len(variantes),
    )
    return variantes, "api_bioinformatica"


def consultar_variantes_gen(
    *,
    gen_id: int,
    q: str | None = None,
    clasificacion: str | None = None,
    limite: int | None = None,
    offset: int = 0,
    bioinformatica_client: Any | None = None,
) -> dict[str, Any]:
    """STEP 3 (Escenario 15): Consulta variantes en API de bioinformatica, sincroniza y cae a cache local."""
    gen = bioinformatica_repo.buscar_gen_por_id(gen_id)
    if gen is None:
        raise ErrorDominio("Gen no encontrado.", codigo="GEN_NO_ENCONTRADO", http_status=404)

    variantes, fuente = _obtener_y_sincronizar_variantes(
        gen=gen,
        q=q,
        clasificacion=clasificacion,
        limite=limite,
        offset=offset,
        bioinformatica_client=bioinformatica_client,
    )
    respuesta: dict[str, Any] = {
        "gen_id": gen.id,
        "simbolo": gen.simbolo,
        "nombre": gen.nombre,
        "fuente": fuente,
        "variantes": [_serializar_variante(v) for v in variantes],
    }
    if fuente == "cache_local_contingencia":
        respuesta["warning"] = "USANDO_CATALOGO_LOCAL_CACHEADO"
    return respuesta


def consultar_variantes_estudio(
    *,
    estudio_id: int,
    gen_id: int,
    usuario_id: int,
    q: str | None = None,
    clasificacion: str | None = None,
    limite: int | None = None,
    offset: int = 0,
    bioinformatica_client: Any | None = None,
) -> dict[str, Any]:
    """Escenario 24: Valida estudio y gen en analisis, consulta API de bioinformatica y sincroniza variantes."""
    try:
        estudio = bioinformatica_repo.buscar_estudio_por_id(estudio_id, completo=False)
        gen = bioinformatica_repo.buscar_gen_por_id(gen_id)
    except SQLAlchemyError as exc:
        bioinformatica_repo.deshacer_cambios()
        logger.error(
            "[analisis_service] step_1_error_bd estudio_id=%s gen_id=%s err=%s",
            estudio_id,
            gen_id,
            exc,
        )
        raise ErrorDominio(
            "No se pudo consultar el estudio o el gen en este momento.",
            codigo="DB_TIMEOUT_O_ERROR",
            http_status=504,
            reintentable=True,
        ) from exc

    if estudio is None or gen is None:
        raise ErrorDominio(
            "El estudio o el gen seleccionado no existe.",
            codigo="ESTUDIO_O_GEN_NO_ENCONTRADO",
            http_status=404,
        )

    if estudio.estado != EstadoEstudio.EN_ANALISIS_BIOINFORMATICO:
        raise ErrorDominio(
            "El estudio debe estar en estado 'En analisis de un bioinformatico' para consultar variantes.",
            codigo="ESTADO_ESTUDIO_INVALIDO_PARA_ANALISIS",
            http_status=409,
        )

    activo = _analisis_activo(estudio)
    if activo is None or activo.bioinformatico_id != usuario_id:
        raise ErrorDominio(
            "El estudio esta asignado a otro bioinformatico.",
            codigo="ESTUDIO_ASIGNADO_A_OTRO_BIOINFORMATICO",
            http_status=403,
        )

    genes_del_estudio = (
        {ag.gen_id for ag in activo.genes}
        if activo.genes
        else {eg.gen_id for eg in estudio.genes}
    )
    if gen.id not in genes_del_estudio:
        raise ErrorDominio(
            "El gen seleccionado no pertenece a la lista de genes a analizar en este estudio.",
            codigo="GEN_NO_SOLICITADO_EN_ESTUDIO",
            http_status=422,
        )

    logger.info(
        "[analisis_service] step_1_validar_consulta_variantes estudio_id=%s gen_id=%s simbolo=%s",
        estudio.id,
        gen.id,
        gen.simbolo,
    )

    variantes, fuente = _obtener_y_sincronizar_variantes(
        gen=gen,
        q=q,
        clasificacion=clasificacion,
        limite=limite,
        offset=offset,
        bioinformatica_client=bioinformatica_client,
        estricto=True,
        codigo_no_disponible="API_BIOINFORMATICA_NO_DISPONIBLE",
        status_no_disponible=503,
        codigo_error_externo="RESPUESTA_INVALIDA_API_BIOINFORMATICA",
        status_error_bd=503,
        estudio_id=estudio.id,
    )

    return {
        "estudio_id": estudio.id,
        "estado_estudio": estudio.estado.value,
        "gen": {
            "gen_id": gen.id,
            "simbolo": gen.simbolo,
            "nombre": gen.nombre,
        },
        "fuente": fuente,
        "variantes": [
            {
                "variante_id": v.id,
                "notacion": v.notacion,
                "clinvar_id": v.clinvar_id,
                "clasificacion": v.clasificacion.value,
            }
            for v in variantes
        ],
    }


def registrar_variantes_analisis(
    *,
    estudio_id: int,
    usuario_id: int,
    variantes_ids: list[int],
    email_client: EmailClient | None = None,
    ip_origen: str | None = None,
) -> dict[str, Any]:
    """STEP 4: Registra variantes del analisis y genera Resultado + notificaciones (Escenario 16)."""
    ids_unicos = list(dict.fromkeys(variantes_ids))

    estudio = bioinformatica_repo.buscar_estudio_por_id(estudio_id, bloquear=True)
    if estudio is None:
        raise ErrorDominio("Estudio no encontrado.", codigo="ESTUDIO_NO_ENCONTRADO", http_status=404)

    if estudio.estado != EstadoEstudio.EN_ANALISIS_BIOINFORMATICO:
        raise ErrorDominio(
            "El estudio debe estar en estado 'En analisis de un bioinformatico'.",
            codigo="ESTUDIO_NO_ESTA_EN_ANALISIS_BIOINFORMATICO",
            http_status=409,
        )

    activo = _analisis_activo(estudio)
    if activo is None:
        if any(a.bioinformatico_id == usuario_id and a.resultado is not None for a in estudio.analisis):
            raise ErrorDominio(
                "El analisis ya posee un resultado registrado.",
                codigo="RESULTADO_YA_EXISTE_PARA_ANALISIS",
                http_status=409,
            )
        raise ErrorDominio(
            "El estudio esta asignado a otro bioinformatico.",
            codigo="ESTUDIO_ASIGNADO_A_OTRO_BIOINFORMATICO",
            http_status=403,
        )
    if activo.bioinformatico_id != usuario_id:
        raise ErrorDominio(
            "El estudio esta asignado a otro bioinformatico.",
            codigo="ESTUDIO_ASIGNADO_A_OTRO_BIOINFORMATICO",
            http_status=403,
        )

    genes_habilitados = {ag.gen_id for ag in activo.genes} or {eg.gen_id for eg in estudio.genes}
    variantes = bioinformatica_repo.buscar_variantes_por_ids(ids_unicos)
    if len(variantes) != len(ids_unicos) or any(v.gen_id not in genes_habilitados for v in variantes):
        raise ErrorDominio(
            "La variante seleccionada no pertenece a los genes solicitados en este estudio.",
            codigo="VARIANTE_FUERA_DE_GENES_DEL_ESTUDIO",
            http_status=400,
        )

    variantes_por_id = {v.id: v for v in variantes}
    variantes_ordenadas = [variantes_por_id[vid] for vid in ids_unicos]

    ruta_pdf_creada = None
    try:
        bioinformatica_repo.agregar_variantes_analisis(activo.id, ids_unicos)
        resultado, ruta_pdf_creada, avisos_mail, contexto_mail = (
            resultado_service.preparar_resultado_en_transaccion(
                estudio=estudio,
                analisis=activo,
                variantes=variantes_ordenadas,
                usuario_bioinformatico_id=usuario_id,
                ip_origen=ip_origen,
            )
        )
        bioinformatica_repo.guardar_cambios()
    except ErrorDominio:
        bioinformatica_repo.deshacer_cambios()
        if ruta_pdf_creada is not None:
            ruta_pdf_creada.unlink(missing_ok=True)
        raise
    except IntegrityError as exc:
        bioinformatica_repo.deshacer_cambios()
        if ruta_pdf_creada is not None:
            ruta_pdf_creada.unlink(missing_ok=True)
        raise ErrorDominio(
            "El analisis ya posee un resultado registrado.",
            codigo="RESULTADO_YA_EXISTE_PARA_ANALISIS",
            http_status=409,
        ) from exc
    except SQLAlchemyError as exc:
        bioinformatica_repo.deshacer_cambios()
        if ruta_pdf_creada is not None:
            ruta_pdf_creada.unlink(missing_ok=True)
        raise ErrorDominio(
            "Error al registrar las variantes y resultado del analisis.",
            codigo="DB_ERROR",
            http_status=500,
            reintentable=True,
        ) from exc

    resultado_service.despachar_correos_resultado(
        avisos_mail=avisos_mail,
        contexto_mail=contexto_mail,
        email_client=email_client,
        cliente_cls=EmailClient,
    )

    if activo.tipo == TipoAnalisis.REANALISIS:
        logger.info(
            "[bioinformatica_service] reanalisis_completado estudio_id=%s analisis_id=%s resultado_id=%s",
            estudio.id,
            activo.id,
            resultado.id,
        )
    else:
        logger.info(
            '[bioinformatica_service] variantes_registradas estudio_id=%s analisis_id=%s variantes=%s estado="%s"',
            estudio.id,
            activo.id,
            ids_unicos,
            estudio.estado.value,
        )
    return {
        "estudio_id": estudio.id,
        "analisis_id": activo.id,
        "tipo_analisis": activo.tipo.value,
        "total_analisis_en_historial": len(estudio.analisis),
        "variantes_registradas": [
            {
                "id": v.id,
                "gen_simbolo": v.gen.simbolo if v.gen else "",
                "notacion": v.notacion,
                "clinvar_id": v.clinvar_id,
                "clasificacion": v.clasificacion.value,
            }
            for v in variantes_ordenadas
        ],
        "resultado": {
            "id": resultado.id,
            "positivo": bool(resultado.positivo),
            "diagnostico": resultado.diagnostico.value,
            "fecha_proximo_estudio": (
                resultado.fecha_proximo_estudio.isoformat()
                if resultado.fecha_proximo_estudio
                else None
            ),
            "pdf_path": resultado.pdf_path,
        },
        "estado_estudio": estudio.estado.value,
    }


def _validar_simbolo_gen_en_apigen(simbolo: str, cliente: Any) -> dict[str, Any] | None:
    """Consulta Apigen por prefijo y verifica coincidencia exacta del simbolo de gen."""
    try:
        items = cliente.buscar_genes(simbolo, limite=20)
    except (ClienteConexionError, ClienteServicioError) as exc:
        logger.warning("[bioinformatica_client] fallo transitorio buscar_genes simbolo=%s err=%s", simbolo, exc)
        raise ErrorDominio(
            "No se pudo validar los genes contra la API de bioinformatica. Intente nuevamente.",
            codigo="API_BIOINFORMATICA_NO_DISPONIBLE",
            http_status=503,
            reintentable=True,
        ) from exc
    except (ClienteError, httpx.HTTPStatusError, ValueError) as exc:
        logger.warning("[bioinformatica_client] error buscar_genes simbolo=%s err=%s", simbolo, exc)
        raise ErrorDominio(
            "Error al validar los genes contra la API de bioinformatica.",
            codigo="BIOINFORMATICS_API_ERROR",
            http_status=502,
        ) from exc

    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict) and str(item.get("simbolo", "")).strip().upper() == simbolo:
            return item
        if isinstance(item, str) and item.strip().upper() == simbolo:
            return {"simbolo": simbolo}
    return None


def _notificar_bioinformaticos_reanalisis(
    *,
    estudio: Estudio,
    analisis_id: int,
    simbolos_nuevos: list[str],
    avisos_mail: list[Aviso],
    destinatarios: list[str],
    email_client: EmailClient | None,
) -> None:
    mail_equipo = os.environ.get("BIOINFORMATICA_EQUIPO_EMAIL", "").strip()
    if mail_equipo and mail_equipo not in destinatarios:
        destinatarios.append(mail_equipo)

    cliente_email = resultado_service.resolver_email_client(email_client, cliente_cls=EmailClient)
    if destinatarios and cliente_email is not None:
        detalles_reanalisis = [
            f"Estudio: #{estudio.id} (Reanálisis #{analisis_id})",
            f"Nuevos genes solicitados: {', '.join(simbolos_nuevos)}",
            "Datos crudos: reutiliza la secuencia ACTG existente (sin nueva muestra).",
        ]
        if estudio.patologia_sospechada is not None:
            detalles_reanalisis.append(f"Patología sospechada: {estudio.patologia_sospechada.nombre}")
        cuerpo_reanalisis = formatear_correo(
            titulo="Solicitud de reanálisis bioinformático",
            introduccion=(
                f"Se solicitó un reanálisis sobre el estudio #{estudio.id}. "
                "El estudio volvió a la bandeja de bioinformática."
            ),
            destacado=[
                f"Estudio #{estudio.id} · Reanálisis #{analisis_id}",
                f"Nuevos genes: {', '.join(simbolos_nuevos)}",
            ],
            secciones=[("Detalle de la solicitud", detalles_reanalisis)],
            cierre="Ingresá a la bandeja de bioinformática para tomar el reanálisis.",
        )
        enviado = resultado_service.enviar_email_resiliente(
            cliente_email,
            asunto=asunto_correo(f"Reanálisis disponible · Estudio #{estudio.id} ({', '.join(simbolos_nuevos)})"),
            mensaje=cuerpo_reanalisis,
            destinatarios=destinatarios,
            referencia=f"REANALISIS-{estudio.id}-{analisis_id}",
            idempotency_key=f"reanalisis-{estudio.id}-{analisis_id}",
        )
        if enviado and avisos_mail:
            try:
                bioinformatica_repo.marcar_avisos_enviados(avisos_mail, resultado_service.ahora_utc_naive())
                bioinformatica_repo.guardar_cambios()
            except SQLAlchemyError as exc:
                bioinformatica_repo.deshacer_cambios()
                logger.warning(
                    "[bioinformatica_service] error_marcar_avisos_reanalisis estudio_id=%s analisis_id=%s err=%s",
                    estudio.id,
                    analisis_id,
                    exc,
                )


def solicitar_reanalisis_estudio(
    *,
    estudio_id: int,
    usuario: Usuario,
    nuevos_genes_simbolos: list[str] | None = None,
    genes_ids: list[int] | None = None,
    nueva_patologia_sospechada_id: int | None = None,
    bioinformatica_client: Any | None = None,
    email_client: EmailClient | None = None,
    ip_origen: str | None = None,
) -> dict[str, Any]:
    """Escenario 17 (STEP 1 y STEP 2): Valida y crea un Analisis(REANALISIS) sobre los DatosCrudos existentes."""
    if usuario.rol not in (Rol.MEDICO, Rol.GERENTE_MEDICO):
        raise ErrorDominio(
            "Solo un medico puede solicitar el reanalisis de un estudio.",
            codigo="SOLO_MEDICO",
            http_status=403,
        )

    medico = bioinformatica_repo.buscar_medico_por_usuario_id(usuario.id)
    if medico is None:
        raise ErrorDominio(
            "El usuario autenticado no posee perfil de medico activo.",
            codigo="SOLO_MEDICO",
            http_status=403,
        )

    estudio = bioinformatica_repo.buscar_estudio_por_id(estudio_id, bloquear=True)
    if estudio is None:
        raise ErrorDominio("Estudio no encontrado.", codigo="ESTUDIO_NO_ENCONTRADO", http_status=404)

    es_medico_autorizado = estudio.medico_id == medico.id or any(
        a.solicitado_por_id == medico.id for a in estudio.analisis
    )
    # shortcut: pacientes_medicos_autorizados (Escenario 40) aun no existe en models/; extender aqui al implementarlo
    if not es_medico_autorizado:
        logger.warning(
            "[estudio_service] reanalisis_denegado estudio_id=%s usuario_id=%s medico_id=%s",
            estudio.id,
            usuario.id,
            medico.id,
        )
        raise ErrorDominio(
            "No tiene permisos para solicitar un reanalisis sobre este estudio.",
            codigo="FORBIDDEN_REANALISIS_ESTUDIO",
            http_status=403,
        )

    if (
        estudio.estado != EstadoEstudio.RESULTADO_CARGADO
        or estudio.datos_crudos is None
        or _analisis_activo(estudio) is not None
    ):
        raise ErrorDominio(
            "El estudio debe estar en estado 'Resultado cargado' y contar con datos crudos para solicitar un reanalisis.",
            codigo="ESTUDIO_NO_APTO_PARA_REANALISIS",
            http_status=409,
        )

    nueva_patologia = None
    if nueva_patologia_sospechada_id is not None:
        nueva_patologia = clinica_repo.buscar_patologia_por_id(nueva_patologia_sospechada_id)
        if nueva_patologia is None:
            raise ErrorDominio(
                "La patologia sospechada indicada no existe.",
                codigo="PATOLOGIA_NO_ENCONTRADA",
                http_status=404,
            )

    simbolos_limpios: list[str] = []
    for raw in nuevos_genes_simbolos or []:
        simbolo = str(raw).strip().upper()
        if not simbolo:
            continue
        if not _PATRON_SIMBOLO_GEN.match(simbolo):
            raise ErrorDominio(
                f"El simbolo de gen '{simbolo}' tiene un formato invalido.",
                codigo="GEN_SIMBOLO_INVALIDO",
                http_status=400,
            )
        if simbolo not in simbolos_limpios:
            simbolos_limpios.append(simbolo)

    ids_limpios = list(dict.fromkeys(genes_ids or []))

    logger.info(
        "[estudio_service] validando_reanalisis estudio_id=%s medico_id=%s nuevos_genes=%s",
        estudio.id,
        medico.id,
        simbolos_limpios or ids_limpios,
    )

    genes_solicitados: list[Gen] = []
    vistos_gen_ids: set[int] = set()

    if ids_limpios:
        encontrados_ids = {g.id: g for g in clinica_repo.buscar_genes_por_ids(ids_limpios)}
        faltantes_ids = [gid for gid in ids_limpios if gid not in encontrados_ids]
        if faltantes_ids:
            raise ErrorDominio(
                "Alguno de los genes seleccionados no existe en el catalogo.",
                codigo="GEN_NO_ENCONTRADO",
                http_status=400,
            )
        for gid in ids_limpios:
            genes_solicitados.append(encontrados_ids[gid])
            vistos_gen_ids.add(gid)

    simbolos_para_crear: list[dict[str, Any]] = []
    if simbolos_limpios:
        encontrados_sim = {
            g.simbolo.upper(): g for g in clinica_repo.buscar_genes_por_simbolos(simbolos_limpios)
        }
        faltantes_sim = [s for s in simbolos_limpios if s not in encontrados_sim]
        if faltantes_sim:
            cliente = _resolver_bioinformatica_client(bioinformatica_client)
            for simbolo in faltantes_sim:
                info = _validar_simbolo_gen_en_apigen(simbolo, cliente)
                if info is None:
                    raise ErrorDominio(
                        f"El gen '{simbolo}' no fue encontrado en el catalogo de bioinformatica.",
                        codigo="GEN_DESCONOCIDO",
                        http_status=400,
                    )
                simbolos_para_crear.append(
                    {
                        "simbolo": simbolo,
                        "nombre": info.get("nombre"),
                        "es_hallazgo_secundario": bool(info.get("es_hallazgo_secundario", False)),
                    }
                )
        for simbolo in simbolos_limpios:
            gen_local = encontrados_sim.get(simbolo)
            if gen_local is not None and gen_local.id not in vistos_gen_ids:
                genes_solicitados.append(gen_local)
                vistos_gen_ids.add(gen_local.id)

    if not simbolos_limpios and not ids_limpios and nueva_patologia is not None:
        for gen_pat in nueva_patologia.genes:
            if gen_pat.id not in vistos_gen_ids:
                genes_solicitados.append(gen_pat)
                vistos_gen_ids.add(gen_pat.id)

    if not genes_solicitados and not simbolos_para_crear:
        raise ErrorDominio(
            "Debe indicar al menos un gen nuevo para solicitar el reanalisis.",
            codigo="GENES_YA_ANALIZADOS_O_VACIOS",
            http_status=400,
        )

    genes_ya_analizados_ids = {ag.gen_id for a in estudio.analisis for ag in a.genes}
    if not genes_ya_analizados_ids and estudio.analisis:
        genes_ya_analizados_ids = {eg.gen_id for eg in estudio.genes}
    simbolos_previos = sorted(
        {ag.gen.simbolo for a in estudio.analisis for ag in a.genes if ag.gen is not None}
    )

    genes_existentes_nuevos = [g for g in genes_solicitados if g.id not in genes_ya_analizados_ids]
    if not genes_existentes_nuevos and not simbolos_para_crear:
        raise ErrorDominio(
            "Todos los genes solicitados ya fueron analizados previamente en este estudio.",
            codigo="GENES_YA_ANALIZADOS_O_VACIOS",
            http_status=400,
        )

    patologia_objetivo = nueva_patologia or estudio.patologia_sospechada
    patologia_genes_ids = (
        {g.id for g in patologia_objetivo.genes} if patologia_objetivo is not None else set()
    )
    ahora = resultado_service.ahora_utc_naive()
    bioinformaticos = usuario_repo.listar_por_rol(Rol.BIOINFORMATICO)
    avisos_mail: list[Aviso] = []
    destinatarios: list[str] = []

    try:
        genes_creados = [
            clinica_repo.crear_gen(
                simbolo=item["simbolo"],
                nombre=item["nombre"],
                es_hallazgo_secundario=item["es_hallazgo_secundario"],
            )
            for item in simbolos_para_crear
        ]
        nuevos_genes = [*genes_existentes_nuevos, *genes_creados]
        nuevos_genes_ids = [g.id for g in nuevos_genes]
        simbolos_nuevos = [g.simbolo for g in nuevos_genes]

        nuevo_analisis = bioinformatica_repo.crear_analisis_reanalisis(
            estudio_id=estudio.id,
            solicitado_por_id=medico.id,
            genes_ids=nuevos_genes_ids,
        )

        genes_con_origen = [
            (
                g.id,
                OrigenGen.PATOLOGIA
                if g.id in patologia_genes_ids
                else (OrigenGen.HALLAZGO_SECUNDARIO if g.es_hallazgo_secundario else OrigenGen.MANUAL),
            )
            for g in nuevos_genes
        ]
        bioinformatica_repo.agregar_genes_estudio(estudio, genes_con_origen)

        estado_anterior = estudio.estado.value
        patologia_anterior_id = estudio.patologia_sospechada_id
        if nueva_patologia is not None:
            estudio.patologia_sospechada_id = nueva_patologia.id
        estudio.estado = EstadoEstudio.EN_ANALISIS_BIOINFORMATICA

        cambios_auditoria: dict[str, Any] = {
            "estado": {
                "anterior": estado_anterior,
                "nuevo": EstadoEstudio.EN_ANALISIS_BIOINFORMATICA.value,
            },
            "analisis_id": {"anterior": None, "nuevo": nuevo_analisis.id},
            "tipo_analisis": {"anterior": None, "nuevo": TipoAnalisis.REANALISIS.value},
            "nuevos_genes": {"anterior": simbolos_previos, "nuevo": simbolos_nuevos},
        }
        if nueva_patologia is not None and patologia_anterior_id != nueva_patologia.id:
            cambios_auditoria["patologia_sospechada_id"] = {
                "anterior": patologia_anterior_id,
                "nuevo": nueva_patologia.id,
            }

        auditoria_service.registrar_modificacion(
            entidad_tipo=EntidadAuditable.ESTUDIO,
            entidad_id=estudio.id,
            accion=TipoAccionAuditoria.CAMBIO_ESTADO,
            usuario_id=usuario.id,
            origen="usuario",
            cambios=cambios_auditoria,
            motivo="Solicitud de reanalisis de estudio",
            ip_origen=ip_origen,
        )

        aviso_msg = (
            f"Reanalisis solicitado para estudio #{estudio.id} sobre nuevos genes: "
            f"{', '.join(simbolos_nuevos)}."
        )
        for bio_u in bioinformaticos:
            bioinformatica_repo.crear_aviso(
                usuario_id=bio_u.id,
                mensaje=aviso_msg,
                canal=CanalAviso.APP,
                enviado=True,
                enviado_en=ahora,
            )
            avisos_mail.append(
                bioinformatica_repo.crear_aviso(
                    usuario_id=bio_u.id,
                    mensaje=aviso_msg,
                    canal=CanalAviso.MAIL,
                    enviado=False,
                )
            )
            if bio_u.email and bio_u.email not in destinatarios:
                destinatarios.append(bio_u.email)

        bioinformatica_repo.guardar_cambios()
    except (IntegrityError, SQLAlchemyError) as exc:
        bioinformatica_repo.deshacer_cambios()
        raise ErrorDominio(
            "Error al registrar la solicitud de reanalisis. Intente nuevamente.",
            codigo="DB_ERROR",
            http_status=500,
            reintentable=True,
        ) from exc

    _notificar_bioinformaticos_reanalisis(
        estudio=estudio,
        analisis_id=nuevo_analisis.id,
        simbolos_nuevos=simbolos_nuevos,
        avisos_mail=avisos_mail,
        destinatarios=destinatarios,
        email_client=email_client,
    )

    logger.info(
        "[estudio_service] reanalisis_creado estudio_id=%s analisis_id=%s solicitado_por_medico_id=%s",
        estudio.id,
        nuevo_analisis.id,
        medico.id,
    )
    return {
        "estudio_id": estudio.id,
        "analisis_id": nuevo_analisis.id,
        "tipo_analisis": TipoAnalisis.REANALISIS.value,
        "solicitado_por_medico_id": medico.id,
        "nuevos_genes": [
            {"gen_id": g.id, "simbolo": g.simbolo, "nombre": g.nombre}
            for g in nuevos_genes
        ],
        "estado_estudio": estudio.estado.value,
        "requiere_nueva_muestra": False,
    }


def buscar_genes_catalogo(
    *,
    q: str | None = None,
    limite: int = 30,
    bioinformatica_client: Any | None = None,
) -> list[dict[str, Any]]:
    """Lista genes locales y complementa por prefijo con Apigen si hay query de >= 2 caracteres."""
    if limite <= 0 or limite > 100:
        raise ErrorDominio(
            "El parametro limite debe ser un entero entre 1 y 100.",
            codigo="DATOS_INVALIDOS",
            http_status=400,
        )

    locales = clinica_repo.listar_genes_locales(q, limite=limite)
    por_simbolo: dict[str, dict[str, Any]] = {
        g.simbolo.upper(): {
            "gen_id": g.id,
            "simbolo": g.simbolo,
            "nombre": g.nombre,
            "es_hallazgo_secundario": bool(g.es_hallazgo_secundario),
        }
        for g in locales
    }

    consulta = (q or "").strip()
    puede_consultar_externo = len(consulta) >= 2 and (
        bioinformatica_client is not None
        or not (
            has_app_context()
            and current_app.config.get("TESTING")
            and not current_app.config.get("BIOINFORMATICA_CLIENT")
        )
    )
    if puede_consultar_externo and len(por_simbolo) < limite:
        try:
            cliente = _resolver_bioinformatica_client(bioinformatica_client)
            remotos = cliente.buscar_genes(consulta, limite=limite)
            if isinstance(remotos, list):
                for item in remotos:
                    simbolo = (
                        str(item.get("simbolo", "")).strip().upper()
                        if isinstance(item, dict)
                        else str(item).strip().upper()
                    )
                    if simbolo and simbolo not in por_simbolo:
                        por_simbolo[simbolo] = {
                            "gen_id": None,
                            "simbolo": simbolo,
                            "nombre": item.get("nombre") if isinstance(item, dict) else None,
                            "es_hallazgo_secundario": False,
                        }
        except (ClienteError, httpx.HTTPStatusError, OSError, ValueError) as exc:
            logger.warning("[bioinformatica_client] fallback catalogo genes q=%r err=%s", consulta, exc)

    return sorted(por_simbolo.values(), key=lambda g: g["simbolo"])[:limite]
