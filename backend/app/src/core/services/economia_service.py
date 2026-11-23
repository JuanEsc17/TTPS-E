"""Servicio de negocio para emitir el presupuesto de un estudio (Escenario 3)."""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from flask import current_app, has_app_context
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from src.clients import ClienteError, EmailClient, ObraSocialClient
from src.core.models.economia import ObraSocial, Presupuesto
from src.core.models.enums import EntidadAuditable, EstadoEstudio, TipoAccionAuditoria
from src.core.models.estudios import Estudio
from src.core.models.reglas import (
    GENES_INCLUIDOS,
    PRECIO_BASE_USD,
    PRECIO_GEN_ADICIONAL_USD,
    calcular_precio,
)
from src.core.repos.economia_repo import EconomiaRepo
from src.core.services import auditoria_service
from src.core.services.excepciones import (
    ErrorBaseDatos,
    ErrorConflicto,
    ErrorDatosInvalidos,
    ErrorDominio,
    ErrorNoEncontrado,
)
from src.core.services.formato_correo import asunto_correo, formatear_correo

logger = logging.getLogger(__name__)


def _usd(valor: Decimal) -> str:
    """Formatea un monto como string con 2 decimales, segun el contrato de la spec."""
    return f"{Decimal(valor):.2f}"


class EconomiaService:
    """Coordina la emision del presupuesto: calculo, obra social, aviso y mail."""

    # ------------------------------------------------------------------ clientes externos
    @staticmethod
    def _resolver_cliente(clave_config: str, fabrica: Callable[[], Any]) -> Any | None:
        """Usa el cliente inyectado en app.config; en tests sin cliente devuelve None."""
        if has_app_context():
            configurado = current_app.config.get(clave_config)
            if configurado is not None:
                return configurado
            if current_app.config.get("TESTING"):
                return None
        return fabrica()

    @staticmethod
    def _buscar_obra_social_externa(datos: list[dict[str, Any]], obra_social: ObraSocial) -> dict | None:
        for item in datos:
            if obra_social.rnos and str(item.get("rnos")) == obra_social.rnos:
                return item
            if str(item.get("nombre", "")).strip().lower() == obra_social.nombre.strip().lower():
                return item
        return None

    @classmethod
    def _consultar_obra_social(
        cls, obra_social: ObraSocial, estudio: Estudio
    ) -> tuple[Decimal, str | None]:
        """STEP 2: refresca cobertura y da de alta la solicitud. Si la API falla, usa la copia local."""
        cliente = cls._resolver_cliente("OBRA_SOCIAL_CLIENT", ObraSocialClient)
        if cliente is None:
            return obra_social.porcentaje_cobertura, None

        try:
            respuesta = cliente.listar_obras_sociales(buscar=obra_social.nombre)
            externa = cls._buscar_obra_social_externa(respuesta.get("datos", []), obra_social)
            if externa is None:
                return obra_social.porcentaje_cobertura, None
            if externa.get("porcentaje_cobertura") is not None:
                obra_social.porcentaje_cobertura = Decimal(str(externa["porcentaje_cobertura"]))
            id_externo = externa.get("id")
        except (ClienteError, OSError, AttributeError, InvalidOperation) as exc:
            logger.warning(
                "[economia_service] API obras sociales no disponible, uso copia local obra_social_id=%s: %s",
                obra_social.id, exc,
            )
            return obra_social.porcentaje_cobertura, None

        if not id_externo:
            return obra_social.porcentaje_cobertura, None

        u_pac = estudio.paciente.usuario
        try:
            solicitud = cliente.crear_solicitud(
                obra_social_id=str(id_externo),
                paciente_nombre=f"{u_pac.nombre} {u_pac.apellido}",
                fecha=date.today(),
                referencia_externa=str(estudio.id),
            )
            solicitud_id = solicitud.get("id")
        except (ClienteError, OSError, AttributeError) as exc:
            logger.warning(
                "[economia_service] no se pudo crear la solicitud externa estudio_id=%s: %s",
                estudio.id, exc,
            )
            solicitud_id = None

        return obra_social.porcentaje_cobertura, (str(solicitud_id) if solicitud_id else None)

    @classmethod
    def _notificar_paciente_por_mail(
        cls, estudio: Estudio, presupuesto: Presupuesto, por_obra_social: bool
    ) -> None:
        """Envio obligatorio: si falla se aborta toda la emision (TC-08)."""
        cliente = cls._resolver_cliente("EMAIL_CLIENT", EmailClient)
        u_pac = estudio.paciente.usuario
        if cliente is None or not u_pac.email:
            return

        siguiente_paso = (
            "Su obra social debe autorizar el estudio. Le avisaremos cuando responda."
            if por_obra_social
            else "Puede abonarlo desde el portal en un solo pago o en cuotas con MercadoPago."
        )
        cuerpo = formatear_correo(
            titulo="Presupuesto disponible",
            saludo=f"Estimado/a {u_pac.nombre} {u_pac.apellido},",
            introduccion=f"Ya está disponible el presupuesto de su Estudio #{estudio.id}.",
            destacado=[
                f"Cantidad de genes: {presupuesto.cantidad_genes}",
                f"Monto total: USD {_usd(presupuesto.monto_total_usd)}",
                f"Estado del estudio: {estudio.estado.value}",
            ],
            secciones=[("Cómo continuar", [siguiente_paso])],
        )
        try:
            cliente.enviar_aviso(
                asunto=asunto_correo(f"Presupuesto disponible · Estudio #{estudio.id}"),
                mensaje=cuerpo,
                destinatarios=[u_pac.email],
                referencia=f"PRESUPUESTO-{presupuesto.id}",
                idempotency_key=f"presupuesto-{presupuesto.id}",
            )
        except (ClienteError, OSError) as exc:
            raise ErrorDominio(
                f"No se pudo enviar el correo del presupuesto al paciente: {exc!s}",
                codigo="ERROR_ENVIO_EMAIL",
                http_status=502,
                reintentable=True,
            ) from exc

    # ------------------------------------------------------------------ caso de uso
        @staticmethod
    def listar_pendientes_presupuesto(*, dni: str | None = None) -> list[dict[str, Any]]:
        """STEP 0: bandeja de estudios en Creado sin presupuesto, con desglose estimado."""
        resultado: list[dict[str, Any]] = []
        for estudio, cantidad_genes in EconomiaRepo.listar_estudios_pendientes_presupuesto(dni=dni):
            u_pac = estudio.paciente.usuario
            u_med = estudio.medico.usuario if estudio.medico else None
            obra_social = estudio.obra_social
            genes_adicionales = max(0, cantidad_genes - GENES_INCLUIDOS)
            resultado.append(
                {
                    "estudio_id": estudio.id,
                    "estado_estudio": estudio.estado.value,
                    "es_pompe_urgente": estudio.es_pompe_urgente,
                    "creado_en": estudio.created_at.isoformat() if estudio.created_at else None,
                    "paciente_nombre": f"{u_pac.nombre} {u_pac.apellido}".strip(),
                    "paciente_dni": estudio.paciente.dni,
                    "medico_nombre": f"{u_med.nombre} {u_med.apellido}".strip() if u_med else None,
                    "patologia_nombre": (
                        estudio.patologia_sospechada.nombre if estudio.patologia_sospechada else None
                    ),
                    "cantidad_genes": cantidad_genes,
                    "precio_base_usd": _usd(PRECIO_BASE_USD),
                    "genes_adicionales": genes_adicionales,
                    "costo_adicional_usd": _usd(PRECIO_GEN_ADICIONAL_USD * genes_adicionales),
                    "monto_estimado_usd": (
                        _usd(calcular_precio(cantidad_genes)) if cantidad_genes > 0 else None
                    ),
                    "obra_social": (
                        {
                            "id": obra_social.id,
                            "nombre": obra_social.nombre,
                            "porcentaje_cobertura": _usd(obra_social.porcentaje_cobertura),
                        }
                        if obra_social
                        else None
                    ),
                }
            )
        return resultado
    @classmethod
    def emitir_presupuesto(
        cls, *, estudio_id: int, usuario_actual_id: int, obra_social_id: int | None = None
    ) -> dict[str, Any]:
        # ---------- STEP 1: validaciones ----------
        estudio = EconomiaRepo.obtener_estudio_para_presupuesto(estudio_id)
        if estudio is None:
            raise ErrorNoEncontrado(f"El estudio #{estudio_id} no existe.", codigo="ESTUDIO_NO_ENCONTRADO")

        if estudio.presupuesto is not None:
            raise ErrorConflicto(
                "El estudio ya posee un presupuesto emitido", codigo="PRESUPUESTO_YA_EMITIDO"
            )

        if estudio.estado != EstadoEstudio.CREADO:
            raise ErrorConflicto(
                f"El estudio #{estudio.id} en estado '{estudio.estado.value}' no admite emitir presupuesto.",
                codigo="ESTADO_ESTUDIO_INVALIDO",
            )

        cantidad_genes = EconomiaRepo.contar_genes(estudio.id)
        if cantidad_genes == 0:
            raise ErrorDatosInvalidos(
                f"El estudio #{estudio.id} no tiene genes asociados.", codigo="ESTUDIO_SIN_GENES"
            )

        if obra_social_id is not None:
            obra_social = EconomiaRepo.obtener_obra_social(obra_social_id)
            if obra_social is None:
                raise ErrorNoEncontrado(
                    f"La obra social #{obra_social_id} no existe.", codigo="OBRA_SOCIAL_NO_ENCONTRADA"
                )
        else:
            obra_social = estudio.obra_social

        logger.info(
            "[economia_service] STEP 1 iniciado estudio_id=%s administrativo_id=%s cantidad_genes=%s",
            estudio.id, usuario_actual_id, cantidad_genes,
        )

        # ---------- STEP 2: calculo ----------
        monto_total_usd = calcular_precio(cantidad_genes)
        genes_adicionales = max(0, cantidad_genes - GENES_INCLUIDOS)
        costo_adicional_usd = PRECIO_GEN_ADICIONAL_USD * genes_adicionales

        try:
            if obra_social is not None and estudio.obra_social_id != obra_social.id:
                estudio.obra_social_id = obra_social.id

            porcentaje_cobertura: Decimal | None = None
            solicitud_externa_id: str | None = None
            if obra_social is not None:
                porcentaje_cobertura, solicitud_externa_id = cls._consultar_obra_social(obra_social, estudio)

            logger.info(
                "[economia_service] STEP 2 monto_total_usd=%s cantidad_genes=%s obra_social_id=%s",
                monto_total_usd, cantidad_genes, obra_social.id if obra_social else None,
            )

            # ---------- STEP 3: persistencia ----------
            presupuesto = EconomiaRepo.crear_presupuesto(
                estudio_id=estudio.id,
                emitido_por_id=usuario_actual_id,
                cantidad_genes=cantidad_genes,
                monto_total_usd=monto_total_usd,
            )

            if obra_social is not None:
                estado_anterior = estudio.estado
                estudio.estado = EstadoEstudio.PENDIENTE_AUTORIZACION
                auditoria_service.registrar_modificacion(
                    entidad_tipo=EntidadAuditable.ESTUDIO,
                    entidad_id=estudio.id,
                    accion=TipoAccionAuditoria.CAMBIO_ESTADO,
                    usuario_id=usuario_actual_id,
                    motivo="Emision de presupuesto con obra social",
                    cambios={
                        "estado": {
                            "anterior": estado_anterior.value,
                            "nuevo": EstadoEstudio.PENDIENTE_AUTORIZACION.value,
                        }
                    },
                )
                EconomiaRepo.crear_autorizacion(
                    estudio_id=estudio.id, solicitud_externa_id=solicitud_externa_id
                )

            EconomiaRepo.crear_aviso(
                usuario_id=estudio.paciente.usuario_id,
                mensaje=(
                    f"El presupuesto de su Estudio #{estudio.id} ya está disponible: "
                    f"USD {_usd(monto_total_usd)}."
                ),
            )

            cls._notificar_paciente_por_mail(estudio, presupuesto, por_obra_social=obra_social is not None)

            EconomiaRepo.guardar_cambios()
        except ErrorDominio:
            EconomiaRepo.deshacer_cambios()
            raise
        except IntegrityError as exc:
            EconomiaRepo.deshacer_cambios()
            raise ErrorConflicto(
                "El estudio ya posee un presupuesto emitido", codigo="PRESUPUESTO_YA_EMITIDO"
            ) from exc
        except SQLAlchemyError as exc:
            EconomiaRepo.deshacer_cambios()
            raise ErrorBaseDatos(f"Error al emitir el presupuesto: {exc!s}") from exc

        logger.info(
            "[economia_repo] STEP 3 presupuesto_id=%s estudio_id=%s monto_usd=%s estado_estudio=%s",
            presupuesto.id, estudio.id, monto_total_usd, estudio.estado.value,
        )
        return {
            "presupuesto_id": presupuesto.id,
            "estudio_id": estudio.id,
            "emitido_por_id": usuario_actual_id,
            "cantidad_genes": cantidad_genes,
            "precio_base_usd": _usd(PRECIO_BASE_USD),
            "genes_adicionales": genes_adicionales,
            "costo_adicional_usd": _usd(costo_adicional_usd),
            "monto_total_usd": _usd(monto_total_usd),
            "estado_estudio": estudio.estado.value,
            "porcentaje_cobertura_obra_social": (
                _usd(porcentaje_cobertura) if porcentaje_cobertura is not None else None
            ),
        }