import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { cancelarTurnoRequest, listarMisTurnosRequest } from "../api/turnos";

const ESTILOS_ESTADO = {
    Confirmado: "border-cyan-200 bg-cyan-50 text-[#0B4F8A]",
    Asistido: "border-emerald-200 bg-emerald-50 text-emerald-700",
    Cancelado: "border-slate-200 bg-slate-100 text-slate-600",
    Ausente: "border-amber-200 bg-amber-50 text-amber-800",
};

function obtenerAlertaAusencias(ausencias, maxAusencias = 5) {
    if (!Number.isFinite(ausencias) || ausencias < maxAusencias - 2) return null;
    if (ausencias >= maxAusencias) {
        return {
            nivel: "critico",
            titulo: `Límite de ${maxAusencias} ausencias alcanzado`,
            texto: "Se anuló el pago anterior. Deberás abonar nuevamente el estudio para volver a sacar turno.",
        };
    }
    const restantes = maxAusencias - ausencias;
    return {
        nivel: "alerta",
        titulo:
            restantes === 1
                ? "¡Última oportunidad antes de perder el pago!"
                : "Estás cerca del límite de ausencias",
        texto:
            restantes === 1
                ? `Acumulás ${ausencias} de ${maxAusencias} ausencias. Si faltás una vez más perderás el pago del estudio.`
                : `Acumulás ${ausencias} de ${maxAusencias} ausencias. Te quedan ${restantes} oportunidades antes de perder el pago.`,
    };
}

const FILTROS = [
    { id: "Activos", label: "Activos" },
    { id: "Cancelado", label: "Cancelados" },
    { id: "Ausente", label: "Ausentes" },
];

function formatearFechaCorta(iso) {
    if (!iso) return "";
    const fecha = new Date(iso);
    if (Number.isNaN(fecha.getTime())) return iso;
    return fecha.toLocaleDateString("es-AR", {
        weekday: "short",
        day: "2-digit",
        month: "short",
        year: "numeric",
    });
}

function formatearFechaLarga(iso) {
    if (!iso) return "";
    const fecha = new Date(iso);
    if (Number.isNaN(fecha.getTime())) return iso;
    return fecha.toLocaleDateString("es-AR", {
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric",
    });
}

function formatearHora(iso) {
    if (!iso) return "";
    const match = iso.match(/T(\d{2}:\d{2})/);
    if (match) return match[1];
    const fecha = new Date(iso);
    if (Number.isNaN(fecha.getTime())) return "";
    return fecha.toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" });
}

