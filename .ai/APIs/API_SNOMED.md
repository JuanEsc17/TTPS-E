# API de síntomas SNOMED CT

**Terminología clínica · Edición Argentina**

Qué es, cómo integrarla y cómo funcionan sus tres capas de búsqueda.

- **Capa 1 · Directa**
- **Capa 2 · Léxica**
- **Capa 3 · Semántica**

---

## ¿Qué es la API?

1. **Recibe texto libre.** Lo que escribe el médico: «me falta el aire», «cefal», «fiebrre».
2. **Devuelve síntomas SNOMED CT.** Cada uno con su identificador único (SCTID), para que sean comparables. Estrategias de búsqueda: exacta · prefijo · léxica · semántica.
3. **El médico elige.** Los resultados son sugerencias, no un diagnóstico. Ejemplo: `disnea` · SCTID `267036007`.

> **Notas:** la API recibe lo que escribe el médico en lenguaje natural y devuelve los síntomas de SNOMED CT Edición Argentina que más se parecen. Los resultados son sugerencias: el médico es quien elige. El SCTID del ejemplo es ilustrativo.

---

## Cómo integrarla en el proyecto

**Frontend** (lo que ve el médico) → **Tu backend** (guarda la clave) → **API SNOMED** (Supabase)

> Siempre frontend → backend → API. Si el frontend llama directo, la clave queda visible en el navegador.

**`GET`**

```
https://hwmpslajqivdqeaylhdc.supabase.co/functions/v1/terminologia/sintomas?q={texto}&limite={n}
```

**Parámetros**

- `q`: mínimo 3 caracteres.
- `limite`: de 1 a 50 (10 por defecto).

**Encabezados**

- `X-API-Key`: obligatorio.
- `x-region: us-east-1`: baja de ≈ 8 s a ≈ 1,2 s.

**Buenas prácticas**

- Clave en variable de entorno.
- SCTID siempre como texto.
- Timeout de 15 s.

> **Notas:** la integración es un GET con la clave del grupo en el encabezado `X-API-Key`. Importante: llamarla siempre desde el backend, nunca desde el navegador, para no exponer la clave. Guardar la clave en una variable de entorno (`SNOMED_API_KEY`). El encabezado `x-region: us-east-1` baja el tiempo de respuesta de unos 8 s a unos 1,2 s.

---

## API keys por grupo

| Grupo | API key |
|-------|---------|
| Grupo 1 | `eSUsnZG4y0jHnaJN6TrGX1nyU9gmkNRD` |
| Grupo 2 | `A6DI-dRu4b4XN7eUXOZFtSsyKgqO8c9a` |
| Grupo 3 | `vvJUZJ_pZX7vn_or3ei3ES4lKzl4TsMO` |
| Grupo 4 | `sDuTQzvBPGkClchAM34ztjAJwwa5gVEU` |
| Grupo 5 | `x8dCIKSXh7oD8On71TjsnqM4y16P6eTc` |
| Grupo 6 | `78KMDTaH6OKWUOLg0nNc2gEUJynQ7Yqhi4b2rSnrsJo` |
| Grupo 7 | `RF58r0xDIiWYt-2JBvFvYL905kr3wXJrvIF3MSX4New` |
| Grupo 8 | `9zv509ja2TgN400lxvhCla7u9pVdNeOyEX_zoNA9jWA` |
| Grupo 9 | `pCrp94wHz6ZhyEthbjUzbhse_xRXrUwCt9s56wyW8l0` |
| Grupo 10 | `Wx0RjmM92x9n_OfUo0LDBIKfW1XaWmVAvfUv352UrYA` |

> **Notas:** cada grupo tiene la suya; si se filtra, se rota solo esa.

---

## Capa 1 · Búsqueda directa

Resuelve el caso más frecuente: texto bien escrito, completo o parcial.

**1A · Exacta**

```
q=fiebre  →  fiebre
```

Compara el término completo. Si coincide, lo devuelve primero que todos los demás resultados. Si devuelve al menos un resultado, no pasa a las capas 2 y 3.

**1B · Prefijo**

```
q=cefal  →  cefalea, cefalea aguda…
```

Autocompleta mientras el médico escribe (mín. 3 letras). Si devuelve al menos un resultado, no pasa a las capas 2 y 3.

- Mayúsculas y tildes no importan.
- Cada síntoma aparece una sola vez.

> **Notas:** la capa 1 es la primera de la cascada. Primero busca coincidencia exacta; si la encuentra, corta y no mezcla otros resultados. Si no, busca por prefijo (autocompletado). Si devuelve al menos un candidato, no se ejecutan las capas 2 y 3.

---

## Capa 1 · Probala (1): `q=fiebre`

