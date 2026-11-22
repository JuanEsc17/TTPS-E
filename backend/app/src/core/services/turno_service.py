"""Servicio de logica de negocio para turnos y centros de extraccion."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from flask import current_app, has_app_context
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from src.clients import ClienteError, EmailClient
from src.core.models.enums import CanalAviso, EstadoEstudio, ResultadoAutorizacion
from src.core.models.estudios import Estudio
from src.core.models.reglas import MAX_AUSENCIAS
from src.core.models.turnos import CentroExtraccion
from src.core.repos.turno_repo import TurnoRepo
from src.core.services.formato_correo import asunto_correo, formatear_correo

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
    def _resolver_email_client(email_client: Any | None = None) -> Any | None:
        """Obtiene el cliente de email inyectado, configurado en app o por defecto."""
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
    def listar_centros() -> list[CentroExtraccion]:
        """Retorna todos los centros de extraccion para el mapa interactivo."""
        return TurnoRepo.listar_centros()

    @staticmethod
    def _esta_habilitado_para_turno(estudio: Estudio) -> bool:
        """Evalua si un estudio cumple las condiciones economicas/clinicas para sacar turno."""
        if estudio.estado == EstadoEstudio.AUTORIZADO:
            return True
        if estudio.estado == EstadoEstudio.CREADO and estudio.presupuesto:
            return any(not p.anulado for p in estudio.presupuesto.pagos)
        return (
            estudio.estado == EstadoEstudio.REMUESTREO_REQUERIDO
            or (estudio.estado == EstadoEstudio.TURNO_SACADO and estudio.ausencias < MAX_AUSENCIAS)
        )

    @classmethod
    def estudio_admite_nuevo_turno(cls, estudio: Estudio) -> bool:
        """Indica si el estudio esta habilitado y no posee un turno activo pendiente."""
        turno_activo = next(
            (t for t in estudio.turnos if t.activo and t.asistio is None),
            None,
        )
        return cls._esta_habilitado_para_turno(estudio) and turno_activo is None

    @staticmethod
    def _serializar_centro_dict(centro: CentroExtraccion | None) -> dict[str, Any] | None:
        """Convierte un CentroExtraccion a diccionario plano."""
        if not centro:
            return None
        return {
            "id": centro.id,
            "nombre": centro.nombre,
            "direccion": centro.direccion,
            "provincia": centro.provincia,
            "latitud": centro.latitud,
            "longitud": centro.longitud,
        }

    @classmethod
    def listar_estudios_paciente(cls, usuario_actual_id: int) -> list[dict[str, Any]]:
        """Lista los estudios del paciente titular con su habilitacion y turno activo."""
        estudios = TurnoRepo.listar_estudios_de_usuario(usuario_actual_id)
        resultado: list[dict[str, Any]] = []
        for e in estudios:
            turno_activo = next(
                (t for t in e.turnos if t.activo and t.asistio is None),
                None,
            )
            habilitado = cls._esta_habilitado_para_turno(e) and turno_activo is None
            resultado.append(
                {
                    "estudio_id": e.id,
                    "estado": e.estado.value,
                    "patologia": e.patologia_sospechada.nombre if e.patologia_sospechada else None,
                    "ausencias": e.ausencias,
                    "max_ausencias": MAX_AUSENCIAS,
                    "habilitado_para_turno": habilitado,
                    "turno_activo": (
                        {
                            "turno_id": turno_activo.id,
                            "estudio_id": e.id,
                            "centro_id": turno_activo.centro_id,
                            "inicio": turno_activo.inicio.isoformat(),
                            "duracion_minutos": DURACION_SLOT_MINUTOS,
                            "ausencias_acumuladas": e.ausencias,
                            "max_ausencias": MAX_AUSENCIAS,
                            "centro": cls._serializar_centro_dict(turno_activo.centro),
                        }
                        if turno_activo
                        else None
                    ),
                }
            )
        return resultado

    @classmethod
    def listar_turnos_paciente(cls, usuario_actual_id: int) -> list[dict[str, Any]]:
        """Lista todos los turnos (activos e historicos) del paciente con sus detalles."""
        turnos = TurnoRepo.listar_turnos_de_usuario(usuario_actual_id)
        resultado: list[dict[str, Any]] = []
        for t in turnos:
            estudio = t.estudio
            muestra_turno = (
                next((m for m in estudio.muestras if m.turno_id == t.id), None)
                if estudio
                else None
            )

            if t.asistio is True or muestra_turno is not None:
                estado_turno = "Asistido"
            elif not t.activo and t.asistio is False:
                estado_turno = "Ausente"
            elif not t.activo:
                estado_turno = "Cancelado"
            else:
                estado_turno = "Confirmado"

            puede_cancelar = bool(
                t.activo
                and t.asistio is None
                and estudio is not None
                and estudio.estado == EstadoEstudio.TURNO_SACADO
                and muestra_turno is None
            )

            resultado.append(
                {
                    "turno_id": t.id,
                    "estudio_id": t.estudio_id,
                    "estado_estudio": estudio.estado.value if estudio else None,
                    "patologia": (
                        estudio.patologia_sospechada.nombre
                        if (estudio and estudio.patologia_sospechada)
                        else None
                    ),
                    "ausencias_estudio": estudio.ausencias if estudio else 0,
                    "max_ausencias": MAX_AUSENCIAS,
                    "inicio": t.inicio.isoformat(),
                    "duracion_minutos": DURACION_SLOT_MINUTOS,
                    "activo": t.activo,
                    "asistio": t.asistio,
                    "estado_turno": estado_turno,
                    "puede_cancelar": puede_cancelar,
                    "muestra_tomada_en": (
                        muestra_turno.tomada_en.isoformat()
                        if (muestra_turno and muestra_turno.tomada_en)
                        else None
                    ),
                    "centro": cls._serializar_centro_dict(t.centro),
                }
            )
        return resultado

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
        ahora: datetime | None = None,
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

        fecha_actual = ahora or datetime.now()
        if fecha_actual.tzinfo is not None:
            fecha_actual = fecha_actual.replace(tzinfo=None)

        # Generamos los 36 slots del dia (de 09:00 a 17:45)
        slots_teoricos = cls.generar_slots_teoricos_del_dia(fecha)

        # Consultamos en el repositorio los turnos ya ocupados ese dia
        turnos_ocupados = TurnoRepo.listar_turnos_ocupados(centro_id, fecha)
        horarios_ocupados = {t.inicio for t in turnos_ocupados}

        # Filtramos los slots disponibles restando los ocupados y horarios ya pasados
        slots_libres = [
            slot
            for slot in slots_teoricos
            if slot not in horarios_ocupados and slot > fecha_actual
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
        habilitado = cls._esta_habilitado_para_turno(estudio)

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
            cliente_email = cls._resolver_email_client(email_client)

            if cliente_email is not None:
                try:
                    email_destino = (
                        estudio.paciente.usuario.email
                        if (estudio.paciente and estudio.paciente.usuario)
                        else ""
                    )
                    cuerpo_email = formatear_correo(
                        titulo="Confirmación de turno de extracción",
                        saludo=(
                            f"Estimado/a {estudio.paciente.usuario.nombre} "
                            f"{estudio.paciente.usuario.apellido},"
                        ),
                        introduccion=(
                            f"Su turno de extracción de sangre para el Estudio #{estudio.id} "
                            "ha sido reservado con éxito."
                        ),
                        destacado=[
                            f"Fecha y hora: {inicio.strftime('%d/%m/%Y · %H:%M hs')}",
                            f"Centro: {centro.nombre}",
                        ],
                        secciones=[
                            (
                                "Detalle del turno",
                                [
                                    f"Estudio: #{estudio.id}",
                                    f"Centro de extracción: {centro.nombre}",
                                    f"Dirección: {centro.direccion}, {centro.provincia}",
                                    f"Duración estimada: {DURACION_SLOT_MINUTOS} minutos",
                                ],
                            ),
                            (
                                "Indicaciones importantes",
                                [
                                    "No requiere ayuno ni preparación especial.",
                                    "Recuerde llevar impresa y firmada la Orden de extraccion y la plantilla de Consentimiento informado.",
                                    f"Límite de inasistencias: se permiten hasta {MAX_AUSENCIAS} ausencias máximas. Al acumular {MAX_AUSENCIAS} ausencias perderá el pago del estudio.",
                                ],
                            ),
                        ],
                        cierre="Si no puede asistir, puede cancelar y reprogramar el turno desde el portal.",
                    )
                    cliente_email.enviar_aviso(
                        asunto=asunto_correo(f"Confirmación de turno de extracción · Estudio #{estudio.id}"),
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

    @staticmethod
    def _determinar_estado_retorno_estudio(estudio: Estudio) -> EstadoEstudio:
        """Calcula el estado al que vuelve el estudio tras cancelar un turno activo."""
        if any(m.motivo_descarte is not None for m in estudio.muestras) and estudio.muestra_vigente is None:
            return EstadoEstudio.REMUESTREO_REQUERIDO
        if any(a.resultado == ResultadoAutorizacion.AUTORIZADA for a in estudio.autorizaciones):
            return EstadoEstudio.AUTORIZADO
        return EstadoEstudio.CREADO

    @classmethod
    def cancelar_turno(
        cls,
        turno_id: int,
        usuario_actual_id: int,
    ) -> tuple[dict[str, Any] | None, str | None, int]:
        """Cancela un turno activo por solicitud exclusiva del paciente titular."""
        turno = TurnoRepo.obtener_turno_por_id(turno_id, bloquear=True)
        if not turno:
            return None, f"El turno con ID {turno_id} no existe.", 404

        if not turno.paciente or turno.paciente.usuario_id != usuario_actual_id:
            return (
                None,
                "Solo el paciente titular puede cancelar su turno de extraccion.",
                403,
            )

        estudio = turno.estudio
        if (
            not turno.activo
            or turno.asistio is not None
            or estudio.estado != EstadoEstudio.TURNO_SACADO
            or TurnoRepo.existe_muestra_por_turno(turno.id)
        ):
            return (
                None,
                "El turno ya fue cancelado o ya fue procesado y no puede cancelarse.",
                409,
            )

        try:
            TurnoRepo.cancelar_turno(turno)
            estudio.estado = cls._determinar_estado_retorno_estudio(estudio)
            TurnoRepo.crear_aviso(
                usuario_id=turno.paciente.usuario_id,
                mensaje=(
                    f"Su turno del {turno.inicio.strftime('%d/%m/%Y %H:%M')} fue cancelado. "
                    "Ya puede solicitar un nuevo turno de extraccion."
                ),
                canal=CanalAviso.APP,
                enviado=True,
            )
            TurnoRepo.guardar_cambios()
        except SQLAlchemyError as exc:
            TurnoRepo.deshacer_cambios()
            return None, f"Error inesperado al cancelar el turno: {exc!s}", 500

        resultado = {
            "turno_id": turno.id,
            "estudio_id": estudio.id,
            "centro_id": turno.centro_id,
            "inicio": turno.inicio.isoformat(),
            "activo": turno.activo,
            "estado_estudio": estudio.estado.value,
            "ausencias": estudio.ausencias,
            "puede_sacar_nuevo_turno": True,
        }
        return resultado, None, 200
