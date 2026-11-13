"""Servicio de logica de negocio para turnos y centros de extraccion."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from flask import current_app, has_app_context
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from src.clients import ClienteError, EmailClient
from src.core.models.enums import CanalAviso, EstadoEstudio
from src.core.models.reglas import MAX_AUSENCIAS
from src.core.models.turnos import CentroExtraccion
from src.core.repos.turno_repo import TurnoRepo

# Constantes de agenda segun LEL (Lunes a viernes 9 a 18 cada 15 min, sin feriados)
HORA_APERTURA = time(9, 0)
HORA_ULTIMO_SLOT = time(17, 45)
DURACION_SLOT_MINUTOS = 15

# Feriados nacionales inamovibles de referencia para validacion
FERIADOS_ARGENTINA_DEFAULT: set[tuple[int, int]] = {
    (1, 1),    # Anio Nuevo
    (3, 24),   # Memoria por la Verdad y Justicia
    (4, 2),    # Veteranos y Caidos en Malvinas
    (5, 1),    # Dia del Trabajador
    (5, 25),   # Revolucion de Mayo
    (6, 20),   # Belgrano
    (7, 9),    # Dia de la Independencia
    (12, 8),   # Inmaculada Concepcion
    (12, 25),  # Navidad
}


class TurnoService:
    """Servicio que coordina la logica de negocio de turnos y centros de extraccion."""

    @staticmethod
    def listar_centros() -> list[CentroExtraccion]:
        """Retorna todos los centros de extraccion para el mapa interactivo."""
        return TurnoRepo.listar_centros()

    @staticmethod
    def es_dia_laborable(
        fecha: date,
        feriados_adicionales: set[date] | None = None,
    ) -> bool:
        """Verifica si una fecha cae en lunes a viernes y no es feriado."""
        # 1. Fin de semana (5 = Sabado, 6 = Domingo)
        if fecha.weekday() >= 5:
            return False

        # 2. Feriado fijo por mes y dia
        if (fecha.month, fecha.day) in FERIADOS_ARGENTINA_DEFAULT:
            return False

        # 3. Feriados adicionales dinamicos
        return not bool(feriados_adicionales and fecha in feriados_adicionales)

    @staticmethod
    def generar_slots_teoricos_del_dia(fecha: date) -> list[datetime]:
        """Genera los 36 slots de 15 minutos entre las 09:00 y las 17:45 para una fecha."""
        slots: list[datetime] = []
        actual = datetime.combine(fecha, HORA_APERTURA)
        limite = datetime.combine(fecha, HORA_ULTIMO_SLOT)

        while actual <= limite:
            slots.append(actual)
            actual += timedelta(minutes=DURACION_SLOT_MINUTOS)

        return slots

    @classmethod
    def obtener_disponibilidad(
        cls,
        centro_id: int,
        fecha: date,
        feriados_adicionales: set[date] | None = None,
    ) -> tuple[dict[str, Any] | None, str | None, int]:
        """Calcula los turnos disponibles en un centro para una fecha dada.

        Retorna:
            (resultado, None, 200) en caso de exito.
            (None, mensaje_error, status_code) en caso de error.
        """
        centro = TurnoRepo.obtener_centro_por_id(centro_id)
        if not centro:
            return None, f"El centro de extraccion con ID {centro_id} no existe.", 404

        # Si no es dia laborable (fin de semana o feriado), retorna lista vacia
        if not cls.es_dia_laborable(fecha, feriados_adicionales):
            return {
                "centro": centro,
                "fecha": fecha.isoformat(),
                "slots_libres": [],
            }, None, 200

        # Generamos los 36 slots del dia (de 09:00 a 17:45)
        slots_teoricos = cls.generar_slots_teoricos_del_dia(fecha)

        # Consultamos en el repositorio los turnos ya ocupados ese dia
        turnos_ocupados = TurnoRepo.listar_turnos_ocupados(centro_id, fecha)
        horarios_ocupados = {t.inicio for t in turnos_ocupados}

        # Filtramos los slots disponibles restando los ocupados
        slots_libres = [
            slot for slot in slots_teoricos if slot not in horarios_ocupados
        ]

        return {
            "centro": centro,
            "fecha": fecha.isoformat(),
            "slots_libres": [slot.isoformat() for slot in slots_libres],
        }, None, 200

    @classmethod
    def solicitar_turno(
        cls,
        estudio_id: int,
        centro_id: int,
        inicio: datetime,
        usuario_actual_id: int | None = None,
        feriados_adicionales: set[date] | None = None,
        email_client: Any | None = None,
    ) -> tuple[dict[str, Any] | None, str | None, int]:
        """Reserva un turno de extraccion de forma atomica para un paciente titular."""
        # Normalizar timezone si viene aware para operar sobre hora local naive
        if inicio.tzinfo is not None:
            inicio = inicio.replace(tzinfo=None)

        # 1. Obtener y validar existencia del Estudio con bloqueo FOR UPDATE
        estudio = TurnoRepo.obtener_estudio_por_id(estudio_id, bloquear=True)
        if not estudio:
            return None, f"El estudio con ID {estudio_id} no existe.", 404

        # 2. Obtener y validar existencia del Centro de extraccion
        centro = TurnoRepo.obtener_centro_por_id(centro_id)
        if not centro:
            return None, f"El centro de extraccion con ID {centro_id} no existe.", 404

        # 3. Validar permisos: el usuario actual debe ser el paciente titular del estudio
        if not estudio.paciente:
            return None, "No tiene permisos para solicitar turno para este estudio.", 403
        if usuario_actual_id is not None and estudio.paciente.usuario_id != usuario_actual_id:
            return None, "No tiene permisos para solicitar turno para este estudio.", 403

        # 4. Validar reglas de agenda del horario solicitado (inicio)
        # 4.1. Debe ser un horario futuro
        if inicio <= datetime.now():
            return None, "El horario del turno debe ser posterior a la fecha y hora actual.", 422

        # 4.2. Debe ser un dia laborable (lunes a viernes no feriado)
        if not cls.es_dia_laborable(inicio.date(), feriados_adicionales):
            return None, "Los turnos solo pueden reservarse de lunes a viernes en dias no feriados.", 422

        # 4.3. Franja horaria de 09:00 a 17:45 inclusive (turnos de 15 min finalizan a las 18:00)
        if not (HORA_APERTURA <= inicio.time() <= HORA_ULTIMO_SLOT):
            return None, "El horario debe encontrarse entre las 09:00 y las 17:45.", 422

        # 4.4. Debe ser multiplo exacto de 15 minutos (00, 15, 30, 45) y segundos 0
        if inicio.minute not in (0, 15, 30, 45) or inicio.second != 0 or inicio.microsecond != 0:
            return None, "Los turnos deben ser intervalos exactos de 15 minutos (00, 15, 30, 45).", 422

        # 5. Validar habilitacion del Estudio para sacar turno
        habilitado = False
        if estudio.estado == EstadoEstudio.AUTORIZADO:
            habilitado = True
        elif estudio.estado == EstadoEstudio.CREADO and estudio.presupuesto:
            habilitado = any(not p.anulado for p in estudio.presupuesto.pagos)
        elif (
            estudio.estado == EstadoEstudio.REMUESTREO_REQUERIDO
            or (estudio.estado == EstadoEstudio.TURNO_SACADO and estudio.ausencias < MAX_AUSENCIAS)
        ):
            habilitado = True

        if not habilitado:
            return (
                None,
                "El estudio no se encuentra habilitado para sacar turno o no cuenta con pago/autorizacion vigente.",
                409,
            )

        # 6. Validar que el estudio no posea ya un turno activo reservado
        turno_activo = TurnoRepo.buscar_turno_activo_por_estudio(estudio.id)
        if turno_activo:
            return None, "El estudio ya posee un turno activo reservado.", 409

        # 7. Reserva atomica, cambio de estado y generacion de avisos
        try:
            turno = TurnoRepo.crear_turno(
                centro_id=centro.id,
                paciente_id=estudio.paciente_id,
                estudio_id=estudio.id,
                inicio=inicio,
            )
            estudio.estado = EstadoEstudio.TURNO_SACADO

            # Generar aviso pendiente de envio
            mensaje_aviso = (
                f"Turno reservado para el {inicio.strftime('%d/%m/%Y %H:%M')} en {centro.nombre}. "
                f"Recuerde que al acumular {MAX_AUSENCIAS} ausencias perdera el pago del estudio."
            )
            aviso = TurnoRepo.crear_aviso(
                usuario_id=estudio.paciente.usuario_id,
                mensaje=mensaje_aviso,
                canal=CanalAviso.MAIL,
                enviado=False,
            )

            # Despacho de correo y documentacion mediante EmailClient
            cliente_email = email_client
            if cliente_email is None and has_app_context():
                cliente_email = current_app.config.get("EMAIL_CLIENT")
            if cliente_email is None:
                if has_app_context() and current_app.config.get("TESTING"):
                    cliente_email = None
                else:
                    cliente_email = EmailClient()

            if cliente_email is not None:
                try:
                    email_destino = (
                        estudio.paciente.usuario.email
                        if (estudio.paciente and estudio.paciente.usuario)
                        else ""
                    )
                    cuerpo_email = (
                        f"Estimado/a {estudio.paciente.usuario.nombre} {estudio.paciente.usuario.apellido}:\n\n"
                        f"Su turno de extraccion de sangre para el Estudio #{estudio.id} ha sido reservado con exito.\n\n"
                        f"Detalle del turno:\n"
                        f"- Centro de extraccion: {centro.nombre}\n"
                        f"- Direccion: {centro.direccion}, {centro.provincia}\n"
                        f"- Fecha y hora: {inicio.strftime('%d/%m/%Y a las %H:%M hs')}\n"
                        f"- Duracion: {DURACION_SLOT_MINUTOS} minutos\n\n"
                        f"Indicaciones importantes:\n"
                        f"1. No requiere ayuno ni preparacion especial.\n"
                        f"2. Recuerde llevar impresa y firmada la plantilla de Consentimiento informado y la Orden de extraccion.\n"
                        f"3. Limite de inasistencias: El sistema permite hasta {MAX_AUSENCIAS} ausencias maximas. Al acumular {MAX_AUSENCIAS} ausencias perdera el pago del estudio.\n"
                    )
                    cliente_email.enviar_aviso(
                        asunto=f"Confirmacion de turno de extraccion - Estudio #{estudio.id}",
                        mensaje=cuerpo_email,
                        destinatarios=[email_destino],
                        referencia=f"TURNO-{turno.id}",
                    )
                except (ClienteError, OSError) as exc:
                    TurnoRepo.deshacer_cambios()
                    return (
                        None,
                        f"No se pudo despachar la documentacion por correo electronico: {exc!s}. Intente nuevamente.",
                        502,
                    )

            TurnoRepo.marcar_aviso_enviado(aviso)
            TurnoRepo.guardar_cambios()
        except IntegrityError:
            TurnoRepo.deshacer_cambios()
            return (
                None,
                "El turno seleccionado acaba de ser ocupado por otro paciente. Por favor elija otro horario.",
                409,
            )
        except SQLAlchemyError as exc:
            TurnoRepo.deshacer_cambios()
            return None, f"Error inesperado al registrar el turno: {exc!s}", 500

        resultado = {
            "turno_id": turno.id,
            "estudio_id": estudio.id,
            "paciente_id": estudio.paciente_id,
            "centro_id": centro.id,
            "inicio": inicio.isoformat(),
            "duracion_minutos": DURACION_SLOT_MINUTOS,
            "activo": turno.activo,
            "estado_estudio": estudio.estado.value,
            "ausencias_acumuladas": estudio.ausencias,
            "max_ausencias": MAX_AUSENCIAS,
            "documentacion_enviada": {
                "orden_extraccion": True,
                "consentimiento_informado": True,
                "recordatorio": True,
            },
        }
        return resultado, None, 201
