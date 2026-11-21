import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { listarAvisosRequest } from "../api/resultados";

const ROLES_CON_ENLACE_RESULTADO = new Set([
    "paciente",
    "medico",
    "gerente_medico",
    "bioinformatico",
]);

function formatearFechaAviso(iso) {
    if (!iso) return "";
    const fecha = new Date(iso);
    if (Number.isNaN(fecha.getTime())) return "";
    return fecha.toLocaleString("es-AR", {
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
    });
}

export default function CampanaAvisos({ sesion }) {
    const token = sesion?.access_token;
    const rol = sesion?.usuario?.rol;

    const [abierto, setAbierto] = useState(false);
    const [recargaId, setRecargaId] = useState(0);
    const claveActual = `${token || ""}:${recargaId}`;
    const [estadoCarga, setEstadoCarga] = useState({
        clave: null,
        token: null,
        noLeidos: 0,
        avisos: [],
        error: "",
    });

    const contenedorRef = useRef(null);
    const botonRef = useRef(null);

    useEffect(() => {
        if (!token) return;
        const controller = new AbortController();

        listarAvisosRequest(token, { limite: 20, signal: controller.signal })
            .then(({ no_leidos, avisos }) => {
                if (controller.signal.aborted) return;
                setEstadoCarga({
                    clave: claveActual,
                    token,
                    noLeidos: no_leidos,
                    avisos,
                    error: "",
                });
            })
            .catch((err) => {
                if (err?.name === "AbortError" || controller.signal.aborted) return;
                setEstadoCarga((prev) => ({
                    clave: claveActual,
                    token,
                    noLeidos: prev.token === token ? prev.noLeidos : 0,
                    avisos: prev.token === token ? prev.avisos : [],
                    error: err.message || "No se pudieron cargar los avisos.",
                }));
            });

        return () => controller.abort();
    }, [token, claveActual]);

    useEffect(() => {
        const onActualizar = () => setRecargaId((n) => n + 1);
        window.addEventListener("avisos:actualizar", onActualizar);
        return () => window.removeEventListener("avisos:actualizar", onActualizar);
    }, []);

    useEffect(() => {
        if (!abierto) return;
        const onClickFuera = (e) => {
            if (contenedorRef.current && !contenedorRef.current.contains(e.target)) {
                setAbierto(false);
            }
        };
        const onKeyDown = (e) => {
            if (e.key === "Escape") {
                setAbierto(false);
                botonRef.current?.focus();
            }
        };
        document.addEventListener("mousedown", onClickFuera);
        document.addEventListener("keydown", onKeyDown);
        return () => {
            document.removeEventListener("mousedown", onClickFuera);
            document.removeEventListener("keydown", onKeyDown);
        };
    }, [abierto]);

    const mismoUsuario = estadoCarga.token === token;
    const cargando = Boolean(token) && estadoCarga.clave !== claveActual;
    const noLeidos = mismoUsuario ? estadoCarga.noLeidos : 0;
    const avisos = mismoUsuario ? estadoCarga.avisos : [];
    const error = estadoCarga.clave === claveActual ? estadoCarga.error : "";

    function handleToggle() {
        const proximo = !abierto;
        setAbierto(proximo);
        if (proximo) setRecargaId((n) => n + 1);
    }

    const puedeAbrirResultado = ROLES_CON_ENLACE_RESULTADO.has(rol);
    const etiquetaBoton =
        noLeidos > 0
            ? `Avisos (${noLeidos} sin leer)`
            : "Avisos del sistema";

    return (
        <div ref={contenedorRef} className="relative">
            <button
                ref={botonRef}
                type="button"
                onClick={handleToggle}
                aria-label={etiquetaBoton}
                aria-expanded={abierto}
                aria-haspopup="dialog"
                aria-controls="panel-avisos"
                className="relative flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200/80 bg-white/85 text-slate-600 transition hover:border-[#0B4F8A]/40 hover:bg-white hover:text-[#0B4F8A] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A]"
            >
                <svg
                    viewBox="0 0 24 24"
                    className="h-4.5 w-4.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                >
                    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                    <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                </svg>
                {noLeidos > 0 && (
                    <span
                        aria-hidden="true"
                        className="absolute -top-1 -right-1 flex min-w-4.5 items-center justify-center rounded-full bg-[#0B4F8A] px-1 py-0.5 text-[10px] leading-none font-bold text-white shadow-xs"
                    >
                        {noLeidos > 99 ? "99+" : noLeidos}
                    </span>
                )}
            </button>

            {abierto && (
                <section
                    id="panel-avisos"
                    role="dialog"
                    aria-label="Avisos del sistema"
                    className="absolute right-0 mt-2 w-[min(23rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-xl shadow-[#062846]/15"
                >
                    <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/80 px-4 py-3">
                        <div className="flex items-center gap-2">
                            <h2 className="text-xs font-semibold text-slate-900">Avisos</h2>
                            {noLeidos > 0 && (
                                <span className="rounded-full bg-[#EAF2FA] px-2 py-0.5 text-[10px] font-semibold text-[#0B4F8A]">
                                    {noLeidos} sin leer
                                </span>
                            )}
                        </div>
                        <button
                            type="button"
                            onClick={() => setRecargaId((n) => n + 1)}
                            disabled={cargando}
                            className="text-[11px] font-semibold text-[#0B4F8A] hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] disabled:opacity-50"
                        >
                            {cargando ? "Actualizando..." : "Actualizar"}
                        </button>
                    </div>

                    <div className="max-h-80 overflow-y-auto">
                        {error ? (
                            <div role="alert" className="space-y-2 p-4 text-xs text-red-700">
                                <p>{error}</p>
                                <button
                                    type="button"
                                    onClick={() => setRecargaId((n) => n + 1)}
                                    className="font-semibold underline"
                                >
                                    Reintentar
                                </button>
                            </div>
                        ) : cargando && avisos.length === 0 ? (
                            <p role="status" className="p-4 text-xs text-slate-500">
                                Cargando avisos...
                            </p>
                        ) : avisos.length === 0 ? (
                            <p className="p-5 text-center text-xs text-slate-500">
                                No tenés avisos registrados por el momento.
                            </p>
                        ) : (
                            <ul className="divide-y divide-slate-100">
                                {avisos.map((aviso) => {
                                    const esResultado =
                                        puedeAbrirResultado &&
                                        Boolean(aviso.estudio_id) &&
                                        /resultado/i.test(aviso.mensaje || "");
                                    const esBandejaBio =
                                        rol === "bioinformatico" &&
                                        !esResultado &&
                                        /reanalisis|bioinformatic/i.test(aviso.mensaje || "");
                                    const fecha = formatearFechaAviso(
                                        aviso.enviado_en || aviso.created_at
                                    );
                                    return (
                                        <li
                                            key={aviso.id}
                                            className={`px-4 py-3 text-xs transition ${
                                                aviso.leido
                                                    ? "bg-white text-slate-600"
                                                    : "border-l-2 border-[#0B4F8A] bg-[#EAF2FA]/45 text-slate-900"
                                            }`}
                                        >
                                            <div className="flex items-start justify-between gap-2">
                                                <p className={aviso.leido ? "font-normal" : "font-medium"}>
                                                    {aviso.mensaje}
                                                </p>
                                                {!aviso.leido && (
                                                    <span className="shrink-0 rounded-full bg-[#0B4F8A] px-1.5 py-0.5 text-[10px] font-semibold text-white">
                                                        Nuevo
                                                    </span>
                                                )}
                                            </div>
                                            <div className="mt-1.5 flex items-center justify-between gap-2 text-[11px] text-slate-500">
                                                <span>{fecha}</span>
                                                {esResultado ? (
                                                    <Link
                                                        to={`/estudios/${aviso.estudio_id}/resultado`}
                                                        onClick={() => setAbierto(false)}
                                                        className="font-semibold text-[#0B4F8A] hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A]"
                                                    >
                                                        Ver resultado →
                                                    </Link>
                                                ) : esBandejaBio ? (
                                                    <Link
                                                        to="/bioinformatica/cola"
                                                        onClick={() => setAbierto(false)}
                                                        className="font-semibold text-[#0B4F8A] hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A]"
                                                    >
                                                        Ir a bandeja →
                                                    </Link>
                                                ) : null}
                                            </div>
                                        </li>
                                    );
                                })}
                            </ul>
                        )}
                    </div>
                </section>
            )}
        </div>
    );
}
