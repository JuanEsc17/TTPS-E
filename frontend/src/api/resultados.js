const TIMEOUT_MS = 10000;

async function fetchConTimeout(
    url,
    { token, method = "GET", body, signal, timeoutMs = TIMEOUT_MS } = {}
) {
    const controller = new AbortController();
    let porTimeout = false;
    const onExternalAbort = () => controller.abort();
    if (signal) {
        if (signal.aborted) {
            controller.abort();
        } else {
            signal.addEventListener("abort", onExternalAbort, { once: true });
        }
    }
    const timer = setTimeout(() => {
        porTimeout = true;
        controller.abort();
    }, timeoutMs);

    const headers = { Authorization: `Bearer ${token}` };
    if (body !== undefined) {
        headers["Content-Type"] = "application/json";
    }

    try {
        return await fetch(url, {
            method,
            headers,
            body: body !== undefined ? JSON.stringify(body) : undefined,
            signal: controller.signal,
        });
    } catch (err) {
        if (porTimeout) {
            const timeoutErr = new Error(
                "La solicitud demoró demasiado. Podés reintentar en unos segundos."
            );
            timeoutErr.code = "TIMEOUT";
            timeoutErr.retryable = true;
            throw timeoutErr;
        }
        if (err?.name === "AbortError") throw err;
        const netErr = new Error(
            "No se pudo conectar con el servidor. Verificá tu conexión e intentá nuevamente."
        );
        netErr.code = "NETWORK_ERROR";
        netErr.retryable = true;
        throw netErr;
    } finally {
        clearTimeout(timer);
        if (signal) signal.removeEventListener("abort", onExternalAbort);
    }
}

async function parsearError(resp, fallback) {
    const data = await resp.json().catch(() => ({}));
    const err = new Error(data.error || fallback);
    err.code = data.code;
    err.status = resp.status;
    err.retryable = Boolean(data.retryable);
    return err;
}

function extraerNombreArchivo(contentDisposition, fallback) {
    if (!contentDisposition) return fallback;
    const match = contentDisposition.match(/filename="?([^";]+)"?/i);
    return match?.[1]?.trim() || fallback;
}

export async function listarAvisosRequest(
    token,
    { soloNoLeidos = false, limite = 20, signal } = {}
) {
    const params = new URLSearchParams();
    if (soloNoLeidos) params.set("solo_no_leidos", "true");
    if (limite) params.set("limite", String(limite));
    const qs = params.toString() ? `?${params.toString()}` : "";

    const resp = await fetchConTimeout(`/api/avisos${qs}`, { token, signal });
    if (!resp.ok) {
        throw await parsearError(resp, "No se pudieron cargar los avisos.");
    }
    const data = await resp.json().catch(() => ({}));
    if (!data.ok) {
        const err = new Error(data.error || "No se pudieron cargar los avisos.");
        err.code = data.code;
        err.status = resp.status;
        err.retryable = Boolean(data.retryable);
        throw err;
    }
    return {
        no_leidos: Number(data.no_leidos) || 0,
        avisos: Array.isArray(data.avisos) ? data.avisos : [],
    };
}

export async function listarMisEstudiosResultadosRequest(token, { signal } = {}) {
    const resp = await fetchConTimeout("/api/estudios/mis-estudios", { token, signal });
    if (!resp.ok) {
        throw await parsearError(resp, "No se pudo cargar el listado de estudios.");
    }
    const data = await resp.json().catch(() => ({}));
    if (!data.ok) {
        const err = new Error(data.error || "No se pudo cargar el listado de estudios.");
        err.code = data.code;
        err.status = resp.status;
        err.retryable = Boolean(data.retryable);
        throw err;
    }
    return data.estudios || [];
}

export async function obtenerResultadoEstudioRequest({ token, estudioId, signal }) {
    const resp = await fetchConTimeout(`/api/estudios/${estudioId}/resultado`, { token, signal });
    if (!resp.ok) {
        throw await parsearError(resp, "No se pudo consultar el resultado del estudio.");
    }
    const data = await resp.json().catch(() => ({}));
    if (!data.ok) {
        const err = new Error(data.error || "No se pudo consultar el resultado del estudio.");
        err.code = data.code;
        err.status = resp.status;
        err.retryable = Boolean(data.retryable);
        throw err;
    }
    return data;
}

export async function descargarResultadoPdfRequest({ token, estudioId, analisisId } = {}) {
    const qs = analisisId ? `?analisis_id=${encodeURIComponent(analisisId)}` : "";
    const resp = await fetchConTimeout(`/api/estudios/${estudioId}/resultado/pdf${qs}`, {
        token,
        timeoutMs: 15000,
    });
    if (!resp.ok) {
        throw await parsearError(resp, "No se pudo descargar el PDF del resultado.");
    }

    const blob = await resp.blob();
    const fallback = `resultado_estudio_${estudioId}.pdf`;
    const nombreArchivo = extraerNombreArchivo(
        resp.headers.get("Content-Disposition"),
        fallback
    );

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

export async function obtenerHistorialAnalisisRequest({ token, estudioId, signal }) {
    const resp = await fetchConTimeout(`/api/estudios/${estudioId}/analisis`, { token, signal });
    if (!resp.ok) {
        throw await parsearError(resp, "No se pudo consultar el historial de análisis del estudio.");
    }
    const data = await resp.json().catch(() => ({}));
    if (!data.ok) {
        const err = new Error(
            data.error || "No se pudo consultar el historial de análisis del estudio."
        );
        err.code = data.code;
        err.status = resp.status;
        err.retryable = Boolean(data.retryable);
        throw err;
    }
    return data;
}

export async function solicitarReanalisisRequest({
    token,
    estudioId,
    nuevosGenesSimbolos,
    nuevaPatologiaSospechadaId = null,
}) {
    const payload = {
        nuevos_genes_simbolos: nuevosGenesSimbolos,
    };
    if (nuevaPatologiaSospechadaId) {
        payload.nueva_patologia_sospechada_id = Number(nuevaPatologiaSospechadaId);
    }

    const resp = await fetchConTimeout(`/api/estudios/${estudioId}/reanalisis`, {
        token,
        method: "POST",
        body: payload,
    });
    if (!resp.ok) {
        throw await parsearError(resp, "No se pudo solicitar el reanálisis del estudio.");
    }
    const data = await resp.json().catch(() => ({}));
    if (!data.ok) {
        const err = new Error(data.error || "No se pudo solicitar el reanálisis del estudio.");
        err.code = data.code;
        err.status = resp.status;
        err.retryable = Boolean(data.retryable);
        throw err;
    }
    return data;
}

export async function buscarGenesCatalogoRequest({ token, q = "", limite = 20, signal }) {
    const params = new URLSearchParams();
    if (q.trim()) params.set("q", q.trim());
    if (limite) params.set("limite", String(limite));
    const qs = params.toString() ? `?${params.toString()}` : "";

    const resp = await fetchConTimeout(`/api/genes${qs}`, { token, signal });
    if (!resp.ok) {
        throw await parsearError(resp, "No se pudo consultar el catálogo de genes.");
    }
    const data = await resp.json().catch(() => ({}));
    return Array.isArray(data.genes) ? data.genes : [];
}