```powershell
$SNOMED_API_KEY = "sDuTQzvBPGkClchAM34ztjAJwwa5gVEU"; (curl.exe -G "https://hwmpslajqivdqeaylhdc.supabase.co/functions/v1/terminologia/sintomas" --data-urlencode "q=fiebre" -d "limite=2" -H "X-API-Key: $SNOMED_API_KEY" -H "x-region: us-east-1" | ConvertFrom-Json).resultados
```

`q=fiebre` (texto escrito) → coincidencia exacta y después los que empiezan igual (prefijo).

**Respuesta en JSON** (valores ilustrativos)

```
sctid               : 386661006
termino_preferido   : fiebre
termino_coincidente : fiebre
estrategia          : exacta
similitud           :
origen              : snomed

sctid               : 304213008
termino_preferido   : fiebre baja
termino_coincidente : fiebre baja
estrategia          : prefijo
similitud           :
origen              : snomed
```

---

## Capa 1 · Probala (2): `q=fie`

```powershell
$SNOMED_API_KEY = "sDuTQzvBPGkClchAM34ztjAJwwa5gVEU"; (curl.exe -G "https://hwmpslajqivdqeaylhdc.supabase.co/functions/v1/terminologia/sintomas" --data-urlencode "q=fie" -d "limite=2" -H "X-API-Key: $SNOMED_API_KEY" -H "x-region: us-east-1" | ConvertFrom-Json).resultados
```

`q=fie` (texto escrito) → prefijo.

**Respuesta en JSON** (valores ilustrativos)

```
sctid               : 386661006
termino_preferido   : fiebre
termino_coincidente : fiebre
estrategia          : prefijo
similitud           :
origen              : snomed

sctid               : 304213008
termino_preferido   : fiebre baja
termino_coincidente : fiebre baja
estrategia          : prefijo
similitud           :
origen              : snomed
```

---

## Capa 1 · Probala (3): Postman

*(Diapositiva con una captura de pantalla de Postman; la imagen no está incluida en este archivo.)*

```
https://hwmpslajqivdqeaylhdc.supabase.co/functions/v1/terminologia/sintomas?q={TEXTO}&limite={n}
```

---

## Capa 1 · Probala (4): terminal

*(Diapositiva con una captura de pantalla del resultado del comando; la imagen no está incluida en este archivo.)*

```powershell
$SNOMED_API_KEY = "sDuTQzvBPGkClchAM34ztjAJwwa5gVEU"; (curl.exe -G "https://hwmpslajqivdqeaylhdc.supabase.co/functions/v1/terminologia/sintomas" --data-urlencode "q=fiebre" -d "limite=2" -H "X-API-Key: $SNOMED_API_KEY" -H "x-region: us-east-1" | ConvertFrom-Json).resultados
```

---

## Capa 2 · Búsqueda léxica

Encuentra síntomas que se parecen en letras al texto escrito: errores de tipeo, letras omitidas, cambiadas o de más.

**Trigramas** (grupos de 3 letras; `·` = espacio):

| Texto | Trigramas |
|-------|-----------|
| `fiebre` | `··f` `·fi` `fie` `ieb` `ebr` `bre` `re·` |
| `fiebrre` | `··f` `·fi` `fie` `ieb` `ebr` `brr` `rre` `re·` |

Compartidos: `··f`, `·fi`, `fie`, `ieb`, `ebr`, `re·`.

**Similitud:** 6 compartidos ÷ 9 totales ≈ **0,67**

Un error de tipeo cambia pocos trigramas, así que la similitud sigue alta.

| Umbral | Significado |
|--------|-------------|
| **0,35** | Similitud mínima para mostrar un resultado |
| **0,80** | Si se alcanza, no hace falta la capa 3 |

> **Notas:** la capa 2 usa trigramas con la extensión `pg_trgm` de PostgreSQL. La similitud es la proporción de trigramas compartidos sobre el total de trigramas distintos. El mínimo se bajó de 0,50 a 0,35 y el corte es 0,80; ambos valores están sujetos a calibración. Solo se ejecuta si la capa 1 no encontró coincidencia exacta.

---

## Capa 2 · Probala: `q=fiebrre`

```powershell
$SNOMED_API_KEY = "sDuTQzvBPGkClchAM34ztjAJwwa5gVEU"; (curl.exe -G "https://hwmpslajqivdqeaylhdc.supabase.co/functions/v1/terminologia/sintomas" --data-urlencode "q=fiebrre" -d "limite=5" -H "X-API-Key: $SNOMED_API_KEY" -H "x-region: us-east-1" | ConvertFrom-Json).resultados
```

**Respuesta esperada** (estrategia léxica)

