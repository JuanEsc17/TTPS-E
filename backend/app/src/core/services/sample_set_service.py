"""Servicio de logica de negocio para armado y consulta de SampleSets (Escenarios 12 y 14)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from src.core.database import db
from src.core.models import (
    MUESTRAS_POR_SAMPLE_SET,
    EntidadAuditable,
    EstadoEstudio,
    EstadoSampleSet,
    Muestra,
    SampleSet,
    TipoAccionAuditoria,
)
from src.core.repos.sample_set_repo import SampleSetRepo
from src.core.services import auditoria_service
from src.core.services.excepciones import (
    ErrorBaseDatos,
    ErrorConflicto,
    ErrorNoEncontrado,
)

logger = logging.getLogger(__name__)


class SampleSetService:
    """Gestiona el agrupamiento automatico en lotes de 10 muestras y su inmutabilidad."""

    @staticmethod
    def serializar_detalle_sample_set(sample_set: SampleSet) -> dict[str, Any]:
        """Serializa un SampleSet junto con el detalle de sus muestras y estudios."""
        muestras_ordenadas = sorted(sample_set.muestras, key=lambda m: m.id)
        muestras_detalle: list[dict[str, Any]] = []
        for muestra in muestras_ordenadas:
            estudio = muestra.estudio
            pac = estudio.paciente if estudio else None
            pac_u = pac.usuario if pac else None
            patologia = estudio.patologia_sospechada if estudio else None
            muestras_detalle.append(
                {
                    "muestra_id": muestra.id,
                    "estudio_id": muestra.estudio_id,
                    "estado_estudio": estudio.estado.value if estudio else None,
                    "es_pompe_urgente": bool(estudio.es_pompe_urgente) if estudio else False,
                    "paciente_dni": pac.dni if pac else None,
                    "paciente_nombre": (
                        f"{pac_u.nombre} {pac_u.apellido}".strip() if pac_u else None
                    ),
                    "patologia": patologia.nombre if patologia else None,
                    "llegada_lab_central": (
                        muestra.llegada_lab_central.isoformat()
                        if muestra.llegada_lab_central
                        else None
                    ),
                }
            )

        return {
            "id": sample_set.id,
            "estado": sample_set.estado.value,
            "es_pompe_urgente": bool(sample_set.es_pompe_urgente),
            "cantidad_muestras": len(muestras_ordenadas),
            "capacidad_maxima": MUESTRAS_POR_SAMPLE_SET,
            "cerrado_en": sample_set.cerrado_en.isoformat() if sample_set.cerrado_en else None,
            "csv_path": sample_set.csv_path,
            "autorizacion_ministerio_pdf_path": sample_set.autorizacion_ministerio_pdf_path,
            "retiro_fedex_pedido_id": sample_set.retiro_fedex_pedido_id,
            "muestras_ids": [m.id for m in muestras_ordenadas],
            "muestras": muestras_detalle,
        }

    @classmethod
    def _cerrar_sample_set_en_tx(
        cls,
        sample_set: SampleSet,
        *,
        marca_tiempo: datetime,
        usuario_id: int | None,
        origen: str,
    ) -> None:
        """Sella el SampleSet, avanza sus estudios a EN_ESPERA_RETIRO, audita y notifica."""
        estado_previo_ss = sample_set.estado
        sample_set.estado = EstadoSampleSet.CERRADO
        sample_set.cerrado_en = marca_tiempo
        cantidad = len(sample_set.muestras)

        auditoria_service.registrar_modificacion(
            entidad_tipo=EntidadAuditable.SAMPLE_SET,
            entidad_id=sample_set.id,
            accion=TipoAccionAuditoria.CAMBIO_ESTADO,
            usuario_id=usuario_id,
            origen=origen,
            motivo=(
                "Cierre inmediato de sample-set por muestra Pompe urgente"
                if sample_set.es_pompe_urgente
                else f"Cierre automatico de sample-set al completar {cantidad} muestras"
            ),
            cambios={
                "estado": {
                    "anterior": estado_previo_ss.value,
                    "nuevo": EstadoSampleSet.CERRADO.value,
                },
                "cantidad_muestras": {"anterior": None, "nuevo": cantidad},
                "es_pompe_urgente": {
                    "anterior": None,
                    "nuevo": bool(sample_set.es_pompe_urgente),
                },
            },
        )

        for muestra in sorted(sample_set.muestras, key=lambda m: m.id):
            estudio = muestra.estudio
            if estudio is None or estudio.estado != EstadoEstudio.EN_LAB_CENTRAL:
                continue
            estado_anterior_est = estudio.estado
            estudio.estado = EstadoEstudio.EN_ESPERA_RETIRO
            auditoria_service.registrar_modificacion(
                entidad_tipo=EntidadAuditable.ESTUDIO,
                entidad_id=estudio.id,
                accion=TipoAccionAuditoria.CAMBIO_ESTADO,
                usuario_id=usuario_id,
                origen=origen,
                motivo=f"SampleSet #{sample_set.id} cerrado para retiro hacia Corea",
                cambios={
                    "estado": {
                        "anterior": estado_anterior_est.value,
                        "nuevo": EstadoEstudio.EN_ESPERA_RETIRO.value,
                    },
                    "sample_set_id": {"anterior": None, "nuevo": sample_set.id},
                },
            )

        etiqueta_urgente = " · POMPE URGENTE" if sample_set.es_pompe_urgente else ""
        mensaje_aviso = (
            f"SampleSet #{sample_set.id} cerrado ({cantidad}/{MUESTRAS_POR_SAMPLE_SET} "
            f"muestras{etiqueta_urgente}) y pasado a En espera de retiro."
        )
        for admin_uid in SampleSetRepo.listar_usuarios_administrativos_ids():
            SampleSetRepo.crear_aviso(usuario_id=admin_uid, mensaje=mensaje_aviso)

        logger.info(
            "[logistica_service] sample_set_actualizado sample_set_id=%s estado=%s cantidad_muestras=%s",
            sample_set.id,
            sample_set.estado.value,
            cantidad,
        )

    @classmethod
    def incorporar_muestras_en_tx(
        cls,
        muestras: list[Muestra],
        *,
        usuario_id: int | None = None,
        origen: str = "sistema",
        ahora: datetime | None = None,
    ) -> list[SampleSet]:
        """Agrupa muestras en lotes de 10 dentro de la transaccion activa."""
        if not muestras:
            return []

        marca_tiempo = ahora or datetime.now()
        lote_actual = SampleSetRepo.obtener_abierto(bloquear=True)
        lotes_afectados: list[SampleSet] = []
        lotes_vistos: set[int] = set()

        def _recordar_lote(lote: SampleSet) -> None:
            if lote.id not in lotes_vistos:
                lotes_vistos.add(lote.id)
                lotes_afectados.append(lote)

        for muestra in muestras:
            if muestra.sample_set_id is not None:
                lote_existente = SampleSetRepo.obtener_por_id(muestra.sample_set_id)
                if lote_existente is not None:
                    _recordar_lote(lote_existente)
                continue

            estudio = muestra.estudio
            if estudio is None or estudio.estado != EstadoEstudio.EN_LAB_CENTRAL:
                estado_actual = estudio.estado.value if estudio else "desconocido"
                raise ErrorConflicto(
                    f"La muestra #{muestra.id} (estudio en '{estado_actual}') no esta apta para ingresar a un sample-set.",
                    codigo="MUESTRA_NO_APTA_PARA_SAMPLE_SET",
                )

            if (
                lote_actual is None
                or lote_actual.estado != EstadoSampleSet.ABIERTO
                or len(lote_actual.muestras) >= MUESTRAS_POR_SAMPLE_SET
            ):
                lote_actual = SampleSetRepo.crear_sample_set(es_pompe_urgente=False)
                auditoria_service.registrar_modificacion(
                    entidad_tipo=EntidadAuditable.SAMPLE_SET,
                    entidad_id=lote_actual.id,
                    accion=TipoAccionAuditoria.CREACION,
                    usuario_id=usuario_id,
                    origen=origen,
                    motivo="Creacion de nuevo sample-set abierto en laboratorio central",
                    cambios={
                        "estado": {"anterior": None, "nuevo": EstadoSampleSet.ABIERTO.value}
                    },
                )

            if lote_actual.estado != EstadoSampleSet.ABIERTO:
                raise ErrorConflicto(
                    "El sample-set indicado ya se encuentra cerrado y no admite modificaciones.",
                    codigo="SAMPLE_SET_CERRADO_INMUTABLE",
                )

            muestra.sample_set_id = lote_actual.id
            if muestra not in lote_actual.muestras:
                lote_actual.muestras.append(muestra)
            if estudio.es_pompe_urgente:
                lote_actual.es_pompe_urgente = True
            db.session.flush()

            auditoria_service.registrar_modificacion(
                entidad_tipo=EntidadAuditable.SAMPLE_SET,
                entidad_id=lote_actual.id,
                accion=TipoAccionAuditoria.MODIFICACION,
                usuario_id=usuario_id,
                origen=origen,
                motivo=f"Incorporacion de muestra #{muestra.id} (Estudio #{estudio.id})",
                cambios={
                    "muestra_agregada_id": {"anterior": None, "nuevo": muestra.id},
                    "estudio_id": {"anterior": None, "nuevo": estudio.id},
                },
            )
            _recordar_lote(lote_actual)

            if (
                len(lote_actual.muestras) >= MUESTRAS_POR_SAMPLE_SET
                or lote_actual.es_pompe_urgente
            ):
                cls._cerrar_sample_set_en_tx(
                    lote_actual,
                    marca_tiempo=marca_tiempo,
                    usuario_id=usuario_id,
                    origen=origen,
                )
                lote_actual = None

        return lotes_afectados

    @classmethod
    def armar_sample_set_para_muestras_recibidas(
        cls,
        muestras_ids: list[int],
        *,
        usuario_id: int | None = None,
        origen: str = "sistema",
        ahora: datetime | None = None,
    ) -> list[int]:
        """Agrupa por IDs las muestras recibidas en laboratorio central y confirma cambios."""
        if not muestras_ids:
            return []
        try:
            muestras = SampleSetRepo.listar_muestras_por_ids(muestras_ids, bloquear=True)
            lotes = cls.incorporar_muestras_en_tx(
                muestras,
                usuario_id=usuario_id,
                origen=origen,
                ahora=ahora,
            )
            SampleSetRepo.guardar_cambios()
        except ErrorConflicto:
            SampleSetRepo.deshacer_cambios()
            raise
        except SQLAlchemyError as exc:
            SampleSetRepo.deshacer_cambios()
            raise ErrorBaseDatos(
                f"Error al armar sample-sets en laboratorio central: {exc!s}"
            ) from exc
        return [lote.id for lote in lotes]

    @classmethod
    def listar_sample_sets(cls, *, estado: EstadoSampleSet | None = None) -> list[dict[str, Any]]:
        """Lista los SampleSets del laboratorio ordenados por prioridad y fecha."""
        lotes = SampleSetRepo.listar(estado=estado)
        return [cls.serializar_detalle_sample_set(lote) for lote in lotes]

    @classmethod
    def obtener_sample_set(cls, sample_set_id: int) -> dict[str, Any]:
        """Devuelve el detalle completo de un SampleSet por ID."""
        lote = SampleSetRepo.obtener_por_id(sample_set_id)
        if lote is None:
            raise ErrorNoEncontrado(
                f"El sample-set #{sample_set_id} no existe.",
                codigo="SAMPLE_SET_NO_ENCONTRADO",
            )
        return cls.serializar_detalle_sample_set(lote)

