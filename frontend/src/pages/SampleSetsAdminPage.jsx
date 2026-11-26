import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { listarSampleSetsRequest, obtenerSampleSetRequest } from "../api/sampleSets";

const FILTROS_ESTADO = [
    { value: "", label: "Todos" },
    { value: "abierto", label: "Abiertos" },
    { value: "cerrado", label: "Cerrados (En espera)" },
    { value: "en_viaje_a_corea", label: "En viaje a Corea" },
];

const ETIQUETA_ESTADO = {
    abierto: "Abierto (en armado)",
    cerrado: "Cerrado · En espera de retiro",
    en_viaje_a_corea: "En viaje a Corea",
};

const ESTILO_ESTADO = {
    abierto: "border-cyan-200 bg-cyan-50 text-[#0B4F8A]",
    cerrado: "border-emerald-200 bg-emerald-50 text-emerald-800",
    en_viaje_a_corea: "border-indigo-200 bg-indigo-50 text-indigo-800",
};

function formatearFechaHora(iso) {
    if (!iso) return "-";
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

function seleccionarIdInicial(lista, buscado) {
    if (!Array.isArray(lista) || lista.length === 0) return null;
    if (buscado && lista.some((s) => s.id === buscado)) return buscado;
    return lista[0].id;
}

export default function SampleSetsAdminPage({ sesion }) {
    const token = sesion?.access_token;
    const esAdmin = sesion?.usuario?.rol === "administrativo";
    const [searchParams, setSearchParams] = useSearchParams();

    const sampleSetSolicitadoId = useMemo(() => {
        const raw = searchParams.get("sampleSetId");
        const num = Number(raw);
        return Number.isInteger(num) && num > 0 ? num : null;
    }, [searchParams]);

    const [filtroEstado, setFiltroEstado] = useState("");
    const [recargaId, setRecargaId] = useState(0);
    const claveCarga = `${token || ""}:${filtroEstado}:${recargaId}`;

    const [estadoCarga, setEstadoCarga] = useState({
        clave: null,
        token: null,
        items: [],
        error: "",
    });
    const [seleccionadoId, setSeleccionadoId] = useState(sampleSetSolicitadoId);
    const [detalleRemoto, setDetalleRemoto] = useState(null);
    const [errorDetalle, setErrorDetalle] = useState("");

    useEffect(() => {
        if (!token || !esAdmin) return;
        const controller = new AbortController();

        listarSampleSetsRequest(token, {
            estado: filtroEstado,
            signal: controller.signal,
        })
            .then((lista) => {
                if (controller.signal.aborted) return;
                setEstadoCarga({
                    clave: claveCarga,
                    token,
                    items: Array.isArray(lista) ? lista : [],
                    error: "",
                });
                setSeleccionadoId((prev) => {
                    const objetivo = sampleSetSolicitadoId || prev;
                    return seleccionarIdInicial(lista, objetivo);
                });
            })
            .catch((err) => {
                if (err?.name === "AbortError" || controller.signal.aborted) return;
                setEstadoCarga((prev) => ({
                    clave: claveCarga,
                    token,
                    items: prev.token === token ? prev.items : [],
                    error: err?.message || "No se pudieron cargar los sample-sets.",
                }));
            });

        return () => controller.abort();
    }, [token, esAdmin, filtroEstado, claveCarga, sampleSetSolicitadoId]);

    const sampleSets = useMemo(
        () => (estadoCarga.token === token ? estadoCarga.items : []),
        [estadoCarga, token]
    );
    const cargando = Boolean(token && esAdmin) && estadoCarga.clave !== claveCarga;
    const error = estadoCarga.token === token ? estadoCarga.error : "";

    const idActivo = useMemo(() => {
        if (sampleSetSolicitadoId && sampleSets.some((s) => s.id === sampleSetSolicitadoId)) {
            return sampleSetSolicitadoId;
        }
        if (seleccionadoId && sampleSets.some((s) => s.id === seleccionadoId)) {
            return seleccionadoId;
        }
        return sampleSets[0]?.id ?? sampleSetSolicitadoId ?? null;
    }, [sampleSets, seleccionadoId, sampleSetSolicitadoId]);

    useEffect(() => {
        if (!token || !esAdmin || !idActivo) return;
        const controller = new AbortController();

        obtenerSampleSetRequest(token, idActivo, { signal: controller.signal })
            .then((detalle) => {
                if (controller.signal.aborted) return;
                setDetalleRemoto(detalle);
                setErrorDetalle("");
            })
            .catch((err) => {
                if (err?.name === "AbortError" || controller.signal.aborted) return;
                setErrorDetalle(err?.message || "No se pudo consultar el detalle del sample-set.");
            });

        return () => controller.abort();
    }, [token, esAdmin, idActivo, recargaId]);

    const sampleSetDetalle = useMemo(() => {
        if (detalleRemoto && detalleRemoto.id === idActivo) return detalleRemoto;
        return sampleSets.find((s) => s.id === idActivo) || null;
    }, [detalleRemoto, sampleSets, idActivo]);

    const resumen = useMemo(() => {
        let abiertos = 0;
        let cerrados = 0;
        let pompeUrgentes = 0;
        for (const ss of sampleSets) {
            if (ss.estado === "abierto") abiertos += 1;
            if (ss.estado === "cerrado") cerrados += 1;
            if (ss.es_pompe_urgente) pompeUrgentes += 1;
        }
        return { total: sampleSets.length, abiertos, cerrados, pompeUrgentes };
    }, [sampleSets]);

    function handleElegirSampleSet(id) {
        setSeleccionadoId(id);
        setErrorDetalle("");
        if (searchParams.has("sampleSetId")) {
            const next = new URLSearchParams(searchParams);
            next.delete("sampleSetId");
            setSearchParams(next, { replace: true });
        }
    }

    if (!esAdmin) {
        return (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
                Esta vista es exclusiva para el personal administrativo del laboratorio central.
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Encabezado */}
            <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                        Laboratorio central · Armado de lotes
                    </p>
                    <h1 className="font-titulo mt-1 text-2xl font-semibold text-slate-900 sm:text-3xl">
                        Sample sets de muestras
                    </h1>
                    <p className="mt-1 text-sm text-slate-600">
                        Lotes automáticos de hasta 10 muestras o cierre inmediato ante un caso{" "}
                        <strong>Pompe urgente</strong>.
                    </p>
                </div>

                <button
                    type="button"
                    onClick={() => setRecargaId((n) => n + 1)}
                    disabled={cargando}
                    className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 shadow-xs transition hover:bg-slate-50 disabled:opacity-50"
                >
                    {cargando ? "Actualizando..." : "Actualizar"}
                </button>
            </div>

            {/* Tarjetas de resumen y filtros */}
            <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="flex flex-wrap items-center gap-2">
                    {FILTROS_ESTADO.map((f) => {
                        const activo = filtroEstado === f.value;
                        return (
                            <button
                                key={f.value || "todos"}
                                type="button"
                                onClick={() => {
                                    setFiltroEstado(f.value);
                                    setErrorDetalle("");
                                }}
                                className={`rounded-xl border px-3.5 py-2 text-xs font-semibold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] ${activo
                                    ? "border-[#0B4F8A] bg-[#0B4F8A] text-white shadow-xs"
                                    : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                                    }`}
                            >
                                {f.label}
                            </button>
                        );
                    })}
                </div>

                <div className="flex flex-wrap items-center gap-2 text-xs">
                    <span className="rounded-full border border-slate-200 bg-white px-3 py-1 font-medium text-slate-700">
                        Visibles: <strong>{resumen.total}</strong>
                    </span>
                    <span className="rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1 font-medium text-[#0B4F8A]">
                        Abiertos: <strong>{resumen.abiertos}</strong>
                    </span>
                    <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 font-medium text-emerald-800">
                        Cerrados: <strong>{resumen.cerrados}</strong>
                    </span>
                    {resumen.pompeUrgentes > 0 && (
                        <span className="rounded-full border border-red-200 bg-red-50 px-3 py-1 font-semibold text-red-700">
                            Pompe urgente: {resumen.pompeUrgentes}
                        </span>
                    )}
                </div>
            </div>

            {(error || errorDetalle) && (
                <div
                    role="alert"
                    className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-medium text-red-700"
                >
                    {error || errorDetalle}
                </div>
            )}

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                {/* Columna izquierda: Lista de SampleSets */}
                <aside
                    aria-label="Listado de sample-sets"
                    className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs lg:col-span-5"
                >
                    <div className="flex items-center justify-between">
                        <h2 className="text-sm font-semibold text-slate-900">Lotes registrados</h2>
                        <span className="rounded-full bg-[#EAF2FA] px-2.5 py-0.5 text-[11px] font-semibold text-[#0B4F8A]">
                            {sampleSets.length}
                        </span>
                    </div>

                    {cargando && sampleSets.length === 0 ? (
                        <p className="mt-4 text-xs text-slate-500">Cargando sample-sets...</p>
                    ) : sampleSets.length === 0 ? (
                        <p className="mt-4 rounded-xl border border-dashed border-slate-200 p-5 text-xs text-slate-500">
                            No hay sample-sets registrados para el filtro seleccionado. Se crean
                            automáticamente cuando el transportista confirma la llegada de muestras al
                            laboratorio central.
                        </p>
                    ) : (
                        <ul className="mt-4 space-y-2.5">
                            {sampleSets.map((ss) => {
                                const seleccionado = sampleSetDetalle?.id === ss.id;
                                const capacidad = ss.capacidad_maxima || 10;
                                const porcentaje = Math.min(
                                    100,
                                    Math.round(((ss.cantidad_muestras || 0) / capacidad) * 100)
                                );
                                return (
                                    <li key={ss.id}>
                                        <button
                                            type="button"
                                            onClick={() => handleElegirSampleSet(ss.id)}
                                            className={`w-full rounded-xl border p-3.5 text-left transition focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] ${seleccionado
                                                ? "border-[#0B4F8A] bg-[#EAF2FA]/60"
                                                : "border-slate-200 hover:border-slate-300 hover:bg-slate-50/70"
                                                }`}
                                        >
                                            <div className="flex flex-wrap items-center justify-between gap-2">
                                                <span className="text-sm font-semibold text-slate-900">
                                                    SampleSet #{ss.id}
                                                </span>
                                                <div className="flex flex-wrap items-center gap-1.5">
                                                    {ss.es_pompe_urgente && (
                                                        <span className="rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-red-700">
                                                            Pompe urgente
                                                        </span>
                                                    )}
                                                    <span
                                                        className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${ESTILO_ESTADO[ss.estado] ||
                                                            "border-slate-200 bg-slate-100 text-slate-700"
                                                            }`}
                                                    >
                                                        {ETIQUETA_ESTADO[ss.estado] || ss.estado}
                                                    </span>
                                                </div>
                                            </div>

                                            <div className="mt-2.5 flex items-center justify-between text-[11px] text-slate-600">
                                                <span>
                                                    <strong>{ss.cantidad_muestras}</strong> /{" "}
                                                    {capacidad} muestras
                                                </span>
                                                <span>
                                                    {ss.cerrado_en
                                                        ? `Cerrado: ${formatearFechaHora(ss.cerrado_en)}`
                                                        : "Esperando completar lote"}
                                                </span>
                                            </div>

                                            <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                                                <div
                                                    className={`h-full rounded-full transition-all ${ss.es_pompe_urgente
                                                        ? "bg-red-500"
                                                        : ss.estado === "abierto"
                                                            ? "bg-[#0891B2]"
                                                            : "bg-emerald-600"
                                                        }`}
                                                    style={{ width: `${porcentaje}%` }}
                                                />
                                            </div>
                                        </button>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </aside>

                {/* Columna derecha: Detalle del SampleSet */}
                <section
                    aria-label="Detalle del sample-set seleccionado"
                    className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs lg:col-span-7"
                >
                    {!sampleSetDetalle ? (
                        <div className="rounded-xl border border-dashed border-slate-200 p-8 text-center text-xs text-slate-500">
                            Seleccioná un sample-set de la lista para ver sus muestras, estudios y
                            estado de cierre.
                        </div>
                    ) : (
                        <div className="space-y-5">
                            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-4">
                                <div>
                                    <div className="flex flex-wrap items-center gap-2">
                                        <h2 className="font-titulo text-xl font-semibold text-slate-900">
                                            SampleSet #{sampleSetDetalle.id}
                                        </h2>
                                        {sampleSetDetalle.es_pompe_urgente && (
                                            <span className="rounded-full border border-red-200 bg-red-50 px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide text-red-700">
                                                Pompe urgente
                                            </span>
                                        )}
                                    </div>
                                    <p className="mt-1 text-xs text-slate-500">
                                        {sampleSetDetalle.estado === "abierto"
                                            ? "Lote abierto: sigue incorporando muestras que ingresen al laboratorio central hasta llegar a 10 (o ante un Pompe urgente)."
                                            : "Lote sellado e inmutable: no admite agregar ni quitar muestras."}
                                    </p>
                                </div>
                                <span
                                    className={`rounded-full border px-3 py-1 text-xs font-semibold ${ESTILO_ESTADO[sampleSetDetalle.estado] ||
                                        "border-slate-200 bg-slate-100 text-slate-700"
                                        }`}
                                >
                                    {ETIQUETA_ESTADO[sampleSetDetalle.estado] ||
                                        sampleSetDetalle.estado}
                                </span>
                            </div>

                            {sampleSetDetalle.es_pompe_urgente && (
                                <div className="rounded-xl border border-red-200 bg-red-50/70 px-4 py-3 text-xs text-red-900">
                                    <strong>Cierre prioritario por Pompe urgente:</strong> este lote
                                    incluye un paciente menor de 4 meses con sospecha de Pompe y se
                                    cerró automáticamente sin esperar a completar las 10 muestras.
                                </div>
                            )}

                            <dl className="grid grid-cols-1 gap-3 rounded-xl border border-slate-200/80 bg-[#F8FAFC] p-4 text-xs sm:grid-cols-3">
                                <div>
                                    <dt className="text-[11px] font-medium text-slate-500">
                                        Cantidad de muestras
                                    </dt>
                                    <dd className="mt-0.5 text-sm font-semibold text-slate-900">
                                        {sampleSetDetalle.cantidad_muestras} /{" "}
                                        {sampleSetDetalle.capacidad_maxima || 10}
                                    </dd>
                                </div>
                                <div>
                                    <dt className="text-[11px] font-medium text-slate-500">
                                        Fecha de cierre
                                    </dt>
                                    <dd className="mt-0.5 font-semibold text-slate-900">
                                        {formatearFechaHora(sampleSetDetalle.cerrado_en)}
                                    </dd>
                                </div>
                                <div>
                                    <dt className="text-[11px] font-medium text-slate-500">
                                        Inmutabilidad
                                    </dt>
                                    <dd className="mt-0.5 font-semibold text-slate-900">
                                        {sampleSetDetalle.estado === "abierto"
                                            ? "En formación"
                                            : "Sellado"}
                                    </dd>
                                </div>
                            </dl>

                            <div>
                                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                                    Muestras incluidas en este lote (
                                    {sampleSetDetalle.muestras?.length || 0})
                                </h3>

                                {!sampleSetDetalle.muestras ||
                                    sampleSetDetalle.muestras.length === 0 ? (
                                    <p className="mt-3 rounded-xl border border-dashed border-slate-200 p-4 text-xs text-slate-500">
                                        Este sample-set aún no tiene muestras detalladas.
                                    </p>
                                ) : (
                                    <div className="mt-3 overflow-x-auto rounded-xl border border-slate-200">
                                        <table className="w-full border-collapse text-left text-xs">
                                            <thead className="bg-slate-50 text-[11px] font-semibold uppercase tracking-wide text-slate-600">
                                                <tr>
                                                    <th className="px-3.5 py-2.5">Muestra / Estudio</th>
                                                    <th className="px-3.5 py-2.5">Paciente</th>
                                                    <th className="px-3.5 py-2.5">Patología</th>
                                                    <th className="px-3.5 py-2.5">Llegada lab</th>
                                                    <th className="px-3.5 py-2.5">Estado</th>
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y divide-slate-100">
                                                {sampleSetDetalle.muestras.map((m) => (
                                                    <tr
                                                        key={m.muestra_id}
                                                        className={
                                                            m.es_pompe_urgente ? "bg-red-50/40" : ""
                                                        }
                                                    >
                                                        <td className="px-3.5 py-2.5 font-medium text-slate-900">
                                                            <div>Muestra #{m.muestra_id}</div>
                                                            <div className="text-[11px] text-slate-500">
                                                                Estudio #{m.estudio_id}
                                                            </div>
                                                        </td>
                                                        <td className="px-3.5 py-2.5">
                                                            <div className="font-medium text-slate-900">
                                                                {m.paciente_nombre || "-"}
                                                            </div>
                                                            <div className="font-mono text-[11px] text-slate-500">
                                                                DNI {m.paciente_dni || "-"}
                                                            </div>
                                                        </td>
                                                        <td className="px-3.5 py-2.5">
                                                            <div className="flex flex-wrap items-center gap-1.5">
                                                                <span className="text-slate-800">
                                                                    {m.patologia || "-"}
                                                                </span>
                                                                {m.es_pompe_urgente && (
                                                                    <span className="rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-[10px] font-bold uppercase text-red-700">
                                                                        Urgente
                                                                    </span>
                                                                )}
                                                            </div>
                                                        </td>
                                                        <td className="px-3.5 py-2.5 text-[11px] text-slate-600">
                                                            {formatearFechaHora(
                                                                m.llegada_lab_central
                                                            )}
                                                        </td>
                                                        <td className="px-3.5 py-2.5">
                                                            <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-medium text-slate-700">
                                                                {m.estado_estudio || "-"}
                                                            </span>
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </section>
            </div>
        </div>
    );
}
