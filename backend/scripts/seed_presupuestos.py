"""Script idempotente para cargar estudios en Creado sin presupuesto (Escenario 3)."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from src import create_app
from src.core.database import create_tables, db
from src.core.models import (
    Autorizacion,
    Aviso,
    DispositivoConocido,
    EntidadAuditable,
    EstadoEstudio,
    Estudio,
    EstudioGen,
    Gen,
    Medico,
    Muestra,
    ObraSocial,
    OrigenGen,
    Paciente,
    Pago,
    Patologia,
    Presupuesto,
    RegistroModificacion,
    Rol,
    Turno,
    Usuario,
)
from src.core.services.seguridad import hashear_password, sha256_hex

PASSWORD_DEFAULT = "Clave1234"
DISPOSITIVOS_POR_DEFECTO = ("pc-lab", "pc-oficina")

GENES = [
    ("GAA", "Alfa-glucosidasa acida"),
    ("GLA", "Alfa-galactosidasa A"),
    ("GBA", "Glucocerebrosidasa"),
    ("IDUA", "Alfa-L-iduronidasa"),
    ("CFTR", "Regulador de conductancia transmembrana"),
    ("BRCA1", "Supresor tumoral BRCA1"),
    ("BRCA2", "Supresor tumoral BRCA2"),
    ("TP53", "Proteina tumoral p53"),
]

# Cada caso cubre un camino distinto de la pantalla de presupuestos.
CASOS_PRESUPUESTO: list[dict] = [
    {   # Particular con hasta 5 genes -> USD 500
        "email": "seed.presupuesto1@exoma.test", "nombre": "Valentina", "apellido": "Rios",
        "dni": "62200101", "fecha_nacimiento": date(1990, 4, 12),
        "patologia": "Enfermedad de Fabry", "patologia_desc": "Patologia lisosomal de almacenamiento.",
        "genes": 4, "obra_social": False, "es_pompe_urgente": False, "dias_desde_alta": 3,
    },
    {   # Particular con 8 genes -> USD 590 (500 + 3 x 30)
        "email": "seed.presupuesto2@exoma.test", "nombre": "Joaquin", "apellido": "Ferreyra",
        "dni": "62200102", "fecha_nacimiento": date(1985, 11, 2),
        "patologia": "Enfermedad de Gaucher", "patologia_desc": "Patologia lisosomal por deficit de glucocerebrosidasa.",
        "genes": 8, "obra_social": False, "es_pompe_urgente": False, "dias_desde_alta": 5,
    },
    {   # Con obra social y 6 genes -> USD 530 y pasa a Pendiente de autorizacion
        "email": "seed.presupuesto3@exoma.test", "nombre": "Martina", "apellido": "Acosta",
        "dni": "62200103", "fecha_nacimiento": date(1996, 7, 21),
        "patologia": "Enfermedad de Fabry", "patologia_desc": "Patologia lisosomal de almacenamiento.",
        "genes": 6, "obra_social": True, "es_pompe_urgente": False, "dias_desde_alta": 2,
    },
    {   # Pompe urgente (bebe < 4 meses): aparece primero en la bandeja
        "email": "seed.presupuesto4@exoma.test", "nombre": "Benjamin", "apellido": "Luna",
        "dni": "62200104", "fecha_nacimiento": date.today() - timedelta(days=60),
        "patologia": "Enfermedad de Pompe", "patologia_desc": "Glucogenosis tipo II por deficit de GAA.",
        "genes": 5, "obra_social": False, "es_pompe_urgente": True, "dias_desde_alta": 1,
    },
    {   # Sin genes: el boton "Emitir presupuesto" debe quedar deshabilitado
        "email": "seed.presupuesto5@exoma.test", "nombre": "Sofia", "apellido": "Medina",
        "dni": "62200105", "fecha_nacimiento": date(1979, 1, 30),
        "patologia": "Enfermedad de Gaucher", "patologia_desc": "Patologia lisosomal por deficit de glucocerebrosidasa.",
        "genes": 0, "obra_social": False, "es_pompe_urgente": False, "dias_desde_alta": 4,
    },
]


def _asegurar_patologia(nombre: str, descripcion: str) -> Patologia:
    pat = db.session.scalar(select(Patologia).where(Patologia.nombre == nombre))
    if pat is None:
        pat = Patologia(nombre=nombre, descripcion=descripcion)
        db.session.add(pat)
        db.session.flush()
    return pat


def _asegurar_genes() -> list[Gen]:
    genes: list[Gen] = []
    for simbolo, nombre in GENES:
        gen = db.session.scalar(select(Gen).where(Gen.simbolo == simbolo))
        if gen is None:
            gen = Gen(simbolo=simbolo, nombre=nombre)
            db.session.add(gen)
            db.session.flush()
        genes.append(gen)
    return genes


def _asegurar_obra_social() -> ObraSocial:
    obra_social = db.session.scalar(select(ObraSocial).where(ObraSocial.nombre == "OSDE"))
    if obra_social is None:
        obra_social = ObraSocial(nombre="OSDE", rnos="115404", porcentaje_cobertura=Decimal("80.00"))
        db.session.add(obra_social)
        db.session.flush()
    return obra_social


def _asegurar_usuario(email: str, rol: Rol, nombre: str, apellido: str, telefono: str) -> Usuario:
    usuario = db.session.scalar(select(Usuario).where(Usuario.email == email))
    if usuario is None:
        usuario = Usuario(
            email=email,
            password_hash=hashear_password(PASSWORD_DEFAULT),
            rol=rol,
            nombre=nombre,
            apellido=apellido,
            telefono=telefono,
            debe_cambiar_password=False,
        )
        db.session.add(usuario)
        db.session.flush()
    else:
        usuario.password_hash = hashear_password(PASSWORD_DEFAULT)
        usuario.debe_cambiar_password = False
    return usuario


def _asegurar_dispositivos(usuario: Usuario, hashes: set[str], ahora: datetime) -> None:
    """Registra pc-lab / pc-oficina como conocidos para entrar sin codigo por mail."""
    existentes = set(
        db.session.scalars(
            select(DispositivoConocido.identificador).where(DispositivoConocido.usuario_id == usuario.id)
        ).all()
    )
    for disp_hash in sorted(hashes - existentes):
        db.session.add(DispositivoConocido(usuario_id=usuario.id, identificador=disp_hash, ultimo_acceso=ahora))


def _borrar_estudios_previos(paciente: Paciente) -> None:
    """Limpieza idempotente: borra los estudios del paciente semilla y todo lo que cuelga de ellos."""
    for est in list(db.session.scalars(select(Estudio).where(Estudio.paciente_id == paciente.id)).all()):
        db.session.execute(
            delete(RegistroModificacion).where(
                RegistroModificacion.entidad_tipo == EntidadAuditable.ESTUDIO,
                RegistroModificacion.entidad_id == est.id,
            )
        )
        db.session.execute(delete(Muestra).where(Muestra.estudio_id == est.id))
        db.session.execute(delete(Turno).where(Turno.estudio_id == est.id))
        presupuesto = db.session.scalar(select(Presupuesto).where(Presupuesto.estudio_id == est.id))
        if presupuesto is not None:
            db.session.execute(delete(Pago).where(Pago.presupuesto_id == presupuesto.id))
            db.session.delete(presupuesto)
        db.session.execute(delete(Autorizacion).where(Autorizacion.estudio_id == est.id))
        db.session.execute(delete(EstudioGen).where(EstudioGen.estudio_id == est.id))
        db.session.delete(est)
    db.session.flush()


def cargar_estudios_presupuesto() -> list[dict]:
    """Crea o reinicia 5 estudios en Creado sin presupuesto para probar el Escenario 3."""
    app = create_app()
    resumen: list[dict] = []
    ahora = datetime.now(UTC).replace(tzinfo=None)
    origenes = [OrigenGen.PATOLOGIA, OrigenGen.MANUAL, OrigenGen.HALLAZGO_SECUNDARIO]

    with app.app_context():
        create_tables()
        hashes = {sha256_hex(d) for d in DISPOSITIVOS_POR_DEFECTO}

        u_admin = _asegurar_usuario(
            "administrativo@lab.com", Rol.ADMINISTRATIVO, "Personal", "Administrativo", "2215100002"
        )
        _asegurar_dispositivos(u_admin, hashes, ahora)

        u_med = _asegurar_usuario(
            "medico.presupuesto.seed@exoma.test", Rol.MEDICO, "Laura", "Mendez", "2215200003"
        )
        medico = db.session.scalar(select(Medico).where(Medico.usuario_id == u_med.id))
        if medico is None:
            medico = Medico(usuario_id=u_med.id, matricula="MN-56003")
            db.session.add(medico)
            db.session.flush()

        genes = _asegurar_genes()
        obra_social = _asegurar_obra_social()

        for idx, caso in enumerate(CASOS_PRESUPUESTO, start=1):
            patologia = _asegurar_patologia(caso["patologia"], caso["patologia_desc"])
            u_pac = _asegurar_usuario(
                caso["email"], Rol.PACIENTE, caso["nombre"], caso["apellido"], f"221560000{idx}"
            )
            _asegurar_dispositivos(u_pac, hashes, ahora)

            paciente = db.session.scalar(select(Paciente).where(Paciente.usuario_id == u_pac.id))
            if paciente is None:
                dni_ocupado = db.session.scalar(select(Paciente.id).where(Paciente.dni == caso["dni"]))
                paciente = Paciente(
                    usuario_id=u_pac.id,
                    medico_id=medico.id,
                    dni=caso["dni"] if dni_ocupado is None else f"88{u_pac.id:06d}",
                    fecha_nacimiento=caso["fecha_nacimiento"],
                    diagnostico_presuntivo_id=patologia.id,
                    historia_clinica="Paciente semilla para pruebas de presupuestos.",
                    tipo_sospecha="clinica",
                )
                db.session.add(paciente)
                db.session.flush()

            db.session.execute(delete(Aviso).where(Aviso.usuario_id == u_pac.id))
            _borrar_estudios_previos(paciente)

            estudio = Estudio(
                paciente_id=paciente.id,
                medico_id=medico.id,
                patologia_sospechada_id=patologia.id,
                estado=EstadoEstudio.CREADO,
                obra_social_id=obra_social.id if caso["obra_social"] else None,
                es_pompe_urgente=caso["es_pompe_urgente"],
                ausencias=0,
                created_at=ahora - timedelta(days=caso["dias_desde_alta"]),
            )
            db.session.add(estudio)
            db.session.flush()

            for i, gen in enumerate(genes[: caso["genes"]]):
                db.session.add(EstudioGen(estudio_id=estudio.id, gen_id=gen.id, origen=origenes[i % 3]))

            resumen.append(
                {
                    "estudio_id": estudio.id,
                    "paciente": f"{u_pac.nombre} {u_pac.apellido}",
                    "email": u_pac.email,
                    "dni": paciente.dni,
                    "genes": caso["genes"],
                    "obra_social": obra_social.nombre if caso["obra_social"] else "Particular",
                    "es_pompe_urgente": caso["es_pompe_urgente"],
                }
            )

        db.session.commit()

    return resumen


if __name__ == "__main__":
    filas = cargar_estudios_presupuesto()
    print(f"Cargados {len(filas)} estudios en Creado sin presupuesto (password: {PASSWORD_DEFAULT}).")
    print("Ingresa como administrativo@lab.com; en el navegador: localStorage.setItem('exoma_dispositivo_id', 'pc-lab')")
    for f in filas:
        urg = " [POMPE URGENTE]" if f["es_pompe_urgente"] else ""
        print(
            f" - Estudio #{f['estudio_id']} | {f['genes']} genes | {f['obra_social']}{urg} | "
            f"{f['paciente']} ({f['email']}, DNI {f['dni']})"
        )