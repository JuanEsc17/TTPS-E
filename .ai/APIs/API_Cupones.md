# API de cupones

**EXOMA CARE / TTPS**

Guía de integración para los grupos

*Versión 2 · HTTP + JSON · Clave por grupo*

---

## Cómo se procesa una solicitud

1. **Backend del grupo:** autoriza a su usuario y envía `X-API-Key` con la petición HTTP.
2. **Edge Function de cupones:** valida el hash de la clave, obtiene el grupo y ejecuta la operación.
3. **PostgreSQL vía RPC:** guarda los cupones y aplica las reglas. Devuelve el resultado como JSON.

---

## Conexión y autenticación

**URL base**

```
https://vekuhonbpqtzakqbcoph.supabase.co/functions/v1/cupones-api
```

**Headers del consumidor**

```
X-API-Key: <CLAVE_DE_TU_GRUPO>
Content-Type: application/json   (para POST)
```

> La clave identifica al grupo. No enviar `p_grupo_id` ni `Authorization: Bearer`.

---

## El recorrido del cupón

1. **Generar** → estado `disponible`
2. **Asignar al médico** → estado `medico`
3. **Asignar al paciente** → estado `paciente`
4. **Canjear** → estado `usado`

La misma fila conserva su código. Asignar al paciente todavía no consume el cupón.

---

## Consultar cupones y estados

### `GET /cupones`

Devuelve una página de cupones del grupo identificado por la clave.

**Consulta**

```
?limit=20&offset=0
```

Sin cuerpo JSON.

```
X-API-Key: <CLAVE_DE_TU_GRUPO>
```

**Respuesta · `200 OK`**

