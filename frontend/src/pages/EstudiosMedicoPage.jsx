import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
    consultarEstudioFamiliarVinculadoRequest,
    listarEstudiosFamiliaresVinculadosRequest,
    listarEstudiosRequest,
} from "../api/estudios";

export default function EstudiosMedicoPage({ sesion }) {
    const [estudios, setEstudios] = useState([]);
    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState("");

    // Escenario 41: estudios de familiares vinculados
    const [estudioSeleccionado, setEstudioSeleccionado] = useState(null);
    const [vinculosFamiliares, setVinculosFamiliares] = useState([]);
    const [cargandoVinculos, setCargandoVinculos] = useState(false);
    const [errorVinculos, setErrorVinculos] = useState("");
    const [detalleVinculado, setDetalleVinculado] = useState(null);
    const [cargandoDetalle, setCargandoDetalle] = useState(false);

    async function cargar() {
        setCargando(true);
        setError("");
        try {
            const lista = await listarEstudiosRequest(sesion?.access_token);
            setEstudios(lista || []);
        } catch (err) {
            setError(err.message);
        } finally {
            setCargando(false);
        }
    }

    useEffect(() => {
        if (sesion?.access_token) {
            cargar();
        }
    }, [sesion?.access_token]);

    async function abrirVinculosFamiliares(est) {
        setEstudioSeleccionado(est);
        setVinculosFamiliares([]);
        setDetalleVinculado(null);
        setErrorVinculos("");
        setCargandoVinculos(true);
        try {
            const lista = await listarEstudiosFamiliaresVinculadosRequest(
                sesion?.access_token,
                est.estudio_id
            );
            setVinculosFamiliares(lista || []);
        } catch (err) {
            setErrorVinculos(err.message);
        } finally {
            setCargandoVinculos(false);
        }
    }

    async function verDetalleVinculado(estudioRelacionadoId) {
        if (!estudioSeleccionado) return;
        setErrorVinculos("");
        setCargandoDetalle(true);
        try {
            const det = await consultarEstudioFamiliarVinculadoRequest(
                sesion?.access_token,
                estudioSeleccionado.estudio_id,
                estudioRelacionadoId
            );
            setDetalleVinculado(det);
        } catch (err) {
            setErrorVinculos(err.message);
        } finally {
            setCargandoDetalle(false);
        }
    }

    function cerrarPanelVinculos() {
        setEstudioSeleccionado(null);
        setVinculosFamiliares([]);
        setDetalleVinculado(null);
        setErrorVinculos("");
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                        Gestión clínica · Escenario E2
                    </p>
                    <h1 className="font-titulo mt-1 text-2xl font-semibold text-slate-900">
                        Estudios de exoma clínico
                    </h1>
                </div>
                <Link
                    to="/medico/estudios/nuevo"
                    className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-[#0B4F8A] to-[#0E7490] px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:from-[#093E6D] hover:to-[#0B5E75]"
                >
                    + Solicitar nuevo estudio
                </Link>
            </div>

            <section className="tarjeta-cristal">
                <div className="h-1.5 w-full bg-gradient-to-r from-[#062846] via-[#0B4F8A] to-[#0891B2]" />
                <div className="p-6">
                    {cargando ? (
                        <p className="text-sm text-slate-500">Cargando estudios...</p>
                    ) : error ? (
                        <div className="flex items-center justify-between rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700">
                            <span>{error}</span>
                            <button type="button" onClick={cargar} className="font-semibold underline">
                                Reintentar
                            </button>
                        </div>
                    ) : estudios.length === 0 ? (
                        <div className="py-8 text-center">
                            <p className="text-sm font-medium text-slate-700">
                                Todavía no solicitaste estudios de exoma clínico.
                            </p>
                            <p className="mt-1 text-xs text-slate-500">
                                Seleccioná un paciente registrado, su patología sospechada y los genes a secuenciar.
                            </p>
                            <Link
                                to="/medico/estudios/nuevo"
                                className="mt-4 inline-flex items-center rounded-xl bg-[#0B4F8A] px-4 py-2 text-xs font-medium text-white hover:bg-[#093E6D]"
                            >
                                Solicitar primer estudio →
                            </Link>
                        </div>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="w-full text-left text-sm">
                                <thead>
                                    <tr className="border-b border-slate-200/80 text-xs font-semibold uppercase tracking-wider text-slate-500">
                                        <th className="pb-3 pr-4">#</th>
                                        <th className="pb-3 pr-4">Paciente</th>
                                        <th className="pb-3 pr-4">Patología</th>
                                        <th className="pb-3 pr-4">Cobertura</th>
                                        <th className="pb-3 pr-4">Genes</th>
                                        <th className="pb-3 pr-4">Estado</th>
                                        <th className="pb-3 text-right">Familiares vinculados</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-200/60">
                                    {estudios.map((est) => (
                                        <tr key={est.estudio_id} className="text-xs text-slate-700">
                                            <td className="py-3 pr-4 font-mono font-semibold text-slate-900">
                                                #{est.estudio_id}
                                            </td>
                                            <td className="py-3 pr-4">
                                                <p className="font-semibold text-slate-900">{est.paciente_nombre}</p>
                                                <p className="font-mono text-[11px] text-slate-500">DNI {est.paciente_dni}</p>
                                            </td>
                                            <td className="py-3 pr-4">
                                                <span className="font-medium text-[#0B4F8A]">{est.patologia_nombre}</span>
                                                {est.es_pompe_urgente && (
                                                    <span className="ml-2 inline-flex rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-semibold text-red-700">
                                                        Pompe urgente
                                                    </span>
                                                )}
                                            </td>
                                            <td className="py-3 pr-4">{est.obra_social_nombre}</td>
                                            <td className="py-3 pr-4">
                                                <span className="font-semibold">{est.cantidad_genes_total}</span> genes
                                                {est.quiere_hallazgos_secundarios && (
                                                    <span className="ml-1.5 text-[11px] text-cyan-700">
                                                        (+ ACMG)
                                                    </span>
                                                )}
                                            </td>
                                            <td className="py-3 pr-4">
                                                <span className="inline-flex rounded-full bg-[#EAF2FA] px-2.5 py-0.5 text-[11px] font-semibold text-[#0B4F8A]">
                                                    {est.estado}
                                                </span>
                                            </td>
                                            <td className="py-3 text-right">
                                                <button
                                                    type="button"
                                                    onClick={() => abrirVinculosFamiliares(est)}
                                                    className="rounded-lg border border-[#0B4F8A]/30 bg-white px-2.5 py-1 text-[11px] font-semibold text-[#0B4F8A] transition hover:bg-[#EAF2FA]"
                                                >
                                                    Ver vinculados
                                                </button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            </section>

            {estudioSeleccionado && (
                <section className="tarjeta-cristal">
                    <div className="h-1.5 w-full bg-gradient-to-r from-[#0B4F8A] to-[#0891B2]" />
                    <div className="space-y-4 p-6">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                            <div>
                                <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                                    Escenario E41 · Estudio #{estudioSeleccionado.estudio_id}
                                </p>
                                <h2 className="font-titulo text-lg font-semibold text-slate-900">
                                    Estudios de familiares vinculados · {estudioSeleccionado.paciente_nombre}
                                </h2>
                            </div>
                            <button
                                type="button"
                                onClick={cerrarPanelVinculos}
                                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
                            >
                                Cerrar
                            </button>
                        </div>

                        {errorVinculos && (
                            <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-medium text-red-700">
                                {errorVinculos}
                            </div>
                        )}

                        {cargandoVinculos ? (
                            <p className="text-xs text-slate-500">Buscando estudios de familiares vinculados...</p>
                        ) : vinculosFamiliares.length === 0 ? (
                            <p className="rounded-xl border border-slate-200/80 bg-[#E6EFF7]/50 px-4 py-3 text-xs text-slate-600">
                                No hay estudios de familiares vinculados para este paciente. Si cargás el DNI de sus familiares en el familiograma y esos familiares tienen estudios en el sistema, se vincularán automáticamente.
                            </p>
                        ) : (
                            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                                <ul className="space-y-2.5">
                                    {vinculosFamiliares.map((v) => {
                                        const activo = detalleVinculado?.estudio_id === v.estudio_relacionado_id;
                                        return (
                                            <li
                                                key={v.estudio_relacionado_id}
                                                className={`flex items-center justify-between gap-3 rounded-xl border p-3.5 text-xs transition ${
                                                    activo
                                                        ? "border-[#0B4F8A] bg-[#EAF2FA]/60"
                                                        : "border-slate-200/80 bg-white/80"
                                                }`}
                                            >
                                                <div>
                                                    <p className="font-semibold text-slate-900">
                                                        Estudio #{v.estudio_relacionado_id} · {v.paciente_nombre}
                                                    </p>
                                                    <p className="mt-0.5 text-slate-600">
                                                        Parentesco: <span className="capitalize font-medium">{v.parentesco}</span> · {v.patologia_nombre}
                                                    </p>
                                                    <div className="mt-1.5 flex flex-wrap gap-2">
                                                        <span className="inline-flex rounded-full bg-[#EAF2FA] px-2 py-0.5 text-[10px] font-semibold text-[#0B4F8A]">
                                                            {v.estado}
                                                        </span>
                                                        <span
                                                            className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                                                                v.tiene_resultado
                                                                    ? "bg-emerald-100 text-emerald-700"
                                                                    : "bg-slate-100 text-slate-600"
                                                            }`}
                                                        >
                                                            {v.tiene_resultado ? "Con resultado" : "Sin resultado aún"}
                                                        </span>
                                                    </div>
                                                </div>
                                                <button
                                                    type="button"
                                                    onClick={() => verDetalleVinculado(v.estudio_relacionado_id)}
                                                    className="shrink-0 rounded-lg bg-[#0B4F8A] px-3 py-1.5 text-[11px] font-semibold text-white hover:bg-[#093E6D]"
                                                >
                                                    Ver detalle
                                                </button>
                                            </li>
                                        );
                                    })}
                                </ul>

                                <div className="rounded-xl border border-slate-200/80 bg-white/85 p-4 text-xs">
                                    {cargandoDetalle ? (
                                        <p className="text-slate-500">Cargando detalle genético...</p>
                                    ) : !detalleVinculado ? (
                                        <p className="text-slate-500">
                                            Seleccioná &ldquo;Ver detalle&rdquo; en un estudio vinculado para consultar sus genes y resultados (sin datos de pago).
                                        </p>
                                    ) : (
                                        <div className="space-y-3">
                                            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200/70 pb-2">
                                                <div>
                                                    <h3 className="font-semibold text-slate-900">
                                                        Estudio #{detalleVinculado.estudio_id} · {detalleVinculado.paciente_nombre}
                                                    </h3>
                                                    <p className="text-[11px] text-slate-600">
                                                        Parentesco: <span className="capitalize">{detalleVinculado.parentesco}</span> · {detalleVinculado.patologia_nombre}
                                                    </p>
                                                </div>
                                                <span className="inline-flex rounded-full bg-[#EAF2FA] px-2.5 py-0.5 text-[11px] font-semibold text-[#0B4F8A]">
                                                    {detalleVinculado.estado}
                                                </span>
                                            </div>

                                            <div>
                                                <p className="mb-1.5 font-semibold text-slate-700">Genes analizados</p>
                                                {detalleVinculado.genes?.length > 0 ? (
                                                    <div className="flex flex-wrap gap-1.5">
                                                        {detalleVinculado.genes.map((g, i) => (
                                                            <span
                                                                key={`${g.simbolo}-${i}`}
                                                                className="rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-[11px] text-slate-800"
                                                            >
                                                                {g.simbolo} <span className="text-slate-400">({g.origen})</span>
                                                            </span>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <p className="text-slate-500">Sin genes registrados.</p>
                                                )}
                                            </div>

                                            <div>
                                                <p className="mb-1.5 font-semibold text-slate-700">Resultados bioinformáticos</p>
                                                {detalleVinculado.resultados?.length > 0 ? (
                                                    <ul className="space-y-1.5">
                                                        {detalleVinculado.resultados.map((res) => (
                                                            <li
                                                                key={res.analisis_id}
                                                                className="flex items-center justify-between rounded-lg border border-slate-200/70 bg-slate-50/70 px-3 py-1.5"
                                                            >
                                                                <span>Análisis #{res.analisis_id} ({res.tipo})</span>
                                                                <span
                                                                    className={`font-semibold ${
                                                                        res.positivo ? "text-emerald-700" : "text-slate-600"
                                                                    }`}
                                                                >
                                                                    {res.positivo ? "Positivo" : "Negativo"}
                                                                </span>
                                                            </li>
                                                        ))}
                                                    </ul>
                                                ) : (
                                                    <p className="text-slate-500">Todavía no hay resultados cargados para este estudio.</p>
                                                )}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                </section>
            )}
        </div>
    );
}
