//Helper: hace el fetch con el token y, si el backend devuelve error lanza un error con code y ststus
async function requestJson(url, { token, method = "GET", body } = {}) {
    const headers = {
        Authorization: `Bearer ${token}`};
    if (body!== undefined) {
        headers["Content-Type"] = "application/json";
    }
    
    const resp = await fetch(url, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
        const error = new Error(data.error || "Error en la solicitud");
        error.code = data.code;
        error.status = resp.status;
        throw error;
    }
    return data.data;
}
export function registrarGerenteMedicoRequest({
    token, nombre, apellido, telefono, email, password, matricula, especialidadesIds,
}) {
    return requestJson("/api/v1/admin/gerentes-medicos", {
        token,
        method: "POST",
        body: {
            nombre, apellido, telefono, email, password, matricula,
            especialidades_ids: especialidadesIds,   // el backend lo espera en snake_case
        },
    });
}