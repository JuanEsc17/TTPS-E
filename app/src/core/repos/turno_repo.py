"""Repositorio para la persistencia de turnos y centros de extraccion."""
from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from src.core.database import db
from src.core.models.economia import Presupuesto
from src.core.models.estudios import Estudio
from src.core.models.perfiles import Paciente
from src.core.models.turnos import CentroExtraccion, Turno
from src.core.models.usuarios import Aviso, CanalAviso


class TurnoRepo:
    """Operaciones de acceso a datos para Centros de Extraccion, Turnos y Estudios."""

    @staticmethod
    def listar_centros() -> list[CentroExtraccion]:
        """Retorna todos los centros de extraccion ordenados por nombre."""
        stmt = select(CentroExtraccion).order_by(CentroExtraccion.nombre.asc())
        return list(db.session.execute(stmt).scalars().all())

    @staticmethod
    def obtener_centro_por_id(centro_id: int) -> CentroExtraccion | None:
        """Busca un centro de extraccion por su ID."""
        return db.session.get(CentroExtraccion, centro_id)

    @staticmethod
    def obtener_turno_por_id(turno_id: int) -> Turno | None:
        """Busca un turno por su ID."""
        return db.session.get(Turno, turno_id)

    @staticmethod
    def obtener_estudio_por_id(
        estudio_id: int,
        bloquear: bool = False,
    ) -> Estudio | None:
        """Busca un estudio por su ID cargando relaciones necesarias.

        Si bloquear=True, aplica SELECT ... FOR UPDATE sobre la fila de estudio.
        """
        stmt = (
            select(Estudio)
            .options(
                joinedload(Estudio.paciente).joinedload(Paciente.usuario),
                joinedload(Estudio.presupuesto).joinedload(Presupuesto.pagos),
            )
            .where(Estudio.id == estudio_id)
        )
        if bloquear:
            stmt = stmt.with_for_update(of=Estudio)
        return db.session.execute(stmt).unique().scalars().first()

    @staticmethod
    def buscar_turno_activo_por_estudio(estudio_id: int) -> Turno | None:
        """Busca si un estudio ya tiene un turno reservado pendiente de asistencia."""
        stmt = select(Turno).where(
            Turno.estudio_id == estudio_id,
            Turno.activo.is_(True),
            Turno.asistio.is_(None),
        )
        return db.session.execute(stmt).scalars().first()

    @staticmethod
    def listar_turnos_ocupados(centro_id: int, fecha: date) -> list[Turno]:
        """Retorna los turnos activos reservados para un centro en una fecha dada."""
        inicio_dia = datetime.combine(fecha, time.min)
        fin_dia = datetime.combine(fecha, time.max)

        stmt = (
            select(Turno)
            .where(
                Turno.centro_id == centro_id,
                Turno.activo.is_(True),
                Turno.inicio >= inicio_dia,
                Turno.inicio <= fin_dia,
            )
            .order_by(Turno.inicio.asc())
        )
        return list(db.session.execute(stmt).scalars().all())

    @staticmethod
    def crear_turno(
        centro_id: int,
        paciente_id: int,
        estudio_id: int,
        inicio: datetime,
    ) -> Turno:
        """Crea y persiste un nuevo turno en estado activo.

        Ejecuta flush() para validar inmediatamente constraints como uq_turno_activo.
        """
        turno = Turno(
            centro_id=centro_id,
            paciente_id=paciente_id,
            estudio_id=estudio_id,
            inicio=inicio,
            activo=True,
            asistio=None,
        )
        db.session.add(turno)
        db.session.flush()
        return turno

    @staticmethod
    def crear_aviso(
        usuario_id: int,
        mensaje: str,
        canal: CanalAviso = CanalAviso.MAIL,
        enviado: bool = False,
    ) -> Aviso:
        """Registra una notificacion para el usuario."""
        aviso = Aviso(
            usuario_id=usuario_id,
            mensaje=mensaje,
            canal=canal,
            enviado=enviado,
            enviado_en=datetime.now() if enviado else None,
        )
        db.session.add(aviso)
        db.session.flush()
        return aviso

    @staticmethod
    def marcar_aviso_enviado(aviso: Aviso) -> None:
        """Marca un aviso existente como enviado registrando la fecha y hora."""
        aviso.enviado = True
        aviso.enviado_en = datetime.now()
        db.session.flush()

    @staticmethod
    def guardar_cambios() -> None:
        """Confirma la transaccion en la base de datos."""
        db.session.commit()

    @staticmethod
    def deshacer_cambios() -> None:
        """Revierte la transaccion en caso de error."""
        db.session.rollback()