```json
{
  "sctid": "386661006",
  "termino_preferido": "fiebre",
  "estrategia": "lexica",
  "similitud": 0.67
}
```

**Más consultas para probar**

| Consulta | Resultado |
|----------|-----------|
| `q=fibre` | 0,444: pasa el mínimo (≥ 0,35) |
| `q=fbre` | 0,333: no pasa (< 0,35) |
| `q=dolr abdominal` | — |

> **Notas:** mismo procedimiento que en la capa 1, cambiando `q`. En Swagger o Postman alcanza con escribir `fiebrre` en el parámetro `q`. La similitud del ejemplo es ilustrativa (≈ 0,67 calculado a mano). Con `fibre` la similitud es 0,444: con el mínimo en 0,35 sí se devuelve (con 0,50 quedaba afuera). Con `fbre` la similitud contra `fiebre` es 0,333, por debajo de 0,35: la capa léxica no la devuelve. Valores calculados a mano con la regla de `pg_trgm` contra el término `fiebre`; conviene confirmarlos en Swagger, porque otro término del catálogo podría superar el umbral y la capa 3 puede aportar resultados igual.

---

## Capa 3 · Búsqueda semántica

Entiende el significado, no las letras: «me falta el aire» → disnea · «chuchos de frío» → escalofríos.

**Texto** → **Modelo E5** → **Coseno** → **Candidatos**

| Paso | Qué hace | Ejemplo |
|------|----------|---------|
| Texto | Lo que escribe el médico | `me falta el aire` |
| Modelo E5 | Lo convierte en 384 números | |
| Coseno | Lo compara con 2217 textos | |
| Candidatos | Los más cercanos en significado | |

- **384:** números por vector.
- **2217:** textos indexados (2131 de SNOMED y 86 coloquiales).
- **35 MB:** modelo recortado (de 118 MB) para entrar en 256 MB.

> **Notas:** la capa 3 usa embeddings: el modelo `multilingual-e5-small` convierte el texto en un vector de 384 números y se compara por similitud coseno contra los 2217 textos indexados (2131 de SNOMED y 86 expresiones del glosario coloquial argentino). El modelo se recortó y cuantizó (q8) para entrar en el límite de 256 MB de las Edge Functions.

---

## Capa 3 · Probala: `q=me falta el aire`

```powershell
$SNOMED_API_KEY = "sDuTQzvBPGkClchAM34ztjAJwwa5gVEU"; (curl.exe -G "https://hwmpslajqivdqeaylhdc.supabase.co/functions/v1/terminologia/sintomas" --data-urlencode "q=me falta el aire" -d "limite=5" -H "X-API-Key: $SNOMED_API_KEY" -H "x-region: us-east-1" | ConvertFrom-Json).resultados
```

**Se encuentra por significado**

- `q=me falta el aire` → disnea, sin compartir letras.
- `q=tengo chuchos de frío` → escalofríos (glosario coloquial).
- `q=panza` → dolor abdominal.

**Respuesta** (valores ilustrativos)

```json
{
  "sctid": "267036007",
  "termino_preferido": "disnea",
  "termino_coincidente": "falta de aire",
  "estrategia": "semantica",
  "similitud": 0.93
}
```

> **Notas:** la capa 3 encuentra síntomas por significado. «me falta el aire» no comparte letras con «disnea», pero el modelo ubica ambos textos cerca; el término coincidente es «falta de aire» y se muestra el preferido, disnea. «tengo chuchos de frío» coincide con una expresión del glosario coloquial (`origen: coloquial`) y apunta a escalofríos. La similitud va de 0 a 1 y no es comparable con la de otras capas. Los valores del JSON son ilustrativos.

---

## Cómo se combinan las capas

1. **Exacta · Capa 1.** ¿Hay coincidencia exacta? La devuelve y termina.
2. **Prefijo + léxica · Capas 1 y 2, en paralelo.** Autocompleta y tolera errores de tipeo. Si la mejor similitud es ≥ 0,80, termina.
3. **Semántica · Capa 3.** Solo si no hubo nada o lo mejor es dudoso (< 0,80). Entiende paráfrasis y lenguaje coloquial.

Va de lo más barato y seguro a lo más caro y difuso. Si falla solo el modelo, la API responde 200 con lo que encontraron las capas 1 y 2.

> **Notas:** la cascada va de lo más barato y seguro a lo más caro. Si hay coincidencia exacta, no tiene sentido sugerir otra cosa. Prefijo y léxica se combinan porque se complementan. La semántica entra solo si no hubo nada o lo mejor de la léxica es dudoso (menor a 0,80).

---

## Más ejemplos para probar

