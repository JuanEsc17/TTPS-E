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