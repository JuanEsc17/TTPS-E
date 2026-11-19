"""Repositorio de acceso a datos para datos crudos, analisis bioinformatico, variantes y resultados."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from src.core.database import db
from src.core.models import (
    Analisis,
    AnalisisGen,
    AnalisisVariante,
    Aviso,
    CanalAviso,
    ClasificacionVariante,
    ConclusionDiagnostica,
    DatosCrudos,
    EstadoEstudio,
    Estudio,
    EstudioGen,
    Gen,
    Medico,
    Paciente,
    Resultado,
    TipoAnalisis,
    Variante,
)


def _opciones_estudio_completo():
    return (
        selectinload(Estudio.datos_crudos),
        selectinload(Estudio.paciente).selectinload(Paciente.usuario),
        selectinload(Estudio.medico).selectinload(Medico.usuario),
        selectinload(Estudio.patologia_sospechada),
        selectinload(Estudio.genes).selectinload(EstudioGen.gen),
        selectinload(Estudio.analisis).selectinload(Analisis.genes).selectinload(AnalisisGen.gen),
        selectinload(Estudio.analisis)
        .selectinload(Analisis.variantes)
        .selectinload(AnalisisVariante.variante),
        selectinload(Estudio.analisis).selectinload(Analisis.resultado),
    )


def _opciones_estudio_analisis():
    return (
        selectinload(Estudio.genes),
        selectinload(Estudio.analisis).selectinload(Analisis.genes),
        selectinload(Estudio.analisis).selectinload(Analisis.resultado),
    )


def buscar_estudio_por_id(
    estudio_id: int,
    *,
    bloquear: bool = False,
    completo: bool = True,
) -> Estudio | None:
    """Obtiene un estudio con sus relaciones clinicas y de analisis."""
    opciones = _opciones_estudio_completo() if completo else _opciones_estudio_analisis()
    stmt = (
        select(Estudio)
        .where(Estudio.id == estudio_id)
        .options(*opciones)
    )
    if bloquear:
        stmt = stmt.with_for_update()
    return db.session.scalar(stmt)


def listar_estudios_por_estado(estado: EstadoEstudio) -> list[Estudio]:
    """Lista estudios en un estado priorizando Pompe urgente y orden cronologico FIFO."""
    stmt = (
        select(Estudio)
        .where(Estudio.estado == estado)
        .options(*_opciones_estudio_completo())
        .order_by(
            Estudio.es_pompe_urgente.desc(),
            Estudio.updated_at.asc(),
            Estudio.id.asc(),
        )
    )
    return list(db.session.scalars(stmt).all())


def crear_datos_crudos(
    *,
    estudio_id: int,
    cargado_por_id: int,
    archivo_path: str,
) -> DatosCrudos:
    """Persiste el registro de datos crudos para el estudio."""
    datos = DatosCrudos(
        estudio_id=estudio_id,
        cargado_por_id=cargado_por_id,
        archivo_path=archivo_path,
    )
    db.session.add(datos)
    db.session.flush()
    return datos


def crear_analisis_inicial(estudio_id: int, genes_ids: list[int]) -> Analisis:
    """Crea el analisis inicial del estudio y copia los genes solicitados."""
    analisis = Analisis(
        estudio_id=estudio_id,
        tipo=TipoAnalisis.INICIAL,
        bioinformatico_id=None,
    )
    db.session.add(analisis)
    db.session.flush()

    for gen_id in dict.fromkeys(genes_ids):
        db.session.add(AnalisisGen(analisis_id=analisis.id, gen_id=gen_id))
    db.session.flush()
    return analisis


def copiar_genes_a_analisis(analisis_id: int, genes_ids: list[int]) -> None:
    """Asocia genes a un analisis existente sin duplicar claves."""
    for gen_id in dict.fromkeys(genes_ids):
        db.session.add(AnalisisGen(analisis_id=analisis_id, gen_id=gen_id))
    db.session.flush()


def buscar_gen_por_id(gen_id: int) -> Gen | None:
    return db.session.get(Gen, gen_id)


def listar_variantes_por_gen(
    gen_id: int,
    *,
    q: str | None = None,
    clasificacion: ClasificacionVariante | None = None,
    limite: int | None = None,
    offset: int = 0,
) -> list[Variante]:
    """Consulta el catalogo local cacheado de variantes de un gen."""
    stmt = select(Variante).where(Variante.gen_id == gen_id)
    if q:
        stmt = stmt.where(Variante.notacion.ilike(f"%{q.strip()}%"))
    if clasificacion is not None:
        stmt = stmt.where(Variante.clasificacion == clasificacion)
    stmt = stmt.order_by(Variante.notacion.asc(), Variante.id.asc())
    if offset:
        stmt = stmt.offset(offset)
    if limite is not None:
        stmt = stmt.limit(limite)
    return list(db.session.scalars(stmt).all())


def _aplicar_upsert_variantes(gen_id: int, items: list[dict[str, Any]]) -> list[Variante]:
    notaciones = [item["notacion"] for item in items]
    dialecto = db.session.get_bind().dialect.name
    insert_fn = pg_insert if dialecto == "postgresql" else sqlite_insert
    filas = [
        {
            "gen_id": gen_id,
            "notacion": item["notacion"],
            "clinvar_id": item["clinvar_id"],
            "clasificacion": item["clasificacion"],
        }
        for item in items
    ]
    stmt = insert_fn(Variante).values(filas)
    stmt = stmt.on_conflict_do_update(
        index_elements=["gen_id", "notacion"],
        set_={
            "clasificacion": stmt.excluded.clasificacion,
            "clinvar_id": func.coalesce(stmt.excluded.clinvar_id, Variante.clinvar_id),
        },
    )
    db.session.execute(stmt)
    db.session.flush()
    return list(
        db.session.scalars(
            select(Variante)
            .where(Variante.gen_id == gen_id, Variante.notacion.in_(notaciones))
            .order_by(Variante.notacion.asc(), Variante.id.asc())
            .execution_options(populate_existing=True)
        ).all()
    )


def sincronizar_variantes_gen(gen_id: int, items: list[dict[str, Any]]) -> list[Variante]:
    """Sincroniza (upsert por gen_id y notacion) las variantes conocidas de un gen."""
    if not items:
        return []
    try:
        variantes = _aplicar_upsert_variantes(gen_id, items)
        db.session.commit()
        return variantes
    except IntegrityError:
        db.session.rollback()
        variantes = _aplicar_upsert_variantes(gen_id, items)
        db.session.commit()
        return variantes


def buscar_variantes_por_ids(variantes_ids: list[int]) -> list[Variante]:
    """Obtiene variantes por sus IDs junto con su Gen."""
    if not variantes_ids:
        return []
    stmt = (
        select(Variante)
        .where(Variante.id.in_(variantes_ids))
        .options(selectinload(Variante.gen))
    )
    return list(db.session.scalars(stmt).all())


def agregar_variantes_analisis(analisis_id: int, variantes_ids: list[int]) -> None:
    """Registra las variantes seleccionadas en analisis_variantes."""
    for variante_id in dict.fromkeys(variantes_ids):
        db.session.add(AnalisisVariante(analisis_id=analisis_id, variante_id=variante_id))
    db.session.flush()


def crear_resultado(
    *,
    analisis_id: int,
    positivo: bool,
    diagnostico: ConclusionDiagnostica,
    fecha_proximo_estudio: date | None,
    pdf_path: str,
    generado_en: datetime,
) -> Resultado:
    """Persiste la fila de resultado clinico del analisis."""
    resultado = Resultado(
        analisis_id=analisis_id,
        positivo=positivo,
        diagnostico=diagnostico,
        fecha_proximo_estudio=fecha_proximo_estudio,
        pdf_path=pdf_path,
        generado_en=generado_en,
    )
    db.session.add(resultado)
    db.session.flush()
    return resultado


def crear_aviso(
    *,
    usuario_id: int,
    mensaje: str,
    canal: CanalAviso,
    enviado: bool = False,
    enviado_en: datetime | None = None,
) -> Aviso:
    aviso = Aviso(
        usuario_id=usuario_id,
        mensaje=mensaje[:500],
        canal=canal,
        enviado=enviado,
        enviado_en=enviado_en,
    )
    db.session.add(aviso)
    return aviso


def marcar_avisos_enviados(avisos: list[Aviso], enviado_en: datetime) -> None:
    for aviso in avisos:
        aviso.enviado = True
        aviso.enviado_en = enviado_en


def guardar_cambios() -> None:
    db.session.commit()


def deshacer_cambios() -> None:
    db.session.rollback()
