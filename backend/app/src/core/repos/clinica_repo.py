"""Repositorio de acceso a datos para patologias, sintomas y genes."""
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import selectinload
from src.core.database import db
from src.core.models import Gen, Patologia, PatologiaGen, PatologiaSintoma, Sintoma


def listar_patologias() -> list[Patologia]:
    stmt = (
        select(Patologia)
        .options(
            selectinload(Patologia.sintomas).selectinload(PatologiaSintoma.sintoma),
            selectinload(Patologia.genes),
        )
        .order_by(Patologia.nombre.asc())
    )
    return list(db.session.scalars(stmt).all())


def buscar_patologia_por_id(patologia_id: int, *, for_update: bool = False) -> Patologia | None:
    stmt = (
        select(Patologia)
        .options(
            selectinload(Patologia.sintomas).selectinload(PatologiaSintoma.sintoma),
            selectinload(Patologia.genes),
        )
        .where(Patologia.id == patologia_id)
    )
    if for_update:
        stmt = stmt.with_for_update()
    return db.session.scalar(stmt)


def buscar_sintomas_locales(texto: str, limite: int = 20) -> list[Sintoma]:
    """Fallback local sobre tabla sintomas cuando SNOMED externo no responde."""
    patron_inicio = f"{texto}%"
    patron_contiene = f"%{texto}%"
    stmt = (
        select(Sintoma)
        .where(
            or_(
                Sintoma.descripcion.ilike(patron_inicio),
                Sintoma.descripcion.ilike(patron_contiene),
            )
        )
        .order_by(Sintoma.descripcion.asc())
        .limit(limite)
    )
    return list(db.session.scalars(stmt).all())


def buscar_sintomas_por_snomed_ids(snomed_ids: list[str]) -> list[Sintoma]:
    """Busca sintomas existentes a partir de sus codigos SNOMED."""
    if not snomed_ids:
        return []
    stmt = select(Sintoma).where(Sintoma.snomed_id.in_(snomed_ids))
    return list(db.session.scalars(stmt).all())


def sincronizar_sintomas(items: list[dict[str, str]]) -> list[Sintoma]:
    """Guarda en tabla local sintomas los terminos SNOMED nuevos (upsert por snomed_id)."""
    if not items:
        return []

    snomed_ids = [str(item["snomed_id"]).strip() for item in items if item.get("snomed_id")]
    existentes = {s.snomed_id: s for s in buscar_sintomas_por_snomed_ids(snomed_ids)}
    resultado: list[Sintoma] = []

    for item in items:
        sid = str(item["snomed_id"]).strip()
        desc = str(item["descripcion"]).strip()
        if not sid or not desc:
            continue
        if sid in existentes:
            resultado.append(existentes[sid])
        else:
            nuevo = Sintoma(snomed_id=sid, descripcion=desc[:255])
            db.session.add(nuevo)
            existentes[sid] = nuevo
            resultado.append(nuevo)

    db.session.commit()
    return resultado


def buscar_patologia_por_nombre(nombre: str, *, excluir_id: int | None = None) -> Patologia | None:
    stmt = select(Patologia).where(func.lower(Patologia.nombre) == nombre.strip().lower())
    if excluir_id is not None:
        stmt = stmt.where(Patologia.id != excluir_id)
    return db.session.scalar(stmt)


def upsert_sintomas(sintomas: list[dict[str, str]]) -> dict[str, Sintoma]:
    """Asegura en `sintomas` cada snomed_id y devuelve el mapa snomed_id -> Sintoma."""
    codigos = [s["snomed_id"] for s in sintomas]
    existentes = {
        s.snomed_id: s
        for s in db.session.scalars(select(Sintoma).where(Sintoma.snomed_id.in_(codigos))).all()
    }
    for item in sintomas:
        snomed_id = item["snomed_id"]
        if snomed_id in existentes:
            existentes[snomed_id].descripcion = item["descripcion"]
        else:
            nuevo = Sintoma(snomed_id=snomed_id, descripcion=item["descripcion"])
            db.session.add(nuevo)
            existentes[snomed_id] = nuevo
    db.session.flush()
    return existentes


