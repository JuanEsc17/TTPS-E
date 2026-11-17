import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { cambiarPasswordInicialRequest } from "../api/auth";
import FondoAdn from "../components/FondoAdn";
import LogoAdn from "../components/LogoAdn"

function CampoPassword({ id, label, value, onChange, autoComplete, placeholder }) {
    const [visible, setVisible] = useState(false)

    return (
        <div>
            <label htmlFor={id} className="mb-1.5 block text-xs font-medium text-slate-700">
                {label}
            </label>
            <div className="relative">
                <input
                    id={id}
                    type={visible ? "text" : "password"}
                    required
                    autoComplete={autoComplete}
                    placeholder={placeholder}
                    value={value}
                    onChange={(e) => onChange(e.target.value)}
                    className="w-full rounded-xl border border-slate-200 bg-slate-50/50 py-2.5 pl-3.5 pr-16 text-sm text-slate-900 placeholder:text-slate-400 focus:border-[#0B4F8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0B4F8A]/15"
                />
                <button
                    type="button"
                    onClick={() => setVisible((v) => !v)}
                    aria-label={visible ? `Ocultar ${label.toLowerCase()}` : `Mostrar ${label.toLowerCase()}`}
                    aria-pressed={visible}
                    className="absolute inset-y-0 right-2 flex items-center px-2 text-xs font-medium text-slate-500 hover:text-slate-800"
                >
                    {visible ? "Ocultar" : "Ver"}
                </button>
            </div>
        </div>
    );
}

export default function CambiarPasswordInicialPage({ sesion, onSesion }) {
    const { state } = useLocation()
    const navigate = useNavigate()

    const [passwordInicial, setPasswordInicial] = useState("")
    const [nuevaPassword, setNuevaPassword] = useState("")
    const [confirmacionPassword, setConfirmacionPassword] = useState("")
    const [error, setError] = useState("")
    const [cargando, setCargando] = useState(false)

    if (sesion?.access_token) {
        return <Navigate to={sesion.ruta_inicio || "/paciente/estudios"} replace />
    }

    const tokenTemporal = state?.tokenTemporal
    const usuario = state?.usuario

    if (!tokenTemporal) {
        return <Navigate to="/login" replace />
    }

    async function handleSubmit(e) {
        e.preventDefault()
        setError("")

        if (nuevaPassword !== confirmacionPassword) {
            setError("La confirmacion no coincide con la nueva contrasena.")
            return
        }

        setCargando(true)
        try {
            const data = await cambiarPasswordInicialRequest({
                tokenTemporal,
                passwordInicial,
                nuevaPassword,
                confirmacionPassword,
            })
            onSesion(data)
            navigate(data.ruta_inicio || "/paciente/estudios", { replace: true })
        } catch (err) {
            if (err.code == "PASSWORD_INICIAL_YA_CAMBIADA") {
                navigate("/login", { replace: true })
                return
            }
            setError(err.message)
        } finally {
            setCargando(false)
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
                        <span className="block text-xs font-semibold text-slate-800">Paciente</span>
                        <span className="block text-[10px] text-slate-500">Primer acceso</span>
                    </div>
                </div>
            </header>
            <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6 sm:py-10">
                <div className="mb-6">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                        Acceso del paciente
                    </p>
                    <h1 className="font-titulo mt-1 text-3xl font-semibold text-slate-900">
                        Cambiá tu contraseña inicial
                    </h1>
                    <p className="mt-1 text-sm text-slate-600">
                        Establecé una contraseña propia para tu cuenta de Exoma Clínico.
                    </p>
                </div>
                <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                    <section
                        aria-label="Cambio de contraseña inicial"
                        className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs lg:col-span-7"
                    >
                        <div className="mb-5 flex items-center justify-between border-b border-slate-100 pb-4">
                            <div>
                                <h2 className="text-sm font-semibold text-slate-900">Cuenta de paciente</h2>
                                <p className="text-xs text-slate-500">
                                    {usuario?.email ? `Cuenta: ${usuario.email}` : "Primer ingreso - contraseña inicial"}
                                </p>
                            </div>
                            <span className="rounded-full bg-[#EAF2FA] px-2.5 py-0.5 text-[11px] font-medium text-[#0B4F8A]">
                                Acceso
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
                        <form onSubmit={handleSubmit} className="space-y-4">
                            <CampoPassword
                                id="pwd-inicial"
                                label="Contraseña inicial"
                                value={passwordInicial}
                                onChange={setPasswordInicial}
                                autoComplete="current-password"
                                placeholder="Ingresá la contraseña recibida por correo"
                            />
                            <CampoPassword
                                id="pwd-nueva"
                                label="Nueva contraseña"
                                value={nuevaPassword}
                                onChange={setNuevaPassword}
                                autoComplete="new-password"
                                placeholder="Mínimo 8 caracteres, letras y números"
                            />
                            <CampoPassword
                                id="pwd-confirmacion"
                                label="Confirmar nueva contraseña"
                                value={confirmacionPassword}
                                onChange={setConfirmacionPassword}
                                autoComplete="new-password"
                                placeholder="Repetí la nueva contraseña"
                            />
                            <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
                                <Link to="/login" className="text-xs font-medium text-slate-500 hover:text-slate-800">
                                    ← Volver al ingreso
                                </Link>
                                <button
                                    type="submit"
                                    disabled={cargando}
                                    className="inline-flex items-center justify-center rounded-xl bg-[#0B4F8A] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#093E6D] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] focus-visible:ring-offset-2 disabled:opacity-50"
                                >
                                    {cargando ? "Guardando..." : "Confirmar y continuar →"}
                                </button>
                            </div>
                        </form>
                    </section>
                    <aside
                        aria-label="Información de primer acceso seguro"
                        className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs lg:col-span-5"
                    >
                        <h2 className="text-sm font-semibold text-slate-900">Primer acceso seguro</h2>
                        <p className="mt-1 text-xs text-slate-500">Cambio de contraseña inicial</p>
                        <ul className="mt-5 space-y-4 text-xs text-slate-600">
                            <li className="rounded-xl border border-slate-100 bg-[#F8FAFC] p-3">
                                <p className="font-semibold text-slate-800">Credenciales recibidas</p>
                                <p className="mt-0.5 leading-relaxed">
                                    Tu médico creó la cuenta y recibiste las credenciales iniciales por correo electrónico.
                                </p>
                            </li>
                            <li className="rounded-xl border border-slate-100 bg-[#F8FAFC] p-3">
                                <p className="font-semibold text-slate-800">Una contraseña propia</p>
                                <p className="mt-0.5 leading-relaxed">
                                    Debe tener entre 8 y 128 caracteres, incluir al menos una letra y un número, y ser distinta de la inicial.
                                </p>
                            </li>
                            <li className="rounded-xl border border-slate-100 bg-[#F8FAFC] p-3">
                                <p className="font-semibold text-slate-800">Ingreso directo</p>
                                <p className="mt-0.5 leading-relaxed">
                                    Al confirmarla, este equipo queda registrado y accedés directamente a tus estudios.
                                </p>
                            </li>
                        </ul>
                    </aside>
                </div>
            </main>
        </div>
    )
}