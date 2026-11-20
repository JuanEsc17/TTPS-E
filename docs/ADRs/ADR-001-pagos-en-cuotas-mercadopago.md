# ADR-001: Pagos en Cuotas con MercadoPago y Visibilidad Administrativa

## Status
Accepted (2026-11-17)

## Context
El requerimiento original contemplaba pagos particulares simulados y exclusivamente en un único pago. Los nuevos requerimientos exigen:
1. Dar soporte al pago por **cuotas**, implementado con **MercadoPago**.
2. Que el **administrativo** pueda **ver las cuotas de los pacientes** (estado, vencimientos, deuda pendiente e identificador de operación).

En la integración con MercadoPago existen dos formas principales de modelar cuotas:
- **Opción A (Financiación exclusivamente interna de tarjeta en un único cobro MP):** El backend crea una única preferencia por el total (`installments = N`) y el paciente elige cuotas dentro de la tarjeta en MercadoPago; MercadoPago liquida el plan al comercio en una sola transacción y no existen vencimientos mensuales posteriores en el sistema del laboratorio.
- **Opción B (Plan de cuotas gestionado con cobro por cuota vía MercadoPago + registro de referencia MP):** El paciente elige `cantidad_cuotas` (`1..N`, aplicando un `Cupón` previo al prorrateo). Se persiste `Pago` y sus `N` filas en `cuotas` (`numero_cuota = 1..N`, `monto_usd`, `fecha_vencimiento` mensual, `estado`: `pendiente | pagada | vencida | rechazada | anulada`). La primera cuota (o pago único si `N = 1`) se abona mediante MercadoPago Checkout Pro y al confirmarse por webhook habilita `Sacar turno`; las cuotas restantes permanecen trazables con su vencimiento para ser abonadas vía MercadoPago y monitoreadas por el **administrativo**.

## Decision
Se adopta la **Opción B** (`Pago` + tabla `cuotas` con preferencias y webhooks de MercadoPago), manteniendo compatibilidad con `N = 1` (pago único) y registrando `mp_preference_id` y `mp_payment_id` tanto en `Pago` como en cada `Cuota`.

### Criterios clave de diseño
1. **Aplicación de Cupón antes del prorrateo:** El descuento de `Cupón` vigente se calcula sobre el total del `Presupuesto` antes de dividir el saldo neto en `cantidad_cuotas`, y el cupón solo se marca `usado = True` y se consume en la `API de cupones` cuando MercadoPago confirma el webhook `approved` de la cuota inicial (evitando quemar cupones ante checkouts abandonados).
2. **Habilitación para sacar turno:** El `Estudio` en `EstadoEstudio.CREADO` queda habilitado para `Sacar turno` en cuanto el pago único o la **cuota 1** alcanza estado `pagada` (`Pago.estado` en `pagado` o `parcial` con `anulado == False`).
3. **Cinco ausencias (`MAX_AUSENCIAS = 5`):** Al acumular 5 ausencias, `Pago.anulado = True`, todas las cuotas no pagadas (`pendiente`, `vencida`, `rechazada`) pasan a `anulada`, y el estudio vuelve a `EstadoEstudio.CREADO`.
4. **Visibilidad administrativa:** El `Administrativo` dispone de vistas y endpoints filtrables sobre `cuotas` + `pagos` + `pacientes` + `estudios` para auditar recaudación y morosidad (`vencida`).

## Consequences
- **Positivas:** Permite al administrativo monitorear cuotas pagadas, pendientes y vencidas por paciente/estudio (alineado con el objetivo original de control de caja y deudas); soporta idempotencia estricta ante reintentos de webhooks de MercadoPago mediante `mp_payment_id` y bloqueo `FOR UPDATE`.
- **Negativas / Trade-offs:** Requiere un job periódico diario que marque `pendiente -> vencida` cuando `fecha_vencimiento < hoy` y notifique al paciente; añade la tabla `cuotas` y el cliente `MercadoPagoClient` en `app/src/clients/`.
- **Reversibilidad:** Alta; el diseño desacopla la lógica de negocio (`economia_service`) del proveedor de pagos mediante `MercadoPagoClient` (Ports & Adapters).
