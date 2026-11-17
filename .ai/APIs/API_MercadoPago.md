# API de MercadoPago (Referencia de Integración)

**Sistema de Seguimiento de Estudios de Exoma Clínico (TTPS-E)**

Contrato de integración desde el backend Flask (`app/src/clients/mercadopago_client.py`) hacia la API REST oficial de **MercadoPago** (Checkout Pro / Payments API) para el cobro de presupuestos particulares en un pago o en cuotas, y la recepción asíncrona de confirmaciones vía webhook.

---

## 1. Configuración y Autenticación

| Variable de entorno | Uso |
|---|---|
| `MERCADOPAGO_ACCESS_TOKEN` | Token Bearer del vendedor (`Authorization: Bearer <ACCESS_TOKEN>`). Nunca se expone al frontend. |
| `MERCADOPAGO_WEBHOOK_SECRET` | Secreto para validar la firma HMAC-SHA256 del encabezado `x-signature` en notificaciones entrantes. |
| `MERCADOPAGO_BASE_URL` | Por defecto `https://api.mercadopago.com` (permite apuntar a sandbox/mock en tests). |
| `MERCADOPAGO_NOTIFICATION_URL` | URL pública del backend para webhooks: `<BASE_URL>/api/v1/webhooks/mercadopago`. |

---

## 2. Endpoints Consumidos por el Backend

### 2.1. Crear Preferencia de Pago (`POST /checkout/preferences`)

Se invoca cuando el **paciente** inicia el pago del **presupuesto** (en un solo pago o primera cuota) o cuando abona una **cuota** subsiguiente pendiente/vencida.

**Payload de ejemplo:**
```json
{
  "items": [
    {
      "id": "estudio-101-cuota-1",
      "title": "Estudio de Exoma Clínico #101 - Cuota 1/3",
      "quantity": 1,
      "currency_id": "ARS",
      "unit_price": 186.67
    }
  ],
  "external_reference": "estudio:101:pago:45:cuota:1",
  "payment_methods": {
    "installments": 1
  },
  "back_urls": {
    "success": "https://app.lab.local/estudios/101/pago/exito",
    "failure": "https://app.lab.local/estudios/101/pago/error",
    "pending": "https://app.lab.local/estudios/101/pago/pendiente"
  },
  "auto_return": "approved",
  "notification_url": "https://api.lab.local/api/v1/webhooks/mercadopago"
}
```

**Respuesta esperada (`201 Created`):**
```json
{
  "id": "123456789-abcdef-1234",
  "init_point": "https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=123456789-abcdef-1234",
  "sandbox_init_point": "https://sandbox.mercadopago.com.ar/checkout/v1/redirect?pref_id=123456789-abcdef-1234",
  "external_reference": "estudio:101:pago:45:cuota:1"
}
```

### 2.2. Consultar Detalle de Pago (`GET /v1/payments/{payment_id}`)

Al recibir un webhook `type: "payment"`, el backend consulta siempre la API de MercadoPago para verificar el estado real (nunca confía únicamente en parámetros de redirección del navegador).

**Respuesta esperada (`200 OK`):**
```json
{
  "id": 9876543210,
  "status": "approved",
  "status_detail": "accredited",
  "external_reference": "estudio:101:pago:45:cuota:1",
  "transaction_amount": 186.67,
  "installments": 1,
  "transaction_details": {
    "installment_amount": 186.67,
    "total_paid_amount": 186.67
  },
  "date_approved": "2026-11-17T15:30:00.000-03:00"
}
```

---

## 3. Webhook Entrante en el Backend (`POST /api/v1/webhooks/mercadopago`)

**Payload enviado por MercadoPago:**
```json
{
  "action": "payment.created",
  "api_version": "v1",
  "data": { "id": "9876543210" },
  "date_created": "2026-11-17T15:30:01Z",
  "id": 123456,
  "live_mode": false,
  "type": "payment"
}
```

**Reglas de seguridad e idempotencia:**
1. Validar la firma `x-signature` con `MERCADOPAGO_WEBHOOK_SECRET` (o rechazar con `401 Unauthorized`).
2. Consultar `GET /v1/payments/{data.id}` en MercadoPago antes de mutar cualquier estado local.
3. Procesar de forma idempotente bajo bloqueo `SELECT ... FOR UPDATE` sobre `cuotas` y `pagos`: si la cuota ya figura `pagada` con el mismo `mp_payment_id`, responder `200 OK` sin duplicar efectos.
4. Si `status == "approved"`, marcar la cuota como `pagada`, actualizar el estado de `Pago` (`parcial` si restan cuotas pendientes, `pagado` si se completó el total), habilitar `Sacar turno` cuando corresponda (cuota 1 / pago único) y vencer el `Cupón` en la `API de cupones` si se aplicó uno.
