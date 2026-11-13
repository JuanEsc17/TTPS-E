# INTEGRACIÓN DE SISTEMAS: API FedEx

**Retiros programados y seguimiento**

* `REST / JSON`
* `SUPABASE`
* `POSTMAN`

### GRUPO 3 - INTEGRANTES
* Gabriel Enrique Guas Córdova
* Nicolas Montanari
* Sofia Spazzarini
* Nicolas Quiñones

*Presentación API FedEx 2026*

---

## 01 / CONTEXTO
### ¿Qué resuelve esta API?
El cliente indica dónde y cuándo debe retirarse el paquete.

* **01. Programar un retiro:** El cliente especifica el lugar y la fecha del retiro del paquete.
* **02. Consultar el estado:** Consultar por UUID si un retiro continúa programado o ya alcanzó su fecha.
* **03. Listar los retiros:** Consultar el historial del cliente autenticado, con paginación.

> La API registra las solicitudes y permite consultar su estado.

*API FEDEX / SERVICIO DE RETIROS — 02*

---

## 02 / FLUJO DEL RETIRO
### Cómo funciona el retiro
El cliente indica dónde y cuándo debe retirarse el paquete.

* **01 / ETAPA — Datos del retiro:** El cliente indica el lugar y la fecha en la que debe realizarse el retiro del paquete.
* **02 / ETAPA — Registro de la solicitud:** La API registra la solicitud de retiro y devuelve un identificador único.
* **03 / ETAPA — Consulta de estado:** El cliente puede consultar el estado del retiro, que puede ser `PROGRAMADO` o `RETIRADO`.

> El cliente conserva el UUID y consulta `GET /retiros/{uuid}`.  
> La API recibe únicamente lugar y fecha; no requiere el contenido ni los datos del paquete.

*API FEDEX / SERVICIO DE RETIROS — 03*

---

## 03 / ARQUITECTURA
### Una integración HTTP sencilla
El backend del cliente consume una Edge Function desplegada en Supabase.

1. **SOLICITA — Sistema cliente:** Backend cliente / Postman
2. **VALIDA Y PROCESA — API FedEx:** Edge Function Deno / TypeScript
3. **ALMACENA — PostgreSQL:** Supabase Persistencia

* **Autenticación:** Basic Auth + bcrypt
* **Validaciones:** JSON, fecha, lugar, UUID
* **Tablas:** `clientes_api`, `retiros`

*API FEDEX / SERVICIO DE RETIROS — 04*

---

## 04 / CONTRATO REST
### Los 3 endpoints
Rutas HTTP disponibles y sus requisitos de autenticación.

| Método | Ruta | Descripción | Autenticación |
| :--- | :--- | :--- | :--- |
| `POST` | `/retiros` | Programar un retiro nuevo | Sí · Basic Auth |
| `GET` | `/retiros` | Listar retiros del cliente | Sí · Basic Auth |
| `GET` | `/retiros/{uuid}` | Consultar estado por ID | No · seguimiento |

* **BASE:** `https://blcecvxqrkvotawkunxk.supabase.co/functions/v1/fedex`
* `GET /retiros`: pagina 1–100000 (pred. 1) · limite 1–50 (pred. 10)

*API FEDEX / SERVICIO DE RETIROS — 05*

---

## 05 / REGLAS DE DATOS
### Fechas simples para los consumidores
La API toma el horario argentino como contrato de entrada y salida.

#### SOLICITUD POST (JSON de entrada)
```json
{
  "lugar": "La Plata, Buenos Aires",
  "fecha_programada": "2026-11-10T15:00:00"
}
```
*Sin sufijo horario en el POST*

#### NORMALIZACIÓN (La API interpreta UTC-3)
* **15:00** (Argentina) $\rightarrow$ **18:00** (UTC en base)
* **Respuesta:** `2026-11-10T15:00:00-03:00`

> El backend valida que la fecha exista, esté en el futuro y respete el formato `YYYY-MM-DDTHH:mm:ss`.

*API FEDEX / SERVICIO DE RETIROS — 06*

---

## 06 / POSTMAN CASO REAL
### POST /retiros: alta exitosa
El cliente envía lugar y fecha, y la API devuelve un identificador único.

* **Método y URL:** `POST https://blcecvxqrkvotawkunxk.supabase.co/functions/v1/fedex/retiros`
* **Estado:** `201 Created` (1.50 s · 1.28 KB)

