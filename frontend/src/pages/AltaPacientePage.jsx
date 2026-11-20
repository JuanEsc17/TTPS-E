import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
    altaPacienteRequest,
    buscarSintomasSnomedRequest,
    listarPatologiasRequest,
    validarSintomasPatologiaRequest,
} from "../api/pacientes";

const PARENTESCOS = [
    "progenitor",
    "hermano/a",
    "hijo/a",
    "abuelo/a materno/a",
    "abuelo/a paterno/a",
    "tío/a materno/a",
    "tío/a paterno/a",
    "primo/a materno/a",
    "primo/a paterno/a",
    "pareja del paciente",
];

function calcularEdad(fechaStr) {
    if (!fechaStr) return null;
    const hoy = new Date();
    const nac = new Date(`${fechaStr}T00:00:00`);
    if (Number.isNaN(nac.getTime())) return null;
    let edad = hoy.getFullYear() - nac.getFullYear();
    const m = hoy.getMonth() - nac.getMonth();
    if (m < 0 || (m === 0 && hoy.getDate() < nac.getDate())) {
        edad -= 1;
    }
    return edad;
}

export default function AltaPacientePage({ sesion }) {
    const token = sesion?.access_token;

    const [patologias, setPatologias] = useState([]);
    const [cargandoPatologias, setCargandoPatologias] = useState(true);

    // Datos personales
    const [dni, setDni] = useState("");
    const [nombre, setNombre] = useState("");
    const [apellido, setApellido] = useState("");
    const [telefono, setTelefono] = useState("");
    const [email, setEmail] = useState("");
    const [fechaNacimiento, setFechaNacimiento] = useState("");
    const [responsableNombre, setResponsableNombre] = useState("");
    const [responsableDni, setResponsableDni] = useState("");

    // Datos clinicos
    const [diagnosticoId, setDiagnosticoId] = useState("");
    const [tipoSospecha, setTipoSospecha] = useState("clinica");
    const [historiaClinica, setHistoriaClinica] = useState("");

    // Sintomas SNOMED (E36)
    const [busquedaSnomed, setBusquedaSnomed] = useState("");
    const [resultadosSnomed, setResultadosSnomed] = useState([]);
    const [buscandoSnomed, setBuscandoSnomed] = useState(false);
    const [errorSnomed, setErrorSnomed] = useState("");
    const [sintomasSeleccionados, setSintomasSeleccionados] = useState([]);
    const [validacionClinica, setValidacionClinica] = useState(null);

    // Informacion familiar (E1 / E19)
    const [sinInfoFamiliar, setSinInfoFamiliar] = useState(false);
    const [familiares, setFamiliares] = useState([]);
    const [nuevoFamParentesco, setNuevoFamParentesco] = useState("progenitor");
    const [nuevoFamNombre, setNuevoFamNombre] = useState("");
    const [nuevoFamDiag, setNuevoFamDiag] = useState("");

    const [enviando, setEnviando] = useState(false);
    const [error, setError] = useState("");
    const [erroresCampos, setErroresCampos] = useState({});
    const [pacienteCreado, setPacienteCreado] = useState(null);

    const edad = useMemo(() => calcularEdad(fechaNacimiento), [fechaNacimiento]);
    const esMenor = edad !== null && edad < 18;

    useEffect(() => {
        if (!token) return;
        setCargandoPatologias(true);
        listarPatologiasRequest(token)
            .then((lista) => {
                setPatologias(lista || []);
                if (lista?.length > 0) {
                    setDiagnosticoId(String(lista[0].id));
                }
            })
            .catch((err) => setError(err.message))
            .finally(() => setCargandoPatologias(false));
    }, [token]);

    async function handleBuscarSnomed() {
        const q = busquedaSnomed.trim();
        setErrorSnomed("");
        if (q.length < 3) {
            setErrorSnomed("Ingresá al menos 3 letras para buscar en SNOMED.");
            return;
        }
        setBuscandoSnomed(true);
        try {
            const data = await buscarSintomasSnomedRequest(token, q);
            setResultadosSnomed(data.resultados || []);
        } catch (err) {
            setErrorSnomed(err.message);
        } finally {
            setBuscandoSnomed(false);
        }
    }

    function agregarSintoma(item) {
        if (sintomasSeleccionados.some((s) => s.snomed_id === item.snomed_id)) return;
        setSintomasSeleccionados((prev) => [...prev, item]);
        setValidacionClinica(null);
    }

    function quitarSintoma(snomedId) {
        setSintomasSeleccionados((prev) => prev.filter((s) => s.snomed_id !== snomedId));
        setValidacionClinica(null);
    }

    async function handlePreValidarSintomas() {
        setError("");
        setValidacionClinica(null);
        if (!diagnosticoId || sintomasSeleccionados.length === 0) {
            setValidacionClinica({
                ok: false,
                mensaje: "Seleccioná una patología y al menos un síntoma.",
            });
            return;
        }
        try {
            await validarSintomasPatologiaRequest(
                token,
                Number(diagnosticoId),
                sintomasSeleccionados.map((s) => s.snomed_id),
                sintomasSeleccionados
            );
            setValidacionClinica({
                ok: true,
                mensaje: "Los síntomas cumplen con el criterio clínico de la patología.",
            });
        } catch (err) {
            setValidacionClinica({ ok: false, mensaje: err.message });
        }
    }

    function agregarFamiliar() {
        if (!nuevoFamNombre.trim()) return;
        setFamiliares((prev) => [
            ...prev,
            {
                parentesco: nuevoFamParentesco,
                nombre: nuevoFamNombre.trim(),
                diagnostico_previo: nuevoFamDiag.trim() || null,
                sintomas_snomed_ids: [],
            },
        ]);
        setNuevoFamNombre("");
        setNuevoFamDiag("");
    }

    function quitarFamiliar(idx) {
        setFamiliares((prev) => prev.filter((_, i) => i !== idx));
    }

    function validarFormulario() {
        const errs = {};
        const dniLimpio = dni.trim();
        if (!/^\d{7,10}$/.test(dniLimpio)) {
            errs.dni = "El DNI debe contener entre 7 y 10 dígitos numéricos (sin puntos ni letras).";
        }
        if (!nombre.trim()) errs.nombre = "Ingresá el nombre del paciente.";
        if (!apellido.trim()) errs.apellido = "Ingresá el apellido del paciente.";
        if (!fechaNacimiento) {
            errs.fechaNacimiento = "Seleccioná la fecha de nacimiento.";
        } else if (edad !== null && edad < 0) {
            errs.fechaNacimiento = "La fecha de nacimiento debe ser anterior a hoy.";
        }

        const tel = telefono.trim();
        const digitosTel = (tel.match(/\d/g) || []).length;
        if (!tel || !/^\+?[\d\s\-()]{7,20}$/.test(tel) || digitosTel < 7) {
            errs.telefono = "Ingresá un teléfono válido (al menos 7 dígitos).";
        }
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
            errs.email = "Ingresá un correo electrónico válido.";
        }
        if (esMenor) {
            if (!responsableNombre.trim()) errs.responsableNombre = "Ingresá el nombre del responsable.";
            if (!/^\d{7,10}$/.test(responsableDni.trim())) {
                errs.responsableDni = "El DNI del responsable debe tener entre 7 y 10 dígitos numéricos.";
            }
        }
        if (!diagnosticoId) errs.diagnosticoId = "Seleccioná una patología sospechada.";
        if (!historiaClinica.trim()) errs.historiaClinica = "Ingresá la historia clínica.";
        if (sintomasSeleccionados.length === 0) {
            errs.sintomas = "Cargá al menos un síntoma SNOMED.";
        }
        return errs;
    }

    async function handleSubmit(e) {
        e.preventDefault();
        setError("");

        const errs = validarFormulario();
        setErroresCampos(errs);
        if (Object.keys(errs).length > 0) {
            setError("Revisá los campos marcados antes de confirmar el alta.");
            window.scrollTo({ top: 0, behavior: "smooth" });
            return;
        }

        setEnviando(true);
        try {
            const creado = await altaPacienteRequest(token, {
                dni,
                nombre,
                apellido,
                telefono,
                email,
                fecha_nacimiento: fechaNacimiento,
                diagnostico_presuntivo_id: Number(diagnosticoId),
                historia_clinica: historiaClinica,
                tipo_sospecha: tipoSospecha,
                responsable_nombre: esMenor ? responsableNombre : null,
                responsable_dni: esMenor ? responsableDni : null,
                sintomas_snomed_ids: sintomasSeleccionados.map((s) => s.snomed_id),
                sin_informacion_familiar: sinInfoFamiliar,
                familiares: sinInfoFamiliar ? [] : familiares,
            });
            setPacienteCreado(creado);
        } catch (err) {
            setError(err.message);
            window.scrollTo({ top: 0, behavior: "smooth" });
        } finally {
            setEnviando(false);
        }
    }

    if (pacienteCreado) {
        return (
            <section className="tarjeta-cristal">
                <div className="h-1.5 w-full bg-gradient-to-r from-emerald-500 to-[#0891B2]" />
                <div className="p-6">
                    <h1 className="font-titulo text-2xl font-semibold text-slate-900">
                        Paciente dado de alta
                    </h1>
                    <p className="mt-1 text-sm text-slate-600">
                        Se enviaron las credenciales iniciales a <strong>{pacienteCreado.email}</strong>.
                    </p>
                    <div className="mt-4 grid grid-cols-1 gap-3 rounded-xl border border-slate-200/80 bg-[#E6EFF7]/60 p-4 text-xs sm:grid-cols-2">
                        <p><span className="font-semibold">Paciente:</span> {pacienteCreado.nombre} {pacienteCreado.apellido}</p>
                        <p><span className="font-semibold">DNI:</span> {pacienteCreado.dni}</p>
                        <p><span className="font-semibold">Tipo de sospecha:</span> {pacienteCreado.tipo_sospecha}</p>
                        <p>
                            <span className="font-semibold">Familiograma:</span>{" "}
                            {pacienteCreado.familiograma_pdf_path ? "Generado" : "Sin información familiar (E19)"}
                        </p>
                    </div>
                    <div className="mt-5 flex flex-wrap gap-3">
                        <Link
                            to="/medico/pacientes"
                            className="rounded-xl bg-[#0B4F8A] px-4 py-2 text-xs font-medium text-white hover:bg-[#093E6D]"
                        >
                            Ver lista de pacientes
                        </Link>
                        <button
                            type="button"
                            onClick={() => window.location.reload()}
                            className="rounded-xl border border-slate-300 bg-white/80 px-4 py-2 text-xs font-medium text-slate-700 hover:bg-white"
                        >
                            Registrar otro paciente
                        </button>
                    </div>
                </div>
            </section>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[#0B4F8A]">
                        Consulta médica · Escenarios E1 / E19 / E36
                    </p>
                    <h1 className="font-titulo mt-1 text-2xl font-semibold text-slate-900">
                        Alta de paciente
                    </h1>
                </div>
                <Link to="/medico/pacientes" className="text-xs font-semibold text-[#0B4F8A] hover:underline">
                    ← Volver a pacientes
                </Link>
            </div>

            {error && (
                <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-medium text-red-700">
                    {error}
                </div>
            )}

            <form onSubmit={handleSubmit} noValidate className="space-y-6">
                {/* 1. Datos personales */}
                <section className="tarjeta-cristal">
                    <div className="h-1.5 w-full bg-gradient-to-r from-[#062846] via-[#0B4F8A] to-[#0891B2]" />
                    <div className="space-y-4 p-6">
                        <h2 className="text-sm font-semibold text-slate-900">
                            1. Datos personales del paciente
                        </h2>
                        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                            <div>
                                <label className="mb-1 block text-xs font-medium text-slate-700">DNI</label>
                                <input type="text" value={dni} onChange={(e) => setDni(e.target.value)} placeholder="40123456" className="campo-clinico" />
                                {erroresCampos.dni && <p className="mt-1 text-[11px] font-medium text-red-600">{erroresCampos.dni}</p>}
                            </div>
                            <div>
                                <label className="mb-1 block text-xs font-medium text-slate-700">Nombre</label>
                                <input type="text" value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="Juan" className="campo-clinico" />
                                {erroresCampos.nombre && <p className="mt-1 text-[11px] font-medium text-red-600">{erroresCampos.nombre}</p>}
                            </div>
                            <div>
                                <label className="mb-1 block text-xs font-medium text-slate-700">Apellido</label>
                                <input type="text" value={apellido} onChange={(e) => setApellido(e.target.value)} placeholder="Pérez" className="campo-clinico" />
                                {erroresCampos.apellido && <p className="mt-1 text-[11px] font-medium text-red-600">{erroresCampos.apellido}</p>}
                            </div>
                        </div>

                        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                            <div>
                                <label className="mb-1 block text-xs font-medium text-slate-700">Fecha de nacimiento</label>
                                <input type="date" value={fechaNacimiento} onChange={(e) => setFechaNacimiento(e.target.value)} className="campo-clinico" />
                                {erroresCampos.fechaNacimiento && <p className="mt-1 text-[11px] font-medium text-red-600">{erroresCampos.fechaNacimiento}</p>}
                            </div>
                            <div>
                                <label className="mb-1 block text-xs font-medium text-slate-700">Teléfono</label>
                                <input type="tel" value={telefono} onChange={(e) => setTelefono(e.target.value)} placeholder="+5492215551122" className="campo-clinico" />
                                {erroresCampos.telefono && <p className="mt-1 text-[11px] font-medium text-red-600">{erroresCampos.telefono}</p>}
                            </div>
                            <div>
                                <label className="mb-1 block text-xs font-medium text-slate-700">Correo electrónico</label>
                                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="paciente@ejemplo.com" className="campo-clinico" />
                                {erroresCampos.email && <p className="mt-1 text-[11px] font-medium text-red-600">{erroresCampos.email}</p>}
                            </div>
                        </div>

                        {esMenor && (
                            <div className="rounded-xl border border-amber-200 bg-amber-50/80 p-4">
                                <p className="mb-3 text-xs font-semibold text-amber-900">
                                    Paciente menor de edad ({edad} años): datos obligatorios del responsable
                                </p>
                                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                                    <div>
                                        <label className="mb-1 block text-xs font-medium text-slate-700">Nombre del responsable</label>
                                        <input type="text" value={responsableNombre} onChange={(e) => setResponsableNombre(e.target.value)} className="campo-clinico" />
                                        {erroresCampos.responsableNombre && <p className="mt-1 text-[11px] font-medium text-red-600">{erroresCampos.responsableNombre}</p>}
                                    </div>
                                    <div>
                                        <label className="mb-1 block text-xs font-medium text-slate-700">DNI del responsable</label>
                                        <input type="text" value={responsableDni} onChange={(e) => setResponsableDni(e.target.value)} className="campo-clinico" />
                                        {erroresCampos.responsableDni && <p className="mt-1 text-[11px] font-medium text-red-600">{erroresCampos.responsableDni}</p>}
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                </section>

                {/* 2. Diagnostico presuntivo e historia clinica */}
                <section className="tarjeta-cristal">
                    <div className="space-y-4 p-6">
                        <h2 className="text-sm font-semibold text-slate-900">
                            2. Diagnóstico presuntivo e historia clínica
                        </h2>
                        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                            <div>
                                <label className="mb-1 block text-xs font-medium text-slate-700">Patología sospechada</label>
                                <select
                                    required
                                    disabled={cargandoPatologias}
                                    value={diagnosticoId}
                                    onChange={(e) => {
                                        setDiagnosticoId(e.target.value);
                                        setValidacionClinica(null);
                                    }}
                                    className="campo-clinico"
                                >
                                    {patologias.length === 0 ? (
                                        <option value="">Sin patologías cargadas</option>
                                    ) : (
                                        patologias.map((p) => (
                                            <option key={p.id} value={p.id}>{p.nombre}</option>
                                        ))
                                    )}
                                </select>
                            </div>
                            <div>
                                <label className="mb-1 block text-xs font-medium text-slate-700">Tipo de sospecha</label>
                                <select value={tipoSospecha} onChange={(e) => setTipoSospecha(e.target.value)} className="campo-clinico">
                                    <option value="clinica">Clínica</option>
                                    <option value="familiar">Familiar</option>
                                </select>
                            </div>
                        </div>

                        <div>
                            <label className="mb-1 block text-xs font-medium text-slate-700">Historia clínica</label>
                            <textarea
                                rows={4}
                                value={historiaClinica}
                                onChange={(e) => setHistoriaClinica(e.target.value)}
                                placeholder="Resumen clínico del paciente..."
                                className="campo-clinico"
                            />
                            {erroresCampos.historiaClinica && <p className="mt-1 text-[11px] font-medium text-red-600">{erroresCampos.historiaClinica}</p>}
                        </div>
                    </div>
                </section>

                {/* 3. Sintomas SNOMED (E36) */}
                <section className="tarjeta-cristal">
                    <div className="space-y-4 p-6">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                            <div>
                                <h2 className="text-sm font-semibold text-slate-900">
                                    3. Síntomas del paciente (SNOMED CT)
                                </h2>
                                <p className="text-xs text-slate-500">
                                    Debe coincidir al menos el síntoma cardinal o 2 síntomas secundarios de la patología.
                                </p>
                            </div>
                            <button
                                type="button"
                                onClick={handlePreValidarSintomas}
                                className="rounded-xl border border-[#0B4F8A]/30 bg-[#EAF2FA] px-3 py-1.5 text-xs font-semibold text-[#0B4F8A] hover:bg-[#DCEAF7]"
                            >
                                Validar contra patología
                            </button>
                        </div>

                        <div className="flex gap-2">
                            <input
                                type="text"
                                value={busquedaSnomed}
                                onChange={(e) => setBusquedaSnomed(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === "Enter") {
                                        e.preventDefault();
                                        handleBuscarSnomed();
                                    }
                                }}
                                placeholder="Escribí al menos 3 letras (ej. cefalea, acroparestesia)..."
                                className="campo-clinico"
                            />
                            <button
                                type="button"
                                onClick={handleBuscarSnomed}
                                disabled={buscandoSnomed}
                                className="shrink-0 rounded-xl bg-[#0B4F8A] px-4 py-2.5 text-xs font-medium text-white hover:bg-[#093E6D] disabled:opacity-50"
                            >
                                {buscandoSnomed ? "Buscando..." : "Buscar SNOMED"}
                            </button>
                        </div>

                        {errorSnomed && <p className="text-xs text-red-600">{errorSnomed}</p>}

                        {resultadosSnomed.length > 0 && (
                            <div className="max-h-44 space-y-1 overflow-y-auto rounded-xl border border-slate-200 bg-white/80 p-2">
                                {resultadosSnomed.map((item) => (
                                    <button
                                        key={item.snomed_id}
                                        type="button"
                                        onClick={() => agregarSintoma(item)}
                                        className="flex w-full items-center justify-between rounded-lg px-3 py-1.5 text-left text-xs hover:bg-[#EAF2FA]"
                                    >
                                        <span className="font-medium text-slate-800">{item.descripcion}</span>
                                        <span className="font-mono text-[11px] text-slate-500">{item.snomed_id} +</span>
                                    </button>
                                ))}
                            </div>
                        )}

                        {sintomasSeleccionados.length > 0 && (
                            <div className="flex flex-wrap gap-2">
                                {sintomasSeleccionados.map((s) => (
                                    <span
                                        key={s.snomed_id}
                                        className="inline-flex items-center gap-2 rounded-full border border-[#0B4F8A]/30 bg-[#0B4F8A]/10 px-3 py-1 text-xs font-medium text-[#0B4F8A]"
                                    >
                                        {s.descripcion}
                                        <button
                                            type="button"
                                            onClick={() => quitarSintoma(s.snomed_id)}
                                            className="font-bold hover:text-red-600"
                                            aria-label={`Quitar ${s.descripcion}`}
                                        >
                                            ×
                                        </button>
                                    </span>
                                ))}
                            </div>
                        )}

                        {validacionClinica && (
                            <div
                                className={`rounded-xl border px-3.5 py-2 text-xs font-medium ${
                                    validacionClinica.ok
                                        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                                        : "border-red-200 bg-red-50 text-red-700"
                                }`}
                            >
                                {validacionClinica.mensaje}
                            </div>
                        )}
                    </div>
                </section>

                {/* 4. Informacion familiar (E1 / E19) */}
                <section className="tarjeta-cristal">
                    <div className="space-y-4 p-6">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                            <h2 className="text-sm font-semibold text-slate-900">
                                4. Información familiar (Familiograma)
                            </h2>
                            <label className="flex cursor-pointer items-center gap-2 text-xs font-medium text-slate-700">
                                <input
                                    type="checkbox"
                                    checked={sinInfoFamiliar}
                                    onChange={(e) => setSinInfoFamiliar(e.target.checked)}
                                    className="h-4 w-4 rounded border-slate-300 text-[#0B4F8A]"
                                />
                                Sin información familiar (E19)
                            </label>
                        </div>

                        {!sinInfoFamiliar && (
                            <>
                                <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
                                    <select
                                        value={nuevoFamParentesco}
                                        onChange={(e) => setNuevoFamParentesco(e.target.value)}
                                        className="campo-clinico"
                                    >
                                        {PARENTESCOS.map((par) => (
                                            <option key={par} value={par}>{par}</option>
                                        ))}
                                    </select>
                                    <input
                                        type="text"
                                        value={nuevoFamNombre}
                                        onChange={(e) => setNuevoFamNombre(e.target.value)}
                                        placeholder="Nombre completo del familiar"
                                        className="campo-clinico"
                                    />
                                    <input
                                        type="text"
                                        value={nuevoFamDiag}
                                        onChange={(e) => setNuevoFamDiag(e.target.value)}
                                        placeholder="Diagnóstico previo (opcional)"
                                        className="campo-clinico"
                                    />
                                    <button
                                        type="button"
                                        onClick={agregarFamiliar}
                                        className="rounded-xl border border-[#0B4F8A] bg-white/80 px-3 py-2 text-xs font-semibold text-[#0B4F8A] hover:bg-[#EAF2FA]"
                                    >
                                        + Agregar familiar
                                    </button>
                                </div>

                                {familiares.length > 0 && (
                                    <ul className="space-y-2">
                                        {familiares.map((f, idx) => (
                                            <li
                                                key={idx}
                                                className="flex items-center justify-between rounded-xl border border-slate-200 bg-white/80 px-3.5 py-2 text-xs"
                                            >
                                                <span>
                                                    <strong className="capitalize">{f.parentesco}:</strong> {f.nombre}
                                                    {f.diagnostico_previo ? ` · Dx: ${f.diagnostico_previo}` : ""}
                                                </span>
                                                <button
                                                    type="button"
                                                    onClick={() => quitarFamiliar(idx)}
                                                    className="font-semibold text-red-600 hover:underline"
                                                >
                                                    Quitar
                                                </button>
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </>
                        )}
                    </div>
                </section>

                {error && (
                    <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-medium text-red-700">
                        {error}
                    </div>
                )}

                <div className="flex justify-end">
                    <button
                        type="submit"
                        disabled={enviando}
                        className="rounded-xl bg-gradient-to-r from-[#0B4F8A] to-[#0E7490] px-6 py-3 text-sm font-medium text-white shadow-sm transition hover:from-[#093E6D] hover:to-[#0B5E75] disabled:opacity-50"
                    >
                        {enviando ? "Registrando paciente..." : "Confirmar alta de paciente →"}
                    </button>
                </div>
            </form>
        </div>
    );
}
