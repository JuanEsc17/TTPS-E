async function requestBio(url, { token, method = "GET", body } = {}) {
    const headers = { Authorization: `Bearer ${token}` };
    let payload = body;

    if (body !== undefined && !(body instanceof FormData)) {
        headers["Content-Type"] = "application/json";
        payload = JSON.stringify(body);
    }

    const resp = await fetch(url, {
        method,
        headers,
        body: payload,
    });

    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || !data.ok) {
        const err = new Error(data.error || "No se pudo completar la operación.");
        err.code = data.code;
        err.status = resp.status;
        err.retryable = Boolean(data.retryable);
        throw err;
    }
    return data;
}

export function listarEstudiosPendientesDatosCrudosRequest(token) {
    return requestBio("/api/estudios/pendientes-datos-crudos", { token });
}

export function cargarDatosCrudosRequest({
    token,
    estudioId,
    archivo,
    contenidoActg,
    nombreArchivo,
}) {
    if (archivo) {
        const formData = new FormData();
        formData.append("archivo_datos_crudos", archivo);
        return requestBio(`/api/estudios/${estudioId}/datos-crudos`, {
            token,
            method: "POST",
            body: formData,
        });
    }

    return requestBio(`/api/estudios/${estudioId}/datos-crudos`, {
        token,
        method: "POST",
        body: {
            nombre_archivo: nombreArchivo || undefined,
            contenido_actg: contenidoActg,
        },
    });
}

export function listarBandejaBioinformaticaRequest(token) {
    return requestBio("/api/bioinformatica/estudios", { token });
}

export function obtenerDatosCrudosEstudioRequest({ token, estudioId }) {
    return requestBio(`/api/bioinformatica/estudios/${estudioId}/datos-crudos`, { token });
}

export function tomarEstudioBioinformaticaRequest({ token, estudioId }) {
    return requestBio(`/api/bioinformatica/estudios/${estudioId}/tomar`, {
        token,
        method: "POST",
        body: {},
    });
}

export function consultarVariantesGenRequest({
    token,
    genId,
    q,
    clasificacion,
    limite = 50,
}) {
    const params = new URLSearchParams();
    if (q && q.trim()) params.set("q", q.trim());
    if (clasificacion) params.set("clasificacion", clasificacion);
    if (limite) params.set("limite", String(limite));
    const qs = params.toString();
    return requestBio(`/api/bioinformatica/genes/${genId}/variantes${qs ? `?${qs}` : ""}`, {
        token,
    });
}

export function registrarVariantesAnalisisRequest({ token, estudioId, variantesIds }) {
    return requestBio(`/api/bioinformatica/estudios/${estudioId}/analisis`, {
        token,
        method: "POST",
        body: { variantes_ids: variantesIds },
    });
}