#### Body (Request JSON)
```json
{
  "lugar": "La Plata, Buenos Aires",
  "fecha_programada": "2026-10-27T20:13:00"
}
```

#### Body (Response JSON)
```json
{
  "mensaje": "Retiro programado correctamente",
  "retiro": {
    "id": "f274b15b-c227-4211-a554-4f367bb4e1ae",
    "lugar": "La Plata, Buenos Aires",
    "fecha_programada": "2026-10-27T20:13:00-03:00",
    "url_seguimiento": "https://blcecvxqrkvotawkunxk.supabase.co/functions/v1/fedex/retiros/f274b15b-c227-4211-a554-4f367bb4e1ae"
  }
}
```

#### PUNTO CLAVE (`201 Created`)
* JSON de entrada con lugar y fecha.
* Respuesta con UUID y URL de seguimiento.
* Fecha devuelta con UTC-3.
* **Retiro registrado correctamente**

*API FEDEX / SERVICIO DE RETIROS — 07*

---

## 07 / POSTMAN SEGUIMIENTO
### GET /retiros/{uuid}: consultar estado
Un único identificador permite consultar el retiro, sin listar datos de otros clientes.

* **Método y URL:** `GET https://blcecvxqrkvotawkunxk.supabase.co/functions/v1/fedex/retiros/f274b15b-c227-4211-a554-4f367bb4e1ae`
* **Estado:** `200 OK`

#### Body (Response JSON)
```json
{
  "id": "f274b15b-c227-4211-a554-4f367bb4e1ae",
  "estado": "RETIRADO",
  "fecha_programada": "2026-10-27T20:13:00-03:00"
}
```

#### PUNTO CLAVE (`200 OK`)
* La URL incorpora el UUID generado.
* La respuesta expone `id`, `estado` y `fecha`.
* `RETIRADO` significa que se alcanzó la fecha.
* En la captura: `RETIRADO` por fecha.
* **Seguimiento público por UUID**

*API FEDEX / SERVICIO DE RETIROS — 08*

---

## 08 / POSTMAN HISTORIAL
### GET /retiros: listado paginado
Cada cliente autenticado obtiene solamente sus propios retiros.

* **Método y URL:** `GET https://blcecvxqrkvotawkunxk.supabase.co/functions/v1/fedex/retiros`
* **Estado:** `200 OK`

#### Body (Response JSON)
```json
{
  "pagina": 1,
  "limite": 10,
  "total": 11,
  "total_paginas": 2,
  "retiros": [
    {
      "id": "f274b15b-c227-4211-a554-4f367bb4e1ae",
      "lugar": "La Plata, Buenos Aires",
      "fecha_programada": "2026-10-27T20:13:00-03:00",
      "estado": "RETIRADO",
      "url_seguimiento": "https://blcecvxqrkvotawkunxk.supabase.co/functions/v1/fedex/retiros/f274b15b-c227-4211-a554-4f367bb4e1ae"
    },
    {
      "id": "f251a140-a76e-425d-906f-6835422240dc",
      "lugar": "La Plata, Buenos Aires",
      "fecha_programada": "2026-10-27T19:57:00-03:00",
      "estado": "RETIRADO",
      "url_seguimiento": "https://blcecvxqrkvotawkunxk.supabase.co/functions/v1/fedex/retiros/f251a140-a76e-425d-906f-6835422240dc"
    }
  ]
}
```

#### PUNTO CLAVE (`200 OK`)
* La respuesta incluye `pagina` y `limite`.
* `total`: 11 retiros.
* `total_paginas`: 2 con límite 10.
* **Filtro por cliente autenticado**

*API FEDEX / SERVICIO DE RETIROS — 09*

---

## 09 / POSTMAN VALIDACIÓN
### 400 Bad Request: fecha pasada
La API rechaza datos inválidos antes de intentar registrar un retiro.

* **Método y URL:** `POST https://blcecvxqrkvotawkunxk.supabase.co/functions/v1/fedex/retiros`
* **Estado:** `400 Bad Request`

#### Body (Request JSON)
```json
{
  "lugar": "La Plata, Buenos Aires",
  "fecha_programada": "2026-09-27T20:13:00"
}
```

#### Body (Response JSON)
```json
{
  "error": "La fecha programada debe ser posterior a la fecha y hora actual"
}
```

