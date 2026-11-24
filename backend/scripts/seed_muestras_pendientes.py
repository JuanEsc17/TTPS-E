"""Script idempotente para cargar turnos pendientes de toma de muestra (urgentes Pompe y normales)."""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import delete, select
from src import create_app
from src.core.database import create_tables, db
from src.core.models import (
    Autorizacion,
    CentroExtraccion,
    EstadoEstudio,
    Estudio,
    Medico,
    MotivoDescarte,
    Muestra,
    Paciente,
    Patologia,
    ResultadoAutorizacion,
    Rol,
    Turno,
    Usuario,
)
from src.core.services.seguridad import hashear_password

from scripts.seed_escenario_15 import _asegurar_columnas_escenario_15

PASSWORD_DEFAULT = "Clave1234"

CASOS_MUESTRAS: list[dict] = [
    {
        "email": "seed.muestra1@exoma.test",
        "nombre": "Mateo",
        "apellido": "Alvarez",
        "dni": "54100101",
        "fecha_nacimiento": date.today() - timedelta(days=60),
        "patologia": "Enfermedad de Pompe",
        "patologia_desc": "Glucogenosis tipo II por deficit de GAA.",
        "es_pompe_urgente": True,
        "centro": {
            "nombre": "Laboratorio BioGen - La Plata Centro",
            "direccion": "Calle 7 Nro 850, La Plata",
            "provincia": "Buenos Aires",
            "latitud": -34.9205,
            "longitud": -57.9536,
        },
        "dia_offset": 0,
        "hora": time(9, 30),
        "remuestreo": False,
    },
    {
        "email": "seed.muestra2@exoma.test",
        "nombre": "Olivia",
        "apellido": "Benitez",
        "dni": "54100102",
        "fecha_nacimiento": date.today() - timedelta(days=90),
        "patologia": "Enfermedad de Pompe",
        "patologia_desc": "Glucogenosis tipo II por deficit de GAA.",
        "es_pompe_urgente": True,
        "centro": {
            "nombre": "Centro Medico City Bell",
            "direccion": "Cantilo Nro 420, City Bell",
            "provincia": "Buenos Aires",
            "latitud": -34.8682,
            "longitud": -58.0468,
        },
        "dia_offset": 0,
        "hora": time(10, 45),
        "remuestreo": False,
    },
    {
        "email": "seed.muestra3@exoma.test",
        "nombre": "Santiago",
        "apellido": "Rojas",
        "dni": "33200201",
        "fecha_nacimiento": date(1988, 7, 14),
        "patologia": "Enfermedad de Fabry",
        "patologia_desc": "Patologia lisosomal de almacenamiento.",
        "es_pompe_urgente": False,
        "centro": {
            "nombre": "Centro Extraccion Plaza Italia",
            "direccion": "Diag. 74 Nro 1520, La Plata",
            "provincia": "Buenos Aires",
            "latitud": -34.9102,
            "longitud": -57.9554,
        },
        "dia_offset": 0,
        "hora": time(11, 15),
        "remuestreo": False,
    },
    {
        "email": "seed.muestra4@exoma.test",
        "nombre": "Valentina",
        "apellido": "Castro",
        "dni": "36200202",
        "fecha_nacimiento": date(1992, 3, 22),
        "patologia": "Enfermedad de Gaucher",
        "patologia_desc": "Patologia lisosomal por deficit de glucocerebrosidasa.",
        "es_pompe_urgente": False,
        "centro": {
            "nombre": "Laboratorio Sur - Berisso",
            "direccion": "Av. Montevideo 1180, Berisso",
            "provincia": "Buenos Aires",
            "latitud": -34.8728,
            "longitud": -57.8842,
        },
        "dia_offset": 1,
        "hora": time(9, 0),
        "remuestreo": False,
    },
    {
        "email": "seed.muestra5@exoma.test",
        "nombre": "Lucas",
        "apellido": "Peralta",
        "dni": "39200203",
        "fecha_nacimiento": date(1995, 11, 5),
        "patologia": "Enfermedad de Fabry",
        "patologia_desc": "Patologia lisosomal de almacenamiento.",
        "es_pompe_urgente": False,
        "centro": {
            "nombre": "Centro Diagnostico Nueva Cordoba",
            "direccion": "Av. Hipolito Yrigoyen 380, Cordoba",
            "provincia": "Cordoba",
            "latitud": -31.4239,
            "longitud": -64.1865,
        },
        "dia_offset": 1,
        "hora": time(14, 30),
        "remuestreo": True,
    },
]


def _asegurar_patologia(nombre: str, descripcion: str) -> Patologia:
    pat = db.session.scalar(select(Patologia).where(Patologia.nombre == nombre))
    if pat is None:
        pat = Patologia(nombre=nombre, descripcion=descripcion)
        db.session.add(pat)
        db.session.flush()
    return pat


def _asegurar_centro(datos: dict) -> CentroExtraccion:
    centro = db.session.scalar(
        select(CentroExtraccion).where(CentroExtraccion.nombre == datos["nombre"])
    )
    if centro is None:
        centro = CentroExtraccion(**datos)
        db.session.add(centro)
        db.session.flush()
    return centro


def _asegurar_medico() -> Medico:
    u_med = db.session.scalar(
        select(Usuario).where(Usuario.email == "medico.muestras.seed@exoma.test")
    )
    if u_med is None:
        u_med = Usuario(
            email="medico.muestras.seed@exoma.test",
            password_hash=hashear_password(PASSWORD_DEFAULT),
            rol=Rol.MEDICO,
            nombre="Laura",
            apellido="Mendez",
            telefono="2215200001",
            debe_cambiar_password=False,
        )
        db.session.add(u_med)
        db.session.flush()

    medico = db.session.scalar(select(Medico).where(Medico.usuario_id == u_med.id))
    if medico is None:
        medico = Medico(usuario_id=u_med.id, matricula="MN-55001")
        db.session.add(medico)
        db.session.flush()
    return medico


