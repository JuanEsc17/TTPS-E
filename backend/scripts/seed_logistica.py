"""Script idempotente para cargar un transportista y 4 centros con muestras listas (Escenario 11)."""
from __future__ import annotations

import argparse
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select
from src import create_app
from src.core.database import create_tables, db
from src.core.models import (
    CentroExtraccion,
    DispositivoConocido,
    EstadoEstudio,
    Estudio,
    Medico,
    Muestra,
    OrdenDelDia,
    Paciente,
    Patologia,
    Rol,
    Transportista,
    Turno,
    Usuario,
)
from src.core.services.seguridad import hashear_password, sha256_hex

PASSWORD_DEFAULT = "Clave1234"
EMAIL_TRANSPORTISTA_DEFAULT = "transportista.ba@exoma.test"
PROVINCIA_DEFAULT = "Buenos Aires"

CENTROS_SEED: list[dict] = [
    {
        "nombre": "Centro Extraccion La Plata",
        "direccion": "Calle 7 Nro 850, La Plata",
        "provincia": PROVINCIA_DEFAULT,
        "latitud": -34.9152,
        "longitud": -57.9479,
        "paciente_email": "paciente.log1@exoma.test",
        "paciente_nombre": "Lucia",
        "paciente_apellido": "Fernandez",
        "dni": "40100001",
    },
    {
        "nombre": "Laboratorio Quilmes Sur",
        "direccion": "Av. Hipolito Yrigoyen 420, Quilmes",
        "provincia": PROVINCIA_DEFAULT,
        "latitud": -34.7203,
        "longitud": -58.2546,
        "paciente_email": "paciente.log2@exoma.test",
        "paciente_nombre": "Tomas",
        "paciente_apellido": "Benitez",
        "dni": "40100002",
    },
    {
        "nombre": "Sede Avellaneda Centro",
        "direccion": "Av. Mitre 780, Avellaneda",
        "provincia": PROVINCIA_DEFAULT,
        "latitud": -34.6615,
        "longitud": -58.3647,
        "paciente_email": "paciente.log3@exoma.test",
        "paciente_nombre": "Camila",
        "paciente_apellido": "Rojas",
        "dni": "40100003",
    },
    {
        "nombre": "Centro Norte Palermo",
        "direccion": "Av. Santa Fe 3450, CABA",
        "provincia": PROVINCIA_DEFAULT,
        "latitud": -34.5885,
        "longitud": -58.4105,
        "paciente_email": "paciente.log4@exoma.test",
        "paciente_nombre": "Mateo",
        "paciente_apellido": "Sosa",
        "dni": "40100004",
    },
]


def _ahora_utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _asegurar_usuario(
    *,
    email: str,
    password: str,
    rol: Rol,
    nombre: str,
    apellido: str,
    telefono: str,
) -> Usuario:
    email_norm = email.strip().lower()
    usuario = db.session.scalar(select(Usuario).where(Usuario.email == email_norm))
    password_hash = hashear_password(password)
    if usuario is None:
        usuario = Usuario(
            email=email_norm,
            password_hash=password_hash,
            rol=rol,
            nombre=nombre,
            apellido=apellido,
            telefono=telefono,
            debe_cambiar_password=False,
        )
        db.session.add(usuario)
        db.session.flush()
    else:
        usuario.password_hash = password_hash
        usuario.rol = rol
        usuario.nombre = nombre
        usuario.apellido = apellido
        usuario.telefono = telefono
        usuario.debe_cambiar_password = False
    return usuario


def _obtener_o_crear_patologia() -> Patologia:
    patologia = db.session.scalar(
        select(Patologia).where(Patologia.nombre == "Enfermedad de Fabry")
    )
    if patologia is None:
        patologia = Patologia(
            nombre="Enfermedad de Fabry",
            descripcion="Patologia lisosomal de almacenamiento (dato semilla).",
        )
        db.session.add(patologia)
        db.session.flush()
    return patologia


def _asegurar_medico() -> Medico:
    u_med = _asegurar_usuario(
        email="medico.logistica@exoma.test",
        password=PASSWORD_DEFAULT,
        rol=Rol.MEDICO,
        nombre="Laura",
        apellido="Mendez",
        telefono="2215100000",
    )
    medico = db.session.scalar(select(Medico).where(Medico.usuario_id == u_med.id))
    if medico is None:
        medico = Medico(usuario_id=u_med.id, matricula="MN-20001")
        db.session.add(medico)
        db.session.flush()
    return medico


def _asegurar_transportista(
    email: str,
    password: str,
    provincia: str,
    dispositivo_id: str | None,
) -> Transportista:
    u_transp = _asegurar_usuario(
        email=email,
        password=password,
        rol=Rol.TRANSPORTISTA,
        nombre="Lucas",
        apellido="Vega",
        telefono="2215200000",
    )
    transportista = db.session.scalar(
        select(Transportista).where(Transportista.provincia == provincia)
    )
    if transportista is None:
        transportista = Transportista(usuario_id=u_transp.id, provincia=provincia)
        db.session.add(transportista)
        db.session.flush()
    else:
        transportista.usuario_id = u_transp.id

    if dispositivo_id:
        identificador_hash = sha256_hex(dispositivo_id)
        conocido = db.session.scalar(
            select(DispositivoConocido).where(
                DispositivoConocido.usuario_id == u_transp.id,
                DispositivoConocido.identificador == identificador_hash,
            )
        )
        if conocido is None:
            db.session.add(
                DispositivoConocido(
                    usuario_id=u_transp.id,
                    identificador=identificador_hash,
                    ultimo_acceso=_ahora_utc_naive(),
                )
            )
    return transportista


