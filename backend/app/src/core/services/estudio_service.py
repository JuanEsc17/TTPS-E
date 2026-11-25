"""Logica de negocio para el alta y consulta de estudios de exoma (Escenario 2)."""
from datetime import date

from src.clients.apigen_client import ApigenClient
from src.clients.exceptions import ClienteError
from src.core.models import OrigenGen
from src.core.repos import clinica_repo, estudio_repo, paciente_repo
from src.core.services.excepciones import ErrorDominio


def _es_pompe_urgente(patologia_nombre: str, fecha_nacimiento: date) -> bool:
    """Retorna True si la patologia es Pompe y el paciente tiene menos de 4 meses."""
    if patologia_nombre.strip().lower() != "pompe":
        return False
    hoy = date.today()
    meses = (hoy.year - fecha_nacimiento.year) * 12 + (hoy.month - fecha_nacimiento.month)
    if hoy.day < fecha_nacimiento.day:
        meses -= 1
    return meses < 4


def listar_obras_sociales() -> list[dict]:
    """Retorna el catalogo de obras sociales disponibles."""
    return [
        {
            "id": os_item.id,
            "nombre": os_item.nombre,
            "porcentaje_cobertura": float(os_item.porcentaje_cobertura),
        }
        for os_item in estudio_repo.listar_obras_sociales()
    ]


def listar_estudios_medico(usuario_actual_id: int) -> list[dict]:
    """Lista los estudios solicitados por el medico autenticado."""
    medico = paciente_repo.buscar_medico_por_usuario_id(usuario_actual_id)
    if medico is None:
        raise ErrorDominio(
            "Solo un medico tratante o gerente medico puede consultar estudios.",
            codigo="FORBIDDEN_ROLE",
            http_status=403,
        )

    estudios = estudio_repo.listar_estudios_por_medico(medico.id)
    return [
        {
            "estudio_id": est.id,
            "paciente_id": est.paciente_id,
            "paciente_nombre": f"{est.paciente.usuario.nombre} {est.paciente.usuario.apellido}",
            "paciente_dni": est.paciente.dni,
            "patologia_nombre": est.patologia_sospechada.nombre,
            "estado": est.estado.value,
            "es_pompe_urgente": est.es_pompe_urgente,
            "quiere_hallazgos_secundarios": est.quiere_hallazgos_secundarios,
            "obra_social_nombre": est.obra_social.nombre if est.obra_social else "Particular",
            "cantidad_genes_total": len(est.genes),
            "genes": [
                {"simbolo": eg.gen.simbolo, "origen": eg.origen.value}
                for eg in est.genes
            ],
        }
        for est in estudios
    ]


def obtener_genes_para_estudio(
    *,
    patologia_id: int,
    incluir_secundarios: bool = False,
    apigen_client: ApigenClient | None = None,
) -> dict:
    """Obtiene los genes de una patologia y opcionalmente los hallazgos secundarios."""
    patologia = clinica_repo.buscar_patologia_por_id(patologia_id)
    if patologia is None:
        raise ErrorDominio(
            "La patologia indicada no existe.",
            codigo="RECURSO_NO_ENCONTRADO",
            http_status=404,
        )

    cliente = apigen_client or ApigenClient(timeout=8.0)

    # 1. Genes de la patologia (Apigen con fallback local)
    genes_patologia: list[dict] = []
    try:
        simbolos = cliente.obtener_genes_por_patologia(patologia.nombre)
        genes_patologia = [{"simbolo": str(s).strip().upper(), "nombre": None} for s in simbolos if str(s).strip()]
    except ClienteError:
        genes_patologia = [
            {"simbolo": g.simbolo.upper(), "nombre": g.nombre}
            for g in patologia.genes
        ]

    # 2. Genes de hallazgos secundarios (si se solicitan)
    hallazgos_secundarios: list[dict] = []
    if incluir_secundarios:
        try:
            crudos = cliente.obtener_genes_hallazgos_secundarios()
            hallazgos_secundarios = [
                {
                    "simbolo": str(item.get("gen", "")).strip().upper(),
                    "nombre": item.get("condicion"),
                }
                for item in crudos
                if str(item.get("gen", "")).strip()
            ]
        except ClienteError:
            hallazgos_secundarios = [
                {"simbolo": g.simbolo.upper(), "nombre": g.nombre}
                for g in estudio_repo.listar_genes_hallazgos_secundarios()
            ]

    return {
        "patologia_id": patologia.id,
        "patologia_nombre": patologia.nombre,
        "genes_patologia": genes_patologia,
        "hallazgos_secundarios": hallazgos_secundarios,
    }


def buscar_genes_manuales(
    *,
    q: str,
    apigen_client: ApigenClient | None = None,
) -> list[dict]:
    """Busca simbolos de genes para agregado manual (minimo 2 caracteres)."""
    texto = (q or "").strip().upper()
    if len(texto) < 2:
        raise ErrorDominio(
            "Debe ingresar al menos 2 caracteres para buscar genes.",
            codigo="PREFIJO_GEN_CORTO",
            http_status=422,
        )

    cliente = apigen_client or ApigenClient(timeout=6.0)
    try:
        res = cliente.buscar_genes(texto, limite=20)
        return [
            {"simbolo": str(item["simbolo"]).strip().upper()}
            for item in res
            if item.get("simbolo")
        ]
    except ClienteError:
        locales = estudio_repo.buscar_genes_por_prefijo(texto, limite=20)
        return [{"simbolo": g.simbolo} for g in locales]


