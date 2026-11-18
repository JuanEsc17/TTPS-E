import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { listarEspecialidadesRequest, registrarMedicoRequest } from "../api/medicos";
import FondoAdn from "../components/FondoAdn";
import LogoAdn from "../components/LogoAdn";

export default function RegistroMedicoPage({ sesion }) {
    const [especialidades, setEspecialidades] = useState([]);
    const [cargandoEspecialidades, setCargandoEspecialidades] = useState(true);
    const [errorEspecialidades, setErrorEspecialidades] = useState("");

    const [nombre, setNombre] = useState("");
    const [apellido, setApellido] = useState("");
    const [telefono, setTelefono] = useState("");
    const [email, setEmail] = useState("");
    const [matricula, setMatricula] = useState("");
    const [password, setPassword] = useState("");
    const [mostrarPassword, setMostrarPassword] = useState(false);
    const [especialidadesIds, setEspecialidadesIds] = useState([]);

    const [enviando, setEnviando] = useState(false);
    const [error, setError] = useState("");
    const [codigoError, setCodigoError] = useState("");
    const [erroresCampos, setErroresCampos] = useState({});
    const [registroExitoso, setRegistroExitoso] = useState(null);

    async function cargarEspecialidades() {
        setCargandoEspecialidades(true);
        setErrorEspecialidades("");
        try {
            const lista = await listarEspecialidadesRequest();
            setEspecialidades(lista);
        } catch (err) {
            setErrorEspecialidades(err.message);
        } finally {
            setCargandoEspecialidades(false);
        }
    }

    useEffect(() => {
        cargarEspecialidades();
    }, []);

    if (sesion?.access_token) {
        return <Navigate to={sesion.ruta_inicio || "/medico/estudios"} replace />;
    }

    function toggleEspecialidad(id) {
        setEspecialidadesIds((prev) =>
            prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
        );
    }

    function validarFormulario() {
        const errs = {};
        if (!nombre.trim()) errs.nombre = "Ingresá tu nombre.";
        if (!apellido.trim()) errs.apellido = "Ingresá tu apellido.";
        if (!matricula.trim()) errs.matricula = "Ingresá tu matrícula profesional.";

        const tel = telefono.trim();
        const digitosTel = (tel.match(/\d/g) || []).length;
        if (!tel || !/^\+?[\d\s\-()]{7,20}$/.test(tel) || digitosTel < 7) {
            errs.telefono = "Ingresá un teléfono válido (solo números, al menos 7 dígitos).";
        }

        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
            errs.email = "Ingresá un correo electrónico válido.";
        }

        if (password.length < 8 || !/[A-Za-z]/.test(password) || !/\d/.test(password)) {
            errs.password = "La contraseña debe tener como mínimo 8 caracteres, al menos una letra y un número.";
        }

        if (especialidadesIds.length === 0) {
            errs.especialidades = "Seleccioná al menos una especialidad médica.";
        }

        return errs;
    }

    async function handleSubmit(e) {
        e.preventDefault();
        setError("");
        setCodigoError("");

        const errs = validarFormulario();
        setErroresCampos(errs);
        if (Object.keys(errs).length > 0) {
            setError("Revisá los campos marcados antes de continuar.");
            return;
        }

        setEnviando(true);
        try {
            const medico = await registrarMedicoRequest({
                nombre,
                apellido,
                telefono,
                email,
                password,
                matricula,
                especialidadesIds,
            });
            setRegistroExitoso(medico);
        } catch (err) {
            setError(err.message);
            setCodigoError(err.code || "");
        } finally {
            setEnviando(false);
        }
    }

    const inputBase =
        "w-full rounded-xl border bg-[#E6EFF7]/80 px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 transition focus:bg-white focus:outline-none focus:ring-2";
    const inputNormal = `${inputBase} border-slate-300/80 focus:border-[#0B4F8A] focus:ring-[#0B4F8A]/15`;
    const inputError = `${inputBase} border-red-300 focus:border-red-500 focus:ring-red-500/15`;

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
                        Portal de Genética Clínica
                    </span>
                    <Link
                        to="/login"
                        className="rounded-full border border-white/70 bg-white/75 px-3.5 py-1.5 text-xs font-semibold text-[#0B4F8A] shadow-xs backdrop-blur-md transition hover:bg-white"
                    >
                        ← Volver a iniciar sesión
                    </Link>
                </div>
            </header>

            <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6 sm:py-10">
                <div className="mb-6">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                        Alta profesional · Exoma clínico
                    </p>
                    <h1 className="font-titulo mt-1 text-3xl font-semibold text-slate-900">
                        Registro de médico
                    </h1>
                    <p className="mt-1 text-sm text-slate-600">
                        Completá tus datos profesionales, matrícula y especialidades para operar en el sistema.
                    </p>
                </div>

                {registroExitoso ? (
                    <section className="rounded-2xl border border-emerald-200 bg-white p-6 shadow-xs">
                        <div className="flex items-start gap-3">
                            <span className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-sm font-semibold text-emerald-700">
                                ✓
                            </span>
                            <div>
                                <h2 className="text-base font-semibold text-slate-900">
                                    Registro exitoso
                                </h2>
                                <p className="mt-1 text-sm text-slate-600">
                                    Ya puede iniciar sesión con su correo y contraseña.
                                </p>
                                <div className="mt-4 rounded-xl border border-slate-100 bg-slate-50 p-4 text-xs text-slate-700">
                                    <p>
                                        <span className="font-semibold">Profesional:</span>{" "}
                                        {registroExitoso.nombre} {registroExitoso.apellido}
                                    </p>
                                    <p className="mt-1">
                                        <span className="font-semibold">Matrícula:</span>{" "}
                                        {registroExitoso.matricula}
                                    </p>
                                    <p className="mt-1">
                                        <span className="font-semibold">Especialidades:</span>{" "}
                                        {registroExitoso.especialidades.map((e) => e.nombre).join(", ")}
                                    </p>
                                </div>
                                <Link
                                    to="/login"
                                    className="mt-5 inline-flex items-center justify-center rounded-xl bg-[#0B4F8A] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#093E6D]"
                                >
                                    Ir a iniciar sesión →
                                </Link>
                            </div>
                        </div>
                    </section>
                ) : (
                    <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                        <section
                            aria-label="Formulario de registro médico"
                            className="overflow-hidden rounded-2xl border border-white/80 bg-gradient-to-br from-white/85 via-white/75 to-[#EAF3FA]/80 shadow-lg shadow-[#0B4F8A]/10 backdrop-blur-md lg:col-span-8"
                        >
                            <div className="h-1.5 w-full bg-gradient-to-r from-[#062846] via-[#0B4F8A] to-[#0891B2]" />
                            <div className="p-6">
                            <div className="mb-5 border-b border-slate-100 pb-4">
                                <h2 className="text-sm font-semibold text-slate-900">
                                    Datos personales y matrícula
                                </h2>
                                <p className="text-xs text-slate-500">
                                    Todos los campos son obligatorios para habilitar tu perfil médico.
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

                            <form onSubmit={handleSubmit} noValidate className="space-y-4">
                                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                                    <div>
                                        <label htmlFor="med-nombre" className="mb-1.5 block text-xs font-medium text-slate-700">
                                            Nombre
                                        </label>
                                        <input
                                            id="med-nombre"
                                            type="text"
                                            placeholder="Martín"
                                            value={nombre}
                                            onChange={(e) => setNombre(e.target.value)}
                                            className={erroresCampos.nombre ? inputError : inputNormal}
                                        />
                                        {erroresCampos.nombre && (
                                            <p className="mt-1 text-[11px] font-medium text-red-600">{erroresCampos.nombre}</p>
                                        )}
                                    </div>
                                    <div>
                                        <label htmlFor="med-apellido" className="mb-1.5 block text-xs font-medium text-slate-700">
                                            Apellido
                                        </label>
                                        <input
                                            id="med-apellido"
                                            type="text"
                                            placeholder="Gómez"
                                            value={apellido}
                                            onChange={(e) => setApellido(e.target.value)}
                                            className={erroresCampos.apellido ? inputError : inputNormal}
                                        />
                                        {erroresCampos.apellido && (
                                            <p className="mt-1 text-[11px] font-medium text-red-600">{erroresCampos.apellido}</p>
                                        )}
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                                    <div>
                                        <label htmlFor="med-matricula" className="mb-1.5 block text-xs font-medium text-slate-700">
                                            Matrícula profesional
                                        </label>
                                        <input
                                            id="med-matricula"
                                            type="text"
                                            maxLength={50}
                                            placeholder="MP-114523"
                                            value={matricula}
                                            onChange={(e) => setMatricula(e.target.value)}
                                            className={codigoError === "MATRICULA_YA_REGISTRADA" || erroresCampos.matricula ? inputError : inputNormal}
                                        />
                                        {erroresCampos.matricula && (
                                            <p className="mt-1 text-[11px] font-medium text-red-600">{erroresCampos.matricula}</p>
                                        )}
                                    </div>
                                    <div>
                                        <label htmlFor="med-telefono" className="mb-1.5 block text-xs font-medium text-slate-700">
                                            Teléfono
                                        </label>
                                        <input
                                            id="med-telefono"
                                            type="tel"
                                            maxLength={30}
                                            placeholder="+5492214448899"
                                            value={telefono}
                                            onChange={(e) => setTelefono(e.target.value)}
                                            className={erroresCampos.telefono ? inputError : inputNormal}
                                        />
                                        {erroresCampos.telefono && (
                                            <p className="mt-1 text-[11px] font-medium text-red-600">{erroresCampos.telefono}</p>
                                        )}
                                    </div>
                                </div>

                                <div>
                                    <label htmlFor="med-email" className="mb-1.5 block text-xs font-medium text-slate-700">
                                        Correo electrónico
                                    </label>
                                    <input
                                        id="med-email"
                                        type="email"
                                        autoComplete="email"
                                        placeholder="martin.gomez@hospital.org.ar"
                                        value={email}
                                        onChange={(e) => setEmail(e.target.value)}
                                        className={codigoError === "EMAIL_YA_REGISTRADO" || erroresCampos.email ? inputError : inputNormal}
                                    />
                                    {erroresCampos.email && (
                                        <p className="mt-1 text-[11px] font-medium text-red-600">{erroresCampos.email}</p>
                                    )}
                                </div>

                                <div>
                                    <label htmlFor="med-password" className="mb-1.5 block text-xs font-medium text-slate-700">
                                        Contraseña
                                    </label>
                                    <div className="relative">
                                        <input
                                            id="med-password"
                                            type={mostrarPassword ? "text" : "password"}
                                            autoComplete="new-password"
                                            placeholder="Mínimo 8 caracteres, al menos una letra y un número"
                                            value={password}
                                            onChange={(e) => setPassword(e.target.value)}
                                            className={`${erroresCampos.password ? inputError : inputNormal} pr-14`}
                                        />
                                        <button
                                            type="button"
                                            onClick={() => setMostrarPassword((v) => !v)}
                                            className="absolute inset-y-0 right-2 flex items-center px-2 text-xs font-medium text-slate-500 hover:text-slate-800"
                                        >
                                            {mostrarPassword ? "Ocultar" : "Ver"}
                                        </button>
                                    </div>
                                    {erroresCampos.password && (
                                        <p className="mt-1 text-[11px] font-medium text-red-600">{erroresCampos.password}</p>
                                    )}
                                </div>

                                <div>
                                    <span className="mb-2 block text-xs font-medium text-slate-700">
                                        Especialidades médicas (seleccioná al menos una)
                                    </span>

                                    {cargandoEspecialidades ? (
                                        <p className="text-xs text-slate-500">Cargando especialidades...</p>
                                    ) : errorEspecialidades ? (
                                        <div className="flex items-center justify-between rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-2.5 text-xs text-amber-800">
                                            <span>{errorEspecialidades}</span>
                                            <button
                                                type="button"
                                                onClick={cargarEspecialidades}
                                                className="font-semibold underline"
                                            >
                                                Reintentar
                                            </button>
                                        </div>
                                    ) : especialidades.length === 0 ? (
                                        <p className="rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs text-slate-600">
                                            No hay especialidades cargadas en el catálogo.
                                        </p>
                                    ) : (
                                        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                                            {especialidades.map((esp) => {
                                                const seleccionada = especialidadesIds.includes(esp.id);
                                                return (
                                                    <label
                                                        key={esp.id}
                                                        className={`flex cursor-pointer items-center gap-2.5 rounded-xl border px-3 py-2 text-xs transition ${
                                                            seleccionada
                                                                ? "border-[#0B4F8A] bg-[#0B4F8A]/10 font-medium text-[#0B4F8A]"
                                                                : "border-slate-300/75 bg-[#E6EFF7]/65 text-slate-700 hover:bg-[#E6EFF7]"
                                                        }`}
                                                    >
                                                        <input
                                                            type="checkbox"
                                                            checked={seleccionada}
                                                            onChange={() => toggleEspecialidad(esp.id)}
                                                            className="h-4 w-4 rounded border-slate-300 text-[#0B4F8A] focus:ring-[#0B4F8A]"
                                                        />
                                                        <span>{esp.nombre}</span>
                                                    </label>
                                                );
                                            })}
                                        </div>
                                    )}
                                </div>

                                <div className="pt-2">
                                    <button
                                        type="submit"
                                        disabled={enviando || cargandoEspecialidades}
                                        className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-[#0B4F8A] to-[#0E7490] px-5 py-2.5 text-sm font-medium text-white shadow-sm transition hover:from-[#093E6D] hover:to-[#0B5E75] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] focus-visible:ring-offset-2 disabled:opacity-50"
                                    >
                                        {enviando ? "Registrando médico..." : "Crear cuenta profesional →"}
                                    </button>
                                </div>
                            </form>
                            </div>
                        </section>

                        <aside
                            aria-label="Información del registro médico"
                            className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-[#062846] via-[#0B4F8A] to-[#0E7490] p-6 text-white shadow-lg shadow-[#062846]/15 lg:col-span-4"
                        >
                            <svg
                                aria-hidden="true"
                                viewBox="0 0 120 260"
                                className="pointer-events-none absolute -right-4 -bottom-6 h-56 w-28 opacity-15"
                                fill="none"
                            >
                                <path d="M25 10 C95 50, 95 90, 25 130 C-25 160, 95 210, 25 250" stroke="white" strokeWidth="5" strokeLinecap="round" />
                                <path d="M95 10 C25 50, 25 90, 95 130 C145 160, 25 210, 95 250" stroke="#67E8F9" strokeWidth="5" strokeLinecap="round" />
                                <line x1="35" y1="35" x2="85" y2="35" stroke="white" strokeWidth="3" />
                                <line x1="35" y1="95" x2="85" y2="95" stroke="white" strokeWidth="3" />
                                <line x1="35" y1="165" x2="85" y2="165" stroke="white" strokeWidth="3" />
                                <line x1="35" y1="225" x2="85" y2="225" stroke="white" strokeWidth="3" />
                            </svg>

                            <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-cyan-200">
                                Secuenciación de Exoma
                            </span>
                            <h2 className="mt-3 text-base font-semibold text-white">
                                Alcance del perfil médico
                            </h2>
                            <p className="mt-1 text-xs text-cyan-100/85">
                                Al registrarte como profesional vas a poder:
                            </p>
                            <ul className="relative mt-5 space-y-3 text-xs">
                                <li className="rounded-xl border border-white/15 bg-white/10 p-3.5 backdrop-blur-xs">
                                    <p className="font-semibold text-white">Alta de pacientes</p>
                                    <p className="mt-0.5 leading-relaxed text-cyan-100/90">
                                        Cargar diagnóstico presuntivo, síntomas SNOMED, historia clínica y datos familiares.
                                    </p>
                                </li>
                                <li className="rounded-xl border border-white/15 bg-white/10 p-3.5 backdrop-blur-xs">
                                    <p className="font-semibold text-white">Solicitud de estudios</p>
                                    <p className="mt-0.5 leading-relaxed text-cyan-100/90">
                                        Iniciar estudios de exoma clínico seleccionando genes y patologías sospechadas.
                                    </p>
                                </li>
                                <li className="rounded-xl border border-white/15 bg-white/10 p-3.5 backdrop-blur-xs">
                                    <p className="font-semibold text-white">Equipo verificado</p>
                                    <p className="mt-0.5 leading-relaxed text-cyan-100/90">
                                        Esta computadora quedará registrada para agilizar tu próximo ingreso.
                                    </p>
                                </li>
                            </ul>
                        </aside>
                    </div>
                )}
            </main>
        </div>
    );
}
