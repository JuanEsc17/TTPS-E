import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
    obtenerFamiliogramaSvgRequest,
    obtenerHistoriaClinicaRequest,
} from "../api/pacientes";

function formatearFechaNacimiento(iso) {
    if (!iso) return "—";
    const partes = String(iso).split("-");
    return partes.length === 3 ? `${partes[2]}/${partes[1]}/${partes[0]}` : iso;
}

export default function HistoriaClinicaPacientePage({ sesion }) {
    const { pacienteId } = useParams();
    const token = sesion?.access_token;
    const rol = sesion?.usuario?.rol;
    const esMedico = rol === "medico" || rol === "gerente_medico";

    const [recargaId, setRecargaId] = useState(0);
    const claveActual = `${pacienteId || ""}:${recargaId}`;
    const [estado, setEstado] = useState({
        clave: "",
        datos: null,
        error: "",
        code: "",
        status: 0,
    });

    const [svgFamiliograma, setSvgFamiliograma] = useState("");
    const [cargandoSvg, setCargandoSvg] = useState(false);
    const [errorSvg, setErrorSvg] = useState("");

    useEffect(() => {
        if (!token || !esMedico || !pacienteId) return;
        const controller = new AbortController();

        obtenerHistoriaClinicaRequest(token, pacienteId, { signal: controller.signal })
            .then((datos) => {
                if (controller.signal.aborted) return;
                setEstado({
                    clave: claveActual,
                    datos,
                    error: "",
                    code: "",
                    status: 200,
                });
            })
            .catch((err) => {
                if (err?.name === "AbortError" || controller.signal.aborted) return;
                setEstado({
                    clave: claveActual,
                    datos: null,
                    error: err.message || "No se pudo consultar la historia clínica.",
                    code: err.code || "",
                    status: err.status || 0,
                });
            });

        return () => controller.abort();
    }, [token, esMedico, pacienteId, claveActual]);

    async function handleVerFamiliograma() {
        setCargandoSvg(true);
        setErrorSvg("");
        try {
            const svg = await obtenerFamiliogramaSvgRequest(token, pacienteId);
            setSvgFamiliograma(svg);
        } catch (err) {
            setErrorSvg(err.message || "No se pudo cargar el familiograma.");
        } finally {
            setCargandoSvg(false);
        }
    }

    if (!esMedico) {
        return (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
                Esta sección está habilitada únicamente para médicos tratantes y gerencia médica.
            </div>
        );
    }

    const cargando = estado.clave !== claveActual;
    const datos = estado.clave === claveActual ? estado.datos : null;
    const error = estado.clave === claveActual ? estado.error : "";
    const esAccesoDenegado =
        estado.clave === claveActual &&
        (estado.status === 403 || estado.code === "HISTORIA_CLINICA_NO_AUTORIZADA");

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                        Historia clínica · Consulta médica autorizada
                    </p>
                    <h1 className="font-titulo mt-1 text-2xl font-semibold text-slate-900">
                        {datos ? datos.nombre_completo : `Paciente #${pacienteId}`}
                    </h1>
                </div>
                <Link
                    to="/medico/pacientes"
                    className="text-xs font-semibold text-[#0B4F8A] hover:underline"
                >
                    ← Volver a pacientes autorizados
                </Link>
            </div>

            {cargando ? (
                <section className="tarjeta-cristal p-6">
                    <p role="status" className="text-sm text-slate-500">
                        Cargando historia clínica del paciente...
                    </p>
                </section>
            ) : esAccesoDenegado ? (
                <section
                    role="alert"
                    className="tarjeta-cristal border-red-200/80"
                >
                    <div className="h-1.5 w-full bg-gradient-to-r from-red-600 to-amber-500" />
                    <div className="space-y-3 p-6">
                        <span className="inline-flex rounded-full bg-red-100 px-3 py-1 text-[11px] font-semibold text-red-800">
                            403 · Acceso denegado
                        </span>
                        <h2 className="text-base font-semibold text-slate-900">
                            No contás con autorización vigente para ver esta historia clínica
                        </h2>
                        <p className="text-sm text-slate-600">
                            {error ||
                                "El paciente no otorgó o revocó el permiso de consulta sobre su historia clínica."}
                        </p>
                        <div className="pt-2">
                            <Link
                                to="/medico/pacientes"
                                className="inline-flex items-center rounded-xl bg-[#0B4F8A] px-4 py-2 text-xs font-semibold text-white hover:bg-[#093E6D]"
                            >
                                Volver a mis pacientes autorizados
                            </Link>
                        </div>
                    </div>
                </section>
            ) : error ? (
                <div
                    role="alert"
                    className="flex items-center justify-between rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700"
                >
                    <span>{error}</span>
                    <button
                        type="button"
                        onClick={() => setRecargaId((n) => n + 1)}
                        className="font-semibold underline"
                    >
                        Reintentar
                    </button>
                </div>
            ) : datos ? (
                <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                    {/* Columna principal: perfil clinico + historia clinica + sintomas + familiares */}
                    <div className="space-y-6 lg:col-span-8">
                        <section className="tarjeta-cristal">
                            <div className="h-1.5 w-full bg-gradient-to-r from-[#062846] via-[#0B4F8A] to-[#0891B2]" />
                            <div className="space-y-5 p-6">
                                <div className="grid grid-cols-1 gap-4 border-b border-slate-200/70 pb-4 sm:grid-cols-3">
                                    <div>
                                        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                                            DNI
                                        </p>
                                        <p className="mt-0.5 font-mono text-sm font-semibold text-slate-900">
                                            {datos.dni}
                                        </p>
                                    </div>
                                    <div>
                                        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                                            Fecha de nacimiento
                                        </p>
                                        <p className="mt-0.5 text-sm font-medium text-slate-800">
                                            {formatearFechaNacimiento(datos.fecha_nacimiento)}
                                        </p>
                                    </div>
                                    <div>
                                        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                                            Tipo de sospecha
                                        </p>
                                        <p className="mt-0.5 text-sm font-medium capitalize text-slate-800">
                                            {datos.tipo_sospecha}
                                        </p>
                                    </div>
                                </div>

                                {datos.responsable_nombre && (
                                    <div className="rounded-xl border border-cyan-200/80 bg-cyan-50/60 px-4 py-2.5 text-xs text-slate-700">
                                        <span className="font-semibold text-[#0B4F8A]">
                                            Adulto responsable:
                                        </span>{" "}
                                        {datos.responsable_nombre}
                                        {datos.responsable_dni ? ` (DNI ${datos.responsable_dni})` : ""}
                                    </div>
                                )}

                                <div>
                                    <h2 className="text-xs font-semibold uppercase tracking-wider text-[#0B4F8A]">
                                        Resumen de historia clínica
                                    </h2>
                                    <div className="mt-2 rounded-xl border border-slate-200/80 bg-white/90 p-4 text-sm leading-relaxed whitespace-pre-wrap text-slate-800">
                                        {datos.historia_clinica}
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                                    <div className="rounded-xl border border-slate-200/80 bg-white/85 p-4">
                                        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                                            Diagnóstico presuntivo
                                        </h3>
                                        <p className="mt-1 text-sm font-semibold text-[#0B4F8A]">
                                            {datos.diagnostico_presuntivo?.nombre}
                                        </p>
                                        {datos.diagnostico_presuntivo?.descripcion && (
                                            <p className="mt-1 text-xs text-slate-600">
                                                {datos.diagnostico_presuntivo.descripcion}
                                            </p>
                                        )}
                                    </div>

                                    <div className="rounded-xl border border-slate-200/80 bg-white/85 p-4">
                                        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                                            Síntomas SNOMED ({datos.sintomas?.length || 0})
                                        </h3>
                                        {datos.sintomas?.length > 0 ? (
                                            <div className="mt-2 flex flex-wrap gap-1.5">
                                                {datos.sintomas.map((s) => (
                                                    <span
                                                        key={s.id}
                                                        className="inline-flex items-center gap-1 rounded-full bg-[#EAF2FA] px-2.5 py-1 text-[11px] font-medium text-[#0B4F8A]"
                                                    >
                                                        <span>{s.descripcion}</span>
                                                        <span className="font-mono text-[10px] text-slate-500">
                                                            {s.snomed_id}
                                                        </span>
                                                    </span>
                                                ))}
                                            </div>
                                        ) : (
                                            <p className="mt-1 text-xs text-slate-500">
                                                Sin síntomas cargados.
                                            </p>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </section>

                        <section className="tarjeta-cristal">
                            <div className="h-1.5 w-full bg-gradient-to-r from-[#0891B2] to-[#0B4F8A]" />
                            <div className="space-y-4 p-6">
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                    <h2 className="text-sm font-semibold text-slate-900">
                                        Grupo familiar y familiograma ({datos.familiares?.length || 0})
                                    </h2>
                                    <div className="flex items-center gap-2">
                                        {datos.familiograma_generado && !svgFamiliograma && (
                                            <button
                                                type="button"
                                                onClick={handleVerFamiliograma}
                                                disabled={cargandoSvg}
                                                className="rounded-lg border border-[#0B4F8A]/30 bg-[#EAF2FA] px-3 py-1 text-xs font-semibold text-[#0B4F8A] hover:bg-[#DCEAF7]"
                                            >
                                                {cargandoSvg ? "Cargando..." : "Ver familiograma"}
                                            </button>
                                        )}
                                        <Link
                                            to={`/medico/pacientes/${datos.paciente_id}/familiares`}
                                            className="text-xs font-semibold text-[#0B4F8A] hover:underline"
                                        >
                                            Gestionar familiares →
                                        </Link>
                                    </div>
                                </div>

                                {datos.familiares?.length > 0 ? (
                                    <ul className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                                        {datos.familiares.map((fam) => (
                                            <li
                                                key={fam.id}
                                                className="rounded-xl border border-slate-200/80 bg-white/90 p-3.5 text-xs"
                                            >
                                                <p className="font-semibold text-slate-900">
                                                    <span className="capitalize text-[#0B4F8A]">
                                                        {fam.parentesco}:
                                                    </span>{" "}
                                                    {fam.nombre}
                                                </p>
                                                {fam.diagnostico_previo && (
                                                    <p className="mt-0.5 text-slate-600">
                                                        Diagnóstico previo: {fam.diagnostico_previo}
                                                    </p>
                                                )}
                                                {fam.sintomas?.length > 0 && (
                                                    <p className="mt-1 text-[11px] text-slate-500">
                                                        Síntomas:{" "}
                                                        {fam.sintomas.map((s) => s.descripcion).join(", ")}
                                                    </p>
                                                )}
                                            </li>
                                        ))}
                                    </ul>
                                ) : (
                                    <p className="rounded-xl border border-dashed border-slate-300 bg-[#E6EFF7]/40 px-4 py-3 text-xs text-slate-600">
                                        Sin información familiar registrada.
                                    </p>
                                )}

                                {errorSvg && (
                                    <p role="alert" className="text-xs text-red-700">
                                        {errorSvg}
                                    </p>
                                )}

                                {svgFamiliograma && (
                                    <div
                                        className="overflow-auto rounded-xl border border-slate-200 bg-white p-3 [&_svg]:h-auto [&_svg]:w-full"
                                        dangerouslySetInnerHTML={{ __html: svgFamiliograma }}
                                    />
                                )}
                            </div>
                        </section>
                    </div>

                    {/* Columna lateral: equipo medico autorizado */}
                    <aside className="lg:col-span-4">
                        <section className="tarjeta-cristal">
                            <div className="h-1.5 w-full bg-gradient-to-r from-[#062846] to-[#0891B2]" />
                            <div className="space-y-4 p-6">
                                <div>
                                    <h2 className="text-sm font-semibold text-slate-900">
                                        Médicos con acceso activo ({datos.medicos_autorizados?.length || 0})
                                    </h2>
                                    <p className="mt-0.5 text-xs text-slate-500">
                                        Profesionales autorizados por el paciente para interconsulta.
                                    </p>
                                </div>

                                <ul className="space-y-2.5">
                                    {(datos.medicos_autorizados || []).map((med) => (
                                        <li
                                            key={med.medico_id}
                                            className="rounded-xl border border-slate-200/80 bg-white/90 p-3.5 text-xs"
                                        >
                                            <div className="flex flex-wrap items-center justify-between gap-1.5">
                                                <p className="font-semibold text-slate-900">
                                                    {med.nombre_completo}
                                                </p>
                                                {med.es_medico_alta && (
                                                    <span className="rounded-full bg-[#EAF2FA] px-2 py-0.5 text-[10px] font-semibold text-[#0B4F8A]">
                                                        Alta
                                                    </span>
                                                )}
                                            </div>
                                            <p className="mt-0.5 font-mono text-[11px] text-slate-500">
                                                Matrícula {med.matricula}
                                            </p>
                                            {med.especialidades?.length > 0 && (
                                                <div className="mt-1.5 flex flex-wrap gap-1">
                                                    {med.especialidades.map((esp) => (
                                                        <span
                                                            key={esp.id}
                                                            className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-600"
                                                        >
                                                            {esp.nombre}
                                                        </span>
                                                    ))}
                                                </div>
                                            )}
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        </section>
                    </aside>
                </div>
            ) : null}
        </div>
    );
}