def cargar_turnos_pendientes_muestra() -> list[dict]:
    """Crea o reinicia 5 turnos activos en Turno sacado (2 Pompe urgentes y 3 normales)."""
    app = create_app()
    resumen: list[dict] = []
    hoy = datetime.now(UTC).date()

    with app.app_context():
        create_tables()
        _asegurar_columnas_escenario_15()
        medico = _asegurar_medico()

        for idx, caso in enumerate(CASOS_MUESTRAS, start=1):
            patologia = _asegurar_patologia(caso["patologia"], caso["patologia_desc"])
            centro = _asegurar_centro(caso["centro"])

            u_pac = db.session.scalar(select(Usuario).where(Usuario.email == caso["email"]))
            if u_pac is None:
                u_pac = Usuario(
                    email=caso["email"],
                    password_hash=hashear_password(PASSWORD_DEFAULT),
                    rol=Rol.PACIENTE,
                    nombre=caso["nombre"],
                    apellido=caso["apellido"],
                    telefono=f"221530000{idx}",
                    debe_cambiar_password=False,
                )
                db.session.add(u_pac)
                db.session.flush()

            paciente = db.session.scalar(
                select(Paciente).where(Paciente.usuario_id == u_pac.id)
            )
            if paciente is None:
                dni_ocupado = db.session.scalar(
                    select(Paciente.id).where(Paciente.dni == caso["dni"])
                )
                dni_final = caso["dni"] if dni_ocupado is None else f"88{u_pac.id:06d}"
                paciente = Paciente(
                    usuario_id=u_pac.id,
                    medico_id=medico.id,
                    dni=dni_final,
                    fecha_nacimiento=caso["fecha_nacimiento"],
                    diagnostico_presuntivo_id=patologia.id,
                    historia_clinica="Paciente semilla para prueba de registro de muestras.",
                    tipo_sospecha="clinica",
                )
                db.session.add(paciente)
                db.session.flush()

            # Reinicia estudios previos de este paciente semilla para que el script sea idempotente
            estudios_previos = list(
                db.session.scalars(select(Estudio).where(Estudio.paciente_id == paciente.id)).all()
            )
            for est_prev in estudios_previos:
                db.session.execute(delete(Muestra).where(Muestra.estudio_id == est_prev.id))
                db.session.execute(delete(Turno).where(Turno.estudio_id == est_prev.id))
                db.session.execute(
                    delete(Autorizacion).where(Autorizacion.estudio_id == est_prev.id)
                )
                db.session.delete(est_prev)
            db.session.flush()

            estudio = Estudio(
                paciente_id=paciente.id,
                medico_id=medico.id,
                patologia_sospechada_id=patologia.id,
                estado=EstadoEstudio.TURNO_SACADO,
                es_pompe_urgente=caso["es_pompe_urgente"],
                ausencias=0,
            )
            db.session.add(estudio)
            db.session.flush()

            db.session.add(
                Autorizacion(
                    estudio_id=estudio.id,
                    resultado=ResultadoAutorizacion.AUTORIZADA,
                )
            )

            fecha_turno = hoy + timedelta(days=caso["dia_offset"])
            inicio_turno = datetime.combine(fecha_turno, caso["hora"])

            if caso["remuestreo"]:
                turno_anterior = Turno(
                    centro_id=centro.id,
                    paciente_id=paciente.id,
                    estudio_id=estudio.id,
                    inicio=datetime.combine(hoy - timedelta(days=7), time(10, 0)),
                    activo=False,
                    asistio=True,
                )
                db.session.add(turno_anterior)
                db.session.flush()
                db.session.add(
                    Muestra(
                        estudio_id=estudio.id,
                        turno_id=turno_anterior.id,
                        tomada_en=datetime.combine(hoy - timedelta(days=7), time(10, 10)),
                        motivo_descarte=MotivoDescarte.ADN_INSUFICIENTE,
                    )
                )

            turno_activo = Turno(
                centro_id=centro.id,
                paciente_id=paciente.id,
                estudio_id=estudio.id,
                inicio=inicio_turno,
                activo=True,
                asistio=None,
            )
            db.session.add(turno_activo)
            db.session.flush()

            resumen.append(
                {
                    "turno_id": turno_activo.id,
                    "estudio_id": estudio.id,
                    "paciente": f"{u_pac.nombre} {u_pac.apellido}",
                    "dni": paciente.dni,
                    "es_pompe_urgente": estudio.es_pompe_urgente,
                    "centro": centro.nombre,
                    "inicio": inicio_turno.isoformat(),
                    "remuestreo": caso["remuestreo"],
                }
            )

        db.session.commit()

    return resumen


if __name__ == "__main__":
    filas = cargar_turnos_pendientes_muestra()
    print(f"Cargados {len(filas)} turnos pendientes de toma de muestra:")
    for f in filas:
        tipo = "POMPE URGENTE" if f["es_pompe_urgente"] else ("REMUESTREO" if f["remuestreo"] else "NORMAL")
        print(
            f" - [{tipo}] Turno #{f['turno_id']} | Estudio #{f['estudio_id']} | "
            f"{f['paciente']} (DNI {f['dni']}) | {f['centro']} | {f['inicio']}"
        )
