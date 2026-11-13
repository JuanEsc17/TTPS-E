# Apigen

**TTPS 2026 · Grupo 10 · Módulo 5**

La API de bioinformática

Nicolás Díaz, Justina Guerrero, Iván Sgriletti, Leonel Gómez

---

## El problema

### Qué le pregunta su sistema a Apigen

| Caso de uso | Pregunta | Detalle | Endpoints |
|-------------|----------|---------|-----------|
| **E10** · Dar de alta estudio | ¿Qué genes estudio? | Los de la patología sospechada y los de hallazgos secundarios. | 2 · 3 · 4 |
| **E34** · Registrar variante | ¿Qué variante encontré? | Una de las conocidas del gen, con su clasificación. | 1 · 5 |
| **E35** · Informar resultado | ¿Se confirma el diagnóstico? | Positivo, portador o negativo, y los hallazgos secundarios. | 6 · 7 · 8 |
| **E36** · Dar de alta patología | ¿Y una patología nueva? | El grupo la carga con sus genes y su herencia. | 9 |

- **Gen:** el tramo de ADN con la receta de una proteína.
- **Variante:** una letra distinta a la del ADN de referencia.

---

## Arquitectura

### De ClinVar a sus sistemas, sin servidor propio

**ClinVar** → *carga* → **Supabase** → *API REST* → **Sus sistemas**

- **ClinVar:** la base pública de variantes genéticas del NCBI. Se carga con `cargar_clinvar_v2.py`.
- **Supabase:**
  - **PostgREST:** genera la API REST sola, desde tablas, vistas y funciones.
  - **PostgreSQL:** la lógica de diagnóstico, en funciones PL/pgSQL.
  - Solo lectura (RLS). Única escritura: `alta_patologia`.
- **Sus sistemas:** cualquier cliente HTTP con el header `apikey`.
  - El sistema de cada grupo.
  - Cliente de ejemplo: FastAPI.

---

## Los datos

### Apigen en números

| Número | Qué es | Detalle |
|--------|--------|---------|
| **6** | patologías base | Fabry · Pompe · Gaucher · MPS 1 · MPS 2 · ASMD |
| **84** | genes de hallazgos secundarios | Lista ACMG SF v3.3 |
| **~19.000** | genes cargados | Casi 19.000, todos desde ClinVar |
| **+600.000** | variantes cargadas | Cada una con su clasificación |
| **~3.660** | variantes solo en GAA | El gen de Pompe |
| **9** | endpoints | 8 de consulta y 1 de alta |

---

## El desafío

### Todo ClinVar no entra en 500 MB

*Esquema, no a escala:* ClinVar completo supera los 500 MB del plan gratuito; Apigen queda por debajo.

**1. Tabla compacta**

La clasificación se guarda como un número que apunta a una tabla catálogo.

```
clasificación: 1  →  1 = patogenica
```

**2. Carga selectiva**

- Nuestros genes → todas las variantes
- Resto del genoma → solo las patogénicas

---

## ¿Cómo conectarse?

### Una URL base y un header

| | |
|---|---|
| **URL base** | `https://edmrjmfjklwgazzztjcl.supabase.co/rest/v1` |
| **Header** | `apikey: sb_publishable_Ogyld01ST0Gu8zlPBjLmow_9FYtNamo` |
| **No así** | ~~`Authorization: Bearer sb_publishable_…`~~ |

**Así se ve un pedido**

```
GET /gen?simbolo=ilike.GA*&select=simbolo&limit=20
apikey: sb_publishable_Ogyld01ST0Gu8zlPBjLmow_9FYtNamo
```

- Clave pública: se puede mostrar.
- Todo es de solo lectura.

---

## La variante estrella

### Cómo se lee una variante

```
IDS:c.514C>T
```

| Parte | Significado |
|-------|-------------|
| **IDS** · El gen | IDS es el gen de la MPS 2 (mucopolisacaridosis tipo 2). |
| **c.** · ADN codificante | La posición se cuenta en la parte del gen que se traduce a proteína. |
| **514** · La posición | El lugar 514 de esa secuencia. |
| **C>T** · El cambio | Donde debería haber una C (citosina) hay una T (timina). |

