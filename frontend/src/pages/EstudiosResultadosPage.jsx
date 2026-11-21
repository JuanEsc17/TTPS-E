import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
    descargarResultadoPdfRequest,
    listarMisEstudiosResultadosRequest,
} from "../api/resultados";

const BADGE_DIAGNOSTICO = {
    positivo: {
        texto: "Positivo",
        clase: "border-red-200 bg-red-50 text-red-700",
    },
    vus: {
        texto: "VUS · Seguimiento 1 año",
        clase: "border-amber-200 bg-amber-50 text-amber-800",
    },
    negativo: {
        texto: "Negativo",
        clase: "border-emerald-200 bg-emerald-50 text-emerald-700",
    },
};

const FILTROS = [
    { id: "todos", label: "Todos" },
    { id: "con_resultado", label: "Resultado cargado" },
    { id: "en_curso", label: "En curso" },
];

function formatearSoloFecha(isoDate) {
    if (!isoDate) return "";
    const partes = String(isoDate).split("-");
    return partes.length === 3 ? `${partes[2]}/${partes[1]}/${partes[0]}` : isoDate;
}

export default function EstudiosResultadosPage({ sesion }) {
    const token = sesion?.access_token;
    const rol = sesion?.usuario?.rol;
    const esPaciente = rol === "paciente";
    const esMedico = rol === "medico" || rol === "gerente_medico";

    const [recargaId, setRecargaId] = useState(0);
    const [estadoCarga, setEstadoCarga] = useState({
        recargaId: -1,
        estudios: [],
        error: "",
    });
    const [filtro, setFiltro] = useState("todos");
    const [descargandoId, setDescargandoId] = useState(null);
    const [errorDescarga, setErrorDescarga] = useState("");

    useEffect(() => {
        if (!token || (!esPaciente && !esMedico)) return;
        const controller = new AbortController();

        listarMisEstudiosResultadosRequest(token, { signal: controller.signal })
            .then((lista) => {
                if (controller.signal.aborted) return;
                setEstadoCarga({ recargaId, estudios: lista, error: "" });
            })
            .catch((err) => {
                if (err?.name === "AbortError" || controller.signal.aborted) return;
                setEstadoCarga({
                    recargaId,
                    estudios: [],
                    error: err.message || "No se pudieron cargar los estudios.",
                });
            });

        return () => controller.abort();
    }, [token, esPaciente, esMedico, recargaId]);

    const cargando = Boolean(token && (esPaciente || esMedico)) && estadoCarga.recargaId !== recargaId;
    const estudios = estadoCarga.estudios;
    const error = estadoCarga.recargaId === recargaId ? estadoCarga.error : "";

    const conteos = useMemo(() => {
        const conResultado = estudios.filter((e) => e.tiene_resultado).length;
        return {
            todos: estudios.length,
            con_resultado: conResultado,
            en_curso: estudios.length - conResultado,
        };
    }, [estudios]);

    const estudiosFiltrados = useMemo(() => {
        if (filtro === "con_resultado") return estudios.filter((e) => e.tiene_resultado);
        if (filtro === "en_curso") return estudios.filter((e) => !e.tiene_resultado);
        return estudios;
    }, [estudios, filtro]);

    async function handleDescargarPdf(estudioId) {
        if (!token) return;
        setDescargandoId(estudioId);
        setErrorDescarga("");
        try {
            await descargarResultadoPdfRequest({ token, estudioId });
        } catch (err) {
            setErrorDescarga(err.message || "No se pudo descargar el PDF.");
        } finally {
            setDescargandoId(null);
        }
    }

    if (!esPaciente && !esMedico) {
        return (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
                Esta sección está habilitada únicamente para pacientes y médicos tratantes.
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                        {esPaciente
                            ? "Exoma Clínico · Portal del paciente"
                            : "Gestión clínica · Estudios y resultados"}
                    </p>
                    <h1 className="font-titulo mt-1 text-2xl font-semibold text-slate-900 sm:text-3xl">
                        {esPaciente ? "Mis estudios y resultados" : "Estudios de pacientes"}
                    </h1>
                    <p className="mt-1 text-sm text-slate-600">
                        {esPaciente
                            ? "Seguí el estado de tus estudios de exoma clínico, visualizá tus variantes y descargá el informe en PDF."
                            : "Consultá el avance de los estudios derivados, revisá los diagnósticos cargados y descargá los informes en PDF."}
                    </p>
                </div>
                <button
                    type="button"
                    onClick={() => setRecargaId((n) => n + 1)}
                    disabled={cargando}
                    className="rounded-xl border border-[#0B4F8A] bg-white px-4 py-2 text-xs font-semibold text-[#0B4F8A] transition hover:bg-[#EAF2FA] disabled:opacity-50"
                >
                    {cargando ? "Actualizando..." : "Actualizar lista"}
                </button>
            </div>

            {error && (
                <div
                    role="alert"
                    className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-medium text-red-700"
                >
                    <span>{error}</span>
                    <button
                        type="button"
                        onClick={() => setRecargaId((n) => n + 1)}
                        className="font-semibold underline"
                    >
                        Reintentar
                    </button>
                </div>
            )}

            {errorDescarga && (
                <div
                    role="alert"
                    className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-medium text-red-700"
                >
                    <span>{errorDescarga}</span>
                    <button
                        type="button"
                        onClick={() => setErrorDescarga("")}
                        className="font-semibold underline"
                    >
                        Cerrar
                    </button>
                </div>
            )}

            <section className="tarjeta-cristal">
                <div className="h-1.5 w-full bg-gradient-to-r from-[#062846] via-[#0B4F8A] to-[#0891B2]" />
                <div className="space-y-4 p-5 sm:p-6">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                        <h2 className="text-sm font-semibold text-slate-900">
                            Listado de estudios ({estudiosFiltrados.length})
                        </h2>
                        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filtrar estudios">
                            {FILTROS.map((f) => {
                                const activo = filtro === f.id;
                                return (
                                    <button
                                        key={f.id}
                                        type="button"
                                        aria-pressed={activo}
                                        onClick={() => setFiltro(f.id)}
                                        className={`rounded-full px-3 py-1 text-[11px] font-semibold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] ${
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

                    {cargando ? (
                        <div
                            role="status"
                            aria-live="polite"
                            className="flex items-center gap-2 py-8 text-xs text-slate-500"
                        >
                            <span
                                aria-hidden="true"
                                className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-[#0B4F8A] border-t-transparent"
                            />
                            Cargando estudios...
                        </div>
                    ) : estudiosFiltrados.length === 0 ? (
                        <div className="rounded-xl border border-dashed border-slate-200 bg-white/70 p-8 text-center">
                            <p className="text-sm font-semibold text-slate-800">
                                {estudios.length === 0
                                    ? "Todavía no hay estudios registrados"
                                    : "No hay estudios en esta categoría"}
                            </p>
                            <p className="mt-1 text-xs text-slate-500">
                                {esPaciente
                                    ? "Cuando tu estudio tenga el resultado cargado podrás consultarlo y descargar el PDF desde aquí."
                                    : "Los estudios de tus pacientes derivados aparecerán aquí con acceso directo a sus resultados."}
                            </p>
                        </div>
                    ) : (
                        <ul className="space-y-3">
                            {estudiosFiltrados.map((est) => {
                                const badgeDiag = est.resultado?.diagnostico
                                    ? BADGE_DIAGNOSTICO[est.resultado.diagnostico]
                                    : null;
                                return (
                                    <li
                                        key={est.estudio_id}
                                        className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-200/90 bg-white/95 p-4 shadow-2xs transition hover:border-[#0B4F8A]/40"
                                    >
                                        <div className="min-w-0 space-y-1">
                                            <div className="flex flex-wrap items-center gap-2">
                                                <span className="text-sm font-semibold text-slate-900">
                                                    Estudio #{est.estudio_id}
                                                </span>
                                                <span
                                                    className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${
                                                        est.tiene_resultado
                                                            ? "border-cyan-200 bg-cyan-50 text-[#0B4F8A]"
                                                            : "border-slate-200 bg-slate-100 text-slate-600"
                                                    }`}
                                                >
                                                    {est.estado}
                                                </span>
                                                {est.es_pompe_urgente && (
                                                    <span className="rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-[10px] font-bold uppercase text-red-700">
                                                        Pompe urgente
                                                    </span>
                                                )}
                                                {badgeDiag && (
                                                    <span
                                                        className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${badgeDiag.clase}`}
                                                    >
                                                        {badgeDiag.texto}
                                                    </span>
                                                )}
                                                {est.cantidad_analisis > 1 && (
                                                    <span className="rounded-full border border-indigo-200 bg-indigo-50 px-2.5 py-0.5 text-[11px] font-semibold text-indigo-700">
                                                        {est.cantidad_analisis} análisis
                                                    </span>
                                                )}
                                            </div>

                                            <p className="text-xs font-medium text-slate-700">
                                                {est.patologia || "Patología en evaluación"}
                                                {esMedico && est.paciente?.nombre && (
                                                    <span className="font-normal text-slate-500">
                                                        {" "}· Paciente: {est.paciente.nombre} (DNI{" "}
                                                        {est.paciente.dni})
                                                    </span>
                                                )}
                                                {esPaciente && est.medico_nombre && (
                                                    <span className="font-normal text-slate-500">
                                                        {" "}· Médico tratante: {est.medico_nombre}
                                                    </span>
                                                )}
                                            </p>

                                            {est.tiene_resultado && est.fecha_reevaluacion_vus && (
                                                <p className="text-[11px] font-medium text-amber-800">
                                                    Reevaluación anual por VUS sugerida para:{" "}
                                                    <span className="font-mono font-semibold">
                                                        {formatearSoloFecha(est.fecha_reevaluacion_vus)}
                                                    </span>
                                                </p>
                                            )}
                                        </div>

                                        <div className="flex flex-wrap items-center gap-2">
                                            {est.tiene_resultado ? (
                                                <>
                                                    <Link
                                                        to={`/estudios/${est.estudio_id}/resultado`}
                                                        className="rounded-xl bg-[#0B4F8A] px-3.5 py-2 text-xs font-semibold text-white transition hover:bg-[#093E6D] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] focus-visible:ring-offset-1"
                                                    >
                                                        Ver resultado
                                                    </Link>
                                                    {esMedico && est.tiene_datos_crudos && (
                                                        <Link
                                                            to={`/estudios/${est.estudio_id}/resultado?reanalizar=1`}
                                                            className="rounded-xl border border-cyan-600/40 bg-cyan-50/70 px-3.5 py-2 text-xs font-semibold text-[#0B4F8A] transition hover:bg-cyan-100/70 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] focus-visible:ring-offset-1"
                                                        >
                                                            Reanalizar
                                                        </Link>
                                                    )}
                                                    <button
                                                        type="button"
                                                        disabled={descargandoId === est.estudio_id}
                                                        onClick={() =>
                                                            handleDescargarPdf(est.estudio_id)
                                                        }
                                                        className="rounded-xl border border-[#0B4F8A] bg-white px-3.5 py-2 text-xs font-semibold text-[#0B4F8A] transition hover:bg-[#EAF2FA] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] focus-visible:ring-offset-1 disabled:opacity-50"
                                                    >
                                                        {descargandoId === est.estudio_id
                                                            ? "Descargando..."
                                                            : "Descargar PDF"}
                                                    </button>
                                                </>
                                            ) : est.cantidad_analisis > 1 ? (
                                                <Link
                                                    to={`/estudios/${est.estudio_id}/resultado`}
                                                    className="rounded-xl border border-[#0B4F8A] bg-white px-3.5 py-2 text-xs font-semibold text-[#0B4F8A] transition hover:bg-[#EAF2FA] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] focus-visible:ring-offset-1"
                                                >
                                                    Ver historial
                                                </Link>
                                            ) : (
                                                <span className="text-xs font-medium text-slate-400">
                                                    Resultado aún no disponible
                                                </span>
                                            )}
                                        </div>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </div>
            </section>
        </div>
    );
}
