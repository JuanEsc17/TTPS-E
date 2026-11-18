export async function consultarChatbotRequest({
    token,
    pregunta,
    conversacionId = null,
    patologiaId = null,
}) {
    const body = { pregunta };
    if (conversacionId) {
        body.conversacion_id = conversacionId;
    }
    if (patologiaId !== null && patologiaId !== undefined) {
        body.patologia_id = patologiaId;
    }

    const resp = await fetch("/api/v1/chatbot/consultas", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
    });

    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || !data.ok) {
        const err = new Error(
            data.error ||
                "El asistente de consultas sobre patologías no se encuentra disponible en este momento. Por favor, intente nuevamente en unos instantes."
        );
        err.code = data.code;
        err.status = resp.status;
        err.retryable = Boolean(data.retryable);
        throw err;
    }

    return data.data;
}
