# API de Notificaciones por Email

**TTPS · Guía para los grupos**

Cómo mandar correos desde el sistema de tu grupo: un pedido, un id y una consulta de estado.

---

## Antes de empezar

### Cómo funciona

1. **Tu sistema**: hace `POST /avisos` con su API Key.
2. **La API**: valida el pedido y responde al instante.
3. **La cola**: por orden de llegada, compartida por todos los grupos.
4. **Gmail**: el correo sale desde la cuenta de tu grupo.

> **Es asíncrono:** la respuesta del POST quiere decir **«recibido»**, no **«enviado»**. Si salió o no, lo consultás después con `GET /avisos/{id}`.

### Lo que necesita tu grupo

**URL base**

```
https://jpnbycihugrzeeolobev.supabase.co/functions/v1
```

**Una API Key por grupo**

```
avs_<16 hex>_<64 hex>
```

Va en el encabezado **`X-API-Key`** de cada pedido. Identifica a tu sistema: no la compartas ni la subas a GitHub/GitLab.

**Una cuenta Gmail por grupo**

Es el remitente de todos los correos de tu sistema. Si le cambian la contraseña o le quitan el acceso a la app, **tus envíos quedan en espera** hasta que se renueve la autorización.

### Cuatro endpoints, una sola ruta

| Método | Ruta | Para qué sirve |
|--------|------|----------------|
| GET | `/avisos` | Probar que tu API Key funciona |
| POST | `/avisos` | Pedir el envío de un correo |
| GET | `/avisos/{id}` | Ver el estado de ese pedido |
| GET | `/avisos/pendientes` | Listar tus avisos que siguen sin terminar |

**Primera prueba**

```bash
curl https://…/functions/v1/avisos -H "X-API-Key: avs_…"
```

```
200 {"mensaje": "Autenticación exitosa", "sistema": {"nombre": "grupo07"}}
```

---

## Enviar un aviso

### El pedido: `POST /avisos`

**Encabezados**

```
POST /avisos
X-API-Key: avs_…
Idempotency-Key: resultado-123-aviso
Content-Type: application/json
```

> **`Idempotency-Key` es obligatoria:** un valor único por aviso. Si reintentás, mandá el mismo.

**Cuerpo (JSON)**

```json
{
  "asunto": "Tu resultado está listo para ser consultado en la web",
  "mensaje": "Ya podés ver tu resultado ingresando a la web.",
  "referencia": "RESULTADO-123",
  "destinatarios": [
    { "canal": "email", "destino": "paciente@mail.com" },
    { "canal": "email", "destino": "medico@mail.com" }
  ]
}
```

### Las reglas del pedido

| Campo | Regla | Si falla |
|-------|-------|----------|
| `asunto` | Obligatorio · hasta 200 caracteres | 400 |
| `mensaje` | Obligatorio · hasta 10.000 caracteres · texto plano | 400 |
| `referencia` | Opcional · texto o `null` | 400 |
| `destinatarios` | Entre 1 y 50 por aviso | 400 |
| `canal` | Siempre `"email"` | 400 |
| `destino` | Email válido · hasta 320 caracteres | 400 |
| `Idempotency-Key` | Obligatoria · hasta 200 caracteres | 400 |
| `Content-Type` | `application/json` | 415 |
| Cuerpo completo | JSON válido · hasta 64 KB | 400 / 413 |

### Las tres respuestas posibles

#### 202 · Aviso nuevo

Quedó en la cola. Guardá el `id`.

```
"id": "696a0cfc-…"
"estado": "pendiente"
"creado": true
```

#### 200 · Pedido repetido

Misma clave y mismo contenido: no se duplica.

```
"id": "696a0cfc-…"
"estado": "enviado"
"creado": false
```

#### 409 · Clave reutilizada

Misma clave con otro contenido. Para un aviso nuevo, usá una clave nueva.

```
"error": "Idempotency-Key utilizada con otro contenido"
```

---

## Seguir el envío

### La consulta: `GET /avisos/{id}`

```
GET /avisos/696a0cfc-…
X-API-Key: avs_…
```

- **`estado`** resume el aviso; **`envios`** trae el detalle de cada destinatario.
- Solo ves los avisos de tu sistema: un id ajeno responde **404**.
- El worker corre cada minuto: consultá **una vez por minuto** como mucho.

**Respuesta**

```json
200 {
  "id": "696a0cfc-…",
  "asunto": "Tu resultado está listo para ser consultado en la web", …
  "estado": "parcial",
  "envios": [
    { "destino": "paciente@mail.com",
      "estado": "enviado", "intentos": 1,
      "ultimo_error": null },
    { "destino": "medico@mail.com",
      "estado": "fallido", "intentos": 1,
      "ultimo_error": "Gmail HTTP 400: …" }
  ]
}
```

### Qué significa cada estado

**El aviso (campo `estado`)**

| Estado | Significado |
|--------|-------------|
| `pendiente` | Algún correo sigue en cola o se está enviando |
| `enviado` | Salieron todos los correos |
| `parcial` | Terminaron: unos salieron y otros fallaron |
| `fallido` | No salió ningún correo |

**Cada envío (`envios[].estado`)**

`pendiente` → `procesando` → `enviado` o `fallido`

> Un envío **`pendiente`** con **`ultimo_error`** no falló: está esperando (límite de Gmail o cuenta sin autorización) y se reintenta solo.

---

## Errores y ejemplos

### Códigos de error

Todas las respuestas de error son `{"error": "…"}`.

