"""Servicio de logica de negocio para analisis bioinformatico (Escenarios 15 y 24)."""
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
    Rol,
    TipoAccionAuditoria,
    Variante,
)
from src.core.repos import bioinformatica_repo, usuario_repo
from src.core.services import auditoria_service, resultado_service
from src.core.services.excepciones import ErrorDominio

logger = logging.getLogger(__name__)
_EMAIL_CLIENT_ORIGINAL = EmailClient

MAX_BYTES_DATOS_CRUDOS = 5 * 1024 * 1024  # 5 MB
_BACKOFFS_BIOINFORMATICA = (0.5, 1.0)

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
        enviado = resultado_service.enviar_email_resiliente(
            cliente_email,
            asunto=f"Estudio #{estudio.id} en analisis por bioinformatica",
            mensaje=aviso_msg,
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

    logger.info(
        "[bioinformatica_service] estudio_tomado estudio_id=%s analisis_id=%s bioinformatico_id=%s",
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
    if activo is None or activo.bioinformatico_id != usuario_id:
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
