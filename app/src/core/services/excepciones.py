"""Excepcion de dominio traducible a respuesta HTTP en la capa web."""


class ErrorDominio(Exception):
    def __init__(
        self,
        mensaje: str,
        codigo: str = "ERROR_DOMINIO",
        http_status: int = 400,
        reintentable: bool = False,
    ) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo
        self.http_status = http_status
        self.reintentable = reintentable