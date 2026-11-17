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

# ---------- Tipos de error: el status queda fijo; codigo y mensaje se pasan en cada lugar ----------
class ErrorDatosInvalidos(ErrorDominio):          # 422
    def __init__(self, mensaje: str, codigo: str = "DATOS_ENTRADA_INVALIDOS") -> None:
        super().__init__(mensaje, codigo=codigo, http_status=422)


class ErrorNoAutenticado(ErrorDominio):           # 401
    def __init__(self, mensaje: str, codigo: str = "NO_AUTENTICADO") -> None:
        super().__init__(mensaje, codigo=codigo, http_status=401)


class ErrorSinPermiso(ErrorDominio):              # 403
    def __init__(self, mensaje: str, codigo: str = "SIN_PERMISO") -> None:
        super().__init__(mensaje, codigo=codigo, http_status=403)


class ErrorNoEncontrado(ErrorDominio):            # 404
    def __init__(self, mensaje: str, codigo: str = "NO_ENCONTRADO") -> None:
        super().__init__(mensaje, codigo=codigo, http_status=404)


class ErrorConflicto(ErrorDominio):               # 409
    def __init__(self, mensaje: str, codigo: str = "CONFLICTO") -> None:
        super().__init__(mensaje, codigo=codigo, http_status=409)


class ErrorBaseDatos(ErrorDominio):               # 500, reintentable
    def __init__(self, mensaje: str = "Error temporal de base de datos. Intente nuevamente.",
                 codigo: str = "DB_ERROR") -> None:
        super().__init__(mensaje, codigo=codigo, http_status=500, reintentable=True)