| `q` | Estrategia esperada | Resultado |
|-----|---------------------|-----------|
| `fiebre` | exacta | fiebre |
| `cefal` | prefijo | cefalea |
| `escalofríos` | exacta · con tilde | escalofríos |
| `estreñimiento` | exacta · con ñ | estreñimiento |
| `fiebrre` | léxica | fiebre |
| `me falta el aire` | semántica | disnea |
| `tengo chuchos de frío` | semántica · coloquial | escalofríos |
| `ab` | Error 400 | menos de 3 caracteres |
| `no tengo fiebre` | sin negaciones | puede devolver fiebre |

> **Notas:** consultas para recorrer cada estrategia. «escalofríos» muestra que la tilde funciona en la consulta (con o sin tilde da lo mismo) y «estreñimiento» que la ñ se conserva: «estrenimiento» no equivale a «estreñimiento» en la búsqueda directa. Las dos últimas muestran el error 400 y la limitación de las negaciones. Conviene confirmar en Swagger que estos términos estén en el subconjunto de 1500 síntomas.

---

## Ejemplo de integración en Python

```python
import os, requests

URL = ("https://hwmpslajqivdqeaylhdc.supabase.co"
       "/functions/v1/terminologia/sintomas")

def buscar_sintomas(texto, limite=10):
    clave = os.environ["SNOMED_API_KEY"]
    r = requests.get(
        URL,
        params={"q": texto, "limite": limite},
        headers={"X-API-Key": clave,
                 "x-region": "us-east-1"},
        timeout=15,
    )
    if r.status_code == 200:
        return r.json()["resultados"]
    if r.status_code == 400:
        raise ValueError(r.json()["detalle"])
    r.raise_for_status()
```

**Lo que se le pasa**

| Dato | Dónde | Descripción |
|------|-------|-------------|
| `q` | URL | texto del médico (mín. 3 caracteres) |
| `limite` | URL | máximo de resultados, de 1 a 50 |
| `X-API-Key` | encabezado | la clave de tu grupo |
| `x-region` | encabezado | `us-east-1`: tarda ≈ 1,2 s |

Devuelve `resultados[]`: guardá el `sctid` como texto.

> **Notas:** lo más importante es qué se le pasa a la API. `q` y `limite` van en la URL (en `requests`, con `params`). La clave del grupo va en el encabezado `X-API-Key` y se lee de una variable de entorno. `x-region: us-east-1` es recomendado porque baja el tiempo de unos 8 s a unos 1,2 s. La respuesta es una lista en `resultados`; el `sctid` siempre como texto. Un 200 con lista vacía no es un error.

---

## Respuesta de la API en JSON

```jsonc
// q=me falta el aire · valores ilustrativos
{
  "resultados": [
    {
      "sctid": "267036007",
      "termino_preferido": "disnea",
      "termino_coincidente": "falta de aire",
      "estrategia": "semantica",
      "similitud": 0.93
    },
    {
      "sctid": "230145002",
      "termino_preferido": "dificultad respiratoria",
      "termino_coincidente": "respiración difícil",
      "estrategia": "semantica",
      "similitud": 0.88
    }
  ]
}
```

**Cómo leerla**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `resultados` | lista | síntomas encontrados; puede venir vacía |
| `sctid` | texto | código SNOMED: guardalo como texto |
| `termino_preferido` | texto | nombre oficial: el que se muestra |
| `estrategia` | texto | `exacta`, `prefijo`, `lexica`, `semantica` |

También: `similitud` (de 0 a 1) y, a veces, `termino_coincidente`.

> **Notas:** el ejemplo trae dos resultados, pero pueden venir varios (hasta el `limite` pedido). Según la capa puede venir también `termino_coincidente`: el texto del catálogo que coincidió con lo escrito. Los valores del ejemplo son ilustrativos y corresponden a la capa 3 con `q=me falta el aire`. Un 200 con lista vacía no es un error; si hay error, el cuerpo es `{"detalle": "..."}`.

---

## Códigos HTTP y límites

| Código | Cuándo |
|--------|--------|
| 200 | Búsqueda correcta, también sin resultados |
| 400 | `q` muy corta o `limite` inválido |
| 401 | Falta la clave o no es válida |
| 500 / 503 | Error de la API o base caída: reintentar |

**Límites a conocer**

- Catálogo de 1500 síntomas, de 15 777 posibles.
- Glosario coloquial (86 expresiones) sin validación clínica.
- No entiende negaciones: «no tengo fiebre».

> **Notas:** todos los errores tienen el cuerpo `{"detalle": "..."}`. Un 200 con lista vacía no es un error.

---

## Video explicativo

*(Diapositiva con un video sobre las capas de la API; en la presentación todavía figura el texto «Acá va el video» y falta pegar el link.)*

---

## ¿Preguntas?
