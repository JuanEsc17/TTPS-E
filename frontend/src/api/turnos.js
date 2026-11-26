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


export async function descargarConsentimientoTurnoPdfRequest({ token, turnoId }) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    let resp;
    try {
        resp = await fetch(`/api/v1/turnos/${turnoId}/consentimiento-pdf`, {
            headers: { Authorization: `Bearer ${token}` },
            signal: controller.signal,
        });
    } catch (err) {
        if (err?.name === "AbortError") {
            throw new Error("La descarga demoró demasiado. Intentá nuevamente.", { cause: err });
        }
        throw new Error("No se pudo conectar con el servidor para descargar el PDF.", {
            cause: err,
        });
    } finally {
        clearTimeout(timer);
    }

    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        const err = new Error(
            data.error || "No se pudo descargar la Orden de extracción y Consentimiento informado."
        );
        err.code = data.code;
        err.status = resp.status;
        throw err;
    }

    const blob = await resp.blob();
    const fallback = `orden_consentimiento_turno_${turnoId}.pdf`;
    const disposition = resp.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="?([^";]+)"?/i);
    const nombreArchivo = match?.[1]?.trim() || fallback;

    const url = URL.createObjectURL(blob);
    const enlace = document.createElement("a");
    enlace.href = url;
    enlace.download = nombreArchivo;
    document.body.appendChild(enlace);
    enlace.click();
    enlace.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return nombreArchivo;
}
