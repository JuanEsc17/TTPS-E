import { useCallback, useEffect, useMemo, useState } from "react";
import {
    emitirPresupuestoRequest,
    listarEstudiosPendientesPresupuestoRequest,
} from "../api/presupuestos";

const MENSAJES_ERROR = {
    PRESUPUESTO_YA_EMITIDO: "Este estudio ya tiene un presupuesto emitido. Actualizamos la lista.",
    ESTADO_ESTUDIO_INVALIDO: "El estudio ya no está en estado Creado. Actualizamos la lista.",
    ESTUDIO_NO_ENCONTRADO: "El estudio ya no existe. Actualizamos la lista.",
    ESTUDIO_SIN_GENES:
        "El estudio no tiene genes asociados. El médico debe completarlos antes de presupuestar.",
    ERROR_ENVIO_EMAIL:
        "No se pudo enviar el correo al paciente, así que el presupuesto no se emitió. Podés reintentar.",
};

const CODIGOS_QUE_RECARGAN = new Set([
    "PRESUPUESTO_YA_EMITIDO",
    "ESTADO_ESTUDIO_INVALIDO",
    "ESTUDIO_NO_ENCONTRADO",
]);

function soloDigitos(valor) {
    return String(valor || "").replace(/\D/g, "");
}

function formatearFecha(iso) {
    if (!iso) return "-";
    const fecha = new Date(iso);
    if (Number.isNaN(fecha.getTime())) return iso;
    return fecha.toLocaleDateString("es-AR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export default function PresupuestosAdminPage({ sesion }) {
    const token = sesion?.access_token;
    const esAdmin = sesion?.usuario?.rol === "administrativo";

    const [estudios, setEstudios] = useState([]);
    const [cargando, setCargando] = useState(Boolean(token && esAdmin));
    const [dniForm, setDniForm] = useState("");
    const [dniAplicado, setDniAplicado] = useState("");
    const [seleccionadoId, setSeleccionadoId] = useState(null);
    const [confirmando, setConfirmando] = useState(false);
    const [enviando, setEnviando] = useState(false);
    const [error, setError] = useState(null);
    const [resultadoExito, setResultadoExito] = useState(null);

    const aplicarEstudios = useCallback((lista) => {
        const items = Array.isArray(lista) ? lista : [];
        setEstudios(items);
        setSeleccionadoId((prev) =>
            prev && items.some((e) => e.estudio_id === prev) ? prev : items[0]?.estudio_id ?? null
        );
    }, []);

    const recargarLista = useCallback(
        async (dni = dniAplicado) => {
            if (!token || !esAdmin) return;
            setCargando(true);
            try {
                const data = await listarEstudiosPendientesPresupuestoRequest(token, { dni });
                aplicarEstudios(data);
            } catch (err) {
                setError({ mensaje: err.message, reintentable: false });
            } finally {
                setCargando(false);
            }
        },
        [token, esAdmin, dniAplicado, aplicarEstudios]
    );

    useEffect(() => {
        if (!token || !esAdmin) return;
        let cancelado = false;

        listarEstudiosPendientesPresupuestoRequest(token)
            .then((data) => {
                if (!cancelado) aplicarEstudios(data);
            })
            .catch((err) => {
                if (!cancelado) setError({ mensaje: err.message, reintentable: false });
            })
            .finally(() => {
                if (!cancelado) setCargando(false);
            });

        return () => {
            cancelado = true;
        };
    }, [token, esAdmin, aplicarEstudios]);

    const estudioActivo = useMemo(
        () => estudios.find((e) => e.estudio_id === seleccionadoId) || null,
        [estudios, seleccionadoId]
    );

    if (!esAdmin) {
        return (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
                Solo el Personal Administrativo puede emitir presupuestos.
            </div>
        );
    }

    function limpiarMensajes() {
        setError(null);
        setResultadoExito(null);
    }

    function handleFiltrar(e) {
        e.preventDefault();
        limpiarMensajes();
        setDniAplicado(dniForm);
        recargarLista(dniForm);
    }

    function handleLimpiar() {
        limpiarMensajes();
        setDniForm("");
        setDniAplicado("");
        recargarLista("");
    }

    async function handleEmitir() {
        if (!estudioActivo) return;
        limpiarMensajes();
        setEnviando(true);
        try {
            const resp = await emitirPresupuestoRequest({ token, estudioId: estudioActivo.estudio_id });
            setResultadoExito({
                ...resp,
                paciente_nombre: estudioActivo.paciente_nombre,
                paciente_dni: estudioActivo.paciente_dni,
            });
            setConfirmando(false);
            window.dispatchEvent(new Event("avisos:actualizar"));
            await recargarLista();
        } catch (err) {
            setError({
                mensaje: MENSAJES_ERROR[err.code] || err.message,
                reintentable: err.retryable,
            });
            setConfirmando(false);
            if (CODIGOS_QUE_RECARGAN.has(err.code)) await recargarLista();
        } finally {
            setEnviando(false);
        }
    }

    const sinGenes = estudioActivo && estudioActivo.cantidad_genes === 0;

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                        Personal administrativo · Presupuestos
                    </p>
                    <h1 className="font-titulo mt-1 text-2xl font-semibold text-slate-900 sm:text-3xl">
                        Emitir presupuestos
                    </h1>
                    <p className="mt-1 text-sm text-slate-600">
                        Estudios en estado <span className="font-semibold text-slate-800">Creado</span>{" "}
                        que todavía no tienen presupuesto. USD 500 hasta 5 genes y USD 30 por cada gen
                        adicional.
                    </p>
                </div>

                <button
                    type="button"
                    onClick={() => {
                        limpiarMensajes();
                        recargarLista();
                    }}
                    disabled={cargando}
                    className="rounded-xl border border-[#0B4F8A] bg-white px-4 py-2 text-xs font-semibold text-[#0B4F8A] transition hover:bg-[#EAF2FA] disabled:opacity-50"
                >
                    {cargando ? "Actualizando..." : "Actualizar lista"}
                </button>
            </div>

            <form
                onSubmit={handleFiltrar}
                aria-label="Filtrar estudios pendientes de presupuesto"
                className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs"
            >
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div className="sm:col-span-2">
                        <label
                            htmlFor="presupuesto-filtro-dni"
                            className="mb-1 block text-xs font-medium text-slate-700"
                        >
                            DNI del paciente
                        </label>
                        <input
                            id="presupuesto-filtro-dni"
                            type="text"
                            inputMode="numeric"
                            pattern="[0-9]*"
                            maxLength={12}
                            value={dniForm}
                            onChange={(e) => setDniForm(soloDigitos(e.target.value))}
                            placeholder="Solo números (ej: 30111333)"
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
                            onClick={handleLimpiar}
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
                    className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-medium text-red-700"
                >
                    <span>{error.mensaje}</span>
                    {error.reintentable && estudioActivo && (
                        <button
                            type="button"
                            onClick={handleEmitir}
                            disabled={enviando}
                            className="rounded-lg border border-red-300 bg-white px-3 py-1.5 font-semibold text-red-700 hover:bg-red-100 disabled:opacity-50"
                        >
                            {enviando ? "Reintentando..." : "Reintentar"}
                        </button>
                    )}
                </div>
            )}

            {resultadoExito && (
                <div
                    role="status"
                    className="rounded-2xl border border-emerald-200 bg-emerald-50 px-5 py-4 text-xs text-emerald-900"
                >
                    <p className="text-sm font-semibold">
                        Presupuesto #{resultadoExito.presupuesto_id} emitido por USD{" "}
                        {resultadoExito.monto_total_usd}
                    </p>
                    <p className="mt-1">
                        Estudio #{resultadoExito.estudio_id} · {resultadoExito.paciente_nombre}
                        {resultadoExito.paciente_dni ? ` · DNI ${resultadoExito.paciente_dni}` : ""} ·
                        Estado: <strong>{resultadoExito.estado_estudio}</strong>
                    </p>
                    <p className="mt-1 text-[11px] text-emerald-800">
                        {resultadoExito.porcentaje_cobertura_obra_social
                            ? `Se solicitó la autorización a la obra social (cobertura ${resultadoExito.porcentaje_cobertura_obra_social}%).`
                            : "Pago particular: el paciente ya puede abonarlo en un pago o en cuotas."}{" "}
                        Se avisó al paciente por la app y por correo.
                    </p>
                </div>
            )}

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                <aside
                    aria-label="Estudios pendientes de presupuesto"
                    className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs lg:col-span-6"
                >
                    <div className="flex items-center justify-between">
                        <h2 className="text-sm font-semibold text-slate-900">Pendientes de presupuesto</h2>
                        <span className="rounded-full bg-[#EAF2FA] px-2.5 py-0.5 text-[11px] font-semibold text-[#0B4F8A]">
                            {estudios.length}
                        </span>
                    </div>

                    {cargando ? (
                        <p className="mt-4 text-xs text-slate-500">Consultando estudios pendientes...</p>
                    ) : estudios.length === 0 ? (
                        <p className="mt-4 rounded-xl border border-dashed border-slate-200 p-5 text-xs text-slate-500">
                            No hay estudios en estado &ldquo;Creado&rdquo; pendientes de presupuesto
                            {dniAplicado ? " para el DNI ingresado" : ""}.
                        </p>
                    ) : (
                        <ul className="mt-4 space-y-2.5">
                            {estudios.map((est) => {
                                const seleccionado = est.estudio_id === seleccionadoId;
                                return (
                                    <li key={est.estudio_id}>
                                        <button
                                            type="button"
                                            aria-pressed={seleccionado}
                                            onClick={() => {
                                                setSeleccionadoId(est.estudio_id);
                                                setConfirmando(false);
                                                limpiarMensajes();
                                            }}
                                            className={`w-full rounded-xl border p-3.5 text-left transition focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] ${
                                                seleccionado
                                                    ? "border-[#0B4F8A] bg-[#EAF2FA]/60"
                                                    : "border-slate-200 hover:border-slate-300 hover:bg-slate-50/70"
                                            }`}
                                        >
                                            <div className="flex flex-wrap items-center justify-between gap-2">
                                                <span className="text-sm font-semibold text-slate-900">
                                                    Estudio #{est.estudio_id}
                                                </span>
                                                <div className="flex items-center gap-1.5">
                                                    {est.es_pompe_urgente && (
                                                        <span className="rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-700">
                                                            Pompe urgente
                                                        </span>
                                                    )}
                                                    <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold text-slate-700">
                                                        {est.obra_social ? est.obra_social.nombre : "Particular"}
                                                    </span>
                                                </div>
                                            </div>
                                            <p className="mt-1.5 text-xs font-medium text-slate-800">
                                                {est.paciente_nombre} · DNI {est.paciente_dni || "-"}
                                            </p>
                                            <p className="mt-0.5 text-[11px] text-slate-500">
                                                {est.patologia_nombre || "Patología"} · {est.cantidad_genes}{" "}
                                                {est.cantidad_genes === 1 ? "gen" : "genes"} · Alta:{" "}
                                                {formatearFecha(est.creado_en)}
                                            </p>
                                        </button>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </aside>

                <section
                    aria-label="Detalle del presupuesto"
                    className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs lg:col-span-6"
                >
                    <div className="mb-5 border-b border-slate-100 pb-3">
                        <h2 className="text-sm font-semibold text-slate-900">
                            {estudioActivo
                                ? `Presupuesto · Estudio #${estudioActivo.estudio_id}`
                                : "Detalle del presupuesto"}
                        </h2>
                    </div>

                    {!estudioActivo ? (
                        <div className="rounded-xl border border-dashed border-slate-200 p-6 text-center text-xs text-slate-500">
                            Seleccioná un estudio de la lista para ver el desglose y emitir su presupuesto.
                        </div>
                    ) : (
                        <div className="space-y-4">
                            <dl className="grid grid-cols-1 gap-3 rounded-xl border border-slate-200/80 bg-[#F8FAFC] p-4 text-xs sm:grid-cols-2">
                                <div>
                                    <dt className="text-[11px] font-medium text-slate-500">Paciente</dt>
                                    <dd className="mt-0.5 font-semibold text-slate-900">
                                        {estudioActivo.paciente_nombre}
                                    </dd>
                                </div>
                                <div>
                                    <dt className="text-[11px] font-medium text-slate-500">DNI</dt>
                                    <dd className="mt-0.5 font-mono font-semibold text-slate-900">
                                        {estudioActivo.paciente_dni || "-"}
                                    </dd>
                                </div>
                                <div>
                                    <dt className="text-[11px] font-medium text-slate-500">Médico tratante</dt>
                                    <dd className="mt-0.5 font-semibold text-slate-900">
                                        {estudioActivo.medico_nombre || "-"}
                                    </dd>
                                </div>
                                <div>
                                    <dt className="text-[11px] font-medium text-slate-500">Financiación</dt>
                                    <dd className="mt-0.5 font-semibold text-slate-900">
                                        {estudioActivo.obra_social
                                            ? `${estudioActivo.obra_social.nombre} (cobertura ${estudioActivo.obra_social.porcentaje_cobertura}%)`
                                            : "Particular"}
                                    </dd>
                                </div>
                            </dl>

                            {sinGenes ? (
                                <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
                                    Este estudio no tiene genes asociados. No se puede presupuestar hasta que el
                                    médico los complete.
                                </div>
                            ) : (
                                <table className="w-full text-xs">
                                    <caption className="sr-only">Desglose del presupuesto estimado</caption>
                                    <tbody className="divide-y divide-slate-100">
                                        <tr>
                                            <th scope="row" className="py-2 text-left font-normal text-slate-600">
                                                Precio base (hasta 5 genes)
                                            </th>
                                            <td className="py-2 text-right font-mono text-slate-900">
                                                USD {estudioActivo.precio_base_usd}
                                            </td>
                                        </tr>
                                        <tr>
                                            <th scope="row" className="py-2 text-left font-normal text-slate-600">
                                                Genes adicionales ({estudioActivo.genes_adicionales})
                                            </th>
                                            <td className="py-2 text-right font-mono text-slate-900">
                                                USD {estudioActivo.costo_adicional_usd}
                                            </td>
                                        </tr>
                                        <tr>
                                            <th scope="row" className="py-2 text-left font-semibold text-slate-900">
                                                Total ({estudioActivo.cantidad_genes} genes)
                                            </th>
                                            <td className="py-2 text-right font-mono text-sm font-semibold text-[#0B4F8A]">
                                                USD {estudioActivo.monto_estimado_usd}
                                            </td>
                                        </tr>
                                    </tbody>
                                </table>
                            )}

                            <div className="rounded-xl border border-cyan-200/80 bg-cyan-50/60 px-4 py-3 text-[11px] text-[#0B4F8A]">
                                {estudioActivo.obra_social ? (
                                    <>
                                        Al emitirlo, el estudio pasa a <strong>Pendiente de autorización</strong> y se
                                        solicita la autorización a <strong>{estudioActivo.obra_social.nombre}</strong>.
                                    </>
                                ) : (
                                    <>
                                        Al emitirlo, el estudio queda en <strong>Creado</strong> a la espera del pago
                                        particular del paciente (en un pago o en cuotas).
                                    </>
                                )}{" "}
                                El paciente recibe un aviso en la app y un correo.
                            </div>

                            <div className="border-t border-slate-100 pt-3">
                                {enviando ? (
                                    <p role="status" aria-live="polite" className="text-right text-xs font-medium text-slate-600">
                                        Calculando presupuesto...
                                    </p>
                                ) : !confirmando ? (
                                    <div className="flex justify-end">
                                        <button
                                            type="button"
                                            onClick={() => {
                                                limpiarMensajes();
                                                setConfirmando(true);
                                            }}
                                            disabled={sinGenes}
                                            className="inline-flex items-center justify-center rounded-xl bg-[#0B4F8A] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#093E6D] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] focus-visible:ring-offset-2 disabled:opacity-50"
                                        >
                                            Emitir presupuesto
                                        </button>
                                    </div>
                                ) : (
                                    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 p-3.5 text-xs text-amber-950">
                                        <span className="font-medium">
                                            ¿Confirmás emitir el presupuesto del Estudio #{estudioActivo.estudio_id} por
                                            USD {estudioActivo.monto_estimado_usd}?
                                        </span>
                                        <div className="flex items-center gap-2">
                                            <button
                                                type="button"
                                                onClick={() => setConfirmando(false)}
                                                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 font-medium text-slate-700 hover:bg-slate-50"
                                            >
                                                Cancelar
                                            </button>
                                            <button
                                                type="button"
                                                onClick={handleEmitir}
                                                className="rounded-lg bg-[#0B4F8A] px-3.5 py-1.5 font-semibold text-white hover:bg-[#093E6D]"
                                            >
                                                Confirmar emisión
                                            </button>
                                        </div>
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