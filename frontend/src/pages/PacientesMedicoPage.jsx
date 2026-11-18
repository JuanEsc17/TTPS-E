import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listarPacientesRequest } from "../api/pacientes";

export default function PacientesMedicoPage({ sesion }) {
    const [pacientes, setPacientes] = useState([]);
    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState("");

    async function cargar() {
        setCargando(true);
        setError("");
        try {
            const lista = await listarPacientesRequest(sesion?.access_token);
            setPacientes(lista || []);
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
                        Gestión clínica · Médico tratante
                    </p>
                    <h1 className="font-titulo mt-1 text-2xl font-semibold text-slate-900">
                        Pacientes registrados
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
                                        <th className="pb-3 pr-4">Sospecha</th>
                                        <th className="pb-3">Familiograma</th>
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
                                            <td className="py-3 pr-4 font-medium text-[#0B4F8A]">
                                                {p.patologia_nombre}
                                            </td>
                                            <td className="py-3 pr-4 capitalize">{p.tipo_sospecha}</td>
                                            <td className="py-3">
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
