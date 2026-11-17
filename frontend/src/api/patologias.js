async function requestJson(url, { token, method = "GET", body } = {}) {
    const headers = { Authorization: `Bearer ${token}` };
    if (body !== undefined) {
        headers["Content-Type"] = "application/json";
    }

    const resp = await fetch(url, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || !data.ok) {
        const err = new Error(data.error || "No se pudo completar la operación.");
        err.code = data.code;
        err.status = resp.status;
        throw err;
    }
    return data.data;
}

export function listarPatologiasRequest(token) {
    return requestJson("/api/v1/patologias", { token });
}

export function guardarPatologiaRequest({ token, patologiaId, payload }) {
    const esEdicion = Boolean(patologiaId);
    return requestJson(
        esEdicion ? `/api/v1/patologias/${patologiaId}` : "/api/v1/patologias",
        {
            token,
            method: esEdicion ? "PUT" : "POST",
            body: payload,
        }
    );
}

export function buscarSintomasSnomedRequest({ token, q, limite = 10 }) {
    const params = new URLSearchParams({ q: q.trim(), limite: String(limite) });
    return requestJson(`/api/v1/sintomas/snomed?${params.toString()}`, { token });
}