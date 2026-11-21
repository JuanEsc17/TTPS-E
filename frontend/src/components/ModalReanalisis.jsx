import { useEffect, useMemo, useRef, useState } from "react";
import { listarPatologiasRequest } from "../api/patologias";
import {
    buscarGenesCatalogoRequest,
    solicitarReanalisisRequest,
} from "../api/resultados";

const PATRON_SIMBOLO_GEN = /^[A-Z0-9][A-Z0-9._-]{0,29}$/;

export default function ModalReanalisis({
    token,
    estudioId,
    patologiaActualId = null,
    genesYaAnalizados = [],
    onCerrar,
    onCreado,
}) {
    const [patologias, setPatologias] = useState([]);
    const [patologiaId, setPatologiaId] = useState("");
    const [busquedaGen, setBusquedaGen] = useState("");
    const [sugerencias, setSugerencias] = useState([]);
    const [buscandoGenes, setBuscandoGenes] = useState(false);
    const [genesSeleccionados, setGenesSeleccionados] = useState([]);
    const [avisoInput, setAvisoInput] = useState("");
    const [enviando, setEnviando] = useState(false);
    const [errorEnvio, setErrorEnvio] = useState("");

    const inputGenRef = useRef(null);

    const setYaAnalizados = useMemo(
        () => new Set(genesYaAnalizados.map((s) => String(s).toUpperCase())),
        [genesYaAnalizados]
    );
    const setSeleccionados = useMemo(
        () => new Set(genesSeleccionados),
        [genesSeleccionados]
    );

    useEffect(() => {
        inputGenRef.current?.focus();
        const onKeyDown = (e) => {
            if (e.key === "Escape" && !enviando) onCerrar();
        };
        document.addEventListener("keydown", onKeyDown);
        return () => document.removeEventListener("keydown", onKeyDown);
    }, [enviando, onCerrar]);

    useEffect(() => {
        if (!token) return;
        let cancelado = false;
        listarPatologiasRequest(token)
            .then((lista) => {
                if (!cancelado && Array.isArray(lista)) setPatologias(lista);
            })
            .catch(() => {
                // La seleccion de patologia es opcional; no bloqueamos el reanalisis manual
            });
        return () => {
            cancelado = true;
        };
    }, [token]);

    useEffect(() => {
        if (!token) return;
        const controller = new AbortController();
        const timer = setTimeout(() => {
            setBuscandoGenes(true);
            buscarGenesCatalogoRequest({
                token,
                q: busquedaGen,
                limite: 16,
                signal: controller.signal,
            })
                .then((lista) => {
                    if (!controller.signal.aborted) setSugerencias(lista);
                })
                .catch(() => {
                    if (!controller.signal.aborted) setSugerencias([]);
                })
                .finally(() => {
                    if (!controller.signal.aborted) setBuscandoGenes(false);
                });
        }, busquedaGen.trim() ? 220 : 0);

        return () => {
            clearTimeout(timer);
            controller.abort();
        };
    }, [token, busquedaGen]);

    const patologiaSeleccionada = useMemo(
        () => patologias.find((p) => String(p.patologia_id) === String(patologiaId)) || null,
        [patologias, patologiaId]
    );

    const genesNuevosDePatologia = useMemo(() => {
        if (!patologiaSeleccionada?.genes) return [];
        return patologiaSeleccionada.genes
            .map((g) => String(g.simbolo || "").trim().toUpperCase())
            .filter((s) => s && !setYaAnalizados.has(s) && !setSeleccionados.has(s));
    }, [patologiaSeleccionada, setYaAnalizados, setSeleccionados]);

    function agregarSimbolo(raw) {
        const simbolo = String(raw || "").trim().toUpperCase();
        setAvisoInput("");
        setErrorEnvio("");
        if (!simbolo) return;
        if (!PATRON_SIMBOLO_GEN.test(simbolo)) {
            setAvisoInput(`"${simbolo}" no es un símbolo de gen válido (ej. IDUA, GBA, SMPD1).`);
            return;
        }
        if (setYaAnalizados.has(simbolo)) {
            setAvisoInput(`${simbolo} ya fue analizado previamente en este estudio.`);
            return;
        }
        if (setSeleccionados.has(simbolo)) {
            setAvisoInput(`${simbolo} ya está incluido en el reanálisis.`);
            return;
        }
        setGenesSeleccionados((prev) => [...prev, simbolo]);
        setBusquedaGen("");
    }

    function quitarSimbolo(simbolo) {
        setGenesSeleccionados((prev) => prev.filter((s) => s !== simbolo));
        setAvisoInput("");
    }

    function agregarGenesDePatologia() {
        if (genesNuevosDePatologia.length === 0) return;
        setGenesSeleccionados((prev) => [...prev, ...genesNuevosDePatologia]);
        setAvisoInput("");
        setErrorEnvio("");
    }

    function handleKeyDownInput(e) {
        if (e.key === "Enter") {
            e.preventDefault();
            agregarSimbolo(busquedaGen);
        }
    }

    async function handleConfirmar(e) {
        e.preventDefault();
        if (genesSeleccionados.length === 0) {
            setAvisoInput("Agregá al menos un gen nuevo que no haya sido analizado todavía.");
            return;
        }
        setEnviando(true);
        setErrorEnvio("");
        try {
            const respuesta = await solicitarReanalisisRequest({
                token,
                estudioId,
                nuevosGenesSimbolos: genesSeleccionados,
                nuevaPatologiaSospechadaId: patologiaId ? Number(patologiaId) : null,
            });
            onCreado(respuesta);
        } catch (err) {
            setErrorEnvio(err.message || "No se pudo registrar la solicitud de reanálisis.");
        } finally {
            setEnviando(false);
        }
    }

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            role="dialog"
            aria-modal="true"
            aria-labelledby="titulo-modal-reanalisis"
        >
            <div
                className="fixed inset-0 bg-slate-900/45 backdrop-blur-xs"
                onClick={() => !enviando && onCerrar()}
            />

            <div className="relative z-10 flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
                <div className="h-1.5 w-full bg-gradient-to-r from-[#062846] via-[#0B4F8A] to-[#0891B2]" />

                <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-6 py-4">
                    <div>
                        <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                            Estudio #{estudioId} · Exoma existente
                        </p>
                        <h2
                            id="titulo-modal-reanalisis"
                            className="font-titulo mt-0.5 text-xl font-semibold text-slate-900"
                        >
                            Solicitar reanálisis de nuevos genes
                        </h2>
                        <p className="mt-1 text-xs text-slate-600">
                            Se reutilizan los datos crudos ya secuenciados. No requiere nueva muestra ni turno de extracción y conserva el historial anterior.
                        </p>
                    </div>
                    <button
                        type="button"
                        onClick={onCerrar}
                        disabled={enviando}
                        aria-label="Cerrar ventana de reanálisis"
                        className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A]"
                    >
                        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
                            <line x1="18" y1="6" x2="6" y2="18" />
                            <line x1="6" y1="6" x2="18" y2="18" />
                        </svg>
                    </button>
                </div>

                <form onSubmit={handleConfirmar} className="flex min-h-0 flex-1 flex-col">
                    <div className="space-y-5 overflow-y-auto px-6 py-5">
                        {/* Genes ya analizados (contexto solo lectura) */}
                        <div className="rounded-xl border border-slate-200/80 bg-slate-50/80 p-3.5">
                            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                                Genes ya analizados en este estudio ({genesYaAnalizados.length})
                            </p>
                            {genesYaAnalizados.length === 0 ? (
                                <p className="mt-1.5 text-xs text-slate-500">Sin genes registrados.</p>
                            ) : (
                                <div className="mt-2 flex flex-wrap gap-1.5">
                                    {genesYaAnalizados.map((simbolo) => (
                                        <span
                                            key={simbolo}
                                            className="rounded-md border border-slate-200 bg-white px-2 py-0.5 font-mono text-xs font-medium text-slate-600"
                                        >
                                            {simbolo}
                                        </span>
                                    ))}
                                </div>
                            )}
                        </div>

                        {/* Nueva patologia sospechada opcional */}
                        <div>
                            <label
                                htmlFor="select-patologia-reanalisis"
                                className="block text-xs font-semibold text-slate-700"
                            >
                                Nueva patología sospechada{" "}
                                <span className="font-normal text-slate-400">(opcional)</span>
                            </label>
                            <select
                                id="select-patologia-reanalisis"
                                value={patologiaId}
                                onChange={(e) => setPatologiaId(e.target.value)}
                                className="campo-clinico mt-1.5"
                            >
                                <option value="">Mantener patología sospechada actual</option>
                                {patologias.map((p) => (
                                    <option key={p.patologia_id} value={p.patologia_id}>
                                        {p.nombre}
                                        {p.patologia_id === patologiaActualId ? " (actual)" : ""}
                                        {p.genes?.length
                                            ? ` · ${p.genes.map((g) => g.simbolo).join(", ")}`
                                            : ""}
                                    </option>
                                ))}
                            </select>

                            {patologiaSeleccionada && (
                                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-cyan-200/80 bg-cyan-50/60 px-3 py-2 text-xs text-[#0B4F8A]">
                                    <span>
                                        {genesNuevosDePatologia.length > 0
                                            ? `Genes nuevos asociados a ${patologiaSeleccionada.nombre}: ${genesNuevosDePatologia.join(", ")}`
                                            : `Los genes registrados de ${patologiaSeleccionada.nombre} ya están analizados o seleccionados.`}
                                    </span>
                                    {genesNuevosDePatologia.length > 0 && (
                                        <button
                                            type="button"
                                            onClick={agregarGenesDePatologia}
                                            className="shrink-0 rounded-lg bg-[#0B4F8A] px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-[#093E6D]"
                                        >
                                            + Agregar genes
                                        </button>
                                    )}
                                </div>
                            )}
                        </div>

                        {/* Buscador y alta de nuevos genes */}
                        <div>
                            <label
                                htmlFor="input-buscar-genes"
                                className="block text-xs font-semibold text-slate-700"
                            >
                                Nuevos genes a analizar
                            </label>
                            <div className="mt-1.5 flex gap-2">
                                <input
                                    ref={inputGenRef}
                                    id="input-buscar-genes"
                                    type="text"
                                    value={busquedaGen}
                                    onChange={(e) => {
                                        setBusquedaGen(e.target.value);
                                        setAvisoInput("");
                                    }}
                                    onKeyDown={handleKeyDownInput}
                                    placeholder="Buscá por símbolo o escribí uno (ej. IDUA, GBA) y presioná Enter"
                                    className="campo-clinico flex-1 font-mono uppercase placeholder:font-sans placeholder:normal-case"
                                />
                                <button
                                    type="button"
                                    onClick={() => agregarSimbolo(busquedaGen)}
                                    disabled={!busquedaGen.trim()}
                                    className="shrink-0 rounded-xl border border-[#0B4F8A] bg-white px-4 py-2 text-xs font-semibold text-[#0B4F8A] transition hover:bg-[#EAF2FA] disabled:opacity-40"
                                >
                                    Agregar
                                </button>
                            </div>

                            {avisoInput && (
                                <p role="status" className="mt-1.5 text-xs font-medium text-amber-800">
                                    {avisoInput}
                                </p>
                            )}

                            {/* Sugerencias del catalogo */}
                            <div className="mt-3">
                                <p className="text-[11px] font-medium text-slate-500">
                                    {buscandoGenes
                                        ? "Buscando en catálogo de genes..."
                                        : "Catálogo disponible (clic para agregar):"}
                                </p>
                                {sugerencias.length > 0 ? (
                                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                                        {sugerencias.map((g) => {
                                            const sim = String(g.simbolo).toUpperCase();
                                            const yaAnalizado = setYaAnalizados.has(sim);
                                            const yaElegido = setSeleccionados.has(sim);
                                            const deshabilitado = yaAnalizado || yaElegido;
                                            return (
                                                <button
                                                    key={sim}
                                                    type="button"
                                                    disabled={deshabilitado}
                                                    onClick={() => agregarSimbolo(sim)}
                                                    title={g.nombre || sim}
                                                    className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-xs font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] ${
                                                        yaAnalizado
                                                            ? "cursor-not-allowed border-slate-200 bg-slate-100 text-slate-400 line-through"
                                                            : yaElegido
                                                                ? "cursor-default border-[#0B4F8A]/30 bg-[#EAF2FA] text-[#0B4F8A]"
                                                                : "border-slate-200 bg-white text-slate-700 hover:border-[#0B4F8A] hover:bg-[#EAF2FA]/60 hover:text-[#0B4F8A]"
                                                    }`}
                                                >
                                                    <span className="font-mono font-semibold">{sim}</span>
                                                    {yaAnalizado ? (
                                                        <span className="text-[10px]">(ya analizado)</span>
                                                    ) : yaElegido ? (
                                                        <span className="text-[10px]">✓</span>
                                                    ) : (
                                                        <span aria-hidden="true">+</span>
                                                    )}
                                                </button>
                                            );
                                        })}
                                    </div>
                                ) : !buscandoGenes ? (
                                    <p className="mt-1 text-[11px] text-slate-400">
                                        Sin coincidencias locales; podés ingresar el símbolo exacto y el sistema lo validará contra bioinformática.
                                    </p>
                                ) : null}
                            </div>
                        </div>

                        {/* Genes seleccionados para el reanalisis */}
                        <div className="rounded-xl border border-[#0B4F8A]/25 bg-[#EAF2FA]/45 p-3.5">
                            <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                                Genes seleccionados para este reanálisis ({genesSeleccionados.length})
                            </p>
                            {genesSeleccionados.length === 0 ? (
                                <p className="mt-1.5 text-xs text-slate-600">
                                    Todavía no seleccionaste ningún gen nuevo.
                                </p>
                            ) : (
                                <div className="mt-2 flex flex-wrap gap-2">
                                    {genesSeleccionados.map((simbolo) => (
                                        <span
                                            key={simbolo}
                                            className="inline-flex items-center gap-1.5 rounded-full bg-[#0B4F8A] px-3 py-1 font-mono text-xs font-semibold text-white"
                                        >
                                            {simbolo}
                                            <button
                                                type="button"
                                                onClick={() => quitarSimbolo(simbolo)}
                                                aria-label={`Quitar gen ${simbolo}`}
                                                className="rounded-full p-0.5 text-cyan-100 hover:bg-white/20 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-white"
                                            >
                                                ×
                                            </button>
                                        </span>
                                    ))}
                                </div>
                            )}
                        </div>

                        {errorEnvio && (
                            <div
                                role="alert"
                                className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-medium text-red-700"
                            >
                                {errorEnvio}
                            </div>
                        )}
                    </div>

                    <div className="flex flex-wrap items-center justify-end gap-2.5 border-t border-slate-100 bg-slate-50/70 px-6 py-4">
                        <button
                            type="button"
                            onClick={onCerrar}
                            disabled={enviando}
                            className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
                        >
                            Cancelar
                        </button>
                        <button
                            type="submit"
                            disabled={enviando || genesSeleccionados.length === 0}
                            aria-busy={enviando}
                            className="rounded-xl bg-gradient-to-r from-[#0B4F8A] to-[#0E7490] px-5 py-2 text-xs font-semibold text-white shadow-sm transition hover:from-[#093E6D] hover:to-[#0B5E75] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] focus-visible:ring-offset-1 disabled:opacity-50"
                        >
                            {enviando
                                ? "Enviando a bioinformática..."
                                : `Confirmar reanálisis (${genesSeleccionados.length})`}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}
