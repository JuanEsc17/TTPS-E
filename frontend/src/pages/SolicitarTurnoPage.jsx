import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router-dom";
import {
    cancelarTurnoRequest,
    listarCentrosRequest,
    listarMisEstudiosRequest,
    obtenerDisponibilidadRequest,
    reservarTurnoRequest,
} from "../api/turnos";
import MapaCentrosLeaflet from "../components/MapaCentrosLeaflet";

// Feriados nacionales fijos alineados con TurnoService en el backend
const FERIADOS_FIJOS = new Set([
    "01-01",
    "03-24",
    "04-02",
    "05-01",
    "05-25",
    "06-20",
    "07-09",
    "12-08",
    "12-25",
]);

// Los 36 slots teoricos de 15 min entre 09:00 y 17:45
const SLOTS_TEORICOS = Array.from({ length: 36 }, (_, idx) => {
    const totalMin = 9 * 60 + idx * 15;
    const h = String(Math.floor(totalMin / 60)).padStart(2, "0");
    const m = String(totalMin % 60).padStart(2, "0");
    return `${h}:${m}`;
});

function aIsoFechaLocal(fecha) {
    const y = fecha.getFullYear();
    const m = String(fecha.getMonth() + 1).padStart(2, "0");
    const d = String(fecha.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
}

function esDiaHabil(fecha) {
    const dia = fecha.getDay();
    if (dia === 0 || dia === 6) return false;
    const mmdd = `${String(fecha.getMonth() + 1).padStart(2, "0")}-${String(fecha.getDate()).padStart(2, "0")}`;
    return !FERIADOS_FIJOS.has(mmdd);
}

function generarProximosDiasHabiles(cantidad = 5) {
    const ahora = new Date();
    const hoyIso = aIsoFechaLocal(ahora);
    const pasoUltimoTurnoHoy =
        ahora.getHours() > 17 || (ahora.getHours() === 17 && ahora.getMinutes() >= 45);

    const dias = [];
    const cursor = new Date(ahora);
    cursor.setHours(0, 0, 0, 0);
    if (pasoUltimoTurnoHoy) {
        cursor.setDate(cursor.getDate() + 1);
    }

    while (dias.length < cantidad) {
        if (esDiaHabil(cursor)) {
            const iso = aIsoFechaLocal(cursor);
            dias.push({
                iso,
                esHoy: iso === hoyIso,
                diaSemana:
                    iso === hoyIso
                        ? "Hoy"
                        : cursor.toLocaleDateString("es-AR", { weekday: "short" }),
                numero: cursor.getDate(),
                mes: cursor.toLocaleDateString("es-AR", { month: "short" }),
            });
        }
        cursor.setDate(cursor.getDate() + 1);
    }
    return dias;
}

function formatearFechaLarga(isoFecha) {
    if (!isoFecha) return "";
    const [y, m, d] = isoFecha.split("-").map(Number);
    const fecha = new Date(y, m - 1, d);
    return fecha.toLocaleDateString("es-AR", {
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric",
    });
}

function formatearHoraDeIso(isoDatetime) {
    if (!isoDatetime) return "";
    const match = isoDatetime.match(/T(\d{2}:\d{2})/);
    return match ? match[1] : isoDatetime;
}

export default function SolicitarTurnoPage({ sesion }) {
    const token = sesion?.access_token;
    const esPaciente = sesion?.usuario?.rol === "paciente";

    const { estudioId: estudioIdParam } = useParams();
    const [searchParams] = useSearchParams();
    const location = useLocation();

    const estudioSolicitadoId = useMemo(() => {
        const raw =
            estudioIdParam ||
            searchParams.get("estudioId") ||
            location.state?.estudioId;
        const num = Number(raw);
        return Number.isInteger(num) && num > 0 ? num : null;
    }, [estudioIdParam, searchParams, location.state?.estudioId]);

    const diasSugeridos = useMemo(() => generarProximosDiasHabiles(5), []);
    const fechaMinima = diasSugeridos[0]?.iso || "";

    const [misEstudios, setMisEstudios] = useState([]);
    const [estudioSeleccionadoId, setEstudioSeleccionadoId] = useState(estudioSolicitadoId);
    const [cargandoInicial, setCargandoInicial] = useState(Boolean(token && esPaciente));

    const [centros, setCentros] = useState([]);
    const [busquedaCentro, setBusquedaCentro] = useState("");
    const [centroSeleccionadoId, setCentroSeleccionadoId] = useState(null);

    const [fechaSeleccionada, setFechaSeleccionada] = useState(fechaMinima);
    const [slotsLibresIso, setSlotsLibresIso] = useState([]);
    const [cargandoSlots, setCargandoSlots] = useState(false);
    const [slotSeleccionadoIso, setSlotSeleccionadoIso] = useState("");

    const [confirmando, setConfirmando] = useState(false);
    const [confirmarCancelacion, setConfirmarCancelacion] = useState(false);
    const [cancelando, setCancelando] = useState(false);

    const [error, setError] = useState("");
    const [aviso, setAviso] = useState("");

    // Cargar estudios del paciente autenticado y centros de extraccion
    useEffect(() => {
        if (!token || !esPaciente) return;
        let cancelado = false;

        Promise.all([listarMisEstudiosRequest(token), listarCentrosRequest(token)])
            .then(([estudiosData, centrosData]) => {
                if (cancelado) return;
                const listaEstudios = Array.isArray(estudiosData) ? estudiosData : [];
                const listaCentros = Array.isArray(centrosData) ? centrosData : [];

                setMisEstudios(listaEstudios);
                setCentros(listaCentros);

                if (listaEstudios.length > 0) {
                    const porUrl = estudioSolicitadoId
                        ? listaEstudios.find((e) => e.estudio_id === estudioSolicitadoId)
                        : null;
                    const elegido =
                        porUrl ||
                        listaEstudios.find((e) => e.habilitado_para_turno) ||
                        listaEstudios.find((e) => e.turno_activo) ||
                        listaEstudios[0];
                    setEstudioSeleccionadoId(elegido.estudio_id);
                }

                if (listaCentros.length > 0) {
                    setCentroSeleccionadoId((prev) => prev ?? listaCentros[0].id);
                }
                setError("");
            })
            .catch((err) => {
                if (!cancelado) setError(err.message);
            })
            .finally(() => {
                if (!cancelado) setCargandoInicial(false);
            });

        return () => {
            cancelado = true;
        };
    }, [token, esPaciente, estudioSolicitadoId]);

    const estudioActual = useMemo(
        () => misEstudios.find((e) => e.estudio_id === estudioSeleccionadoId) || null,
        [misEstudios, estudioSeleccionadoId]
    );

    const turnoActivo = estudioActual?.turno_activo || null;
    const puedeReservarEstudio = Boolean(estudioActual?.habilitado_para_turno && !turnoActivo);

    // Cargar disponibilidad cuando cambia el centro o la fecha (y el estudio admite reserva)
    useEffect(() => {
        if (
            !token ||
            !esPaciente ||
            !centroSeleccionadoId ||
            !fechaSeleccionada ||
            turnoActivo ||
            !puedeReservarEstudio
        ) {
            return;
        }
        let cancelado = false;

        Promise.resolve().then(() => {
            if (!cancelado) {
                setCargandoSlots(true);
                setSlotSeleccionadoIso("");
            }
        });

        obtenerDisponibilidadRequest({
            token,
            centroId: centroSeleccionadoId,
            fecha: fechaSeleccionada,
        })
            .then((data) => {
                if (cancelado) return;
                setSlotsLibresIso(data?.slots_libres || []);
                setError("");
            })
            .catch((err) => {
                if (!cancelado) {
                    setSlotsLibresIso([]);
                    setError(err.message);
                }
            })
            .finally(() => {
                if (!cancelado) setCargandoSlots(false);
            });

        return () => {
            cancelado = true;
        };
    }, [token, esPaciente, centroSeleccionadoId, fechaSeleccionada, turnoActivo, puedeReservarEstudio]);

    const centrosFiltrados = useMemo(() => {
        const q = busquedaCentro.trim().toLowerCase();
        if (!q) return centros;
        return centros.filter(
            (c) =>
                c.nombre.toLowerCase().includes(q) ||
                c.direccion.toLowerCase().includes(q)
        );
    }, [centros, busquedaCentro]);

    const centroSeleccionado = useMemo(
        () => centros.find((c) => c.id === centroSeleccionadoId) || null,
        [centros, centroSeleccionadoId]
    );

    const mapaSlotsPorHora = useMemo(() => {
        const mapa = new Map();
        for (const iso of slotsLibresIso) {
            mapa.set(formatearHoraDeIso(iso), iso);
        }
        return mapa;
    }, [slotsLibresIso]);

    const hoyIso = useMemo(() => aIsoFechaLocal(new Date()), []);

    const slotsVisibles = useMemo(() => {
        if (fechaSeleccionada !== hoyIso) return SLOTS_TEORICOS;
        const ahora = new Date();
        const horaActual = `${String(ahora.getHours()).padStart(2, "0")}:${String(ahora.getMinutes()).padStart(2, "0")}`;
        return SLOTS_TEORICOS.filter((h) => h > horaActual);
    }, [fechaSeleccionada, hoyIso]);

    const slotsManana = useMemo(
        () => slotsVisibles.filter((h) => h < "13:00"),
        [slotsVisibles]
    );
    const slotsTarde = useMemo(
        () => slotsVisibles.filter((h) => h >= "13:00"),
        [slotsVisibles]
    );

    const handleSeleccionarCentro = useCallback((id) => {
        setCentroSeleccionadoId(id);
        setError("");
    }, []);

    async function recargarEstudios() {
        const actualizados = await listarMisEstudiosRequest(token);
        setMisEstudios(Array.isArray(actualizados) ? actualizados : []);
    }

    async function handleConfirmarTurno() {
        if (!estudioActual) {
            setError("No tenés un estudio seleccionado para agendar el turno.");
            return;
        }
        if (!centroSeleccionadoId || !slotSeleccionadoIso) {
            setError("Seleccioná un centro de extracción y un horario disponible.");
            return;
        }

        setConfirmando(true);
        setError("");
        setAviso("");
        try {
            await reservarTurnoRequest({
                token,
                estudioId: estudioActual.estudio_id,
                centroId: centroSeleccionadoId,
                inicio: slotSeleccionadoIso,
            });
            await recargarEstudios();
            setConfirmarCancelacion(false);
            setAviso("Turno reservado con éxito. Enviamos la documentación y recordatorio a tu correo.");
        } catch (err) {
            setError(err.message);
        } finally {
            setConfirmando(false);
        }
    }

    async function handleCancelarTurno() {
        if (!turnoActivo?.turno_id) return;
        setCancelando(true);
        setError("");
        try {
            await cancelarTurnoRequest({
                token,
                turnoId: turnoActivo.turno_id,
            });
            await recargarEstudios();
            setConfirmarCancelacion(false);
            setSlotSeleccionadoIso("");
            setAviso("Turno cancelado correctamente. Ya podés elegir un nuevo centro u horario sin cargo.");
        } catch (err) {
            setError(err.message);
        } finally {
            setCancelando(false);
        }
    }

    if (!esPaciente) {
        return (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
                Esta sección es exclusiva para pacientes con un estudio habilitado para extracción.
            </div>
        );
    }

    const horaSeleccionadaTexto = formatearHoraDeIso(slotSeleccionadoIso);
    const puedeReservar = Boolean(estudioActual?.habilitado_para_turno && !turnoActivo);

    return (
        <div className="space-y-6">
            {/* Stepper de progreso clinico */}
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-white/80 bg-white/75 px-5 py-3 shadow-xs backdrop-blur-md">
                <ol className="flex flex-wrap items-center gap-3 text-xs">
                    <li className="flex items-center gap-2 text-emerald-700">
                        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-100 font-bold text-emerald-700">
                            ✓
                        </span>
                        <span className="font-semibold">Pago / Obra Social</span>
                    </li>
                    <span className="text-slate-300" aria-hidden="true">→</span>
                    <li className="flex items-center gap-2 text-[#0B4F8A]">
                        <span
                            className={`flex h-6 w-6 items-center justify-center rounded-full font-bold ${
                                turnoActivo
                                    ? "bg-emerald-100 text-emerald-700"
                                    : "bg-[#0B4F8A] text-white"
                            }`}
                        >
                            {turnoActivo ? "✓" : "2"}
                        </span>
                        <span className="font-semibold">Centro y horario</span>
                    </li>
                    <span className="text-slate-300" aria-hidden="true">→</span>
                    <li
                        className={`flex items-center gap-2 ${
                            turnoActivo ? "font-semibold text-[#0B4F8A]" : "text-slate-400"
                        }`}
                    >
                        <span
                            className={`flex h-6 w-6 items-center justify-center rounded-full font-bold ${
                                turnoActivo
                                    ? "bg-[#0B4F8A] text-white"
                                    : "bg-slate-100 text-slate-400"
                            }`}
                        >
                            3
                        </span>
                        <span>Extracción de muestra</span>
                    </li>
                </ol>

                <div className="flex items-center gap-4">
                    <Link
                        to="/paciente/mis-turnos"
                        className="text-xs font-semibold text-[#0B4F8A] hover:underline"
                    >
                        Ver mis turnos e historial →
                    </Link>
                    <Link
                        to="/paciente/estudios"
                        className="text-xs font-semibold text-slate-600 hover:text-[#0B4F8A] hover:underline"
                    >
                        ← Mis estudios
                    </Link>
                </div>
            </div>

            {/* Encabezado principal */}
            <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                        Exoma Clínico · La Plata y alrededores
                    </p>
                    <h1 className="font-titulo mt-1 text-2xl font-semibold text-slate-900 sm:text-3xl">
                        Elegí dónde y cuándo
                    </h1>
                    <p className="mt-1 text-sm text-slate-600">
                        Seleccioná un centro de extracción en La Plata o alrededores y un horario disponible. Cada turno dura 15 minutos y se atiende de lunes a viernes hábiles.
                    </p>
                </div>

                {misEstudios.length > 0 && (
                    <div className="flex items-center gap-2 rounded-xl border border-slate-200/90 bg-white/90 px-3 py-2 text-xs shadow-xs">
                        <label htmlFor="selector-mi-estudio" className="font-medium text-slate-500">
                            Estudio:
                        </label>
                        {misEstudios.length === 1 ? (
                            <span className="font-bold text-[#0B4F8A]">
                                #{misEstudios[0].estudio_id}
                                {misEstudios[0].patologia ? ` · ${misEstudios[0].patologia}` : ""}
                            </span>
                        ) : (
                            <select
                                id="selector-mi-estudio"
                                value={estudioSeleccionadoId ?? ""}
                                onChange={(e) => {
                                    setEstudioSeleccionadoId(Number(e.target.value));
                                    setError("");
                                    setAviso("");
                                }}
                                className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs font-semibold text-[#0B4F8A] focus:border-[#0B4F8A] focus:outline-none"
                            >
                                {misEstudios.map((est) => (
                                    <option key={est.estudio_id} value={est.estudio_id}>
                                        #{est.estudio_id} · {est.patologia || "Exoma"} ({est.estado})
                                    </option>
                                ))}
                            </select>
                        )}
                    </div>
                )}
            </div>

            {/* Banner superior de estado */}
            {!cargandoInicial && (
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
                                {!estudioActual
                                    ? "Sin estudios disponibles"
                                    : turnoActivo
                                        ? `Turno confirmado para el Estudio #${estudioActual.estudio_id}`
                                        : estudioActual.habilitado_para_turno
                                            ? `Estudio #${estudioActual.estudio_id} habilitado para reservar`
                                            : `Estudio #${estudioActual.estudio_id} en estado "${estudioActual.estado}"`}
                            </p>
                            <p className="text-xs text-slate-500">
                                {!estudioActual
                                    ? "Todavía no tenés estudios asignados a tu cuenta."
                                    : turnoActivo
                                        ? "Recordá presentarte con tu documento, orden de extracción y consentimiento informado."
                                        : estudioActual.habilitado_para_turno
                                            ? estudioActual.estado === "Remuestreo requerido"
                                                ? "Tu muestra requiere una nueva extracción sin costo adicional. Elegí sede y horario."
                                                : "El pago o la autorización de obra social habilitan la reserva en cualquiera de nuestras sedes."
                                            : "Para reservar un turno el estudio debe estar autorizado por obra social o abonado."}
                            </p>
                        </div>
                    </div>
                    {estudioActual && (
                        <span
                            className={`rounded-full border px-3 py-1 text-xs font-semibold ${
                                turnoActivo
                                    ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                                    : estudioActual.habilitado_para_turno
                                        ? "border-cyan-200 bg-cyan-50 text-[#0B4F8A]"
                                        : "border-amber-200 bg-amber-50 text-amber-800"
                            }`}
                        >
                            {turnoActivo
                                ? "Turno sacado"
                                : estudioActual.habilitado_para_turno
                                    ? "Habilitado · Turno de 15 min"
                                    : estudioActual.estado}
                        </span>
                    )}
                </div>
            )}

            {estudioActual &&
                !cargandoInicial &&
                estudioActual.ausencias >= (estudioActual.max_ausencias || 5) - 2 && (
                    <div
                        className={`rounded-xl border px-4 py-3 text-xs ${
                            estudioActual.ausencias >= (estudioActual.max_ausencias || 5)
                                ? "border-red-200 bg-red-50 text-red-900"
                                : "border-amber-300 bg-amber-50 text-amber-900"
                        }`}
                        role="alert"
                    >
                        {estudioActual.ausencias >= (estudioActual.max_ausencias || 5) ? (
                            <p>
                                <strong>Límite de {estudioActual.max_ausencias || 5} ausencias alcanzado:</strong>{" "}
                                el pago del Estudio #{estudioActual.estudio_id} fue anulado. Deberás abonarlo nuevamente para poder reservar otro turno.
                            </p>
                        ) : (
                            <p>
                                <strong>¡Atención con tus inasistencias!</strong> El Estudio #{estudioActual.estudio_id} acumula{" "}
                                <strong>
                                    {estudioActual.ausencias} de {estudioActual.max_ausencias || 5} ausencias
                                </strong>
                                . Te queda{" "}
                                <strong>
                                    {(estudioActual.max_ausencias || 5) - estudioActual.ausencias} oportunidad
                                    {(estudioActual.max_ausencias || 5) - estudioActual.ausencias === 1 ? "" : "es"}
                                </strong>{" "}
                                antes de perder el pago.
                            </p>
                        )}
                    </div>
                )}

            {error && (
                <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">
                    {error}
                </div>
            )}

            {aviso && (
                <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800" role="status">
                    {aviso}
                </div>
            )}

            {cargandoInicial ? (
                <div className="tarjeta-cristal p-8 text-center text-sm text-slate-500">
                    Cargando tus estudios y centros de extracción...
                </div>
            ) : !estudioActual ? (
                <div className="rounded-2xl border border-dashed border-slate-300 bg-white/80 p-8 text-center">
                    <h2 className="text-base font-semibold text-slate-800">
                        No tenés estudios para agendar turno
                    </h2>
                    <p className="mt-1 text-sm text-slate-500">
                        Cuando tu médico solicite un estudio y esté autorizado o abonado, vas a poder reservar tu turno acá.
                    </p>
                </div>
            ) : turnoActivo ? (
                /* Vista post-confirmacion (Ticket profesional + cancelar/reprogramar Escenario 8) */
                <section className="tarjeta-cristal">
                    <div className="h-1.5 w-full bg-gradient-to-r from-emerald-500 via-[#0891B2] to-[#0B4F8A]" />
                    <div className="grid grid-cols-1 gap-6 p-6 lg:grid-cols-12">
                        <div className="space-y-4 lg:col-span-7">
                            <div className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
                                <span className="h-2 w-2 rounded-full bg-emerald-500" aria-hidden="true" />
                                Comprobante de turno #{turnoActivo.turno_id}
                            </div>

                            <h2 className="font-titulo text-2xl font-semibold text-slate-900">
                                {turnoActivo.centro?.nombre || `Centro #${turnoActivo.centro_id}`}
                            </h2>
                            {turnoActivo.centro?.direccion && (
                                <p className="text-sm text-slate-600">
                                    {turnoActivo.centro.direccion}
                                    {turnoActivo.centro.provincia
                                        ? `, ${turnoActivo.centro.provincia}`
                                        : ""}
                                </p>
                            )}

                            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                                <div className="rounded-xl border border-slate-200/80 bg-white/90 p-3.5">
                                    <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                                        Fecha
                                    </p>
                                    <p className="mt-1 text-sm font-semibold capitalize text-slate-900">
                                        {formatearFechaLarga(turnoActivo.inicio.slice(0, 10))}
                                    </p>
                                </div>
                                <div className="rounded-xl border border-slate-200/80 bg-white/90 p-3.5">
                                    <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                                        Horario
                                    </p>
                                    <p className="mt-1 text-sm font-semibold text-[#0B4F8A]">
                                        {formatearHoraDeIso(turnoActivo.inicio)} hs ({turnoActivo.duracion_minutos} min)
                                    </p>
                                </div>
                                <div className="rounded-xl border border-slate-200/80 bg-white/90 p-3.5">
                                    <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                                        Ausencias registradas
                                    </p>
                                    <p className="mt-1 text-sm font-semibold text-slate-900">
                                        {turnoActivo.ausencias_acumuladas} de {turnoActivo.max_ausencias}
                                    </p>
                                </div>
                            </div>

                            {turnoActivo.centro?.latitud != null && (
                                <div className="pt-1">
                                    <a
                                        href={`https://www.google.com/maps/search/?api=1&query=${turnoActivo.centro.latitud},${turnoActivo.centro.longitud}`}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="inline-flex items-center gap-2 rounded-xl border border-[#0B4F8A]/30 bg-white px-4 py-2 text-xs font-semibold text-[#0B4F8A] transition hover:bg-[#EAF2FA]"
                                    >
                                        Cómo llegar en Google Maps ↗
                                    </a>
                                </div>
                            )}
                        </div>

                        <div className="flex flex-col justify-between gap-4 rounded-2xl border border-slate-200/80 bg-white/85 p-5 lg:col-span-5">
                            <div>
                                <h3 className="text-sm font-semibold text-slate-900">
                                    Documentación enviada a tu correo
                                </h3>
                                <ul className="mt-3 space-y-2 text-xs text-slate-600">
                                    <li className="flex items-center gap-2">
                                        <span className="font-bold text-emerald-600">✓</span>
                                        Orden de extracción médica
                                    </li>
                                    <li className="flex items-center gap-2">
                                        <span className="font-bold text-emerald-600">✓</span>
                                        Plantilla de Consentimiento informado (llevar impresa y firmada)
                                    </li>
                                    <li className="flex items-center gap-2">
                                        <span className="font-bold text-emerald-600">✓</span>
                                        No requiere ayuno ni preparación especial
                                    </li>
                                </ul>
                            </div>

                            <div className="border-t border-slate-200 pt-4">
                                {!confirmarCancelacion ? (
                                    <button
                                        type="button"
                                        onClick={() => setConfirmarCancelacion(true)}
                                        className="w-full rounded-xl border border-red-200 bg-red-50/70 px-4 py-2.5 text-xs font-semibold text-red-700 transition hover:bg-red-100"
                                    >
                                        Cancelar y elegir otro turno
                                    </button>
                                ) : (
                                    <div className="space-y-2 rounded-xl border border-red-200 bg-red-50 p-3">
                                        <p className="text-xs font-medium text-red-800">
                                            ¿Confirmás cancelar este turno? No consume ausencias y podrás reservar otro horario.
                                        </p>
                                        <div className="flex gap-2">
                                            <button
                                                type="button"
                                                disabled={cancelando}
                                                onClick={handleCancelarTurno}
                                                className="flex-1 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-700 disabled:opacity-50"
                                            >
                                                {cancelando ? "Cancelando..." : "Sí, cancelar"}
                                            </button>
                                            <button
                                                type="button"
                                                disabled={cancelando}
                                                onClick={() => setConfirmarCancelacion(false)}
                                                className="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                                            >
                                                Mantener
                                            </button>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                </section>
            ) : !puedeReservar ? (
                <section className="rounded-2xl border border-amber-200 bg-amber-50/80 p-8 text-center">
                    <h2 className="text-base font-semibold text-amber-950">
                        El Estudio #{estudioActual.estudio_id} no admite reserva de turno en este estado
                    </h2>
                    <p className="mt-1.5 text-sm text-amber-900">
                        Estado actual: <strong>{estudioActual.estado}</strong>.{" "}
                        {estudioActual.estado === "Creado"
                            ? "Debe contar con un pago vigente o autorización de obra social para poder agendar la extracción."
                            : "Este estudio ya cuenta con una muestra tomada o continúa su circuito clínico, por lo que no permite sacar un nuevo turno."}
                    </p>
                    <div className="mt-4">
                        <Link
                            to="/paciente/mis-turnos"
                            className="inline-flex items-center rounded-xl bg-[#0B4F8A] px-4 py-2 text-xs font-semibold text-white hover:bg-[#093E6D]"
                        >
                            Ver mis turnos e historial →
                        </Link>
                    </div>
                </section>
            ) : (
                /* Grilla principal en 2 columnas: Centros (izq) + Fecha/Horario/Doc (der) */
                <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                    {/* Columna izquierda: Mapa + listado interactivo de centros en La Plata */}
                    <section className="tarjeta-cristal lg:col-span-7">
                        <div className="h-1.5 w-full bg-gradient-to-r from-[#062846] via-[#0B4F8A] to-[#0891B2]" />
                        <div className="space-y-4 p-5">
                            <div className="flex items-center gap-3">
                                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#EAF2FA] text-[#0B4F8A]">
                                    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                                        <path d="M12 21s-6-5.33-6-10a6 6 0 1 1 12 0c0 4.67-6 10-6 10z" />
                                        <circle cx="12" cy="11" r="2.2" />
                                    </svg>
                                </div>
                                <div>
                                    <h2 className="text-sm font-semibold text-slate-900">
                                        Centros de extracción · La Plata y alrededores
                                    </h2>
                                    <p className="text-xs text-slate-500">
                                        Tocá un marcador en el mapa o elegí una sede de la lista.
                                    </p>
                                </div>
                            </div>

                            <input
                                type="search"
                                value={busquedaCentro}
                                onChange={(e) => setBusquedaCentro(e.target.value)}
                                placeholder="Buscar sede en La Plata, City Bell, Berisso o Ensenada..."
                                aria-label="Buscar centro de extracción"
                                className="campo-clinico py-2 text-xs"
                            />

                            <MapaCentrosLeaflet
                                centros={centrosFiltrados}
                                centroSeleccionadoId={centroSeleccionadoId}
                                onSeleccionarCentro={handleSeleccionarCentro}
                            />

                            <div className="max-h-56 space-y-2 overflow-y-auto pr-1" role="listbox" aria-label="Listado de centros de extracción">
                                {centrosFiltrados.length === 0 ? (
                                    <p className="py-4 text-center text-xs text-slate-500">
                                        No encontramos centros que coincidan con tu búsqueda.
                                    </p>
                                ) : (
                                    centrosFiltrados.map((c) => {
                                        const activo = c.id === centroSeleccionadoId;
                                        return (
                                            <button
                                                key={c.id}
                                                type="button"
                                                role="option"
                                                aria-selected={activo}
                                                onClick={() => handleSeleccionarCentro(c.id)}
                                                className={`flex w-full items-center justify-between gap-3 rounded-xl border px-3.5 py-2.5 text-left transition ${
                                                    activo
                                                        ? "border-[#0B4F8A] bg-[#EAF2FA]/85 shadow-xs"
                                                        : "border-slate-200/90 bg-white/90 hover:border-slate-300 hover:bg-white"
                                                }`}
                                            >
                                                <div className="min-w-0 flex-1">
                                                    <div className="flex items-center gap-2">
                                                        <span className="truncate text-xs font-semibold text-slate-900">
                                                            {c.nombre}
                                                        </span>
                                                        {activo && (
                                                            <span className="rounded-full bg-[#0B4F8A] px-2 py-0.5 text-[10px] font-semibold text-white">
                                                                Seleccionado
                                                            </span>
                                                        )}
                                                    </div>
                                                    <p className="mt-0.5 truncate text-[11px] text-slate-500">
                                                        {c.direccion}
                                                    </p>
                                                </div>
                                            </button>
                                        );
                                    })
                                )}
                            </div>
                        </div>
                    </section>

                    {/* Columna derecha: Fecha/Horario + Documentacion y Confirmacion */}
                    <div className="space-y-6 lg:col-span-5">
                        {/* Tarjeta 1: Fecha y horario */}
                        <section className="tarjeta-cristal">
                            <div className="h-1.5 w-full bg-gradient-to-r from-[#0B4F8A] to-[#0891B2]" />
                            <div className="space-y-4 p-5">
                                <div className="flex items-center gap-3">
                                    <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#EAF2FA] text-[#0B4F8A]">
                                        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                                            <rect x="3" y="4" width="18" height="18" rx="2" />
                                            <line x1="16" y1="2" x2="16" y2="6" />
                                            <line x1="8" y1="2" x2="8" y2="6" />
                                            <line x1="3" y1="10" x2="21" y2="10" />
                                        </svg>
                                    </div>
                                    <div>
                                        <h2 className="text-sm font-semibold text-slate-900">
                                            Fecha y horario
                                        </h2>
                                        <p className="text-xs text-slate-500">
                                            Turnos de 15 min · Lun a vie · 09:00 a 18:00 hs.
                                        </p>
                                    </div>
                                </div>

                                {/* Proximos dias habiles + selector calendario */}
                                <div className="space-y-2.5">
                                    <div className="grid grid-cols-5 gap-1.5">
                                        {diasSugeridos.map((dia) => {
                                            const activo = fechaSeleccionada === dia.iso;
                                            return (
                                                <button
                                                    key={dia.iso}
                                                    type="button"
                                                    onClick={() => setFechaSeleccionada(dia.iso)}
                                                    className={`flex flex-col items-center rounded-xl border py-2 text-center transition ${
                                                        activo
                                                            ? "border-[#0B4F8A] bg-[#EAF2FA] text-[#0B4F8A] shadow-xs"
                                                            : "border-slate-200 bg-white text-slate-700 hover:border-slate-300"
                                                    }`}
                                                >
                                                    <span className="text-[10px] font-semibold uppercase">
                                                        {dia.diaSemana}
                                                    </span>
                                                    <span className="text-sm font-bold">{dia.numero}</span>
                                                    <span className="text-[10px] capitalize text-slate-500">
                                                        {dia.mes}
                                                    </span>
                                                </button>
                                            );
                                        })}
                                    </div>

                                    <div className="flex items-center justify-between gap-2 pt-1">
                                        <label htmlFor="selector-fecha-turno" className="text-[11px] font-medium text-slate-500">
                                            Otra fecha:
                                        </label>
                                        <input
                                            id="selector-fecha-turno"
                                            type="date"
                                            min={fechaMinima}
                                            value={fechaSeleccionada}
                                            onChange={(e) => setFechaSeleccionada(e.target.value)}
                                            className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 focus:border-[#0B4F8A] focus:outline-none"
                                        />
                                    </div>
                                </div>

                                {/* Grilla de slots disponibles */}
                                <div className="space-y-3 border-t border-slate-200/80 pt-3">
                                    <div className="flex items-center justify-between text-xs">
                                        <span className="font-semibold text-slate-800">
                                            Horarios disponibles
                                        </span>
                                        <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-semibold text-slate-600">
                                            {cargandoSlots
                                                ? "Consultando..."
                                                : `${slotsLibresIso.length} libres`}
                                        </span>
                                    </div>

                                    {cargandoSlots ? (
                                        <div className="grid grid-cols-4 gap-2">
                                            {Array.from({ length: 8 }).map((_, i) => (
                                                <div
                                                    key={i}
                                                    className="h-8 animate-pulse rounded-lg bg-slate-200/70"
                                                />
                                            ))}
                                        </div>
                                    ) : slotsLibresIso.length === 0 ? (
                                        <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50/70 p-4 text-center text-xs text-slate-500">
                                            Sin horarios disponibles para esta fecha (puede ser fin de semana, feriado o agenda completa). Probá seleccionando otro día hábil.
                                        </div>
                                    ) : (
                                        <div className="max-h-56 space-y-3 overflow-y-auto pr-1">
                                            {[
                                                { titulo: "Mañana", horas: slotsManana },
                                                { titulo: "Tarde", horas: slotsTarde },
                                            ]
                                                .filter((grupo) => grupo.horas.length > 0)
                                                .map((grupo) => (
                                                <div key={grupo.titulo}>
                                                    <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                                                        {grupo.titulo}
                                                    </p>
                                                    <div className="grid grid-cols-4 gap-1.5">
                                                        {grupo.horas.map((hora) => {
                                                            const isoLibre = mapaSlotsPorHora.get(hora);
                                                            const disponible = Boolean(isoLibre);
                                                            const elegido =
                                                                disponible &&
                                                                slotSeleccionadoIso === isoLibre;

                                                            return (
                                                                <button
                                                                    key={hora}
                                                                    type="button"
                                                                    disabled={!disponible}
                                                                    onClick={() =>
                                                                        setSlotSeleccionadoIso(isoLibre)
                                                                    }
                                                                    title={
                                                                        disponible
                                                                            ? `Seleccionar ${hora} hs`
                                                                            : "Horario ocupado"
                                                                    }
                                                                    className={`rounded-lg border py-1.5 text-xs font-semibold transition ${
                                                                        elegido
                                                                            ? "border-[#0B4F8A] bg-gradient-to-r from-[#0B4F8A] to-[#0E7490] text-white shadow-xs"
                                                                            : disponible
                                                                                ? "border-slate-200 bg-white text-slate-700 hover:border-[#0B4F8A] hover:bg-[#EAF2FA]/60"
                                                                                : "cursor-not-allowed border-slate-100 bg-slate-100/70 text-slate-300 line-through"
                                                                    }`}
                                                                >
                                                                    {hora}
                                                                </button>
                                                            );
                                                        })}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </div>
                        </section>

                        {/* Tarjeta 2: Documentacion para el turno + Confirmar */}
                        <section className="tarjeta-cristal">
                            <div className="space-y-4 p-5">
                                <div className="flex items-start gap-3">
                                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#EAF2FA] text-[#0B4F8A]">
                                        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                                            <polyline points="14 2 14 8 20 8" />
                                            <line x1="16" y1="13" x2="8" y2="13" />
                                            <line x1="16" y1="17" x2="8" y2="17" />
                                        </svg>
                                    </div>
                                    <div>
                                        <h2 className="text-sm font-semibold text-slate-900">
                                            Documentación para el turno
                                        </h2>
                                        <p className="mt-0.5 text-xs text-slate-500">
                                            Al confirmar, recibís por mail la orden de extracción, el consentimiento informado para imprimir/firmar y un recordatorio. No requiere ayuno.
                                        </p>
                                    </div>
                                </div>

                                <div className="rounded-xl border border-amber-200/80 bg-amber-50/70 px-3.5 py-2.5 text-[11px] text-amber-900">
                                    <strong>Importante:</strong> Podés reprogramar sin cargo antes del turno. Si acumulás <strong>5 inasistencias</strong> sin aviso, el pago del estudio se anula.
                                </div>

                                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200/80 pt-3">
                                    <div className="min-w-0 flex-1 text-xs">
                                        <p className="font-medium text-slate-400">Selección actual</p>
                                        <p className="truncate font-semibold text-slate-800">
                                            {centroSeleccionado
                                                ? `${horaSeleccionadaTexto || "Sin hora"} · ${centroSeleccionado.nombre}`
                                                : "Elegí un centro y horario"}
                                        </p>
                                    </div>

                                    <button
                                        type="button"
                                        disabled={
                                            confirmando ||
                                            !puedeReservar ||
                                            !centroSeleccionadoId ||
                                            !slotSeleccionadoIso
                                        }
                                        onClick={handleConfirmarTurno}
                                        className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-[#0B4F8A] to-[#0E7490] px-5 py-2.5 text-xs font-semibold text-white shadow-sm transition hover:from-[#093E6D] hover:to-[#0B5E75] disabled:cursor-not-allowed disabled:opacity-50"
                                    >
                                        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
                                            <polyline points="20 6 9 17 4 12" />
                                        </svg>
                                        {confirmando ? "Confirmando..." : "Confirmar turno"}
                                    </button>
                                </div>
                            </div>
                        </section>
                    </div>
                </div>
            )}
        </div>
    );
}
