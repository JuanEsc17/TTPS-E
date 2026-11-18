import { useEffect, useRef, useState } from "react";
import { consultarChatbotRequest } from "../api/chatbot";

const PATOLOGIAS_SUGERIDAS = [
    {
        nombre: "Enfermedad de Fabry",
        pregunta: "¿Qué es la enfermedad de Fabry y cuáles son sus síntomas principales?",
    },
    {
        nombre: "Enfermedad de Pompe",
        pregunta: "¿Qué es la enfermedad de Pompe y cómo se presenta?",
    },
    {
        nombre: "Mucopolisacaridosis 1",
        pregunta: "¿Qué es la mucopolisacaridosis tipo 1 (MPS 1)?",
    },
    {
        nombre: "Enfermedad de Gaucher",
        pregunta: "¿Qué es la enfermedad de Gaucher y qué signos suele provocar?",
    },
    {
        nombre: "ASMD",
        pregunta: "¿Qué es el ASMD y cuál es su causa genética?",
    },
];

const ETIQUETA_TIPO = {
    fuera_de_alcance: {
        texto: "Fuera de alcance",
        clase: "border-slate-200 bg-slate-100 text-slate-700",
    },
    derivar_medico: {
        texto: "Consultá con tu médico tratante",
        clase: "border-amber-200 bg-amber-50 text-amber-800",
    },
    sin_informacion: {
        texto: "Información no disponible",
        clase: "border-cyan-200 bg-cyan-50 text-[#0B4F8A]",
    },
};

function formatearHora(iso) {
    if (!iso) return "";
    const fecha = new Date(iso);
    if (Number.isNaN(fecha.getTime())) return "";
    return fecha.toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" });
}

