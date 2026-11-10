# Módulo de familiograma

**API para los grupos de Laboratorio**

Cómo llamar a los endpoints y usar la imagen devuelta

*Laboratorio · TTPS*

---

## Dos endpoints principales

| Método | Ruta respecto de BASE | Resultado |
|--------|-----------------------|-----------|
| GET | `/parentescos` | Catálogo para armar el selector |
| POST | BASE, sin sufijo | Imagen SVG codificada en base64 |

**BASE**

```
https://cnylfdemauswqeqmvwmz.supabase.co/functions/v1/familiograma
```

Además: `GET BASE + /salud` es público y devuelve `{"estado":"disponible"}`.

---

## Una clave por grupo

- 10 claves, una para cada grupo.
- Cada clave se asocia al nombre de un grupo.
- El validador comprueba la clave y reconoce ese cliente.

```
x-api-key: CLAVE_DEL_GRUPO
Content-Type: application/json
```

La clave se usa desde el servidor del grupo y se conserva como secreto.

La identidad se reconoce al validar; hoy no se guarda un historial de llamadas.

---

## `GET /parentescos`

No recibe cuerpo. Devuelve 16 elementos con `id` y `parentesco`.

| id | parentesco | id | parentesco |
|----|------------|----|------------|
| 0 | paciente | 8 | primo/a paterno/a |
| 1 | progenitor | 9 | hijo/a |
| 2 | hermano/a | 10 | medio hermano/a materno/a |
| 3 | abuelo/a materno/a | 11 | medio hermano/a paterno/a |
| 4 | abuelo/a paterno/a | 12 | pareja del paciente |
| 5 | tío/a materno/a | 13 | suegro/a |
| 6 | tío/a paterno/a | 14 | sobrino/a |
| 7 | primo/a materno/a | 15 | nieto/a |

El selector usa `id` como valor y `parentesco` como etiqueta.

El `0` corresponde al paciente; se excluye al agregar familiares.

---

## `POST /familiograma`: qué recibe

```json
{"personas": [
  {"parentesco": 0, "nombre": "Tomás",
   "apellido": "Ruiz", "sexo": "hombre",
   "edad": 9},
  {"parentesco": 1, "nombre": "Carolina",
   "apellido": "Ruiz", "sexo": "mujer",
   "edad": 36},
  {"parentesco": 1, "nombre": "Martín",
   "apellido": "Ruiz", "sexo": "hombre",
   "edad": 43, "fallecido": true}
]}
```

**Obligatorios por persona**

- `parentesco`
- `nombre`
- `apellido`

Debe haber exactamente un paciente: código `0`.

Los vínculos se deducen a partir de los códigos. Si faltan referencias o hay ambigüedad, devuelve `422`.

---

## Datos opcionales del POST

| Campo | Qué se envía / valor por defecto |
|-------|----------------------------------|
| `sexo` | `hombre`, `mujer` o `no_identificado` (por defecto) |
| `edad` | Años; admite fracciones. Omitida o `null`: desconocida |
| `fallecido` | `true` o `false`. Por defecto: `false` |
| `sintomas` | Lista de `{codigo, nombre}`. Por defecto: `[]` |
| `diagnosticos` | Lista de `{codigo, nombre}`. Por defecto: `[]` |
| `opciones.reglaSospecha` | `desactivada` o `un_cardinal_o_dos_secundarios` |

Ejemplo de diagnóstico confirmado de Carolina:

```json
"diagnosticos": [{"codigo":"SIM-FABRY", "nombre":"Fabry"}]
```

---

## Qué devuelve el POST

```json
{
  "advertencias": [],
  "imagen": {
    "tipo": "image/svg+xml",
    "base64": "PHN2Zy..."
  }
}
```

El SVG puede mostrarse, guardarse o convertirse al formato que necesite cada grupo.

```js
img.src = "data:" + datos.imagen.tipo +
          ";base64," + datos.imagen.base64;
```

**Imagen de ejemplo del PDF:** un familiograma titulado «Familiograma» (*Familia informada · Flecha: paciente · Diagonal: fallecimiento*). Muestra a Carolina Ruiz (progenitor, 36 años, Dx: Fabry) con símbolo circular sólido, a Martín Ruiz (progenitor, 43 años al fallecer) con un cuadrado tachado en diagonal, y a Tomás Ruiz (paciente, 9 años) con un cuadrado y una flecha. La leyenda indica: *Sólido: diagnóstico · Rayado: sospecha · Vacío: sin diagnóstico ni sospecha representados*, y aclara que *el rayado es una propuesta del equipo. No representa un diagnóstico confirmado.*

---

## Cómo llamarla desde el servidor

```js
const respuesta = await fetch(BASE, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "x-api-key": process.env.FAMILIOGRAMA_API_KEY
  },
  body: JSON.stringify({ personas })
});
const datos = await respuesta.json();
if (!respuesta.ok) throw new Error(datos.error.mensaje);
```

Para el catálogo: usar `BASE + "/parentescos"`, método `GET` y la misma clave.

El servidor del grupo entrega después la imagen a su frontend.

---

## Errores y alcance

| HTTP | Qué revisar |
|------|-------------|
| 401 | Falta `x-api-key` o la clave no es válida |
| 400 / 415 | JSON mal formado / `Content-Type` incorrecto |
| 422 | Campos inválidos, paciente incorrecto o vínculos ambiguos |
| 413 | La entrada supera 1 MiB |
| 500 / 502 | Error interno / fallo del evaluador conectado |

Un error incluye `codigo`, `mensaje` y detalles de los campos afectados.

El módulo devuelve la imagen. Cada grupo decide dónde guardarla y cómo mostrarla.

La evaluación de síntomas usa, por ahora, un catálogo provisorio.

---

## Swagger de la API

<https://laboratorio-navy-eta.vercel.app/familiograma-api/index.html>

### API keys por grupo

| Grupo | Clave |
|-------|-------|
| grupo-01 | `lab_KGehGBVylaUf2zyQ_bIlejkJQv6ogcuY6bZYKvbuH-Y` |
| grupo-02 | `lab_tU6h9RvB5b3j1vXqZbNtrgWInJw7T8FeTffcJ3cpYKw` |
| grupo-03 | `lab_l9aU7ZibIIzAOIcium214H14HWfDH1y8bBgqx3sw6Zg` |
| grupo-04 | `lab_J9aB_4cwuffil1hJkoIfl5YpozT_TbugsIjfnSqgvvg` |
| grupo-05 | `lab_u80v1gZnSX66uAh9l6H5OxkQR0UywKOb62FqCey_YFw` |
| grupo-06 | `lab_HJNRJV3D7YpjE2etbVdW5w9xruKQ1WKjE2xI3L9QloY` |
| grupo-07 | `lab_C0iAtj74-Yv_nM2kSuO5pbLMKGDgHDK-izVM0U8Ia1U` |
| grupo-08 | `lab_INJP_jLTyqbFPzx5agArGPfVrUUM5ppcnJF09mNDQU4` |
| grupo-09 | `lab_AiAhvtLHfDE6VoWBl-mc9SecVeNbbnJ2eDbiQg6qhPY` |
| grupo-10 | `lab_ghQam6_Ed5gLzS2DrjsyL_O909u8X8qsWsEZ_k8Tw0E` |
