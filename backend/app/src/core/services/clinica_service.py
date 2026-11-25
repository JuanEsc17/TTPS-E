"""Logica de negocio clinica: patologias y sintomas SNOMED (Escenario 36)."""
from sqlalchemy.exc import SQLAlchemyError
from src.clients.exceptions import ClienteError
from src.clients.snomed_client import SnomedClient
from src.core.models import Patologia, Sintoma
from src.core.repos import clinica_repo
from src.core.services.excepciones import ErrorDominio


def listar_patologias() -> list[dict]:
    """Retorna el catalogo de patologias para seleccion de diagnostico presuntivo."""
    patologias = clinica_repo.listar_patologias()
    return [
        {"id": p.id, "nombre": p.nombre, "descripcion": p.descripcion}
        for p in patologias
    ]


def buscar_sintomas_snomed(
    q: str,
    *,
    limite: int = 20,
    snomed_client: SnomedClient | None = None,
) -> dict:
    """Busca sintomas en SNOMED (minimo 3 letras) con fallback a catalogo local."""
    texto = (q or "").strip()
    if len(texto) < 3:
        raise ErrorDominio(
            "Debe ingresar al menos 3 caracteres para buscar sintomas en SNOMED.",
            codigo="PREFIJO_DEMASIADO_CORTO",
            http_status=422,
        )

    cliente = snomed_client or SnomedClient(timeout=2.0)

    try:
        crudos = cliente.buscar_sintomas(texto, limite=min(max(limite, 1), 50))
        normalizados = [
            {
                "snomed_id": str(item["sctid"]),
                "descripcion": str(item["termino_preferido"]),
            }
            for item in crudos
            if item.get("sctid") and item.get("termino_preferido")
        ]
        # Cachea en PostgreSQL/SQLite los terminos devueltos por SNOMED
        clinica_repo.sincronizar_sintomas(normalizados)
        return {"fuente": "snomed_api", "resultados": normalizados}
    except ClienteError:
        # Si SNOMED externo falla o vence el timeout, hace fallback a la tabla local
        try:
            locales = clinica_repo.buscar_sintomas_locales(texto, limite=limite)
            return {
                "fuente": "local_fallback",
                "resultados": [
                    {"snomed_id": s.snomed_id, "descripcion": s.descripcion}
                    for s in locales
                ],
            }
        except SQLAlchemyError as exc:
            raise ErrorDominio(
                "El servicio SNOMED no se encuentra disponible temporalmente.",
                codigo="SNOMED_NO_DISPONIBLE",
                http_status=502,
                reintentable=True,
            ) from exc


def validar_sintomas_contra_patologia(
    *,
    patologia_id: int,
    sintomas_snomed_ids: list[str],
    sintomas_detalle: list[dict[str, str]] | None = None,
) -> tuple[Patologia, list[Sintoma]]:
    """Valida que los sintomas cumplan: >= 1 cardinal OR >= 2 secundarios de la patologia."""
    ids_limpios = list(dict.fromkeys(str(sid).strip() for sid in sintomas_snomed_ids if str(sid).strip()))
    if not ids_limpios:
        raise ErrorDominio(
            "Debe seleccionar al menos un sintoma para el paciente.",
            codigo="SINTOMAS_REQUERIDOS",
            http_status=422,
        )

    patologia = clinica_repo.buscar_patologia_por_id(patologia_id)
    if patologia is None:
        raise ErrorDominio(
            "La patologia indicada como diagnostico presuntivo no existe.",
            codigo="PATOLOGIA_NO_ENCONTRADA",
            http_status=404,
        )

    # Si el frontend mando {snomed_id, descripcion}, sincroniza los nuevos antes de validar
    if sintomas_detalle:
        clinica_repo.sincronizar_sintomas(sintomas_detalle)

    sintomas_entidades = clinica_repo.buscar_sintomas_por_snomed_ids(ids_limpios)
    if len(sintomas_entidades) != len(ids_limpios):
        raise ErrorDominio(
            "Uno o mas sintomas seleccionados no existen en el catalogo SNOMED.",
            codigo="SINTOMA_NO_REGISTRADO",
            http_status=422,
        )

    # Mapea sintoma_id -> es_cardinal y por descripcion en minuscula (cubre conceptos SNOMED equivalentes)
    mapa_patologia = {ps.sintoma_id: ps.es_cardinal for ps in patologia.sintomas}
    mapa_por_nombre = {
        ps.sintoma.descripcion.strip().lower(): ps.es_cardinal
        for ps in patologia.sintomas
        if ps.sintoma and ps.sintoma.descripcion
    }

    cardinales = 0
    secundarios = 0
    for sintoma in sintomas_entidades:
        es_cardinal = mapa_patologia.get(sintoma.id)
        if es_cardinal is None:
            es_cardinal = mapa_por_nombre.get((sintoma.descripcion or "").strip().lower())

        if es_cardinal is not None:
            if es_cardinal:
                cardinales += 1
            else:
                secundarios += 1

    if cardinales < 1 and secundarios < 2:
        raise ErrorDominio(
            "Los sintomas seleccionados no corresponden al diagnostico presuntivo: "
            "se requiere el sintoma cardinal o al menos dos sintomas secundarios de la patologia.",
            codigo="SINTOMAS_INCOMPATIBLES_PATOLOGIA",
            http_status=422,
        )

    return patologia, sintomas_entidades