export default function MisTurnosPage({ sesion }) {
    const token = sesion?.access_token;
    const esPaciente = sesion?.usuario?.rol === "paciente";

    const [turnos, setTurnos] = useState([]);
    const [cargando, setCargando] = useState(Boolean(token && esPaciente));
    const [filtro, setFiltro] = useState("Activos");
    const [seleccionadoId, setSeleccionadoId] = useState(null);
    const [confirmandoCancelId, setConfirmandoCancelId] = useState(null);
    const [cancelandoId, setCancelandoId] = useState(null);
    const [estudioCanceladoId, setEstudioCanceladoId] = useState(null);
    const [error, setError] = useState("");
    const [aviso, setAviso] = useState("");

    useEffect(() => {
        if (!token || !esPaciente) return;
        let cancelado = false;

        listarMisTurnosRequest(token)
            .then((data) => {
                if (cancelado) return;
                const lista = Array.isArray(data) ? data : [];
                setTurnos(lista);
                if (lista.length > 0) {
                    const activo = lista.find(
                        (t) => t.estado_turno === "Confirmado" || t.estado_turno === "Asistido"
                    );
                    setSeleccionadoId((prev) => prev ?? (activo ? activo.turno_id : lista[0].turno_id));
                }
                setError("");
            })
            .catch((err) => {
                if (!cancelado) setError(err.message);
            })
            .finally(() => {
                if (!cancelado) setCargando(false);
            });

        return () => {
            cancelado = true;
        };
    }, [token, esPaciente]);

    const conteos = useMemo(() => {
        const mapa = {
            Activos: 0,
            Cancelado: 0,
            Ausente: 0,
        };
        for (const t of turnos) {
            if (t.estado_turno === "Confirmado" || t.estado_turno === "Asistido") {
                mapa.Activos += 1;
            } else if (mapa[t.estado_turno] !== undefined) {
                mapa[t.estado_turno] += 1;
            }
        }
        return mapa;
    }, [turnos]);

    const turnosFiltrados = useMemo(() => {
        if (filtro === "Activos") {
            return turnos.filter(
                (t) => t.estado_turno === "Confirmado" || t.estado_turno === "Asistido"
            );
        }
        return turnos.filter((t) => t.estado_turno === filtro);
    }, [turnos, filtro]);

    const turnoDetalle = useMemo(() => {
        if (turnosFiltrados.length === 0) return null;
        return (
            turnosFiltrados.find((t) => t.turno_id === seleccionadoId) ||
            turnosFiltrados[0]
        );
    }, [turnosFiltrados, seleccionadoId]);

    async function handleCancelarTurno(turno) {
        if (!turno?.turno_id) return;
        setCancelandoId(turno.turno_id);
        setError("");
        setAviso("");
        try {
            await cancelarTurnoRequest({ token, turnoId: turno.turno_id });
            const actualizados = await listarMisTurnosRequest(token);
            setTurnos(Array.isArray(actualizados) ? actualizados : []);
            setConfirmandoCancelId(null);
            setEstudioCanceladoId(turno.estudio_id);
            setAviso(
                `Turno #${turno.turno_id} cancelado correctamente. No consumió ausencias y ya podés elegir otro horario.`
            );
        } catch (err) {
            setError(err.message);
        } finally {
            setCancelandoId(null);
        }
    }

    if (!esPaciente) {
        return (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
                Esta sección es exclusiva para pacientes.
            </div>
        );
    }

    const turnoActivo = turnos.find((t) => t.estado_turno === "Confirmado") || null;

    return (
        <div className="space-y-6">
            {/* Encabezado */}
            <div>
                <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                    Exoma Clínico · Agenda del paciente
                </p>
                <h1 className="font-titulo mt-1 text-2xl font-semibold text-slate-900 sm:text-3xl">
                    Mis turnos e historial
                </h1>
                <p className="mt-1 text-sm text-slate-600">
                    Consultá tus turnos activos y pasados, revisá el detalle de cada sede y cancelá o reprogramá sin cargo.
                </p>
            </div>

            {/* Banner de proximo turno activo */}
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200/90 bg-white px-5 py-3.5 shadow-xs">
                <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#EAF2FA] text-[#0B4F8A]">
                        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                            <rect x="3" y="4" width="18" height="18" rx="2" />
                            <line x1="16" y1="2" x2="16" y2="6" />
                            <line x1="8" y1="2" x2="8" y2="6" />
                            <line x1="3" y1="10" x2="21" y2="10" />
                        </svg>
                    </div>
                    <div>
                        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                            Próximo turno activo
                        </p>
                        <p className="text-sm font-semibold text-slate-900">
                            {turnoActivo
                                ? `${formatearFechaCorta(turnoActivo.inicio)} · ${formatearHora(turnoActivo.inicio)} hs — ${turnoActivo.centro?.nombre || "Centro de extracción"}`
                                : "Sin turno activo"}
                        </p>
                    </div>
                </div>
                <span
                    className={`rounded-full border px-3 py-1 text-xs font-semibold ${
                        turnoActivo
                            ? "border-cyan-200 bg-cyan-50 text-[#0B4F8A]"
                            : "border-slate-200 bg-slate-100 text-slate-600"
                    }`}
                >
                    {turnoActivo ? "Confirmado" : "Disponible para reservar"}
                </span>
            </div>

            {error && (
                <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">
                    {error}
                </div>
            )}

            {aviso && (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800" role="status">
                    <span>{aviso}</span>
                    {estudioCanceladoId && (
                        <Link
                            to={`/paciente/estudios/${estudioCanceladoId}/turno`}
                            className="rounded-lg bg-emerald-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-800"
                        >
                            Elegir nuevo turno →
                        </Link>
                    )}
                </div>
            )}

            {cargando ? (
                <div className="tarjeta-cristal p-8 text-center text-sm text-slate-500">
                    Cargando tu historial de turnos...
                </div>
            ) : turnos.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-slate-300 bg-white/80 p-8 text-center">
                    <h2 className="text-base font-semibold text-slate-800">
                        Todavía no sacaste ningún turno
                    </h2>
                    <p className="mt-1 text-sm text-slate-500">
                        Cuando abones o se autorice tu estudio y reserves un turno en un centro de extracción, vas a poder consultar su estado e historial aquí.
                    </p>
                </div>
            ) : (
                <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                    {/* Columna izquierda: Filtros + Listado historial */}
                    <section className="tarjeta-cristal lg:col-span-7">
                        <div className="h-1.5 w-full bg-gradient-to-r from-[#062846] via-[#0B4F8A] to-[#0891B2]" />
                        <div className="space-y-4 p-5">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                                <h2 className="text-sm font-semibold text-slate-900">
                                    Historial de reservas
                                </h2>
                                <div className="flex flex-wrap gap-1.5">
                                    {FILTROS.map((f) => {
                                        const activo = filtro === f.id;
                                        return (
                                            <button
                                                key={f.id}
                                                type="button"
                                                onClick={() => setFiltro(f.id)}
                                                className={`rounded-full px-3 py-1 text-[11px] font-semibold transition ${
                                                    activo
                                                        ? "bg-[#0B4F8A] text-white"
                                                        : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                                                }`}
                                            >
                                                {f.label} ({conteos[f.id]})
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>

                            {turnosFiltrados.length === 0 ? (
                                <p className="py-6 text-center text-xs text-slate-500">
                                    No hay turnos en esta categoría.
                                </p>
                            ) : (
                                <div className="space-y-2.5">
                                    {turnosFiltrados.map((t) => {
                                        const elegido = turnoDetalle?.turno_id === t.turno_id;
                                        const esAsistido = t.estado_turno === "Asistido";
                                        const badgeClase =
                                            ESTILOS_ESTADO[t.estado_turno] ||
                                            "border-slate-200 bg-slate-100 text-slate-700";
                                        const alertaCard =
                                            !esAsistido
                                                ? obtenerAlertaAusencias(t.ausencias_estudio, t.max_ausencias)
                                                : null;

                                        return (
                                            <div
                                                key={t.turno_id}
                                                onClick={() => setSeleccionadoId(t.turno_id)}
                                                role="button"
                                                tabIndex={0}
                                                onKeyDown={(e) => {
                                                    if (e.key === "Enter" || e.key === " ") {
                                                        e.preventDefault();
                                                        setSeleccionadoId(t.turno_id);
                                                    }
                                                }}
                                                className={`cursor-pointer rounded-xl border p-4 transition ${
                                                    elegido
                                                        ? "border-[#0B4F8A] bg-[#EAF2FA]/75 shadow-xs"
                                                        : "border-slate-200/90 bg-white/90 hover:border-slate-300 hover:bg-white"
                                                }`}
                                            >
                                                <div className="flex flex-wrap items-start justify-between gap-2">
                                                    <div>
                                                        <div className="flex flex-wrap items-center gap-2">
                                                            <span className="text-xs font-bold text-[#0B4F8A]">
                                                                Turno #{t.turno_id}
                                                            </span>
                                                            <span className="text-[11px] text-slate-400">·</span>
                                                            <span className="text-xs font-semibold text-slate-800">
                                                                Estudio #{t.estudio_id}
                                                                {t.patologia ? ` (${t.patologia})` : ""}
                                                            </span>
                                                        </div>
                                                        <p className="mt-1 text-sm font-semibold text-slate-900">
                                                            {t.centro?.nombre || "Centro de extracción"}
                                                        </p>
                                                        <p className="mt-0.5 text-xs text-slate-600 capitalize">
                                                            {formatearFechaCorta(t.inicio)} ·{" "}
                                                            <span className="font-semibold text-slate-800">
                                                                {formatearHora(t.inicio)} hs
                                                            </span>
                                                        </p>
                                                    </div>

                                                    <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${badgeClase}`}>
                                                        {t.estado_turno}
                                                    </span>
                                                </div>

                                                {alertaCard && (
                                                    <div
                                                        className={`mt-2.5 rounded-lg border px-3 py-1.5 text-[11px] font-medium ${
                                                            alertaCard.nivel === "critico"
                                                                ? "border-red-200 bg-red-50 text-red-800"
                                                                : "border-amber-200 bg-amber-50 text-amber-900"
                                                        }`}
                                                    >
                                                        <strong>{alertaCard.titulo}:</strong> {alertaCard.texto}
                                                    </div>
                                                )}

                                                {t.puede_cancelar && (
                                                    <div
                                                        className="mt-3 flex flex-wrap items-center justify-end gap-2 border-t border-slate-200/70 pt-2.5"
                                                        onClick={(e) => e.stopPropagation()}
                                                    >
                                                        {confirmandoCancelId === t.turno_id ? (
                                                            <div className="flex w-full flex-wrap items-center justify-between gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2">
                                                                <span className="text-[11px] font-medium text-red-800">
                                                                    ¿Confirmás cancelar este turno?
                                                                </span>
                                                                <div className="flex gap-2">
                                                                    <button
                                                                        type="button"
                                                                        disabled={cancelandoId === t.turno_id}
                                                                        onClick={() => handleCancelarTurno(t)}
                                                                        className="rounded-lg bg-red-600 px-3 py-1 text-[11px] font-semibold text-white hover:bg-red-700 disabled:opacity-50"
                                                                    >
                                                                        {cancelandoId === t.turno_id ? "Cancelando..." : "Sí, cancelar"}
                                                                    </button>
                                                                    <button
                                                                        type="button"
                                                                        disabled={cancelandoId === t.turno_id}
                                                                        onClick={() => setConfirmandoCancelId(null)}
                                                                        className="rounded-lg border border-slate-300 bg-white px-3 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-50"
                                                                    >
                                                                        No
                                                                    </button>
                                                                </div>
                                                            </div>
                                                        ) : (
                                                            <button
                                                                type="button"
                                                                onClick={() => setConfirmandoCancelId(t.turno_id)}
                                                                className="rounded-lg border border-red-200 bg-white px-3 py-1 text-[11px] font-semibold text-red-700 transition hover:bg-red-50"
                                                            >
                                                                Cancelar turno
                                                            </button>
                                                        )}
                                                    </div>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    </section>

                    {/* Columna derecha: Detalle completo del turno seleccionado */}
                    <section className="tarjeta-cristal lg:col-span-5">
                        <div className="h-1.5 w-full bg-gradient-to-r from-[#0B4F8A] to-[#0891B2]" />
                        {turnoDetalle ? (
                            <div className="space-y-4 p-5">
                                <div className="flex items-start justify-between gap-3">
                                    <div>
                                        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                                            Detalle del turno #{turnoDetalle.turno_id}
                                        </p>
                                        <h2 className="font-titulo mt-0.5 text-xl font-semibold text-slate-900">
                                            {turnoDetalle.centro?.nombre || "Centro de extracción"}
                                        </h2>
                                    </div>
                                    <span
                                        className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${
                                            ESTILOS_ESTADO[turnoDetalle.estado_turno] ||
                                            "border-slate-200 bg-slate-100 text-slate-700"
                                        }`}
                                    >
                                        {turnoDetalle.estado_turno}
                                    </span>
                                </div>

                                <div className="space-y-2.5 rounded-xl border border-slate-200/80 bg-white/90 p-4 text-xs">
                                    <div className="flex justify-between gap-2">
                                        <span className="text-slate-500">Fecha</span>
                                        <span className="font-semibold capitalize text-slate-900">
                                            {formatearFechaLarga(turnoDetalle.inicio)}
                                        </span>
                                    </div>
                                    <div className="flex justify-between gap-2">
                                        <span className="text-slate-500">Horario</span>
                                        <span className="font-semibold text-[#0B4F8A]">
                                            {formatearHora(turnoDetalle.inicio)} hs ({turnoDetalle.duracion_minutos} min)
                                        </span>
                                    </div>
                                    <div className="flex justify-between gap-2">
                                        <span className="text-slate-500">Dirección</span>
                                        <span className="text-right font-medium text-slate-800">
                                            {turnoDetalle.centro?.direccion || "—"}
                                        </span>
                                    </div>
                                    <div className="flex justify-between gap-2 border-t border-slate-100 pt-2">
                                        <span className="text-slate-500">Estudio</span>
                                        <span className="font-semibold text-slate-900">
                                            #{turnoDetalle.estudio_id}
                                            {turnoDetalle.patologia ? ` · ${turnoDetalle.patologia}` : ""}
                                        </span>
                                    </div>
                                    <div className="flex justify-between gap-2">
                                        <span className="text-slate-500">Estado del estudio</span>
                                        <span className="font-semibold text-slate-800">
                                            {turnoDetalle.estado_estudio || "—"}
                                        </span>
                                    </div>
                                    <div className="flex justify-between gap-2">
                                        <span className="text-slate-500">Ausencias del estudio</span>
                                        <span className="font-semibold text-slate-800">
                                            {turnoDetalle.ausencias_estudio} de {turnoDetalle.max_ausencias}
                                        </span>
                                    </div>
                                    {turnoDetalle.muestra_tomada_en && (
                                        <div className="flex justify-between gap-2 border-t border-slate-100 pt-2">
                                            <span className="text-slate-500">Muestra tomada</span>
                                            <span className="font-semibold text-emerald-700">
                                                {formatearFechaCorta(turnoDetalle.muestra_tomada_en)} ·{" "}
                                                {formatearHora(turnoDetalle.muestra_tomada_en)} hs
                                            </span>
                                        </div>
                                    )}
                                </div>

                                {turnoDetalle.centro?.latitud != null && (
                                    <a
                                        href={`https://www.google.com/maps/search/?api=1&query=${turnoDetalle.centro.latitud},${turnoDetalle.centro.longitud}`}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="flex w-full items-center justify-center gap-2 rounded-xl border border-[#0B4F8A]/30 bg-white px-4 py-2 text-xs font-semibold text-[#0B4F8A] transition hover:bg-[#EAF2FA]"
                                    >
                                        Ver ubicación en Google Maps ↗
                                    </a>
                                )}

                                {turnoDetalle.estado_turno !== "Asistido" &&
                                    (() => {
                                        const alertaDet = obtenerAlertaAusencias(
                                            turnoDetalle.ausencias_estudio,
                                            turnoDetalle.max_ausencias
                                        );
                                        if (!alertaDet) return null;
                                        return (
                                            <div
                                                className={`rounded-xl border p-3.5 text-xs ${
                                                    alertaDet.nivel === "critico"
                                                        ? "border-red-200 bg-red-50 text-red-900"
                                                        : "border-amber-200 bg-amber-50 text-amber-900"
                                                }`}
                                                role="alert"
                                            >
                                                <p className="font-semibold">{alertaDet.titulo}</p>
                                                <p className="mt-1 text-[11px]">{alertaDet.texto}</p>
                                            </div>
                                        );
                                    })()}

                                {turnoDetalle.estado_turno === "Confirmado" && (
                                    <div className="rounded-xl border border-cyan-200/80 bg-cyan-50/70 p-3.5 text-xs text-slate-700">
                                        <p className="font-semibold text-[#0B4F8A]">Recordatorio para asistir</p>
                                        <ul className="mt-1.5 space-y-1 text-[11px]">
                                            <li>• No requiere ayuno ni preparación previa.</li>
                                            <li>• Llevá impresa la Orden de extracción y el Consentimiento informado.</li>
                                        </ul>
                                    </div>
                                )}

                                {turnoDetalle.puede_cancelar && (
                                    <div className="border-t border-slate-200 pt-3">
                                        {confirmandoCancelId === turnoDetalle.turno_id ? (
                                            <div className="space-y-2 rounded-xl border border-red-200 bg-red-50 p-3">
                                                <p className="text-xs font-medium text-red-800">
                                                    ¿Confirmás cancelar el turno #{turnoDetalle.turno_id}? Podrás volver a reservar sin cargo.
                                                </p>
                                                <div className="flex gap-2">
                                                    <button
                                                        type="button"
                                                        disabled={cancelandoId === turnoDetalle.turno_id}
                                                        onClick={() => handleCancelarTurno(turnoDetalle)}
                                                        className="flex-1 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-700 disabled:opacity-50"
                                                    >
                                                        {cancelandoId === turnoDetalle.turno_id ? "Cancelando..." : "Sí, cancelar"}
                                                    </button>
                                                    <button
                                                        type="button"
                                                        disabled={cancelandoId === turnoDetalle.turno_id}
                                                        onClick={() => setConfirmandoCancelId(null)}
                                                        className="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                                                    >
                                                        Mantener
                                                    </button>
                                                </div>
                                            </div>
                                        ) : (
                                            <button
                                                type="button"
                                                onClick={() => setConfirmandoCancelId(turnoDetalle.turno_id)}
                                                className="w-full rounded-xl border border-red-200 bg-red-50/70 px-4 py-2.5 text-xs font-semibold text-red-700 transition hover:bg-red-100"
                                            >
                                                Cancelar este turno
                                            </button>
                                        )}
                                    </div>
                                )}
                            </div>
                        ) : (
                            <div className="p-6 text-center text-xs text-slate-500">
                                Seleccioná un turno de la lista para ver sus detalles.
                            </div>
                        )}
                    </section>
                </div>
            )}
        </div>
    );
}
