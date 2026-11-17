"""Servicio de gestion clinica de patologias y sintomas SNOMED (Escenario 23)."""
import logging
import time
from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from src.clients.apigen_client import ApigenClient
from src.clients.exceptions import (
    ClienteConexionError,
    ClienteError,
    ClienteServicioError,
)
from src.clients.snomed_client import SnomedClient
from src.core.database import db
from src.core.models import Patologia
from src.core.repos import clinica_repo
from src.core.services.excepciones import ErrorDominio

logger = logging.getLogger(__name__)


def _serializar_patologia(patologia: Patologia, *, genes_sincronizados: bool = True) -> dict[str, Any]:
    cardinal = None
    secundarios = []
    for rel in patologia.sintomas:
        item = {
            "sintoma_id": rel.sintoma.id,
            "snomed_id": rel.sintoma.snomed_id,
            "descripcion": rel.sintoma.descripcion,
            "es_cardinal": bool(rel.es_cardinal),
        }
        if rel.es_cardinal:
            cardinal = item
        else:
            secundarios.append(item)

    secundarios.sort(key=lambda s: s["descripcion"].lower())
    return {
        "patologia_id": patologia.id,
        "nombre": patologia.nombre,
        "descripcion": patologia.descripcion,
        "sintoma_cardinal": cardinal,
        "sintomas_secundarios": secundarios,
        "genes": [
            {"id": g.id, "simbolo": g.simbolo, "nombre": g.nombre}
            for g in sorted(patologia.genes, key=lambda gen: gen.simbolo)
        ],
        "genes_sincronizados": genes_sincronizados,
    }


def _normalizar_sintoma(item: dict[str, Any] | None) -> dict[str, str] | None:
    if not isinstance(item, dict):
        return None
    snomed_id = str(item.get("snomed_id", "")).strip()
    descripcion = str(item.get("descripcion", "")).strip()
    if not snomed_id or not descripcion:
        return None
    return {"snomed_id": snomed_id, "descripcion": descripcion}


def _validar_estructura(
    nombre: str,
    sintoma_cardinal: dict[str, Any] | None,
    sintomas_secundarios: list[dict[str, Any]] | None,
) -> tuple[str, dict[str, str], list[dict[str, str]]]:
    nombre_limpio = nombre.strip()
    if not (1 <= len(nombre_limpio) <= 120):
        raise ErrorDominio(
            "El nombre de la patologia debe tener entre 1 y 120 caracteres.",
            codigo="ESTRUCTURA_PATOLOGIA_INVALIDA",
            http_status=400,
        )

    cardinal = _normalizar_sintoma(sintoma_cardinal)
    if cardinal is None:
        raise ErrorDominio(
            "Debe indicar exactamente un sintoma cardinal con codigo SNOMED y descripcion.",
            codigo="ESTRUCTURA_PATOLOGIA_INVALIDA",
            http_status=400,
        )

    if not isinstance(sintomas_secundarios, list) or len(sintomas_secundarios) < 2:
        raise ErrorDominio(
            "La patologia debe incluir al menos 2 sintomas secundarios.",
            codigo="ESTRUCTURA_PATOLOGIA_INVALIDA",
            http_status=400,
        )

    secundarios_limpios: list[dict[str, str]] = []
    codigos_vistos: set[str] = set()
    for raw in sintomas_secundarios:
        sec = _normalizar_sintoma(raw)
        if sec is None:
            raise ErrorDominio(
                "Todos los sintomas secundarios deben incluir codigo SNOMED y descripcion.",
                codigo="ESTRUCTURA_PATOLOGIA_INVALIDA",
                http_status=400,
            )
        if sec["snomed_id"] == cardinal["snomed_id"]:
            raise ErrorDominio(
                "El sintoma cardinal no puede estar repetido en la lista de sintomas secundarios.",
                codigo="ESTRUCTURA_PATOLOGIA_INVALIDA",
                http_status=400,
            )
        if sec["snomed_id"] in codigos_vistos:
            raise ErrorDominio(
                "No puede repetir sintomas secundarios con el mismo codigo SNOMED.",
                codigo="ESTRUCTURA_PATOLOGIA_INVALIDA",
                http_status=400,
            )
        codigos_vistos.add(sec["snomed_id"])
        secundarios_limpios.append(sec)

    return nombre_limpio, cardinal, secundarios_limpios


def _sincronizar_genes_resiliente(
    patologia_id: int,
    nombre_patologia: str,
    apigen_client: ApigenClient | None,
) -> bool:
    cliente = apigen_client or ApigenClient()
    crudos: list[Any] | None = None
    for intento in range(3):
        try:
            crudos = cliente.obtener_genes_por_patologia(nombre_patologia)
            break
        except (ClienteConexionError, ClienteServicioError) as exc:
            logger.warning(
                "[patologia_service] fallo transitorio bioinformatica patologia_id=%s intento=%s err=%s",
                patologia_id,
                intento + 1,
                exc,
            )
            if intento < 2:
                time.sleep(0.5 * (intento + 1))
        except ClienteError as exc:
            logger.warning("[patologia_service] error cliente bioinformatica patologia_id=%s err=%s", patologia_id, exc)
            return False

    if crudos is None:
        return False

    genes_info = [
        item if isinstance(item, dict) else {"simbolo": str(item), "nombre": None, "es_hallazgo_secundario": False}
        for item in crudos
    ]
    try:
        clinica_repo.sincronizar_genes_patologia(patologia_id, genes_info)
        return True
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.warning("[patologia_service] error persistiendo genes patologia_id=%s err=%s", patologia_id, exc)
        return False