#### PUNTO CLAVE (`400`)
* La fecha enviada ya había pasado.
* La API valida el horario y su formato.
* El error explica qué corregir.
* **No se crea ningún retiro**

*API FEDEX / SERVICIO DE RETIROS — 10*

---

## 10 / POSTMAN SEGURIDAD
### 401 Unauthorized: credenciales inválidas
La API exige Basic Auth para crear retiros y listar los del cliente autenticado.

* **Método y URL:** `GET https://blcecvxqrkvotawkunxk.supabase.co/functions/v1/fedex/retiros`
* **Authorization:**
  * **Auth Type:** Basic Auth
  * **Username:** `grupo01`
  * **Password:** `••••••••••••••••••••••••••••••••••••••`
* **Estado:** `401 Unauthorized`

#### Body (Response JSON)
```json
{
  "error": "Credenciales inválidas o faltantes"
}
```

#### PUNTO CLAVE (`401`)
* El servidor verifica usuario y contraseña.
* La contraseña se contrasta con un hash bcrypt.
* Sin credenciales válidas, no hay acceso.
* **Usar siempre HTTPS**

*API FEDEX / SERVICIO DE RETIROS — 11*

---

## 11 / ERRORES HTTP
### Respuestas de error implementadas
Los errores se devuelven como JSON: `{ "error": "Descripción del problema" }`.

| HTTP | SIGNIFICADO | CUÁNDO OCURRE |
| :--- | :--- | :--- |
| **400** | Bad Request | Datos inválidos: JSON, lugar, fecha, UUID o paginación. |
| **401** | Unauthorized | Credenciales Basic Auth ausentes, incorrectas o usuario inactivo. |
| **404** | Not Found | Retiro inexistente o ruta no implementada. |
| **405** | Method Not Allowed | Método incorrecto. El servidor informa los permitidos. |
| **500** | Internal Server Error | Error interno, acceso a BD o fallo inesperado. |

*API FEDEX / SERVICIO DE RETIROS — 12*

---

## 12 / DETALLE DE ERRORES
### Qué valida cada endpoint
Casos concretos que podemos reproducir en Postman.

#### POST /RETIROS 400 — Validaciones de entrada
* JSON válido y objeto con campos requeridos.
* `lugar`: texto obligatorio, no vacío y hasta 500 caracteres.
* `fecha_programada`: texto `YYYY-MM-DDTHH:mm:ss`.
* No se acepta sufijo de zona horaria (`Z`, `-03:00`, etc.).
* Debe ser una fecha real y posterior al momento actual.

#### GET VALIDACIONES — Consultas y rutas
* `GET /retiros`: `pagina` entre 1 y 100000.
* `GET /retiros`: `limite` entre 1 y 50.
* `GET /retiros/{uuid}`: UUID con formato válido.
* **404:** UUID correcto pero no registrado.
* **405:** método HTTP no permitido.

> **500:** consultar o guardar en PostgreSQL falla, o se produce un error inesperado.

*API FEDEX / SERVICIO DE RETIROS — 13*

---

## 13 / LÓGICA DE NEGOCIO
### Dos estados, sin tareas programadas
El estado se calcula en el momento de cada consulta.

* **ANTES DE LA FECHA:** `PROGRAMADO`
* **AL LLEGAR A LA FECHA:** `RETIRADO`

```javascript
Date.now() >= new Date(fechaProgramada).getTime()
  ? "RETIRADO" : "PROGRAMADO"
```

> No hay confirmación manual, cron jobs ni cambio persistido de estado.

*API FEDEX / SERVICIO DE RETIROS — 14*

---

## 14 / EJEMPLO DE INTEGRACIÓN
### Integración desde Node.js
El backend del cliente solicita retiros mediante HTTP y Basic Auth.

#### EJEMPLO NODE.JS 18+ FETCH
```javascript
const base = process.env.FEDEX_URL;
const user = process.env.FEDEX_USER;
const pass = process.env.FEDEX_PASS;
const auth = Buffer.from(`${user}:${pass}`).toString("base64");

const r = await fetch(`${base}/retiros`, {
  method: "POST",
  headers: { "Content-Type": "application/json",
             Authorization: `Basic ${auth}` },
  body: JSON.stringify({
    lugar: "La Plata, Buenos Aires",
    fecha_programada: "2026-12-15T15:00:00"
  })
});

const data = await r.json();
if (!r.ok) throw Error(data.error ?? `HTTP ${r.status}`);
console.log(data.retiro.id);
```

