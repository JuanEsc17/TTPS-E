"""Servicio de logica de negocio para Logistica Terrestre (Escenario 11)."""
from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from flask import current_app
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from src.clients import OptimizacionClient
from src.clients.exceptions import ClienteError
from src.core.models import CentroExtraccion, EstadoEstudio, OrdenDelDia
from src.core.repos.logistica_repo import LogisticaRepo

LAB_CENTRAL_COORDS = {"lat": -34.921577136619085, "lon": -57.93843617249286}


class LogisticaService:
    """Casos de uso del transportista y ordenes del dia."""

    @staticmethod
    def _resolver_optimizacion_client(client: Any | None = None) -> OptimizacionClient:
        if client is not None:
            return client
        try:
            configurado = current_app.config.get("OPTIMIZACION_CLIENT")
            if configurado is not None:
                return configurado
        except RuntimeError:
            pass
        return OptimizacionClient()

    @staticmethod
    def _ordenar_centros_local(
        centros: list[CentroExtraccion],
        origen: dict[str, float] | None = None,
    ) -> list[CentroExtraccion]:
        """Fallback deterministico por vecino mas cercano desde la ubicacion de origen."""
        actual = origen or LAB_CENTRAL_COORDS
        lat_actual, lon_actual = actual["lat"], actual["lon"]
        pendientes = list(centros)
        ordenados: list[CentroExtraccion] = []
        while pendientes:
            siguiente = min(
                pendientes,
                key=lambda c: (
                    math.hypot(c.latitud - lat_actual, c.longitud - lon_actual),
                    c.id,
                ),
            )
            ordenados.append(siguiente)
            pendientes.remove(siguiente)
            lat_actual, lon_actual = siguiente.latitud, siguiente.longitud
        return ordenados

    @classmethod
    def _optimizar_centros(
        cls,
        centros: list[CentroExtraccion],
        optimizacion_client: Any | None = None,
        origen: dict[str, float] | None = None,
    ) -> list[CentroExtraccion]:
        if len(centros) <= 1:
            return centros

        punto_origen = origen or LAB_CENTRAL_COORDS
        cliente = cls._resolver_optimizacion_client(optimizacion_client)
        coordenadas = [
            punto_origen,
            *[{"lat": float(c.latitud), "lon": float(c.longitud)} for c in centros],
            LAB_CENTRAL_COORDS,
        ]

        recorrido = None
        for _ in range(3):
            try:
                recorrido = cliente.optimizar_recorrido(coordenadas)
                break
            except (ClienteError, OSError):
                continue

        if not recorrido:
            return cls._ordenar_centros_local(centros, origen=punto_origen)

        # Mapea las coordenadas intermedias devueltas por OSRM a los centros reales
        pendientes = list(centros)
        ordenados: list[CentroExtraccion] = []
        intermedias = recorrido[1:-1] if len(recorrido) >= len(centros) + 2 else recorrido
        for punto in intermedias:
            if not pendientes:
                break
            plat = float(punto.get("lat", 0.0))
            plon = float(punto.get("lon", 0.0))
            mas_cercano = min(
                pendientes,
                key=lambda c: math.hypot(c.latitud - plat, c.longitud - plon),
            )
            ordenados.append(mas_cercano)
            pendientes.remove(mas_cercano)

        ordenados.extend(pendientes)
        return ordenados

    @staticmethod
    def _serializar_orden(orden: OrdenDelDia) -> dict[str, Any]:
        ultima_pos = (
            max(orden.posiciones, key=lambda pos: pos.id) if orden.posiciones else None
        )
        return {
            "orden_id": orden.id,
            "transportista_id": orden.transportista_id,
            "fecha": orden.fecha.isoformat(),
            "ubicacion_transportista": (
                {
                    "latitud": ultima_pos.latitud,
                    "longitud": ultima_pos.longitud,
                    "registrada_en": (
                        ultima_pos.registrada_en.isoformat() if ultima_pos.registrada_en else None
                    ),
                }
                if ultima_pos
                else None
            ),
            "paradas": [
                {
                    "parada_id": p.id,
                    "centro_id": p.centro_id,
                    "nombre_centro": p.centro.nombre if p.centro else None,
                    "direccion": p.centro.direccion if p.centro else None,
                    "latitud": p.centro.latitud if p.centro else None,
                    "longitud": p.centro.longitud if p.centro else None,
                    "posicion": p.posicion,
                    "retirada_en": p.retirada_en.isoformat() if p.retirada_en else None,
                    "llegada_lab_central": (
                        p.llegada_lab_central.isoformat() if p.llegada_lab_central else None
                    ),
                }
                for p in orden.paradas
            ],
        }

    @classmethod
    def obtener_o_generar_orden_del_dia(
        cls,
        usuario_actual_id: int,
        fecha: date | None = None,
        optimizacion_client: Any | None = None,
        origen_lat: float | None = None,
        origen_lon: float | None = None,
        recalcular: bool = False,
    ) -> tuple[dict[str, Any] | None, str | None, int]:
        transportista = LogisticaRepo.obtener_transportista_por_usuario(usuario_actual_id)
        if not transportista:
            return None, "El usuario no posee un perfil de transportista.", 403

        fecha_obj = fecha or date.today()
        if fecha_obj.weekday() >= 5:
            return (
                None,
                "No se generan ordenes del dia en fines de semana (DIA_NO_HABIL_SIN_ORDEN_DEL_DIA).",
                400,
            )

        origen = (
            {"lat": float(origen_lat), "lon": float(origen_lon)}
            if origen_lat is not None and origen_lon is not None
            else None
        )

        existente = LogisticaRepo.obtener_orden_del_dia(transportista.id, fecha_obj)
        if existente:
            sin_recogidas = all(p.retirada_en is None for p in existente.paradas)
            if recalcular and origen is not None and sin_recogidas:
                centros_actuales = [p.centro for p in existente.paradas if p.centro is not None]
                if not centros_actuales:
                    centros_actuales = LogisticaRepo.listar_centros_con_muestras_listas(
                        transportista.provincia
                    )
                if centros_actuales:
                    centros_reordenados = cls._optimizar_centros(
                        centros_actuales,
                        optimizacion_client=optimizacion_client,
                        origen=origen,
                    )
                    try:
                        LogisticaRepo.reemplazar_paradas_orden(existente.id, centros_reordenados)
                        LogisticaRepo.registrar_posicion(
                            orden_id=existente.id,
                            latitud=origen["lat"],
                            longitud=origen["lon"],
                        )
                        LogisticaRepo.guardar_cambios()
                        orden_actualizada = LogisticaRepo.obtener_orden_por_id(existente.id)
                        return cls._serializar_orden(orden_actualizada or existente), None, 200
                    except SQLAlchemyError as exc:
                        LogisticaRepo.deshacer_cambios()
                        return None, f"Error al recalcular la orden del dia: {exc!s}", 500
            return cls._serializar_orden(existente), None, 200

        centros = LogisticaRepo.listar_centros_con_muestras_listas(transportista.provincia)
        if not centros:
            return {"orden_del_dia": None, "paradas": []}, None, 200

        centros_ordenados = cls._optimizar_centros(
            centros,
            optimizacion_client=optimizacion_client,
            origen=origen,
        )
        try:
            orden = LogisticaRepo.crear_orden_del_dia(
                transportista_id=transportista.id,
                fecha=fecha_obj,
                centros_ordenados=centros_ordenados,
            )
            if origen is not None:
                LogisticaRepo.registrar_posicion(
                    orden_id=orden.id,
                    latitud=origen["lat"],
                    longitud=origen["lon"],
                )
            LogisticaRepo.guardar_cambios()
        except IntegrityError:
            LogisticaRepo.deshacer_cambios()
            orden_carrera = LogisticaRepo.obtener_orden_del_dia(transportista.id, fecha_obj)
            if orden_carrera:
                return cls._serializar_orden(orden_carrera), None, 200
            return None, "Conflicto al generar la orden del dia.", 409
        except SQLAlchemyError as exc:
            LogisticaRepo.deshacer_cambios()
            return None, f"Error al guardar la orden del dia: {exc!s}", 500

        orden_completa = LogisticaRepo.obtener_orden_por_id(orden.id)
        return cls._serializar_orden(orden_completa or orden), None, 200

    @classmethod
    def marcar_recogida_centro(
        cls,
        orden_id: int,
        parada_id: int,
        usuario_actual_id: int,
        ahora: datetime | None = None,
    ) -> tuple[dict[str, Any] | None, str | None, int]:
        transportista = LogisticaRepo.obtener_transportista_por_usuario(usuario_actual_id)
        if not transportista:
            return None, "El usuario no posee un perfil de transportista.", 403

        orden = LogisticaRepo.obtener_orden_por_id(orden_id)
        if not orden:
            return None, f"La orden del dia {orden_id} no existe.", 404
        if orden.transportista_id != transportista.id:
            return None, "No tiene permisos para operar sobre esta orden del dia.", 403

        parada = LogisticaRepo.obtener_parada_por_id(orden_id, parada_id)
        if not parada:
            return None, f"La parada {parada_id} no pertenece a la orden {orden_id}.", 404
        if parada.retirada_en is not None:
            return None, "La recogida en este centro ya fue registrada (PARADA_YA_RETIRADA).", 409

        marca_tiempo = ahora or datetime.now()
        try:
            parada.retirada_en = marca_tiempo
            if parada.centro is not None:
                LogisticaRepo.registrar_posicion(
                    orden_id=orden.id,
                    latitud=parada.centro.latitud,
                    longitud=parada.centro.longitud,
                )

            muestras = LogisticaRepo.listar_muestras_por_centro_y_estado(
                centro_id=parada.centro_id,
                estado_estudio=EstadoEstudio.LISTA_PARA_RETIRAR,
            )
            estudios_ids: list[int] = []
            for muestra in muestras:
                muestra.estudio.estado = EstadoEstudio.EN_CAMINO_LAB_CENTRAL
                estudios_ids.append(muestra.estudio.id)

            LogisticaRepo.guardar_cambios()
        except SQLAlchemyError as exc:
            LogisticaRepo.deshacer_cambios()
            return None, f"Error al registrar la recogida: {exc!s}", 500

        return {
            "orden_id": orden.id,
            "parada_id": parada.id,
            "centro_id": parada.centro_id,
            "retirada_en": marca_tiempo.isoformat(),
            "estudios_en_camino_ids": estudios_ids,
        }, None, 200

    @classmethod
    def armar_sample_set_para_muestras_recibidas(
        cls,
        muestras_ids: list[int],
    ) -> list[int]:
        """Hook hacia Escenario 12/14: se completara al implementar SampleSets."""
        return []

    @classmethod
    def marcar_llegada_lab_central(
        cls,
        orden_id: int,
        usuario_actual_id: int,
        mililitros_por_muestra: list[dict[str, Any]] | None = None,
        ahora: datetime | None = None,
    ) -> tuple[dict[str, Any] | None, str | None, int]:
        transportista = LogisticaRepo.obtener_transportista_por_usuario(usuario_actual_id)
        if not transportista:
            return None, "El usuario no posee un perfil de transportista.", 403

        orden = LogisticaRepo.obtener_orden_por_id(orden_id)
        if not orden:
            return None, f"La orden del dia {orden_id} no existe.", 404
        if orden.transportista_id != transportista.id:
            return None, "No tiene permisos para operar sobre esta orden del dia.", 403

        retiradas = [p for p in orden.paradas if p.retirada_en is not None]
        if not retiradas:
            return None, "No hay muestras retiradas en camino (SIN_MUESTRAS_EN_CAMINO).", 409

        pendientes = [p for p in retiradas if p.llegada_lab_central is None]
        if not pendientes:
            return None, "La llegada ya fue registrada previamente (LLEGADA_YA_REGISTRADA).", 409

        mapa_ml = {
            int(item["muestra_id"]): Decimal(str(item["mililitros"]))
            for item in (mililitros_por_muestra or [])
            if "muestra_id" in item and "mililitros" in item
        }

        marca_tiempo = ahora or datetime.now()
        muestras_ids: list[int] = []
        estudios_ids: list[int] = []
        try:
            for parada in pendientes:
                parada.llegada_lab_central = marca_tiempo
                muestras = LogisticaRepo.listar_muestras_por_centro_y_estado(
                    centro_id=parada.centro_id,
                    estado_estudio=EstadoEstudio.EN_CAMINO_LAB_CENTRAL,
                )
                for muestra in muestras:
                    muestra.llegada_lab_central = marca_tiempo
                    if muestra.id in mapa_ml:
                        muestra.mililitros = mapa_ml[muestra.id]
                    muestra.estudio.estado = EstadoEstudio.EN_LAB_CENTRAL
                    muestras_ids.append(muestra.id)
                    estudios_ids.append(muestra.estudio.id)

            LogisticaRepo.guardar_cambios()
        except SQLAlchemyError as exc:
            LogisticaRepo.deshacer_cambios()
            return None, f"Error al registrar la llegada al laboratorio central: {exc!s}", 500

        sample_sets_ids = cls.armar_sample_set_para_muestras_recibidas(muestras_ids)
        return {
            "orden_id": orden.id,
            "llegada_lab_central": marca_tiempo.isoformat(),
            "muestras_recibidas_ids": muestras_ids,
            "estudios_en_lab_central_ids": estudios_ids,
            "sample_sets_afectados_ids": sample_sets_ids,
        }, None, 200