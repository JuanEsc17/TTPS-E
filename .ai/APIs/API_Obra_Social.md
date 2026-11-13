# API de Obras Sociales

**Grupo 9:** Castro Carlo, Conde Nicolás, Gatica Catalina, Rivas Luca

------------------------------------------------------------------------

## Página 1 --- Portada

# API de Obras Sociales

**Grupo 9:** Castro Carlo, Conde Nicolás, Gatica Catalina, Rivas Luca

------------------------------------------------------------------------

## Página 2 --- URL base y OpenAPI

-   **URL base:**\
    `https://bxsvmfesrtjrqubblgws.supabase.co/functions/v1/api`

-   **URL de OpenAPI con documentación de la API:**\
    `https://bxsvmfesrtjrqubblgws.supabase.co/functions/v1/api/openapi.json`

> Insertar la URL en la sección **File** de la página
> [editor.swagger.io](https://editor.swagger.io).

La diapositiva incluye capturas de Postman y de la documentación
OpenAPI/Swagger.

------------------------------------------------------------------------

## Página 3 --- El acceso: la API Key

La API key provista para cada grupo es necesaria para el acceso a la
API, y debe enviarse como dato en el **header**. En caso contrario se
obtiene el error **401**.

La captura muestra una request sin la API key y la respuesta
`401 Unauthorized`. También se ve el mensaje de error de autenticación.

------------------------------------------------------------------------

## Página 4 --- API Keys

  Grupo          API Key
  -------------- --------------------------------------------
  Grupo 01       `osk_Pn6LPMR56wp-iipOcdhoEieLlrCsV_UI`
  Grupo 02       `osk_50Dnj_1G2rYwSKFGIGkzwc4GwgsA9EWZ`
  Grupo 03       `osk_fNCuEURLz3lrk3c4cTziCGhaMEZMRWZZ`
  Grupo 04       `osk_ti_HqZaLcAlG6keepRaBtkvTDtbkd2Nf`
  Grupo 05       `osk_fPERIKHBT-rUAkMmfXWz2hzCvjDUxVdc`
  Grupo 06       `osk_aikS4fsci0UXkB7RUAgR-mhvEJU1zAA8`
  Grupo 07       `osk_gDw5u5Tm60AmMIyoz_Z1L6dxiHy4PpAi`
  Grupo 08       `osk_gXOy_3o4d4KzcPI5Cmffwi7kqmnZkFDh`
  **Grupo 09**   **`osk_01Co96COen2D1LIqjiwvJ18BG-WocwSp`**
  Grupo 10       `osk_JvmH1tJIBzY_4oeiS55yVcDt-1_qAVeQ`

------------------------------------------------------------------------

## Página 5 --- Listado de obras sociales

Pueden solicitar un listado de obras sociales indicando en la URL la
cantidad de resultados que quieran mostrar en la página. Esta cantidad
se ingresa como parámetro en la URL.

Por ejemplo, solicitar 3 obras sociales por página:

``` http
<base_url>/obras-sociales?por_pagina=3
```

La captura muestra una request `GET` y una respuesta `200 OK`.

------------------------------------------------------------------------

## Página 6 --- Error en el listado de obras sociales

Si se envía un parámetro inválido, se obtiene el error **400**.

Por ejemplo:

``` http
por_pag=abc
```

La captura muestra una request `GET` con el parámetro `por_pagina` y
valor `abc`, que devuelve `400 Bad Request`. En el cuerpo de la
respuesta se presenta un objeto de error con los campos `error`,
`codigo`, `mensaje` y `detalle`; dentro de `detalle` aparece información
sobre `campos`, `campo` y `problema`.

------------------------------------------------------------------------

## Página 7 --- Búsqueda de una obra social

Pueden solicitar información de una obra social específica buscándola
por su nombre, sigla o código RNOS\*. El dato buscado se envía como
parámetro en la URL.

Por ejemplo, "osde":

``` http
<base_url>/obras-sociales?buscar=osde
```

La captura muestra una request `GET` con el parámetro `buscar=osde` y
una respuesta `200 OK`. En el ejemplo de respuesta se alcanza a leer
información de una obra social:

-   `id`: `e49f6b78-b4f7-4cbe-b82a-493e86f53daa`
-   `rnos_codigo`: `DEMO-001`
-   `nombre`: `OSDE`
-   `sigla`: `OSDE`
-   `porcentaje_cobertura`: aparece en el objeto de respuesta.

También se observan datos de paginación: `pagina: 1`, `por_pagina: 20`,
`total: 1` y `total_paginas: 1`.

\* El código RNOS es el código del Registro Nacional de Obras Sociales.

------------------------------------------------------------------------

## Página 8 --- Crear una solicitud de cobertura

Para realizar una solicitud de cobertura, se debe enviar un request con
los siguientes parámetros en el **body**:

-   id de obra social
-   nombre del paciente
-   fecha
-   id del estudio

La API va a devolver la información de la solicitud en estado
**"pendiente"** y las dos URL para simular la autorización o el rechazo
de la misma.

La captura muestra una request `POST` al recurso `/solicitudes`, con el
body en formato JSON, y una respuesta `201 Created`.

------------------------------------------------------------------------

## Página 9 --- Error en la creación de la solicitud

Si no se envían todos los parámetros, se obtiene el error **400** y en
el body del response se obtiene el informe del parámetro faltante. Va a
pasar lo mismo si se ingresa una fecha inválida\*.

Por ejemplo, si falta el nombre del paciente en el body.

La captura muestra una request `POST` a `/solicitudes` y una respuesta
`400 Bad Request`. El detalle identifica el campo faltante.

\* El formato de las fechas es **Año-Mes-Día**.

------------------------------------------------------------------------

## Página 10 --- Consultar el estado de una solicitud

Pueden consultar el estado de una solicitud ya creada indicando el id de
la solicitud como parámetro en la URL.

Por ejemplo, queremos consultar la solicitud creada previamente con id:

``` text
18f5c467-8a64-4acb-b621-3bec228c8d7f
```

La captura muestra una request `GET` al recurso `/solicitudes/{id}` y
una respuesta `200 OK`.

------------------------------------------------------------------------

## Página 11 --- Autorización de la solicitud

Cuando usen la URL para autorizar la solicitud, la API va a actualizar
el estado de la misma a **"autorizada"** y va a devolver de nuevo toda
su información.

La captura muestra una request `POST` a la URL de autorización y una
respuesta `200 OK` con la información actualizada.

------------------------------------------------------------------------

## Página 12 --- Rechazo de la solicitud

Para simular el rechazo de la solicitud, se debe enviar una request a la
URL obtenida en la creación de la solicitud, y agregar el **motivo**
como dato en el body.

Luego la API va a actualizar el estado de la solicitud a
**"rechazada"**, y va a registrar el motivo del rechazo.

La captura muestra una request `POST` a la URL de rechazo, con el motivo
en el body.

------------------------------------------------------------------------

## Página 13 --- Carga de una demanda

Cuando se vaya a enviar una demanda a la API, debe ser en formato
**PDF** y no debe superar los **5 MB**. Este PDF lo deben cargar en un
campo llamado **"archivo"** dentro del `formData` que va a ir en el body
de la request, como se puede ver en la imagen.

La captura muestra una request `POST` al recurso
`/solicitudes/{solicitud_id}/demanda`, con el body en formato
`form-data`:

  Campo       Tipo/valor mostrado
  ----------- -----------------------
  `archivo`   `ejemplo_demanda.pdf`

La respuesta mostrada es `201 Created`.

------------------------------------------------------------------------

## Página 14 --- Error al cargar otra demanda

Si la solicitud tiene una demanda cargada, pero esta no se resolvió (o
sea que no tiene fecha de resolución), no se va a poder cargar otra, y
la API va a devolver un error **409**.

La captura muestra la carga de un archivo PDF mediante `form-data` y una
respuesta `409 Conflict`.

------------------------------------------------------------------------

## Página 15 --- Autorización o rechazo de la demanda de una solicitud

Para simular que se autoriza la demanda y la solicitud que la tiene
registrada, se debe enviar una request a la URL que recibieron al cargar
la demanda. Esta request debe tener el **porcentaje de la cobertura**\*
como dato en el body.

Para simular que se rechaza la demanda y la solicitud, es el mismo
procedimiento enviando una request a la URL de rechazo, agregando el
**motivo** como dato en el body. Luego se puede cargar otra demanda para
intentar autorizar la solicitud de nuevo.

\* Todas las obras sociales tienen un porcentaje por defecto, pero ante
una demanda, este puede variar y por eso se envía como body.

La captura muestra requests `POST` a las URL de simulación de
autorización y rechazo.

------------------------------------------------------------------------

## Página 16 --- Error al autorizar la solicitud

Se puede generar un error al querer autorizar una demanda si no se
realiza la request a una URL válida, o si la solicitud ya está
autorizada.

Por ejemplo, si la solicitud ya está autorizada.

La captura muestra una request `POST` a la URL de autorización con un
body JSON que contiene el campo `porcentaje`, y una respuesta
`409 Conflict`. El mensaje de error indica que la solicitud ya está
autorizada y muestra el estado actual `autorizada`.

------------------------------------------------------------------------

## Página 17 --- Cierre

# ¡Gracias por su atención!

**Grupo 9:** Castro Carlo, Conde Nicolás, Gatica Catalina, Rivas Luca

------------------------------------------------------------------------

## Nota sobre la transcripción

Se transcribió el texto de las 17 diapositivas y se incorporaron los
datos legibles de las capturas (rutas, parámetros, estados HTTP y
ejemplos visibles). Algunas porciones del código JSON dentro de las
capturas tienen una resolución demasiado baja para garantizar una
transcripción literal completa; por eso no se reconstruyeron ni se
inventaron esos fragmentos.
