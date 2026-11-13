"""Repositorio de acceso a datos de usuario y seguridad de acceso"""
from datetime import UTC, datetime

from sqlalchemy import select, update
from src.core.database import db
from src.core.models import CodigoVerificacion, DispositivoConocido, Usuario


def ahora_utc():
    return datetime.now(UTC).replace(tzinfo=None)

def buscar_por_email(email:str) -> Usuario | None:
    stmt = select(Usuario).where(Usuario.email == email)
    return db.session.scalar(stmt)

def buscar_dispositivo(usuario_id: int, identificador_hash:str) -> DispositivoConocido | None:
    stmt = select(DispositivoConocido).where(
        DispositivoConocido.usuario_id == usuario_id,
        DispositivoConocido.identificador == identificador_hash
    )
    return db.session.scalar(stmt)

def actualizar_ultimo_acceso(dispositivo: DispositivoConocido) -> None:
    dispositivo.ultimo_acceso = ahora_utc()

def crear_codigo_verificacion(
    usuario_id: int,
    codigo_hash: str,
    dispositivo_hash: str,
    expira_en: datetime,
) -> CodigoVerificacion:
    #Invalida codigos previos sin usar de esa misma maquina para que solo valga el ultimo
    db.session.execute(
        update(CodigoVerificacion)
        .where(
            CodigoVerificacion.usuario_id == usuario_id,
            CodigoVerificacion.dispositivo_identificador == dispositivo_hash,
            CodigoVerificacion.usado.is_(False),
        )
        .values(usado=True)
    )
    codigo = CodigoVerificacion(
        usuario_id=usuario_id,
        codigo_hash=codigo_hash,
        dispositivo_identificador=dispositivo_hash,
        expira_en=expira_en,
        usado=False
    )
    db.session.add(codigo)
    return codigo
