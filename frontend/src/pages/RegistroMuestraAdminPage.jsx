import { useCallback, useEffect, useMemo, useState } from "react";
import {
    listarTurnosPendientesMuestraRequest,
    registrarTomaMuestraRequest,
} from "../api/muestras";
import { listarCentrosRequest } from "../api/turnos";

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

function obtenerDatetimeLocalActual() {
    const ahora = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    return (
        `${ahora.getFullYear()}-${pad(ahora.getMonth() + 1)}-${pad(ahora.getDate())}` +
        `T${pad(ahora.getHours())}:${pad(ahora.getMinutes())}`
    );
}

const FILTROS_INICIALES = {
    dni: "",
    estudioId: "",
    centroId: "",
    fecha: "",
};

function soloDigitos(valor) {
    return String(valor || "").replace(/\D/g, "");
}

export default function RegistroMuestraAdminPage({ sesion }) {
    const token = sesion?.access_token;
    const esAdmin = sesion?.usuario?.rol === "administrativo";

    const [turnos, setTurnos] = useState([]);
    const [centros, setCentros] = useState([]);
    const [cargando, setCargando] = useState(Boolean(token && esAdmin));
    const [filtrosForm, setFiltrosForm] = useState(FILTROS_INICIALES);
    const [filtrosAplicados, setFiltrosAplicados] = useState(FILTROS_INICIALES);
    const [turnoSeleccionadoId, setTurnoSeleccionadoId] = useState(null);

    const [usarHoraActual, setUsarHoraActual] = useState(true);
    const [fechaTomaManual, setFechaTomaManual] = useState(() => obtenerDatetimeLocalActual());
    const [registrando, setRegistrando] = useState(false);
    const [error, setError] = useState("");
    const [resultadoExito, setResultadoExito] = useState(null);

    const aplicarTurnos = useCallback((lista) => {
        const items = Array.isArray(lista) ? lista : [];
        setTurnos(items);
        setTurnoSeleccionadoId((prev) => {
            if (prev && items.some((t) => t.turno_id === prev)) {
                return prev;
            }
            return items[0] ? items[0].turno_id : null;
        });
    }, []);

    const recargarPendientes = useCallback(
        async (filtros = { centroId: filtrosAplicados.centroId, fecha: filtrosAplicados.fecha }) => {
            if (!token || !esAdmin) return;
            setCargando(true);
            setError("");
            try {
                const data = await listarTurnosPendientesMuestraRequest(token, {
                    centroId: filtros.centroId,
                    fecha: filtros.fecha,
                });
                aplicarTurnos(data);
            } catch (err) {
                setError(err.message);
            } finally {
                setCargando(false);
            }
        },
        [token, esAdmin, filtrosAplicados.centroId, filtrosAplicados.fecha, aplicarTurnos]
    );

    useEffect(() => {
        if (!token || !esAdmin) return;
        let cancelado = false;

        listarCentrosRequest(token)
            .then((data) => {
                if (!cancelado && Array.isArray(data)) {
                    setCentros(data);
                }
            })
            .catch(() => {
                // El filtro de centros es auxiliar; si falla no bloquea el listado principal
            });

        return () => {
            cancelado = true;
        };
    }, [token, esAdmin]);

    useEffect(() => {
        if (!token || !esAdmin) return;
        let cancelado = false;

        listarTurnosPendientesMuestraRequest(token, {
            centroId: filtrosAplicados.centroId,
            fecha: filtrosAplicados.fecha,
        })
            .then((data) => {
                if (!cancelado) {
                    aplicarTurnos(data);
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
    }, [token, esAdmin, filtrosAplicados.centroId, filtrosAplicados.fecha, aplicarTurnos]);

    const turnosVisibles = useMemo(() => {
        const dniFiltro = filtrosForm.dni.trim();
        const estudioFiltro = filtrosForm.estudioId.trim();
        return turnos.filter((t) => {
            if (dniFiltro && !String(t.paciente_dni || "").includes(dniFiltro)) {
                return false;
            }
            if (estudioFiltro && !String(t.estudio_id || "").includes(estudioFiltro)) {
                return false;
            }
            return true;
        });
    }, [turnos, filtrosForm.dni, filtrosForm.estudioId]);

    const turnoActivo = useMemo(() => {
        if (turnosVisibles.length === 0) return null;
        return (
            turnosVisibles.find((t) => t.turno_id === turnoSeleccionadoId) ||
            turnosVisibles[0]
        );
    }, [turnosVisibles, turnoSeleccionadoId]);

    const resumen = useMemo(() => {
        const urgentes = turnosVisibles.filter((t) => t.es_pompe_urgente).length;
        const centrosUnicos = new Set(turnosVisibles.map((t) => t.centro_id).filter(Boolean)).size;
        return {
            total: turnosVisibles.length,
            urgentes,
            centrosUnicos,
        };
    }, [turnosVisibles]);

    if (!esAdmin) {
        return (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
                Solo el Personal Administrativo puede registrar la toma de muestras.
            </div>
        );
    }

    function handleAplicarFiltros(e) {
        e.preventDefault();
        setError("");
        setResultadoExito(null);
        setFiltrosAplicados({ ...filtrosForm });
        recargarPendientes({ centroId: filtrosForm.centroId, fecha: filtrosForm.fecha });
    }

    function handleLimpiarFiltros() {
        setError("");
        setResultadoExito(null);
        setFiltrosForm(FILTROS_INICIALES);
        if (filtrosAplicados.centroId || filtrosAplicados.fecha) {
            setCargando(true);
        }
        setFiltrosAplicados(FILTROS_INICIALES);
    }

    async function handleRegistrarToma(e) {
        e.preventDefault();
        if (!turnoActivo) return;

        setError("");
        setResultadoExito(null);

        let tomadaEnIso;
        if (!usarHoraActual) {
            if (!fechaTomaManual) {
                setError("Indicá la fecha y hora en que se realizó la extracción.");
                return;
            }
            tomadaEnIso = fechaTomaManual.length === 16 ? `${fechaTomaManual}:00` : fechaTomaManual;
        }

        setRegistrando(true);
        try {
            const data = await registrarTomaMuestraRequest({
                token,
                turnoId: turnoActivo.turno_id,
                tomadaEn: tomadaEnIso,
            });
            setResultadoExito({
                ...data,
                paciente_nombre: turnoActivo.paciente_nombre,
                paciente_dni: turnoActivo.paciente_dni,
            });
            await recargarPendientes(filtrosAplicados);
        } catch (err) {
            setError(err.message);
        } finally {
            setRegistrando(false);
        }
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                        Personal administrativo · Extracción de sangre
                    </p>
                    <h1 className="font-titulo mt-1 text-2xl font-semibold text-slate-900 sm:text-3xl">
                        Registro de toma de muestra
                    </h1>
                    <p className="mt-1 text-sm text-slate-600">
                        Registrá la extracción confirmada por el centro para pasar el estudio a{" "}
                        <span className="font-semibold text-slate-800">Lista para retirar</span>.
                    </p>
                </div>

                <button
                    type="button"
                    onClick={() => {
                        setResultadoExito(null);
                        recargarPendientes(filtrosAplicados);
                    }}
                    disabled={cargando}
                    className="rounded-xl border border-[#0B4F8A] bg-white px-4 py-2 text-xs font-semibold text-[#0B4F8A] transition hover:bg-[#EAF2FA] disabled:opacity-50"
                >
                    {cargando ? "Actualizando..." : "Actualizar lista"}
                </button>
            </div>

            {/* Indicadores operativos */}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                        Turnos pendientes de toma
                    </p>
                    <p className="mt-1 text-2xl font-semibold text-slate-900">{resumen.total}</p>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                        Prioridad Pompe urgente
                    </p>
                    <p className="mt-1 text-2xl font-semibold text-red-700">{resumen.urgentes}</p>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                        Centros con turnos activos
                    </p>
                    <p className="mt-1 text-2xl font-semibold text-[#0B4F8A]">
                        {resumen.centrosUnicos}
                    </p>
                </div>
            </div>

            {/* Filtros de búsqueda */}
            <form
                onSubmit={handleAplicarFiltros}
                aria-label="Filtros de turnos pendientes de toma"
                className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs"
            >
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
                    <div>
                        <label
                            htmlFor="filtro-dni"
                            className="mb-1 block text-xs font-medium text-slate-700"
                        >
                            DNI del paciente
                        </label>
                        <input
                            id="filtro-dni"
                            type="text"
                            inputMode="numeric"
                            pattern="[0-9]*"
                            maxLength={12}
                            value={filtrosForm.dni}
                            onChange={(e) => {
                                const limpio = soloDigitos(e.target.value);
                                setFiltrosForm((prev) => ({ ...prev, dni: limpio }));
                            }}
                            placeholder="Solo números (ej: 541)"
                            className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3 py-2 text-xs text-slate-900 focus:border-[#0B4F8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0B4F8A]/15"
                        />
                    </div>

                    <div>
                        <label
                            htmlFor="filtro-estudio-id"
                            className="mb-1 block text-xs font-medium text-slate-700"
                        >
                            ID de estudio
                        </label>
                        <input
                            id="filtro-estudio-id"
                            type="text"
                            inputMode="numeric"
                            pattern="[0-9]*"
                            maxLength={10}
                            value={filtrosForm.estudioId}
                            onChange={(e) => {
                                const limpio = soloDigitos(e.target.value);
                                setFiltrosForm((prev) => ({ ...prev, estudioId: limpio }));
                            }}
                            placeholder="Solo números (ej: 15)"
                            className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3 py-2 text-xs text-slate-900 focus:border-[#0B4F8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0B4F8A]/15"
                        />
                    </div>

                    <div>
                        <label
                            htmlFor="filtro-centro"
                            className="mb-1 block text-xs font-medium text-slate-700"
                        >
                            Centro de extracción
                        </label>
                        <select
                            id="filtro-centro"
                            value={filtrosForm.centroId}
                            onChange={(e) =>
                                setFiltrosForm((prev) => ({ ...prev, centroId: e.target.value }))
                            }
                            className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3 py-2 text-xs text-slate-900 focus:border-[#0B4F8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0B4F8A]/15"
                        >
                            <option value="">Todos los centros</option>
                            {centros.map((centro) => (
                                <option key={centro.id} value={String(centro.id)}>
                                    {centro.nombre} ({centro.provincia})
                                </option>
                            ))}
                        </select>
                    </div>

                    <div>
                        <label
                            htmlFor="filtro-fecha"
                            className="mb-1 block text-xs font-medium text-slate-700"
                        >
                            Fecha del turno
                        </label>
                        <input
                            id="filtro-fecha"
                            type="date"
                            value={filtrosForm.fecha}
                            onChange={(e) =>
                                setFiltrosForm((prev) => ({ ...prev, fecha: e.target.value }))
                            }
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
                        Muestra #{resultadoExito.muestra_id} registrada correctamente
                    </p>
                    <p className="mt-1">
                        Estudio #{resultadoExito.estudio_id} ({resultadoExito.paciente_nombre || "Paciente"}{" "}
                        {resultadoExito.paciente_dni ? `· DNI ${resultadoExito.paciente_dni}` : ""}) pasó a{" "}
                        <strong>{resultadoExito.estado_estudio}</strong> en{" "}
                        <strong>{resultadoExito.centro_nombre || "centro de extracción"}</strong>.
                    </p>
                    <p className="mt-1 text-[11px] text-emerald-800">
                        Turno #{resultadoExito.turno_id} marcado como asistido · Toma:{" "}
                        {formatearFechaHora(resultadoExito.tomada_en)} · Aviso enviado al paciente.
                    </p>
                </div>
            )}

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                {/* Columna izquierda: Turnos pendientes */}
                <aside
                    aria-label="Turnos con estudio en estado Turno sacado"
                    className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs lg:col-span-6"
                >
                    <div className="flex items-center justify-between">
                        <h2 className="text-sm font-semibold text-slate-900">
                            Turnos en estado &ldquo;Turno sacado&rdquo;
                        </h2>
                        <span className="rounded-full bg-[#EAF2FA] px-2.5 py-0.5 text-[11px] font-semibold text-[#0B4F8A]">
                            {turnosVisibles.length}
                        </span>
                    </div>

                    {cargando ? (
                        <p className="mt-4 text-xs text-slate-500">
                            Consultando turnos pendientes de extracción...
                        </p>
                    ) : turnosVisibles.length === 0 ? (
                        <p className="mt-4 rounded-xl border border-dashed border-slate-200 p-5 text-xs text-slate-500">
                            No hay turnos activos pendientes de toma de muestra con los filtros seleccionados.
                        </p>
                    ) : (
                        <ul className="mt-4 space-y-2.5">
                            {turnosVisibles.map((turno) => {
                                const seleccionado = turnoActivo?.turno_id === turno.turno_id;
                                return (
                                    <li key={turno.turno_id}>
                                        <button
                                            type="button"
                                            onClick={() => {
                                                setTurnoSeleccionadoId(turno.turno_id);
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
                                                        Estudio #{turno.estudio_id}
                                                    </span>
                                                    <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
                                                        Turno #{turno.turno_id}
                                                    </span>
                                                </div>
                                                <div className="flex items-center gap-1.5">
                                                    {turno.es_pompe_urgente && (
                                                        <span className="rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-700">
                                                            Pompe urgente
                                                        </span>
                                                    )}
                                                    <span className="rounded-full border border-cyan-200 bg-cyan-50 px-2 py-0.5 text-[10px] font-semibold text-[#0B4F8A]">
                                                        {turno.estado_estudio}
                                                    </span>
                                                </div>
                                            </div>

                                            <p className="mt-1.5 text-xs font-medium text-slate-800">
                                                {turno.paciente_nombre || "Paciente sin nombre"} · DNI{" "}
                                                {turno.paciente_dni || "-"}
                                            </p>
                                            <p className="mt-0.5 text-[11px] text-slate-500">
                                                {turno.centro_nombre} ({turno.centro_provincia}) ·{" "}
                                                {formatearFechaHora(turno.inicio)}
                                            </p>
                                        </button>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </aside>

                {/* Columna derecha: Confirmación de toma de muestra */}
                <section
                    aria-label="Formulario de registro de toma de muestra"
                    className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs lg:col-span-6"
                >
                    <div className="mb-5 flex items-center justify-between border-b border-slate-100 pb-3">
                        <h2 className="text-sm font-semibold text-slate-900">
                            {turnoActivo
                                ? `Confirmar toma · Turno #${turnoActivo.turno_id}`
                                : "Detalle del turno"}
                        </h2>
                        <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-medium text-slate-600">
                            Turno sacado → Lista para retirar
                        </span>
                    </div>

                    {!turnoActivo ? (
                        <div className="rounded-xl border border-dashed border-slate-200 p-6 text-center text-xs text-slate-500">
                            Seleccioná un turno de la lista para registrar que la muestra de sangre fue
                            extraída en el centro correspondiente.
                        </div>
                    ) : (
                        <form onSubmit={handleRegistrarToma} className="space-y-4">
                            {turnoActivo.es_pompe_urgente && (
                                <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-800">
                                    <strong>Estudio con sospecha de enfermedad de Pompe:</strong> esta
                                    muestra tiene prioridad urgente para despacho directo al laboratorio.
                                </div>
                            )}

                            <dl className="grid grid-cols-1 gap-3 rounded-xl border border-slate-200/80 bg-[#F8FAFC] p-4 text-xs sm:grid-cols-2">
                                <div>
                                    <dt className="text-[11px] font-medium text-slate-500">Paciente</dt>
                                    <dd className="mt-0.5 font-semibold text-slate-900">
                                        {turnoActivo.paciente_nombre || "-"}
                                    </dd>
                                </div>
                                <div>
                                    <dt className="text-[11px] font-medium text-slate-500">DNI</dt>
                                    <dd className="mt-0.5 font-mono font-semibold text-slate-900">
                                        {turnoActivo.paciente_dni || "-"}
                                    </dd>
                                </div>
                                <div>
                                    <dt className="text-[11px] font-medium text-slate-500">
                                        Estudio / Turno
                                    </dt>
                                    <dd className="mt-0.5 font-semibold text-slate-900">
                                        Estudio #{turnoActivo.estudio_id} · Turno #{turnoActivo.turno_id}
                                    </dd>
                                </div>
                                <div>
                                    <dt className="text-[11px] font-medium text-slate-500">
                                        Horario programado
                                    </dt>
                                    <dd className="mt-0.5 font-semibold text-slate-900">
                                        {formatearFechaHora(turnoActivo.inicio)}
                                    </dd>
                                </div>
                                <div className="sm:col-span-2">
                                    <dt className="text-[11px] font-medium text-slate-500">
                                        Centro de extracción
                                    </dt>
                                    <dd className="mt-0.5 font-semibold text-slate-900">
                                        {turnoActivo.centro_nombre} ({turnoActivo.centro_provincia})
                                    </dd>
                                </div>
                            </dl>

                            <div className="space-y-3 rounded-xl border border-slate-200 p-4">
                                <label className="flex cursor-pointer items-start gap-2.5 text-xs text-slate-700">
                                    <input
                                        type="checkbox"
                                        checked={usarHoraActual}
                                        onChange={(e) => setUsarHoraActual(e.target.checked)}
                                        className="mt-0.5 h-4 w-4 rounded border-slate-300 text-[#0B4F8A] focus:ring-[#0B4F8A]"
                                    />
                                    <span>
                                        <strong className="block text-slate-900">
                                            Registrar con la fecha y hora actual
                                        </strong>
                                        <span className="text-[11px] text-slate-500">
                                            Destildá esta opción si el centro informó una hora de extracción
                                            anterior.
                                        </span>
                                    </span>
                                </label>

                                {!usarHoraActual && (
                                    <div>
                                        <label
                                            htmlFor="tomada-en-input"
                                            className="mb-1 block text-xs font-medium text-slate-700"
                                        >
                                            Fecha y hora de extracción
                                        </label>
                                        <input
                                            id="tomada-en-input"
                                            type="datetime-local"
                                            required
                                            value={fechaTomaManual}
                                            onChange={(e) => setFechaTomaManual(e.target.value)}
                                            className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-2 text-xs text-slate-900 focus:border-[#0B4F8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0B4F8A]/15"
                                        />
                                    </div>
                                )}
                            </div>

                            <div className="rounded-xl border border-cyan-200/80 bg-cyan-50/60 px-4 py-3 text-[11px] text-[#0B4F8A]">
                                Al confirmar, el turno quedará marcado como <strong>asistido</strong>, se
                                creará la <strong>Muestra</strong> en estado{" "}
                                <strong>Lista para retirar</strong> (habilitada para la orden del día del
                                transportista) y se notificará al paciente.
                            </div>

                            <div className="flex justify-end pt-1">
                                <button
                                    type="submit"
                                    disabled={registrando}
                                    className="inline-flex items-center justify-center rounded-xl bg-[#0B4F8A] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#093E6D] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] focus-visible:ring-offset-2 disabled:opacity-50"
                                >
                                    {registrando
                                        ? "Registrando toma..."
                                        : "Confirmar toma de muestra"}
                                </button>
                            </div>
                        </form>
                    )}
                </section>
            </div>
        </div>
    );
}