def guardar_patologia_con_sintomas(
    *,
    patologia: Patologia | None,
    nombre: str,
    descripcion: str | None,
    sintoma_cardinal_id: int,
    sintomas_secundarios_ids: list[int],
) -> Patologia:
    """Crea o actualiza `Patologia` y reemplaza atómicamente `PatologiaSintoma`."""
    if patologia is None:
        patologia = Patologia(nombre=nombre, descripcion=descripcion)
        db.session.add(patologia)
        db.session.flush()
    else:
        patologia.nombre = nombre
        patologia.descripcion = descripcion
        # flush() tras DELETE evita violar el indice parcial uq_un_cardinal_por_patologia
        db.session.execute(delete(PatologiaSintoma).where(PatologiaSintoma.patologia_id == patologia.id))
        db.session.flush()

    db.session.add(PatologiaSintoma(patologia_id=patologia.id, sintoma_id=sintoma_cardinal_id, es_cardinal=True))
    for sec_id in sintomas_secundarios_ids:
        db.session.add(PatologiaSintoma(patologia_id=patologia.id, sintoma_id=sec_id, es_cardinal=False))
    db.session.flush()
    return patologia


def sincronizar_genes_patologia(patologia_id: int, genes_info: list[dict[str, object]]) -> list[Gen]:
    """Upsert de genes y reemplazo de asociaciones en `patologias_genes`."""
    simbolos = [str(g["simbolo"]).strip().upper() for g in genes_info if str(g.get("simbolo", "")).strip()]
    db.session.execute(delete(PatologiaGen).where(PatologiaGen.patologia_id == patologia_id))
    if not simbolos:
        db.session.commit()
        return []

    existentes = {
        g.simbolo.upper(): g
        for g in db.session.scalars(select(Gen).where(Gen.simbolo.in_(simbolos))).all()
    }
    genes_asociados: list[Gen] = []
    vistos: set[str] = set()
    for info in genes_info:
        simbolo = str(info.get("simbolo", "")).strip().upper()
        if not simbolo or simbolo in vistos:
            continue
        vistos.add(simbolo)
        gen = existentes.get(simbolo)
        if gen is None:
            gen = Gen(
                simbolo=simbolo,
                nombre=str(info["nombre"]) if info.get("nombre") else None,
                es_hallazgo_secundario=bool(info.get("es_hallazgo_secundario", False)),
            )
            db.session.add(gen)
            existentes[simbolo] = gen
        elif info.get("nombre") and not gen.nombre:
            gen.nombre = str(info["nombre"])
        genes_asociados.append(gen)

    db.session.flush()
    for gen in genes_asociados:
        db.session.add(PatologiaGen(patologia_id=patologia_id, gen_id=gen.id))
    db.session.commit()
    return genes_asociados


def buscar_genes_por_ids(genes_ids: list[int]) -> list[Gen]:
    """Obtiene genes por sus IDs."""
    if not genes_ids:
        return []
    stmt = select(Gen).where(Gen.id.in_(genes_ids))
    return list(db.session.scalars(stmt).all())


def buscar_genes_por_simbolos(simbolos: list[str]) -> list[Gen]:
    """Busca genes por simbolo (comparacion insensible a mayusculas)."""
    limpios = [s.strip().upper() for s in simbolos if s and s.strip()]
    if not limpios:
        return []
    stmt = select(Gen).where(func.upper(Gen.simbolo).in_(limpios))
    return list(db.session.scalars(stmt).all())


def crear_gen(
    *,
    simbolo: str,
    nombre: str | None = None,
    es_hallazgo_secundario: bool = False,
) -> Gen:
    """Inserta un nuevo Gen validado en la sesion actual sin hacer commit."""
    gen = Gen(
        simbolo=simbolo.strip().upper(),
        nombre=nombre.strip()[:255] if isinstance(nombre, str) and nombre.strip() else None,
        es_hallazgo_secundario=es_hallazgo_secundario,
    )
    db.session.add(gen)
    db.session.flush()
    return gen


def listar_genes_locales(q: str | None = None, *, limite: int = 30) -> list[Gen]:
    """Lista genes cacheados localmente con filtro opcional por simbolo o nombre."""
    stmt = select(Gen)
    if q and q.strip():
        texto = q.strip()
        stmt = stmt.where(
            or_(
                Gen.simbolo.ilike(f"{texto}%"),
                Gen.simbolo.ilike(f"%{texto}%"),
                Gen.nombre.ilike(f"%{texto}%"),
            )
        )
    stmt = stmt.order_by(Gen.simbolo.asc()).limit(limite)
    return list(db.session.scalars(stmt).all())