`p.Arg172Ter`: en la posición 172, en vez de arginina aparece un **stop**: la proteína queda cortada.
Clasificación **patogénica** → resultado **positivo · ligada al X**.

### Por qué el gen va adelante

**54** genes distintos tienen una variante `c.514C>T`:

| Variante | Clasificación |
|----------|---------------|
| `IDS:c.514C>T` | patogénica |
| `ABCD1:c.514C>T` | benigna |
| `APC:c.514C>T` | VUS · incierta |
| `BAG3:c.514C>T` | patogénica |

---

## Endpoints 1 y 2 · Para empezar

### Buscar genes y listar patologías

#### GET · Buscar genes

```
/gen?simbolo=ilike.GA*&select=simbolo&limit=20
```

- `simbolo`: filtro por prefijo.
- `select` · `limit`: qué columnas y cuántas filas.

**Respuesta**

```json
[{"simbolo":"GAA"},
 {"simbolo":"GAB1"}…]
```

**Para qué:** autocompletar el gen cuando el médico lo agrega a mano (E10).

#### POST · Listar patologías

```
/rpc/listar_patologias
```

- `p_grupo_id`: opcional, ej. `grupo3`; suma las de tu grupo.

**Pedido → respuesta**

```json
{"p_grupo_id": "grupo3"}
→ [{"codigo": "ASMD", …,
    "herencia": "autosomica_recesiva",
    "genes": ["SMPD1"],
    "de_grupo": false}, …]
```

**Para qué:** llenar el selector del diagnóstico presuntivo (E06).

---

## Endpoints 3 y 4 · Qué genes estudiar

### Genes de una patología y genes ACMG

#### POST · Genes de una patología

```
/rpc/genes_por_patologia
```

- `p_patologia`: código, por ejemplo `POMPE`.
- `p_grupo_id`: para las de tu grupo.

**Pedido → respuesta**

```json
{"p_patologia":"POMPE"}
→ ["GAA"]
```

**Para qué:** cargar los genes del estudio al darlo de alta (E10).

#### GET · Genes de hallazgos secundarios

```
/genes_hallazgos_secundarios?select=gen,condicion,herencia
```

Sin parámetros: siempre devuelve los 84 de la lista ACMG SF v3.3.

**Respuesta (84 genes)**

```json
[{"gen": "BRCA1",
  "condicion":
    "Cáncer de mama y ovario hereditario",
  "herencia": "dominante"}, …]
```

**Para qué:** si el estudio evalúa hallazgos secundarios, saber qué genes mirar (E10).

---

## Endpoint 5 · Registrar variante

### Variantes de un gen

#### GET · `/variantes`

```
?gen=eq.GAA
&select=id,hgvs_c,proteina,clasificacion
&limit=50&offset=0
```

**Parámetros**

| Parámetro | Descripción |
|-----------|-------------|
| `gen` | `eq.GAA`: el gen |
| `hgvs_c` | `ilike.*…*`: buscar texto |
| `clasificacion` | `eq.…`: filtrar por clase |
| `limit` · `offset` | paginación |
| `Prefer` | header `count=exact`: el total |

**Pedido**

```
GET /variantes?gen=eq.GAA&…
Prefer: count=exact
```

**Respuesta**

```
Content-Range: 0-49/3662
```

```json
[{"id": "GAA:c.-32-13T>G",
  "hgvs_c": "c.-32-13T>G",
  "proteina": null,
  "clasificacion": "patogenica"}, …]
```

**Para qué lo usa tu sistema:** el bioinformático elige, entre las conocidas del gen, la variante que encontró (E34).

---

## Reglas de negocio · Clasificaciones

### Solo patogénica confirma

| Clasificación | Valor | Significado | ¿Confirma? |
|---------------|-------|-------------|------------|
| Patogénica | `patogenica` | Causa la enfermedad. | **Confirma el diagnóstico** |
| Probablemente patogénica | `probablemente_patogenica` | Es muy posible que la cause. | **No confirma.** El sistema del grupo programa una reevaluación al año. |
| VUS | `vus` | Significado incierto: todavía no se sabe. | **No confirma.** El sistema del grupo programa una reevaluación al año. |
| Benigna | `benigna` | No causa la enfermedad. | **No confirma** |

