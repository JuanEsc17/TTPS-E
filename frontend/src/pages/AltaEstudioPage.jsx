import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
    altaEstudioRequest,
    buscarGenesManualesRequest,
    listarObrasSocialesRequest,
    obtenerGenesPatologiaRequest,
} from "../api/estudios";
import { listarPacientesRequest, listarPatologiasRequest } from "../api/pacientes";

export default function AltaEstudioPage({ sesion }) {
    const token = sesion?.access_token;

    const [pacientes, setPacientes] = useState([]);
    const [patologias, setPatologias] = useState([]);
    const [obrasSociales, setObrasSociales] = useState([]);
    const [cargando, setCargando] = useState(true);

    const [pacienteId, setPacienteId] = useState("");
    const [patologiaId, setPatologiaId] = useState("");
    const [obraSocialId, setObraSocialId] = useState("");
    const [quiereSecundarios, setQuiereSecundarios] = useState(false);

    // Genes
    const [genesPatologia, setGenesPatologia] = useState([]);
    const [genesPatSeleccionados, setGenesPatSeleccionados] = useState([]);
    const [genesSecundarios, setGenesSecundarios] = useState([]);
    const [cargandoGenes, setCargandoGenes] = useState(false);

    // Busqueda manual de genes
    const [busquedaGen, setBusquedaGen] = useState("");
    const [resultadosGenes, setResultadosGenes] = useState([]);
    const [genesManuales, setGenesManuales] = useState([]);
    const [buscandoGen, setBuscandoGen] = useState(false);

    const [enviando, setEnviando] = useState(false);
    const [error, setError] = useState("");
    const [estudioCreado, setEstudioCreado] = useState(null);

    useEffect(() => {
        if (!token) return;
        setCargando(true);
        Promise.all([
            listarPacientesRequest(token),
            listarPatologiasRequest(token),
            listarObrasSocialesRequest(token).catch(() => []),
        ])
            .then(([pacs, pats, osList]) => {
                setPacientes(pacs || []);
                setPatologias(pats || []);
                setObrasSociales(osList || []);
                if (pacs?.length > 0) {
                    setPacienteId(String(pacs[0].paciente_id));
                    setPatologiaId(String(pacs[0].diagnostico_presuntivo_id || pats?.[0]?.id || ""));
                } else if (pats?.length > 0) {
                    setPatologiaId(String(pats[0].id));
                }
            })
            .catch((err) => setError(err.message))
            .finally(() => setCargando(false));
    }, [token]);

    // Cuando cambia la patologia o el check de hallazgos secundarios, consulta Apigen
    useEffect(() => {
        if (!token || !patologiaId) return;
        setCargandoGenes(true);
        obtenerGenesPatologiaRequest(token, Number(patologiaId), quiereSecundarios)
            .then((res) => {
                const gp = res.genes_patologia || [];
                setGenesPatologia(gp);
                setGenesPatSeleccionados(gp.map((g) => g.simbolo));
                setGenesSecundarios(res.hallazgos_secundarios || []);
            })
            .catch((err) => setError(err.message))
            .finally(() => setCargandoGenes(false));
    }, [token, patologiaId, quiereSecundarios]);

    function handleSeleccionarPaciente(nuevoId) {
        setPacienteId(nuevoId);
        const pac = pacientes.find((p) => String(p.paciente_id) === String(nuevoId));
        if (pac?.diagnostico_presuntivo_id) {
            setPatologiaId(String(pac.diagnostico_presuntivo_id));
        }
    }

    function toggleGenPatologia(simbolo) {
        setGenesPatSeleccionados((prev) =>
            prev.includes(simbolo) ? prev.filter((s) => s !== simbolo) : [...prev, simbolo]
        );
    }

    async function handleBuscarGen() {
        const q = busquedaGen.trim();
        setError("");
        if (q.length < 2) {
            setError("Ingresá al menos 2 letras para buscar un gen.");
            return;
        }
        setBuscandoGen(true);
        try {
            const lista = await buscarGenesManualesRequest(token, q);
            setResultadosGenes(lista || []);
        } catch (err) {
            setError(err.message);
        } finally {
            setBuscandoGen(false);
        }
    }

    function agregarGenManual(simbolo) {
        if (genesManuales.includes(simbolo) || genesPatSeleccionados.includes(simbolo)) return;
        setGenesManuales((prev) => [...prev, simbolo]);
    }

    async function handleSubmit(e) {
        e.preventDefault();
        setError("");

        if (!pacienteId) {
            setError("Seleccioná un paciente registrado.");
            window.scrollTo({ top: 0, behavior: "smooth" });
            return;
        }
        if (!patologiaId) {
            setError("Seleccioná la patología sospechada.");
            window.scrollTo({ top: 0, behavior: "smooth" });
            return;
        }
        if (genesPatSeleccionados.length === 0 && genesManuales.length === 0 && !quiereSecundarios) {
            setError("Debe haber al menos un gen seleccionado para analizar.");
            window.scrollTo({ top: 0, behavior: "smooth" });
            return;
        }

        setEnviando(true);
        try {
            const creado = await altaEstudioRequest(token, {
                paciente_id: Number(pacienteId),
                patologia_sospechada_id: Number(patologiaId),
                quiere_hallazgos_secundarios: quiereSecundarios,
                obra_social_id: obraSocialId ? Number(obraSocialId) : null,
                genes_patologia_simbolos: genesPatSeleccionados,
                genes_manuales_simbolos: genesManuales,
            });
            setEstudioCreado(creado);
        } catch (err) {
            setError(err.message);
            window.scrollTo({ top: 0, behavior: "smooth" });
        } finally {
            setEnviando(false);
        }
    }

    if (estudioCreado) {
        return (
            <section className="tarjeta-cristal">
                <div className="h-1.5 w-full bg-gradient-to-r from-emerald-500 to-[#0891B2]" />
                <div className="space-y-4 p-6">
                    <h1 className="font-titulo text-2xl font-semibold text-slate-900">
                        Estudio #{estudioCreado.estudio_id} dado de alta
                    </h1>
                    <p className="text-sm text-slate-600">
                        Estado inicial: <strong className="text-[#0B4F8A]">{estudioCreado.estado}</strong> ·{" "}
                        Total de genes a secuenciar: <strong>{estudioCreado.cantidad_genes_total}</strong>
                    </p>
                    {estudioCreado.es_pompe_urgente && (
                        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-xs font-semibold text-red-700">
                            Marcado automáticamente como Pompe urgente (paciente menor de 4 meses).
                        </div>
                    )}
                    <div className="flex flex-wrap gap-1.5">
                        {estudioCreado.genes.map((g) => (
                            <span
                                key={g.simbolo}
                                className="rounded-full border border-[#0B4F8A]/25 bg-[#EAF2FA] px-2.5 py-0.5 text-xs font-medium text-[#0B4F8A]"
                            >
                                {g.simbolo} ({g.origen})
                            </span>
                        ))}
                    </div>
                    <div className="flex flex-wrap gap-3 pt-2">
                        <Link
                            to="/medico/estudios"
                            className="rounded-xl bg-[#0B4F8A] px-4 py-2 text-xs font-medium text-white hover:bg-[#093E6D]"
                        >
                            Ver estudios médicos
                        </Link>
                        <button
                            type="button"
                            onClick={() => window.location.reload()}
                            className="rounded-xl border border-slate-300 bg-white/80 px-4 py-2 text-xs font-medium text-slate-700 hover:bg-white"
                        >
                            Solicitar otro estudio
                        </button>
                    </div>
                </div>
            </section>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                        Consulta médica · Escenario E2
                    </p>
                    <h1 className="font-titulo mt-1 text-2xl font-semibold text-slate-900">
                        Solicitar estudio de exoma
                    </h1>
                </div>
                <Link to="/medico/estudios" className="text-xs font-semibold text-[#0B4F8A] hover:underline">
                    ← Volver a estudios
                </Link>
            </div>

            {error && (
                <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-medium text-red-700">
                    {error}
                </div>
            )}

            {cargando ? (
                <p className="text-sm text-slate-500">Cargando pacientes y catálogo...</p>
            ) : (
                <form onSubmit={handleSubmit} noValidate className="space-y-6">
                    <section className="tarjeta-cristal">
                        <div className="h-1.5 w-full bg-gradient-to-r from-[#062846] via-[#0B4F8A] to-[#0891B2]" />
                        <div className="space-y-4 p-6">
                            <h2 className="text-sm font-semibold text-slate-900">
                                1. Paciente, patología y cobertura
                            </h2>
                            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                                <div>
                                    <label className="mb-1 block text-xs font-medium text-slate-700">Paciente</label>
                                    <select
                                        value={pacienteId}
                                        onChange={(e) => handleSeleccionarPaciente(e.target.value)}
                                        className="campo-clinico"
                                    >
                                        {pacientes.length === 0 ? (
                                            <option value="">No hay pacientes registrados</option>
                                        ) : (
                                            pacientes.map((p) => (
                                                <option key={p.paciente_id} value={p.paciente_id}>
                                                    {p.nombre} {p.apellido} (DNI {p.dni})
                                                </option>
                                            ))
                                        )}
                                    </select>
                                </div>
                                <div>
                                    <label className="mb-1 block text-xs font-medium text-slate-700">Patología sospechada</label>
                                    <select
                                        value={patologiaId}
                                        onChange={(e) => setPatologiaId(e.target.value)}
                                        className="campo-clinico"
                                    >
                                        {patologias.map((pat) => (
                                            <option key={pat.id} value={pat.id}>{pat.nombre}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label className="mb-1 block text-xs font-medium text-slate-700">Cobertura / Obra social</label>
                                    <select
                                        value={obraSocialId}
                                        onChange={(e) => setObraSocialId(e.target.value)}
                                        className="campo-clinico"
                                    >
                                        <option value="">Particular (sin obra social)</option>
                                        {obrasSociales.map((os) => (
                                            <option key={os.id} value={os.id}>
                                                {os.nombre} ({os.porcentaje_cobertura}%)
                                            </option>
                                        ))}
                                    </select>
                                </div>
                            </div>
                        </div>
                    </section>

                    <section className="tarjeta-cristal">
                        <div className="space-y-4 p-6">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                                <h2 className="text-sm font-semibold text-slate-900">
                                    2. Genes asociados a la patología y hallazgos secundarios
                                </h2>
                                <label className="flex cursor-pointer items-center gap-2 text-xs font-medium text-slate-700">
                                    <input
                                        type="checkbox"
                                        checked={quiereSecundarios}
                                        onChange={(e) => setQuiereSecundarios(e.target.checked)}
                                        className="h-4 w-4 rounded border-slate-300 text-[#0B4F8A]"
                                    />
                                    Incluir hallazgos secundarios (ACMG)
                                </label>
                            </div>

                            {cargandoGenes ? (
                                <p className="text-xs text-slate-500">Consultando genes en Bioinformática (Apigen)...</p>
                            ) : genesPatologia.length === 0 ? (
                                <p className="rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-2 text-xs text-amber-800">
                                    No se devolvieron genes automáticos para esta patología. Podés agregar genes manualmente abajo.
                                </p>
                            ) : (
                                <div className="flex flex-wrap gap-2">
                                    {genesPatologia.map((g) => {
                                        const activo = genesPatSeleccionados.includes(g.simbolo);
                                        return (
                                            <button
                                                key={g.simbolo}
                                                type="button"
                                                onClick={() => toggleGenPatologia(g.simbolo)}
                                                className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
                                                    activo
                                                        ? "border-[#0B4F8A] bg-[#0B4F8A] text-white"
                                                        : "border-slate-300 bg-white/80 text-slate-600"
                                                }`}
                                            >
                                                {g.simbolo}
                                            </button>
                                        );
                                    })}
                                </div>
                            )}

                            {quiereSecundarios && genesSecundarios.length > 0 && (
                                <p className="rounded-xl border border-cyan-200 bg-cyan-50/70 px-3.5 py-2 text-xs text-[#0B4F8A]">
                                    Se incluirán automáticamente <strong>{genesSecundarios.length}</strong> genes de hallazgos secundarios (ACMG).
                                </p>
                            )}

                            <div className="space-y-3 border-t border-slate-200/70 pt-4">
                                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-600">
                                    Agregar genes adicionales manualmente
                                </h3>
                                <div className="flex gap-2">
                                    <input
                                        type="text"
                                        value={busquedaGen}
                                        onChange={(e) => setBusquedaGen(e.target.value)}
                                        placeholder="Símbolo del gen (ej. GAA, GLA, BRCA)..."
                                        className="campo-clinico"
                                    />
                                    <button
                                        type="button"
                                        onClick={handleBuscarGen}
                                        disabled={buscandoGen}
                                        className="shrink-0 rounded-xl bg-[#0B4F8A] px-4 py-2 text-xs font-medium text-white hover:bg-[#093E6D]"
                                    >
                                        {buscandoGen ? "Buscando..." : "Buscar gen"}
                                    </button>
                                </div>

                                {resultadosGenes.length > 0 && (
                                    <div className="flex flex-wrap gap-1.5">
                                        {resultadosGenes.map((g) => (
                                            <button
                                                key={g.simbolo}
                                                type="button"
                                                onClick={() => agregarGenManual(g.simbolo)}
                                                className="rounded-lg border border-slate-200 bg-white/80 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-[#EAF2FA]"
                                            >
                                                {g.simbolo} +
                                            </button>
                                        ))}
                                    </div>
                                )}

                                {genesManuales.length > 0 && (
                                    <div className="flex flex-wrap gap-2">
                                        {genesManuales.map((sim) => (
                                            <span
                                                key={sim}
                                                className="inline-flex items-center gap-1.5 rounded-full border border-[#0E7490]/40 bg-[#0E7490]/10 px-3 py-1 text-xs font-semibold text-[#0E7490]"
                                            >
                                                {sim} (Manual)
                                                <button
                                                    type="button"
                                                    onClick={() => setGenesManuales((prev) => prev.filter((x) => x !== sim))}
                                                >
                                                    ×
                                                </button>
                                            </span>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    </section>

                    {error && (
                        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-medium text-red-700">
                            {error}
                        </div>
                    )}

                    <div className="flex justify-end">
                        <button
                            type="submit"
                            disabled={enviando}
                            className="rounded-xl bg-gradient-to-r from-[#0B4F8A] to-[#0E7490] px-6 py-3 text-sm font-medium text-white shadow-sm transition hover:from-[#093E6D] hover:to-[#0B5E75] disabled:opacity-50"
                        >
                            {enviando ? "Creando estudio..." : "Confirmar alta de estudio →"}
                        </button>
                    </div>
                </form>
            )}
        </div>
    );
}
