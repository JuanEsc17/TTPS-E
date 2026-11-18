import { useCallback, useEffect, useState } from "react";
import {
    marcarLlegadaLabCentralRequest,
    marcarRecogidaParadaRequest,
    obtenerOrdenDelDiaHoyRequest,
} from "../api/logistica";
import MapaRutaLeaflet from "../components/MapaRutaLeaflet";

const LAB_CENTRAL_PUNTO = {
    nombre: "Laboratorio Central",
    direccion: "Calle 60 Nro 555, La Plata",
    latitud: -34.921577136619085,
    longitud: -57.93843617249286,
};

function formatearHora(iso) {
    if (!iso) return "";
    const fecha = new Date(iso);
    if (Number.isNaN(fecha.getTime())) return iso;
    return fecha.toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" });
}

export default function OrdenDelDiaPage({ sesion }) {
    const token = sesion?.access_token;
    const esTransportista = sesion?.usuario?.rol === "transportista";

    const [orden, setOrden] = useState(null);
    const [cargando, setCargando] = useState(Boolean(token && esTransportista));
    const [error, setError] = useState("");
    const [aviso, setAviso] = useState(null);
    const [paradaSeleccionadaId, setParadaSeleccionadaId] = useState(null);
    const [paradaProcesandoId, setParadaProcesandoId] = useState(null);
    const [confirmandoLlegada, setConfirmandoLlegada] = useState(false);
    const [ubicacionLocal, setUbicacionLocal] = useState(null);
    const [modoFijarUbicacion, setModoFijarUbicacion] = useState(false);

    const aplicarOrden = useCallback((data) => {
        setOrden(data);
        const primeraPendiente =
            data?.paradas?.find((p) => !p.retirada_en) || data?.paradas?.[0] || null;
        setParadaSeleccionadaId(primeraPendiente ? primeraPendiente.parada_id : null);
    }, []);

    const cargarOrdenHoy = useCallback(
        async (coords = null, { recalcular = false } = {}) => {
            if (!token || !esTransportista) return;
            const origen = coords || ubicacionLocal;
            setCargando(true);
            setError("");
            try {
                const data = await obtenerOrdenDelDiaHoyRequest(token, {
                    lat: origen?.latitud,
                    lon: origen?.longitud,
                    recalcular,
                });
                aplicarOrden(data);
            } catch (err) {
                setError(err.message);
            } finally {
                setCargando(false);
            }
        },
        [token, esTransportista, ubicacionLocal, aplicarOrden]
    );

    useEffect(() => {
        if (!token || !esTransportista) return;
        let cancelado = false;

        function pedirOrden(coords) {
            obtenerOrdenDelDiaHoyRequest(token, {
                lat: coords?.latitud,
                lon: coords?.longitud,
            })
                .then((data) => {
                    if (!cancelado) {
                        aplicarOrden(data);
                        setError("");
                    }
                })
                .catch((err) => {
                    if (!cancelado) setError(err.message);
                })
                .finally(() => {
                    if (!cancelado) setCargando(false);
                });
        }

        if (typeof navigator !== "undefined" && navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (pos) => {
                    if (cancelado) return;
                    const coords = {
                        latitud: pos.coords.latitude,
                        longitud: pos.coords.longitude,
                    };
                    setUbicacionLocal(coords);
                    pedirOrden(coords);
                },
                () => {
                    if (!cancelado) pedirOrden(null);
                },
                { timeout: 3000, maximumAge: 60000 }
            );
        } else {
            pedirOrden(null);
        }

        return () => {
            cancelado = true;
        };
    }, [token, esTransportista, aplicarOrden]);

    function handleUsarMiGps() {
        if (typeof navigator === "undefined" || !navigator.geolocation) {
            setError("Tu navegador no soporta geolocalización. Usá 'Ubicar en mapa' para fijar tu posición.");
            return;
        }
        setError("");
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                const coords = {
                    latitud: pos.coords.latitude,
                    longitud: pos.coords.longitude,
                };
                setUbicacionLocal(coords);
                setModoFijarUbicacion(false);
                cargarOrdenHoy(coords, { recalcular: true });
            },
            () => {
                setError("No se pudo obtener el GPS del navegador. Podés fijar tu posición con 'Ubicar en mapa'.");
            },
            { timeout: 4000 }
        );
    }

    function handleFijarUbicacionMapa(coords) {
        setUbicacionLocal(coords);
        setModoFijarUbicacion(false);
        cargarOrdenHoy(coords, { recalcular: true });
    }

    async function handleMarcarRecogida(parada) {
        if (!orden?.orden_id) return;
        setParadaProcesandoId(parada.parada_id);
        setError("");
        setAviso(null);
        try {
            const res = await marcarRecogidaParadaRequest({
                token,
                ordenId: orden.orden_id,
                paradaId: parada.parada_id,
            });
            setOrden((prev) => {
                if (!prev) return prev;
                return {
                    ...prev,
                    paradas: prev.paradas.map((item) =>
                        item.parada_id === parada.parada_id
                            ? { ...item, retirada_en: res.retirada_en }
                            : item
                    ),
                };
            });
            const cantidad = res.estudios_en_camino_ids?.length || 0;
            setAviso({
                tipo: "ok",
                texto: `Recogida registrada en ${parada.nombre_centro || `Centro #${parada.centro_id}`} (${cantidad} estudio${cantidad === 1 ? "" : "s"} en camino al laboratorio central).`,
            });
        } catch (err) {
            setError(err.message);
        } finally {
            setParadaProcesandoId(null);
        }
    }

    async function handleConfirmarLlegada() {
        if (!orden?.orden_id) return;
        setConfirmandoLlegada(true);
        setError("");
        setAviso(null);
        try {
            const res = await marcarLlegadaLabCentralRequest({
                token,
                ordenId: orden.orden_id,
            });
            setOrden((prev) => {
                if (!prev) return prev;
                return {
                    ...prev,
                    paradas: prev.paradas.map((item) =>
                        item.retirada_en && !item.llegada_lab_central
                            ? { ...item, llegada_lab_central: res.llegada_lab_central }
                            : item
                    ),
                };
            });
            const cant = res.muestras_recibidas_ids?.length || 0;
            setAviso({
                tipo: "ok",
                texto: `Llegada al laboratorio central registrada (${cant} muestra${cant === 1 ? "" : "s"} recibida${cant === 1 ? "" : "s"}).`,
            });
        } catch (err) {
            setError(err.message);
        } finally {
            setConfirmandoLlegada(false);
        }
    }

    if (!esTransportista) {
        return (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
                Solo el personal con rol Transportista puede consultar y operar la orden del día.
            </div>
        );
    }

    const paradas = orden?.paradas || [];
    const ubicacionTransportista = ubicacionLocal || orden?.ubicacion_transportista || null;
    const tieneOrden = Boolean(orden?.orden_id && paradas.length > 0);
    const paradasRetiradas = paradas.filter((p) => Boolean(p.retirada_en));
    const paradasPendientesEntrega = paradasRetiradas.filter((p) => !p.llegada_lab_central);
    const todasEntregadas =
        tieneOrden && paradas.length > 0 && paradas.every((p) => Boolean(p.llegada_lab_central));
    const paradaSeleccionada =
        paradas.find((p) => p.parada_id === paradaSeleccionadaId) || paradas[0] || null;

    let badgeTexto = "Sin muestras pendientes";
    let badgeClase = "border-slate-200 bg-slate-100 text-slate-700";
    if (todasEntregadas) {
        badgeTexto = "Recorrido finalizado · En Lab Central";
        badgeClase = "border-emerald-200 bg-emerald-50 text-emerald-700";
    } else if (paradasPendientesEntrega.length > 0) {
        badgeTexto = `${paradasRetiradas.length}/${paradas.length} paradas retiradas`;
        badgeClase = "border-cyan-200 bg-cyan-50 text-[#0B4F8A]";
    } else if (tieneOrden) {
        badgeTexto = `Ruta fijada · ${paradas.length} parada${paradas.length === 1 ? "" : "s"}`;
        badgeClase = "border-emerald-200 bg-emerald-50 text-emerald-700";
    }

    return (
        <div className="space-y-6">
            {/* Encabezado alineado al estilo clinico base */}
            <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                        Logística terrestre · Transporte de muestras
                    </p>
                    <h1 className="font-titulo mt-1 text-2xl font-semibold text-slate-900 sm:text-3xl">
                        Orden del día y retiro de muestras
                    </h1>
                    <p className="mt-1 text-sm text-slate-600">
                        Seguí el orden de paradas asignado para tu provincia, marcá cada recogida e informá la llegada al laboratorio central.
                    </p>
                </div>
                <button
                    type="button"
                    onClick={() => cargarOrdenHoy()}
                    disabled={cargando}
                    className="rounded-xl border border-[#0B4F8A] bg-white px-4 py-2 text-xs font-semibold text-[#0B4F8A] transition hover:bg-[#EAF2FA] disabled:opacity-50"
                >
                    {cargando ? "Actualizando..." : "Actualizar orden"}
                </button>
            </div>

            {/* Banner superior de estado (similar al prototipo) */}
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200/90 bg-white px-5 py-3.5 shadow-xs">
                <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#EAF2FA] text-[#0B4F8A]">
                        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                            <path d="M9 12l2 2 4-4" />
                            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                        </svg>
                    </div>
                    <div>
                        <p className="text-sm font-semibold text-slate-900">
                            {tieneOrden
                                ? `Orden del día #${orden.orden_id} · ${orden.fecha}`
                                : "Estado de la orden diaria"}
                        </p>
                        <p className="text-xs text-slate-500">
                            {tieneOrden
                                ? "La secuencia de centros es fija e inmutable durante toda la jornada hábil."
                                : "Se genera de lunes a viernes hábiles cuando existen muestras listas para retirar."}
                        </p>
                    </div>
                </div>
                <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${badgeClase}`}>
                    {badgeTexto}
                </span>
            </div>

            {error && (
                <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">
                    {error}
                </div>
            )}

            {aviso && (
                <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800" role="status">
                    {aviso.texto}
                </div>
            )}

            {cargando ? (
                <div className="tarjeta-cristal p-8 text-center text-sm text-slate-500">
                    Cargando orden del día...
                </div>
            ) : !tieneOrden ? (
                <div className="rounded-2xl border border-dashed border-slate-300 bg-white/80 p-8 text-center">
                    <h2 className="text-base font-semibold text-slate-800">
                        No hay paradas asignadas para hoy
                    </h2>
                    <p className="mt-1 text-sm text-slate-500">
                        Cuando existan muestras en estado &ldquo;Lista para retirar&rdquo; en tu provincia, aparecerán ordenadas aquí.
                    </p>
                </div>
            ) : (
                <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                    {/* Columna izquierda: Mapa de ruta */}
                    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs lg:col-span-7">
                        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                            <div className="flex items-center gap-3">
                                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#EAF2FA] text-[#0B4F8A]">
                                    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                                        <path d="M12 21s-6-5.33-6-10a6 6 0 1 1 12 0c0 4.67-6 10-6 10z" />
                                        <circle cx="12" cy="11" r="2.2" />
                                    </svg>
                                </div>
                                <div>
                                    <h2 className="text-sm font-semibold text-slate-900">
                                        Recorrido desde tu ubicación hasta el Lab Central
                                    </h2>
                                    <p className="text-xs text-slate-500">
                                        {modoFijarUbicacion
                                            ? "Hacé clic en cualquier punto del mapa para fijar tu ubicación actual."
                                            : "Orden: Transportista → Paradas 1..N → Laboratorio Central."}
                                    </p>
                                </div>
                            </div>
                            <div className="flex flex-wrap items-center gap-2">
                                <button
                                    type="button"
                                    disabled={paradasRetiradas.length > 0}
                                    onClick={handleUsarMiGps}
                                    className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                    Mi GPS
                                </button>
                                <button
                                    type="button"
                                    disabled={paradasRetiradas.length > 0}
                                    onClick={() => setModoFijarUbicacion((prev) => !prev)}
                                    className={`rounded-lg border px-2.5 py-1.5 text-[11px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${
                                        modoFijarUbicacion
                                            ? "border-amber-500 bg-amber-50 text-amber-800"
                                            : "border-[#0B4F8A]/30 bg-white text-[#0B4F8A] hover:bg-[#EAF2FA]"
                                    }`}
                                >
                                    {modoFijarUbicacion ? "Cancelar ubicación" : "Ubicar en mapa"}
                                </button>
                            </div>
                        </div>

                        <MapaRutaLeaflet
                            paradas={paradas}
                            labCentral={LAB_CENTRAL_PUNTO}
                            ubicacionTransportista={ubicacionTransportista}
                            paradaSeleccionadaId={paradaSeleccionada?.parada_id}
                            onSeleccionarParada={setParadaSeleccionadaId}
                            modoFijarUbicacion={modoFijarUbicacion}
                            onFijarUbicacion={handleFijarUbicacionMapa}
                        />

                        {paradaSeleccionada && (
                            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200/80 bg-slate-50/70 px-4 py-3">
                                <div className="flex items-center gap-3">
                                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-white text-[#0B4F8A] shadow-xs">
                                        <span className="text-xs font-bold">#{paradaSeleccionada.posicion}</span>
                                    </div>
                                    <div>
                                        <p className="text-xs font-semibold text-slate-900">
                                            {paradaSeleccionada.nombre_centro || `Centro #${paradaSeleccionada.centro_id}`}
                                        </p>
                                        <p className="text-[11px] text-slate-500">
                                            {paradaSeleccionada.direccion || "Dirección no informada"}
                                        </p>
                                    </div>
                                </div>
                                <div className="flex items-center gap-3">
                                    <span className="text-xs font-medium text-slate-600">
                                        {paradaSeleccionada.llegada_lab_central
                                            ? `Entregada ${formatearHora(paradaSeleccionada.llegada_lab_central)}`
                                            : paradaSeleccionada.retirada_en
                                                ? `Retirada ${formatearHora(paradaSeleccionada.retirada_en)}`
                                                : "Pendiente de retiro"}
                                    </span>
                                    {Number.isFinite(Number(paradaSeleccionada.latitud)) &&
                                        Number.isFinite(Number(paradaSeleccionada.longitud)) && (
                                            <a
                                                href={`https://www.google.com/maps/dir/?api=1&destination=${paradaSeleccionada.latitud},${paradaSeleccionada.longitud}`}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="rounded-lg border border-[#0B4F8A]/30 bg-white px-2.5 py-1 text-[11px] font-semibold text-[#0B4F8A] transition hover:bg-[#EAF2FA]"
                                            >
                                                Cómo llegar
                                            </a>
                                        )}
                                </div>
                            </div>
                        )}
                    </section>

                    {/* Columna derecha: Paradas ordenadas + Confirmar llegada al lab central */}
                    <div className="space-y-6 lg:col-span-5">
                        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
                            <div className="mb-4 flex items-center gap-3">
                                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#EAF2FA] text-[#0B4F8A]">
                                    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                                        <rect x="3" y="4" width="18" height="16" rx="2" />
                                        <path d="M8 9h8M8 13h5" />
                                    </svg>
                                </div>
                                <div>
                                    <h2 className="text-sm font-semibold text-slate-900">
                                        Paradas de hoy ({paradas.length})
                                    </h2>
                                    <p className="text-xs text-slate-500">
                                        Marcá cada centro al retirar las muestras listas.
                                    </p>
                                </div>
                            </div>

                            <ul className="space-y-2.5">
                                {paradas.map((p) => {
                                    const recogida = Boolean(p.retirada_en);
                                    const entregada = Boolean(p.llegada_lab_central);
                                    const seleccionada = p.parada_id === paradaSeleccionada?.parada_id;
                                    const procesando = paradaProcesandoId === p.parada_id;

                                    return (
                                        <li
                                            key={p.parada_id}
                                            className={`rounded-xl border p-3.5 transition ${seleccionada
                                                    ? "border-[#0B4F8A] bg-[#EAF2FA]/45"
                                                    : "border-slate-200 hover:border-slate-300 hover:bg-slate-50/70"
                                                }`}
                                        >
                                            <div className="flex items-start justify-between gap-3">
                                                <button
                                                    type="button"
                                                    onClick={() => setParadaSeleccionadaId(p.parada_id)}
                                                    className="min-w-0 flex-1 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] rounded-lg"
                                                >
                                                    <div className="flex items-center gap-2">
                                                        <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#0B4F8A] text-[11px] font-semibold text-white">
                                                            {p.posicion}
                                                        </span>
                                                        <span className="truncate text-sm font-semibold text-slate-900">
                                                            {p.nombre_centro || `Centro #${p.centro_id}`}
                                                        </span>
                                                    </div>
                                                    {p.direccion && (
                                                        <p className="mt-1 pl-7 text-xs text-slate-500">{p.direccion}</p>
                                                    )}
                                                </button>

                                                {entregada ? (
                                                    <span className="shrink-0 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700">
                                                        En Lab Central
                                                    </span>
                                                ) : recogida ? (
                                                    <span className="shrink-0 rounded-full bg-cyan-50 px-2.5 py-1 text-[11px] font-semibold text-[#0891B2]">
                                                        Retirada · {formatearHora(p.retirada_en)}
                                                    </span>
                                                ) : (
                                                    <button
                                                        type="button"
                                                        disabled={procesando}
                                                        onClick={() => handleMarcarRecogida(p)}
                                                        className="shrink-0 rounded-lg bg-[#0B4F8A] px-3 py-1.5 text-xs font-semibold text-white shadow-xs transition hover:bg-[#093D6B] disabled:opacity-50"
                                                    >
                                                        {procesando ? "Guardando..." : "Marcar recogida"}
                                                    </button>
                                                )}
                                            </div>
                                        </li>
                                    );
                                })}
                            </ul>
                        </section>

                        {/* Tarjeta inferior derecha: Llegada al laboratorio central */}
                        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
                            <div className="flex items-start gap-3">
                                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#EAF2FA] text-[#0B4F8A]">
                                    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                                        <path d="M3 12h13l3 4v4H3v-8z" />
                                        <path d="M16 12V7H3v5" />
                                        <circle cx="7.5" cy="20" r="1.5" />
                                        <circle cx="17.5" cy="20" r="1.5" />
                                    </svg>
                                </div>
                                <div>
                                    <h2 className="text-sm font-semibold text-slate-900">
                                        Llegada al laboratorio central
                                    </h2>
                                    <p className="mt-0.5 text-xs text-slate-500">
                                        {LAB_CENTRAL_PUNTO.direccion}. Confirmá al entregar las muestras retiradas en el laboratorio central.
                                    </p>
                                </div>
                            </div>

                            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
                                <div className="text-xs text-slate-600">
                                    <span className="font-semibold text-slate-800">En camino:</span>{" "}
                                    {paradasPendientesEntrega.length} parada
                                    {paradasPendientesEntrega.length === 1 ? "" : "s"}
                                </div>
                                <button
                                    type="button"
                                    disabled={paradasPendientesEntrega.length === 0 || confirmandoLlegada}
                                    onClick={handleConfirmarLlegada}
                                    className="inline-flex items-center gap-2 rounded-xl bg-[#0B4F8A] px-4 py-2.5 text-xs font-semibold text-white shadow-xs transition hover:bg-[#093D6B] disabled:cursor-not-allowed disabled:bg-slate-300"
                                >
                                    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
                                        <polyline points="20 6 9 17 4 12" />
                                    </svg>
                                    {confirmandoLlegada
                                        ? "Registrando llegada..."
                                        : todasEntregadas
                                            ? "Llegada confirmada"
                                            : "Confirmar llegada"}
                                </button>
                            </div>
                        </section>
                    </div>
                </div>
            )}
        </div>
    );
}
