import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listarPacientesRequest } from "../api/pacientes";

export default function PacientesMedicoPage({ sesion }) {
    const token = sesion?.access_token;
    const [recargaId, setRecargaId] = useState(0);
    const [estado, setEstado] = useState({ recargaId: -1, pacientes: [], error: "" });

    useEffect(() => {
        if (!token) return;
        let cancelado = false;
        listarPacientesRequest(token)
            .then((lista) => {
                if (!cancelado) setEstado({ recargaId, pacientes: lista || [], error: "" });
            })
            .catch((err) => {
                if (!cancelado) {
                    setEstado({
                        recargaId,
                        pacientes: [],
                        error: err.message || "No se pudieron cargar los pacientes.",
                    });
                }
            });
        return () => {
            cancelado = true;
        };
    }, [token, recargaId]);

    const cargando = Boolean(token) && estado.recargaId !== recargaId;
    const pacientes = estado.pacientes;
    const error = estado.recargaId === recargaId ? estado.error : "";
    const cargar = () => setRecargaId((n) => n + 1);

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                        Gestión clínica · Médicos y consultas autorizadas
                    </p>
                    <h1 className="font-titulo mt-1 text-2xl font-semibold text-slate-900">
                        Pacientes autorizados
                    </h1>
                </div>
                <Link
                    to="/medico/pacientes/nuevo"
                    className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-[#0B4F8A] to-[#0E7490] px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:from-[#093E6D] hover:to-[#0B5E75]"
                >
                    + Dar de alta paciente
                </Link>
            </div>

            <section className="tarjeta-cristal">
                <div className="h-1.5 w-full bg-gradient-to-r from-[#062846] via-[#0B4F8A] to-[#0891B2]" />
                <div className="p-6">
                    {cargando ? (
                        <p className="text-sm text-slate-500">Cargando pacientes...</p>
                    ) : error ? (
                        <div className="flex items-center justify-between rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700">
                            <span>{error}</span>
                            <button type="button" onClick={cargar} className="font-semibold underline">
                                Reintentar
                            </button>
                        </div>
                    ) : pacientes.length === 0 ? (
                        <div className="py-8 text-center">
                            <p className="text-sm font-medium text-slate-700">
                                Todavía no registraste pacientes en el sistema.
                            </p>
                            <p className="mt-1 text-xs text-slate-500">
                                Iniciá el alta clínica cargando diagnóstico presuntivo, síntomas SNOMED y datos familiares.
                            </p>
                            <Link
                                to="/medico/pacientes/nuevo"
                                className="mt-4 inline-flex items-center rounded-xl bg-[#0B4F8A] px-4 py-2 text-xs font-medium text-white hover:bg-[#093E6D]"
                            >
                                Registrar primer paciente →
                            </Link>
                        </div>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="w-full text-left text-sm">
                                <thead>
                                    <tr className="border-b border-slate-200/80 text-xs font-semibold uppercase tracking-wider text-slate-500">
                                        <th className="pb-3 pr-4">Paciente</th>
                                        <th className="pb-3 pr-4">DNI</th>
                                        <th className="pb-3 pr-4">Diagnóstico presuntivo</th>
                                        <th className="pb-3 pr-4">Acceso</th>
                                        <th className="pb-3 pr-4">Familiograma</th>
                                        <th className="pb-3">Acciones</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-200/60">
                                    {pacientes.map((p) => (
                                        <tr key={p.paciente_id} className="text-xs text-slate-700">
                                            <td className="py-3 pr-4">
                                                <p className="font-semibold text-slate-900">
                                                    {p.nombre} {p.apellido}
                                                </p>
                                                <p className="text-[11px] text-slate-500">{p.email}</p>
                                            </td>
                                            <td className="py-3 pr-4 font-mono">{p.dni}</td>
                                            <td className="py-3 pr-4">
                                                <p className="font-medium text-[#0B4F8A]">{p.patologia_nombre}</p>
                                                <p className="text-[11px] capitalize text-slate-500">
                                                    Sospecha {p.tipo_sospecha}
                                                </p>
                                            </td>
                                            <td className="py-3 pr-4">
                                                {p.es_medico_alta === false ? (
                                                    <span className="inline-flex rounded-full border border-cyan-200 bg-cyan-50 px-2.5 py-0.5 text-[11px] font-medium text-[#0B4F8A]">
                                                        Autorizado por paciente
                                                    </span>
                                                ) : (
                                                    <span className="inline-flex rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-medium text-slate-700">
                                                        Médico de alta
                                                    </span>
                                                )}
                                            </td>
                                            <td className="py-3 pr-4">
                                                {p.familiograma_pdf_path ? (
                                                    <span className="inline-flex rounded-full bg-emerald-100 px-2.5 py-0.5 text-[11px] font-medium text-emerald-700">
                                                        Generado
                                                    </span>
                                                ) : (
                                                    <span className="inline-flex rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-medium text-slate-600">
                                                        Sin info familiar
                                                    </span>
                                                )}
                                            </td>
                                            <td className="py-3">
                                                <div className="flex flex-wrap items-center gap-3">
                                                    <Link
                                                        to={`/medico/pacientes/${p.paciente_id}/historia-clinica`}
                                                        className="rounded-lg border border-[#0B4F8A]/30 bg-[#EAF2FA] px-2.5 py-1 text-[11px] font-semibold text-[#0B4F8A] transition hover:bg-[#DCEAF7]"
                                                    >
                                                        Ver historia clínica
                                                    </Link>
                                                    <Link
                                                        to={`/medico/pacientes/${p.paciente_id}/familiares`}
                                                        className="font-semibold text-slate-600 hover:text-[#0B4F8A] hover:underline"
                                                    >
                                                        Familiares
                                                    </Link>
                                                </div>
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
