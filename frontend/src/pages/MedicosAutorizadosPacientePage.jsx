import { useEffect, useState } from "react";
import {
    listarDirectorioMedicosRequest,
    listarEspecialidadesRequest,
} from "../api/medicos";
import {
    autorizarMedicosRequest,
    listarMedicosAutorizadosRequest,
    revocarAutorizacionMedicoRequest,
} from "../api/pacientes";

function formatearFechaHora(iso) {
    if (!iso) return "Desde el alta clínica";
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

export default function MedicosAutorizadosPacientePage({ sesion }) {
    const token = sesion?.access_token;
    const esPaciente = sesion?.usuario?.rol === "paciente";

    const [recargaId, setRecargaId] = useState(0);
    const [busqueda, setBusqueda] = useState("");
    const [busquedaDebounced, setBusquedaDebounced] = useState("");
    const [especialidadId, setEspecialidadId] = useState("");
    const [especialidades, setEspecialidades] = useState([]);

    const [estadoAutorizados, setEstadoAutorizados] = useState({
        recargaId: -1,
        items: [],
        error: "",
    });
    const [estadoDirectorio, setEstadoDirectorio] = useState({
        clave: "",
        medicos: [],
        error: "",
    });

    const [seleccionadosIds, setSeleccionadosIds] = useState([]);
    const [motivoAutorizacion, setMotivoAutorizacion] = useState("");
    const [guardandoAutorizacion, setGuardandoAutorizacion] = useState(false);

    const [revocandoId, setRevocandoId] = useState(null);
    const [confirmandoRevocacionId, setConfirmandoRevocacionId] = useState(null);
    const [motivoRevocacion, setMotivoRevocacion] = useState("");

    const [mensajeExito, setMensajeExito] = useState("");
    const [errorAccion, setErrorAccion] = useState("");

    useEffect(() => {
        const timer = setTimeout(() => setBusquedaDebounced(busqueda), 250);
        return () => clearTimeout(timer);
    }, [busqueda]);

    useEffect(() => {
        if (!esPaciente) return;
        let activo = true;
        listarEspecialidadesRequest()
            .then((lista) => {
                if (activo) setEspecialidades(lista || []);
            })
            .catch(() => {
                // El filtro por especialidad es opcional; si falla no bloquea el directorio
            });
        return () => {
            activo = false;
        };
    }, [esPaciente]);

    useEffect(() => {
        if (!token || !esPaciente) return;
        const controller = new AbortController();

        listarMedicosAutorizadosRequest(token, { signal: controller.signal })
            .then((data) => {
                if (controller.signal.aborted) return;
                setEstadoAutorizados({
                    recargaId,
                    items: data?.medicos_autorizados || [],
                    error: "",
                });
            })
            .catch((err) => {
                if (err?.name === "AbortError" || controller.signal.aborted) return;
                setEstadoAutorizados({
                    recargaId,
                    items: [],
                    error: err.message || "No se pudieron cargar los médicos autorizados.",
                });
            });

        return () => controller.abort();
    }, [token, esPaciente, recargaId]);

    const claveDirectorio = `${recargaId}|${busquedaDebounced}|${especialidadId}`;

    useEffect(() => {
        if (!token || !esPaciente) return;
        const controller = new AbortController();

        listarDirectorioMedicosRequest(token, {
            q: busquedaDebounced,
            especialidadId,
            signal: controller.signal,
        })
            .then((data) => {
                if (controller.signal.aborted) return;
                setEstadoDirectorio({
                    clave: claveDirectorio,
                    medicos: data?.medicos || [],
                    error: "",
                });
            })
            .catch((err) => {
                if (err?.name === "AbortError" || controller.signal.aborted) return;
                setEstadoDirectorio({
                    clave: claveDirectorio,
                    medicos: [],
                    error: err.message || "No se pudo consultar el directorio de médicos.",
                });
            });

        return () => controller.abort();
    }, [token, esPaciente, busquedaDebounced, especialidadId, claveDirectorio]);

    if (!esPaciente) {
        return (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
                Esta sección está habilitada únicamente para pacientes.
            </div>
        );
    }

    const cargandoAutorizados = estadoAutorizados.recargaId !== recargaId;
    const cargandoDirectorio = estadoDirectorio.clave !== claveDirectorio;
    const autorizados = estadoAutorizados.items;
    const medicosDirectorio = estadoDirectorio.medicos;

    function toggleSeleccion(medicoId) {
        setErrorAccion("");
        setSeleccionadosIds((prev) =>
            prev.includes(medicoId)
                ? prev.filter((id) => id !== medicoId)
                : [...prev, medicoId]
        );
    }

    async function handleAutorizarSeleccionados(e) {
        e.preventDefault();
        if (seleccionadosIds.length === 0) return;

        setGuardandoAutorizacion(true);
        setErrorAccion("");
        setMensajeExito("");
        try {
            const res = await autorizarMedicosRequest(token, {
                medicosIds: seleccionadosIds,
                motivo: motivoAutorizacion,
            });
            setMensajeExito(
                res?.mensaje ||
                    `Se autorizó a ${seleccionadosIds.length} médico(s) a visualizar su historia clínica.`
            );
            setSeleccionadosIds([]);
            setMotivoAutorizacion("");
            setRecargaId((n) => n + 1);
            window.dispatchEvent(new Event("avisos:actualizar"));
        } catch (err) {
            setErrorAccion(err.message || "No se pudo registrar la autorización.");
        } finally {
            setGuardandoAutorizacion(false);
        }
    }

    async function handleConfirmarRevocacion(medicoId, nombreCompleto) {
        setRevocandoId(medicoId);
        setErrorAccion("");
        setMensajeExito("");
        try {
            await revocarAutorizacionMedicoRequest(token, medicoId, {
                motivo: motivoRevocacion,
            });
            setMensajeExito(
                `Se revocó la autorización de ${nombreCompleto}. Ya no podrá consultar tu historia clínica.`
            );
            setConfirmandoRevocacionId(null);
            setMotivoRevocacion("");
            setRecargaId((n) => n + 1);
            window.dispatchEvent(new Event("avisos:actualizar"));
        } catch (err) {
            setErrorAccion(err.message || "No se pudo revocar la autorización.");
        } finally {
            setRevocandoId(null);
        }
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                        Portal del paciente · Privacidad de historia clínica
                    </p>
                    <h1 className="font-titulo mt-1 text-2xl font-semibold text-slate-900">
                        Médicos autorizados
                    </h1>
                    <p className="mt-1 max-w-2xl text-sm text-slate-600">
                        Elegí qué profesionales pueden consultar tu historia clínica para interconsultas y revocá el acceso cuando lo necesites.
                    </p>
                </div>
                <div className="inline-flex items-center gap-2 rounded-full border border-[#0B4F8A]/20 bg-white/85 px-3.5 py-1.5 text-xs font-semibold text-[#0B4F8A] shadow-xs">
                    <span className="h-2 w-2 rounded-full bg-emerald-500" aria-hidden="true" />
                    {autorizados.length} médico{autorizados.length === 1 ? "" : "s"} con acceso activo
                </div>
            </div>

            {mensajeExito && (
                <div
                    role="status"
                    aria-live="polite"
                    className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs font-medium text-emerald-800"
                >
                    {mensajeExito}
                </div>
            )}

            {errorAccion && (
                <div
                    role="alert"
                    className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-medium text-red-700"
                >
                    {errorAccion}
                </div>
            )}

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                {/* Panel izquierdo: medicos actualmente autorizados */}
                <section className="tarjeta-cristal lg:col-span-5">
                    <div className="h-1.5 w-full bg-gradient-to-r from-[#062846] via-[#0B4F8A] to-[#0891B2]" />
                    <div className="space-y-4 p-6">
                        <div className="flex items-center justify-between gap-2">
                            <h2 className="text-sm font-semibold text-slate-900">
                                Profesionales con acceso activo
                            </h2>
                            <button
                                type="button"
                                onClick={() => setRecargaId((n) => n + 1)}
                                disabled={cargandoAutorizados}
                                className="text-xs font-semibold text-[#0B4F8A] hover:underline disabled:opacity-50"
                            >
                                Actualizar
                            </button>
                        </div>

                        {estadoAutorizados.error ? (
                            <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700">
                                {estadoAutorizados.error}
                            </div>
                        ) : cargandoAutorizados && autorizados.length === 0 ? (
                            <p role="status" className="text-xs text-slate-500">
                                Cargando autorizaciones activas...
                            </p>
                        ) : autorizados.length === 0 ? (
                            <div className="rounded-xl border border-dashed border-slate-300 bg-[#E6EFF7]/40 p-5 text-center text-xs text-slate-600">
                                No tenés ningún médico autorizado actualmente. Seleccioná profesionales del directorio para habilitar su consulta.
                            </div>
                        ) : (
                            <ul className="space-y-3" aria-label="Médicos actualmente autorizados">
                                {autorizados.map((med) => {
                                    const estaConfirmando = confirmandoRevocacionId === med.medico_id;
                                    const estaRevocando = revocandoId === med.medico_id;
                                    return (
                                        <li
                                            key={med.medico_id}
                                            className="rounded-xl border border-slate-200/80 bg-white/90 p-4 shadow-2xs"
                                        >
                                            <div className="flex items-start justify-between gap-3">
                                                <div className="min-w-0">
                                                    <div className="flex flex-wrap items-center gap-2">
                                                        <p className="text-sm font-semibold text-slate-900">
                                                            {med.nombre_completo}
                                                        </p>
                                                        {med.es_medico_alta && (
                                                            <span className="rounded-full bg-[#EAF2FA] px-2 py-0.5 text-[10px] font-semibold text-[#0B4F8A]">
                                                                Médico de alta
                                                            </span>
                                                        )}
                                                    </div>
                                                    <p className="mt-0.5 font-mono text-[11px] text-slate-500">
                                                        Matrícula {med.matricula}
                                                    </p>
                                                    {med.especialidades?.length > 0 && (
                                                        <div className="mt-2 flex flex-wrap gap-1.5">
                                                            {med.especialidades.map((esp) => (
                                                                <span
                                                                    key={esp.id}
                                                                    className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] text-slate-600"
                                                                >
                                                                    {esp.nombre}
                                                                </span>
                                                            ))}
                                                        </div>
                                                    )}
                                                    <p className="mt-2 text-[11px] text-slate-500">
                                                        Autorizado: {formatearFechaHora(med.otorgada_en)}
                                                    </p>
                                                </div>

                                                {!estaConfirmando && (
                                                    <button
                                                        type="button"
                                                        onClick={() => {
                                                            setConfirmandoRevocacionId(med.medico_id);
                                                            setMotivoRevocacion("");
                                                            setErrorAccion("");
                                                        }}
                                                        className="shrink-0 rounded-lg border border-red-200 bg-red-50/70 px-2.5 py-1.5 text-xs font-semibold text-red-700 transition hover:bg-red-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
                                                    >
                                                        Revocar
                                                    </button>
                                                )}
                                            </div>

                                            {estaConfirmando && (
                                                <div className="mt-3 space-y-2.5 rounded-xl border border-red-200/80 bg-red-50/60 p-3">
                                                    <p className="text-xs font-medium text-red-800">
                                                        ¿Confirmás revocar el acceso a tu historia clínica para {med.nombre_completo}?
                                                    </p>
                                                    <input
                                                        type="text"
                                                        value={motivoRevocacion}
                                                        onChange={(e) => setMotivoRevocacion(e.target.value)}
                                                        maxLength={500}
                                                        placeholder="Motivo (opcional, ej. Fin de interconsulta)"
                                                        aria-label={`Motivo de revocación para ${med.nombre_completo}`}
                                                        className="w-full rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs text-slate-800 placeholder:text-slate-400 focus:border-red-400 focus:outline-none focus:ring-2 focus:ring-red-200"
                                                    />
                                                    <div className="flex flex-wrap justify-end gap-2">
                                                        <button
                                                            type="button"
                                                            onClick={() => {
                                                                setConfirmandoRevocacionId(null);
                                                                setMotivoRevocacion("");
                                                            }}
                                                            disabled={estaRevocando}
                                                            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                                                        >
                                                            Cancelar
                                                        </button>
                                                        <button
                                                            type="button"
                                                            disabled={estaRevocando}
                                                            onClick={() =>
                                                                handleConfirmarRevocacion(
                                                                    med.medico_id,
                                                                    med.nombre_completo
                                                                )
                                                            }
                                                            className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-700 disabled:opacity-50"
                                                        >
                                                            {estaRevocando ? "Revocando..." : "Confirmar revocación"}
                                                        </button>
                                                    </div>
                                                </div>
                                            )}
                                        </li>
                                    );
                                })}
                            </ul>
                        )}
                    </div>
                </section>

                {/* Panel derecho: directorio de medicos y seleccion multiple */}
                <section className="tarjeta-cristal lg:col-span-7">
                    <div className="h-1.5 w-full bg-gradient-to-r from-[#0891B2] to-[#0B4F8A]" />
                    <form onSubmit={handleAutorizarSeleccionados} className="space-y-4 p-6">
                        <div>
                            <h2 className="text-sm font-semibold text-slate-900">
                                Directorio de médicos registrados
                            </h2>
                            <p className="mt-0.5 text-xs text-slate-500">
                                Buscá por nombre, apellido, matrícula o especialidad y seleccioná uno o varios médicos para autorizarlos en un solo paso.
                            </p>
                        </div>

                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-12">
                            <div className="sm:col-span-7">
                                <label htmlFor="filtro-busqueda-medicos" className="sr-only">
                                    Buscar médico por nombre, matrícula o especialidad
                                </label>
                                <input
                                    id="filtro-busqueda-medicos"
                                    type="search"
                                    value={busqueda}
                                    onChange={(e) => setBusqueda(e.target.value)}
                                    placeholder="Buscar por nombre, matrícula o especialidad..."
                                    className="campo-clinico"
                                />
                            </div>
                            <div className="sm:col-span-5">
                                <label htmlFor="filtro-especialidad-medicos" className="sr-only">
                                    Filtrar por especialidad
                                </label>
                                <select
                                    id="filtro-especialidad-medicos"
                                    value={especialidadId}
                                    onChange={(e) => setEspecialidadId(e.target.value)}
                                    className="campo-clinico"
                                >
                                    <option value="">Todas las especialidades</option>
                                    {especialidades.map((esp) => (
                                        <option key={esp.id} value={esp.id}>
                                            {esp.nombre}
                                        </option>
                                    ))}
                                </select>
                            </div>
                        </div>

                        {estadoDirectorio.error ? (
                            <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700">
                                {estadoDirectorio.error}
                            </div>
                        ) : cargandoDirectorio && medicosDirectorio.length === 0 ? (
                            <p role="status" className="py-4 text-xs text-slate-500">
                                Buscando médicos disponibles...
                            </p>
                        ) : medicosDirectorio.length === 0 ? (
                            <div className="rounded-xl border border-dashed border-slate-300 bg-[#E6EFF7]/40 p-6 text-center text-xs text-slate-600">
                                No se encontraron médicos que coincidan con los filtros aplicados.
                            </div>
                        ) : (
                            <ul
                                className="max-h-96 space-y-2.5 overflow-y-auto pr-1"
                                aria-label="Directorio de médicos"
                            >
                                {medicosDirectorio.map((med) => {
                                    const seleccionado = seleccionadosIds.includes(med.medico_id);
                                    const deshabilitado = Boolean(med.autorizado);
                                    return (
                                        <li key={med.medico_id}>
                                            <label
                                                className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3.5 transition ${
                                                    deshabilitado
                                                        ? "cursor-default border-emerald-200/80 bg-emerald-50/40"
                                                        : seleccionado
                                                            ? "border-[#0B4F8A] bg-[#EAF2FA]/70 shadow-xs"
                                                            : "border-slate-200/80 bg-white/90 hover:border-[#0B4F8A]/40"
                                                }`}
                                            >
                                                <input
                                                    type="checkbox"
                                                    checked={deshabilitado || seleccionado}
                                                    disabled={deshabilitado}
                                                    onChange={() => toggleSeleccion(med.medico_id)}
                                                    className="mt-1 h-4 w-4 rounded border-slate-300 text-[#0B4F8A] focus:ring-[#0B4F8A] disabled:opacity-60"
                                                />
                                                <div className="min-w-0 flex-1">
                                                    <div className="flex flex-wrap items-center justify-between gap-2">
                                                        <span className="text-sm font-semibold text-slate-900">
                                                            {med.nombre_completo}
                                                        </span>
                                                        {deshabilitado ? (
                                                            <span className="inline-flex rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-700">
                                                                Autorizado
                                                            </span>
                                                        ) : (
                                                            <span className="inline-flex rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-medium text-slate-600">
                                                                Sin autorización
                                                            </span>
                                                        )}
                                                    </div>
                                                    <p className="mt-0.5 font-mono text-[11px] text-slate-500">
                                                        Matrícula {med.matricula}
                                                    </p>
                                                    {med.especialidades?.length > 0 && (
                                                        <div className="mt-2 flex flex-wrap gap-1.5">
                                                            {med.especialidades.map((esp) => (
                                                                <span
                                                                    key={esp.id}
                                                                    className="rounded-full border border-slate-200/90 bg-white px-2 py-0.5 text-[11px] text-slate-600"
                                                                >
                                                                    {esp.nombre}
                                                                </span>
                                                            ))}
                                                        </div>
                                                    )}
                                                </div>
                                            </label>
                                        </li>
                                    );
                                })}
                            </ul>
                        )}

                        <div className="space-y-3 border-t border-slate-200/70 pt-4">
                            <div>
                                <label
                                    htmlFor="motivo-autorizacion"
                                    className="mb-1 block text-xs font-semibold text-slate-700"
                                >
                                    Motivo de la autorización (opcional)
                                </label>
                                <input
                                    id="motivo-autorizacion"
                                    type="text"
                                    maxLength={500}
                                    value={motivoAutorizacion}
                                    onChange={(e) => setMotivoAutorizacion(e.target.value)}
                                    placeholder="Ej. Interconsulta hematológica o segunda opinión"
                                    className="campo-clinico"
                                />
                            </div>

                            <div className="flex flex-wrap items-center justify-between gap-3">
                                <span className="text-xs text-slate-600">
                                    {seleccionadosIds.length === 0
                                        ? "Seleccioná al menos un médico sin autorización para continuar."
                                        : `${seleccionadosIds.length} médico${seleccionadosIds.length === 1 ? "" : "s"} seleccionado${seleccionadosIds.length === 1 ? "" : "s"}`}
                                </span>
                                <div className="flex items-center gap-2">
                                    {seleccionadosIds.length > 0 && (
                                        <button
                                            type="button"
                                            onClick={() => setSeleccionadosIds([])}
                                            disabled={guardandoAutorizacion}
                                            className="rounded-xl border border-slate-300 bg-white px-3.5 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
                                        >
                                            Limpiar selección
                                        </button>
                                    )}
                                    <button
                                        type="submit"
                                        disabled={seleccionadosIds.length === 0 || guardandoAutorizacion}
                                        className="rounded-xl bg-gradient-to-r from-[#0B4F8A] to-[#0E7490] px-5 py-2.5 text-xs font-semibold text-white shadow-sm transition hover:from-[#093E6D] hover:to-[#0B5E75] disabled:cursor-not-allowed disabled:opacity-50"
                                    >
                                        {guardandoAutorizacion
                                            ? "Autorizando..."
                                            : `Autorizar seleccionados (${seleccionadosIds.length})`}
                                    </button>
                                </div>
                            </div>
                        </div>
                    </form>
                </section>
            </div>
        </div>
    );
}
