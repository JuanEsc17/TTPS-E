import { useEffect, useState } from "react";
import {
    buscarSintomasSnomedRequest,
    guardarPatologiaRequest,
    listarPatologiasRequest,
} from "../api/patologias";

function BuscadorSnomed({ token, id, label, placeholder, onSeleccionar, seleccionadosIds }) {
    const [query, setQuery] = useState("");
    const [resultados, setResultados] = useState([]);
    const [buscando, setBuscando] = useState(false);
    const [errorBusqueda, setErrorBusqueda] = useState("");

    useEffect(() => {
        const texto = query.trim();
        if (texto.length < 3) {
            setResultados([]);
            setErrorBusqueda("");
            return;
        }
        let cancelado = false;
        const timer = setTimeout(async () => {
            setBuscando(true);
            setErrorBusqueda("");
            try {
                const items = await buscarSintomasSnomedRequest({ token, q: texto, limite: 8 });
                if (!cancelado) setResultados(items);
            } catch (err) {
                if (!cancelado) {
                    setResultados([]);
                    setErrorBusqueda(err.message);
                }
            } finally {
                if (!cancelado) setBuscando(false);
            }
        }, 300);
        return () => {
            cancelado = true;
            clearTimeout(timer);
        };
    }, [query, token]);

    function elegir(item) {
        onSeleccionar(item);
        setQuery("");
        setResultados([]);
    }

    return (
        <div>
            <label htmlFor={id} className="mb-1.5 block text-xs font-medium text-slate-700">
                {label}
            </label>
            <input
                id={id}
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={placeholder}
                className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-[#0B4F8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0B4F8A]/15"
            />
            {buscando && <p className="mt-1 text-[11px] text-slate-500">Buscando en SNOMED...</p>}
            {errorBusqueda && <p className="mt-1 text-[11px] text-red-600">{errorBusqueda}</p>}
            {resultados.length > 0 && (
                <ul className="mt-1.5 max-h-44 overflow-y-auto rounded-xl border border-slate-200 bg-white divide-y divide-slate-100 shadow-xs">
                    {resultados.map((item) => {
                        const yaElegido = seleccionadosIds.has(item.snomed_id);
                        return (
                            <li key={item.snomed_id}>
                                <button
                                    type="button"
                                    disabled={yaElegido}
                                    onClick={() => elegir(item)}
                                    className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs hover:bg-[#EAF2FA]/60 disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                    <span className="font-medium text-slate-800">{item.descripcion}</span>
                                    <span className="shrink-0 font-mono text-[11px] text-slate-500">
                                        {yaElegido ? "Ya seleccionado" : `SCTID ${item.snomed_id}`}
                                    </span>
                                </button>
                            </li>
                        );
                    })}
                </ul>
            )}
        </div>
    );
}

export default function PatologiasPage({ sesion }) {
    const token = sesion?.access_token;
    const esGerente = sesion?.usuario?.rol === "gerente_medico";

    const [patologias, setPatologias] = useState([]);
    const [cargandoLista, setCargandoLista] = useState(true);
    const [patologiaId, setPatologiaId] = useState(null);
    const [nombre, setNombre] = useState("");
    const [descripcion, setDescripcion] = useState("");
    const [cardinal, setCardinal] = useState(null);
    const [secundarios, setSecundarios] = useState([]);

    const [guardando, setGuardando] = useState(false);
    const [error, setError] = useState("");
    const [aviso, setAviso] = useState(null);

    useEffect(() => {
        if (!token) return;
        let cancelado = false;
        setCargandoLista(true);
        listarPatologiasRequest(token)
            .then((lista) => {
                if (!cancelado) setPatologias(lista);
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
    }, [token]);

    function nuevaPatologia() {
        setPatologiaId(null);
        setNombre("");
        setDescripcion("");
        setCardinal(null);
        setSecundarios([]);
        setError("");
        setAviso(null);
    }

    function seleccionarParaEditar(p) {
        setPatologiaId(p.patologia_id);
        setNombre(p.nombre || "");
        setDescripcion(p.descripcion || "");
        setCardinal(p.sintoma_cardinal ? { snomed_id: p.sintoma_cardinal.snomed_id, descripcion: p.sintoma_cardinal.descripcion } : null);
        setSecundarios(
            (p.sintomas_secundarios || []).map((s) => ({
                snomed_id: s.snomed_id,
                descripcion: s.descripcion,
            }))
        );
        setError("");
        setAviso(null);
    }

    async function handleSubmit(e) {
        e.preventDefault();
        setError("");
        setAviso(null);

        if (!nombre.trim()) {
            setError("Ingresá el nombre de la patología.");
            return;
        }
        if (!cardinal) {
            setError("Seleccioná un síntoma cardinal desde SNOMED.");
            return;
        }
        if (secundarios.length < 2) {
            setError("Agregá al menos 2 síntomas secundarios desde SNOMED.");
            return;
        }

        setGuardando(true);
        try {
            const guardada = await guardarPatologiaRequest({
                token,
                patologiaId,
                payload: {
                    nombre: nombre.trim(),
                    descripcion: descripcion.trim() || null,
                    sintoma_cardinal: cardinal,
                    sintomas_secundarios: secundarios,
                },
            });

            setPatologias((prev) => {
                const resto = prev.filter((item) => item.patologia_id !== guardada.patologia_id);
                return [...resto, guardada].sort((a, b) => a.nombre.localeCompare(b.nombre));
            });
            setPatologiaId(guardada.patologia_id);
            setAviso({
                tipo: guardada.genes_sincronizados ? "ok" : "warn",
                texto: guardada.genes_sincronizados
                    ? "Patología guardada y genes sincronizados correctamente."
                    : "Patología y síntomas guardados. La sincronización de genes con Bioinformática quedó pendiente.",
            });
        } catch (err) {
            setError(err.message);
        } finally {
            setGuardando(false);
        }
    }

    if (!esGerente) {
        return (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
                Solo el Gerente Médico puede administrar patologías y sus síntomas SNOMED.
            </div>
        );
    }

    const idsEnUso = new Set([
        ...(cardinal ? [cardinal.snomed_id] : []),
        ...secundarios.map((s) => s.snomed_id),
    ]);

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                        Gerencia médica · Terminología SNOMED
                    </p>
                    <h1 className="font-titulo mt-1 text-2xl font-semibold text-slate-900 sm:text-3xl">
                        Gestión de patologías
                    </h1>
                    <p className="mt-1 text-sm text-slate-600">
                        Definí cada patología con su síntoma cardinal único y al menos dos síntomas secundarios.
                    </p>
                </div>
                <button
                    type="button"
                    onClick={nuevaPatologia}
                    className="rounded-xl border border-[#0B4F8A] bg-white px-4 py-2 text-xs font-semibold text-[#0B4F8A] transition hover:bg-[#EAF2FA]"
                >
                    + Nueva patología
                </button>
            </div>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                <aside className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs lg:col-span-5">
                    <h2 className="text-sm font-semibold text-slate-900">Patologías registradas</h2>
                    {cargandoLista ? (
                        <p className="mt-4 text-xs text-slate-500">Cargando catálogo...</p>
                    ) : patologias.length === 0 ? (
                        <p className="mt-4 rounded-xl border border-dashed border-slate-200 p-4 text-xs text-slate-500">
                            Todavía no hay patologías cargadas. Creá la primera desde el formulario.
                        </p>
                    ) : (
                        <ul className="mt-4 space-y-2.5">
                            {patologias.map((p) => {
                                const activa = p.patologia_id === patologiaId;
                                return (
                                    <li key={p.patologia_id}>
                                        <button
                                            type="button"
                                            onClick={() => seleccionarParaEditar(p)}
                                            className={`w-full rounded-xl border p-3.5 text-left transition ${
                                                activa
                                                    ? "border-[#0B4F8A] bg-[#EAF2FA]/50"
                                                    : "border-slate-200 hover:border-slate-300 hover:bg-slate-50/70"
                                            }`}
                                        >
                                            <div className="flex items-center justify-between gap-2">
                                                <span className="text-sm font-semibold text-slate-900">{p.nombre}</span>
                                                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
                                                    {p.sintomas_secundarios?.length || 0} sec.
                                                </span>
                                            </div>
                                            {p.sintoma_cardinal && (
                                                <p className="mt-1 text-xs text-[#0B4F8A]">
                                                    Cardinal: {p.sintoma_cardinal.descripcion}
                                                </p>
                                            )}
                                            {p.genes?.length > 0 && (
                                                <div className="mt-2 flex flex-wrap gap-1">
                                                    {p.genes.map((g) => (
                                                        <span
                                                            key={g.simbolo}
                                                            className="rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] font-medium text-slate-700"
                                                        >
                                                            {g.simbolo}
                                                        </span>
                                                    ))}
                                                </div>
                                            )}
                                        </button>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </aside>

                <section
                    aria-label="Formulario de patología"
                    className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs lg:col-span-7"
                >
                    <div className="mb-5 flex items-center justify-between border-b border-slate-100 pb-3">
                        <h2 className="text-sm font-semibold text-slate-900">
                            {patologiaId ? "Modificar patología" : "Alta de nueva patología"}
                        </h2>
                        <span className="rounded-full bg-[#EAF2FA] px-2.5 py-0.5 text-[11px] font-medium text-[#0B4F8A]">
                            {patologiaId ? `ID #${patologiaId}` : "Nueva"}
                        </span>
                    </div>

                    {error && (
                        <div role="alert" className="mb-4 rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-xs font-medium text-red-700">
                            {error}
                        </div>
                    )}
                    {aviso && (
                        <div
                            role="status"
                            className={`mb-4 rounded-xl border px-3.5 py-2.5 text-xs font-medium ${
                                aviso.tipo === "warn"
                                    ? "border-amber-200 bg-amber-50 text-amber-900"
                                    : "border-emerald-200 bg-emerald-50 text-emerald-800"
                            }`}
                        >
                            {aviso.texto}
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className="space-y-5">
                        <div>
                            <label htmlFor="patologia-nombre" className="mb-1.5 block text-xs font-medium text-slate-700">
                                Nombre de la patología
                            </label>
                            <input
                                id="patologia-nombre"
                                type="text"
                                maxLength={120}
                                required
                                placeholder="Ej: Enfermedad de Fabry"
                                value={nombre}
                                onChange={(e) => setNombre(e.target.value)}
                                className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-2 text-sm text-slate-900 focus:border-[#0B4F8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0B4F8A]/15"
                            />
                        </div>

                        <div>
                            <label htmlFor="patologia-desc" className="mb-1.5 block text-xs font-medium text-slate-700">
                                Descripción clínica (opcional)
                            </label>
                            <textarea
                                id="patologia-desc"
                                rows={2}
                                placeholder="Resumen clínico de la patología..."
                                value={descripcion}
                                onChange={(e) => setDescripcion(e.target.value)}
                                className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-2 text-sm text-slate-900 focus:border-[#0B4F8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0B4F8A]/15"
                            />
                        </div>

                        <div className="space-y-2 rounded-xl border border-slate-200/80 bg-[#F8FAFC] p-4">
                            <BuscadorSnomed
                                token={token}
                                id="buscar-cardinal"
                                label="Síntoma cardinal (único · SNOMED)"
                                placeholder="Escribí al menos 3 letras (ej: acroparestesia)..."
                                onSeleccionar={(item) => setCardinal(item)}
                                seleccionadosIds={idsEnUso}
                            />
                            {cardinal ? (
                                <div className="flex items-center justify-between rounded-lg border border-[#0B4F8A]/30 bg-[#EAF2FA] px-3 py-2 text-xs">
                                    <div>
                                        <span className="font-semibold text-[#0B4F8A]">{cardinal.descripcion}</span>
                                        <span className="ml-2 font-mono text-[11px] text-slate-600">
                                            SCTID {cardinal.snomed_id}
                                        </span>
                                    </div>
                                    <button
                                        type="button"
                                        onClick={() => setCardinal(null)}
                                        className="font-medium text-slate-600 hover:text-red-700"
                                    >
                                        Quitar
                                    </button>
                                </div>
                            ) : (
                                <p className="text-[11px] text-slate-500">Sin síntoma cardinal seleccionado.</p>
                            )}
                        </div>

                        <div className="space-y-2 rounded-xl border border-slate-200/80 bg-[#F8FAFC] p-4">
                            <BuscadorSnomed
                                token={token}
                                id="buscar-secundario"
                                label={`Síntomas secundarios (mínimo 2 · actuales: ${secundarios.length})`}
                                placeholder="Buscá síntomas secundarios en SNOMED..."
                                onSeleccionar={(item) => setSecundarios((prev) => [...prev, item])}
                                seleccionadosIds={idsEnUso}
                            />
                            {secundarios.length > 0 && (
                                <ul className="flex flex-wrap gap-2 pt-1">
                                    {secundarios.map((s) => (
                                        <li
                                            key={s.snomed_id}
                                            className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-800"
                                        >
                                            <span>{s.descripcion}</span>
                                            <span className="font-mono text-[10px] text-slate-400">{s.snomed_id}</span>
                                            <button
                                                type="button"
                                                aria-label={`Quitar ${s.descripcion}`}
                                                onClick={() =>
                                                    setSecundarios((prev) => prev.filter((x) => x.snomed_id !== s.snomed_id))
                                                }
                                                className="text-slate-400 hover:text-red-600"
                                            >
                                                ×
                                            </button>
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </div>

                        <div className="flex justify-end pt-1">
                            <button
                                type="submit"
                                disabled={guardando}
                                className="inline-flex items-center justify-center rounded-xl bg-[#0B4F8A] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#093E6D] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] focus-visible:ring-offset-2 disabled:opacity-50"
                            >
                                {guardando
                                    ? "Guardando..."
                                    : patologiaId
                                    ? "Guardar cambios"
                                    : "Registrar patología"}
                            </button>
                        </div>
                    </form>
                </section>
            </div>
        </div>
    );
}
