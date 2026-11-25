"""Repositorio de acceso a datos para presupuestos y autorizaciones (Escenario 3)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import contains_eager, joinedload
from src.core.database import db
from src.core.models.economia import Autorizacion, ObraSocial, Presupuesto
from src.core.models.enums import CanalAviso, EstadoEstudio, ResultadoAutorizacion
from src.core.models.estudios import Estudio, EstudioGen
from src.core.models.perfiles import Medico, Paciente
from src.core.models.usuarios import Aviso


class EconomiaRepo:
    """Unico lugar donde se consulta o escribe la base para el flujo de presupuestos."""

    @staticmethod
    def obtener_estudio_para_presupuesto(estudio_id: int) -> Estudio | None:
        """Obtiene el estudio con bloqueo de fila (SELECT ... FOR UPDATE)."""
        stmt = select(Estudio).where(Estudio.id == estudio_id).with_for_update()
        return db.session.execute(stmt).scalars().first()

    @staticmethod
    def contar_genes(estudio_id: int) -> int:
        """Cuenta todos los genes asociados al estudio (cualquier origen)."""
        stmt = select(func.count()).select_from(EstudioGen).where(EstudioGen.estudio_id == estudio_id)
        return db.session.scalar(stmt) or 0


    @staticmethod
    def listar_estudios_pendientes_presupuesto(dni: str | None = None) -> list[tuple[Estudio, int]]:
        """Estudios en Creado sin presupuesto, con su cantidad de genes en la misma consulta."""
        cantidad_genes = (
            select(func.count())
            .select_from(EstudioGen)
            .where(EstudioGen.estudio_id == Estudio.id)
            .correlate(Estudio)
            .scalar_subquery()
        )
        tiene_presupuesto = select(Presupuesto.id).where(Presupuesto.estudio_id == Estudio.id).exists()

        stmt = (
            select(Estudio, cantidad_genes.label("cantidad_genes"))
            .join(Estudio.paciente)
            .options(
                contains_eager(Estudio.paciente).joinedload(Paciente.usuario),
                joinedload(Estudio.medico).joinedload(Medico.usuario),
                joinedload(Estudio.patologia_sospechada),
                joinedload(Estudio.obra_social),
            )
            .where(Estudio.estado == EstadoEstudio.CREADO, ~tiene_presupuesto)
            .order_by(Estudio.es_pompe_urgente.desc(), Estudio.created_at.asc(), Estudio.id.asc())
        )
        if dni:
            stmt = stmt.where(Paciente.dni.contains(dni))
        return [(estudio, total) for estudio, total in db.session.execute(stmt).all()]

    @staticmethod
    def obtener_obra_social(obra_social_id: int) -> ObraSocial | None:
        return db.session.get(ObraSocial, obra_social_id)

    @staticmethod
    def crear_presupuesto(
        *, estudio_id: int, emitido_por_id: int, cantidad_genes: int, monto_total_usd: Decimal
    ) -> Presupuesto:
        presupuesto = Presupuesto(
            estudio_id=estudio_id,
            emitido_por_id=emitido_por_id,
            cantidad_genes=cantidad_genes,
            monto_total_usd=monto_total_usd,
        )
        db.session.add(presupuesto)
        db.session.flush()
        return presupuesto

    @staticmethod
    def crear_autorizacion(*, estudio_id: int, solicitud_externa_id: str | None) -> Autorizacion:
        autorizacion = Autorizacion(
            estudio_id=estudio_id,
            resultado=ResultadoAutorizacion.PENDIENTE,
            solicitud_externa_id=solicitud_externa_id,
        )
        db.session.add(autorizacion)
        db.session.flush()
        return autorizacion

    @staticmethod
    def crear_aviso(*, usuario_id: int, mensaje: str) -> Aviso:
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
        db.session.commit()

    @staticmethod
    def deshacer_cambios() -> None:
        db.session.rollback()