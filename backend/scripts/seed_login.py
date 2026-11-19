"""Script idempotente para cargar en la BD los casos de prueba de inicio de sesion."""
from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import delete, select
from src import create_app
from src.core.database import create_tables, db
from src.core.models import (
    CodigoVerificacion,
    DispositivoConocido,
    Medico,
    Paciente,
    Patologia,
    Rol,
    Usuario,
)
from src.core.services.seguridad import hashear_password, sha256_hex

PASSWORD_PRUEBA = "Clave1234"

CASOS_USUARIOS: list[dict] = [
    {
        "email": "juanescudero328@gmail.com",
        "rol": Rol.MEDICO,
        "nombre": "Juan",
        "apellido": "Escudero",
        "telefono": "2215000001",
        "debe_cambiar_password": False,
        "dispositivos_conocidos": ["pc-consultorio"],
        "caso": "Maquina conocida -> AUTENTICADO (medico)",
    },
    {
        "email": "juanescudero074@gmail.com",
        "rol": Rol.PACIENTE,
        "nombre": "Juan",
        "apellido": "Escudero",
        "telefono": "2215000002",
        "debe_cambiar_password": True,
        "dispositivos_conocidos": [],
        "caso": "Primer ingreso -> REQUIERE_CAMBIO_PASSWORD_INICIAL (paciente)",
    },
    {
        "email": "ariadnaguarino@yahoo.com",
        "rol": Rol.BIOINFORMATICO,
        "nombre": "Ariadna",
        "apellido": "Guarino",
        "telefono": "2215000003",
        "debe_cambiar_password": False,
        "dispositivos_conocidos": [],
        "caso": "Maquina nueva -> REQUIERE_VERIFICACION_DISPOSITIVO (bioinformatico)",
    },
    {
        "email": "facundotaddei24@gmail.com",
        "rol": Rol.ADMIN_GENERAL,
        "nombre": "Facundo",
        "apellido": "Taddei",
        "telefono": "2215000004",
        "debe_cambiar_password": False,
        "dispositivos_conocidos": ["pc-oficina"],
        "caso": "Maquina conocida -> AUTENTICADO (admin_general)",
    },
]


def _ahora_utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _obtener_o_crear_patologia_base() -> Patologia:
    patologia = db.session.scalar(
        select(Patologia).where(Patologia.nombre == "Enfermedad de Fabry")
    )
    if patologia is None:
        patologia = Patologia(
            nombre="Enfermedad de Fabry",
            descripcion="Patologia lisosomal de almacenamiento (dato semilla para pruebas).",
        )
        db.session.add(patologia)
        db.session.flush()
    return patologia


def _asegurar_usuario(datos: dict) -> Usuario:
    email_norm = datos["email"].strip().lower()
    usuario = db.session.scalar(select(Usuario).where(Usuario.email == email_norm))
    password_hash = hashear_password(PASSWORD_PRUEBA)

    if usuario is None:
        usuario = Usuario(
            email=email_norm,
            password_hash=password_hash,
            rol=datos["rol"],
            nombre=datos["nombre"],
            apellido=datos["apellido"],
            telefono=datos["telefono"],
            debe_cambiar_password=datos["debe_cambiar_password"],
        )
        db.session.add(usuario)
        db.session.flush()
    else:
        usuario.password_hash = password_hash
        usuario.rol = datos["rol"]
        usuario.nombre = datos["nombre"]
        usuario.apellido = datos["apellido"]
        usuario.telefono = datos["telefono"]
        usuario.debe_cambiar_password = datos["debe_cambiar_password"]

    # Reinicia dispositivos y codigos de verificacion para dejar el caso exacto listo para probar
    db.session.execute(
        delete(DispositivoConocido).where(DispositivoConocido.usuario_id == usuario.id)
    )
    db.session.execute(
        delete(CodigoVerificacion).where(CodigoVerificacion.usuario_id == usuario.id)
    )

    for dispositivo_id in datos["dispositivos_conocidos"]:
        db.session.add(
            DispositivoConocido(
                usuario_id=usuario.id,
                identificador=sha256_hex(dispositivo_id),
                ultimo_acceso=_ahora_utc_naive(),
            )
        )

    return usuario


def _asegurar_perfil_medico(usuario: Usuario, matricula: str) -> Medico:
    medico = db.session.scalar(select(Medico).where(Medico.usuario_id == usuario.id))
    if medico is None:
        medico = Medico(usuario_id=usuario.id, matricula=matricula)
        db.session.add(medico)
        db.session.flush()
    return medico


def _asegurar_perfil_paciente(
    usuario: Usuario,
    medico: Medico,
    patologia: Patologia,
    dni: str,
) -> Paciente:
    paciente = db.session.scalar(select(Paciente).where(Paciente.usuario_id == usuario.id))
    if paciente is None:
        paciente = Paciente(
            usuario_id=usuario.id,
            medico_id=medico.id,
            dni=dni,
            fecha_nacimiento=date(1995, 5, 15),
            diagnostico_presuntivo_id=patologia.id,
            historia_clinica="Paciente de prueba para escenario de primer ingreso.",
            tipo_sospecha="clinica",
        )
        db.session.add(paciente)
        db.session.flush()
    else:
        paciente.medico_id = medico.id
        paciente.diagnostico_presuntivo_id = patologia.id
    return paciente


def cargar_casos_login() -> list[dict]:
    """Crea o actualiza en la base de datos los 4 usuarios para probar todos los casos de login."""
    app = create_app()
    resumen: list[dict] = []

    with app.app_context():
        create_tables()
        patologia = _obtener_o_crear_patologia_base()

        usuarios_por_email: dict[str, Usuario] = {}
        for datos in CASOS_USUARIOS:
            usuario = _asegurar_usuario(datos)
            usuarios_por_email[usuario.email] = usuario
            resumen.append(
                {
                    "id": usuario.id,
                    "email": usuario.email,
                    "rol": usuario.rol.value,
                    "debe_cambiar_password": usuario.debe_cambiar_password,
                    "dispositivos_conocidos": datos["dispositivos_conocidos"],
                    "caso": datos["caso"],
                }
            )

        medico_juan = _asegurar_perfil_medico(
            usuarios_por_email["juanescudero328@gmail.com"],
            matricula="MN-10001",
        )
        _asegurar_perfil_paciente(
            usuarios_por_email["juanescudero074@gmail.com"],
            medico=medico_juan,
            patologia=patologia,
            dni="38111222",
        )

        db.session.commit()

    return resumen


if __name__ == "__main__":
    filas = cargar_casos_login()
    print("Casos de inicio de sesion cargados en BD (password:", PASSWORD_PRUEBA, "):")
    for fila in filas:
        print(
            f" - id={fila['id']} | {fila['email']} | rol={fila['rol']} | "
            f"debe_cambiar_password={fila['debe_cambiar_password']} | "
            f"dispositivos={fila['dispositivos_conocidos']} | {fila['caso']}"
        )