| Código | Cuándo pasa | Mensaje de ejemplo |
|--------|-------------|--------------------|
| 400 | Datos inválidos, falta `Idempotency-Key`, JSON mal formado o id que no es UUID | El asunto no puede estar vacío |
| 401 | Falta la API Key o es incorrecta | Credenciales inválidas |
| 403 | Clave revocada o vencida, o sistema desactivado | Credencial deshabilitada |
| 404 | El aviso no existe o es de otro sistema | Aviso no encontrado |
| 409 | `Idempotency-Key` reutilizada con otro contenido | Idempotency-Key utilizada con otro contenido |
| 413 | El cuerpo supera los 64 KB | Solicitud demasiado grande |
| 415 | El `Content-Type` no es `application/json` | Content-Type debe ser application/json |
| 500 | Falla del servidor: reintentá con la misma `Idempotency-Key` | Error interno |

### Ejemplo 1 de 5 · Probar la API Key

```
GET {{URL_BASE}}/avisos
```

**Headers**

```
X-API-Key: avs_3f9c…
```

**Body:** sin cuerpo.

**Respuesta `200 OK`**

```json
{
  "mensaje": "Autenticación exitosa",
  "sistema": {
    "nombre": "grupo07"
  }
}
```

> Si aparece el **nombre de tu sistema**, la clave está bien cargada.

> Sin la clave o con una clave mal copiada: **401** «Credenciales inválidas».

### Ejemplo 2 de 5 · Enviar un aviso

```
POST {{URL_BASE}}/avisos
```

**Headers**

```
X-API-Key: avs_3f9c…
Idempotency-Key: resultado-123-aviso
Content-Type: application/json
```

**Body · JSON**

```json
{
  "asunto": "Tu resultado está listo para ser consultado en la web",
  "mensaje": "Ya podés ver tu resultado ingresando a la web.",
  "destinatarios": [
    { "canal": "email", "destino": "paciente@mail.com" },
    { "canal": "email", "destino": "medico@mail.com" }
  ]
}
```

**Respuesta `202 Accepted`**

```json
{
  "id": "696a0cfc-4925-…",
  "estado": "pendiente",
  "creado": true
}
```

> Guardá el **id**: con él se consulta el estado de los dos correos.

### Ejemplo 3 de 5 · Consultar el estado, un minuto después

```
GET {{URL_BASE}}/avisos/696a0cfc-4925-4ee1-8426-41eb5040a0ea
```

**Headers**

```
X-API-Key: avs_3f9c…
```

**Body:** sin cuerpo.

**Respuesta `200 OK`**

```json
{
  "id": "696a0cfc-4925-…",
  "asunto": "Tu resultado está listo para ser consultado en la web", …
  "estado": "enviado",
  "envios": [
    { "destino": "paciente@mail.com",
      "estado": "enviado", "intentos": 1,
      "enviado_en": "2026-11-02 14:24:01+00:00",
      "ultimo_error": null },
    { "destino": "medico@mail.com", "estado": "enviado", … }
  ]
}
```

> El id es el que devolvió el **202** del ejemplo 2.

### Ejemplo 4 de 5 · Ver qué sigue en la cola

```
GET {{URL_BASE}}/avisos/pendientes?limite=10
```

**Headers**

```
X-API-Key: avs_3f9c…
```

**Params**

- `limite`: `10` (opcional · de 1 a 100 · por defecto 25)

**Body:** sin cuerpo.

> Solo aparecen avisos con envíos **sin terminar**, del más viejo al más nuevo.

**Respuesta `200 OK`**

```json
{
  "total": 2,
  "avisos": [
    { "id": "8b1f2c40-…",
      "asunto": "Tu resultado está listo…",
      "referencia": "RESULTADO-125",
      "creado_en": "2026-11-09 14:23:23+00:00",
      "total_envios": 2, "envios_pendientes": 1,
      "envios_enviados": 1, "envios_fallidos": 0 },
    { "id": "53d3a587-…", "envios_pendientes": 1, … }
  ]
}
```

### Ejemplo 5 de 5 · Un pedido con un error

```
POST {{URL_BASE}}/avisos
```

**Headers**

```
X-API-Key: avs_3f9c…
Idempotency-Key: resultado-124-aviso
Content-Type: application/json
```

**Body · JSON**

```json
{
  "asunto": "Tu resultado está listo para ser consultado en la web",
  "mensaje": "Ya podés ver tu resultado ingresando a la web.",
  "destinatarios": [
    { "canal": "email", "destino": "paciente.mail.com" },
    { "canal": "email", "destino": "medico@mail.com" }
  ]
}
```

**Respuesta `400 Bad Request`**

```json
{
  "error": "El destinatario 1 debe tener un email válido"
}
```

> No se registró nada, ni para el médico: corregí el dato y volvé a enviar.

---

## Para llevarse

### Seis buenas prácticas

1. **Llamala desde el backend.** La API Key no va en el navegador, en la app ni en Git: usá variables de entorno.
2. **Una clave por aviso.** Armá la `Idempotency-Key` con un dato tuyo, como `resultado-123-aviso`, y reusala al reintentar.
3. **Guardá el id.** Es lo único que necesitás para comprobar si el correo se envió.
4. **Consultá sin apuro.** Un correo tarda al menos un minuto, más si hay cola. No bloquees al usuario esperándolo.
5. **Cuidá la cuenta Gmail.** Sin autorización, los envíos esperan; si pasan 48 h, fallan. Avisá si cambiás la contraseña.
6. **Respetá los límites.** Gmail limita los envíos diarios: si tu cuenta llega al tope, se pausa y reintenta sola.

---

## ¿Preguntas?

- **Contrato completo:** `openapi.yaml`
- **URL base:** `https://jpnbycihugrzeeolobev.supabase.co/functions/v1`
- **Consultas:** por Telegram a cualquier integrante del grupo07
