const KEY_DISPOSITIVO = "exoma_dispositivo_id"
const KEY_SESION = "exoma_sesion"

export function obtenerDispositivoId() {
    let id = localStorage.getItem(KEY_DISPOSITIVO)
    if (!id) {
        id = crypto.randomUUID()
        localStorage.setItem(KEY_DISPOSITIVO, id)
    }
    return id
}

export function guardarSesion(sesion) {
    sessionStorage.setItem(KEY_SESION, JSON.stringify(sesion))
}

export function leerSesion() {
    try {
        return JSON.parse(sessionStorage.getItem(KEY_SESION) || "null")
    } catch {
        return null
    }
}

export async function loginRequest({ email, password }) {
    const resp = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            email,
            password,
            dispositivo_identificador: obtenerDispositivoId(),
        })
    })

    const data = await resp.json().catch(() => ({}))
    if (!resp.ok || !data.ok) {
        throw new Error(data.error || "No se pudo iniciar sesion.")
    }
    return data
}

export async function cambiarPasswordInicialRequest({
    tokenTemporal,
    passwordInicial,
    nuevaPassword,
    confirmacionPassword,
}) {
    const resp = await fetch("/api/v1/auth/cambiar-password-inicial", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${tokenTemporal}`,
        },
        body: JSON.stringify({
            password_inicial: passwordInicial,
            nueva_password: nuevaPassword,
            confirmacion_password: confirmacionPassword,
            dispositivo_identificador: obtenerDispositivoId(),
        })
    })

    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || !data.ok) {
        const err = new Error(data.error || "No se pudo actualizar la contrasena inicial.")
        err.code = data.code
        throw err
    }
    return data
}

export function limpiarSesion() {
    sessionStorage.removeItem(KEY_SESION)
}

export async function logoutRequest(token) {
    if (!token) return
    await fetch("/api/v1/auth/logout", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
    }).catch(() => { })
}

export async function verificarDispositivoRequest({ challengeToken, codigo }) {
    const resp = await fetch("/api/v1/auth/verificar-dispositivo", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${challengeToken}`,
        },
        body: JSON.stringify({
            codigo,
            dispositivo_identificador: obtenerDispositivoId()
        })
    })

    const data = await resp.json().catch(() => ({}))
    if (!resp.ok || !data.ok) {
        const err = new Error(data.error || "No se pudo verificar el dispositivo.")
        err.code = data.code
        throw err
    }
    return data;
}

export async function reenviarCodigoRequest(challengeToken) {
    const resp = await fetch("/api/v1/auth/reenviar-codigo-dispositivo", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${challengeToken}`
        },
        body: JSON.stringify({
            dispositivo_identificador: obtenerDispositivoId()
        })
    })

    const data = await resp.json().catch(() => ({}))

    if (!resp.ok || !data.ok) {
        const err = new Error(data.error || "No se pudo reenviar el codigo.")
        err.code = data.code
        throw err
    }

    return data
}

export async function cambiarPasswordRequest({
    token,
    passwordActual,
    passwordNueva,
    confirmacion,
}) {
    const resp = await fetch("/api/v1/auth/cambiar-password", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
            password_actual: passwordActual,
            password_nueva: passwordNueva,
            password_nueva_confirmacion: confirmacion,
        })
    })

    const data = await resp.json().catch(() => ({}))
    if (!resp.ok || !data.ok) {
        const err = new Error(data.error || "No se pudo actualizar la contraseña.")
        err.code = data.code
        err.status = resp.status
        throw err
    }
    return data
}