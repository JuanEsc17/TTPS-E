import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
    descargarResultadoPdfRequest,
    obtenerHistorialAnalisisRequest,
    obtenerResultadoEstudioRequest,
} from "../api/resultados";
import ModalReanalisis from "../components/ModalReanalisis";

const ESTILO_DIAGNOSTICO = {
    positivo: {
        etiqueta: "POSITIVO",
        subtitulo: "Se detectó al menos una variante clasificada como patogénica.",
        contenedor: "border-red-200 bg-red-50/90 text-red-950",
        badge: "border-red-300 bg-red-100 text-red-800",
        icono: "!",
    },
    vus: {
        etiqueta: "VUS · Variante de Significado Incierto",
        subtitulo:
            "Sin variantes patogénicas confirmadas. Se requiere seguimiento y reevaluación dentro de un año.",
        contenedor: "border-amber-200 bg-amber-50/90 text-amber-950",
        badge: "border-amber-300 bg-amber-100 text-amber-900",
        icono: "?",
    },
    negativo: {
        etiqueta: "NEGATIVO",
        subtitulo: "No se detectaron variantes patogénicas ni de significado incierto (VUS).",
        contenedor: "border-emerald-200 bg-emerald-50/90 text-emerald-950",
        badge: "border-emerald-300 bg-emerald-100 text-emerald-800",
        icono: "✓",
    },
};

const BADGE_CLASIFICACION = {
    patogenica: {
        texto: "Patogénica",
        clase: "border-red-200 bg-red-50 text-red-700",
    },
    vus: {
        texto: "VUS",
        clase: "border-amber-200 bg-amber-50 text-amber-800",
    },
    benigna: {
        texto: "Benigna",
        clase: "border-emerald-200 bg-emerald-50 text-emerald-700",
    },
    inocua: {
        texto: "Inocua",
        clase: "border-slate-200 bg-slate-100 text-slate-700",
    },
};

function formatearFechaHora(iso) {
    if (!iso) return "—";
    const fecha = new Date(iso);
    if (Number.isNaN(fecha.getTime())) return iso;
    return fecha.toLocaleString("es-AR", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });
}

function formatearSoloFecha(isoDate) {
    if (!isoDate) return "—";
    const partes = String(isoDate).split("-");
    if (partes.length === 3) {
        return `${partes[2]}/${partes[1]}/${partes[0]}`;
    }
    return isoDate;
}

function rutaVolverPorRol(rol) {
    if (rol === "paciente") return { to: "/paciente/estudios", label: "Volver a mis estudios" };
    if (rol === "medico" || rol === "gerente_medico") {
        return { to: "/medico/estudios", label: "Volver a estudios médicos" };
    }
    if (rol === "bioinformatico") {
        return { to: "/bioinformatica/cola", label: "Volver a análisis bioinformático" };
    }
    return { to: "/login", label: "Volver al inicio" };
}

