function authHeaders(token) {
    return {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
    };
}

async function parseResponse(resp, fallbackMsg) {
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || !data.ok) {
        const err = new Error(data.error || fallbackMsg);
        err.code = data.code;
        err.retryable = Boolean(data.retryable);
        throw err;
    }
    return data.data;
}

export async function listarEstudiosRequest(token) {
    const resp = await fetch("/api/v1/estudios", {
        headers: { Authorization: `Bearer ${token}` },
    });
    return parseResponse(resp, "No se pudieron cargar los estudios.");
}

export async function obtenerGenesPatologiaRequest(token, patologiaId, incluirSecundarios = false) {
    const resp = await fetch(
        `/api/v1/patologias/${patologiaId}/genes?incluir_secundarios=${incluirSecundarios}`,
        { headers: { Authorization: `Bearer ${token}` } }
    );
    return parseResponse(resp, "No se pudieron obtener los genes de la patología.");
}

export async function buscarGenesManualesRequest(token, q) {
    const params = new URLSearchParams({ q });
    const resp = await fetch(`/api/v1/bioinformatica/genes?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
    });
    return parseResponse(resp, "No se pudieron buscar genes.");
}

export async function listarObrasSocialesRequest(token) {
    const resp = await fetch("/api/v1/obras-sociales", {
        headers: { Authorization: `Bearer ${token}` },
    });
    return parseResponse(resp, "No se pudieron cargar las obras sociales.");
}

export async function altaEstudioRequest(token, payload) {
    const resp = await fetch("/api/v1/estudios", {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify(payload),
    });
    return parseResponse(resp, "No se pudo dar de alta el estudio.");
}

export async function listarEstudiosFamiliaresVinculadosRequest(token, estudioId) {
    const resp = await fetch(`/api/v1/estudios/${estudioId}/familiares-vinculados`, {
        headers: { Authorization: `Bearer ${token}` },
    });
    return parseResponse(resp, "No se pudieron cargar los estudios de familiares vinculados.");
}

export async function consultarEstudioFamiliarVinculadoRequest(token, estudioId, estudioRelacionadoId) {
    const resp = await fetch(
        `/api/v1/estudios/${estudioId}/familiares-vinculados/${estudioRelacionadoId}`,
        { headers: { Authorization: `Bearer ${token}` } }
    );
    return parseResponse(resp, "No se pudo consultar el detalle del estudio familiar vinculado.");
}
