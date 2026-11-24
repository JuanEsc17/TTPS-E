import { useCallback, useEffect, useMemo, useState } from "react";
import {
    listarEstudiosRemuestreablesRequest,
    solicitarRemuestreoRequest,
} from "../api/muestras";

const MOTIVOS_DESCARTE = [
    { value: "adn_insuficiente", label: "ADN insuficiente" },
    { value: "desnaturalizada", label: "Muestra desnaturalizada" },
];

const FILTROS_INICIALES = {
    dni: "",
    estudioId: "",
};

function soloDigitos(valor) {
    return String(valor || "").replace(/\D/g, "");
}

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

export default function RemuestreoAdminPage({ sesion }) {
    const token = sesion?.access_token;
    const esAdmin = sesion?.usuario?.rol === "administrativo";

    const [estudios, setEstudios] = useState([]);
    const [cargando, setCargando] = useState(Boolean(token && esAdmin));
    const [filtrosForm, setFiltrosForm] = useState(FILTROS_INICIALES);
    const [estudioSeleccionadoId, setEstudioSeleccionadoId] = useState(null);

    const [motivoDescarte, setMotivoDescarte] = useState("adn_insuficiente");
    const [observacionesCalidad, setObservacionesCalidad] = useState("");
    const [motivo, setMotivo] = useState("");
    const [confirmando, setConfirmando] = useState(false);
    const [enviando, setEnviando] = useState(false);
    const [error, setError] = useState("");
    const [resultadoExito, setResultadoExito] = useState(null);

    const aplicarEstudios = useCallback((lista) => {
        const items = Array.isArray(lista) ? lista : [];
        setEstudios(items);
        setEstudioSeleccionadoId((prev) => {
            if (prev && items.some((e) => e.estudio_id === prev)) {
                return prev;
            }
            return items[0] ? items[0].estudio_id : null;
        });
    }, []);

    const recargarLista = useCallback(async () => {
        if (!token || !esAdmin) return;
        setCargando(true);
        setError("");
        try {
            const data = await listarEstudiosRemuestreablesRequest(token);
            aplicarEstudios(data);
        } catch (err) {
            setError(err.message);
        } finally {
            setCargando(false);
        }
    }, [token, esAdmin, aplicarEstudios]);

    useEffect(() => {
        if (!token || !esAdmin) return;
        let cancelado = false;

        listarEstudiosRemuestreablesRequest(token)
            .then((data) => {
                if (!cancelado) {
                    aplicarEstudios(data);
                    setError("");
                }
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
    }, [token, esAdmin, aplicarEstudios]);

    const estudiosVisibles = useMemo(() => {
        const dniFiltro = filtrosForm.dni.trim();
        const estudioFiltro = filtrosForm.estudioId.trim();
        return estudios.filter((est) => {
            if (dniFiltro && !String(est.paciente_dni || "").includes(dniFiltro)) {
                return false;
            }
            if (estudioFiltro && !String(est.estudio_id || "").includes(estudioFiltro)) {
                return false;
            }
            return true;
        });
    }, [estudios, filtrosForm.dni, filtrosForm.estudioId]);

    const estudioActivo = useMemo(() => {
        if (estudiosVisibles.length === 0) return null;
        return (
            estudiosVisibles.find((e) => e.estudio_id === estudioSeleccionadoId) ||
            estudiosVisibles[0]
        );
    }, [estudiosVisibles, estudioSeleccionadoId]);

    if (!esAdmin) {
        return (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
                Solo el Personal Administrativo puede gestionar solicitudes de remuestreo.
            </div>
        );
    }

    function handleAplicarFiltros(e) {
        e.preventDefault();
        setError("");
        setResultadoExito(null);
        recargarLista();
    }

    function handleLimpiarFiltros() {
        setError("");
        setResultadoExito(null);
        setFiltrosForm(FILTROS_INICIALES);
    }

    function handleSolicitarConfirmacion(e) {
        e.preventDefault();
        setError("");
        setResultadoExito(null);
        if (!estudioActivo) return;
        if (!motivo.trim()) {
            setError("Indicá el motivo del retroceso a remuestreo.");
            return;
        }
        setConfirmando(true);
    }

    async function handleConfirmarRemuestreo() {
        if (!estudioActivo) return;
        setError("");
        setEnviando(true);
        try {
            const resp = await solicitarRemuestreoRequest({
                token,
                estudioId: estudioActivo.estudio_id,
                motivoDescarte,
                observacionesCalidad,
                motivo,
            });
            setResultadoExito({
                ...resp,
                paciente_nombre: estudioActivo.paciente_nombre,
                paciente_dni: estudioActivo.paciente_dni,
            });
            setConfirmando(false);
            setObservacionesCalidad("");
            setMotivo("");
            window.dispatchEvent(new Event("avisos:actualizar"));
            await recargarLista();
        } catch (err) {
            setError(err.message);
            setConfirmando(false);
        } finally {
            setEnviando(false);
        }
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                        Personal administrativo · Control de calidad
                    </p>
                    <h1 className="font-titulo mt-1 text-2xl font-semibold text-slate-900 sm:text-3xl">
                        Remuestreo por calidad de muestra
                    </h1>
                    <p className="mt-1 text-sm text-slate-600">
                        Registrá reportes de Corea por ADN insuficiente o muestra desnaturalizada para
                        retroceder el estudio a{" "}
                        <span className="font-semibold text-slate-800">Remuestreo requerido</span> sin
                        costo adicional.
                    </p>
                </div>

                <button
                    type="button"
                    onClick={() => {
                        setResultadoExito(null);
                        recargarLista();
                    }}
                    disabled={cargando}
                    className="rounded-xl border border-[#0B4F8A] bg-white px-4 py-2 text-xs font-semibold text-[#0B4F8A] transition hover:bg-[#EAF2FA] disabled:opacity-50"
                >
                    {cargando ? "Actualizando..." : "Actualizar lista"}
                </button>
            </div>

            {/* Filtros */}
            <form
                onSubmit={handleAplicarFiltros}
                aria-label="Filtros de estudios elegibles para remuestreo"
                className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs"
            >
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div>
                        <label
                            htmlFor="remuestreo-filtro-dni"
                            className="mb-1 block text-xs font-medium text-slate-700"
                        >
                            DNI del paciente
                        </label>
                        <input
                            id="remuestreo-filtro-dni"
                            type="text"
                            inputMode="numeric"
                            pattern="[0-9]*"
                            maxLength={12}
                            value={filtrosForm.dni}
                            onChange={(e) => {
                                const limpio = soloDigitos(e.target.value);
                                setFiltrosForm((prev) => ({ ...prev, dni: limpio }));
                            }}
                            placeholder="Solo números (ej: 61100101)"
                            className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3 py-2 text-xs text-slate-900 focus:border-[#0B4F8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0B4F8A]/15"
                        />
                    </div>

                    <div>
                        <label
                            htmlFor="remuestreo-filtro-estudio-id"
                            className="mb-1 block text-xs font-medium text-slate-700"
                        >
                            ID de estudio
                        </label>
                        <input
                            id="remuestreo-filtro-estudio-id"
                            type="text"
                            inputMode="numeric"
                            pattern="[0-9]*"
                            maxLength={10}
                            value={filtrosForm.estudioId}
                            onChange={(e) => {
                                const limpio = soloDigitos(e.target.value);
                                setFiltrosForm((prev) => ({ ...prev, estudioId: limpio }));
                            }}
                            placeholder="Solo números (ej: 25)"
                            className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3 py-2 text-xs text-slate-900 focus:border-[#0B4F8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0B4F8A]/15"
                        />
                    </div>

                    <div className="flex items-end gap-2">
                        <button
                            type="submit"
                            disabled={cargando}
                            className="flex-1 rounded-xl bg-[#0B4F8A] px-3 py-2 text-xs font-semibold text-white transition hover:bg-[#093E6D] disabled:opacity-50"
                        >
                            Filtrar
                        </button>
                        <button
                            type="button"
                            onClick={handleLimpiarFiltros}
                            disabled={cargando}
                            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
                        >
                            Limpiar
                        </button>
                    </div>
                </div>
            </form>

            {error && (
                <div
                    role="alert"
                    className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-medium text-red-700"
                >
                    {error}
                </div>
            )}

            {resultadoExito && (
                <div
                    role="status"
                    className="rounded-2xl border border-emerald-200 bg-emerald-50 px-5 py-4 text-xs text-emerald-900"
                >
                    <p className="text-sm font-semibold">
                        Remuestreo registrado para Estudio #{resultadoExito.estudio_id}
                    </p>
                    <p className="mt-1">
                        {resultadoExito.paciente_nombre || "Paciente"}{" "}
                        {resultadoExito.paciente_dni ? `· DNI ${resultadoExito.paciente_dni}` : ""} ·{" "}
                        {resultadoExito.estado_anterior} →{" "}
                        <strong>{resultadoExito.estado_nuevo}</strong>.
                    </p>
                    <p className="mt-1 text-[11px] text-emerald-800">
                        Muestra descartada #{resultadoExito.muestra_descartada_id} (
                        {resultadoExito.motivo_descarte})
                        {resultadoExito.sample_set_id
                            ? ` · SampleSet #${resultadoExito.sample_set_id} preservado sin alteraciones`
                            : ""}{" "}
                        · Avisos enviados al paciente y al médico tratante.
                    </p>
                </div>
            )}

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                {/* Columna izquierda: Estudios elegibles */}
                <aside
                    aria-label="Estudios elegibles para remuestreo"
                    className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs lg:col-span-6"
                >
                    <div className="flex items-center justify-between">
                        <h2 className="text-sm font-semibold text-slate-900">
                            Estudios en viaje a Corea
                        </h2>
                        <span className="rounded-full bg-[#EAF2FA] px-2.5 py-0.5 text-[11px] font-semibold text-[#0B4F8A]">
                            {estudiosVisibles.length}
                        </span>
                    </div>

                    {cargando ? (
                        <p className="mt-4 text-xs text-slate-500">
                            Consultando estudios en viaje a Corea...
                        </p>
                    ) : estudiosVisibles.length === 0 ? (
                        <p className="mt-4 rounded-xl border border-dashed border-slate-200 p-5 text-xs text-slate-500">
                            No hay estudios en estado &ldquo;En viaje a Corea&rdquo; con muestra
                            vigente para los filtros aplicados.
                        </p>
                    ) : (
                        <ul className="mt-4 space-y-2.5">
                            {estudiosVisibles.map((est) => {
                                const seleccionado = estudioActivo?.estudio_id === est.estudio_id;
                                return (
                                    <li key={est.estudio_id}>
                                        <button
                                            type="button"
                                            onClick={() => {
                                                setEstudioSeleccionadoId(est.estudio_id);
                                                setConfirmando(false);
                                                setError("");
                                                setResultadoExito(null);
                                            }}
                                            className={`w-full rounded-xl border p-3.5 text-left transition focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] ${
                                                seleccionado
                                                    ? "border-[#0B4F8A] bg-[#EAF2FA]/60"
                                                    : "border-slate-200 hover:border-slate-300 hover:bg-slate-50/70"
                                            }`}
                                        >
                                            <div className="flex flex-wrap items-center justify-between gap-2">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-sm font-semibold text-slate-900">
                                                        Estudio #{est.estudio_id}
                                                    </span>
                                                    {est.muestra_vigente?.sample_set_id && (
                                                        <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
                                                            SampleSet #{est.muestra_vigente.sample_set_id}
                                                        </span>
                                                    )}
                                                </div>
                                                <div className="flex items-center gap-1.5">
                                                    {est.es_pompe_urgente && (
                                                        <span className="rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-700">
                                                            Pompe urgente
                                                        </span>
                                                    )}
                                                    <span className="rounded-full border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[10px] font-semibold text-indigo-800">
                                                        {est.estado_estudio}
                                                    </span>
                                                </div>
                                            </div>

                                            <p className="mt-1.5 text-xs font-medium text-slate-800">
                                                {est.paciente_nombre || "Paciente"} · DNI{" "}
                                                {est.paciente_dni || "-"}
                                            </p>
                                            <p className="mt-0.5 text-[11px] text-slate-500">
                                                {est.patologia_nombre || "Patología"} · Muestra #
                                                {est.muestra_vigente?.muestra_id || "-"} · Toma:{" "}
                                                {formatearFechaHora(est.muestra_vigente?.tomada_en)}
                                            </p>
                                        </button>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </aside>

                {/* Columna derecha: Formulario de remuestreo */}
                <section
                    aria-label="Formulario de solicitud de remuestreo"
                    className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs lg:col-span-6"
                >
                    <div className="mb-5 flex items-center justify-between border-b border-slate-100 pb-3">
                        <h2 className="text-sm font-semibold text-slate-900">
                            {estudioActivo
                                ? `Declarar remuestreo · Estudio #${estudioActivo.estudio_id}`
                                : "Detalle del estudio"}
                        </h2>
                        <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-medium text-slate-600">
                            → Remuestreo requerido
                        </span>
                    </div>

                    {!estudioActivo ? (
                        <div className="rounded-xl border border-dashed border-slate-200 p-6 text-center text-xs text-slate-500">
                            Seleccioná un estudio de la lista para registrar un descarte por calidad
                            y habilitar un nuevo turno de extracción sin cargo.
                        </div>
                    ) : (
                        <form onSubmit={handleSolicitarConfirmacion} className="space-y-4">
                            <dl className="grid grid-cols-1 gap-3 rounded-xl border border-slate-200/80 bg-[#F8FAFC] p-4 text-xs sm:grid-cols-2">
                                <div>
                                    <dt className="text-[11px] font-medium text-slate-500">Paciente</dt>
                                    <dd className="mt-0.5 font-semibold text-slate-900">
                                        {estudioActivo.paciente_nombre || "-"}
                                    </dd>
                                </div>
                                <div>
                                    <dt className="text-[11px] font-medium text-slate-500">DNI</dt>
                                    <dd className="mt-0.5 font-mono font-semibold text-slate-900">
                                        {estudioActivo.paciente_dni || "-"}
                                    </dd>
                                </div>
                                <div>
                                    <dt className="text-[11px] font-medium text-slate-500">
                                        Médico tratante
                                    </dt>
                                    <dd className="mt-0.5 font-semibold text-slate-900">
                                        {estudioActivo.medico_nombre || "-"}
                                    </dd>
                                </div>
                                <div>
                                    <dt className="text-[11px] font-medium text-slate-500">
                                        Muestra vigente / Lote
                                    </dt>
                                    <dd className="mt-0.5 font-semibold text-slate-900">
                                        Muestra #{estudioActivo.muestra_vigente?.muestra_id || "-"}{" "}
                                        {estudioActivo.muestra_vigente?.sample_set_id
                                            ? `· SampleSet #${estudioActivo.muestra_vigente.sample_set_id}`
                                            : "· Sin lote"}
                                    </dd>
                                </div>
                            </dl>

                            <div>
                                <label
                                    htmlFor="motivo-descarte"
                                    className="mb-1.5 block text-xs font-medium text-slate-700"
                                >
                                    Motivo técnico de descarte
                                </label>
                                <select
                                    id="motivo-descarte"
                                    value={motivoDescarte}
                                    onChange={(e) => {
                                        setMotivoDescarte(e.target.value);
                                        setConfirmando(false);
                                    }}
                                    className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-2 text-xs text-slate-900 focus:border-[#0B4F8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0B4F8A]/15"
                                >
                                    {MOTIVOS_DESCARTE.map((item) => (
                                        <option key={item.value} value={item.value}>
                                            {item.label}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <div>
                                <label
                                    htmlFor="observaciones-calidad"
                                    className="mb-1.5 block text-xs font-medium text-slate-700"
                                >
                                    Observaciones de calidad (opcional)
                                </label>
                                <textarea
                                    id="observaciones-calidad"
                                    rows={2}
                                    maxLength={500}
                                    value={observacionesCalidad}
                                    onChange={(e) => {
                                        setObservacionesCalidad(e.target.value);
                                        setConfirmando(false);
                                    }}
                                    placeholder="Ej: Muestra hemolizada al arribo en Corea según reporte lote #7"
                                    className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-2 text-xs text-slate-900 placeholder:text-slate-400 focus:border-[#0B4F8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0B4F8A]/15"
                                />
                            </div>

                            <div>
                                <label
                                    htmlFor="motivo-remuestreo"
                                    className="mb-1.5 block text-xs font-medium text-slate-700"
                                >
                                    Motivo del retroceso (auditoría)
                                </label>
                                <textarea
                                    id="motivo-remuestreo"
                                    rows={2}
                                    maxLength={500}
                                    required
                                    value={motivo}
                                    onChange={(e) => {
                                        setMotivo(e.target.value);
                                        setConfirmando(false);
                                    }}
                                    placeholder="Ej: Reporte de baja calidad recibido desde Corea; requiere nueva extracción"
                                    className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-2 text-xs text-slate-900 placeholder:text-slate-400 focus:border-[#0B4F8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0B4F8A]/15"
                                />
                            </div>

                            <div className="rounded-xl border border-cyan-200/80 bg-cyan-50/60 px-4 py-3 text-[11px] text-[#0B4F8A]">
                                Solo retrocede el <strong>Estudio #{estudioActivo.estudio_id}</strong>{" "}
                                a <strong>Remuestreo requerido</strong>: conserva intacto el{" "}
                                <strong>SampleSet</strong> histórico y el pago/cuotas del paciente, y
                                notifica al paciente y al médico tratante.
                            </div>

                            <div className="border-t border-slate-100 pt-3">
                                {!confirmando ? (
                                    <div className="flex justify-end">
                                        <button
                                            type="submit"
                                            disabled={enviando}
                                            className="inline-flex items-center justify-center rounded-xl bg-[#0B4F8A] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#093E6D] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] focus-visible:ring-offset-2 disabled:opacity-50"
                                        >
                                            Solicitar remuestreo
                                        </button>
                                    </div>
                                ) : (
                                    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 p-3.5 text-xs text-amber-950">
                                        <span className="font-medium">
                                            ¿Confirmás descartar la Muestra #
                                            {estudioActivo.muestra_vigente?.muestra_id} y retroceder el
                                            Estudio #{estudioActivo.estudio_id}?
                                        </span>
                                        <div className="flex items-center gap-2">
                                            <button
                                                type="button"
                                                onClick={() => setConfirmando(false)}
                                                disabled={enviando}
                                                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                                            >
                                                Cancelar
                                            </button>
                                            <button
                                                type="button"
                                                onClick={handleConfirmarRemuestreo}
                                                disabled={enviando}
                                                className="rounded-lg bg-amber-700 px-3.5 py-1.5 font-semibold text-white hover:bg-amber-800 disabled:opacity-50"
                                            >
                                                {enviando
                                                    ? "Registrando remuestreo..."
                                                    : "Confirmar remuestreo"}
                                            </button>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </form>
                    )}
                </section>
            </div>
        </div>
    );
}
