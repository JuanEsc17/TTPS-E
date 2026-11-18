import { useState } from "react";
import { cambiarPasswordRequest } from "../api/auth";

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
    )
}

export default function CambiarPasswordPage({ sesion, onSesion }) {
    const [passwordActual, setPasswordActual] = useState("")
    const [passwordNueva, setPasswordNueva] = useState("")
    const [confirmacion, setConfirmacion] = useState("")
    const [error, setError] = useState("")
    const [aviso, setAviso] = useState("")
    const [cargando, setCargando] = useState(false)

    function limpiarCampos() {
        setPasswordActual("")
        setPasswordNueva("")
        setConfirmacion("")
    }

    async function handleSubmit(e) {
        e.preventDefault()
        setError("")
        setAviso("")

        if (passwordNueva !== confirmacion) {
            setError("La confirmacion no coincide con la nueva contraseña.")
            return
        }
        if (passwordNueva === passwordActual) {
            setError("La nueva contraseña debe ser diferente de la actual.")
            return
        }

        setCargando(true)
        try {
            const data = await cambiarPasswordRequest({
                token: sesion.access_token,
                passwordActual,
                passwordNueva,
                confirmacion
            })
            // Actualiza el access_token rotado para que la sesión siga activa
            onSesion({
                ...sesion,
                access_token: data.access_token,
                usuario: data.usuario,
                ruta_inicio: data.ruta_inicio
            })
            limpiarCampos()
            setAviso(data.mensaje || "Tu contraseña ha sido actualizada correctamente.")
        } catch (err) {
            limpiarCampos()
            setError(err.message)
        } finally {
            setCargando(false)
        }
    }

    return (
        <div className="space-y-6">
            <div>
                <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                    Seguridad de cuenta
                </p>
                <h1 className="font-titulo mt-1 text-2xl font-semibold text-slate-900 sm:text-3xl">
                    Cambiar contraseña
                </h1>
                <p className="mt-1 text-sm text-slate-600">
                    Actualizá tu contraseña de acceso. Tu sesión actual seguirá activa en este equipo.
                </p>
            </div>
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                <section
                    aria-label="Formulario de cambio de contraseña"
                    className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs lg:col-span-7"
                >
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
                        <CampoPassword
                            id="pwd-actual"
                            label="Contraseña actual"
                            value={passwordActual}
                            onChange={setPasswordActual}
                            autoComplete="current-password"
                            placeholder="Ingresá tu contraseña actual"
                        />
                        <CampoPassword
                            id="pwd-nueva"
                            label="Nueva contraseña"
                            value={passwordNueva}
                            onChange={setPasswordNueva}
                            autoComplete="new-password"
                            placeholder="Mínimo 8 caracteres, letras y números"
                        />
                        <CampoPassword
                            id="pwd-confirmar"
                            label="Confirmar nueva contraseña"
                            value={confirmacion}
                            onChange={setConfirmacion}
                            autoComplete="new-password"
                            placeholder="Repetí la nueva contraseña"
                        />
                        <div className="flex justify-end pt-2">
                            <button
                                type="submit"
                                disabled={cargando}
                                className="inline-flex items-center justify-center rounded-xl bg-[#0B4F8A] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#093E6D] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] focus-visible:ring-offset-2 disabled:opacity-50"
                            >
                                {cargando ? "Actualizando..." : "Actualizar contraseña"}
                            </button>
                        </div>
                    </form>
                </section>
                <aside
                    aria-label="Requisitos de contraseña"
                    className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs lg:col-span-5"
                >
                    <h2 className="text-sm font-semibold text-slate-900">Requisitos de seguridad</h2>
                    <ul className="mt-4 space-y-3 text-xs text-slate-600">
                        <li className="rounded-xl border border-slate-100 bg-[#F8FAFC] p-3">
                            Entre 8 y 128 caracteres, incluyendo al menos una letra y un número.
                        </li>
                        <li className="rounded-xl border border-slate-100 bg-[#F8FAFC] p-3">
                            Debe ser distinta de tu contraseña actual.
                        </li>
                        <li className="rounded-xl border border-slate-100 bg-[#F8FAFC] p-3">
                            Tu dispositivo conocido y tu sesión actual se mantienen activos tras el cambio.
                        </li>
                    </ul>
                </aside>
            </div>
        </div>
    );
}