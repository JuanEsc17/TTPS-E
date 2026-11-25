"""Repositorio de acceso a datos para estudios de exoma y genes."""
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload
from src.core.database import db
from src.core.models import (
    Aviso,
    CanalAviso,
    EntidadAuditable,
    EstadoEstudio,
    Estudio,
    EstudioFamiliarVinculado,
    EstudioGen,
    Familiar,
    Gen,
    ObraSocial,
    OrigenGen,
    Paciente,
    Rol,
    TipoAccionAuditoria,
    Usuario,
)
from src.core.services import auditoria_service
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

def buscar_estudio_por_id(estudio_id: int) -> Estudio | None:
    """Obtiene un estudio con paciente, patologia, genes y analisis."""
    stmt = (
        select(Estudio)
        .options(
            selectinload(Estudio.paciente).selectinload(Paciente.usuario),
            selectinload(Estudio.patologia_sospechada),
            selectinload(Estudio.genes).selectinload(EstudioGen.gen),
            selectinload(Estudio.analisis),
        )
        .where(Estudio.id == estudio_id)
    )
    return db.session.scalar(stmt)


def listar_estudios_de_paciente(paciente_id: int) -> list[Estudio]:
    """Devuelve todos los estudios de un paciente."""
    stmt = (
        select(Estudio)
        .options(selectinload(Estudio.medico))
        .where(Estudio.paciente_id == paciente_id)
        .order_by(Estudio.id.asc())
    )
    return list(db.session.scalars(stmt).all())


def buscar_coincidencias_familiares(paciente: Paciente) -> list[tuple[Familiar, int, int]]:
    """
    Detecta coincidencias bidireccionales por DNI / paciente_vinculado_id.
    Retorna lista de (familiar, paciente_duenio_familiograma_id, paciente_familiar_id).
    """
    coincidencias: list[tuple[Familiar, int, int]] = []
    dni_norm = (paciente.dni or "").strip()

    # Direccion 1: este paciente figura como Familiar en familiogramas ajenos
    condiciones = [Familiar.paciente_vinculado_id == paciente.id]
    if dni_norm:
        condiciones.append(Familiar.dni == dni_norm)

    fams_ajenos = list(
        db.session.scalars(
            select(Familiar).where(
                or_(*condiciones),
                Familiar.paciente_id != paciente.id,
            )
        ).all()
    )
    for fam in fams_ajenos:
        if fam.paciente_vinculado_id is None:
            fam.paciente_vinculado_id = paciente.id
        coincidencias.append((fam, fam.paciente_id, paciente.id))

    # Direccion 2: familiares propios cuyo DNI coincide con otro Paciente
    fams_propios = list(
        db.session.scalars(select(Familiar).where(Familiar.paciente_id == paciente.id)).all()
    )
    for fam in fams_propios:
        pac_rel_id = fam.paciente_vinculado_id
        if pac_rel_id is None and fam.dni:
            otro = db.session.scalar(
                select(Paciente).where(
                    Paciente.dni == fam.dni.strip(),
                    Paciente.id != paciente.id,
                )
            )
            if otro is not None:
                fam.paciente_vinculado_id = otro.id
                pac_rel_id = otro.id
        if pac_rel_id is not None and pac_rel_id != paciente.id:
            coincidencias.append((fam, paciente.id, pac_rel_id))

    db.session.flush()
    return coincidencias


def crear_vinculo_bidireccional_si_no_existe(
    *,
    estudio_a: Estudio,
    estudio_b: Estudio,
    familiar: Familiar,
    parentesco_a_b: str,
    parentesco_b_a: str,
    usuario_actor_id: int | None,
) -> bool:
    """Crea (A->B) y (B->A) de forma idempotente y audita los vinculos nuevos."""
    if estudio_a.id == estudio_b.id:
        return False

    existe = db.session.scalar(
        select(EstudioFamiliarVinculado).where(
            EstudioFamiliarVinculado.estudio_origen_id == estudio_a.id,
            EstudioFamiliarVinculado.estudio_relacionado_id == estudio_b.id,
        )
    )
    if existe is not None:
        return False

    db.session.add_all(
        [
            EstudioFamiliarVinculado(
                estudio_origen_id=estudio_a.id,
                estudio_relacionado_id=estudio_b.id,
                familiar_id=familiar.id,
                parentesco=parentesco_a_b[:80],
            ),
            EstudioFamiliarVinculado(
                estudio_origen_id=estudio_b.id,
                estudio_relacionado_id=estudio_a.id,
                familiar_id=familiar.id,
                parentesco=parentesco_b_a[:80],
            ),
        ]
    )

    for origen_id, rel_id, par in (
        (estudio_a.id, estudio_b.id, parentesco_a_b),
        (estudio_b.id, estudio_a.id, parentesco_b_a),
    ):
        auditoria_service.registrar_modificacion(
            entidad_tipo=EntidadAuditable.ESTUDIO,
            entidad_id=origen_id,
            accion=TipoAccionAuditoria.MODIFICACION,
            cambios={
                "vinculo_familiar_agregado": {
                    "anterior": None,
                    "nuevo": {
                        "estudio_relacionado_id": rel_id,
                        "parentesco": par,
                        "familiar_id": familiar.id,
                    },
                }
            },
            usuario_id=usuario_actor_id,
            motivo="Vinculacion automatica por familiograma (Escenario 41)",
        )

    # Avisa a los medicos tratantes de ambos estudios
    db.session.add_all(
        [
            Aviso(
                usuario_id=estudio_a.medico.usuario_id,
                mensaje=(
                    f"Se vinculo automaticamente el estudio #{estudio_b.id} de un familiar "
                    f"con el estudio #{estudio_a.id}."
                ),
                leido=False,
                canal=CanalAviso.APP,
                enviado=True,
            ),
            Aviso(
                usuario_id=estudio_b.medico.usuario_id,
                mensaje=(
                    f"Se vinculo automaticamente el estudio #{estudio_a.id} de un familiar "
                    f"con el estudio #{estudio_b.id}."
                ),
                leido=False,
                canal=CanalAviso.APP,
                enviado=True,
            ),
        ]
    )
    return True


def listar_vinculos_estudio(estudio_id: int) -> list[EstudioFamiliarVinculado]:
    """Lista los vinculos familiares de un estudio."""
    stmt = (
        select(EstudioFamiliarVinculado)
        .options(
            selectinload(EstudioFamiliarVinculado.estudio_relacionado).selectinload(Estudio.paciente).selectinload(Paciente.usuario),
            selectinload(EstudioFamiliarVinculado.estudio_relacionado).selectinload(Estudio.patologia_sospechada),
            selectinload(EstudioFamiliarVinculado.estudio_relacionado).selectinload(Estudio.analisis),
        )
        .where(EstudioFamiliarVinculado.estudio_origen_id == estudio_id)
        .order_by(EstudioFamiliarVinculado.id.asc())
    )
    return list(db.session.scalars(stmt).all())


def buscar_vinculo_estudio(
    estudio_origen_id: int,
    estudio_relacionado_id: int,
) -> EstudioFamiliarVinculado | None:
    """Verifica si existe vinculo familiar entre dos estudios."""
    stmt = (
        select(EstudioFamiliarVinculado)
        .where(
            EstudioFamiliarVinculado.estudio_origen_id == estudio_origen_id,
            EstudioFamiliarVinculado.estudio_relacionado_id == estudio_relacionado_id,
        )
    )
    return db.session.scalar(stmt)