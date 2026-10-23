from flask import Flask, request, jsonify
from marshmallow import Schema, fields, validate, ValidationError
import requests

app = Flask(__name__)

# Servidor público de OSRM
OSRM_SERVER = "http://router.project-osrm.org"

# --- ESQUEMAS DE VALIDACIÓN DE DATOS (Marshmallow) ---
class CoordenadaSchema(Schema):
    lon = fields.Float(required=True)
    lat = fields.Float(required=True)

class PeticionRecorridoSchema(Schema):
    coordenadas = fields.List(fields.Nested(CoordenadaSchema), required=True, validate=validate.Length(min=2))
    source = fields.Str(load_default="first", validate=validate.OneOf(["first", "any"]))
    destination = fields.Str(load_default="last", validate=validate.OneOf(["last", "any"]))

@app.route('/')
def home():
    return 'hola'

# --- ENDPOINT ---
@app.route('/api/optimizacion', methods=['POST'])
def calcular_recorrido_eficiente():
    """
    Calcula el recorrido eficiente entre un conjunto de coordenadas.

    Entrada (JSON Body):
        coordenadas (list[dict]): Lista de al menos 2 coordenadas geográficas:
            - lon (float): Longitud.
            - lat (float): Latitud.
    
    Respuestas:
        200 OK:
            Lista con las coordenadas de entrada ordenadas según la ruta óptima.
        400 Bad Request:
            - El cuerpo de la petición no es un JSON válido.
            - Error retornado por el motor OSRM.
        422 Unprocessable Entity:
            Errores de validación de los datos (tipos incorrectos, faltan campos requeridos o menos de 2 coordenadas).
        500 Internal Server Error:
            Fallo de conexión o respuesta inesperada del servidor de mapas OSRM.
    """
    # 1. Validar los datos de entrada
    json_data = request.get_json()
    if not json_data:
        return jsonify({"error": "El cuerpo de la petición debe ser un JSON válido."}), 400
        
    schema = PeticionRecorridoSchema()
    try:
        datos = schema.load(json_data)
    except ValidationError as err:
        return jsonify({"errores_validacion": err.messages}), 422

    # 2. Formatear las coordenadas al formato que exige OSRM -> lon,lat;lon,lat...
    coords_str = ";".join([f"{c['lon']},{c['lat']}" for c in datos['coordenadas']])
    
    # 3. Construir la URL y parámetros del servicio 'trip' de OSRM
    url = f"{OSRM_SERVER}/trip/v1/car/{coords_str}"
    params = {
        "source": "first",
        "destination": "last",
        "geometries": "geojson",
        "overview": "full",
        "steps": "false"
    }
    
    try:
        response = requests.get(url, params=params)
        response_json = response.json()
        
        if response.status_code != 200 or response_json.get("code") != "Ok":
            return jsonify({
                "error": f"Error de OSRM: {response_json.get('code', 'Desconocido')}"
            }), 400
            
        # 4. Ordenar las coordenadas de entrada según el recorrido óptimo de OSRM.
        # En la API Trip de OSRM:
        # - 'waypoints' viene en el mismo orden que las coordenadas de entrada.
        # - 'waypoint_index' es el número de orden de visita (0 = primera parada, 1 = segunda, etc.).
        coordenadas_ordenadas = [
            coord for coord, wp in sorted(
                zip(datos['coordenadas'], response_json['waypoints']),
                key=lambda pair: pair[1]['waypoint_index']
            )
        ]
        
        return jsonify(coordenadas_ordenadas), 200

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Error de conexión con el servidor de mapas: {str(e)}"}), 500

if __name__ == '__main__':
    # Ejecuta el servidor de desarrollo en el puerto 5000
    app.run(debug=True, port=5000)