def cargar_datos_logistica(
    email_transportista: str = EMAIL_TRANSPORTISTA_DEFAULT,
    password: str = PASSWORD_DEFAULT,
    dispositivo_id: str | None = None,
    reiniciar_circuito: bool = False,
) -> dict:
    """Crea transportista, 4 centros de extraccion y 4 muestras en Lista para retirar."""
    app = create_app()
    with app.app_context():
        create_tables()
        patologia = _obtener_o_crear_patologia()
        medico = _asegurar_medico()
        transportista = _asegurar_transportista(
            email=email_transportista,
            password=password,
            provincia=PROVINCIA_DEFAULT,
            dispositivo_id=dispositivo_id,
        )

        if reiniciar_circuito:
            db.session.execute(
                delete(OrdenDelDia).where(
                    OrdenDelDia.transportista_id == transportista.id,
                    OrdenDelDia.fecha == date.today(),
                )
            )

        ahora = _ahora_utc_naive()
        centros_resumen: list[dict] = []

        for idx, item in enumerate(CENTROS_SEED, start=1):
            centro = db.session.scalar(
                select(CentroExtraccion).where(CentroExtraccion.nombre == item["nombre"])
            )
            if centro is None:
                centro = CentroExtraccion(
                    nombre=item["nombre"],
                    direccion=item["direccion"],
                    provincia=item["provincia"],
                    latitud=item["latitud"],
                    longitud=item["longitud"],
                )
                db.session.add(centro)
                db.session.flush()

            u_pac = _asegurar_usuario(
                email=item["paciente_email"],
                password=password,
                rol=Rol.PACIENTE,
                nombre=item["paciente_nombre"],
                apellido=item["paciente_apellido"],
                telefono=f"221530000{idx}",
            )
            paciente = db.session.scalar(select(Paciente).where(Paciente.dni == item["dni"]))
            if paciente is None:
                paciente = Paciente(
                    usuario_id=u_pac.id,
                    medico_id=medico.id,
                    dni=item["dni"],
                    fecha_nacimiento=date(1993, idx, 10),
                    diagnostico_presuntivo_id=patologia.id,
                    historia_clinica=f"HC-LOG-{idx}",
                    tipo_sospecha="Clinica",
                )
                db.session.add(paciente)
                db.session.flush()

            estudio = db.session.scalar(
                select(Estudio).where(Estudio.paciente_id == paciente.id)
            )
            if estudio is None:
                estudio = Estudio(
                    paciente_id=paciente.id,
                    medico_id=medico.id,
                    patologia_sospechada_id=patologia.id,
                    estado=EstadoEstudio.LISTA_PARA_RETIRAR,
                )
                db.session.add(estudio)
                db.session.flush()
            elif reiniciar_circuito:
                estudio.estado = EstadoEstudio.LISTA_PARA_RETIRAR

            turno = db.session.scalar(select(Turno).where(Turno.estudio_id == estudio.id))
            if turno is None:
                turno = Turno(
                    centro_id=centro.id,
                    paciente_id=paciente.id,
                    estudio_id=estudio.id,
                    inicio=ahora - timedelta(hours=2, minutes=idx * 15),
                    activo=False,
                    asistio=True,
                )
                db.session.add(turno)
                db.session.flush()

            muestra = db.session.scalar(select(Muestra).where(Muestra.estudio_id == estudio.id))
            if muestra is None:
                muestra = Muestra(
                    estudio_id=estudio.id,
                    turno_id=turno.id,
                    tomada_en=ahora - timedelta(hours=1),
                )
                db.session.add(muestra)
                db.session.flush()
            elif reiniciar_circuito:
                muestra.llegada_lab_central = None
                muestra.motivo_descarte = None

            centros_resumen.append(
                {
                    "centro_id": centro.id,
                    "nombre": centro.nombre,
                    "estudio_id": estudio.id,
                    "estado": estudio.estado.value,
                }
            )

        db.session.commit()
        return {
            "transportista_id": transportista.id,
            "email": email_transportista.strip().lower(),
            "password": password,
            "provincia": transportista.provincia,
            "centros": centros_resumen,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga datos de prueba para Escenario 11.")
    parser.add_argument(
        "--email",
        default=EMAIL_TRANSPORTISTA_DEFAULT,
        help="Email del usuario transportista (usa un correo real si necesitas recibir el codigo 2FA).",
    )
    parser.add_argument(
        "--password",
        default=PASSWORD_DEFAULT,
        help="Contrasena del transportista (por defecto: Clave1234).",
    )
    parser.add_argument(
        "--dispositivo-id",
        default=None,
        help="UUID de localStorage 'exoma_dispositivo_id' para omitir verificacion 2FA de maquina nueva.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Borra la orden de hoy y vuelve los 4 estudios de prueba a 'Lista para retirar'.",
    )
    args = parser.parse_args()

    resumen = cargar_datos_logistica(
        email_transportista=args.email,
        password=args.password,
        dispositivo_id=args.dispositivo_id,
        reiniciar_circuito=args.reset,
    )
    print(
        f"Transportista listo: id={resumen['transportista_id']} | "
        f"email={resumen['email']} | password={resumen['password']} | provincia={resumen['provincia']}"
    )
    for c in resumen["centros"]:
        print(f" - Centro #{c['centro_id']}: {c['nombre']} | estudio={c['estudio_id']} ({c['estado']})")


if __name__ == "__main__":
    main()