---

## Reglas de negocio · Herencia

### ¿Cuántas copias afectadas hacen falta?

Tenemos dos copias de cada gen, una de cada progenitor.

**Recesiva** (Pompe · Gaucher · MPS 1 · ASMD): hacen falta las dos copias afectadas.

| Copias con variante patogénica | Resultado |
|--------------------------------|-----------|
| Ninguna | negativo |
| Una | portador |
| Las dos | positivo |

**Ligada al X** (Fabry · MPS 2): alcanza con una copia afectada.

| Copias con variante patogénica | Resultado |
|--------------------------------|-----------|
| Ninguna | negativo |
| Una | positivo |

**Ejemplo real · Pompe:** `GAA:c.-32-13T>G` → **portador** · repetida (homocigota) → **positivo**.

---

## Endpoints 6 y 7 · Diagnóstico

### Confirmar diagnóstico y resultado

- **POST 6** `/rpc/confirma_diagnostico`
- **POST 7** `/rpc/resultado_diagnostico`

**Parámetros (los mismos en los dos)**

| Parámetro | Descripción |
|-----------|-------------|
| `p_patologia` | código de la patología |
| `p_variantes` | variantes del paciente |
| `p_grupo_id` | tu grupo (sus patologías) |

**6 · `confirma_diagnostico`**

```json
{"p_patologia": "POMPE",
 "p_variantes": ["c.-32-13T>G", "c.525del"]}
→ true
```

**7 · `resultado_diagnostico`**

```json
{"p_patologia": "POMPE",
 "p_variantes": ["GAA:c.-32-13T>G"]}
→ "portador"
```

Valores posibles: `positivo`, `portador`, `negativo`.

**Para qué lo usa tu sistema**

- **6:** ¿se confirma la patología? Sí o no.
- **7:** el matiz para el informe del resultado (E35).

---

## Endpoint 8 · Lo que no se buscaba

### Hallazgos secundarios

```
POST /rpc/hallazgos_secundarios
```

**Parámetros**

| Parámetro | Descripción |
|-----------|-------------|
| `p_variantes` | todas, con el gen |
| `p_excluir_patologias` | lo que se estudia |

**Reglas**

- Solo genes ACMG y variantes patogénicas.
- Sin los genes de la patología sospechada: eso ya es diagnóstico.
- En genes ACMG recesivos hacen falta dos variantes.

**Pedido**

```json
{"p_variantes": ["BRCA2:c.5946del",
                 "GAA:c.-32-13T>G"],
 "p_excluir_patologias": ["POMPE"]}
```

**Respuesta:** solo BRCA2 (GAA queda afuera, es lo que se estudia)

```json
→ [{"variante": "BRCA2:c.5946del",
    "gen": "BRCA2", "hgvs_c": "c.5946del",
    "clasificacion": "patogenica",
    "herencia": "dominante", "copias": 1,
    "condicion": …}]
```

**Para qué lo usa tu sistema:** avisar lo importante que no se buscaba, como BRCA2.

---

## Endpoint 9 · La única escritura

### Alta de una patología del grupo

```
POST /rpc/alta_patologia
```

**Parámetros**

| Parámetro | Descripción |
|-----------|-------------|
| `p_grupo_id` | texto fijo, ej. `grupo3` |
| `p_codigo` | código, por ejemplo `MPS3A` |
| `p_nombre` | nombre de la patología |
| `p_genes` | lista de genes |
| `p_herencia` | autosómica o ligada al X |

**Pedido**

```json
{"p_grupo_id": "grupo3",
 "p_codigo": "MPS3A",
 "p_nombre": "Mucopolisacaridosis tipo 3A",
 "p_genes": ["SGSH"],
 "p_herencia": "autosomica_recesiva"}
```

**Respuesta**

```json
→ [{"codigo": "MPS3A", "nombre": …,
    "herencia": "autosomica_recesiva",
    "genes": ["SGSH"]}]
```

> Función controlada: las tablas siguen siendo de solo lectura.

**Para qué lo usa tu sistema:** sumar una patología propia (E36). Si el código ya existe en tu grupo, se actualiza.

---

