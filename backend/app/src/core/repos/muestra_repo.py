"""Repositorio para el registro de toma de muestras y remuestreo (Escenarios 9 y 10)."""
from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import contains_eager, joinedload, selectinload
from src.core.database import db
from src.core.models.enums import CanalAviso, EstadoEstudio
from src.core.models.estudios import Estudio
from src.core.models.logistica import Muestra
from src.core.models.perfiles import Medico, Paciente
from src.core.models.turnos import Turno
from src.core.models.usuarios import Aviso


class MuestraRepo:
    """Acceso a datos para consultas de turnos pendientes de extraccion y muestras."""

    @staticmethod
    def obtener_turno_para_toma(turno_id: int, bloquear: bool = False) -> Turno | None:
        """Obtiene un turno junto con su centro, paciente y estudio (opcionalmente con lock)
        ,evita que dos admins registren la muestra al mismo tiempo"""
        stmt = (
            select(Turno)
            .join(Turno.estudio)
            .options(
                joinedload(Turno.centro),
                joinedload(Turno.paciente).joinedload(Paciente.usuario),
                contains_eager(Turno.estudio).selectinload(Estudio.muestras),
            )
            .where(Turno.id == turno_id)
        )
        if bloquear:
            stmt = stmt.with_for_update(of=[Turno, Estudio])
        return db.session.execute(stmt).unique().scalars().first()

    @staticmethod
    def listar_turnos_pendientes_toma(
        dni: str | None = None,
        estudio_id: int | None = None,
        centro_id: int | None = None,
        fecha: date | None = None,
    ) -> list[Turno]:
        """Lista turnos activos sin muestra registrada cuyo estudio esta en Turno sacado."""
        muestra_existente = select(Muestra.id).where(Muestra.turno_id == Turno.id).exists()
        stmt = (
            select(Turno)
            .join(Turno.estudio)
            .join(Turno.paciente)
            .options(
                joinedload(Turno.centro),
                contains_eager(Turno.paciente).selectinload(Paciente.usuario),
                contains_eager(Turno.estudio),
            )
            .where(
                Turno.activo.is_(True),
                Turno.asistio.is_(None),
                Estudio.estado == EstadoEstudio.TURNO_SACADO,
                ~muestra_existente,
            )
        )

        if dni:
            stmt = stmt.where(Paciente.dni == dni.strip())
        if estudio_id is not None:
            stmt = stmt.where(Turno.estudio_id == estudio_id)
        if centro_id is not None:
            stmt = stmt.where(Turno.centro_id == centro_id)
        if fecha is not None:
            inicio_dia = datetime.combine(fecha, time.min)
            fin_dia = datetime.combine(fecha, time.max)
            stmt = stmt.where(Turno.inicio >= inicio_dia, Turno.inicio <= fin_dia)

        stmt = stmt.order_by(Turno.inicio.asc(), Turno.id.asc())
        return list(db.session.execute(stmt).unique().scalars().all())

    @staticmethod
    def existe_muestra_por_turno(turno_id: int) -> bool:
        """Verifica si ya existe una muestra registrada para un turno dado."""
        stmt = select(Muestra.id).where(Muestra.turno_id == turno_id).limit(1)
        return db.session.execute(stmt).scalars().first() is not None

    @staticmethod
    def registrar_asistencia_y_crear_muestra(
        turno: Turno,
        tomada_en: datetime,
    ) -> Muestra:
        """Marca asistencia en el turno y crea el registro de muestra asociado."""
        turno.asistio = True
        muestra = Muestra(
            estudio_id=turno.estudio_id,
            turno_id=turno.id,
            sample_set_id=None,
            tomada_en=tomada_en,
            llegada_lab_central=None,
            motivo_descarte=None,
        )
        db.session.add(muestra)
        db.session.flush()
        return muestra

    @staticmethod
    def crear_aviso(
        usuario_id: int,
        mensaje: str,
        canal: CanalAviso = CanalAviso.APP,
        enviado: bool = True,
    ) -> Aviso:
        """Registra una notificacion interna para el usuario."""
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
    def obtener_estudio_para_remuestreo(
        estudio_id: int,
        bloquear: bool = True,
    ) -> Estudio | None:
        """Obtiene un estudio con paciente, medico y muestras (con lock opcional)."""
        stmt = (
            select(Estudio)
            .options(
                joinedload(Estudio.paciente).joinedload(Paciente.usuario),
                joinedload(Estudio.medico).joinedload(Medico.usuario),
                joinedload(Estudio.patologia_sospechada),
                selectinload(Estudio.muestras),
            )
            .where(Estudio.id == estudio_id)
        )
        if bloquear:
            stmt = stmt.with_for_update(of=[Estudio])
        return db.session.execute(stmt).unique().scalars().first()

    @staticmethod
    def listar_estudios_remuestreables(
        estados_permitidos: tuple[EstadoEstudio, ...],
        dni: str | None = None,
        estudio_id: int | None = None,
    ) -> list[Estudio]:
        """Lista estudios en estados elegibles que poseen una muestra vigente sin descartar."""
        tiene_muestra_vigente = (
            select(Muestra.id)
            .where(
                Muestra.estudio_id == Estudio.id,
                Muestra.motivo_descarte.is_(None),
            )
            .exists()
        )
        stmt = (
            select(Estudio)
            .join(Estudio.paciente)
            .options(
                contains_eager(Estudio.paciente).joinedload(Paciente.usuario),
                joinedload(Estudio.medico).joinedload(Medico.usuario),
                joinedload(Estudio.patologia_sospechada),
                selectinload(Estudio.muestras),
            )
            .where(
                Estudio.estado.in_(estados_permitidos),
                tiene_muestra_vigente,
            )
        )

        if dni:
            stmt = stmt.where(Paciente.dni == dni.strip())
        if estudio_id is not None:
            stmt = stmt.where(Estudio.id == estudio_id)

        stmt = stmt.order_by(
            Estudio.es_pompe_urgente.desc(),
            Estudio.updated_at.asc(),
            Estudio.id.asc(),
        )
        return list(db.session.execute(stmt).unique().scalars().all())

    @staticmethod
    def guardar_cambios() -> None:
        """Confirma la transaccion en la base de datos."""
        db.session.commit()

    @staticmethod
    def deshacer_cambios() -> None:
        """Revierte la transaccion ante un error."""
        db.session.rollback()