"""Servicio de logica de negocio para toma de muestras y remuestreo (Escenarios 9 y 10)."""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from flask import current_app, has_app_context
from sqlalchemy.exc import SQLAlchemyError
from src.clients import ClienteError, EmailClient
from src.core.models.enums import (
    CanalAviso,
    EntidadAuditable,
    EstadoEstudio,
    MotivoDescarte,
    TipoAccionAuditoria,
)
from src.core.models.estudios import Estudio
from src.core.models.turnos import Turno
from src.core.repos.muestra_repo import MuestraRepo
from src.core.services import auditoria_service
from src.core.services.excepciones import (
    ErrorBaseDatos,
    ErrorConflicto,
    ErrorDominio,
    ErrorNoEncontrado,
)
from src.core.services.formato_correo import asunto_correo, formatear_correo

logger = logging.getLogger(__name__)

ESTADOS_APTOS_REMUESTREO: tuple[EstadoEstudio, ...] = (EstadoEstudio.EN_VIAJE_COREA,)

_ETIQUETA_MOTIVO_DESCARTE: dict[MotivoDescarte, str] = {
    MotivoDescarte.ADN_INSUFICIENTE: "ADN insuficiente",
    MotivoDescarte.DESNATURALIZADA: "Muestra desnaturalizada",
}


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

    @staticmethod
    def _resolver_email_client(email_client: Any | None = None) -> Any | None:
        if email_client is not None:
            return email_client
        if has_app_context():
            configurado = current_app.config.get("EMAIL_CLIENT")
            if configurado is not None:
                return configurado
            if current_app.config.get("TESTING"):
                return None
        return EmailClient()

    @staticmethod
    def _serializar_estudio_remuestreable(estudio: Estudio) -> dict[str, Any]:
        u_pac = estudio.paciente.usuario if estudio.paciente else None
        u_med = estudio.medico.usuario if estudio.medico else None
        muestra = estudio.muestra_vigente
        return {
            "estudio_id": estudio.id,
            "estado_estudio": estudio.estado.value,
            "es_pompe_urgente": estudio.es_pompe_urgente,
            "patologia_nombre": (
                estudio.patologia_sospechada.nombre if estudio.patologia_sospechada else None
            ),
            "paciente_id": estudio.paciente_id,
            "paciente_dni": estudio.paciente.dni if estudio.paciente else None,
            "paciente_nombre": f"{u_pac.nombre} {u_pac.apellido}".strip() if u_pac else None,
            "medico_nombre": f"{u_med.nombre} {u_med.apellido}".strip() if u_med else None,
            "muestra_vigente": (
                {
                    "muestra_id": muestra.id,
                    "turno_id": muestra.turno_id,
                    "sample_set_id": muestra.sample_set_id,
                    "tomada_en": muestra.tomada_en.isoformat() if muestra.tomada_en else None,
                    "llegada_lab_central": (
                        muestra.llegada_lab_central.isoformat()
                        if muestra.llegada_lab_central
                        else None
                    ),
                }
                if muestra
                else None
            ),
        }

    @classmethod
    def listar_estudios_remuestreables(
        cls,
        *,
        dni: str | None = None,
        estudio_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Lista los estudios en viaje a Corea elegibles para declarar remuestreo (Escenario 10)."""
        estudios = MuestraRepo.listar_estudios_remuestreables(
            estados_permitidos=ESTADOS_APTOS_REMUESTREO,
            dni=dni,
            estudio_id=estudio_id,
        )
        return [cls._serializar_estudio_remuestreable(e) for e in estudios]

    @classmethod
    def solicitar_remuestreo(
        cls,
        *,
        estudio_id: int,
        usuario_actual_id: int,
        motivo_descarte: MotivoDescarte,
        observaciones_calidad: str | None,
        motivo: str,
        ip_origen: str | None = None,
        email_client: Any | None = None,
    ) -> dict[str, Any]:
        """Descarta la muestra vigente y retrocede el estudio a Remuestreo requerido."""
        estudio = MuestraRepo.obtener_estudio_para_remuestreo(estudio_id, bloquear=True)
        if estudio is None:
            raise ErrorNoEncontrado(
                f"El estudio #{estudio_id} no existe.",
                codigo="ESTUDIO_NO_ENCONTRADO",
            )

        if estudio.estado not in ESTADOS_APTOS_REMUESTREO:
            raise ErrorConflicto(
                f"El estudio #{estudio.id} en estado '{estudio.estado.value}' no admite remuestreo.",
                codigo="ESTADO_ESTUDIO_INVALIDO_PARA_REMUESTREO",
            )

        muestra_vigente = estudio.muestra_vigente
        if muestra_vigente is None:
            raise ErrorConflicto(
                f"El estudio #{estudio.id} no posee una muestra vigente para descartar.",
                codigo="SIN_MUESTRA_VIGENTE",
            )

        estado_anterior = estudio.estado
        sample_set_id = muestra_vigente.sample_set_id
        u_pac = estudio.paciente.usuario if estudio.paciente else None
        u_med = estudio.medico.usuario if estudio.medico else None
        paciente_nombre = (
            f"{u_pac.nombre} {u_pac.apellido}".strip() if u_pac else f"Paciente #{estudio.paciente_id}"
        )
        etiqueta_motivo = _ETIQUETA_MOTIVO_DESCARTE.get(motivo_descarte, motivo_descarte.value)

        try:
            # 1. Descartar unicamente la muestra vigente preservando sample_set_id historico
            muestra_vigente.motivo_descarte = motivo_descarte
            muestra_vigente.observaciones_calidad = observaciones_calidad

            # 2. Retroceder el estudio sin alterar pagos, cuotas ni contador de ausencias
            estudio.estado = EstadoEstudio.REMUESTREO_REQUERIDO

            # 3. Registrar modificacion en tabla append-only registro_modificaciones (ADR-003)
            auditoria_service.registrar_modificacion(
                entidad_tipo=EntidadAuditable.ESTUDIO,
                entidad_id=estudio.id,
                accion=TipoAccionAuditoria.CAMBIO_ESTADO,
                usuario_id=usuario_actual_id,
                origen="usuario",
                motivo=motivo,
                ip_origen=ip_origen,
                cambios={
                    "estado": {
                        "anterior": estado_anterior.value,
                        "nuevo": EstadoEstudio.REMUESTREO_REQUERIDO.value,
                    },
                    "muestra_descartada_id": {
                        "anterior": None,
                        "nuevo": muestra_vigente.id,
                    },
                    "motivo_descarte": {
                        "anterior": None,
                        "nuevo": motivo_descarte.value,
                    },
                },
            )

            # 4. Generar avisos internos para Paciente y Medico
            aviso_paciente_id: int | None = None
            if u_pac is not None:
                aviso_pac = MuestraRepo.crear_aviso(
                    usuario_id=u_pac.id,
                    mensaje=(
                        f"Su muestra enviada para análisis no alcanzó la calidad técnica requerida "
                        f"({motivo_descarte.value}). El estudio #{estudio.id} volvió a "
                        "Remuestreo requerido. Por favor solicite un nuevo turno de extracción "
                        "sin costo adicional."
                    ),
                    canal=CanalAviso.APP,
                    enviado=True,
                )
                aviso_paciente_id = aviso_pac.id

            aviso_medico_id: int | None = None
            if u_med is not None:
                aviso_med = MuestraRepo.crear_aviso(
                    usuario_id=u_med.id,
                    mensaje=(
                        f"La muestra del paciente {paciente_nombre} (Estudio #{estudio.id}) "
                        f"presentó {motivo_descarte.value} y fue retrocedida a "
                        "Remuestreo requerido."
                    ),
                    canal=CanalAviso.APP,
                    enviado=True,
                )
                aviso_medico_id = aviso_med.id

            # 5. Notificar por mail si EmailClient esta habilitado
            cliente_email = cls._resolver_email_client(email_client)
            if cliente_email is not None:
                try:
                    if u_pac is not None and u_pac.email:
                        cuerpo_pac = formatear_correo(
                            titulo="Remuestreo requerido sin cargo adicional",
                            saludo=f"Estimado/a {paciente_nombre},",
                            introduccion=(
                                f"La muestra de sangre correspondiente a su Estudio #{estudio.id} "
                                "requiere una nueva extracción debido a un inconveniente técnico de calidad."
                            ),
                            destacado=[
                                f"Estado del estudio: {EstadoEstudio.REMUESTREO_REQUERIDO.value}",
                                f"Motivo técnico: {etiqueta_motivo}",
                            ],
                            secciones=[
                                (
                                    "Cómo continuar",
                                    [
                                        "Su estudio conserva el pago/autorización vigente: no debe abonar ningún cargo adicional.",
                                        "Ingrese al portal para solicitar un nuevo turno de extracción.",
                                    ],
                                )
                            ],
                            cierre=f"Observación administrativa: {observaciones_calidad or motivo}",
                        )
                        cliente_email.enviar_aviso(
                            asunto=asunto_correo(f"Remuestreo requerido · Estudio #{estudio.id}"),
                            mensaje=cuerpo_pac,
                            destinatarios=[u_pac.email],
                            referencia=f"REMUESTREO-{estudio.id}-PAC",
                            idempotency_key=f"remuestreo-{estudio.id}-m{muestra_vigente.id}-pac",
                        )

                    if u_med is not None and u_med.email:
                        cuerpo_med = formatear_correo(
                            titulo="Aviso clínico de remuestreo",
                            saludo=f"Estimado/a Dr./Dra. {u_med.nombre} {u_med.apellido},",
                            introduccion=(
                                f"Le informamos que la muestra del paciente {paciente_nombre} "
                                f"(Estudio #{estudio.id}) requirió remuestreo y volvió a "
                                f"{EstadoEstudio.REMUESTREO_REQUERIDO.value}."
                            ),
                            destacado=[
                                f"Motivo técnico: {etiqueta_motivo}",
                                f"Muestra descartada: #{muestra_vigente.id}",
                            ],
                            secciones=[
                                (
                                    "Detalle administrativo",
                                    [
                                        motivo,
                                        observaciones_calidad or "Sin observaciones técnicas adicionales.",
                                    ],
                                )
                            ],
                        )
                        cliente_email.enviar_aviso(
                            asunto=asunto_correo(
                                f"Remuestreo en paciente {paciente_nombre} · Estudio #{estudio.id}"
                            ),
                            mensaje=cuerpo_med,
                            destinatarios=[u_med.email],
                            referencia=f"REMUESTREO-{estudio.id}-MED",
                            idempotency_key=f"remuestreo-{estudio.id}-m{muestra_vigente.id}-med",
                        )
                except (ClienteError, OSError) as exc:
                    MuestraRepo.deshacer_cambios()
                    raise ErrorDominio(
                        f"No se pudo notificar el remuestreo por correo electronico: {exc!s}",
                        codigo="ERROR_ENVIO_NOTIFICACION",
                        http_status=502,
                        reintentable=True,
                    ) from exc

            MuestraRepo.guardar_cambios()
        except ErrorDominio:
            raise
        except SQLAlchemyError as exc:
            MuestraRepo.deshacer_cambios()
            raise ErrorBaseDatos(
                f"Error inesperado al registrar el remuestreo: {exc!s}"
            ) from exc

        logger.info(
            "[muestra_service] rollback_remuestreo estudio_id=%s de=%s a=%s muestra_id=%s",
            estudio.id,
            estado_anterior.value,
            estudio.estado.value,
            muestra_vigente.id,
        )
        return {
            "estudio_id": estudio.id,
            "estado_anterior": estado_anterior.value,
            "estado_nuevo": estudio.estado.value,
            "muestra_descartada_id": muestra_vigente.id,
            "motivo_descarte": motivo_descarte.value,
            "observaciones_calidad": observaciones_calidad,
            "sample_set_id": sample_set_id,
            "aviso_paciente_id": aviso_paciente_id,
            "aviso_medico_id": aviso_medico_id,
        }