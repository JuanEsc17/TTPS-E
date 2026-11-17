import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { reenviarCodigoRequest, verificarDispositivoRequest } from "../api/auth";
import FondoAdn from "../components/FondoAdn";
import LogoAdn from "../components/LogoAdn";

export default function VerificarDispositivoPage({ sesion, onSesion }) {
    const { state } = useLocation();
    const navigate = useNavigate();

    const [challengeToken, setChallengeToken] = useState(state?.challengeToken || "");
    const [codigo, setCodigo] = useState("");
    const [error, setError] = useState("");
    const [aviso, setAviso] = useState("");
    const [cargando, setCargando] = useState(false);
    const [reenviando, setReenviando] = useState(false);

    if (sesion?.access_token) {
        return <Navigate to={sesion.ruta_inicio || "/login"} replace />;
    }

    if (!challengeToken) {
        return <Navigate to="/login" replace />;
    }

    const usuario = state?.usuario;

    async function handleSubmit(e) {
        e.preventDefault();
        setError("");
        setAviso("");
        setCargando(true);
        try {
            const data = await verificarDispositivoRequest({ challengeToken, codigo });
            onSesion(data);
            navigate(data.ruta_inicio, { replace: true });
        } catch (err) {
            setError(err.message);
        } finally {
            setCargando(false);
        }
    }

    async function handleReenviar() {
        setError("");
        setAviso("");
        setReenviando(true);
        try {
            const data = await reenviarCodigoRequest(challengeToken);
            setChallengeToken(data.challenge_token);
            setCodigo("");
            setAviso("Enviamos un nuevo código de 6 dígitos a tu correo electrónico.");
        } catch (err) {
            setError(err.message);
        } finally {
            setReenviando(false);
        }
    }

    return (
        <div className="relative min-h-screen text-slate-900">
            <FondoAdn />
            <header className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 pt-6 sm:px-6">
                <div className="rounded-2xl border border-white/70 bg-white/75 px-3.5 py-2 shadow-xs backdrop-blur-md">
                    <LogoAdn />
                </div>
                <div className="flex items-center gap-3">
                    <span className="hidden items-center gap-1.5 rounded-full border border-cyan-200/80 bg-white/75 px-3 py-1.5 text-[11px] font-medium text-[#0B4F8A] shadow-xs backdrop-blur-md sm:inline-flex">
                        <span className="h-1.5 w-1.5 rounded-full bg-[#0891B2]" aria-hidden="true" />
                        Circuito clínico protegido
                    </span>
                    <div className="rounded-full border border-white/70 bg-white/75 px-3.5 py-1 text-right leading-tight shadow-xs backdrop-blur-md">
                        <span className="block text-xs font-semibold text-slate-800">
                            {usuario?.rol || "Usuario"}
                        </span>
                        <span className="block text-[10px] text-slate-500">Verificación 2FA</span>
                    </div>
                </div>
            </header>

            <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6 sm:py-10">
                <div className="mb-6">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                        Acceso seguro · Equipo nuevo
                    </p>
                    <h1 className="font-titulo mt-1 text-3xl font-semibold text-slate-900">
                        Verificá este dispositivo
                    </h1>
                    <p className="mt-1 text-sm text-slate-600">
                        Ingresá el código de 6 dígitos que enviamos a tu correo para habilitar este equipo.
                    </p>
                </div>

                <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                    <section
                        aria-label="Código de verificación"
                        className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs lg:col-span-7"
                    >
                        <div className="mb-5 flex items-center justify-between border-b border-slate-100 pb-4">
                            <div>
                                <h2 className="text-sm font-semibold text-slate-900">Confirmación por correo</h2>
                                <p className="text-xs text-slate-500">
                                    {usuario?.email ? `Enviado a: ${usuario.email}` : "Código válido por 10 minutos"}
                                </p>
                            </div>
                            <span className="rounded-full bg-[#EAF2FA] px-2.5 py-0.5 text-[11px] font-medium text-[#0B4F8A]">
                                Máquina nueva
                            </span>
                        </div>

                        {error && (
                            <div
                                role="alert"
                                className="mb-4 rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-xs font-medium text-red-700"
                            >
                                {error}
                            </div>
                        )}

                        {aviso && (
                            <div
                                role="status"
                                className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-3.5 py-2.5 text-xs font-medium text-emerald-800"
                            >
                                {aviso}
                            </div>
                        )}

                        <form onSubmit={handleSubmit} className="space-y-4">
                            <div>
                                <label htmlFor="codigo-2fa" className="mb-1.5 block text-xs font-medium text-slate-700">
                                    Código de verificación (6 dígitos)
                                </label>
                                <input
                                    id="codigo-2fa"
                                    type="text"
                                    inputMode="numeric"
                                    autoComplete="one-time-code"
                                    maxLength={6}
                                    required
                                    placeholder="000000"
                                    value={codigo}
                                    onChange={(e) => setCodigo(e.target.value.replace(/\D/g, "").slice(0, 6))}
                                    aria-invalid={Boolean(error)}
                                    className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-2.5 text-center font-mono text-lg tracking-[0.4em] text-slate-900 placeholder:text-slate-400 focus:border-[#0B4F8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0B4F8A]/15"
                                />
                            </div>

                            <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
                                <div className="flex items-center gap-4">
                                    <Link to="/login" className="text-xs font-medium text-slate-500 hover:text-slate-800">
                                        ← Volver
                                    </Link>
                                    <button
                                        type="button"
                                        onClick={handleReenviar}
                                        disabled={reenviando || cargando}
                                        className="text-xs font-medium text-[#0B4F8A] hover:underline disabled:opacity-50"
                                    >
                                        {reenviando ? "Reenviando..." : "Reenviar código"}
                                    </button>
                                </div>

                                <button
                                    type="submit"
                                    disabled={cargando || codigo.length !== 6}
                                    className="inline-flex items-center justify-center rounded-xl bg-[#0B4F8A] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#093E6D] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] focus-visible:ring-offset-2 disabled:opacity-50"
                                >
                                    {cargando ? "Verificando..." : "Verificar e ingresar →"}
                                </button>
                            </div>
                        </form>
                    </section>

                    <aside
                        aria-label="Información sobre verificación de equipo"
                        className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs lg:col-span-5"
                    >
                        <h2 className="text-sm font-semibold text-slate-900">Resguardo de cuenta</h2>
                        <p className="mt-1 text-xs text-slate-500">Ingreso desde máquina nueva</p>

                        <ul className="mt-5 space-y-4 text-xs text-slate-600">
                            <li className="rounded-xl border border-slate-100 bg-[#F8FAFC] p-3">
                                <p className="font-semibold text-slate-800">Código único de 6 dígitos</p>
                                <p className="mt-0.5 leading-relaxed">
                                    Tiene una validez de 10 minutos y solo puede utilizarse desde este mismo navegador.
                                </p>
                            </li>
                            <li className="rounded-xl border border-slate-100 bg-[#F8FAFC] p-3">
                                <p className="font-semibold text-slate-800">Equipo recordado</p>
                                <p className="mt-0.5 leading-relaxed">
                                    Una vez verificado, este dispositivo queda guardado y los próximos ingresos serán directos.
                                </p>
                            </li>
                        </ul>
                    </aside>
                </div>
            </main>
        </div>
    );
}