export default function ChatbotPage({ sesion }) {
    const token = sesion?.access_token;
    const esPaciente = sesion?.usuario?.rol === "paciente";

    const [mensajes, setMensajes] = useState([]);
    const [pregunta, setPregunta] = useState("");
    const [conversacionId, setConversacionId] = useState(null);
    const [cargando, setCargando] = useState(false);
    const [errorLocal, setErrorLocal] = useState("");
    const [falloEnvio, setFalloEnvio] = useState(null);

    const finChatRef = useRef(null);
    const inputRef = useRef(null);

    useEffect(() => {
        finChatRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }, [mensajes, cargando, falloEnvio]);

    async function enviarConsulta(
        textoOriginal,
        { esReintento = false, idMensajeExistente = null, limpiarInput = false } = {}
    ) {
        const preguntaLimpia = textoOriginal.trim();
        setErrorLocal("");

        if (preguntaLimpia.length < 3 || preguntaLimpia.length > 1000) {
            setErrorLocal("Ingresá una pregunta de entre 3 y 1000 caracteres.");
            return;
        }

        const msgId = idMensajeExistente || `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

        if (esReintento && idMensajeExistente) {
            setMensajes((prev) =>
                prev.map((m) => (m.id === idMensajeExistente ? { ...m, estado: "enviando" } : m))
            );
        } else {
            setMensajes((prev) => [
                ...prev,
                {
                    id: msgId,
                    autor: "paciente",
                    texto: preguntaLimpia,
                    estado: "enviando",
                },
            ]);
            if (limpiarInput) setPregunta("");
        }

        setFalloEnvio(null);
        setCargando(true);

        try {
            const data = await consultarChatbotRequest({
                token,
                pregunta: preguntaLimpia,
                conversacionId,
            });

            setConversacionId(data.conversacion_id || conversacionId);
            setMensajes((prev) => [
                ...prev.map((m) => (m.id === msgId ? { ...m, estado: "enviado" } : m)),
                {
                    id: `bot-${msgId}`,
                    autor: "chatbot",
                    texto: data.respuesta,
                    patologias: data.patologias_relacionadas || [],
                    tipo: data.tipo || "respuesta",
                    respondidoEn: data.respondido_en,
                },
            ]);
        } catch (err) {
            const esRecuperable = Boolean(err.retryable) || !err.status || err.status >= 500;
            setMensajes((prev) =>
                prev.map((m) => (m.id === msgId ? { ...m, estado: "error" } : m))
            );
            setFalloEnvio({
                mensaje: err.message,
                reintentable: esRecuperable,
                pregunta: preguntaLimpia,
                msgId,
            });
        } finally {
            setCargando(false);
            inputRef.current?.focus();
        }
    }

    function handleSubmit(e) {
        e.preventDefault();
        if (cargando) return;
        enviarConsulta(pregunta, { limpiarInput: true });
    }

    function handleKeyDown(e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (!cargando) {
                enviarConsulta(pregunta, { limpiarInput: true });
            }
        }
    }

    function reiniciarConversacion() {
        setMensajes([]);
        setConversacionId(null);
        setErrorLocal("");
        setFalloEnvio(null);
        inputRef.current?.focus();
    }

    if (!esPaciente) {
        return (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
                El asistente de consultas sobre patologías es exclusivo para pacientes.
            </div>
        );
    }

    const largoActual = pregunta.trim().length;

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                        Asistente informativo · Patologías lisosomales
                    </p>
                    <h1 className="font-titulo mt-1 text-2xl font-semibold text-slate-900 sm:text-3xl">
                        Consultar al chatbot sobre patologías
                    </h1>
                    <p className="mt-1 text-sm text-slate-600">
                        Despejá dudas generales sobre Fabry, Pompe, mucopolisacaridosis 1, Gaucher y ASMD.
                    </p>
                </div>

                {mensajes.length > 0 && (
                    <button
                        type="button"
                        onClick={reiniciarConversacion}
                        disabled={cargando}
                        className="rounded-xl border border-[#0B4F8A] bg-white px-4 py-2 text-xs font-semibold text-[#0B4F8A] transition hover:bg-[#EAF2FA] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] disabled:opacity-50"
                    >
                        Nueva conversación
                    </button>
                )}
            </div>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                <section
                    aria-label="Conversación con el asistente sobre patologías"
                    className="flex h-[34rem] flex-col rounded-2xl border border-slate-200 bg-white shadow-xs lg:col-span-8"
                >
                    <div
                        role="log"
                        aria-live="polite"
                        aria-relevant="additions"
                        className="flex-1 space-y-4 overflow-y-auto p-5"
                    >
                        {mensajes.length === 0 ? (
                            <div className="flex h-full flex-col items-center justify-center text-center">
                                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#EAF2FA] text-[#0B4F8A]">
                                    <svg
                                        viewBox="0 0 24 24"
                                        className="h-6 w-6"
                                        fill="none"
                                        stroke="currentColor"
                                        strokeWidth="1.8"
                                        aria-hidden="true"
                                    >
                                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                                    </svg>
                                </div>
                                <h2 className="mt-3 text-sm font-semibold text-slate-900">
                                    Hacé tu primera consulta
                                </h2>
                                <p className="mt-1 max-w-md text-xs text-slate-500">
                                    Escribí una pregunta abajo o seleccioná una de las cinco patologías del panel lateral para empezar.
                                </p>
                            </div>
                        ) : (
                            mensajes.map((msg) => {
                                if (msg.autor === "paciente") {
                                    return (
                                        <div key={msg.id} className="flex justify-end">
                                            <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-[#0B4F8A] px-4 py-2.5 text-sm text-white shadow-xs">
                                                <p className="whitespace-pre-line break-words">{msg.texto}</p>
                                                {msg.estado === "enviando" && (
                                                    <p className="mt-1 text-[11px] text-cyan-100">
                                                        Enviando consulta...
                                                    </p>
                                                )}
                                                {msg.estado === "error" && (
                                                    <p className="mt-1 text-[11px] text-amber-200">
                                                        No se pudo recibir respuesta
                                                    </p>
                                                )}
                                            </div>
                                        </div>
                                    );
                                }

                                const insignia = ETIQUETA_TIPO[msg.tipo];
                                return (
                                    <div key={msg.id} className="flex justify-start">
                                        <div className="max-w-[88%] space-y-2 rounded-2xl rounded-bl-sm border border-slate-200 bg-[#F8FAFC] px-4 py-3 text-sm text-slate-800">
                                            <div className="flex flex-wrap items-center justify-between gap-2">
                                                <span className="text-[11px] font-semibold uppercase tracking-wide text-[#0B4F8A]">
                                                    Asistente de patologías
                                                </span>
                                                {msg.respondidoEn && (
                                                    <span className="text-[11px] text-slate-400">
                                                        {formatearHora(msg.respondidoEn)}
                                                    </span>
                                                )}
                                            </div>

                                            <p className="whitespace-pre-line break-words leading-relaxed">
                                                {msg.texto}
                                            </p>

                                            {(insignia || msg.patologias?.length > 0) && (
                                                <div className="flex flex-wrap gap-1.5 pt-1">
                                                    {msg.patologias?.map((pat) => (
                                                        <span
                                                            key={pat}
                                                            className="rounded-full border border-cyan-200 bg-cyan-50 px-2.5 py-0.5 text-[11px] font-medium text-[#0B4F8A]"
                                                        >
                                                            {pat}
                                                        </span>
                                                    ))}
                                                    {insignia && (
                                                        <span
                                                            className={`rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${insignia.clase}`}
                                                        >
                                                            {insignia.texto}
                                                        </span>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                );
                            })
                        )}

                        {cargando && (
                            <div className="flex justify-start">
                                <div className="rounded-2xl rounded-bl-sm border border-slate-200 bg-[#F8FAFC] px-4 py-2.5 text-xs font-medium text-slate-600">
                                    El asistente está escribiendo una respuesta...
                                </div>
                            </div>
                        )}

                        {falloEnvio && (
                            <div
                                role="alert"
                                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-800"
                            >
                                <span className="flex-1">{falloEnvio.mensaje}</span>
                                {falloEnvio.reintentable && (
                                    <button
                                        type="button"
                                        disabled={cargando}
                                        onClick={() =>
                                            enviarConsulta(falloEnvio.pregunta, {
                                                esReintento: true,
                                                idMensajeExistente: falloEnvio.msgId,
                                            })
                                        }
                                        className="shrink-0 rounded-lg border border-red-300 bg-white px-3 py-1.5 font-semibold text-red-700 transition hover:bg-red-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 disabled:opacity-50"
                                    >
                                        Reintentar envío
                                    </button>
                                )}
                            </div>
                        )}

                        <div ref={finChatRef} />
                    </div>

                    <form onSubmit={handleSubmit} className="border-t border-slate-200 p-4">
                        {errorLocal && (
                            <p id="chatbot-error-local" role="alert" className="mb-2 text-xs font-medium text-red-600">
                                {errorLocal}
                            </p>
                        )}
                        <label htmlFor="chatbot-pregunta" className="sr-only">
                            Escribí tu pregunta sobre patologías
                        </label>
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                            <textarea
                                ref={inputRef}
                                id="chatbot-pregunta"
                                rows={2}
                                maxLength={1000}
                                value={pregunta}
                                onChange={(e) => {
                                    setPregunta(e.target.value);
                                    if (errorLocal) setErrorLocal("");
                                }}
                                onKeyDown={handleKeyDown}
                                placeholder="Escribí tu pregunta sobre las patologías (sin datos personales)..."
                                aria-describedby={errorLocal ? "chatbot-contador chatbot-error-local" : "chatbot-contador"}
                                className="w-full resize-none rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-[#0B4F8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0B4F8A]/15"
                            />
                            <button
                                type="submit"
                                disabled={cargando || largoActual === 0}
                                className="inline-flex shrink-0 items-center justify-center rounded-xl bg-[#0B4F8A] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#093E6D] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                                {cargando ? "Enviando..." : "Enviar"}
                            </button>
                        </div>
                        <div id="chatbot-contador" className="mt-1.5 flex items-center justify-between text-[11px] text-slate-400">
                            <span>Presioná Enter para enviar · Shift+Enter para salto de línea</span>
                            <span>{pregunta.length} / 1000</span>
                        </div>
                    </form>
                </section>

                <aside
                    aria-label="Consultas rápidas e información del asistente"
                    className="space-y-4 lg:col-span-4"
                >
                    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
                        <h2 className="text-sm font-semibold text-slate-900">
                            Patologías cubiertas
                        </h2>
                        <p className="mt-1 text-xs text-slate-500">
                            Elegí una consulta rápida o escribí tu propia pregunta.
                        </p>
                        <div className="mt-3 space-y-2">
                            {PATOLOGIAS_SUGERIDAS.map((item) => (
                                <button
                                    key={item.nombre}
                                    type="button"
                                    disabled={cargando}
                                    onClick={() => enviarConsulta(item.pregunta)}
                                    className="w-full rounded-xl border border-slate-200 bg-[#F8FAFC] px-3.5 py-2.5 text-left text-xs transition hover:border-[#0B4F8A]/40 hover:bg-[#EAF2FA]/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] disabled:opacity-50"
                                >
                                    <span className="block font-semibold text-[#0B4F8A]">
                                        {item.nombre}
                                    </span>
                                    <span className="mt-0.5 block text-slate-600">
                                        {item.pregunta}
                                    </span>
                                </button>
                            ))}
                        </div>
                    </div>

                    <div className="rounded-2xl border border-cyan-200/80 bg-cyan-50/60 p-4 text-xs text-slate-700">
                        <h2 className="font-semibold text-[#0B4F8A]">Sobre este asistente</h2>
                        <ul className="mt-2 space-y-1.5 leading-relaxed">
                            <li>
                                Es un asistente automático informativo y no reemplaza la consulta con tu médico.
                            </li>
                            <li>
                                No compartas datos personales como nombre, DNI, correo, teléfono ni resultados clínicos.
                            </li>
                            <li>
                                No realiza diagnósticos ni deriva conversaciones a operadores humanos.
                            </li>
                        </ul>
                    </div>
                </aside>
            </div>
        </div>
    );
}
