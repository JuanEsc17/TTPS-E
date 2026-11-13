# Chatbot de GenLab: cómo conectarse

Módulo adicional 8 (M11). Este archivo tiene lo que necesitan para usar el chatbot en el sistema de su grupo.

## 1. Datos de acceso

| Dato | Valor | Dónde va |
|---|---|---|
| URL | `[https://vglzngsrbyagquqqmakf.supabase.co/functions/v1/chat]` | Variable de entorno `CHATBOT_URL` |
| Clave publishable | `[sb_publishable_oGrnSdrauwlw_NWXzCaXlA_hh1d3RaL]` | Header `apikey` (variable `CHATBOT_APIKEY`) |
| Token de su grupo | `[fb28c1e3421aac1004d93484bc3aea1eb26750914f15dacf02da078c9c30a08b]` | Header `x-chatbot-token` (variable `CHATBOT_TOKEN`) |

- La URL y la clave publishable son iguales para todos los grupos.
- El **token es solo de su grupo**. Si se pierde o se filtra, avísennos y emitimos uno nuevo: el anterior deja de servir.
- **No suban el token a Git** ni lo usen en código que corra en el navegador. Guárdenlo en un archivo `.env` que esté en el `.gitignore`.

## 2. Verificar que el servicio está activo

Hagan un `GET` a la URL, sin credenciales (alcanza con abrirla en el navegador). Tiene que responder:

```json 
{"estado": "ok"}
```

Si responde `503`, el servicio está apagado por el momento.

## 3. Primera consulta

`POST` a la misma URL, con los dos headers y un JSON.

En macOS, Linux o Git Bash:

```bash
curl -X POST "$CHATBOT_URL" \
  -H "apikey: $CHATBOT_APIKEY" \
  -H "x-chatbot-token: $CHATBOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"mensaje": "¿Qué es un exoma clínico?", "conversacion_id": null}'
```

En PowerShell (usen `curl.exe`, todo en una línea y con las comillas del JSON escapadas):

```powershell
curl.exe -X POST $env:CHATBOT_URL -H "apikey: $env:CHATBOT_APIKEY" -H "x-chatbot-token: $env:CHATBOT_TOKEN" -H "Content-Type: application/json" -d '{\"mensaje\": \"¿Qué es un exoma clínico?\", \"conversacion_id\": null}'
```

### Qué manda el pedido

| Campo | Obligatorio | Detalle |
|---|---|---|
| `mensaje` | Sí | De 1 a 1000 caracteres, y no puede ser solo espacios. Sin datos personales. |
| `conversacion_id` | No | El que devolvió la respuesta anterior. Sin él se abre una conversación nueva. Hasta 200 caracteres. |

### Qué devuelve (200)

```json
{
  "respuesta": "El exoma es la parte del ADN que tiene las instrucciones para fabricar proteínas...",
  "conversacion_id": "6ba1b3fd-9a65-48d7-8c8c-a805cd6e7239",
  "tipo": "respuesta"
}
```

El `tipo` tiene cuatro valores posibles:

| `tipo` | Cuándo | Qué hacer |
|---|---|---|
| `respuesta` | La consulta es del tema y hay información. También saludos y agradecimientos. | Mostrar la respuesta. |
| `fuera_de_alcance` | No es sobre estudios genéticos. | Mostrar la respuesta. |
| `derivar_medico` | Pide un diagnóstico, interpretar su resultado, o habla de síntomas propios o tratamientos. | Mostrar la respuesta. **No ofrecer contacto con el laboratorio.** |
| `sin_informacion` | Es del tema, pero la base no tiene lo necesario. | Mostrar la respuesta. |

En los cuatro casos, muestren el texto de `respuesta` tal cual.

## 4. Seguir una conversación

Guarden el `conversacion_id` de la primera respuesta y mándenlo en los mensajes siguientes. Así el servicio entiende preguntas como «¿y cómo se hereda?».

- Se recuerdan los últimos 6 intercambios.
- La conversación se olvida a los 30 minutos sin mensajes.
- Es solo de su grupo: otro grupo no la puede ver aunque use el mismo identificador.

