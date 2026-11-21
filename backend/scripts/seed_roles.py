"""Script idempotente para crear o actualizar en la BD un usuario por cada rol."""
from __future__ import annotations

from datetime import UTC, date, datetime
from src.core.models import Especialidad 
from sqlalchemy import select
from src import create_app
from src.core.database import create_tables, db
from src.core.models import (
    DispositivoConocido,
    Medico,
    Paciente,
    Patologia,
    Rol,
    Transportista,
    Usuario,
)
from src.core.services.seguridad import hashear_password, sha256_hex

ESPECIALIDAD_BASE = "Genética Médica"

PASSWORD_PRUEBA = "Clave1234"
DISPOSITIVOS_POR_DEFECTO = ("pc-lab", "pc-oficina")

USUARIOS_POR_ROL: list[dict] = [
    {
        "email": "admin@lab.com",
        "rol": Rol.ADMIN_GENERAL,
        "nombre": "Admin",
        "apellido": "General",
        "telefono": "2215100001",
    },
    {
        "email": "administrativo@lab.com",
        "rol": Rol.ADMINISTRATIVO,
        "nombre": "Personal",
        "apellido": "Administrativo",
        "telefono": "2215100002",
    },
    {
        "email": "medico@lab.com",
        "rol": Rol.MEDICO,
        "nombre": "Medico",
        "apellido": "Lab",
        "telefono": "2215100003",
        "matricula": "MN-20001",
    },
    {
        "email": "gerente@lab.com",
        "rol": Rol.GERENTE_MEDICO,
        "nombre": "Gerente",
        "apellido": "Medico",
        "telefono": "2215100004",
        "matricula": "MN-20002",
    },
    {
        "email": "bioinformatico@lab.com",
        "rol": Rol.BIOINFORMATICO,
        "nombre": "Equipo",
        "apellido": "Bioinformatico",
        "telefono": "2215100005",
    },
    {
        "email": "transportista@lab.com",
        "rol": Rol.TRANSPORTISTA,
        "nombre": "Transportista",
        "apellido": "Lab",
        "telefono": "2215100006",
        "provincia": "Buenos Aires",
    },
    {
        "email": "paciente@lab.com",
        "rol": Rol.PACIENTE,
        "nombre": "Paciente",
        "apellido": "Lab",
        "telefono": "2215100007",
        "dni": "40111222",
    },
]

assert {u["rol"] for u in USUARIOS_POR_ROL} == set(Rol)


def _ahora_utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _obtener_o_crear_patologia_base() -> Patologia:
    patologia = db.session.scalar(
        select(Patologia).where(Patologia.nombre == "Enfermedad de Fabry")
    )
    if patologia is None:
        patologia = db.session.scalar(select(Patologia).order_by(Patologia.id.asc()))
    if patologia is None:
        patologia = Patologia(
            nombre="Enfermedad de Fabry",
            descripcion="Patologia lisosomal de almacenamiento (dato semilla para pruebas).",
        )
        db.session.add(patologia)
        db.session.flush()
    return patologia


def _asegurar_usuario(datos: dict, hashes_dispositivos: set[str]) -> Usuario:
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
            debe_cambiar_password=False,
        )
        db.session.add(usuario)
        db.session.flush()
    else:
        usuario.password_hash = password_hash
        usuario.rol = datos["rol"]
        usuario.nombre = datos["nombre"]
        usuario.apellido = datos["apellido"]
        usuario.telefono = datos["telefono"]
        usuario.debe_cambiar_password = False

    existentes = set(
        db.session.scalars(
            select(DispositivoConocido.identificador).where(
                DispositivoConocido.usuario_id == usuario.id
            )
        ).all()
    )
    ahora = _ahora_utc_naive()
    for identificador_hash in sorted(hashes_dispositivos - existentes):
        db.session.add(
            DispositivoConocido(
                usuario_id=usuario.id,
                identificador=identificador_hash,
                ultimo_acceso=ahora,
            )
        )

    return usuario


def _asegurar_perfil_medico(usuario: Usuario, matricula: str) -> Medico:
    medico = db.session.scalar(select(Medico).where(Medico.usuario_id == usuario.id))
    if medico is None:
        ocupada = db.session.scalar(select(Medico).where(Medico.matricula == matricula))
        matricula_final = matricula if ocupada is None else f"MN-{20000 + usuario.id}"
        medico = Medico(usuario_id=usuario.id, matricula=matricula_final)
        db.session.add(medico)
        db.session.flush()
    return medico


