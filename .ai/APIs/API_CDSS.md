# Módulo 4: CDSS

**Sistema de soporte a la decisión clínica · genExoma**

------------------------------------------------------------------------

## Página 1 --- Portada

# Módulo 4: CDSS

Sistema de soporte a la decisión clínica · genExoma

------------------------------------------------------------------------

## Página 2 --- Objetivo del módulo

Dada la lista de síntomas de un paciente, sugiere qué patología
lisosomal puede tener.

-   Es una sugerencia, no un diagnóstico confirmado.
-   Los síntomas entran como códigos SNOMED (ej.: `247398009` = Dolor
    neuropático).
-   Si ningún síntoma es cardinal, responde **"no compatible con
    patologías lisosomales"**.
-   Catálogo fijo: **Fabry, Pompe, Gaucher, ASMD y MPS I**.

------------------------------------------------------------------------

## Página 3 --- Acceso: dirección y clave

-   La dirección base es:

    `https://genexoma.onrender.com`

    Guárdenla en su código y súmenle el endpoint:

    `https://genexoma.onrender.com/api/v1/diagnostico`

-   Cada grupo tiene su clave y la manda en el header de cada pedido.
    Sin clave → **401**.

-   `GET /health` no pide clave: dice si el servicio y la base
    funcionan.

**Dato de entrada (header):**

``` http
X-API-Key: <clave del grupo>
```

**Datos de salida de `GET /health`:**

``` json
{ "status": "ok", "db": "ok" }
```

------------------------------------------------------------------------

## Página 4 --- Endpoints

  Método   Endpoint
  -------- ------------------------------------
  `GET`    `/health`
  `GET`    `/api/v1/patologias`
  `GET`    `/api/v1/estrategias`
  `POST`   `/api/v1/diagnostico`
  `GET`    `/api/v1/configuracion`
  `PUT`    `/api/v1/configuracion/estrategia`

------------------------------------------------------------------------

## Página 5 --- Ver el catálogo de patologías

`GET /api/v1/patologias`

**Datos de entrada**

Solo tu clave, en el header.

``` http
X-API-Key: <clave>
```

**Datos de salida**

Las 5 patologías, cada una con sus síntomas y cuáles son cardinales.

Ejemplo de estructura de respuesta:

``` json
{
  "codigo": "FABRY",
  "nombre": "Enfermedad de Fabry",
  "sintomas": [ ... ]
}
```

------------------------------------------------------------------------

## Página 6 --- Ver las estrategias

`GET /api/v1/estrategias`

**Datos de entrada**

Solo tu clave, en el header.

``` http
X-API-Key: <clave>
```

**Datos de salida**

-   `MAYOR_CANTIDAD_SINTOMAS`\
    Gana la de más síntomas en común.

-   `MAYOR_CANTIDAD_CARDINALES`\
    Gana la de más cardinales en común.

-   `MENOR_DIFERENCIA`\
    Gana a la que le faltan menos síntomas.

------------------------------------------------------------------------

## Página 7 --- Pedir una sugerencia

`POST /api/v1/diagnostico`

**Datos de entrada**

Tu clave y los síntomas del paciente (códigos SNOMED).

Ejemplo de body:

``` json
{
  "sintomas": [
    "247398009",
    "29738008"
  ]
}
```

**Datos de salida**

La patología sugerida (varias si empatan) y las 3 que más coinciden.

Ejemplo de estructura de respuesta:

``` json
{
  "compatible": true,
  "estrategia": "…",
  "patologias": [ ... ],
  "ranking": [ ... ],
  "mensaje": null
}
```

------------------------------------------------------------------------

## Página 8 --- Ver y cambiar la estrategia

### Ver

`GET /api/v1/configuracion`

-   **Entrada:** tu clave.
-   **Salida:** tu grupo y su estrategia.

Ejemplo:

``` json
{
  "cliente": "Grupo 3",
  "estrategia": "…"
}
```

### Cambiar

`PUT /api/v1/configuracion/estrategia`

-   **Entrada:** tu clave y la nueva estrategia.
-   **Salida:** tu grupo con la nueva.

Ejemplo de body:

``` json
{
  "estrategia": "MENOR_DIFERENCIA"
}
```

------------------------------------------------------------------------

## Página 9 --- Misma consulta, distinta estrategia

Paciente con dolor neuropático y esplenomegalia:

  Estrategia del grupo          El CDSS sugiere
  ----------------------------- ---------------------------
  `MAYOR_CANTIDAD_SINTOMAS`     Fabry y Gaucher (empatan)
  `MAYOR_CANTIDAD_CARDINALES`   Fabry y Gaucher (empatan)
  `MENOR_DIFERENCIA`            Gaucher

**El cambio de estrategia afecta solo a tu grupo.**

------------------------------------------------------------------------

## Página 10 --- Códigos de respuesta

Si hay error:

-   `detail`: mensaje para mostrar.
-   `código`: no cambia aunque cambie el texto.

  -----------------------------------------------------------------------------
                   Código HTTP `código`                   Cuándo
  ---------------------------- -------------------------- ---------------------
                         `401` `API_KEY_INVALIDA`         Sin clave o clave
                                                          inválida

                         `404` `RUTA_INEXISTENTE`         La URL no existe

                         `405` `METODO_NO_PERMITIDO`      Método equivocado

                         `422` `DATOS_INVALIDOS`          Datos mal enviados
                                                          (dice qué campo y por
                                                          qué)

                         `500` `ERROR_INTERNO`            Error inesperado del
                                                          servidor

                         `503` `SERVICIO_NO_DISPONIBLE`   `/health` sin
                                                          conexión a la base
  -----------------------------------------------------------------------------

------------------------------------------------------------------------

## Página 11 --- Claves de cada grupo

Las claves se envían en el header `X-API-Key`.

  Grupo         API key
  ------------- ---------------------------------------------------
  Grupo 1       `Pj_wcj-77uN5IeDvFbMNjvsyxNVT6y1smZKrFJdizQI`
  Grupo 3       `mCHCqJhA0bezo9DZWyS0T7VRSC25dwMKPS-obKD-i4c`
  Grupo 4       `gYRDxslCoTwNL6tsnozKebtEaS7tFJyelsX6HzfIOtg`
  Grupo 5       `_Zyko_Uajl4-PWFLplUfYvApTjR0OUG0lbu413zOAYA`
  Grupo 6       `KC9iJ-deOj0hjeBd1zxTU_4Ozm1SaZIbgxlmiJy4QDg`
  Grupo 7       `dBbhwUQ66CLq6YqIbxNkKE6NcKBHcBmhrxIXqS9OtJ0`
  Grupo 8       `1TtNXo-eI4TSPbbf0wZzAPlyysHw9zSwsdToEw847cM`
  **Grupo 9**   **`JfjvtBNseFEIHV-FjdXU5HZ0cvQ0LrXknW3e_l0sI9A`**
  Grupo 10      `USVoyBjpVWNJjw1-eTyPb0ZVfUybL4MfzT3r6Zb0M6A`

> En la diapositiva no aparece una clave para el Grupo 2.

------------------------------------------------------------------------

## Nota sobre la transcripción

Se transcribió el contenido textual de las 11 diapositivas y se
organizaron los endpoints, ejemplos JSON, estrategias y códigos de
respuesta en Markdown. Los fragmentos indicados con `…` o `[ ... ]`
representan contenido que la diapositiva deja como abreviatura o ejemplo
incompleto; no se completaron con datos inventados.
