"""Repositorio de acceso a datos para patologias y sintomas SNOMED."""
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload
from src.core.database import db
from src.core.models import Patologia, PatologiaSintoma, Sintoma


def listar_patologias() -> list[Patologia]:
    """Devuelve todas las patologias ordenadas alfabeticamente."""
    stmt = select(Patologia).order_by(Patologia.nombre.asc())
    return list(db.session.scalars(stmt).all())


def buscar_patologia_por_id(patologia_id: int) -> Patologia | None:
    """Obtiene una patologia junto con sus sintomas cardinal/secundarios."""
    stmt = (
        select(Patologia)
        .options(selectinload(Patologia.sintomas).selectinload(PatologiaSintoma.sintoma))
        .where(Patologia.id == patologia_id)
    )
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