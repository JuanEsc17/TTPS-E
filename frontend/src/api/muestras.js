async function requestMuestras(url, { token, method = "GET", body } = {}) {
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

export function listarTurnosPendientesMuestraRequest(
    token,
    { dni, estudioId, centroId, fecha } = {}
) {
    const params = new URLSearchParams();
    if (dni && String(dni).trim()) {
        params.set("dni", String(dni).trim());
    }
    if (estudioId !== undefined && estudioId !== null && String(estudioId).trim() !== "") {
        params.set("estudio_id", String(estudioId).trim());
    }
    if (centroId !== undefined && centroId !== null && String(centroId).trim() !== "") {
        params.set("centro_id", String(centroId).trim());
    }
    if (fecha && String(fecha).trim()) {
        params.set("fecha", String(fecha).trim());
    }
    const qs = params.toString();
    return requestMuestras(`/api/v1/muestras/pendientes${qs ? `?${qs}` : ""}`, { token });
}

export function registrarTomaMuestraRequest({ token, turnoId, tomadaEn } = {}) {
    const body = tomadaEn ? { tomada_en: tomadaEn } : {};
    return requestMuestras(`/api/v1/muestras/turnos/${turnoId}/toma`, {
        token,
        method: "POST",
        body,
    });
}
