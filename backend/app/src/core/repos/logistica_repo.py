"""Repositorio para la gestion logistica de ordenes del dia y muestras."""
from __future__ import annotations

from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from ..database import db
from ..models import (
    CentroExtraccion,
    EstadoEstudio,
    Estudio,
    Muestra,
    OrdenDelDia,
    OrdenDelDiaParada,
    PosicionTransporte,
    Transportista,
    Turno,
)


class LogisticaRepo:
    """Acceso a datos para transporte terrestre y ordenes del dia."""

    @staticmethod
    def obtener_transportista_por_usuario(usuario_id: int) -> Transportista | None:
        stmt = select(Transportista).where(Transportista.usuario_id == usuario_id)
        return db.session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def obtener_orden_del_dia(transportista_id: int, fecha: date) -> OrdenDelDia | None:
        stmt = (
            select(OrdenDelDia)
            .where(
                OrdenDelDia.transportista_id == transportista_id,
                OrdenDelDia.fecha == fecha,
            )
            .options(
                selectinload(OrdenDelDia.paradas).selectinload(OrdenDelDiaParada.centro),
                selectinload(OrdenDelDia.posiciones),
            )
        )
        return db.session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def obtener_orden_por_id(orden_id: int) -> OrdenDelDia | None:
        stmt = (
            select(OrdenDelDia)
            .where(OrdenDelDia.id == orden_id)
            .options(
                selectinload(OrdenDelDia.transportista),
                selectinload(OrdenDelDia.paradas).selectinload(OrdenDelDiaParada.centro),
                selectinload(OrdenDelDia.posiciones),
            )
        )
        return db.session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def obtener_parada_por_id(orden_id: int, parada_id: int) -> OrdenDelDiaParada | None:
        stmt = (
            select(OrdenDelDiaParada)
            .where(
                OrdenDelDiaParada.id == parada_id,
                OrdenDelDiaParada.orden_id == orden_id,
            )
            .options(selectinload(OrdenDelDiaParada.centro))
        )
        return db.session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def listar_centros_con_muestras_listas(provincia: str) -> list[CentroExtraccion]:
        """Centros de la provincia que tienen muestras vigentes en Lista para retirar."""
        stmt = (
            select(CentroExtraccion)
            .join(Turno, Turno.centro_id == CentroExtraccion.id)
            .join(Muestra, Muestra.turno_id == Turno.id)
            .join(Estudio, Estudio.id == Muestra.estudio_id)
            .where(
                CentroExtraccion.provincia == provincia,
                Estudio.estado == EstadoEstudio.LISTA_PARA_RETIRAR,
                Muestra.motivo_descarte.is_(None),
                Muestra.llegada_lab_central.is_(None),
            )
            .distinct()
            .order_by(CentroExtraccion.id.asc())
        )
        return list(db.session.execute(stmt).scalars().all())

    @staticmethod
    def crear_orden_del_dia(
        transportista_id: int,
        fecha: date,
        centros_ordenados: list[CentroExtraccion],
    ) -> OrdenDelDia:
        orden = OrdenDelDia(transportista_id=transportista_id, fecha=fecha)
        db.session.add(orden)
        db.session.flush()

        for posicion, centro in enumerate(centros_ordenados, start=1):
            db.session.add(
                OrdenDelDiaParada(
                    orden_id=orden.id,
                    centro_id=centro.id,
                    posicion=posicion,
                )
            )
        db.session.flush()
        return orden

    @staticmethod
    def reemplazar_paradas_orden(
        orden_id: int,
        centros_ordenados: list[CentroExtraccion],
    ) -> None:
        """Reemplaza el orden de paradas pendientes cuando aun no hubo recogidas."""
        db.session.execute(
            delete(OrdenDelDiaParada).where(OrdenDelDiaParada.orden_id == orden_id)
        )
        db.session.flush()
        for posicion, centro in enumerate(centros_ordenados, start=1):
            db.session.add(
                OrdenDelDiaParada(
                    orden_id=orden_id,
                    centro_id=centro.id,
                    posicion=posicion,
                )
            )
        db.session.flush()

    @staticmethod
    def listar_muestras_por_centro_y_estado(
        centro_id: int,
        estado_estudio: EstadoEstudio,
    ) -> list[Muestra]:
        """Muestras vigentes provenientes de turnos en ese centro cuyo estudio esta en estado_estudio."""
        stmt = (
            select(Muestra)
            .join(Turno, Turno.id == Muestra.turno_id)
            .join(Estudio, Estudio.id == Muestra.estudio_id)
            .where(
                Turno.centro_id == centro_id,
                Estudio.estado == estado_estudio,
                Muestra.motivo_descarte.is_(None),
            )
            .options(selectinload(Muestra.estudio))
        )
        return list(db.session.execute(stmt).scalars().all())

    @staticmethod
    def registrar_posicion(orden_id: int, latitud: float, longitud: float) -> PosicionTransporte:
        pos = PosicionTransporte(orden_id=orden_id, latitud=latitud, longitud=longitud)
        db.session.add(pos)
        return pos

    @staticmethod
    def guardar_cambios() -> None:
        db.session.commit()

    @staticmethod
    def deshacer_cambios() -> None:
        db.session.rollback()