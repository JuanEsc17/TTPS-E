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

export function obtenerOrdenDelDiaHoyRequest(token, { lat, lon, recalcular = false } = {}) {
    const params = new URLSearchParams();
    if (Number.isFinite(Number(lat)) && Number.isFinite(Number(lon))) {
        params.set("lat", String(lat));
        params.set("lon", String(lon));
    }
    if (recalcular) {
        params.set("recalcular", "1");
    }
    const qs = params.toString();
    return requestJson(`/api/logistica/ordenes-del-dia/hoy${qs ? `?${qs}` : ""}`, { token });
}

export function marcarRecogidaParadaRequest({ token, ordenId, paradaId }) {
    return requestJson(`/api/logistica/ordenes-del-dia/${ordenId}/paradas/${paradaId}/recoger`, {
        token,
        method: "POST",
        body: {},
    });
}

export function marcarLlegadaLabCentralRequest({ token, ordenId }) {
    return requestJson(`/api/logistica/ordenes-del-dia/${ordenId}/llegada-laboratorio-central`, {
        token,
        method: "POST",
        body: {},
    });
}
