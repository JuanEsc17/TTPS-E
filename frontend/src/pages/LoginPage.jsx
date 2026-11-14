import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom"
import { loginRequest } from "../api/auth"
import LogoAdn from "../components/LogoAdn";

export default function LoginPage({ sesion, onSesion }) {
    const navigate = useNavigate()
    const [email, setEmail] = useState("")
    const [password, setPassword] = useState("")
    const [mostrarPassword, setMostrarPassword] = useState(false)
    const [error, setError] = useState("")
    const [cargando, setCargando] = useState(false)

    if (sesion?.access_token) {
        return <Navigate to={sesion.ruta_inicio || "/login"} replace />
    }

    async function handleSubmit(e) {
        e.preventDefault()
        setError("")
        setCargando(true)
        try {
            const data = await loginRequest({ email, password })

            if (data.estado_login === "REQUIERE_CAMBIO_PASSWORD_INICIAL") {
                navigate("/cambiar-password-inicial", {
                    state: { tokenTemporal: data.access_token, usuario: data.usuario },
                })
                return
            }
            if (data.estado_login === "REQUIERE_VERIFICACION_DISPOSITIVO") {
                navigate("/verificar-dispositivo", {
                    state: { challengeToken: data.challenge_token, usuario: data.usuario }
                })
                return
            }

            onSesion(data)
            navigate(data.ruta_inicio, { replace: true })
        } catch (err) {
            setError(err.message)
        } finally {
            setCargando(false)
        }
    }

    return (
        <div className="min-h-screen bg-[#F4F7FA] text-slate-900">
            <header className="border-b border-slate-200 bg-white">
                <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
                    <LogoAdn />
                    <div className="hidden items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50/70 px-3 py-1 text-xs text-slate-600 sm:flex">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden="true" />
                        Circuito clínico protegido
                    </div>
                    <span className="text-xs font-medium text-slate-500">Acceso al sistema</span>
                </div>
            </header>
            <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6 sm:py-10">
                <div className="mb-6">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                        Acceso seguro · Exoma clínico
                    </p>
                    <h1 className="font-titulo mt-1 text-3xl font-semibold text-slate-900">
                        Iniciar sesión
                    </h1>
                    <p className="mt-1 text-sm text-slate-600">
                        Ingresá con tus credenciales institucionales o de paciente para continuar.
                    </p>
                </div>
                <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                    <section
                        aria-label="Formulario de ingreso"
                        className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs lg:col-span-7"
                    >
                        <div className="mb-5 border-b border-slate-100 pb-4">
                            <h2 className="text-sm font-semibold text-slate-900">Credenciales de acceso</h2>
                            <p className="text-xs text-slate-500">
                                El sistema validará tu identidad y el equipo desde el cual ingresás.
                            </p>
                        </div>
                        {error && (
                            <div
                                role="alert"
                                className="mb-4 rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-xs font-medium text-red-700"
                            >
                                {error}
                            </div>
                        )}
                        <form onSubmit={handleSubmit} className="space-y-4">
                            <div>
                                <label htmlFor="login-email" className="mb-1.5 block text-xs font-medium text-slate-700">
                                    Correo electrónico
                                </label>
                                <input
                                    id="login-email"
                                    type="email"
                                    required
                                    autoComplete="email"
                                    placeholder="nombre@ejemplo.com"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    aria-invalid={Boolean(error)}
                                    className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-[#0B4F8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0B4F8A]/15"
                                />
                            </div>
                            <div>
                                <label htmlFor="login-password" className="mb-1.5 block text-xs font-medium text-slate-700">
                                    Contraseña
                                </label>
                                <div className="relative">
                                    <input
                                        id="login-password"
                                        type={mostrarPassword ? "text" : "password"}
                                        required
                                        autoComplete="current-password"
                                        placeholder="Ingresá tu contraseña"
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        aria-invalid={Boolean(error)}
                                        className="w-full rounded-xl border border-slate-200 bg-slate-50/50 py-2.5 pl-3.5 pr-11 text-sm text-slate-900 placeholder:text-slate-400 focus:border-[#0B4F8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0B4F8A]/15"
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setMostrarPassword((v) => !v)}
                                        aria-label={mostrarPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                                        aria-pressed={mostrarPassword}
                                        className="absolute inset-y-0 right-2 flex items-center px-2 text-xs font-medium text-slate-500 hover:text-slate-800"
                                    >
                                        {mostrarPassword ? "Ocultar" : "Ver"}
                                    </button>
                                </div>
                            </div>
                            <div className="pt-2">
                                <button
                                    type="submit"
                                    disabled={cargando}
                                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-[#0B4F8A] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#093E6D] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] focus-visible:ring-offset-2 disabled:opacity-50"
                                >
                                    {cargando ? "Validando..." : "Continuar →"}
                                </button>
                            </div>
                        </form>
                    </section>
                    <aside
                        aria-label="Información de acceso seguro"
                        className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs lg:col-span-5"
                    >
                        <h2 className="text-sm font-semibold text-slate-900">Primer acceso y resguardo</h2>
                        <p className="mt-1 text-xs text-slate-500">
                            Controles automáticos al ingresar al sistema
                        </p>
                        <ul className="mt-5 space-y-4 text-xs text-slate-600">
                            <li className="rounded-xl border border-slate-100 bg-[#F8FAFC] p-3">
                                <p className="font-semibold text-slate-800">Contraseña inicial</p>
                                <p className="mt-0.5 leading-relaxed">
                                    Si es tu primer ingreso como paciente, el sistema te pedirá definir una clave propia antes de operar.
                                </p>
                            </li>
                            <li className="rounded-xl border border-slate-100 bg-[#F8FAFC] p-3">
                                <p className="font-semibold text-slate-800">Verificación de equipo nuevo</p>
                                <p className="mt-0.5 leading-relaxed">
                                    Si accedés desde una máquina no registrada, enviaremos un código temporal a tu correo electrónico.
                                </p>
                            </li>
                            <li className="rounded-xl border border-slate-100 bg-[#F8FAFC] p-3">
                                <p className="font-semibold text-slate-800">Sesión vinculada al rol</p>
                                <p className="mt-0.5 leading-relaxed">
                                    Al validar el ingreso, se habilita únicamente el módulo correspondiente a tu perfil.
                                </p>
                            </li>
                        </ul>
                    </aside>
                </div>
            </main>
        </div>
    );
}