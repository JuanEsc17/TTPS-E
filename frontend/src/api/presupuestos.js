async function requestPresupuestos(url, { token, method = "GET", body } = {}) {
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
        err.retryable = Boolean(data.retryable);
        throw err;
    }
    return data.data;
}

export function listarEstudiosPendientesPresupuestoRequest(token, { dni } = {}) {
    const params = new URLSearchParams();
    if (dni && String(dni).trim()) {
        params.set("dni", String(dni).trim());
    }
    const qs = params.toString();
    return requestPresupuestos(`/api/v1/presupuestos/pendientes${qs ? `?${qs}` : ""}`, { token });
}

export function emitirPresupuestoRequest({ token, estudioId }) {
    return requestPresupuestos(`/api/v1/estudios/${estudioId}/presupuesto`, {
        token,
        method: "POST",
        body: {},
    });
}