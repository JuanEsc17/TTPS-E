import { obtenerDispositivoId } from "./auth";

export async function listarEspecialidadesRequest() {
    const resp = await fetch("/api/v1/especialidades");
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || !data.ok) {
        throw new Error(data.error || "No se pudieron cargar las especialidades.");
    }
    return data.data || [];
}

export async function registrarMedicoRequest({
    nombre,
    apellido,
    telefono,
    email,
    password,
    matricula,
    especialidadesIds,
}) {
    const resp = await fetch("/api/v1/medicos/registro", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            nombre,
            apellido,
            telefono,
            email,
            password,
            matricula,
            especialidades_ids: especialidadesIds,
            dispositivo_identificador: obtenerDispositivoId(),
        }),
    });

    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || !data.ok) {
        const err = new Error(data.error || "No se pudo completar el registro del médico.");
        err.code = data.code;
        err.retryable = Boolean(data.retryable);
        throw err;
    }
    return data.data;
}