export default function ResultadoEstudioPage({ sesion }) {
    const { estudioId } = useParams();
    const [searchParams, setSearchParams] = useSearchParams();
    const token = sesion?.access_token;
    const rol = sesion?.usuario?.rol;
    const esMedico = rol === "medico" || rol === "gerente_medico";

    const [recargaId, setRecargaId] = useState(0);
    const claveActual = `${token || ""}:${estudioId}:${recargaId}`;
    const [estadoCarga, setEstadoCarga] = useState({
        clave: null,
        datos: null,
        historialApi: null,
        error: null,
    });
    const [analisisSeleccionadoId, setAnalisisSeleccionadoId] = useState(null);
    const [descargandoAnalisisId, setDescargandoAnalisisId] = useState(null);
    const [ultimaDescargaAnalisisId, setUltimaDescargaAnalisisId] = useState(null);
    const [errorDescarga, setErrorDescarga] = useState("");
    const [avisoDescargaOk, setAvisoDescargaOk] = useState("");
    const [modalReanalisisAbierto, setModalReanalisisAbierto] = useState(
        () => searchParams.get("reanalizar") === "1"
    );
    const [avisoReanalisisOk, setAvisoReanalisisOk] = useState("");

    useEffect(() => {
        if (!token || !estudioId) return;
        const controller = new AbortController();

        Promise.allSettled([
            obtenerResultadoEstudioRequest({ token, estudioId, signal: controller.signal }),
            obtenerHistorialAnalisisRequest({ token, estudioId, signal: controller.signal }),
        ]).then(([resResultado, resHistorial]) => {
            if (controller.signal.aborted) return;

            const datosRes = resResultado.status === "fulfilled" ? resResultado.value : null;
            const datosHist = resHistorial.status === "fulfilled" ? resHistorial.value : null;

            if (datosRes) {
                setEstadoCarga({
                    clave: claveActual,
                    datos: datosRes,
                    historialApi: datosHist,
                    error: null,
                });
                setAnalisisSeleccionadoId(null);
                // El backend marca los avisos de este estudio como leidos; refrescamos la campana
                window.dispatchEvent(new Event("avisos:actualizar"));
                return;
            }

            // Si hay un reanalisis en curso (/resultado -> 409) pero existe historial previo, mostramos la vista de reanalisis en curso
            if (
                datosHist &&
                Array.isArray(datosHist.historial_analisis) &&
                datosHist.historial_analisis.some((a) => a.resultado !== null)
            ) {
                setEstadoCarga({
                    clave: claveActual,
                    datos: null,
                    historialApi: datosHist,
                    error: null,
                });
                return;
            }

            const err =
                resResultado.status === "rejected"
                    ? resResultado.reason
                    : resHistorial.status === "rejected"
                        ? resHistorial.reason
                        : new Error("No se pudo cargar el resultado.");
            if (err?.name === "AbortError") return;
            setEstadoCarga({
                clave: claveActual,
                datos: null,
                historialApi: null,
                error: {
                    mensaje: err.message,
                    code: err.code,
                    status: err.status,
                    retryable: Boolean(err.retryable),
                },
            });
        });

        return () => controller.abort();
    }, [token, estudioId, claveActual]);

    const cargando = Boolean(token && estudioId) && estadoCarga.clave !== claveActual;
    const datos = estadoCarga.clave === claveActual ? estadoCarga.datos : null;
    const historialApi = estadoCarga.clave === claveActual ? estadoCarga.historialApi : null;
    const error = estadoCarga.clave === claveActual ? estadoCarga.error : null;

    const historial = datos?.historial_resultados || [];
    const historialAnalisis = historialApi?.historial_analisis || [];
    const enReanalisisCurso = !datos && Boolean(historialApi) && historialAnalisis.length > 0;
    const puedeReanalizar = Boolean(esMedico && historialApi?.puede_solicitar_reanalisis);
    const resultadoVisible =
        (analisisSeleccionadoId
            ? historial.find((h) => h.analisis_id === analisisSeleccionadoId)
            : null) || datos?.resultado_actual;

    const destinoVolver = rutaVolverPorRol(rol);

    function abrirModalReanalisis() {
        setAvisoReanalisisOk("");
        setModalReanalisisAbierto(true);
    }

    function cerrarModalReanalisis() {
        setModalReanalisisAbierto(false);
        if (searchParams.has("reanalizar")) {
            const next = new URLSearchParams(searchParams);
            next.delete("reanalizar");
            setSearchParams(next, { replace: true });
        }
    }

    function handleReanalisisCreado(resp) {
        cerrarModalReanalisis();
        const simbolos = (resp.nuevos_genes || []).map((g) => g.simbolo).join(", ");
        setAvisoReanalisisOk(
            `Reanálisis #${resp.analisis_id} enviado a bioinformática sobre ${simbolos}. ` +
            "El estudio pasó a 'En análisis por bioinformática' sin requerir nueva muestra."
        );
        window.dispatchEvent(new Event("avisos:actualizar"));
        setRecargaId((n) => n + 1);
    }

    async function handleDescargarPdf(analisisIdOpcional = null) {
        if (!token || !estudioId) return;
        const claveDescarga = analisisIdOpcional ?? "actual";
        setDescargandoAnalisisId(claveDescarga);
        setUltimaDescargaAnalisisId(analisisIdOpcional);
        setErrorDescarga("");
        setAvisoDescargaOk("");
        try {
            const nombreArchivo = await descargarResultadoPdfRequest({
                token,
                estudioId,
                analisisId: analisisIdOpcional,
            });
            setAvisoDescargaOk(`Archivo descargado: ${nombreArchivo}`);
        } catch (err) {
            setErrorDescarga(err.message || "No se pudo descargar el PDF del resultado.");
        } finally {
            setDescargandoAnalisisId(null);
        }
    }

    const estiloDiag =
        ESTILO_DIAGNOSTICO[resultadoVisible?.diagnostico] || ESTILO_DIAGNOSTICO.negativo;
    const fechaVus =
        resultadoVisible?.fecha_proximo_estudio || datos?.fecha_reevaluacion_vus || null;

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <Link
                        to={destinoVolver.to}
                        className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#0B4F8A] hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A]"
                    >
                        ← {destinoVolver.label}
                    </Link>
                    <p className="mt-2 text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                        Informe genómico · Estudio #{estudioId}
                        {(datos?.patologia_sospechada?.nombre ||
                            historialApi?.patologia_sospechada?.nombre) && (
                            <span>
                                {" "}·{" "}
                                {datos?.patologia_sospechada?.nombre ||
                                    historialApi?.patologia_sospechada?.nombre}
                            </span>
                        )}
                    </p>
                    <h1 className="font-titulo mt-0.5 text-2xl font-semibold text-slate-900 sm:text-3xl">
                        {enReanalisisCurso
                            ? "Historial de análisis y reanálisis en curso"
                            : "Resultado del estudio de exoma"}
                    </h1>
                </div>

                {datos && resultadoVisible && (
                    <div className="flex flex-wrap items-center gap-2.5">
                        {puedeReanalizar && (
                            <button
                                type="button"
                                onClick={abrirModalReanalisis}
                                className="inline-flex items-center gap-2 rounded-xl border border-[#0B4F8A] bg-white px-4 py-2.5 text-sm font-semibold text-[#0B4F8A] shadow-xs transition hover:bg-[#EAF2FA] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] focus-visible:ring-offset-2"
                            >
                                <svg
                                    viewBox="0 0 24 24"
                                    className="h-4 w-4 shrink-0"
                                    fill="none"
                                    stroke="currentColor"
                                    strokeWidth="2"
                                    aria-hidden="true"
                                >
                                    <polyline points="23 4 23 10 17 10" />
                                    <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                                </svg>
                                Solicitar reanálisis
                            </button>
                        )}
                        <button
                            type="button"
                            onClick={() =>
                                handleDescargarPdf(
                                    analisisSeleccionadoId &&
                                        analisisSeleccionadoId !== datos.resultado_actual?.analisis_id
                                        ? analisisSeleccionadoId
                                        : null
                                )
                            }
                            disabled={descargandoAnalisisId !== null}
                            aria-busy={descargandoAnalisisId !== null}
                            className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-[#0B4F8A] to-[#0E7490] px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:from-[#093E6D] hover:to-[#0B5E75] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] focus-visible:ring-offset-2 disabled:opacity-50"
                        >
                            <svg
                                viewBox="0 0 24 24"
                                className="h-4 w-4 shrink-0"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="2"
                                aria-hidden="true"
                            >
                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                                <polyline points="7 10 12 15 17 10" />
                                <line x1="12" y1="15" x2="12" y2="3" />
                            </svg>
                            {descargandoAnalisisId !== null
                                ? "Descargando PDF..."
                                : "Descargar resultado en PDF"}
                        </button>
                    </div>
                )}
            </div>

            {avisoReanalisisOk && (
                <div
                    role="status"
                    aria-live="polite"
                    className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs font-medium text-emerald-900"
                >
                    <span>{avisoReanalisisOk}</span>
                    <button
                        type="button"
                        onClick={() => setAvisoReanalisisOk("")}
                        className="font-semibold underline"
                    >
                        Cerrar
                    </button>
                </div>
            )}

            {avisoDescargaOk && (
                <div
                    role="status"
                    aria-live="polite"
                    className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs font-medium text-emerald-800"
                >
                    <span>{avisoDescargaOk}</span>
                    <button
                        type="button"
                        onClick={() => setAvisoDescargaOk("")}
                        className="font-semibold underline"
                    >
                        Cerrar
                    </button>
                </div>
            )}

            {errorDescarga && (
                <div
                    role="alert"
                    className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-medium text-red-700"
                >
                    <span>{errorDescarga}</span>
                    <div className="flex items-center gap-3">
                        <button
                            type="button"
                            onClick={() => handleDescargarPdf(ultimaDescargaAnalisisId)}
                            className="font-semibold underline"
                        >
                            Reintentar
                        </button>
                        <button
                            type="button"
                            onClick={() => setErrorDescarga("")}
                            className="font-semibold underline"
                        >
                            Cerrar
                        </button>
                    </div>
                </div>
            )}

            {cargando ? (
                <div
                    role="status"
                    aria-live="polite"
                    className="tarjeta-cristal flex items-center gap-3 p-8 text-sm text-slate-600"
                >
                    <span
                        aria-hidden="true"
                        className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-[#0B4F8A] border-t-transparent"
                    />
                    Cargando resultado del estudio #{estudioId}...
                </div>
            ) : error ? (
                <section
                    role="alert"
                    className={`rounded-2xl border p-6 shadow-xs ${
                        error.status === 403
                            ? "border-red-200 bg-red-50/90 text-red-900"
                            : error.status === 409
                                ? "border-amber-200 bg-amber-50/90 text-amber-950"
                                : "border-slate-200 bg-white text-slate-800"
                    }`}
                >
                    <h2 className="text-base font-semibold">
                        {error.code === "FORBIDDEN_RESULTADO_GENETICO" || error.status === 403
                            ? "Acceso restringido a datos genéticos"
                            : error.code === "RESULTADO_AUN_NO_DISPONIBLE" || error.status === 409
                                ? "Resultado aún no disponible"
                                : error.status === 404
                                    ? "Estudio no encontrado"
                                    : "No se pudo cargar el resultado"}
                    </h2>
                    <p className="mt-1.5 text-sm opacity-90">{error.mensaje}</p>
                    <div className="mt-4 flex flex-wrap gap-3">
                        <Link
                            to={destinoVolver.to}
                            className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                        >
                            {destinoVolver.label}
                        </Link>
                        {error.retryable && (
                            <button
                                type="button"
                                onClick={() => setRecargaId((n) => n + 1)}
                                className="rounded-xl bg-[#0B4F8A] px-4 py-2 text-xs font-semibold text-white hover:bg-[#093E6D]"
                            >
                                Reintentar
                            </button>
                        )}
                    </div>
                </section>
            ) : enReanalisisCurso ? (
                <div className="space-y-6">
                    <section
                        aria-label="Reanálisis en curso"
                        className="rounded-2xl border border-cyan-200 bg-cyan-50/85 p-5 text-slate-900 shadow-xs"
                    >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                                <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                                    Reanálisis en curso · Exoma reutilizado
                                </p>
                                <h2 className="mt-0.5 text-lg font-bold text-slate-900">
                                    El equipo de bioinformática está evaluando los nuevos genes
                                </h2>
                                <p className="mt-1 text-xs text-slate-700">
                                    Se utilizan los datos crudos ya secuenciados sin nueva muestra. Mientras finaliza el reanálisis, el historial de resultados anteriores sigue disponible para consulta y descarga.
                                </p>
                            </div>
                            <span className="rounded-full border border-cyan-300 bg-white px-3 py-1 text-xs font-semibold text-[#0B4F8A]">
                                {historialApi.estado_estudio}
                            </span>
                        </div>
                    </section>

                    <section
                        aria-label="Historial de análisis del estudio"
                        className="tarjeta-cristal"
                    >
                        <div className="h-1.5 w-full bg-gradient-to-r from-[#062846] via-[#0B4F8A] to-[#0891B2]" />
                        <div className="p-6">
                            <h2 className="text-base font-semibold text-slate-900">
                                Historial de análisis ({historialAnalisis.length})
                            </h2>
                            <ul className="mt-4 space-y-3">
                                {historialAnalisis.map((item) => {
                                    const res = item.resultado;
                                    const estDiag = res
                                        ? ESTILO_DIAGNOSTICO[res.diagnostico] ||
                                          ESTILO_DIAGNOSTICO.negativo
                                        : null;
                                    return (
                                        <li
                                            key={item.analisis_id}
                                            className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4 text-xs"
                                        >
                                            <div className="space-y-1.5">
                                                <div className="flex flex-wrap items-center gap-2">
                                                    <span className="font-semibold text-slate-900">
                                                        Análisis #{item.analisis_id} (
                                                        {item.tipo === "reanalisis"
                                                            ? "Reanálisis"
                                                            : "Inicial"}
                                                        )
                                                    </span>
                                                    {res ? (
                                                        <span
                                                            className={`rounded-full border px-2.5 py-0.5 text-[10px] font-semibold ${estDiag.badge}`}
                                                        >
                                                            {res.diagnostico.toUpperCase()}
                                                        </span>
                                                    ) : (
                                                        <span className="rounded-full border border-cyan-200 bg-cyan-50 px-2.5 py-0.5 text-[10px] font-semibold text-[#0B4F8A]">
                                                            En análisis
                                                        </span>
                                                    )}
                                                </div>
                                                <div className="flex flex-wrap items-center gap-1.5">
                                                    <span className="text-[11px] text-slate-500">Genes:</span>
                                                    {(item.genes || []).map((sim) => (
                                                        <span
                                                            key={sim}
                                                            className="rounded-md bg-[#EAF2FA] px-2 py-0.5 font-mono text-[11px] font-semibold text-[#0B4F8A]"
                                                        >
                                                            {sim}
                                                        </span>
                                                    ))}
                                                </div>
                                                <p className="text-[11px] text-slate-500">
                                                    Solicitado: {formatearFechaHora(item.created_at)}
                                                    {res?.generado_en && (
                                                        <span>
                                                            {" "}· Emitido: {formatearFechaHora(res.generado_en)}
                                                        </span>
                                                    )}
                                                </p>
                                            </div>
                                            {res && (
                                                <button
                                                    type="button"
                                                    disabled={descargandoAnalisisId !== null}
                                                    onClick={() => handleDescargarPdf(item.analisis_id)}
                                                    className="rounded-xl border border-[#0B4F8A] bg-white px-3.5 py-2 font-semibold text-[#0B4F8A] transition hover:bg-[#EAF2FA] disabled:opacity-50"
                                                >
                                                    {descargandoAnalisisId === item.analisis_id
                                                        ? "Descargando..."
                                                        : "Descargar PDF"}
                                                </button>
                                            )}
                                        </li>
                                    );
                                })}
                            </ul>
                        </div>
                    </section>
                </div>
            ) : datos && resultadoVisible ? (
                <div className="space-y-6">
                    {/* Tarjeta principal de conclusion diagnostica */}
                    <section
                        aria-label="Conclusión diagnóstica"
                        className={`rounded-2xl border p-5 shadow-xs ${estiloDiag.contenedor}`}
                    >
                        <div className="flex flex-wrap items-start justify-between gap-4">
                            <div className="flex items-start gap-3.5">
                                <span
                                    aria-hidden="true"
                                    className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border text-lg font-bold ${estiloDiag.badge}`}
                                >
                                    {estiloDiag.icono}
                                </span>
                                <div>
                                    <p className="text-[11px] font-semibold uppercase tracking-wider opacity-75">
                                        Conclusión diagnóstica
                                    </p>
                                    <h2 className="mt-0.5 text-xl font-bold">
                                        {estiloDiag.etiqueta}
                                    </h2>
                                    <p className="mt-1 text-xs opacity-90">
                                        {estiloDiag.subtitulo}
                                    </p>
                                </div>
                            </div>
                            <span className="rounded-full border border-current/20 bg-white/75 px-3 py-1 text-xs font-semibold text-slate-800">
                                {datos.estado_estudio}
                            </span>
                        </div>

                        {resultadoVisible.diagnostico === "vus" && fechaVus && (
                            <div
                                role="note"
                                className="mt-4 rounded-xl border border-amber-300 bg-white/85 px-4 py-3 text-xs text-amber-950"
                            >
                                <p className="font-semibold">
                                    Recomendación de nuevo estudio / reevaluación VUS programada
                                </p>
                                <p className="mt-1">
                                    Fecha sugerida dentro de un año:{" "}
                                    <strong className="font-mono">
                                        {formatearSoloFecha(fechaVus)}
                                    </strong>{" "}
                                    <span className="text-amber-800">({fechaVus})</span>
                                </p>
                            </div>
                        )}
                    </section>

                    {/* Metadatos del analisis */}
                    <section
                        aria-label="Resumen del análisis"
                        className="grid grid-cols-2 gap-3 sm:grid-cols-4"
                    >
                        <div className="rounded-xl border border-slate-200/90 bg-white/90 p-3.5 shadow-2xs">
                            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                                Resultado
                            </p>
                            <p className="mt-1 text-sm font-semibold text-slate-900">
                                #{resultadoVisible.resultado_id}
                            </p>
                        </div>
                        <div className="rounded-xl border border-slate-200/90 bg-white/90 p-3.5 shadow-2xs">
                            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                                Tipo de análisis
                            </p>
                            <p className="mt-1 text-sm font-semibold text-slate-900">
                                {resultadoVisible.tipo_analisis === "reanalisis"
                                    ? "Reanálisis"
                                    : "Inicial"}
                            </p>
                        </div>
                        <div className="rounded-xl border border-slate-200/90 bg-white/90 p-3.5 shadow-2xs">
                            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                                Fecha de emisión
                            </p>
                            <p className="mt-1 text-sm font-semibold text-slate-900">
                                {formatearFechaHora(resultadoVisible.generado_en)}
                            </p>
                        </div>
                        <div className="rounded-xl border border-slate-200/90 bg-white/90 p-3.5 shadow-2xs">
                            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                                Variantes halladas
                            </p>
                            <p className="mt-1 text-sm font-semibold text-slate-900">
                                {resultadoVisible.variantes?.length || 0}
                            </p>
                        </div>
                    </section>

                    {/* Tabla de variantes encontradas */}
                    <section className="tarjeta-cristal">
                        <div className="h-1.5 w-full bg-gradient-to-r from-[#062846] via-[#0B4F8A] to-[#0891B2]" />
                        <div className="p-6">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                                <div>
                                    <h2 className="text-base font-semibold text-slate-900">
                                        Variantes genéticas informadas
                                    </h2>
                                    <p className="mt-0.5 text-xs text-slate-500">
                                        El diagnóstico es positivo únicamente si al menos una variante es patogénica.
                                    </p>
                                </div>
                                <span className="rounded-full bg-[#EAF2FA] px-2.5 py-0.5 text-xs font-semibold text-[#0B4F8A]">
                                    Análisis #{resultadoVisible.analisis_id}
                                </span>
                            </div>

                            {!resultadoVisible.variantes || resultadoVisible.variantes.length === 0 ? (
                                <p className="mt-5 rounded-xl border border-dashed border-slate-200 bg-white/70 p-6 text-center text-xs text-slate-600">
                                    No se detectaron variantes respecto al genoma de referencia en los genes evaluados.
                                </p>
                            ) : (
                                <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200/80 bg-white">
                                    <table
                                        aria-label="Variantes encontradas en el estudio"
                                        className="w-full border-collapse text-left text-xs"
                                    >
                                        <thead className="border-b border-slate-200 bg-slate-50 text-[11px] font-semibold uppercase tracking-wider text-slate-600">
                                            <tr>
                                                <th scope="col" className="px-4 py-3">Gen</th>
                                                <th scope="col" className="px-4 py-3">Notación</th>
                                                <th scope="col" className="px-4 py-3">ClinVar</th>
                                                <th scope="col" className="px-4 py-3 text-right">
                                                    Clasificación
                                                </th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-slate-100">
                                            {resultadoVisible.variantes.map((v) => {
                                                const badge = BADGE_CLASIFICACION[v.clasificacion] || {
                                                    texto: v.clasificacion,
                                                    clase: "border-slate-200 bg-slate-100 text-slate-700",
                                                };
                                                return (
                                                    <tr key={v.variante_id} className="hover:bg-slate-50/70">
                                                        <td className="px-4 py-3">
                                                            <div className="flex flex-wrap items-center gap-1.5">
                                                                <span className="rounded-md bg-[#EAF2FA] px-2 py-0.5 font-mono font-semibold text-[#0B4F8A]">
                                                                    {v.gen?.simbolo || v.gen_simbolo || "—"}
                                                                </span>
                                                                {v.gen?.es_hallazgo_secundario && (
                                                                    <span className="rounded-full border border-cyan-200 bg-cyan-50 px-2 py-0.5 text-[10px] font-semibold text-[#0B4F8A]">
                                                                        Hallazgo secundario
                                                                    </span>
                                                                )}
                                                            </div>
                                                            {v.gen?.nombre && (
                                                                <p className="mt-0.5 text-[11px] text-slate-500">
                                                                    {v.gen.nombre}
                                                                </p>
                                                            )}
                                                        </td>
                                                        <td className="px-4 py-3 font-mono font-semibold text-slate-900">
                                                            {v.notacion}
                                                        </td>
                                                        <td className="px-4 py-3 font-mono text-slate-600">
                                                            {v.clinvar_id || "—"}
                                                        </td>
                                                        <td className="px-4 py-3 text-right">
                                                            <span
                                                                className={`inline-block rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${badge.clase}`}
                                                            >
                                                                {badge.texto}
                                                            </span>
                                                        </td>
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </div>
                    </section>

                    {/* Historial de analisis si hubo reanalisis */}
                    {historial.length > 1 && (
                        <section
                            aria-label="Historial de análisis del estudio"
                            className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs"
                        >
                            <h2 className="text-sm font-semibold text-slate-900">
                                Historial de análisis ({historial.length})
                            </h2>
                            <p className="mt-0.5 text-xs text-slate-500">
                                Este estudio cuenta con reanálisis. Podés inspeccionar o descargar el PDF de cada edición.
                            </p>
                            <ul className="mt-3 space-y-2.5">
                                {historial.map((item) => {
                                    const esVigente =
                                        item.analisis_id === datos.resultado_actual?.analisis_id;
                                    const estaVisible =
                                        item.analisis_id === resultadoVisible.analisis_id;
                                    const estDiag =
                                        ESTILO_DIAGNOSTICO[item.diagnostico] ||
                                        ESTILO_DIAGNOSTICO.negativo;
                                    return (
                                        <li
                                            key={item.analisis_id}
                                            className={`flex flex-wrap items-center justify-between gap-3 rounded-xl border p-3.5 text-xs ${
                                                estaVisible
                                                    ? "border-[#0B4F8A] bg-[#EAF2FA]/60"
                                                    : "border-slate-200 bg-white"
                                            }`}
                                        >
                                            <div className="space-y-0.5">
                                                <div className="flex flex-wrap items-center gap-2">
                                                    <span className="font-semibold text-slate-900">
                                                        Análisis #{item.analisis_id} (
                                                        {item.tipo_analisis === "reanalisis"
                                                            ? "Reanálisis"
                                                            : "Inicial"}
                                                        )
                                                    </span>
                                                    {esVigente && (
                                                        <span className="rounded-full bg-[#0B4F8A] px-2 py-0.5 text-[10px] font-semibold text-white">
                                                            Vigente
                                                        </span>
                                                    )}
                                                    <span
                                                        className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${estDiag.badge}`}
                                                    >
                                                        {item.diagnostico.toUpperCase()}
                                                    </span>
                                                </div>
                                                <p className="text-[11px] text-slate-500">
                                                    Emitido: {formatearFechaHora(item.generado_en)} ·{" "}
                                                    {item.variantes?.length || 0} variantes
                                                </p>
                                            </div>
                                            <div className="flex flex-wrap items-center gap-2">
                                                {!estaVisible && (
                                                    <button
                                                        type="button"
                                                        onClick={() =>
                                                            setAnalisisSeleccionadoId(
                                                                item.analisis_id
                                                            )
                                                        }
                                                        className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 font-semibold text-slate-700 hover:bg-slate-50"
                                                    >
                                                        Ver detalle
                                                    </button>
                                                )}
                                                <button
                                                    type="button"
                                                    disabled={descargandoAnalisisId !== null}
                                                    onClick={() =>
                                                        handleDescargarPdf(item.analisis_id)
                                                    }
                                                    className="rounded-lg border border-[#0B4F8A] bg-white px-3 py-1.5 font-semibold text-[#0B4F8A] hover:bg-[#EAF2FA] disabled:opacity-50"
                                                >
                                                    {descargandoAnalisisId === item.analisis_id
                                                        ? "Descargando..."
                                                        : "Descargar PDF"}
                                                </button>
                                            </div>
                                        </li>
                                    );
                                })}
                            </ul>
                        </section>
                    )}
                </div>
            ) : null}

            {modalReanalisisAbierto && puedeReanalizar && (
                <ModalReanalisis
                    token={token}
                    estudioId={Number(estudioId)}
                    patologiaActualId={
                        datos?.patologia_sospechada?.id ||
                        historialApi?.patologia_sospechada?.id ||
                        null
                    }
                    genesYaAnalizados={historialApi?.genes_ya_analizados || []}
                    onCerrar={cerrarModalReanalisis}
                    onCreado={handleReanalisisCreado}
                />
            )}
        </div>
    );
}