```json
{
  "items": [...],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

*Ejemplo de estructura.*

---

## Filtros y paginación

**Ejemplos de consulta**

```
/cupones?estado=disponible&limit=20&offset=0
/cupones?medico_id=M-5678&limit=20&offset=20
```

**Cómo leer el resultado**

- `items`: filas de la página.
- `total`: coincidencias del filtro.
- `limit`: hasta 100 filas.
- `offset`: filas a omitir.

Filtros: `estado`, `medico_id` y `gerente_id`. Se pueden combinar.

Sin `estado` se listan todos. *Disponible* no garantiza vigencia: revisar la fecha.

---

## 1. Generar un lote

### `POST /generar_cupones_gerencia`

Un gerente por grupo. Descuento positivo y vencimiento automático a 30 días.

**Cuerpo JSON**

```json
{
  "p_gerente_id": "G-1234",
  "p_cantidad": 2,
  "p_porcentaje_descuento": 20
}
```

**Respuesta · `200 OK`**

```json
[
  {"codigo_cupon": "53399388",
   "porcentaje": 20},
  {"codigo_cupon": "2ded2dc3",
   "porcentaje": 20}
]
```

---

## 2. Asignar un cupón al médico

### `POST /asignar_cupon_a_medico`

Se envía un código específico. Debe pertenecer al gerente y estar disponible.

**Cuerpo JSON**

```json
{
  "p_gerente_id": "G-1234",
  "p_medico_id": "M-5678",
  "p_codigo": "53399388"
}
```

**Respuesta · `200 OK`**

```json
true
```

Nuevo estado: `medico`.

> La API guarda el ID; no verifica al médico en otra aplicación.

---

## 3. Asignar un cupón al paciente

### `POST /asignar_cupon_a_paciente`

El código debe estar vigente y asociado al médico dentro del mismo grupo.

**Cuerpo JSON**

```json
{
  "p_medico_id": "M-5678",
  "p_paciente_id": "P-123",
  "p_codigo": "53399388"
}
```

**Respuesta · `200 OK`**

```json
true
```

Nuevo estado: `paciente`.

> Si el paciente ya tiene un cupón en el grupo, incluso usado: `409`.

---

## 4. Canjear el cupón

### `POST /canjear_cupon`

Comprueba grupo, paciente, estado y vencimiento. Registra `fecha_uso`.

**Cuerpo JSON**

```json
{
  "p_paciente_id": "P-123",
  "p_codigo": "53399388"
}
```

**Respuesta · `200 OK`**

```json
true
```

Nuevo estado: `usado`.

> Un segundo canje: `409 Conflict`. No realiza un cobro.

---

## Errores de negocio

| Código | Cuándo |
|--------|--------|
| 400 | Datos inválidos, cupón vencido o estado no habilitado. |
| 403 | El grupo ya tiene otro gerente al generar el lote. |
| 404 | Código inexistente o que no corresponde al grupo o actor. |
| 409 | Cupón ya usado o paciente con un cupón previo en el grupo. |

Leé `code` y `message` del JSON. Un 404 al asignar no significa que el médico no exista.

---

## Errores de acceso y formato

| Código | Cuándo |
|--------|--------|
| 401 | Clave ausente, inválida o revocada. |
| 405 | Método HTTP incorrecto para la ruta. |
| 413 / 415 | Cuerpo mayor a 16 KiB o `Content-Type` distinto de JSON. |
| 503 | Error interno o dependencia temporalmente no disponible. |

> No repetir escrituras automáticamente ante timeout: consultar el estado primero.

---

## Probar con Swagger o Postman

1. **Abrir Swagger público:** <https://juanmasisti.github.io/exoma-care-cupones-docs/>. En *Authorize*, pegar la clave `ecg_…` del grupo, sin `Bearer`.
2. **Ejecutar:** elegir endpoint → *Try it out* → completar campos → *Execute*.
3. **Seguir el resultado:** consultar `GET` después de cada operación. En Postman: *No Auth* y header `X-API-Key`.

---

## Integración de cada grupo

1. **Recibir la clave:** guardar `ecg_…` en la configuración privada del backend.
2. **Cambiar conexión:** usar la URL nueva y el header `X-API-Key`.
3. **Actualizar cuerpos:** quitar `p_grupo_id`. Asignar siempre por código.
4. **Validar el flujo:** generar, asignar, canjear y comprobar con `GET`.

Usá tus IDs reales y un paciente nuevo de prueba. El backend consumidor autoriza al usuario.

---

## API keys por grupo

Usá la clave de tu grupo en `X-API-Key` o en *Authorize* de Swagger, sin `Bearer`.

| Grupo | API key |
|-------|---------|
| Grupo 1 | `ecg_7d5b194573034dadc366936e6c0df7fa19b30f45e17f379dfab221450088f98a` |
| Grupo 2 | `ecg_cc21f4226a78b45bc81868751c41fa62b039a0029b358ab19bb46f909c40bb9b` |
| Grupo 3 | `ecg_a1b49c8994a07782aa1f9f7b57d52e709dcb362c2f9063091850a43e4f3730ee` |
| Grupo 4 | `ecg_20f52b13fae04bd8682667e76452f02b2e8fbd28eb08931f972cf20e5b936a15` |
| Grupo 5 | `ecg_be0e0260fbace8cf6c0e991681cce4c42e433e8d7c45ac0e7691bb7e8d484e83` |
| Grupo 6 | `ecg_7221c474d1ac20a06a95a18f476d904926fd8a1be5f57b4fab8f9554141b322f` |
| Grupo 7 | `ecg_9e6919ff0a58207a39a2baed283e55281198e972a1e21c13e6f624233a6aa97d` |
| Grupo 8 | `ecg_507af17dc376146070d89f1fe50805387d2edc885595a84c8bdeafdd9082e50b` |
| Grupo 9 | `ecg_05ced9b158d59f444c848da7bb2f903900bfa35895a8d7995d5e4e5dc0e81d1e` |
| Grupo 10 | `ecg_7d029ddfb80bcc4bf7ae301f44e4095d3c14a1c7896d60b16a57622b78499ec1` |