## 5. Errores y qué hacer

Todos devuelven un JSON con la clave `detail`.

| Código | Cuándo | Qué hacer |
|---|---|---|
| `401` | Falta la `apikey` o el token, o son incorrectos | Es un error de configuración de ustedes. Revisen los dos valores. No se lo muestren al paciente. |
| `422` | Mensaje vacío, solo espacios, de más de 1000 caracteres, o con formato incorrecto | Validen el mensaje en su pantalla antes de enviarlo. El `detail` es una lista que dice qué campo falló. |
| `429` | Pasaron el límite de consultas | Esperen los segundos del header `Retry-After` y reintenten **una sola vez**. |
| `503` | El chatbot está apagado | Muestren el `detail` tal cual y no reintenten en bucle. |
| `500` | Falla interna del servicio | Muestren un mensaje genérico y reintenten más tarde. |
| `405` | Método distinto de `GET` o `POST` | Revisen el método del pedido. |

Si la inteligencia artificial del servicio falla, **no hay error**: el chatbot responde igual con la información de su base y devuelve `200`. El formato de la respuesta es el mismo.

## 6. Ejemplo en código (desde su servidor)

Un solo archivo conoce el chatbot, así si algo cambia se arregla en un único lugar. Siempre con timeout, para que su aplicación no se cuelgue.

```js
// src/api/chatbot.js: único archivo que conoce el chatbot
const CHATBOT_URL = process.env.CHATBOT_URL;
const CHATBOT_APIKEY = process.env.CHATBOT_APIKEY;
const CHATBOT_TOKEN = process.env.CHATBOT_TOKEN;

export async function askChatbot(message, conversationId = null) {
  const response = await fetch(CHATBOT_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      apikey: CHATBOT_APIKEY,
      "x-chatbot-token": CHATBOT_TOKEN,
    },
    body: JSON.stringify({ mensaje: message, conversacion_id: conversationId }),
    signal: AbortSignal.timeout(20000),
  });

  if (response.status === 429) {
    const seconds = Number(response.headers.get("Retry-After")) || 5;
    throw Object.assign(new Error("Demasiadas consultas"), { retryAfter: seconds });
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw Object.assign(new Error("Chatbot no disponible"), {
      status: response.status,
      detail: body.detail,
    });
  }
  return response.json(); // { respuesta, conversacion_id, tipo }
}
```

Para trabajar sin depender del servicio, hagan una versión falsa de `askChatbot` que devuelva `{ respuesta, conversacion_id, tipo }`.

## 7. Reglas importantes

1. **Llamen siempre desde su backend.** El frontend le habla a su backend, y el backend al chatbot. El token en el navegador queda a la vista de cualquiera.
2. **No manden datos personales:** ni nombre, ni DNI, ni mail, ni teléfono, ni resultados de un paciente. El servicio tapa mails y números largos, pero **no nombres**.
3. **Respeten los límites:** 1000 caracteres por mensaje y 20 consultas por minuto por grupo. No hagan consultas automáticas en bucle.
4. **Usen siempre un timeout** (por ejemplo, 20 segundos).
5. **Muestren que es un asistente automático** y que no reemplaza a un médico.

## 8. Limitaciones

- Responde **solo** sobre estudios genéticos y las patologías lisosomales: Fabry, Pompe, mucopolisacaridosis tipo 1, Gaucher y ASMD. Lo demás da `fuera_de_alcance`.
- No da diagnósticos, no interpreta resultados de una persona y no habla de tratamientos.
- Usa servicios de IA gratuitos, sin garantía de disponibilidad. Cuando fallan, responde con reglas y con el texto de su base, que es más literal.
- La base de conocimiento está en estado borrador, pendiente de validación. Las preguntas sobre plazos, precios o trámites dan `sin_informacion`.

## 9. Material y ayuda

- Presentación con probador interactivo: https://santiagoc1.github.io/GenLab_Presentacion/#10

Si algo no anda, escríbannos con el **código de estado y el mensaje** que ven.