#### VARIABLES DE ENTORNO
* `FEDEX_URL`
* `FEDEX_USER`
* `FEDEX_PASS`

> **Respuesta 201:** UUID del retiro y URL de seguimiento.

*API FEDEX / SERVICIO DE RETIROS — 15*

---

## 15 / EJEMPLO DE INTEGRACIÓN
### Integración desde Python
También se puede consultar el historial del cliente con `requests`.

#### EJEMPLO PYTHON REQUESTS
```python
import os
import requests

base = os.environ["FEDEX_URL"]
auth = (os.environ["FEDEX_USER"],
        os.environ["FEDEX_PASS"])

r = requests.get(
    f"{base}/retiros",
    auth=auth,
    params={"pagina": 1, "limite": 10},
    timeout=15,
)
r.raise_for_status()

for retiro in r.json()["retiros"]:
    print(retiro["id"], retiro["estado"])
```

#### PREPARACIÓN
```bash
pip install requests
```

#### GET /retiros
* **Basic Auth:** solo recupera los retiros del cliente autenticado.
* Para seguimiento por UUID no se necesita Basic Auth.

*API FEDEX / SERVICIO DE RETIROS — 16*

---

## 16 / GUÍA RÁPIDA
### Cómo empezar a usar la API
Datos mínimos para consumir FedEx desde Postman o desde el backend de cada grupo.

* **URL BASE:** `https://blcecvxqrkvotawkunxk.supabase.co/functions/v1/fedex`

#### 01. AUTENTICACIÓN
* **Basic Auth:** Usuario y contraseña asignados a tu grupo.

#### POST /retiros BODY JSON
```json
{
  "lugar": "La Plata, Buenos Aires",
  "fecha_programada": "2026-12-15T15:00:00"
}
```

#### 02. ENDPOINTS
* `POST /retiros` — Crear un retiro · Basic Auth
* `GET /retiros` — Listar retiros propios · Basic Auth
* `GET /retiros/{uuid}` — Consultar estado público por UUID

* **Listado:** `pagina=1` y `limite=10` por defecto (máx. 50).
* **Fecha futura:** horario argentino sin sufijo de zona.

> Si el POST devuelve 201, guardá el UUID recibido para consultar el seguimiento.

*API FEDEX / SERVICIO DE RETIROS — 17*

---

## 17 / PREGUNTAS
### ¿Dudas?
Consultas sobre los endpoints, la autenticación o el seguimiento de retiros.

*API FEDEX / SERVICIO DE RETIROS — 18*

---

## 18 / CIERRE
### Muchas gracias
**API FedEx — Retiros programados y seguimiento**  
**GRUPO 3**

*API FEDEX / SERVICIO DE RETIROS — 19*

---

## 19 / ACCESOS DE GRUPOS
### Credenciales para los grupos
Usuarios habilitados para consumir la API · Grupo 00 reservado para pruebas.

| NOMBRE DEL GRUPO | USUARIO | CONTRASEÑA |
| :--- | :--- | :--- |
| **Grupo 00** | `grupo00` | `7c5e7111e7d4ec5ea8451aba099105bcc200` |
| **Grupo 01** | `grupo01` | `ca0beef3f61d89528a1671d9400403fae71e` |
| **Grupo 02** | `grupo02` | `3dd3365b084bda8349f1bcc928be8550ccf3` |
| **Grupo 03** | `grupo03` | `2e401d3ac2cd9e1e513c206721b12db0cbce` |
| **Grupo 04** | `grupo04` | `861822f06cb11206b38a55962f27f8ac507d` |
| **Grupo 05** | `grupo05` | `e5fbfa1489868380e283ea822389d26e0951` |
| **Grupo 06** | `grupo06` | `f9afe8e887e3ef84477345c7eaf47518c4d2` |
| **Grupo 07** | `grupo07` | `03b51e2338622d98449e4bdca4d27d478bf6` |
| **Grupo 08** | `grupo08` | `557b731e86e978e953e5e0981e1c234282bf` |
| **Grupo 09** | `grupo09` | `d8587486051da3302d394af4b0d3b9b0360a` |
| **Grupo 10** | `grupo10` | `3ee93c5477c960e27ec38ca1f2aee47321fa` |

*API FEDEX / SERVICIO DE RETIROS — 20*