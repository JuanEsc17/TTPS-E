async function requestSampleSets(url, { token, signal } = {}) {
    const resp = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
        signal,
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || !data.ok) {
        const err = new Error(data.error || "No se pudieron consultar los sample-sets.");
        err.code = data.code;
        err.status = resp.status;
        throw err;
    }
    return data;
}

export async function listarSampleSetsRequest(token, { estado = "", signal } = {}) {
    const params = new URLSearchParams();
    if (estado && String(estado).trim()) {
        params.set("estado", String(estado).trim());
    }
    const qs = params.toString();
    const data = await requestSampleSets(`/api/sample-sets${qs ? `?${qs}` : ""}`, {
        token,
        signal,
    });
    return data.sample_sets || [];
}

export async function obtenerSampleSetRequest(token, sampleSetId, { signal } = {}) {
    const data = await requestSampleSets(`/api/sample-sets/${sampleSetId}`, {
        token,
        signal,
    });
    return data.sample_set || null;
}
