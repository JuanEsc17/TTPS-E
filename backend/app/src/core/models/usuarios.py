"""Usuarios, seguridad de acceso y avisos."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from .enums import CanalAviso, Rol

if TYPE_CHECKING:
    from .perfiles import Medico, Paciente, Transportista


class Usuario(TimestampMixin, Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    rol: Mapped[Rol] = mapped_column(Enum(Rol), index=True)
    nombre: Mapped[str] = mapped_column(String(100))
    apellido: Mapped[str] = mapped_column(String(100))
    telefono: Mapped[str] = mapped_column(String(30))
    # True hasta que el paciente cambia la contrasena inicial (escenario 20)
    debe_cambiar_password: Mapped[bool] = mapped_column(Boolean, default=False)

    paciente: Mapped[Paciente | None] = relationship(back_populates="usuario", uselist=False)
    medico: Mapped[Medico | None] = relationship(back_populates="usuario", uselist=False)
    transportista: Mapped[Transportista | None] = relationship(back_populates="usuario", uselist=False)
    dispositivos: Mapped[list[DispositivoConocido]] = relationship(back_populates="usuario", cascade="all, delete-orphan")
    codigos_verificacion: Mapped[list[CodigoVerificacion]] = relationship(back_populates="usuario", cascade="all, delete-orphan")
    avisos: Mapped[list[Aviso]] = relationship(back_populates="usuario", cascade="all, delete-orphan")


class DispositivoConocido(Base):
    """Maquinas desde las que el usuario ya ingreso (escenarios 26 y 27)."""
    __tablename__ = "dispositivos_conocidos"
    __table_args__ = (UniqueConstraint("usuario_id", "identificador"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"))
    identificador: Mapped[str] = mapped_column(String(255))   # hash de huella / cookie de dispositivo
    ultimo_acceso: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    usuario: Mapped[Usuario] = relationship(back_populates="dispositivos")


class CodigoVerificacion(Base):
    __tablename__ = "codigos_verificacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"))
    codigo_hash: Mapped[str] = mapped_column(String(255))
    dispositivo_identificador: Mapped[str] = mapped_column(String(255))
    expira_en: Mapped[datetime] = mapped_column(DateTime)
    usado: Mapped[bool] = mapped_column(Boolean, default=False)

    usuario: Mapped[Usuario] = relationship(back_populates="codigos_verificacion")


class Aviso(Base):
    """Notificacion dentro del sistema (ademas del mail)."""
    __tablename__ = "avisos"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    mensaje: Mapped[str] = mapped_column(String(500))
    leido: Mapped[bool] = mapped_column(Boolean, default=False)
    canal: Mapped[CanalAviso] = mapped_column(Enum(CanalAviso), default=CanalAviso.APP)
    enviado: Mapped[bool] = mapped_column(Boolean, default=False)           # entregado por el modulo de avisos
    enviado_en: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    usuario: Mapped[Usuario] = relationship(back_populates="avisos")
