import { useCallback, useEffect, useState } from "react";
import {
    cargarDatosCrudosRequest,
    listarEstudiosPendientesDatosCrudosRequest,
} from "../api/bioinformatica";

function validarSecuenciaLocal(texto) {
    const lineas = texto.split(/\r?\n/);
    let bases = 0;
    for (const raw of lineas) {
        const l = raw.trim();
        if (!l || l.startsWith(">")) continue;
        const limpia = l.replace(/[ \t]+/g, "").toUpperCase();
        if (/[^ACTG]/.test(limpia)) {
            return { valida: false, bases: 0, error: "Solo se permiten bases nucleotídicas A, C, T, G." };
        }
        bases += limpia.length;
    }
    if (bases === 0) {
        return { valida: false, bases: 0, error: "Ingresá o adjuntá una secuencia A, C, T, G no vacía." };
    }
    return { valida: true, bases, error: "" };
}

export default function DatosCrudosAdminPage({ sesion }) {
    const token = sesion?.access_token;
    const esAdmin = sesion?.usuario?.rol === "administrativo";

    const [estudios, setEstudios] = useState([]);
    const [cargandoLista, setCargandoLista] = useState(true);
    const [estudioSeleccionadoId, setEstudioSeleccionadoId] = useState("");
    const [archivo, setArchivo] = useState(null);
    const [contenidoActg, setContenidoActg] = useState("");
    const [enviando, setEnviando] = useState(false);
    const [error, setError] = useState("");
    const [resultadoExito, setResultadoExito] = useState(null);

    const aplicarLista = useCallback((resp) => {
        const lista = resp.estudios || [];
        setEstudios(lista);
        setEstudioSeleccionadoId((prev) => {
            if (prev && lista.some((e) => String(e.estudio_id) === String(prev))) {
                return prev;
            }
            return lista[0] ? String(lista[0].estudio_id) : "";
        });
    }, []);

    const cargarPendientes = useCallback(async () => {
        if (!token || !esAdmin) return;
        setCargandoLista(true);
        setError("");
        try {
            const resp = await listarEstudiosPendientesDatosCrudosRequest(token);
            aplicarLista(resp);
        } catch (err) {
            setError(err.message);
        } finally {
            setCargandoLista(false);
        }
    }, [token, esAdmin, aplicarLista]);

    useEffect(() => {
        if (!token || !esAdmin) return;
        let cancelado = false;
        listarEstudiosPendientesDatosCrudosRequest(token)
            .then((resp) => {
                if (!cancelado) aplicarLista(resp);
            })
            .catch((err) => {
                if (!cancelado) setError(err.message);
            })
            .finally(() => {
                if (!cancelado) setCargandoLista(false);
            });
        return () => {
            cancelado = true;
        };
    }, [token, esAdmin, aplicarLista]);

    if (!esAdmin) {
        return (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
                Solo el Personal Administrativo puede cargar datos crudos provenientes de Corea.
            </div>
        );
    }

    const estudioActivo = estudios.find((e) => String(e.estudio_id) === String(estudioSeleccionadoId));
    const validacionTexto = !archivo && contenidoActg.trim() ? validarSecuenciaLocal(contenidoActg) : null;

    async function handleFileChange(e) {
        const file = e.target.files?.[0] || null;
        setArchivo(file);
        setError("");
        setResultadoExito(null);
        if (file) {
            try {
                const texto = await file.text();
                setContenidoActg(texto.slice(0, 4000));
            } catch {
                // Si no puede previsualizar texto, igualmente se envia el File al backend
            }
        }
    }

    async function handleSubmit(e) {
        e.preventDefault();
        setError("");
        setResultadoExito(null);

        const idNum = Number(estudioSeleccionadoId);
        if (!idNum || idNum <= 0) {
            setError("Seleccioná o indicá un ID de estudio válido.");
            return;
        }
        if (!archivo) {
            const check = validarSecuenciaLocal(contenidoActg);
            if (!check.valida) {
                setError(check.error);
                return;
            }
        }

        setEnviando(true);
        try {
            const resp = await cargarDatosCrudosRequest({
                token,
                estudioId: idNum,
                archivo,
                contenidoActg,
                nombreArchivo: archivo?.name || `secuencia_corea_estudio_${idNum}.txt`,
            });
            setResultadoExito(resp);
            setArchivo(null);
            setContenidoActg("");
            await cargarPendientes();
        } catch (err) {
            setError(err.message);
        } finally {
            setEnviando(false);
        }
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                        Personal administrativo · Recepción de Corea
                    </p>
                    <h1 className="font-titulo mt-1 text-2xl font-semibold text-slate-900 sm:text-3xl">
                        Carga de datos crudos (ACTG)
                    </h1>
                    <p className="mt-1 text-sm text-slate-600">
                        Subí el archivo de secuenciación recibido de Corea para pasar el estudio a bioinformática.
                    </p>
                </div>
                <button
                    type="button"
                    onClick={cargarPendientes}
                    disabled={cargandoLista}
                    className="rounded-xl border border-[#0B4F8A] bg-white px-4 py-2 text-xs font-semibold text-[#0B4F8A] transition hover:bg-[#EAF2FA] disabled:opacity-50"
                >
                    {cargandoLista ? "Actualizando..." : "Actualizar lista"}
                </button>
            </div>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                <aside
                    aria-label="Estudios en viaje a Corea"
                    className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs lg:col-span-5"
                >
                    <div className="flex items-center justify-between">
                        <h2 className="text-sm font-semibold text-slate-900">En viaje a Corea</h2>
                        <span className="rounded-full bg-[#EAF2FA] px-2.5 py-0.5 text-[11px] font-semibold text-[#0B4F8A]">
                            {estudios.length}
                        </span>
                    </div>

                    {cargandoLista ? (
                        <p className="mt-4 text-xs text-slate-500">Cargando estudios...</p>
                    ) : estudios.length === 0 ? (
                        <p className="mt-4 rounded-xl border border-dashed border-slate-200 p-4 text-xs text-slate-500">
                            No hay estudios en estado &ldquo;En viaje a Corea&rdquo; pendientes de datos crudos.
                        </p>
                    ) : (
                        <ul className="mt-4 space-y-2.5">
                            {estudios.map((est) => {
                                const activo = String(est.estudio_id) === String(estudioSeleccionadoId);
                                return (
                                    <li key={est.estudio_id}>
                                        <button
                                            type="button"
                                            onClick={() => {
                                                setEstudioSeleccionadoId(String(est.estudio_id));
                                                setError("");
                                                setResultadoExito(null);
                                            }}
                                            className={`w-full rounded-xl border p-3.5 text-left transition focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] ${
                                                activo
                                                    ? "border-[#0B4F8A] bg-[#EAF2FA]/60"
                                                    : "border-slate-200 hover:border-slate-300 hover:bg-slate-50/70"
                                            }`}
                                        >
                                            <div className="flex items-center justify-between gap-2">
                                                <span className="text-sm font-semibold text-slate-900">
                                                    Estudio #{est.estudio_id}
                                                </span>
                                                {est.es_pompe_urgente && (
                                                    <span className="rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-700">
                                                        Pompe urgente
                                                    </span>
                                                )}
                                            </div>
                                            <p className="mt-1 text-xs font-medium text-slate-700">
                                                {est.paciente?.nombre || "Paciente"} · DNI {est.paciente?.dni || "-"}
                                            </p>
                                            <p className="mt-0.5 text-[11px] text-slate-500">
                                                {est.patologia_nombre} · {est.genes?.length || 0} gen(es)
                                            </p>
                                        </button>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </aside>

                <section
                    aria-label="Formulario de carga de datos crudos"
                    className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs lg:col-span-7"
                >
                    <div className="mb-5 flex items-center justify-between border-b border-slate-100 pb-3">
                        <h2 className="text-sm font-semibold text-slate-900">
                            {estudioActivo ? `Cargar secuencia para Estudio #${estudioActivo.estudio_id}` : "Adjuntar datos crudos"}
                        </h2>
                        <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-medium text-slate-600">
                            Formato A, C, T, G
                        </span>
                    </div>

                    {error && (
                        <div
                            role="alert"
                            className="mb-4 rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-xs font-medium text-red-700"
                        >
                            {error}
                        </div>
                    )}

                    {resultadoExito && (
                        <div
                            role="status"
                            className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs text-emerald-900"
                        >
                            <p className="font-semibold">
                                Datos crudos cargados correctamente para Estudio #{resultadoExito.estudio_id}.
                            </p>
                            <p className="mt-1">
                                Estado actual: <strong>{resultadoExito.estado_estudio}</strong> · Análisis #{resultadoExito.analisis_id} · Archivo: <code className="font-mono">{resultadoExito.archivo_path}</code>
                            </p>
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div>
                            <label htmlFor="estudio-id-input" className="mb-1.5 block text-xs font-medium text-slate-700">
                                ID de estudio
                            </label>
                            <input
                                id="estudio-id-input"
                                type="number"
                                min={1}
                                required
                                value={estudioSeleccionadoId}
                                onChange={(e) => setEstudioSeleccionadoId(e.target.value)}
                                placeholder="Ej: 42"
                                className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-2 text-sm text-slate-900 focus:border-[#0B4F8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0B4F8A]/15"
                            />
                        </div>

                        {estudioActivo && (
                            <div className="rounded-xl border border-slate-200/80 bg-[#F8FAFC] p-3.5 text-xs text-slate-700">
                                <p className="font-semibold text-slate-900">
                                    {estudioActivo.paciente?.nombre} · {estudioActivo.patologia_nombre}
                                </p>
                                <div className="mt-2 flex flex-wrap gap-1.5">
                                    {(estudioActivo.genes || []).map((g) => (
                                        <span
                                            key={g.gen_id}
                                            className="rounded-md border border-slate-200 bg-white px-2 py-0.5 font-mono text-[11px] font-medium text-slate-700"
                                        >
                                            {g.simbolo}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )}

                        <div>
                            <label htmlFor="archivo-actg" className="mb-1.5 block text-xs font-medium text-slate-700">
                                Archivo de secuencia (.txt / .fasta)
                            </label>
                            <input
                                id="archivo-actg"
                                type="file"
                                accept=".txt,.fasta,.fa,text/plain"
                                onChange={handleFileChange}
                                className="block w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3 py-2 text-xs text-slate-700 file:mr-3 file:rounded-lg file:border-0 file:bg-[#EAF2FA] file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-[#0B4F8A] hover:file:bg-[#d8e8f8]"
                            />
                            {archivo && (
                                <div className="mt-1.5 flex items-center justify-between text-[11px] text-slate-600">
                                    <span>Archivo seleccionado: <strong>{archivo.name}</strong></span>
                                    <button
                                        type="button"
                                        onClick={() => setArchivo(null)}
                                        className="font-medium text-red-600 hover:underline"
                                    >
                                        Quitar archivo
                                    </button>
                                </div>
                            )}
                        </div>

                        <div>
                            <label htmlFor="contenido-actg" className="mb-1.5 block text-xs font-medium text-slate-700">
                                O pegá directamente la secuencia ACTG
                            </label>
                            <textarea
                                id="contenido-actg"
                                rows={6}
                                value={contenidoActg}
                                onChange={(e) => {
                                    if (archivo) setArchivo(null);
                                    setContenidoActg(e.target.value);
                                }}
                                placeholder="ATCGGCTAGCTAGCTAGCTAGCTGATCGATCG"
                                className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-2 font-mono text-xs text-slate-900 placeholder:text-slate-400 focus:border-[#0B4F8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0B4F8A]/15"
                            />
                            {validacionTexto && (
                                <p
                                    className={`mt-1 text-[11px] font-medium ${
                                        validacionTexto.valida ? "text-emerald-700" : "text-red-600"
                                    }`}
                                >
                                    {validacionTexto.valida
                                        ? `Secuencia válida (${validacionTexto.bases} bases nucleotídicas).`
                                        : validacionTexto.error}
                                </p>
                            )}
                        </div>

                        <div className="flex justify-end pt-1">
                            <button
                                type="submit"
                                disabled={enviando || !estudioSeleccionadoId}
                                className="inline-flex items-center justify-center rounded-xl bg-[#0B4F8A] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#093E6D] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] focus-visible:ring-offset-2 disabled:opacity-50"
                            >
                                {enviando ? "Cargando datos crudos..." : "Cargar datos crudos y notificar"}
                            </button>
                        </div>
                    </form>
                </section>
            </div>
        </div>
    );
}
