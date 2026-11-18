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

export function listarMisEstudiosRequest(token) {
    return requestJson("/api/v1/turnos/mis-estudios", { token });
}

export function listarMisTurnosRequest(token) {
    return requestJson("/api/v1/turnos/mis-turnos", { token });
}

export function listarCentrosRequest(token) {
    return requestJson("/api/v1/centros-extraccion", { token });
}

export function obtenerDisponibilidadRequest({ token, centroId, fecha }) {
    const params = new URLSearchParams({ fecha });
    return requestJson(
        `/api/v1/centros-extraccion/${centroId}/turnos-disponibles?${params.toString()}`,
        { token }
    );
}

export function reservarTurnoRequest({ token, estudioId, centroId, inicio }) {
    return requestJson(`/api/v1/estudios/${estudioId}/turnos`, {
        token,
        method: "POST",
        body: {
            centro_id: Number(centroId),
            inicio,
        },
    });
}

export function cancelarTurnoRequest({ token, turnoId }) {
    return requestJson(`/api/v1/turnos/${turnoId}/cancelar`, {
        token,
        method: "POST",
        body: {},
    });
}
