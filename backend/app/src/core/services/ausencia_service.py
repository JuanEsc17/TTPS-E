"""Servicio de logica de negocio para el procesamiento automatico de ausencias (Escenario 33)."""
from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from src.clients import ClienteError
from src.core.models.enums import EstadoEstudio
from src.core.models.estudios import Estudio
from src.core.models.reglas import MAX_AUSENCIAS
from src.core.repos.turno_repo import TurnoRepo
from src.core.services.turno_service import TurnoService

# Los centros atienden hasta las 18:00 hs; al cierre del dia se procesan las ausencias
HORA_CIERRE_JORNADA = time(18, 0)


class AusenciaService:
    """Coordina la deteccion y el registro automatico de inasistencias al finalizar el dia."""

    @staticmethod
    def _normalizar_fecha(fecha: datetime | None = None) -> datetime:
        """Retorna un datetime naive (sin tzinfo) para comparaciones consistentes."""
        valor = fecha or datetime.now()
        return valor.replace(tzinfo=None) if valor.tzinfo is not None else valor

    @staticmethod
    def _fecha_limite_fin_jornada(fecha_actual: datetime) -> datetime:
        """Calcula el limite exclusivo (<) de turnos cuya jornada ya finalizo."""
        if fecha_actual.time() >= HORA_CIERRE_JORNADA:
            return datetime.combine(fecha_actual.date() + timedelta(days=1), time(0, 0))
        return datetime.combine(fecha_actual.date(), time(0, 0))

    @staticmethod
    def _construir_email_ausencia(
        estudio: Estudio,
        inicio_turno: datetime,
        alcanzo_limite: bool,
    ) -> tuple[str, str]:
        """Construye el asunto y cuerpo en texto plano del mail de inasistencia."""
        fecha_str = inicio_turno.strftime("%d/%m/%Y a las %H:%M hs")
        if alcanzo_limite:
            asunto = f"Perdida de pago por {MAX_AUSENCIAS} ausencias - Estudio #{estudio.id}"
            cuerpo = (
                f"Se registro una nueva inasistencia a su turno del {fecha_str} "
                f"para el Estudio #{estudio.id}.\n\n"
                f"Al haber alcanzado el limite maximo de {MAX_AUSENCIAS} ausencias, "
                f"el pago anterior fue anulado y su estudio volvio al estado Creado.\n"
                f"Para volver a solicitar un turno de extraccion debera abonar nuevamente el presupuesto."
            )
            return asunto, cuerpo

        restantes = MAX_AUSENCIAS - estudio.ausencias
        asunto = (
            f"Inasistencia a turno de extraccion ({estudio.ausencias}/{MAX_AUSENCIAS}) "
            f"- Estudio #{estudio.id}"
        )
        cuerpo = (
            f"Se registro su inasistencia al turno del {fecha_str} para el Estudio #{estudio.id}.\n\n"
            f"Ausencias acumuladas: {estudio.ausencias} de {MAX_AUSENCIAS}.\n"
            f"Puede solicitar un nuevo turno sin cargo adicional. "
            f"Recuerde que le quedan {restantes} oportunidad(es) antes de perder el pago."
        )
        return asunto, cuerpo

    @classmethod
    def registrar_ausencia(
        cls,
        turno_id: int,
        ahora: datetime | None = None,
        email_client: Any | None = None,
    ) -> tuple[dict[str, Any] | None, str | None, int]:
        """Registra la ausencia a un turno vencido y aplica la regla de MAX_AUSENCIAS."""
        fecha_actual = cls._normalizar_fecha(ahora)

        turno = TurnoRepo.obtener_turno_por_id(turno_id, bloquear=True)
        if not turno:
            return None, f"El turno con ID {turno_id} no existe.", 404

        estudio = turno.estudio
        if (
            not turno.activo
            or turno.asistio is not None
            or estudio.estado != EstadoEstudio.TURNO_SACADO
            or TurnoRepo.existe_muestra_por_turno(turno.id)
        ):
            return (
                None,
                "El turno ya fue procesado, cancelado o ya cuenta con una muestra registrada.",
                409,
            )

        if estudio.ausencias >= MAX_AUSENCIAS:
            return (
                None,
                "El estudio ya alcanzo el limite maximo de ausencias permitidas.",
                409,
            )

        inicio_turno = cls._normalizar_fecha(turno.inicio)
        cierre_jornada_turno = datetime.combine(inicio_turno.date(), HORA_CIERRE_JORNADA)
        if fecha_actual < cierre_jornada_turno:
            return (
                None,
                "La jornada del turno aun no finalizo; las ausencias se verifican al finalizar el dia.",
                422,
            )

        try:
            TurnoRepo.registrar_ausencia_turno(turno)
            estudio.ausencias += 1

            alcanzo_limite = estudio.ausencias >= MAX_AUSENCIAS
            pago_anulado_id: int | None = None
            if alcanzo_limite:
                pago_anulado_id = TurnoRepo.anular_pago_activo(estudio)
                estudio.estado = EstadoEstudio.CREADO
            pago_perdido = pago_anulado_id is not None

            cliente_email = TurnoService._resolver_email_client(email_client)
            email_destino = (
                turno.paciente.usuario.email
                if (turno.paciente and turno.paciente.usuario)
                else ""
            )
            if cliente_email is not None and email_destino:
                asunto, cuerpo = cls._construir_email_ausencia(estudio, inicio_turno, alcanzo_limite)
                try:
                    cliente_email.enviar_aviso(
                        asunto=asunto,
                        mensaje=cuerpo,
                        destinatarios=[email_destino],
                        referencia=f"TURNO-{turno.id}-AUSENCIA",
                        idempotency_key=f"ausencia-turno-{turno.id}",
                    )
                except (ClienteError, OSError) as exc:
                    TurnoRepo.deshacer_cambios()
                    return (
                        None,
                        f"No se pudo enviar la notificacion por correo electronico: {exc!s}. Intente nuevamente.",
                        502,
                    )

            TurnoRepo.guardar_cambios()
        except SQLAlchemyError as exc:
            TurnoRepo.deshacer_cambios()
            return None, f"Error inesperado al registrar la ausencia: {exc!s}", 500

        resultado = {
            "turno_id": turno.id,
            "estudio_id": estudio.id,
            "asistio": turno.asistio,
            "ausencias_acumuladas": estudio.ausencias,
            "max_ausencias": MAX_AUSENCIAS,
            "pago_perdido": pago_perdido,
            "pago_anulado_id": pago_anulado_id,
            "estado_estudio": estudio.estado.value,
            "puede_sacar_nuevo_turno": not alcanzo_limite,
            "requiere_nuevo_pago": alcanzo_limite,
        }
        return resultado, None, 200

    @classmethod
    def procesar_turnos_vencidos(
        cls,
        ahora: datetime | None = None,
        email_client: Any | None = None,
    ) -> dict[str, Any]:
        """Procesa en lote al cierre de jornada todos los turnos sin muestra registrada."""
        fecha_actual = cls._normalizar_fecha(ahora)
        fecha_limite_exclusiva = cls._fecha_limite_fin_jornada(fecha_actual)
        turno_ids = TurnoRepo.listar_ids_turnos_vencidos_sin_procesar(fecha_limite_exclusiva)

        procesados: list[dict[str, Any]] = []
        errores: list[dict[str, Any]] = []
        for turno_id in turno_ids:
            resultado, error, status = cls.registrar_ausencia(
                turno_id=turno_id,
                ahora=fecha_actual,
                email_client=email_client,
            )
            if error:
                errores.append({"turno_id": turno_id, "status": status, "error": error})
            elif resultado is not None:
                procesados.append(resultado)

        return {
            "total_detectados": len(turno_ids),
            "total_procesados": len(procesados),
            "procesados": procesados,
            "errores": errores,
        }
