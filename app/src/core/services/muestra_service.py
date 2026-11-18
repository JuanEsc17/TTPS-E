"""Servicio de logica de negocio para el registro de toma de muestras (Escenario 9)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from src.core.models.enums import CanalAviso, EstadoEstudio
from src.core.models.turnos import Turno
from src.core.repos.muestra_repo import MuestraRepo


class MuestraService:
    """Coordina la consulta de turnos pendientes y el registro manual de extracciones."""

    @staticmethod
    def _serializar_turno_pendiente(turno: Turno) -> dict[str, Any]:
        """Convierte un Turno pendiente de extraccion en un diccionario listo para la API."""
        usuario = turno.paciente.usuario if turno.paciente else None
        nombre_completo = (
            f"{usuario.nombre} {usuario.apellido}".strip()
            if usuario
            else None
        )
        return {
            "turno_id": turno.id,
            "estudio_id": turno.estudio_id,
            "estado_estudio": turno.estudio.estado.value if turno.estudio else None,
            "es_pompe_urgente": turno.estudio.es_pompe_urgente if turno.estudio else False,
            "inicio": turno.inicio.isoformat(),
            "centro_id": turno.centro_id,
            "centro_nombre": turno.centro.nombre if turno.centro else None,
            "centro_provincia": turno.centro.provincia if turno.centro else None,
            "paciente_id": turno.paciente_id,
            "paciente_dni": turno.paciente.dni if turno.paciente else None,
            "paciente_nombre": nombre_completo,
        }

    @classmethod
    def listar_turnos_pendientes_toma(
        cls,
        dni: str | None = None,
        estudio_id: int | None = None,
        centro_id: int | None = None,
        fecha: date | None = None,
    ) -> tuple[list[dict[str, Any]], str | None, int]:
        """Retorna los turnos activos en estado Turno sacado sin muestra registrada."""
        turnos = MuestraRepo.listar_turnos_pendientes_toma(
            dni=dni,
            estudio_id=estudio_id,
            centro_id=centro_id,
            fecha=fecha,
        )
        return [cls._serializar_turno_pendiente(t) for t in turnos], None, 200

    @classmethod
    def registrar_toma_muestra(
        cls,
        turno_id: int,
        usuario_actual_id: int | None = None,
        tomada_en: datetime | None = None,
    ) -> tuple[dict[str, Any] | None, str | None, int]:
        """Registra que la muestra fue tomada tras el aviso telefonico del centro."""
        fecha_toma = tomada_en or datetime.now()
        if fecha_toma.tzinfo is not None:
            fecha_toma = fecha_toma.replace(tzinfo=None)

        # 1. Buscar y bloquear el Turno y su Estudio para evitar registros concurrentes
        turno = MuestraRepo.obtener_turno_para_toma(turno_id, bloquear=True)
        if not turno:
            return None, f"El turno con ID {turno_id} no existe.", 404

        # 2. Validar reglas de negocio sobre el turno y el estado del estudio
        if not turno.activo:
            if turno.asistio is False:
                return (
                    None,
                    "El turno ya fue procesado como ausencia y no admite toma de muestra.",
                    409,
                )
            return None, "El turno fue cancelado y no se encuentra activo.", 409

        if turno.asistio is True or MuestraRepo.existe_muestra_por_turno(turno.id):
            return None, "La toma de muestra para este turno ya fue registrada previamente.", 409

        estudio = turno.estudio
        if estudio.estado != EstadoEstudio.TURNO_SACADO:
            return (
                None,
                (
                    f"El estudio #{estudio.id} no esta en estado Turno sacado "
                    f"(estado actual: {estudio.estado.value})."
                ),
                409,
            )

        # 3. Persistencia atomica: asistencia + muestra + transicion de estado + aviso
        try:
            muestra = MuestraRepo.registrar_asistencia_y_crear_muestra(
                turno=turno,
                tomada_en=fecha_toma,
            )
            estudio.estado = EstadoEstudio.LISTA_PARA_RETIRAR

            if turno.paciente and turno.paciente.usuario_id:
                nombre_centro = turno.centro.nombre if turno.centro else "el centro de extraccion"
                MuestraRepo.crear_aviso(
                    usuario_id=turno.paciente.usuario_id,
                    mensaje=(
                        f"La muestra del estudio #{estudio.id} fue tomada en {nombre_centro} "
                        "y se encuentra Lista para retirar."
                    ),
                    canal=CanalAviso.APP,
                    enviado=True,
                )

            MuestraRepo.guardar_cambios()
        except SQLAlchemyError as exc:
            MuestraRepo.deshacer_cambios()
            return None, f"Error inesperado al registrar la toma de muestra: {exc!s}", 500

        resultado = {
            "muestra_id": muestra.id,
            "estudio_id": estudio.id,
            "turno_id": turno.id,
            "centro_id": turno.centro_id,
            "centro_nombre": turno.centro.nombre if turno.centro else None,
            "tomada_en": fecha_toma.isoformat(),
            "asistio": turno.asistio,
            "estado_estudio": estudio.estado.value,
            "registrada_por_usuario_id": usuario_actual_id,
        }
        return resultado, None, 201