const TIMEOUT_MS = 10000;

async function fetchConTimeout(url, { token, signal, timeoutMs = TIMEOUT_MS } = {}) {
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

    try {
        return await fetch(url, {
            method: "GET",
            headers: { Authorization: `Bearer ${token}` },
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