## Errores

### Todos los errores responden igual

```
HTTP 400  {"message": "…un texto que se puede mostrar…"}
```

| Entrada | Mensaje |
|---------|---------|
| `"p_variantes": ["4027"]` | Formato de variante inválido: 4027 (usá GEN:c.… o c.…) |
| `"p_variantes": ["GAA:c.99999A>G"]` | Variante inexistente: GAA:c.99999A>G |
| `"p_patologia": "XYZ"` | Patología inexistente: XYZ |
| hallazgos: `["c.5946del"]` | Indicá el gen de la variante, por ejemplo GEN:c.… |

**Para qué:** su sistema puede mostrar el `message` tal cual, ya está escrito para el usuario.

Aparte: clave inválida o escritura directa → 401 o 403. Lista de variantes vacía → 200 con `[]`.

---

## Cómo la usa un cliente · `demo/main.py`

### Apigen es la API. FastAPI es un cliente.

```python
cliente = httpx.AsyncClient(
    base_url=URL, headers={"apikey": CLAVE}, timeout=5)

async def apigen(metodo, ruta, *,
                 json=None, params=None, headers=None):
    try:
        r = await cliente.request(
            metodo, ruta, json=json, params=params, headers=headers)
    except httpx.HTTPError:
        raise HTTPException(503, "Apigen no responde")
    if r.status_code >= 400:
        raise HTTPException(r.status_code,
                            r.json().get("message", r.text))
    return r
```

- Una sola función habla con Apigen.
- `httpx` con timeout de 5 s.
- Header `apikey` en cada pedido.
- Sin respuesta → 503.
- 400 → error propio con el `message`.

## Cómo la usa un cliente · `POST /api/diagnostico`

### Tres llamadas a Apigen, un solo resumen

Flujo entre el **Médico** (interfaz web), el **Sistema del grupo** (cliente FastAPI) y **Apigen** (Supabase):

1. El médico hace `POST /api/diagnostico` al sistema del grupo.
2. El sistema llama a Apigen:
   1. `genes_por_patologia`
   2. `resultado_diagnostico`
   3. `hallazgos_secundarios`
3. El sistema devuelve al médico un solo resumen + reevaluar al año.

## Cómo la usa un cliente · JavaScript

### ¿No usan Python? Con fetch es igual

```js
const BASE = "https://edmrjmfjklwgazzztjcl.supabase.co/rest/v1";
const CLAVE = "sb_publishable_Ogyld01ST0Gu8zlPBjLmow_9FYtNamo";

const r = await fetch(`${BASE}/rpc/resultado_diagnostico`, {
  method: "POST",
  headers: { apikey: CLAVE, "Content-Type": "application/json" },
  body: JSON.stringify({
    p_patologia: "POMPE",
    p_variantes: ["GAA:c.-32-13T>G"],
  }),
});
if (!r.ok) throw new Error((await r.json()).message);
console.log(await r.json()); // "portador"
```

- URL base y clave pública.
- Header `apikey` y `Content-Type` JSON.
- Si falla, leer el `message`.
- Devuelve `"portador"`.

---

## Demo en vivo

### Así lo usa un médico

1. **Elige la patología** → `listar_patologias`
2. **Busca y agrega variantes del gen** → `variantes`
3. **Confirma el diagnóstico** → `resultado_diagnostico`
4. **Ve los hallazgos secundarios** → `hallazgos_secundarios`

- **Swagger en `/docs`:** la documentación que FastAPI genera sola.
- **Postman y `.http`:** un caso por endpoint y los de error.

---

## Cierre

### Simplificaciones que asumimos

- **No conocemos el sexo del paciente:** en los genes ligados al X alcanza una variante.
- **Dos variantes distintas:** asumimos que están en copias distintas del gen.
- **Resto del genoma:** no cargamos las VUS ni las benignas.

> **9 endpoints · solo lectura · +600.000 variantes**
> Apigen está listo para que lo consuman sus sistemas. ¡Gracias!

---

## ¿Preguntas?

`https://edmrjmfjklwgazzztjcl.supabase.co/rest/v1`

Nicolás Díaz · Justina Guerrero · Iván Sgriletti · Leonel Gómez
