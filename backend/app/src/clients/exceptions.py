"""Excepciones para la capa de clientes de APIs externas."""


class ClienteError(Exception):
    """Excepcion base para errores al comunicarse con servicios externos."""

    def __init__(
        self,
        mensaje: str,
        codigo_http: int | None = None,
        respuesta: dict | str | None = None,
    ):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo_http = codigo_http
        self.respuesta = respuesta


class ClienteAutenticacionError(ClienteError):
    """Error de autenticacion (401 o 403) con la API externa."""


class ClienteValidacionError(ClienteError):
    """Error de validacion o formato (400 o 422) retornado por la API externa."""


class ClienteConexionError(ClienteError):
    """Error de red, timeout o conexion no establecida con el servicio externo."""


class ClienteServicioError(ClienteError):
    """Error interno o falla de servicio (500, 502, 503) en la API externa."""