def dar_de_alta_estudio(
    *,
    usuario_actual_id: int,
    datos: dict,
    apigen_client: ApigenClient | None = None,
) -> dict:
    """Da de alta un Estudio en estado Creado asociando genes y hallazgos secundarios (E2)."""
    medico = paciente_repo.buscar_medico_por_usuario_id(usuario_actual_id)
    if medico is None:
        raise ErrorDominio(
            "Solo un medico tratante o gerente medico puede dar de alta estudios.",
            codigo="FORBIDDEN_ROLE",
            http_status=403,
        )

    paciente = paciente_repo.buscar_paciente_por_id(datos["paciente_id"])
    if paciente is None:
        raise ErrorDominio(
            "El paciente indicado no existe.",
            codigo="RECURSO_NO_ENCONTRADO",
            http_status=404,
        )

    patologia = clinica_repo.buscar_patologia_por_id(datos["patologia_sospechada_id"])
    if patologia is None:
        raise ErrorDominio(
            "La patologia sospechada no existe.",
            codigo="RECURSO_NO_ENCONTRADO",
            http_status=404,
        )

    obra_social_id = datos.get("obra_social_id")
    if obra_social_id is not None and estudio_repo.buscar_obra_social_por_id(obra_social_id) is None:
        raise ErrorDominio(
            "La obra social indicada no existe.",
            codigo="RECURSO_NO_ENCONTRADO",
            http_status=404,
        )

    quiere_secundarios = bool(datos.get("quiere_hallazgos_secundarios", False))
    genes_pat_input = [
        str(s).strip().upper()
        for s in (datos.get("genes_patologia_simbolos") or [])
        if str(s).strip()
    ]
    genes_man_input = [
        str(s).strip().upper()
        for s in (datos.get("genes_manuales_simbolos") or [])
        if str(s).strip()
    ]

    # Si no enviaron genes de patologia explicitamente ni manuales, consulta los de la patologia
    catalogo = obtener_genes_para_estudio(
        patologia_id=patologia.id,
        incluir_secundarios=quiere_secundarios,
        apigen_client=apigen_client,
    )
    if not genes_pat_input and not genes_man_input:
        genes_pat_input = [g["simbolo"] for g in catalogo["genes_patologia"]]

    # Clasifica origen evitando duplicados (prioridad: PATOLOGIA > MANUAL > HALLAZGO_SECUNDARIO)
    origen_por_simbolo: dict[str, OrigenGen] = {}
    info_upsert: list[dict] = []

    for sim in genes_pat_input:
        if sim not in origen_por_simbolo:
            origen_por_simbolo[sim] = OrigenGen.PATOLOGIA
            info_upsert.append({"simbolo": sim, "es_hallazgo_secundario": False})

    for sim in genes_man_input:
        if sim not in origen_por_simbolo:
            origen_por_simbolo[sim] = OrigenGen.MANUAL
            info_upsert.append({"simbolo": sim, "es_hallazgo_secundario": False})

    if quiere_secundarios:
        for item in catalogo["hallazgos_secundarios"]:
            sim = item["simbolo"]
            if sim not in origen_por_simbolo:
                origen_por_simbolo[sim] = OrigenGen.HALLAZGO_SECUNDARIO
                info_upsert.append(
                    {
                        "simbolo": sim,
                        "nombre": item.get("nombre"),
                        "es_hallazgo_secundario": True,
                    }
                )

    if not origen_por_simbolo:
        raise ErrorDominio(
            "Debe seleccionar al menos un gen para analizar en el estudio.",
            codigo="LISTA_GENES_VACIA",
            http_status=422,
        )

    mapa_genes = estudio_repo.upsert_genes(info_upsert)
    genes_con_origen = [
        (mapa_genes[sim], origen)
        for sim, origen in origen_por_simbolo.items()
        if sim in mapa_genes
    ]

    pompe_urgente = _es_pompe_urgente(patologia.nombre, paciente.fecha_nacimiento)

    estudio = estudio_repo.crear_estudio_completo(
        paciente_id=paciente.id,
        paciente_usuario_id=paciente.usuario_id,
        medico_id=medico.id,
        patologia_sospechada_id=patologia.id,
        quiere_hallazgos_secundarios=quiere_secundarios,
        obra_social_id=obra_social_id,
        es_pompe_urgente=pompe_urgente,
        genes_con_origen=genes_con_origen,
    )

    return {
        "estudio_id": estudio.id,
        "paciente_id": estudio.paciente_id,
        "medico_id": estudio.medico_id,
        "patologia_sospechada_id": estudio.patologia_sospechada_id,
        "estado": estudio.estado.value,
        "quiere_hallazgos_secundarios": estudio.quiere_hallazgos_secundarios,
        "obra_social_id": estudio.obra_social_id,
        "es_pompe_urgente": estudio.es_pompe_urgente,
        "cantidad_genes_total": len(genes_con_origen),
        "genes": [
            {"simbolo": gen.simbolo, "origen": origen.value}
            for gen, origen in genes_con_origen
        ],
    }