def listar_patologias() -> list[dict[str, Any]]:
    return [_serializar_patologia(p) for p in clinica_repo.listar_patologias()]


def buscar_sintomas_snomed(
    texto: str,
    *,
    limite: int = 10,
    snomed_client: SnomedClient | None = None,
) -> list[dict[str, str]]:
    consulta = texto.strip()
    if len(consulta) < 3:
        raise ErrorDominio(
            "Ingrese al menos 3 caracteres para buscar sintomas en SNOMED.",
            codigo="QUERY_SNOMED_CORTA",
            http_status=400,
        )
    cliente = snomed_client or SnomedClient()
    try:
        resultados = cliente.buscar_sintomas(consulta, limite=limite)
    except (ClienteConexionError, ClienteServicioError) as exc:
        raise ErrorDominio(
            "El servicio de terminologia SNOMED no esta disponible en este momento.",
            codigo="SNOMED_NO_DISPONIBLE",
            http_status=503,
            reintentable=True,
        ) from exc
    except ClienteError as exc:
        raise ErrorDominio(str(exc), codigo="SNOMED_CONSULTA_INVALIDA", http_status=400) from exc

    return [
        {
            "snomed_id": str(item.get("sctid", "")).strip(),
            "descripcion": str(item.get("termino_preferido", "")).strip(),
        }
        for item in resultados
        if item.get("sctid") and item.get("termino_preferido")
    ]


def guardar_patologia(
    *,
    gerente_usuario_id: int,
    nombre: str,
    descripcion: str | None = None,
    sintoma_cardinal: dict[str, Any] | None = None,
    sintomas_secundarios: list[dict[str, Any]] | None = None,
    patologia_id: int | None = None,
    apigen_client: ApigenClient | None = None,
) -> dict[str, Any]:
    operacion = "modificacion" if patologia_id is not None else "alta"
    logger.info(
        "[patologia_service] step_1_validar_patologia gerente_usuario_id=%s nombre=%s operacion=%s",
        gerente_usuario_id,
        nombre,
        operacion,
    )
    nombre_limpio, cardinal, secundarios = _validar_estructura(nombre, sintoma_cardinal, sintomas_secundarios)
    desc_limpia = descripcion.strip() if isinstance(descripcion, str) and descripcion.strip() else None

    existente: Patologia | None = None
    if patologia_id is not None:
        existente = clinica_repo.buscar_patologia_por_id(patologia_id, for_update=True)
        if existente is None:
            raise ErrorDominio("Patologia no encontrada.", codigo="PATOLOGIA_NO_ENCONTRADA", http_status=404)

    if clinica_repo.buscar_patologia_por_nombre(nombre_limpio, excluir_id=patologia_id) is not None:
        raise ErrorDominio(
            f"Ya existe una patologia registrada con el nombre '{nombre_limpio}'.",
            codigo="PATOLOGIA_NOMBRE_DUPLICADO",
            http_status=409,
        )

    try:
        mapa_sintomas = clinica_repo.upsert_sintomas([cardinal, *secundarios])
        patologia = clinica_repo.guardar_patologia_con_sintomas(
            patologia=existente,
            nombre=nombre_limpio,
            descripcion=desc_limpia,
            sintoma_cardinal_id=mapa_sintomas[cardinal["snomed_id"]].id,
            sintomas_secundarios_ids=[mapa_sintomas[s["snomed_id"]].id for s in secundarios],
        )
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ErrorDominio(
            "Conflicto de concurrencia al guardar la patologia o su sintoma cardinal.",
            codigo="CONFLICTO_CONCURRENTE_PATOLOGIA",
            http_status=409,
        ) from exc
    except SQLAlchemyError as exc:
        db.session.rollback()
        raise ErrorDominio(
            "Error al persistir la patologia en la base de datos. Intente nuevamente.",
            codigo="DB_ERROR",
            http_status=503,
            reintentable=True,
        ) from exc

    genes_ok = _sincronizar_genes_resiliente(patologia.id, patologia.nombre, apigen_client)
    db.session.expire_all()
    patologia_final = clinica_repo.buscar_patologia_por_id(patologia.id) or patologia
    logger.info(
        "[patologia_service] step_4_sincronizar_genes_patologia patologia_id=%s genes_sincronizados=%s",
        patologia.id,
        genes_ok,
    )
    return _serializar_patologia(patologia_final, genes_sincronizados=genes_ok)
