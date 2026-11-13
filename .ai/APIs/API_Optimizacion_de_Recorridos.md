# API de Optimización de Recorridos

Ordena puntos geográficos intermedios para minimizar la distancia de viaje mediante OSRM.

```
POST /api/optimizacion
```

> **Regla de partida y llegada**
>
> La **primera coordenada** de la lista se fija como punto de partida y la **última coordenada** como destino final. El algoritmo únicamente optimiza el orden de las paradas intermedias.

## Petición (Request Body)

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `coordenadas` *(requerido)* | Array de objetos | Lista de al menos 2 coordenadas geográficas. |
| `lat` *(requerido)* | Float | Latitud decimal del punto. |
| `lon` *(requerido)* | Float | Longitud decimal del punto. |

**Ejemplo JSON (Petición)**

```json
{
  "coordenadas": [
    {"lat": -34.6037, "lon": -58.3816},
    {"lat": -34.5700, "lon": -58.4300},
    {"lat": -34.5900, "lon": -58.3900},
    {"lat": -34.5450, "lon": -58.4500}
  ]
}
```

## Códigos de Respuesta

| Código HTTP | Descripción |
|-------------|-------------|
| `200 OK` | Devuelve un objeto con la lista de coordenadas ordenadas óptimamente. |
| `400 Bad Request` | JSON malformado o error devuelto por el motor OSRM. |
| `422 Unprocessable` | Faltan campos obligatorios o se enviaron menos de 2 coordenadas. |
| `500 Server Error` | Error de conexión con el servidor de mapas OSRM. |

**Ejemplo de respuesta 200 OK (Orden Optimizado)**

```json
{
  "coordenadas": [
    {"lat": -34.6037, "lon": -58.3816},
    {"lat": -34.5900, "lon": -58.3900},
    {"lat": -34.5700, "lon": -58.4300},
    {"lat": -34.5450, "lon": -58.4500}
  ]
}
```

> **Nota:** El primer y último punto se mantuvieron fijos, mientras que los puntos intermedios (`-34.5900` y `-34.5700`) se reordenaron para seguir la trayectoria óptima.

---

*API de Optimización • Flask + OSRM*
