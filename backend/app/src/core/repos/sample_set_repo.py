"""Repositorio para la formacion y consulta de SampleSets (Escenarios 12 y 14)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..database import db
from ..models import (
    Aviso,
    CanalAviso,
    EstadoSampleSet,
    Estudio,
    Muestra,
    Paciente,
    Rol,
    SampleSet,
    Usuario,
)


class SampleSetRepo:
    """Acceso a datos para lotes SampleSet y muestras asociadas."""

    @staticmethod
    def obtener_abierto(bloquear: bool = True) -> SampleSet | None:
        """Retorna el SampleSet abierto actual aplicando lock opcional FOR UPDATE."""
        stmt = (
            select(SampleSet)
            .where(SampleSet.estado == EstadoSampleSet.ABIERTO)
            .options(selectinload(SampleSet.muestras).selectinload(Muestra.estudio))
            .order_by(SampleSet.id.asc())
        )
        if bloquear:
            stmt = stmt.with_for_update()
        return db.session.execute(stmt).scalars().first()

    @staticmethod
    def crear_sample_set(*, es_pompe_urgente: bool = False) -> SampleSet:
        """Crea un nuevo SampleSet en estado ABIERTO."""
        sample_set = SampleSet(
            estado=EstadoSampleSet.ABIERTO,
            es_pompe_urgente=es_pompe_urgente,
        )
        db.session.add(sample_set)
        db.session.flush()
        return sample_set

    @staticmethod
    def obtener_por_id(sample_set_id: int, bloquear: bool = False) -> SampleSet | None:
        """Obtiene un SampleSet con sus muestras, estudios, pacientes y patologia."""
        stmt = (
            select(SampleSet)
            .where(SampleSet.id == sample_set_id)
            .options(
                selectinload(SampleSet.muestras)
                .selectinload(Muestra.estudio)
                .selectinload(Estudio.paciente)
                .selectinload(Paciente.usuario),
                selectinload(SampleSet.muestras)
                .selectinload(Muestra.estudio)
                .selectinload(Estudio.patologia_sospechada),
            )
        )
        if bloquear:
            stmt = stmt.with_for_update()
        return db.session.execute(stmt).scalars().first()

    @staticmethod
    def listar(estado: EstadoSampleSet | None = None) -> list[SampleSet]:
        """Lista los SampleSets priorizando Pompe urgente y orden mas reciente."""
        stmt = select(SampleSet).options(
            selectinload(SampleSet.muestras)
            .selectinload(Muestra.estudio)
            .selectinload(Estudio.paciente)
            .selectinload(Paciente.usuario),
            selectinload(SampleSet.muestras)
            .selectinload(Muestra.estudio)
            .selectinload(Estudio.patologia_sospechada),
        )
        if estado is not None:
            stmt = stmt.where(SampleSet.estado == estado)
        stmt = stmt.order_by(SampleSet.es_pompe_urgente.desc(), SampleSet.id.desc())
        return list(db.session.execute(stmt).scalars().all())

    @staticmethod
    def listar_muestras_por_ids(muestras_ids: list[int], bloquear: bool = True) -> list[Muestra]:
        """Obtiene las muestras indicadas en orden deterministico junto con sus estudios."""
        if not muestras_ids:
            return []
        stmt = (
            select(Muestra)
            .where(Muestra.id.in_(muestras_ids))
            .options(selectinload(Muestra.estudio))
            .order_by(Muestra.id.asc())
        )
        if bloquear:
            stmt = stmt.with_for_update()
        return list(db.session.execute(stmt).scalars().all())

    @staticmethod
    def listar_usuarios_administrativos_ids() -> list[int]:
        """Lista IDs de usuarios administrativos para emitir avisos de cierre."""
        stmt = select(Usuario.id).where(Usuario.rol == Rol.ADMINISTRATIVO)
        return list(db.session.execute(stmt).scalars().all())

    @staticmethod
    def crear_aviso(usuario_id: int, mensaje: str) -> Aviso:
        """Registra una notificacion interna in-app para un usuario."""
        aviso = Aviso(
            usuario_id=usuario_id,
            mensaje=mensaje,
            canal=CanalAviso.APP,
            enviado=True,
            enviado_en=datetime.now(),
        )
        db.session.add(aviso)
        db.session.flush()
        return aviso

    @staticmethod
    def guardar_cambios() -> None:
        """Confirma la transaccion activa."""
        db.session.commit()

    @staticmethod
    def deshacer_cambios() -> None:
        """Revierte la transaccion activa ante un error."""
        db.session.rollback()

