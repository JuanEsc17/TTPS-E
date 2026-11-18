function authHeaders(token) {
    return {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
    };
}

async function parseResponse(resp, fallbackMsg) {
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || !data.ok) {
        let mensaje = data.error || fallbackMsg;
        if (data.detalles && typeof data.detalles === "object") {
            const campos = Object.entries(data.detalles)
                .map(([campo, errs]) => `${campo}: ${Array.isArray(errs) ? errs.join(", ") : errs}`)
                .join(" | ");
            if (campos) {
                mensaje = `${mensaje} (${campos})`;
            }
        }
        const err = new Error(mensaje);
        err.code = data.code;
        err.retryable = Boolean(data.retryable);
        throw err;
    }
    return data.data;
}

export async function listarPacientesRequest(token) {
    const resp = await fetch("/api/v1/pacientes", {
        headers: { Authorization: `Bearer ${token}` },
    });
    return parseResponse(resp, "No se pudieron cargar los pacientes.");
}

export async function listarPatologiasRequest(token) {
    const resp = await fetch("/api/v1/patologias", {
        headers: { Authorization: `Bearer ${token}` },
    });
    return parseResponse(resp, "No se pudieron cargar las patologías.");
}

export async function buscarSintomasSnomedRequest(token, q) {
    const params = new URLSearchParams({ q, limite: "15" });
    const resp = await fetch(`/api/v1/snomed/sintomas?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
    });
    return parseResponse(resp, "No se pudo consultar SNOMED.");
}

export async function validarSintomasPatologiaRequest(
    token,
    patologiaId,
    sintomasSnomedIds,
    sintomasSeleccionados
) {
    const resp = await fetch(`/api/v1/patologias/${patologiaId}/validar-sintomas`, {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify({
            sintomas_snomed_ids: sintomasSnomedIds,
            sintomas_seleccionados: sintomasSeleccionados,
        }),
    });
    return parseResponse(resp, "Los síntomas no validan la patología seleccionada.");
}

export async function altaPacienteRequest(token, payload) {
    const resp = await fetch("/api/v1/pacientes", {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify(payload),
    });
    return parseResponse(resp, "No se pudo dar de alta al paciente.");
}
