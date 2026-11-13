"""Capa de Clientes HTTP para integraciones con APIs externas (TTPS-E)."""
from .apigen_client import ApigenClient, BioinformaticaClient
from .cdss_client import CDSSClient, CdssClient
from .chatbot_client import ChatbotClient
from .cupones_client import CuponesClient
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
from .fedex_client import FedExClient, FedexClient
from .obra_social_client import ObraSocialClient, ObrasSocialesClient
from .optimizacion_client import OptimizacionClient
from .snomed_client import SnomedClient

__all__ = [
    "PARENTESCOS_MAP",
    "PARENTESCOS_POR_NOMBRE",
    "ApigenClient",
    "BioinformaticaClient",
    "CDSSClient",
    "CdssClient",
    "ChatbotClient",
    "ClienteAutenticacionError",
    "ClienteConexionError",
    "ClienteError",
    "ClienteServicioError",
    "ClienteValidacionError",
    "CuponesClient",
    "EmailClient",
    "FamiliogramaClient",
    "FedExClient",
    "FedexClient",
    "ObraSocialClient",
    "ObrasSocialesClient",
    "OptimizacionClient",
    "SnomedClient",
]
