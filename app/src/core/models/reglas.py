"""Constantes y reglas de negocio del glosario."""
from decimal import Decimal

PRECIO_BASE_USD = Decimal(500)
GENES_INCLUIDOS = 5
PRECIO_GEN_ADICIONAL_USD = Decimal(30)
MAX_AUSENCIAS = 5
MUESTRAS_POR_SAMPLE_SET = 10
ML_MINIMOS_TUBO = Decimal(2)


def calcular_precio(cantidad_genes: int) -> Decimal:
    """500 USD hasta 5 genes + 30 USD por cada gen adicional."""
    extra = max(0, cantidad_genes - GENES_INCLUIDOS)
    return PRECIO_BASE_USD + PRECIO_GEN_ADICIONAL_USD * extra
