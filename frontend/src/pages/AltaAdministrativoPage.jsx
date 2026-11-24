import { useState } from "react";

import { registrarAdministrativoRequest } from "../api/admin";

// Qué campo se pinta de rojo según el error que devuelve el backend
const CAMPO_POR_CODIGO = {
    EMAIL_YA_REGISTRADO: "adm-email",
};
const REQUISITOS_PASSWORD = [
    { id: "largo", texto: "Mínimo 8 caracteres", cumple: (p) => p.length >= 8 },
    { id: "letra", texto: "Al menos una letra", cumple: (p) => /[A-Za-zÁÉÍÓÚáéíóúÑñ]/.test(p) },
    { id: "numero", texto: "Al menos un número", cumple: (p) => /\d/.test(p) },
];
export default function AltaAdministrativoPage({ sesion }) {
    const esAdmin = sesion?.usuario?.rol === "admin_general";

    // Los campos del formulario
    const [nombre, setNombre] = useState("");
    const [apellido, setApellido] = useState("");
    const [telefono, setTelefono] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [mostrarPassword, setMostrarPassword] = useState(false);

    // Estado del envío
    const [enviando, setEnviando] = useState(false);
    const [error, setError] = useState("");
    const [codigoError, setCodigoError] = useState("");
    const [erroresCampos, setErroresCampos] = useState({});
    const [registroExitoso, setRegistroExitoso] = useState(null);

    // Campo en rojo por un error que devolvió el backend (o null si ninguno)
    const campoConError = CAMPO_POR_CODIGO[codigoError] || null;
    const requisitosPendientes = REQUISITOS_PASSWORD.filter((r) => !r.cumple(password));
    const passwordValida = requisitosPendientes.length === 0;

    if (!esAdmin) {
        return (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
                Solo el admin general puede registrar administrativos.
            </div>
        );
    }

    // Botón "Registrar otro": deja todo vacío
    function reiniciarFormulario() {
        setNombre(""); setApellido(""); setTelefono("");
        setEmail(""); setPassword("");
        setMostrarPassword(false);
        setError(""); setCodigoError(""); setErroresCampos({});
        setRegistroExitoso(null);
    }

    // Mismas reglas que el backend (usuario_service._validar_alta_por_admin)
    function validarFormulario() {
        const errs = {};
        if (!nombre.trim()) errs.nombre = "Ingresá el nombre.";
        if (!apellido.trim()) errs.apellido = "Ingresá el apellido.";

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
            const administrativo = await registrarAdministrativoRequest({
                token: sesion.access_token, nombre, apellido, telefono, email, password,
            });
            setRegistroExitoso(administrativo);
        } catch (err) {
            const code = err.code || "";
            setCodigoError(code);
            setError(code === "DB_ERROR" ? `${err.message} Podés volver a intentarlo.` : err.message);


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
            return { className: inputError, "aria-invalid": "true", "aria-describedby": "adm-error" };
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
                    Alta de administrativo
                </h1>
                <p className="mt-1 text-sm text-slate-600">
                    Registrá un administrativo.
                </p>
            </div>

            {registroExitoso ? (
                <section className="rounded-2xl border border-emerald-200 bg-white p-6 shadow-xs">
                    <div className="flex items-start gap-3">
                        <span className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-sm font-semibold text-emerald-700">✓</span>
                        <div>
                            <h2 className="text-base font-semibold text-slate-900">
                                Administrativo registrado exitosamente
                            </h2>
                            <div className="mt-4 rounded-xl border border-slate-100 bg-slate-50 p-4 text-xs text-slate-700">
                                <p><span className="font-semibold">Nombre:</span> {registroExitoso.nombre} {registroExitoso.apellido}</p>
                                <p className="mt-1"><span className="font-semibold">Email:</span> {registroExitoso.email}</p>
                                <p className="mt-1"><span className="font-semibold">Teléfono:</span> {registroExitoso.telefono}</p>
                            </div>
                            <button
                                type="button"
                                onClick={reiniciarFormulario}
                                className="mt-5 inline-flex items-center justify-center rounded-xl bg-[#0B4F8A] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#093E6D]"
                            >
                                Registrar otro administrativo
                            </button>
                        </div>
                    </div>
                </section>
            ) : (
                <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                    <section
                        aria-label="Formulario de alta de administrativo"
                        className="overflow-hidden rounded-2xl border border-white/80 bg-gradient-to-br from-white/85 via-white/75 to-[#EAF3FA]/80 shadow-lg shadow-[#0B4F8A]/10 backdrop-blur-md lg:col-span-8"
                    >
                        <div className="h-1.5 w-full bg-gradient-to-r from-[#062846] via-[#0B4F8A] to-[#0891B2]" />
                        <div className="p-6">
                            {error && (
                                <div
                                    role="alert"
                                    id="adm-error"
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
                                        <label htmlFor="adm-nombre" className="mb-1.5 block text-xs font-medium text-slate-700">Nombre</label>
                                        <input
                                            id="adm-nombre" type="text" maxLength={100}
                                            value={nombre}
                                            onChange={(e) => setNombre(e.target.value)}
                                            {...estiloCampo("adm-nombre", "nombre")}
                                        />
                                        {errorCampo("adm-nombre", "nombre")}
                                    </div>
                                    <div>
                                        <label htmlFor="adm-apellido" className="mb-1.5 block text-xs font-medium text-slate-700">Apellido</label>
                                        <input
                                            id="adm-apellido" type="text" maxLength={100}
                                            value={apellido}
                                            onChange={(e) => setApellido(e.target.value)}
                                            {...estiloCampo("adm-apellido", "apellido")}
                                        />
                                        {errorCampo("adm-apellido", "apellido")}
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                                    <div>
                                        <label htmlFor="adm-telefono" className="mb-1.5 block text-xs font-medium text-slate-700">Teléfono</label>
                                        <input
                                            id="adm-telefono" type="tel" maxLength={30}
                                            value={telefono}
                                            onChange={(e) => setTelefono(e.target.value)}
                                            {...estiloCampo("adm-telefono", "telefono")}
                                        />
                                        {errorCampo("adm-telefono", "telefono")}
                                    </div>
                                    <div>
                                        <label htmlFor="adm-email" className="mb-1.5 block text-xs font-medium text-slate-700">Correo electrónico</label>
                                        <input
                                            id="adm-email" type="email" autoComplete="off"
                                            value={email}
                                            onChange={(e) => setEmail(e.target.value)}
                                            {...estiloCampo("adm-email", "email")}
                                        />
                                        {errorCampo("adm-email", "email")}
                                    </div>
                                </div>

                                <div>
                                    <label htmlFor="adm-password" className="mb-1.5 block text-xs font-medium text-slate-700">Contraseña</label>
                                    <div className="relative">
                                        <input
                                            id="adm-password"
                                            type={mostrarPassword ? "text" : "password"}
                                            autoComplete="new-password"
                                            placeholder="Mínimo 8 caracteres, al menos una letra y un número"
                                            value={password}
                                            onChange={(e) => setPassword(e.target.value)}
                                            className={`${erroresCampos.password ? inputError : inputNormal} pr-14`}
                                            aria-invalid={erroresCampos.password ? "true" : undefined}
                                            aria-describedby={erroresCampos.password ? "adm-password-error adm-password-ayuda" : "adm-password-ayuda"}
                                        />
                                        <button
                                            type="button"
                                            onClick={() => setMostrarPassword((v) => !v)}
                                            className="absolute inset-y-0 right-2 flex items-center px-2 text-xs font-medium text-slate-500 hover:text-slate-800"
                                        >
                                            {mostrarPassword ? "Ocultar" : "Ver"}
                                        </button>
                                    </div>
                                    {errorCampo("adm-password", "password")}
                                    <div id="adm-password-ayuda" aria-live="polite" className="mt-2">
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

                                <div className="pt-2">
                                    <button
                                        type="submit"
                                        disabled={enviando}
                                        className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-[#0B4F8A] to-[#0E7490] px-5 py-2.5 text-sm font-medium text-white shadow-sm transition hover:from-[#093E6D] hover:to-[#0B5E75] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] focus-visible:ring-offset-2 disabled:opacity-50"
                                    >
                                        {enviando ? "Registrando administrativo..." : "Registrar administrativo →"}
                                    </button>
                                </div>
                            </form>
                        </div>
                    </section>
                        <aside
                            aria-label="Información del administrativo"
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
                                Facultades del administrativo
                            </h2>
                            <p className="mt-1 text-xs text-cyan-100/85">
                                Este perfil va a poder:
                            </p>
                            <ul className="relative mt-5 space-y-3 text-xs">
                                 <li className="rounded-xl border border-white/15 bg-white/10 p-3.5 backdrop-blur-xs">
                                    <p className="font-semibold text-white">Presupuestos</p>
                                    <p className="mt-0.5 leading-relaxed text-cyan-100/90">
                                        Emitir el presupuesto de los estudios
                                    </p>
                                </li>
                                <li className="rounded-xl border border-white/15 bg-white/10 p-3.5 backdrop-blur-xs">
                                    <p className="font-semibold text-white">Obras sociales</p>
                                    <p className="mt-0.5 leading-relaxed text-cyan-100/90">
                                        Cargar la autorización o el rechazo de la obra social
                                    </p>
                                </li>
                                <li className="rounded-xl border border-white/15 bg-white/10 p-3.5 backdrop-blur-xs">
                                    <p className="font-semibold text-white">Datos crudos</p>
                                    <p className="mt-0.5 leading-relaxed text-cyan-100/90">
                                        Cargar los datos crudos recibidos de Corea
                                    </p>
                                </li>
                                <li className="rounded-xl border border-white/15 bg-white/10 p-3.5 backdrop-blur-xs">
                                    <p className="font-semibold text-white">Retiro del sample set</p>
                                    <p className="mt-0.5 leading-relaxed text-cyan-100/90">
                                        Programar el retiro con FedEx
                                    </p>
                                </li>
                            </ul>
                        </aside>   
                </div>
            )}
        </div>
    );
}