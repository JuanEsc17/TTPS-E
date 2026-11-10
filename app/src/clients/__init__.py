"""Capa de Clientes HTTP para integraciones con APIs externas (TTPS-E)."""
from .apigen_client import ApigenClient, BioinformaticaClient
from .email_client import EmailClient
from .exceptions import (
    ClienteAutenticacionError,
    ClienteConexionError,
    ClienteError,
    ClienteServicioError,
    ClienteValidacionError,
)
from .familiograma_client import (
    PARENTESCOS_MAP,
    PARENTESCOS_POR_NOMBRE,
    FamiliogramaClient,
)
from .optimizacion_client import OptimizacionClient
from .snomed_client import SnomedClient

__all__ = [
    "PARENTESCOS_MAP",
    "PARENTESCOS_POR_NOMBRE",
    "ApigenClient",
    "BioinformaticaClient",
    "ClienteAutenticacionError",
    "ClienteConexionError",
    "ClienteError",
    "ClienteServicioError",
    "ClienteValidacionError",
    "EmailClient",
    "FamiliogramaClient",
    "OptimizacionClient",
    "SnomedClient",
]