def _asegurar_perfil_transportista(usuario: Usuario, provincia: str) -> Transportista:
    transportista = db.session.scalar(
        select(Transportista).where(Transportista.usuario_id == usuario.id)
    )
    if transportista is None:
        ocupada = db.session.scalar(
            select(Transportista).where(Transportista.provincia == provincia)
        )
        provincia_final = provincia if ocupada is None else f"{provincia} ({usuario.id})"
        transportista = Transportista(usuario_id=usuario.id, provincia=provincia_final)
        db.session.add(transportista)
        db.session.flush()
    return transportista


def _asegurar_perfil_paciente(
    usuario: Usuario,
    medico: Medico,
    patologia: Patologia,
    dni: str,
) -> Paciente:
    paciente = db.session.scalar(select(Paciente).where(Paciente.usuario_id == usuario.id))
    if paciente is None:
        ocupado = db.session.scalar(select(Paciente).where(Paciente.dni == dni))
        dni_final = dni if ocupado is None else str(40_000_000 + usuario.id)
        paciente = Paciente(
            usuario_id=usuario.id,
            medico_id=medico.id,
            dni=dni_final,
            fecha_nacimiento=date(1995, 5, 15),
            diagnostico_presuntivo_id=patologia.id,
            historia_clinica="Paciente de prueba creado para testing de roles.",
            tipo_sospecha="clinica",
        )
        db.session.add(paciente)
        db.session.flush()
    return paciente


def cargar_usuarios_por_rol() -> list[dict]:
    """Crea o actualiza en la base de datos un usuario completo por cada rol del sistema."""
    app = create_app()
    resumen: list[dict] = []

    with app.app_context():
        create_tables()
        patologia = _obtener_o_crear_patologia_base()

        # Incluye dispositivos ya verificados en la BD para permitir login directo con correos ficticios @lab.com
        hashes_dispositivos = {sha256_hex(d) for d in DISPOSITIVOS_POR_DEFECTO}
        hashes_dispositivos.update(
            db.session.scalars(select(DispositivoConocido.identificador).distinct()).all()
        )

        usuarios_por_email: dict[str, Usuario] = {}
        medicos_por_email: dict[str, Medico] = {}

        for datos in USUARIOS_POR_ROL:
            usuario = _asegurar_usuario(datos, hashes_dispositivos)
            usuarios_por_email[usuario.email] = usuario

            if datos["rol"] in (Rol.MEDICO, Rol.GERENTE_MEDICO):
                medicos_por_email[usuario.email] = _asegurar_perfil_medico(
                    usuario,
                    matricula=datos["matricula"],
                )
            elif datos["rol"] == Rol.TRANSPORTISTA:
                _asegurar_perfil_transportista(usuario, provincia=datos["provincia"])

            resumen.append(
                {
                    "id": usuario.id,
                    "email": usuario.email,
                    "rol": usuario.rol.value,
                }
            )

        _asegurar_perfil_paciente(
            usuarios_por_email["paciente@lab.com"],
            medico=medicos_por_email["medico@lab.com"],
            patologia=patologia,
            dni="40111222",
        )

        especialidad = _obtener_o_crear_especialidad()
        for medico in medicos_por_email.values():
            if especialidad not in medico.especialidades:
                medico.especialidades.append(especialidad)

        db.session.commit()

    return resumen
def _obtener_o_crear_especialidad(nombre: str = ESPECIALIDAD_BASE) -> Especialidad:
    especialidad = db.session.scalar(
        select(Especialidad).where(Especialidad.nombre == nombre)
    )
    if especialidad is None:
        especialidad = Especialidad(nombre=nombre)
        db.session.add(especialidad)
        db.session.flush()
    return especialidad

if __name__ == "__main__":
    filas = cargar_usuarios_por_rol()
    print(f"Usuarios por rol cargados en BD (password: {PASSWORD_PRUEBA}):")
    for fila in filas:
        print(f" - id={fila['id']} | {fila['email']} | rol={fila['rol']}")
