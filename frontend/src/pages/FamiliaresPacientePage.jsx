import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
    actualizarFamiliaresRequest,
    buscarSintomasSnomedRequest,
    obtenerFamiliaresRequest,
    obtenerFamiliogramaSvgRequest,
} from "../api/pacientes";

const PARENTESCOS = [
    "progenitor",
    "hermano/a",
    "hijo/a",
    "abuelo/a materno/a",
    "abuelo/a paterno/a",
    "tío/a materno/a",
    "tío/a paterno/a",
    "primo/a materno/a",
    "primo/a paterno/a",
    "pareja del paciente",
];

export default function FamiliaresPacientePage({ sesion }) {
    const { pacienteId } = useParams();
    const token = sesion?.access_token;

    const [nombrePaciente, setNombrePaciente] = useState("");
    const [familiares, setFamiliares] = useState([]);
    const [svgFamiliograma, setSvgFamiliograma] = useState("");
    const [cargando, setCargando] = useState(true);
    const [guardando, setGuardando] = useState(false);
    const [error, setError] = useState("");
    const [aviso, setAviso] = useState("");

    // Formulario para agregar un familiar
    const [parentesco, setParentesco] = useState("progenitor");
    const [nombre, setNombre] = useState("");
    const [diagPrevio, setDiagPrevio] = useState("");
    const [busquedaSnomed, setBusquedaSnomed] = useState("");
    const [resultadosSnomed, setResultadosSnomed] = useState([]);
    const [sintomasFam, setSintomasFam] = useState([]);
    const [buscandoSnomed, setBuscandoSnomed] = useState(false);

    async function cargarDatos() {
        setCargando(true);
        setError("");
        try {
            const info = await obtenerFamiliaresRequest(token, pacienteId);
            setNombrePaciente(info.nombre_completo || "");
            setFamiliares(
                (info.familiares || []).map((f) => ({
                    nombre: f.nombre,
                    parentesco: f.parentesco,
                    diagnostico_previo: f.diagnostico_previo || "",
                    sintomas: f.sintomas || [],
                }))
            );
            if (info.familiograma_generado) {
                const svg = await obtenerFamiliogramaSvgRequest(token, pacienteId);
                setSvgFamiliograma(svg);
            } else {
                setSvgFamiliograma("");
            }
        } catch (err) {
            setError(err.message);
        } finally {
            setCargando(false);
        }
    }

    useEffect(() => {
        if (token && pacienteId) {
            cargarDatos();
        }
    }, [token, pacienteId]);

    async function handleBuscarSnomed() {
        const q = busquedaSnomed.trim();
        if (q.length < 3) {
            setError("Ingresá al menos 3 letras para buscar síntomas SNOMED del familiar.");
            return;
        }
        setError("");
        setBuscandoSnomed(true);
        try {
            const res = await buscarSintomasSnomedRequest(token, q);
            setResultadosSnomed(res.resultados || []);
        } catch (err) {
            setError(err.message);
        } finally {
            setBuscandoSnomed(false);
        }
    }

    function agregarSintomaFamiliar(item) {
        if (sintomasFam.some((s) => s.snomed_id === item.snomed_id)) return;
        setSintomasFam((prev) => [...prev, item]);
    }

    function agregarFamiliar() {
        if (!nombre.trim()) {
            setError("Ingresá el nombre completo del familiar.");
            return;
        }
        setError("");
        setFamiliares((prev) => [
            ...prev,
            {
                nombre: nombre.trim(),
                parentesco,
                diagnostico_previo: diagPrevio.trim() || null,
                sintomas: sintomasFam,
            },
        ]);
        setNombre("");
        setDiagPrevio("");
        setSintomasFam([]);
        setResultadosSnomed([]);
        setBusquedaSnomed("");
    }

    function quitarFamiliar(idx) {
        setFamiliares((prev) => prev.filter((_, i) => i !== idx));
    }

    async function handleGuardar(listaAEnviar = familiares) {
        setError("");
        setAviso("");
        setGuardando(true);
        try {
            const payload = listaAEnviar.map((f) => ({
                nombre: f.nombre,
                parentesco: f.parentesco,
                diagnostico_previo: f.diagnostico_previo || null,
                sintomas_snomed_ids: (f.sintomas || []).map((s) => s.snomed_id),
            }));
            const res = await actualizarFamiliaresRequest(token, pacienteId, payload);
            setAviso(
                res.familiograma_generado
                    ? "Familiares actualizados y familiograma regenerado."
                    : "Sección familiar vaciada (sin información familiar)."
            );
            if (res.familiograma_generado) {
                const svg = await obtenerFamiliogramaSvgRequest(token, pacienteId);
                setSvgFamiliograma(svg);
            } else {
                setSvgFamiliograma("");
            }
        } catch (err) {
            setError(err.message);
        } finally {
            setGuardando(false);
        }
    }

    function descargarSvg() {
        if (!svgFamiliograma) return;
        const blob = new Blob([svgFamiliograma], { type: "image/svg+xml" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `familiograma_paciente_${pacienteId}.svg`;
        a.click();
        URL.revokeObjectURL(url);
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                        Escenario E18 · Información familiar
                    </p>
                    <h1 className="font-titulo mt-1 text-2xl font-semibold text-slate-900">
                        Familiares y Familiograma {nombrePaciente ? `· ${nombrePaciente}` : ""}
                    </h1>
                </div>
                <Link to="/medico/pacientes" className="text-xs font-semibold text-[#0B4F8A] hover:underline">
                    ← Volver a pacientes
                </Link>
            </div>

            {error && (
                <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-medium text-red-700">
                    {error}
                </div>
            )}

            {aviso && (
                <div role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs font-medium text-emerald-700">
                    {aviso}
                </div>
            )}

            {cargando ? (
                <p className="text-sm text-slate-500">Cargando información familiar...</p>
            ) : (
                <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                    {/* Columna izquierda: gestion de familiares */}
                    <section className="tarjeta-cristal lg:col-span-7">
                        <div className="h-1.5 w-full bg-gradient-to-r from-[#062846] via-[#0B4F8A] to-[#0891B2]" />
                        <div className="space-y-5 p-6">
                            <h2 className="text-sm font-semibold text-slate-900">
                                Grupo familiar registrado ({familiares.length})
                            </h2>

                            {familiares.length === 0 ? (
                                <p className="rounded-xl border border-slate-200/80 bg-[#E6EFF7]/50 px-4 py-3 text-xs text-slate-600">
                                    Este paciente no tiene familiares cargados actualmente.
                                </p>
                            ) : (
                                <ul className="space-y-2.5">
                                    {familiares.map((f, idx) => (
                                        <li
                                            key={idx}
                                            className="flex items-start justify-between gap-3 rounded-xl border border-slate-200/80 bg-white/80 p-3.5 text-xs"
                                        >
                                            <div>
                                                <p className="font-semibold text-slate-900">
                                                    <span className="capitalize text-[#0B4F8A]">{f.parentesco}:</span> {f.nombre}
                                                </p>
                                                {f.diagnostico_previo && (
                                                    <p className="mt-0.5 text-slate-600">
                                                        Diagnóstico previo: {f.diagnostico_previo}
                                                    </p>
                                                )}
                                                {f.sintomas?.length > 0 && (
                                                    <p className="mt-1 text-[11px] text-slate-500">
                                                        Síntomas: {f.sintomas.map((s) => s.descripcion).join(", ")}
                                                    </p>
                                                )}
                                            </div>
                                            <button
                                                type="button"
                                                onClick={() => quitarFamiliar(idx)}
                                                className="font-semibold text-red-600 hover:underline"
                                            >
                                                Quitar
                                            </button>
                                        </li>
                                    ))}
                                </ul>
                            )}

                            {/* Agregar nuevo familiar */}
                            <div className="space-y-3 border-t border-slate-200/70 pt-4">
                                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-600">
                                    Agregar familiar
                                </h3>
                                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                                    <select
                                        value={parentesco}
                                        onChange={(e) => setParentesco(e.target.value)}
                                        className="campo-clinico"
                                    >
                                        {PARENTESCOS.map((p) => (
                                            <option key={p} value={p}>{p}</option>
                                        ))}
                                    </select>
                                    <input
                                        type="text"
                                        value={nombre}
                                        onChange={(e) => setNombre(e.target.value)}
                                        placeholder="Nombre completo"
                                        className="campo-clinico"
                                    />
                                    <input
                                        type="text"
                                        value={diagPrevio}
                                        onChange={(e) => setDiagPrevio(e.target.value)}
                                        placeholder="Diagnóstico previo (opcional)"
                                        className="campo-clinico"
                                    />
                                </div>

                                <div className="flex gap-2">
                                    <input
                                        type="text"
                                        value={busquedaSnomed}
                                        onChange={(e) => setBusquedaSnomed(e.target.value)}
                                        placeholder="Síntomas SNOMED del familiar (opcional, mín. 3 letras)"
                                        className="campo-clinico"
                                    />
                                    <button
                                        type="button"
                                        onClick={handleBuscarSnomed}
                                        disabled={buscandoSnomed}
                                        className="shrink-0 rounded-xl border border-[#0B4F8A]/30 bg-[#EAF2FA] px-3 py-2 text-xs font-semibold text-[#0B4F8A] hover:bg-[#DCEAF7]"
                                    >
                                        {buscandoSnomed ? "..." : "Buscar"}
                                    </button>
                                </div>

                                {resultadosSnomed.length > 0 && (
                                    <div className="max-h-32 space-y-1 overflow-y-auto rounded-xl border border-slate-200 bg-white/80 p-2">
                                        {resultadosSnomed.map((item) => (
                                            <button
                                                key={item.snomed_id}
                                                type="button"
                                                onClick={() => agregarSintomaFamiliar(item)}
                                                className="flex w-full justify-between rounded-lg px-2.5 py-1 text-left text-xs hover:bg-[#EAF2FA]"
                                            >
                                                <span>{item.descripcion}</span>
                                                <span className="font-mono text-[11px] text-slate-500">+</span>
                                            </button>
                                        ))}
                                    </div>
                                )}

                                {sintomasFam.length > 0 && (
                                    <div className="flex flex-wrap gap-1.5">
                                        {sintomasFam.map((s) => (
                                            <span
                                                key={s.snomed_id}
                                                className="inline-flex items-center gap-1.5 rounded-full bg-[#0B4F8A]/10 px-2.5 py-0.5 text-[11px] font-medium text-[#0B4F8A]"
                                            >
                                                {s.descripcion}
                                                <button
                                                    type="button"
                                                    onClick={() =>
                                                        setSintomasFam((prev) =>
                                                            prev.filter((x) => x.snomed_id !== s.snomed_id)
                                                        )
                                                    }
                                                >
                                                    ×
                                                </button>
                                            </span>
                                        ))}
                                    </div>
                                )}

                                <button
                                    type="button"
                                    onClick={agregarFamiliar}
                                    className="rounded-xl border border-[#0B4F8A] bg-white/80 px-4 py-2 text-xs font-semibold text-[#0B4F8A] hover:bg-[#EAF2FA]"
                                >
                                    + Agregar a la lista
                                </button>
                            </div>

                            <div className="flex flex-wrap justify-between gap-3 border-t border-slate-200/70 pt-4">
                                <button
                                    type="button"
                                    disabled={guardando}
                                    onClick={() => {
                                        setFamiliares([]);
                                        handleGuardar([]);
                                    }}
                                    className="rounded-xl border border-slate-300 bg-white/80 px-4 py-2 text-xs font-medium text-slate-700 hover:bg-white disabled:opacity-50"
                                >
                                    Dejar sin información familiar
                                </button>
                                <button
                                    type="button"
                                    disabled={guardando}
                                    onClick={() => handleGuardar(familiares)}
                                    className="rounded-xl bg-gradient-to-r from-[#0B4F8A] to-[#0E7490] px-5 py-2 text-xs font-semibold text-white shadow-sm hover:from-[#093E6D] hover:to-[#0B5E75] disabled:opacity-50"
                                >
                                    {guardando ? "Guardando..." : "Guardar y generar familiograma"}
                                </button>
                            </div>
                        </div>
                    </section>

                    {/* Columna derecha: vista previa del familiograma SVG */}
                    <section className="tarjeta-cristal lg:col-span-5">
                        <div className="h-1.5 w-full bg-gradient-to-r from-[#0891B2] to-[#0B4F8A]" />
                        <div className="space-y-4 p-6">
                            <div className="flex items-center justify-between">
                                <h2 className="text-sm font-semibold text-slate-900">
                                    Vista previa del Familiograma
                                </h2>
                                {svgFamiliograma && (
                                    <button
                                        type="button"
                                        onClick={descargarSvg}
                                        className="rounded-lg border border-[#0B4F8A]/30 bg-[#EAF2FA] px-3 py-1 text-[11px] font-semibold text-[#0B4F8A] hover:bg-[#DCEAF7]"
                                    >
                                        Descargar SVG
                                    </button>
                                )}
                            </div>

                            {svgFamiliograma ? (
                                <div
                                    className="overflow-auto rounded-xl border border-slate-200 bg-white p-3"
                                    dangerouslySetInnerHTML={{ __html: svgFamiliograma }}
                                />
                            ) : (
                                <div className="rounded-xl border border-dashed border-slate-300 bg-[#E6EFF7]/40 p-8 text-center text-xs text-slate-500">
                                    Todavía no hay un familiograma generado. Agregá al menos un familiar y guardá los cambios para visualizarlo acá.
                                </div>
                            )}
                        </div>
                    </section>
                </div>
            )}
        </div>
    );
}
