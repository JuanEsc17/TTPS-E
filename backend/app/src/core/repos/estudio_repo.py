"""Repositorio de acceso a datos para estudios de exoma y genes."""
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload
from src.core.database import db
from src.core.models import (
    Aviso,
    CanalAviso,
    EstadoEstudio,
    Estudio,
    EstudioGen,
    Gen,
    ObraSocial,
    OrigenGen,
    Paciente,
    Rol,
    Usuario,
)
from src.core.services.excepciones import ErrorDominio


def listar_estudios_por_medico(medico_id: int) -> list[Estudio]:
    """Lista los estudios solicitados por un medico."""
    stmt = (
        select(Estudio)
        .options(
            selectinload(Estudio.paciente).selectinload(Paciente.usuario),
            selectinload(Estudio.patologia_sospechada),
            selectinload(Estudio.obra_social),
            selectinload(Estudio.genes).selectinload(EstudioGen.gen),
        )
        .where(Estudio.medico_id == medico_id)
        .order_by(Estudio.id.desc())
    )
    return list(db.session.scalars(stmt).all())


def listar_obras_sociales() -> list[ObraSocial]:
    """Devuelve el catalogo de obras sociales ordenado alfabeticamente."""
    stmt = select(ObraSocial).order_by(ObraSocial.nombre.asc())
    return list(db.session.scalars(stmt).all())


def buscar_obra_social_por_id(obra_social_id: int) -> ObraSocial | None:
    """Busca una obra social por ID."""
    stmt = select(ObraSocial).where(ObraSocial.id == obra_social_id)
    return db.session.scalar(stmt)


def buscar_genes_por_prefijo(prefijo: str, limite: int = 20) -> list[Gen]:
    """Fallback local para buscar genes por simbolo."""
    stmt = (
        select(Gen)
        .where(Gen.simbolo.ilike(f"{prefijo}%"))
        .order_by(Gen.simbolo.asc())
        .limit(limite)
    )
    return list(db.session.scalars(stmt).all())


def listar_genes_hallazgos_secundarios() -> list[Gen]:
    """Fallback local de genes marcados como hallazgo secundario."""
    stmt = select(Gen).where(Gen.es_hallazgo_secundario.is_(True)).order_by(Gen.simbolo.asc())
    return list(db.session.scalars(stmt).all())


def upsert_genes(genes_info: list[dict]) -> dict[str, Gen]:
    """Asegura que cada simbolo de gen exista en la tabla `genes`."""
    simbolos = list(
        dict.fromkeys(
            str(g["simbolo"]).strip().upper()
            for g in genes_info
            if str(g.get("simbolo", "")).strip()
        )
    )
    if not simbolos:
        return {}

    existentes = {
        g.simbolo.upper(): g
        for g in db.session.scalars(select(Gen).where(Gen.simbolo.in_(simbolos))).all()
    }

    for info in genes_info:
        simbolo = str(info.get("simbolo", "")).strip().upper()
        if not simbolo:
            continue
        if simbolo not in existentes:
            nuevo = Gen(
                simbolo=simbolo[:30],
                nombre=str(info["nombre"])[:255] if info.get("nombre") else None,
                es_hallazgo_secundario=bool(info.get("es_hallazgo_secundario", False)),
            )
            db.session.add(nuevo)
            existentes[simbolo] = nuevo

    db.session.flush()
    return existentes


def listar_usuarios_por_rol(rol: Rol) -> list[Usuario]:
    """Devuelve los usuarios activos de un rol dado."""
    stmt = select(Usuario).where(Usuario.rol == rol)
    return list(db.session.scalars(stmt).all())


def crear_estudio_completo(
    *,
    paciente_id: int,
    paciente_usuario_id: int,
    medico_id: int,
    patologia_sospechada_id: int,
    quiere_hallazgos_secundarios: bool,
    obra_social_id: int | None,
    es_pompe_urgente: bool,
    genes_con_origen: list[tuple[Gen, OrigenGen]],
) -> Estudio:
    """Crea Estudio en estado Creado, sus EstudioGen y los Avisos correspondientes."""
    try:
        estudio = Estudio(
            paciente_id=paciente_id,
            medico_id=medico_id,
            patologia_sospechada_id=patologia_sospechada_id,
            estado=EstadoEstudio.CREADO,
            quiere_hallazgos_secundarios=quiere_hallazgos_secundarios,
            obra_social_id=obra_social_id,
            es_pompe_urgente=es_pompe_urgente,
            ausencias=0,
        )
        db.session.add(estudio)
        db.session.flush()

        for gen, origen in genes_con_origen:
            db.session.add(
                EstudioGen(
                    estudio_id=estudio.id,
                    gen_id=gen.id,
                    origen=origen,
                )
            )

        # Avisa a administrativos para emitir presupuesto (E3) y al paciente
        admins = listar_usuarios_por_rol(Rol.ADMINISTRATIVO)
        for admin in admins:
            db.session.add(
                Aviso(
                    usuario_id=admin.id,
                    mensaje=(
                        f"Nuevo estudio #{estudio.id} dado de alta ({len(genes_con_origen)} genes). "
                        "Pendiente emitir presupuesto."
                    ),
                    leido=False,
                    canal=CanalAviso.APP,
                    enviado=True,
                )
            )

        db.session.add(
            Aviso(
                usuario_id=paciente_usuario_id,
                mensaje=f"Se solicito un estudio de exoma clinico (#{estudio.id}).",
                leido=False,
                canal=CanalAviso.APP,
                enviado=True,
            )
        )

        db.session.commit()
        return estudio
    except SQLAlchemyError as exc:
        db.session.rollback()
        raise ErrorDominio(
            "Error temporal al registrar el estudio. Intente nuevamente.",
            codigo="ERROR_BASE_DATOS",
            http_status=503,
            reintentable=True,
        ) from exc