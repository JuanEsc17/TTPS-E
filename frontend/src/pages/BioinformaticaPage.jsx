import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
    consultarVariantesEstudioRequest,
    listarBandejaBioinformaticaRequest,
    obtenerDatosCrudosEstudioRequest,
    registrarVariantesAnalisisRequest,
    tomarEstudioBioinformaticaRequest,
} from "../api/bioinformatica";
import { descargarResultadoPdfRequest } from "../api/resultados";

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

const ETIQUETA_ORIGEN = {
    patologia: "Patología",
    manual: "Manual",
    hallazgo_secundario: "Hallazgo secundario",
};

export default function BioinformaticaPage({ sesion }) {
    const token = sesion?.access_token;
    const esBioinformatico = sesion?.usuario?.rol === "bioinformatico";

    const [pendientes, setPendientes] = useState([]);
    const [enCurso, setEnCurso] = useState([]);
    const [cargandoBandeja, setCargandoBandeja] = useState(true);
    const [tomandoId, setTomandoId] = useState(null);

    const [estudioActivo, setEstudioActivo] = useState(null);
    const [datosCrudos, setDatosCrudos] = useState(null);
    const [genSeleccionado, setGenSeleccionado] = useState(null);
    const [genDetalle, setGenDetalle] = useState(null);
    const [filtroNotation, setFiltroNotation] = useState("");
    const [filtroClasificacion, setFiltroClasificacion] = useState("");
    const [variantesGen, setVariantesGen] = useState([]);
    const [fuenteVariantes, setFuenteVariantes] = useState("");
    const [cargandoVariantes, setCargandoVariantes] = useState(false);
    const abortVariantesRef = useRef(null);

    const [seleccionadas, setSeleccionadas] = useState({});
    const [confirmarSinVariantes, setConfirmarSinVariantes] = useState(false);
    const [guardandoAnalisis, setGuardandoAnalisis] = useState(false);
    const [descargandoPdf, setDescargandoPdf] = useState(false);
    const [error, setError] = useState("");
    const [errorVariantes, setErrorVariantes] = useState(null);
    const [resultadoFinal, setResultadoFinal] = useState(null);

    const cargarBandeja = useCallback(async () => {
        if (!token || !esBioinformatico) return;
        setCargandoBandeja(true);
        try {
            const data = await listarBandejaBioinformaticaRequest(token);
            setPendientes(data.estudios || []);
            setEnCurso(data.en_curso || []);
        } catch (err) {
            setError(err.message);
        } finally {
            setCargandoBandeja(false);
        }
    }, [token, esBioinformatico]);

    useEffect(() => {
        if (!token || !esBioinformatico) return;
        let cancelado = false;
        listarBandejaBioinformaticaRequest(token)
            .then((data) => {
                if (cancelado) return;
                setPendientes(data.estudios || []);
                setEnCurso(data.en_curso || []);
            })
            .catch((err) => {
                if (!cancelado) setError(err.message);
            })
            .finally(() => {
                if (!cancelado) setCargandoBandeja(false);
            });
        return () => {
            cancelado = true;
        };
    }, [token, esBioinformatico]);

    useEffect(() => {
        return () => abortVariantesRef.current?.abort();
    }, []);

    const cargarVariantes = useCallback(
        async (estudioId, gen, { q = "", clasificacion = "" } = {}) => {
            if (!token || !estudioId || !gen) return;
            abortVariantesRef.current?.abort();
            const controller = new AbortController();
            abortVariantesRef.current = controller;

            setCargandoVariantes(true);
            setErrorVariantes(null);
            setFuenteVariantes("");
            setGenDetalle(gen);
            try {
                const data = await consultarVariantesEstudioRequest({
                    token,
                    estudioId,
                    genId: gen.gen_id,
                    q,
                    clasificacion,
                    signal: controller.signal,
                });
                if (controller.signal.aborted) return;
                setVariantesGen(data.variantes || []);
                setFuenteVariantes(data.fuente || "");
                setGenDetalle(data.gen || gen);
            } catch (err) {
                if (err?.name === "AbortError") return;
                setVariantesGen([]);
                setFuenteVariantes("");
                setErrorVariantes({
                    mensaje: err.message,
                    retryable: Boolean(err.retryable),
                    estudioId,
                    gen,
                });
            } finally {
                if (abortVariantesRef.current === controller) {
                    setCargandoVariantes(false);
                }
            }
        },
        [token]
    );

    const abrirEspacioTrabajo = useCallback(
        async (estudioData) => {
            abortVariantesRef.current?.abort();
            setEstudioActivo(estudioData);
            setSeleccionadas({});
            setConfirmarSinVariantes(false);
            setVariantesGen([]);
            setFuenteVariantes("");
            setGenDetalle(null);
            setFiltroNotation("");
            setFiltroClasificacion("");
            setErrorVariantes(null);
            setResultadoFinal(null);
            setDatosCrudos(null);

            const primerGen = estudioData.genes?.[0] || null;
            setGenSeleccionado(primerGen);

            try {
                const crudos = await obtenerDatosCrudosEstudioRequest({
                    token,
                    estudioId: estudioData.estudio_id,
                });
                setDatosCrudos(crudos);
            } catch {
                // Opcional para previsualizacion si no hay archivo fisico en disco
            }

            if (primerGen) {
                await cargarVariantes(estudioData.estudio_id, primerGen, {
                    q: "",
                    clasificacion: "",
                });
            }
        },
        [token, cargarVariantes]
    );

    async function handleTomarEstudio(estudio) {
        setError("");
        setResultadoFinal(null);
        setTomandoId(estudio.estudio_id);
        try {
            const tomado = await tomarEstudioBioinformaticaRequest({
                token,
                estudioId: estudio.estudio_id,
            });
            await cargarBandeja();
            await abrirEspacioTrabajo({
                ...estudio,
                ...tomado,
                estado: tomado.estado_estudio,
            });
        } catch (err) {
            setError(err.message);
            await cargarBandeja();
        } finally {
            setTomandoId(null);
        }
    }

    function toggleVariante(variante, genSimbolo) {
        setConfirmarSinVariantes(false);
        setSeleccionadas((prev) => {
            const copia = { ...prev };
            if (copia[variante.variante_id]) {
                delete copia[variante.variante_id];
            } else {
                copia[variante.variante_id] = { ...variante, gen_simbolo: genSimbolo };
            }
            return copia;
        });
    }

    const listaSeleccionadas = useMemo(() => Object.values(seleccionadas), [seleccionadas]);

    const conclusionPreliminar = useMemo(() => {
        if (listaSeleccionadas.some((v) => v.clasificacion === "patogenica")) {
            return {
                texto: "POSITIVO (variante patogénica seleccionada)",
                clase: "border-red-200 bg-red-50 text-red-800",
            };
        }
        if (listaSeleccionadas.some((v) => v.clasificacion === "vus")) {
            return {
                texto: "VUS (se programará reevaluación dentro de 1 año)",
                clase: "border-amber-200 bg-amber-50 text-amber-900",
            };
        }
        return {
            texto: "NEGATIVO (sin variantes patogénicas ni VUS)",
            clase: "border-emerald-200 bg-emerald-50 text-emerald-800",
        };
    }, [listaSeleccionadas]);

    async function handleRegistrarAnalisis(e) {
        e.preventDefault();
        if (!estudioActivo) return;
        setError("");

        const ids = listaSeleccionadas.map((v) => v.variante_id);
        if (ids.length === 0 && !confirmarSinVariantes) {
            setError("Seleccioná al menos una variante o confirmá que no se encontraron variantes.");
            return;
        }

        setGuardandoAnalisis(true);
        try {
            const resp = await registrarVariantesAnalisisRequest({
                token,
                estudioId: estudioActivo.estudio_id,
                variantesIds: ids,
            });
            setResultadoFinal(resp);
            setEstudioActivo(null);
            setDatosCrudos(null);
            setSeleccionadas({});
            await cargarBandeja();
        } catch (err) {
            setError(err.message);
        } finally {
            setGuardandoAnalisis(false);
        }
    }

    async function handleDescargarResultadoFinal() {
        if (!token || !resultadoFinal?.estudio_id) return;
        setDescargandoPdf(true);
        setError("");
        try {
            await descargarResultadoPdfRequest({
                token,
                estudioId: resultadoFinal.estudio_id,
            });
        } catch (err) {
            setError(err.message);
        } finally {
            setDescargandoPdf(false);
        }
    }

    if (!esBioinformatico) {
        return (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
                Esta sección es exclusiva para el equipo de Bioinformática.
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                        Bioinformática · Variantes y clasificación
                    </p>
                    <h1 className="font-titulo mt-1 text-2xl font-semibold text-slate-900 sm:text-3xl">
                        Análisis de estudios de exoma
                    </h1>
                    <p className="mt-1 text-sm text-slate-600">
                        Los casos de Pompe urgente aparecen primero en la cola. Tomá un estudio, consultá variantes por gen y cargá el resultado.
                    </p>
                </div>
                <button
                    type="button"
                    onClick={cargarBandeja}
                    disabled={cargandoBandeja}
                    className="rounded-xl border border-[#0B4F8A] bg-white px-4 py-2 text-xs font-semibold text-[#0B4F8A] transition hover:bg-[#EAF2FA] disabled:opacity-50"
                >
                    {cargandoBandeja ? "Actualizando..." : "Actualizar bandeja"}
                </button>
            </div>

            {error && (
                <div
                    role="alert"
                    className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-medium text-red-700"
                >
                    {error}
                </div>
            )}

            {resultadoFinal && (
                <div
                    role="status"
                    className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-xs text-emerald-900"
                >
                    <div>
                        <p className="text-sm font-semibold">
                            Resultado informado · Estudio #{resultadoFinal.estudio_id} ({resultadoFinal.estado_estudio})
                        </p>
                        <p className="mt-1">
                            Diagnóstico: <strong className="uppercase">{resultadoFinal.resultado?.diagnostico}</strong> · Variantes registradas: {resultadoFinal.variantes_registradas?.length || 0} · Se notificó al paciente y al médico tratante.
                        </p>
                        {resultadoFinal.resultado?.fecha_proximo_estudio && (
                            <p className="mt-1 font-medium text-amber-900">
                                Reevaluación anual por VUS programada para: {resultadoFinal.resultado.fecha_proximo_estudio}
                            </p>
                        )}
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                        <Link
                            to={`/estudios/${resultadoFinal.estudio_id}/resultado`}
                            className="rounded-xl bg-[#0B4F8A] px-3.5 py-2 font-semibold text-white transition hover:bg-[#093E6D]"
                        >
                            Ver resultado
                        </Link>
                        <button
                            type="button"
                            disabled={descargandoPdf}
                            onClick={handleDescargarResultadoFinal}
                            className="rounded-xl border border-emerald-700 bg-white px-3.5 py-2 font-semibold text-emerald-800 transition hover:bg-emerald-100 disabled:opacity-50"
                        >
                            {descargandoPdf ? "Descargando..." : "Descargar PDF"}
                        </button>
                    </div>
                </div>
            )}

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                <aside className="space-y-5 lg:col-span-4" aria-label="Bandeja de estudios">
                    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
                        <div className="flex items-center justify-between">
                            <h2 className="text-sm font-semibold text-slate-900">
                                En análisis por bioinformática
                            </h2>
                            <span className="rounded-full bg-[#EAF2FA] px-2.5 py-0.5 text-[11px] font-semibold text-[#0B4F8A]">
                                {pendientes.length}
                            </span>
                        </div>

                        {cargandoBandeja ? (
                            <p className="mt-4 text-xs text-slate-500">Cargando bandeja...</p>
                        ) : pendientes.length === 0 ? (
                            <p className="mt-4 rounded-xl border border-dashed border-slate-200 p-4 text-xs text-slate-500">
                                No hay estudios disponibles en espera.
                            </p>
                        ) : (
                            <ul className="mt-3 space-y-3">
                                {pendientes.map((est) => (
                                    <li
                                        key={est.estudio_id}
                                        className={`rounded-xl border p-3.5 ${
                                            est.es_pompe_urgente
                                                ? "border-red-200 bg-red-50/40"
                                                : "border-slate-200 bg-white"
                                        }`}
                                    >
                                        <div className="flex items-center justify-between gap-2">
                                            <span className="text-sm font-semibold text-slate-900">
                                                Estudio #{est.estudio_id}
                                            </span>
                                            {est.es_pompe_urgente && (
                                                <span className="rounded-full border border-red-200 bg-red-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-red-700">
                                                    Pompe urgente
                                                </span>
                                            )}
                                        </div>
                                        <p className="mt-1 text-xs font-medium text-slate-700">
                                            {est.patologia_nombre} · {est.tipo_analisis === "reanalisis" ? "Reanálisis" : "Inicial"}
                                        </p>
                                        <p className="mt-0.5 text-[11px] text-slate-500">
                                            Paciente: {est.paciente?.nombre || `#${est.paciente?.id}`}
                                        </p>
                                        <div className="mt-2 flex flex-wrap gap-1">
                                            {(est.genes || []).map((g) => (
                                                <span
                                                    key={g.gen_id}
                                                    className="rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] font-medium text-slate-700"
                                                >
                                                    {g.simbolo}
                                                </span>
                                            ))}
                                        </div>
                                        <button
                                            type="button"
                                            disabled={tomandoId === est.estudio_id}
                                            onClick={() => handleTomarEstudio(est)}
                                            className="mt-3 w-full rounded-xl bg-[#0B4F8A] px-3 py-2 text-xs font-semibold text-white transition hover:bg-[#093E6D] disabled:opacity-50"
                                        >
                                            {tomandoId === est.estudio_id ? "Tomando estudio..." : "Tomar estudio"}
                                        </button>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </section>

                    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
                        <div className="flex items-center justify-between">
                            <h2 className="text-sm font-semibold text-slate-900">
                                En análisis de un bioinformático
                            </h2>
                            <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-semibold text-slate-700">
                                {enCurso.length}
                            </span>
                        </div>
                        {enCurso.length === 0 ? (
                            <p className="mt-3 text-xs text-slate-500">Sin estudios tomados actualmente.</p>
                        ) : (
                            <ul className="mt-3 space-y-2.5">
                                {enCurso.map((est) => (
                                    <li key={est.estudio_id} className="rounded-xl border border-slate-200 p-3 text-xs">
                                        <div className="flex items-center justify-between gap-2">
                                            <span className="font-semibold text-slate-900">Estudio #{est.estudio_id}</span>
                                            {est.es_pompe_urgente && (
                                                <span className="rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-semibold text-red-700">
                                                    Pompe urgente
                                                </span>
                                            )}
                                        </div>
                                        <p className="mt-1 text-slate-600">
                                            {est.patologia_nombre} ·{" "}
                                            {est.es_mio
                                                ? "Asignado a vos"
                                                : `Asignado a ${est.bioinformatico_nombre || `Bioinformático #${est.bioinformatico_id}`}`}
                                        </p>
                                        {est.es_mio && (
                                            <button
                                                type="button"
                                                onClick={() => abrirEspacioTrabajo(est)}
                                                className="mt-2 w-full rounded-lg border border-[#0B4F8A] bg-[#EAF2FA]/60 px-3 py-1.5 font-semibold text-[#0B4F8A] hover:bg-[#EAF2FA]"
                                            >
                                                Continuar análisis
                                            </button>
                                        )}
                                    </li>
                                ))}
                            </ul>
                        )}
                    </section>
                </aside>

                <section
                    aria-label="Espacio de trabajo del estudio"
                    className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs lg:col-span-8"
                >
                    {!estudioActivo ? (
                        <div className="flex min-h-[22rem] flex-col items-center justify-center text-center">
                            <p className="text-sm font-semibold text-slate-800">
                                Seleccioná o tomá un estudio de la bandeja
                            </p>
                            <p className="mt-1 max-w-md text-xs text-slate-500">
                                Al tomar un estudio pasa a &ldquo;En análisis de un bioinformático&rdquo; de forma exclusiva para que otro integrante no lo tome simultáneamente.
                            </p>
                        </div>
                    ) : (
                        <form onSubmit={handleRegistrarAnalisis} className="space-y-6">
                            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-4">
                                <div>
                                    <div className="flex flex-wrap items-center gap-2">
                                        <h2 className="text-lg font-semibold text-slate-900">
                                            Estudio #{estudioActivo.estudio_id}
                                        </h2>
                                        {estudioActivo.es_pompe_urgente && (
                                            <span className="rounded-full border border-red-200 bg-red-50 px-2.5 py-0.5 text-[11px] font-semibold text-red-700">
                                                Pompe urgente
                                            </span>
                                        )}
                                        <span className="rounded-full bg-cyan-50 px-2.5 py-0.5 text-[11px] font-medium text-[#0B4F8A]">
                                            {estudioActivo.estado || estudioActivo.estado_estudio}
                                        </span>
                                    </div>
                                    <p className="mt-1 text-xs text-slate-600">
                                        {estudioActivo.patologia_nombre} · Paciente: {estudioActivo.paciente?.nombre || `#${estudioActivo.paciente?.id}`}
                                    </p>
                                </div>
                            </div>

                            {datosCrudos && (
                                <details className="rounded-xl border border-slate-200 bg-[#F8FAFC] p-3.5">
                                    <summary className="cursor-pointer text-xs font-semibold text-[#0B4F8A]">
                                        Datos crudos ({datosCrudos.total_bases} bases · {datosCrudos.archivo_path})
                                    </summary>
                                    <pre className="mt-2 max-h-36 overflow-auto rounded-lg bg-white p-2.5 font-mono text-[11px] text-slate-700">
                                        {datosCrudos.preview}
                                    </pre>
                                </details>
                            )}

                            <div>
                                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-700">
                                    1. Seleccioná un gen del estudio para consultar variantes
                                </h3>
                                <div
                                    role="group"
                                    aria-label="Genes del estudio"
                                    className="mt-2.5 flex flex-wrap gap-2"
                                >
                                    {(estudioActivo.genes || []).map((gen) => {
                                        const activo = genSeleccionado?.gen_id === gen.gen_id;
                                        return (
                                            <button
                                                key={gen.gen_id}
                                                type="button"
                                                aria-pressed={activo}
                                                onClick={() => {
                                                    setGenSeleccionado(gen);
                                                    setFiltroNotation("");
                                                    setFiltroClasificacion("");
                                                    cargarVariantes(estudioActivo.estudio_id, gen, {
                                                        q: "",
                                                        clasificacion: "",
                                                    });
                                                }}
                                                className={`inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-xs transition focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] focus-visible:ring-offset-1 ${
                                                    activo
                                                        ? "border-[#0B4F8A] bg-[#0B4F8A] text-white"
                                                        : "border-slate-200 bg-white text-slate-800 hover:border-[#0B4F8A]/50 hover:bg-[#EAF2FA]/50"
                                                }`}
                                            >
                                                <span className="font-mono font-semibold">{gen.simbolo}</span>
                                                <span className={`text-[10px] ${activo ? "text-cyan-100" : "text-slate-500"}`}>
                                                    {ETIQUETA_ORIGEN[gen.origen] || gen.origen}
                                                </span>
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>

                            {genSeleccionado && (
                                <div
                                    aria-busy={cargandoVariantes}
                                    className="space-y-3 rounded-xl border border-slate-200/80 bg-[#F8FAFC] p-4"
                                >
                                    <div className="flex flex-wrap items-center justify-between gap-2">
                                        <div>
                                            <p className="text-xs font-semibold text-slate-900">
                                                Gen <span className="font-mono">{genDetalle?.simbolo || genSeleccionado.simbolo}</span>
                                                {(genDetalle?.nombre || genSeleccionado.nombre) && (
                                                    <span className="font-normal text-slate-600">
                                                        {" "}· {genDetalle?.nombre || genSeleccionado.nombre}
                                                    </span>
                                                )}
                                            </p>
                                        </div>
                                        {!cargandoVariantes && fuenteVariantes && (
                                            <span
                                                className={`rounded-full border px-2.5 py-0.5 text-[10px] font-semibold ${
                                                    fuenteVariantes === "cache_local_contingencia"
                                                        ? "border-amber-200 bg-amber-50 text-amber-800"
                                                        : "border-slate-200 bg-white text-slate-600"
                                                }`}
                                            >
                                                {variantesGen.length} {variantesGen.length === 1 ? "variante" : "variantes"} ·{" "}
                                                {fuenteVariantes === "cache_local_contingencia"
                                                    ? "Caché local (contingencia)"
                                                    : "API de bioinformática"}
                                            </span>
                                        )}
                                    </div>

                                    <div className="flex flex-wrap items-end gap-3">
                                        <div className="min-w-[11rem] flex-1">
                                            <label htmlFor="buscar-variante-hgvs" className="mb-1 block text-[11px] font-medium text-slate-600">
                                                Filtrar notación en {genSeleccionado.simbolo}
                                            </label>
                                            <input
                                                id="buscar-variante-hgvs"
                                                type="search"
                                                value={filtroNotation}
                                                onChange={(e) => setFiltroNotation(e.target.value)}
                                                onKeyDown={(e) => {
                                                    if (e.key === "Enter") {
                                                        e.preventDefault();
                                                        cargarVariantes(estudioActivo.estudio_id, genSeleccionado, {
                                                            q: filtroNotation,
                                                            clasificacion: filtroClasificacion,
                                                        });
                                                    }
                                                }}
                                                placeholder="Ej: c.1935"
                                                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-900 focus:border-[#0B4F8A] focus:outline-none"
                                            />
                                        </div>
                                        <div className="w-40">
                                            <label htmlFor="filtro-clasificacion" className="mb-1 block text-[11px] font-medium text-slate-600">
                                                Clasificación
                                            </label>
                                            <select
                                                id="filtro-clasificacion"
                                                value={filtroClasificacion}
                                                onChange={(e) => {
                                                    const nueva = e.target.value;
                                                    setFiltroClasificacion(nueva);
                                                    cargarVariantes(estudioActivo.estudio_id, genSeleccionado, {
                                                        q: filtroNotation,
                                                        clasificacion: nueva,
                                                    });
                                                }}
                                                className="w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-900 focus:border-[#0B4F8A] focus:outline-none"
                                            >
                                                <option value="">Todas</option>
                                                <option value="patogenica">Patogénica</option>
                                                <option value="vus">VUS</option>
                                                <option value="benigna">Benigna</option>
                                                <option value="inocua">Inocua</option>
                                            </select>
                                        </div>
                                        <button
                                            type="button"
                                            disabled={cargandoVariantes}
                                            onClick={() =>
                                                cargarVariantes(estudioActivo.estudio_id, genSeleccionado, {
                                                    q: filtroNotation,
                                                    clasificacion: filtroClasificacion,
                                                })
                                            }
                                            className="rounded-lg bg-[#0B4F8A] px-3.5 py-1.5 text-xs font-medium text-white hover:bg-[#093E6D] disabled:opacity-50"
                                        >
                                            {cargandoVariantes ? "Consultando..." : "Buscar variantes"}
                                        </button>
                                    </div>

                                    {fuenteVariantes === "cache_local_contingencia" && (
                                        <div role="status" className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                                            La API de bioinformática no respondió; se muestran variantes cacheadas localmente (contingencia).
                                        </div>
                                    )}

                                    {errorVariantes && (
                                        <div role="alert" className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                                            <span>{errorVariantes.mensaje}</span>
                                            {errorVariantes.retryable && (
                                                <button
                                                    type="button"
                                                    onClick={() =>
                                                        cargarVariantes(errorVariantes.estudioId, errorVariantes.gen, {
                                                            q: filtroNotation,
                                                            clasificacion: filtroClasificacion,
                                                        })
                                                    }
                                                    className="shrink-0 rounded-md border border-red-300 bg-white px-2.5 py-1 font-semibold text-red-700 hover:bg-red-100"
                                                >
                                                    Reintentar consulta de variantes
                                                </button>
                                            )}
                                        </div>
                                    )}

                                    {cargandoVariantes ? (
                                        <div
                                            role="status"
                                            aria-live="polite"
                                            className="flex items-center gap-2 py-2 text-xs text-slate-600"
                                        >
                                            <span
                                                aria-hidden="true"
                                                className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-[#0B4F8A] border-t-transparent"
                                            />
                                            <span>
                                                Consultando base bioinformática de variantes para {genSeleccionado.simbolo}...
                                            </span>
                                        </div>
                                    ) : errorVariantes ? null : variantesGen.length === 0 ? (
                                        <p className="text-xs text-slate-500">No se encontraron variantes para los filtros indicados.</p>
                                    ) : (
                                        <div className="max-h-64 overflow-y-auto rounded-lg border border-slate-200 bg-white">
                                            <table className="w-full border-collapse text-left text-xs">
                                                <thead className="sticky top-0 border-b border-slate-200 bg-slate-50 text-[11px] font-semibold text-slate-600">
                                                    <tr>
                                                        <th scope="col" className="w-10 px-3 py-2">
                                                            <span className="sr-only">Seleccionar</span>
                                                        </th>
                                                        <th scope="col" className="px-2 py-2">Notación</th>
                                                        <th scope="col" className="px-2 py-2">ClinVar</th>
                                                        <th scope="col" className="px-3 py-2 text-right">Clasificación</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="divide-y divide-slate-100">
                                                    {variantesGen.map((v) => {
                                                        const checkboxId = `variante-${v.variante_id}`;
                                                        const marcada = Boolean(seleccionadas[v.variante_id]);
                                                        const badge = BADGE_CLASIFICACION[v.clasificacion] || {
                                                            texto: v.clasificacion,
                                                            clase: "border-slate-200 bg-slate-100 text-slate-700",
                                                        };
                                                        return (
                                                            <tr
                                                                key={v.variante_id}
                                                                className={marcada ? "bg-[#EAF2FA]/50" : "hover:bg-slate-50"}
                                                            >
                                                                <td className="px-3 py-2">
                                                                    <input
                                                                        id={checkboxId}
                                                                        type="checkbox"
                                                                        aria-label={`Seleccionar variante ${v.notacion} (${badge.texto})`}
                                                                        checked={marcada}
                                                                        onChange={() => toggleVariante(v, genSeleccionado.simbolo)}
                                                                        className="h-4 w-4 cursor-pointer rounded border-slate-300 text-[#0B4F8A] focus:ring-[#0B4F8A]"
                                                                    />
                                                                </td>
                                                                <td className="px-2 py-2 font-mono font-semibold text-slate-900">
                                                                    <label htmlFor={checkboxId} className="block cursor-pointer">
                                                                        {v.notacion}
                                                                    </label>
                                                                </td>
                                                                <td className="px-2 py-2 font-mono text-[11px] text-slate-500">
                                                                    {v.clinvar_id || "—"}
                                                                </td>
                                                                <td className="px-3 py-2 text-right">
                                                                    <span className={`inline-block rounded-full border px-2.5 py-0.5 text-[10px] font-semibold ${badge.clase}`}>
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
                            )}

                            <div className="space-y-3 border-t border-slate-100 pt-4">
                                <div className="flex items-center justify-between">
                                    <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-700">
                                        2. Variantes encontradas ({listaSeleccionadas.length})
                                    </h3>
                                </div>

                                {listaSeleccionadas.length > 0 ? (
                                    <ul className="flex flex-wrap gap-2">
                                        {listaSeleccionadas.map((v) => {
                                            const badge = BADGE_CLASIFICACION[v.clasificacion] || BADGE_CLASIFICACION.inocua;
                                            return (
                                                <li
                                                    key={v.variante_id}
                                                    className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs"
                                                >
                                                    <span className="font-mono font-semibold text-slate-900">
                                                        {v.gen_simbolo}:{v.notacion}
                                                    </span>
                                                    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${badge.clase}`}>
                                                        {badge.texto}
                                                    </span>
                                                    <button
                                                        type="button"
                                                        aria-label={`Quitar ${v.notacion}`}
                                                        onClick={() => toggleVariante(v, v.gen_simbolo)}
                                                        className="text-slate-400 hover:text-red-600"
                                                    >
                                                        ×
                                                    </button>
                                                </li>
                                            );
                                        })}
                                    </ul>
                                ) : (
                                    <label className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs text-slate-700">
                                        <input
                                            type="checkbox"
                                            checked={confirmarSinVariantes}
                                            onChange={(e) => setConfirmarSinVariantes(e.target.checked)}
                                            className="h-4 w-4 rounded border-slate-300 text-[#0B4F8A]"
                                        />
                                        Confirmo que no se detectaron variantes respecto al genoma de referencia en los genes evaluados.
                                    </label>
                                )}

                                <div className={`rounded-xl border px-3.5 py-2.5 text-xs font-medium ${conclusionPreliminar.clase}`}>
                                    Conclusión preliminar: <strong>{conclusionPreliminar.texto}</strong>
                                </div>

                                <div className="flex justify-end">
                                    <button
                                        type="submit"
                                        disabled={guardandoAnalisis}
                                        className="inline-flex items-center justify-center rounded-xl bg-[#0B4F8A] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#093E6D] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] focus-visible:ring-offset-2 disabled:opacity-50"
                                    >
                                        {guardandoAnalisis ? "Generando informe PDF del resultado..." : "Confirmar análisis y cargar resultado"}
                                    </button>
                                </div>
                            </div>
                        </form>
                    )}
                </section>
            </div>
        </div>
    );
}
