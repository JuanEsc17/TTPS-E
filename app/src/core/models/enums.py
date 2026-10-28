"""Enums del dominio."""
import enum


class Rol(enum.Enum):
    PACIENTE = "paciente"
    MEDICO = "medico"
    GERENTE_MEDICO = "gerente_medico"
    ADMINISTRATIVO = "administrativo"
    BIOINFORMATICO = "bioinformatico"
    TRANSPORTISTA = "transportista"
    ADMIN_GENERAL = "admin_general"


class EstadoEstudio(enum.Enum):
    CREADO = "Creado"
    PENDIENTE_AUTORIZACION = "Pendiente de autorizacion"
    AUTORIZADO = "Autorizado"
    RECHAZADO = "Rechazado"
    TURNO_SACADO = "Turno sacado"
    LISTA_PARA_RETIRAR = "Lista para retirar"
    EN_CAMINO_LAB_CENTRAL = "En camino al laboratorio central"
    EN_LAB_CENTRAL = "En laboratorio central"
    EN_ESPERA_RETIRO = "En espera de retiro"
    EN_VIAJE_COREA = "En viaje a Corea"
    EN_ANALISIS_BIOINFORMATICA = "En analisis por bioinformatica"
    EN_ANALISIS_BIOINFORMATICO = "En analisis de un bioinformatico"
    RESULTADO_CARGADO = "Resultado cargado"
    REMUESTREO_REQUERIDO = "Remuestreo requerido"


class TipoPago(enum.Enum):
    PARTICULAR = "particular"
    OBRA_SOCIAL = "obra_social"


class ResultadoAutorizacion(enum.Enum):
    PENDIENTE = "pendiente"
    AUTORIZADA = "autorizada"
    RECHAZADA = "rechazada"


class EstadoSampleSet(enum.Enum):
    ABIERTO = "abierto"
    CERRADO = "cerrado"                 # sellado, a la espera de retiro
    EN_VIAJE_COREA = "en_viaje_a_corea"


class ClasificacionVariante(enum.Enum):
    PATOGENICA = "patogenica"
    BENIGNA = "benigna"
    INOCUA = "inocua"
    VUS = "vus"


class OrigenGen(enum.Enum):
    PATOLOGIA = "patologia"             # lista obtenida de la API de bioinformatica
    MANUAL = "manual"                   # agregado por el medico
    HALLAZGO_SECUNDARIO = "hallazgo_secundario"


class TipoAnalisis(enum.Enum):
    INICIAL = "inicial"
    REANALISIS = "reanalisis"


class MotivoDescarte(enum.Enum):
    VOLUMEN_INSUFICIENTE = "volumen_insuficiente"   # < 2 ml
    ADN_INSUFICIENTE = "adn_insuficiente"
    DESNATURALIZADA = "desnaturalizada"


class EstrategiaCDSS(enum.Enum):
    """Estrategia que el CDSS usa para elegir la patologia (configurable desde nuestro sistema)."""
    MAYOR_CANTIDAD_SINTOMAS = "mayor_cantidad_sintomas"
    MAYOR_CANTIDAD_CARDINALES = "mayor_cantidad_cardinales"
    MENOR_DIFERENCIA = "menor_diferencia"


class CanalAviso(enum.Enum):
    """Canales del modulo de avisos."""
    APP = "app"
    MAIL = "mail"
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
