import { useEffect, useState } from "react";
import { listarEspecialidadesRequest } from "../api/medicos";
import { registrarGerenteMedicoRequest } from "../api/admin";

// Qué campo se pinta de rojo según el error que devuelve el backend
const CAMPO_POR_CODIGO = {
    EMAIL_YA_REGISTRADO: "ger-email",
    MATRICULA_YA_REGISTRADA: "ger-matricula",
    ESPECIALIDAD_INEXISTENTE: "ger-especialidades",
};
const REQUISITOS_PASSWORD = [
    { id: "largo", texto: "Mínimo 8 caracteres", cumple: (p) => p.length >= 8 },
    { id: "letra", texto: "Al menos una letra", cumple: (p) => /[A-Za-zÁÉÍÓÚáéíóúÑñ]/.test(p) },
    { id: "numero", texto: "Al menos un número", cumple: (p) => /\d/.test(p) },
];
export default function AltaGerenteMedicoPage({ sesion }) {
    const esAdmin = sesion?.usuario?.rol === "admin_general";

    // Lista de especialidades que viene del backend
    const [especialidades, setEspecialidades] = useState([]);
    const [cargandoEspecialidades, setCargandoEspecialidades] = useState(true);
    const [errorEspecialidades, setErrorEspecialidades] = useState("");

    // Los campos del formulario
    const [nombre, setNombre] = useState("");
    const [apellido, setApellido] = useState("");
    const [telefono, setTelefono] = useState("");
    const [email, setEmail] = useState("");
    const [matricula, setMatricula] = useState("");
    const [password, setPassword] = useState("");
    const [mostrarPassword, setMostrarPassword] = useState(false);
    const [especialidadesIds, setEspecialidadesIds] = useState([]);

    // Estado del envío
    const [enviando, setEnviando] = useState(false);
    const [error, setError] = useState("");
    const [codigoError, setCodigoError] = useState("");
    const [erroresCampos, setErroresCampos] = useState({});
    const [registroExitoso, setRegistroExitoso] = useState(null);

    // Campo en rojo por un error que devolvió el backend (o null si ninguno)
    const campoConError = CAMPO_POR_CODIGO[codigoError] || null;
    const especialidadesConError = campoConError === "ger-especialidades" || !!erroresCampos.especialidades;
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
    const requisitosPendientes = REQUISITOS_PASSWORD.filter((r) => !r.cumple(password));
    const passwordValida = requisitosPendientes.length === 0;
    useEffect(() => {
        if (!esAdmin) return;
        let cancelado = false;
        listarEspecialidadesRequest()
            .then((lista) => { if (!cancelado) setEspecialidades(lista); })
            .catch((err) => { if (!cancelado) setErrorEspecialidades(err.message); })
            .finally(() => { if (!cancelado) setCargandoEspecialidades(false); });
        return () => { cancelado = true; };
    }, [esAdmin]);

    if (!esAdmin) {
        return (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
                Solo el admin general puede registrar gerentes médicos.
            </div>
        );
    }
    // Marcar/desmarcar una especialidad
    function toggleEspecialidad(id) {
        setEspecialidadesIds((prev) =>
            prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
        );
    }

    // Botón "Registrar otro": deja todo vacío
    function reiniciarFormulario() {
        setNombre(""); setApellido(""); setTelefono("");
        setEmail(""); setMatricula(""); setPassword("");
        setMostrarPassword(false);
        setEspecialidadesIds([]);
        setError(""); setCodigoError(""); setErroresCampos({});
        setRegistroExitoso(null);
    }

    // Misma validación local que el alta de médico (RegistroMedicoPage)
    function validarFormulario() {
        const errs = {};
        if (!nombre.trim()) errs.nombre = "Ingresá el nombre.";
        if (!apellido.trim()) errs.apellido = "Ingresá el apellido.";
        if (!matricula.trim()) errs.matricula = "Ingresá la matrícula profesional.";

        const tel = telefono.trim();
        const digitosTel = (tel.match(/\d/g) || []).length;
        if (!tel || !/^\+?[\d\s\-()]{7,20}$/.test(tel) || digitosTel < 7) {
            errs.telefono = "Ingresá un teléfono válido (solo números, al menos 7 dígitos).";
        }

        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
            errs.email = "Ingresá un correo electrónico válido.";
        }

        if (!passwordValida) {
            errs.password = "La contraseña debe tener como mínimo 8 caracteres, al menos una letra y un número.";
        }

        if (especialidadesIds.length === 0) {
            errs.especialidades = "Seleccioná al menos una especialidad médica.";
        }

        return errs;
    }

    // Al apretar "Registrar"
    async function handleSubmit(e) {
        e.preventDefault(); // evita que el navegador recargue la página
        setError("");
        setCodigoError("");

        const errs = validarFormulario();
        setErroresCampos(errs);
        if (Object.keys(errs).length > 0) {
            setError("Revisá los campos marcados antes de continuar.");
            return; // no se llama a la API
        }

        setEnviando(true);
        try {
            const gerente = await registrarGerenteMedicoRequest({
                token: sesion.access_token,
                nombre, apellido, telefono, email, password, matricula, especialidadesIds,
            });
            setRegistroExitoso(gerente);
        } catch (err) {
            const code = err.code || "";
            setCodigoError(code);
            setError(code === "DB_ERROR" ? `${err.message} Podés volver a intentarlo.` : err.message);

            if (code === "ESPECIALIDAD_INEXISTENTE") cargarEspecialidades();

            // Mover el cursor al campo con problema (accesibilidad)
            const campo = CAMPO_POR_CODIGO[code];
            if (campo) document.getElementById(campo)?.focus();
        } finally {
            setEnviando(false);
        }
    }
    const inputBase =
        "w-full rounded-xl border bg-[#E6EFF7]/80 px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 transition focus:bg-white focus:outline-none focus:ring-2";
    const inputNormal = `${inputBase} border-slate-300/80 focus:border-[#0B4F8A] focus:ring-[#0B4F8A]/15`;
    const inputError = `${inputBase} border-red-300 focus:border-red-500 focus:ring-red-500/15`;

    // Borde rojo si el campo falló la validación local o el backend lo marcó
    function estiloCampo(id, clave) {
        if (erroresCampos[clave]) {
            return { className: inputError, "aria-invalid": "true", "aria-describedby": `${id}-error` };
        }
        if (campoConError === id) {
            return { className: inputError, "aria-invalid": "true", "aria-describedby": "ger-error" };
        }
        return { className: inputNormal };
    }

    function errorCampo(id, clave) {
        if (!erroresCampos[clave]) return null;
        return (
            <p id={`${id}-error`} className="mt-1 text-[11px] font-medium text-red-600">
                {erroresCampos[clave]}
            </p>
        );
    }
    return (
        <div className="space-y-6">
            <div>
                <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                    Administración general · Alta de usuarios
                </p>
                <h1 className="font-titulo mt-1 text-2xl font-semibold text-slate-900 sm:text-3xl">
                    Alta de gerente médico
                </h1>
                <p className="mt-1 text-sm text-slate-600">
                    Registrá un profesional con facultades de gerencia médica.
                </p>
            </div>

            {registroExitoso ? (
                <section className="rounded-2xl border border-emerald-200 bg-white p-6 shadow-xs">
                    <div className="flex items-start gap-3">
                        <span className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-sm font-semibold text-emerald-700">✓</span>
                        <div>
                            <h2 className="text-base font-semibold text-slate-900">
                                Gerente médico registrado exitosamente
                            </h2>
                            <div className="mt-4 rounded-xl border border-slate-100 bg-slate-50 p-4 text-xs text-slate-700">
                                <p><span className="font-semibold">Nombre:</span> {registroExitoso.nombre} {registroExitoso.apellido}</p>
                                <p className="mt-1"><span className="font-semibold">Email:</span> {registroExitoso.email}</p>
                                <p className="mt-1"><span className="font-semibold">Matrícula:</span> {registroExitoso.matricula}</p>
                                <p className="mt-1"><span className="font-semibold">Especialidades:</span>{" "}
                                    {registroExitoso.especialidades.map((e) => e.nombre).join(", ")}
                                </p>
                            </div>
                            <button
                                type="button"
                                onClick={reiniciarFormulario}
                                className="mt-5 inline-flex items-center justify-center rounded-xl bg-[#0B4F8A] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#093E6D]"
                            >
                                Registrar otro gerente médico
                            </button>
                        </div>
                    </div>
                </section>
            ) : (
                <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                    <section
                        aria-label="Formulario de alta de gerente médico"
                        className="overflow-hidden rounded-2xl border border-white/80 bg-gradient-to-br from-white/85 via-white/75 to-[#EAF3FA]/80 shadow-lg shadow-[#0B4F8A]/10 backdrop-blur-md lg:col-span-8"
                    >
                        <div className="h-1.5 w-full bg-gradient-to-r from-[#062846] via-[#0B4F8A] to-[#0891B2]" />
                        <div className="p-6">
                            {error && (
                                <div
                                    role="alert"
                                    id="ger-error"
                                    className={`mb-4 rounded-xl border px-3.5 py-2.5 text-xs font-medium ${
                                        codigoError === "SOLO_ADMIN_GENERAL"
                                            ? "border-amber-200 bg-amber-50 text-amber-900"
                                            : "border-red-200 bg-red-50 text-red-700"
                                    }`}
                                >
                                    {error}
                                </div>
                            )}

                            <form onSubmit={handleSubmit} noValidate className="space-y-4">
                                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                                    <div>
                                        <label htmlFor="ger-nombre" className="mb-1.5 block text-xs font-medium text-slate-700">Nombre</label>
                                        <input
                                            id="ger-nombre" type="text" maxLength={100}
                                            value={nombre}
                                            onChange={(e) => setNombre(e.target.value)}
                                            {...estiloCampo("ger-nombre", "nombre")}
                                        />
                                        {errorCampo("ger-nombre", "nombre")}
                                    </div>
                                    <div>
                                        <label htmlFor="ger-apellido" className="mb-1.5 block text-xs font-medium text-slate-700">Apellido</label>
                                        <input
                                            id="ger-apellido" type="text" maxLength={100}
                                            value={apellido}
                                            onChange={(e) => setApellido(e.target.value)}
                                            {...estiloCampo("ger-apellido", "apellido")}
                                        />
                                        {errorCampo("ger-apellido", "apellido")}
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                                    <div>
                                        <label htmlFor="ger-matricula" className="mb-1.5 block text-xs font-medium text-slate-700">Matrícula profesional</label>
                                        <input
                                            id="ger-matricula" type="text" maxLength={50}
                                            value={matricula}
                                            onChange={(e) => setMatricula(e.target.value)}
                                            {...estiloCampo("ger-matricula", "matricula")}
                                        />
                                        {errorCampo("ger-matricula", "matricula")}
                                    </div>
                                    <div>
                                        <label htmlFor="ger-telefono" className="mb-1.5 block text-xs font-medium text-slate-700">Teléfono</label>
                                        <input
                                            id="ger-telefono" type="tel" maxLength={30}
                                            value={telefono}
                                            onChange={(e) => setTelefono(e.target.value)}
                                            {...estiloCampo("ger-telefono", "telefono")}
                                        />
                                        {errorCampo("ger-telefono", "telefono")}
                                    </div>
                                </div>

                                <div>
                                    <label htmlFor="ger-email" className="mb-1.5 block text-xs font-medium text-slate-700">Correo electrónico</label>
                                    <input
                                        id="ger-email" type="email" autoComplete="off"
                                        value={email}
                                        onChange={(e) => setEmail(e.target.value)}
                                        {...estiloCampo("ger-email", "email")}
                                    />
                                    {errorCampo("ger-email", "email")}
                                </div>

                                <div>
                                    <label htmlFor="ger-password" className="mb-1.5 block text-xs font-medium text-slate-700">Contraseña</label>
                                    <div className="relative">
                                        <input
                                            id="ger-password"
                                            type={mostrarPassword ? "text" : "password"}
                                            autoComplete="new-password"
                                            placeholder="Mínimo 8 caracteres, al menos una letra y un número"
                                            value={password}
                                            onChange={(e) => setPassword(e.target.value)}
                                            className={`${erroresCampos.password ? inputError : inputNormal} pr-14`}
                                            aria-invalid={erroresCampos.password ? "true" : undefined}
                                            aria-describedby={erroresCampos.password ? "ger-password-error ger-password-ayuda" : "ger-password-ayuda"}
                                        />
                                        <button
                                            type="button"
                                            onClick={() => setMostrarPassword((v) => !v)}
                                            className="absolute inset-y-0 right-2 flex items-center px-2 text-xs font-medium text-slate-500 hover:text-slate-800"
                                        >
                                            {mostrarPassword ? "Ocultar" : "Ver"}
                                        </button>
                                    </div>
                                    {errorCampo("ger-password", "password")}
                                    <div id="ger-password-ayuda" aria-live="polite" className="mt-2">
                                        {passwordValida ? (
                                            <p className="flex items-center gap-1.5 text-[11px] font-medium text-emerald-700">
                                                <span aria-hidden="true">✓</span> La contraseña cumple los requisitos
                                            </p>
                                        ) : (
                                            <ul className="space-y-1">
                                                {requisitosPendientes.map((r) => (
                                                    <li key={r.id} className="flex items-center gap-1.5 text-[11px] text-slate-500">
                                                        <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-slate-400" />
                                                        {r.texto}
                                                    </li>
                                                ))}
                                            </ul>
                                        )}
                                    </div>
                                </div>

                                <fieldset
                                    id="ger-especialidades"
                                    tabIndex={-1}
                                    aria-invalid={especialidadesConError || undefined}
                                    aria-describedby={
                                        erroresCampos.especialidades
                                            ? "ger-especialidades-error"
                                            : campoConError === "ger-especialidades" ? "ger-error" : undefined
                                    }
                                    className={`rounded-xl border p-4 transition focus:outline-none ${
                                        especialidadesConError
                                            ? "border-red-300 bg-red-50/40"
                                            : "border-slate-200/80"
                                    }`}
                                >
                                    <legend className="px-1 text-xs font-medium text-slate-700">
                                        Especialidades médicas (seleccioná al menos una)
                                    </legend>


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
                                    {erroresCampos.especialidades && (
                                        <p id="ger-especialidades-error" className="mt-3 text-[11px] font-medium text-red-600">
                                            {erroresCampos.especialidades}
                                        </p>
                                    )}

                                </fieldset>
                                <div className="pt-2">
                                    <button
                                        type="submit"
                                        disabled={enviando || cargandoEspecialidades}
                                        className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-[#0B4F8A] to-[#0E7490] px-5 py-2.5 text-sm font-medium text-white shadow-sm transition hover:from-[#093E6D] hover:to-[#0B5E75] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] focus-visible:ring-offset-2 disabled:opacity-50"
                                    >
                                        {enviando ? "Registrando gerente médico..." : "Registrar gerente médico →"}
                                    </button>
                                </div>
                            </form>
                        </div>
                    </section>
                        <aside
                            aria-label="Información del gerente médico"
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
                                Facultades del gerente médico
                            </h2>
                            <p className="mt-1 text-xs text-cyan-100/85">
                                Este perfil va a poder:
                            </p>
                            <ul className="relative mt-5 space-y-3 text-xs">
                                <li className="rounded-xl border border-white/15 bg-white/10 p-3.5 backdrop-blur-xs">
                                    <p className="font-semibold text-white">Patologías y síntomas</p>
                                    <p className="mt-0.5 leading-relaxed text-cyan-100/90">
                                        Administrar el catálogo de patologías y sus síntomas SNOMED
                                    </p>
                                </li>
                                <li className="rounded-xl border border-white/15 bg-white/10 p-3.5 backdrop-blur-xs">
                                    <p className="font-semibold text-white">Cupones</p>
                                    <p className="mt-0.5 leading-relaxed text-cyan-100/90">
                                        Crear cupones de descuento para estudios 
                                    </p>
                                </li>
                                <li className="rounded-xl border border-white/15 bg-white/10 p-3.5 backdrop-blur-xs">
                                    <p className="font-semibold text-white">También opera como médico</p>
                                    <p className="mt-0.5 leading-relaxed text-cyan-100/90">
                                        Puede dar de alta pacientes y solicitar estudios
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
        </div>
    );
}