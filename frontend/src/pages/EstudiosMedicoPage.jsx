import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listarEstudiosRequest } from "../api/estudios";

export default function EstudiosMedicoPage({ sesion }) {
    const [estudios, setEstudios] = useState([]);
    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState("");

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
                                        <th className="pb-3">Estado</th>
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
                                            <td className="py-3">
                                                <span className="inline-flex rounded-full bg-[#EAF2FA] px-2.5 py-0.5 text-[11px] font-semibold text-[#0B4F8A]">
                                                    {est.estado}
                                                </span>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            </section>
        </div>
    );
}
