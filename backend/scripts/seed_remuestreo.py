"""Script idempotente para cargar estudios con muestra vigente elegibles para remuestreo (Escenario 10)."""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from src import create_app
from src.core.database import create_tables, db
from src.core.models import (
    Autorizacion,
    CentroExtraccion,
    DispositivoConocido,
    EstadoEstudio,
    EstadoSampleSet,
    Estudio,
    Medico,
    Muestra,
    Paciente,
    Pago,
    Patologia,
    Presupuesto,
    ResultadoAutorizacion,
    Rol,
    SampleSet,
    TipoPago,
    Turno,
    Usuario,
)
from src.core.services.seguridad import hashear_password, sha256_hex

PASSWORD_DEFAULT = "Clave1234"
DISPOSITIVOS_POR_DEFECTO = ("pc-lab", "pc-oficina")

CASOS_REMUESTREO: list[dict] = [
    {
        "email": "seed.remuestreo1@exoma.test",
        "nombre": "Julieta",
        "apellido": "Sosa",
        "dni": "61100101",
        "fecha_nacimiento": date(1991, 6, 18),
        "patologia": "Enfermedad de Fabry",
        "patologia_desc": "Patologia lisosomal de almacenamiento.",
        "estado": EstadoEstudio.EN_VIAJE_COREA,
        "es_pompe_urgente": False,
        "lote": "corea",
        "pago_particular": True,
    },
    {
        "email": "seed.remuestreo2@exoma.test",
        "nombre": "Bautista",
        "apellido": "Quiroga",
        "dni": "61100102",
        "fecha_nacimiento": date.today() - timedelta(days=75),
        "patologia": "Enfermedad de Pompe",
        "patologia_desc": "Glucogenosis tipo II por deficit de GAA.",
        "estado": EstadoEstudio.EN_VIAJE_COREA,
        "es_pompe_urgente": True,
        "lote": "corea",
        "pago_particular": False,
    },
    {
        "email": "seed.remuestreo3@exoma.test",
        "nombre": "Camila",
        "apellido": "Herrera",
        "dni": "61100103",
        "fecha_nacimiento": date(1987, 2, 11),
        "patologia": "Enfermedad de Gaucher",
        "patologia_desc": "Patologia lisosomal por deficit de glucocerebrosidasa.",
        "estado": EstadoEstudio.EN_VIAJE_COREA,
        "es_pompe_urgente": False,
        "lote": "corea2",
        "pago_particular": False,
    },
    {
        "email": "seed.remuestreo4@exoma.test",
        "nombre": "Tomas",
        "apellido": "Navarro",
        "dni": "61100104",
        "fecha_nacimiento": date(1994, 9, 25),
        "patologia": "Enfermedad de Fabry",
        "patologia_desc": "Patologia lisosomal de almacenamiento.",
        "estado": EstadoEstudio.EN_VIAJE_COREA,
        "es_pompe_urgente": False,
        "lote": "corea2",
        "pago_particular": True,
    },
]


def _asegurar_patologia(nombre: str, descripcion: str) -> Patologia:
    pat = db.session.scalar(select(Patologia).where(Patologia.nombre == nombre))
    if pat is None:
        pat = Patologia(nombre=nombre, descripcion=descripcion)
        db.session.add(pat)
        db.session.flush()
    return pat


def _asegurar_centro() -> CentroExtraccion:
    nombre = "Laboratorio BioGen - La Plata Centro"
    centro = db.session.scalar(select(CentroExtraccion).where(CentroExtraccion.nombre == nombre))
    if centro is None:
        centro = CentroExtraccion(
            nombre=nombre,
            direccion="Calle 7 Nro 850, La Plata",
            provincia="Buenos Aires",
            latitud=-34.9205,
            longitud=-57.9536,
        )
        db.session.add(centro)
        db.session.flush()
    return centro


def _asegurar_medico_y_admin() -> tuple[Medico, Usuario]:
    u_admin = db.session.scalar(
        select(Usuario).where(Usuario.email == "administrativo@lab.com")
    )
    if u_admin is None:
        u_admin = Usuario(
            email="administrativo@lab.com",
            password_hash=hashear_password(PASSWORD_DEFAULT),
            rol=Rol.ADMINISTRATIVO,
            nombre="Personal",
            apellido="Administrativo",
            telefono="2215100002",
            debe_cambiar_password=False,
        )
        db.session.add(u_admin)
        db.session.flush()

    u_med = db.session.scalar(
        select(Usuario).where(Usuario.email == "medico.remuestreo.seed@exoma.test")
    )
    if u_med is None:
        u_med = Usuario(
            email="medico.remuestreo.seed@exoma.test",
            password_hash=hashear_password(PASSWORD_DEFAULT),
            rol=Rol.MEDICO,
            nombre="Laura",
            apellido="Mendez",
            telefono="2215200002",
            debe_cambiar_password=False,
        )
        db.session.add(u_med)
        db.session.flush()

    medico = db.session.scalar(select(Medico).where(Medico.usuario_id == u_med.id))
    if medico is None:
        medico = Medico(usuario_id=u_med.id, matricula="MN-56001")
        db.session.add(medico)
        db.session.flush()

    return medico, u_admin


def cargar_estudios_remuestreo() -> list[dict]:
    """Crea o reinicia 4 estudios con muestra vigente listos para probar remuestreo."""
    app = create_app()
    resumen: list[dict] = []
    ahora = datetime.now(UTC).replace(tzinfo=None)

    with app.app_context():
        create_tables()
        medico, u_admin = _asegurar_medico_y_admin()
        centro = _asegurar_centro()
        hashes_dispositivos = {sha256_hex(d) for d in DISPOSITIVOS_POR_DEFECTO}
        hashes_dispositivos.update(
            db.session.scalars(select(DispositivoConocido.identificador).distinct()).all()
        )

        sample_sets_previos: set[int] = set()
        for idx, caso in enumerate(CASOS_REMUESTREO, start=1):
            patologia = _asegurar_patologia(caso["patologia"], caso["patologia_desc"])

            u_pac = db.session.scalar(select(Usuario).where(Usuario.email == caso["email"]))
            if u_pac is None:
                u_pac = Usuario(
                    email=caso["email"],
                    password_hash=hashear_password(PASSWORD_DEFAULT),
                    rol=Rol.PACIENTE,
                    nombre=caso["nombre"],
                    apellido=caso["apellido"],
                    telefono=f"221540000{idx}",
                    debe_cambiar_password=False,
                )
                db.session.add(u_pac)
                db.session.flush()
            else:
                u_pac.password_hash = hashear_password(PASSWORD_DEFAULT)
                u_pac.debe_cambiar_password = False

            existentes_disp = set(
                db.session.scalars(
                    select(DispositivoConocido.identificador).where(
                        DispositivoConocido.usuario_id == u_pac.id
                    )
                ).all()
            )
            for disp_hash in sorted(hashes_dispositivos - existentes_disp):
                db.session.add(
                    DispositivoConocido(
                        usuario_id=u_pac.id,
                        identificador=disp_hash,
                        ultimo_acceso=ahora,
                    )
                )

            paciente = db.session.scalar(
                select(Paciente).where(Paciente.usuario_id == u_pac.id)
            )
            if paciente is None:
                dni_ocupado = db.session.scalar(
                    select(Paciente.id).where(Paciente.dni == caso["dni"])
                )
                dni_final = caso["dni"] if dni_ocupado is None else f"89{u_pac.id:06d}"
                paciente = Paciente(
                    usuario_id=u_pac.id,
                    medico_id=medico.id,
                    dni=dni_final,
                    fecha_nacimiento=caso["fecha_nacimiento"],
                    diagnostico_presuntivo_id=patologia.id,
                    historia_clinica="Paciente semilla para pruebas de remuestreo.",
                    tipo_sospecha="clinica",
                )
                db.session.add(paciente)
                db.session.flush()

            # Limpieza idempotente de estudios previos de estos pacientes semilla
            for est_prev in list(
                db.session.scalars(select(Estudio).where(Estudio.paciente_id == paciente.id)).all()
            ):
                for m_prev in est_prev.muestras:
                    if m_prev.sample_set_id is not None:
                        sample_sets_previos.add(m_prev.sample_set_id)
                db.session.execute(delete(Muestra).where(Muestra.estudio_id == est_prev.id))
                db.session.execute(delete(Turno).where(Turno.estudio_id == est_prev.id))
                pres_prev = db.session.scalar(
                    select(Presupuesto).where(Presupuesto.estudio_id == est_prev.id)
                )
                if pres_prev is not None:
                    db.session.execute(delete(Pago).where(Pago.presupuesto_id == pres_prev.id))
                    db.session.delete(pres_prev)
                db.session.execute(
                    delete(Autorizacion).where(Autorizacion.estudio_id == est_prev.id)
                )
                db.session.delete(est_prev)
            db.session.flush()

        for ss_id in sample_sets_previos:
            ss = db.session.get(SampleSet, ss_id)
            if ss is not None and len(ss.muestras) == 0:
                db.session.delete(ss)
        db.session.flush()

        sample_set_corea = SampleSet(
            estado=EstadoSampleSet.EN_VIAJE_COREA,
            cerrado_en=ahora - timedelta(days=3),
            csv_path="storage/sample_sets/seed_corea.csv",
            autorizacion_ministerio_pdf_path="storage/sample_sets/seed_auth_corea.pdf",
            retiro_fedex_pedido_id="FEDEX-SEED-901",
        )
        sample_set_corea_2 = SampleSet(
            estado=EstadoSampleSet.EN_VIAJE_COREA,
            cerrado_en=ahora - timedelta(days=2),
            csv_path="storage/sample_sets/seed_corea_2.csv",
            autorizacion_ministerio_pdf_path="storage/sample_sets/seed_auth_corea_2.pdf",
            retiro_fedex_pedido_id="FEDEX-SEED-902",
        )
        db.session.add_all([sample_set_corea, sample_set_corea_2])
        db.session.flush()

        lotes = {
            "corea": sample_set_corea,
            "corea2": sample_set_corea_2,
        }

        for idx, caso in enumerate(CASOS_REMUESTREO, start=1):
            u_pac = db.session.scalar(select(Usuario).where(Usuario.email == caso["email"]))
            paciente = db.session.scalar(select(Paciente).where(Paciente.usuario_id == u_pac.id))
            patologia = _asegurar_patologia(caso["patologia"], caso["patologia_desc"])

            estudio = Estudio(
                paciente_id=paciente.id,
                medico_id=medico.id,
                patologia_sospechada_id=patologia.id,
                estado=caso["estado"],
                es_pompe_urgente=caso["es_pompe_urgente"],
                ausencias=0,
            )
            db.session.add(estudio)
            db.session.flush()

            if caso["pago_particular"]:
                pres = Presupuesto(
                    estudio_id=estudio.id,
                    emitido_por_id=u_admin.id,
                    cantidad_genes=5,
                    monto_total_usd=Decimal("500.00"),
                )
                db.session.add(pres)
                db.session.flush()
                db.session.add(
                    Pago(
                        presupuesto_id=pres.id,
                        tipo=TipoPago.PARTICULAR,
                        monto_usd=Decimal("500.00"),
                        anulado=False,
                    )
                )
            else:
                db.session.add(
                    Autorizacion(
                        estudio_id=estudio.id,
                        resultado=ResultadoAutorizacion.AUTORIZADA,
                    )
                )

            fecha_toma = datetime.combine(ahora.date() - timedelta(days=4 + idx), time(10, 0))
            turno = Turno(
                centro_id=centro.id,
                paciente_id=paciente.id,
                estudio_id=estudio.id,
                inicio=fecha_toma,
                activo=False,
                asistio=True,
            )
            db.session.add(turno)
            db.session.flush()

            ss = lotes.get(caso["lote"])
            muestra = Muestra(
                estudio_id=estudio.id,
                turno_id=turno.id,
                sample_set_id=ss.id if ss is not None else None,
                tomada_en=fecha_toma + timedelta(minutes=10),
                llegada_lab_central=fecha_toma + timedelta(hours=3),
                motivo_descarte=None,
            )
            db.session.add(muestra)
            db.session.flush()

            resumen.append(
                {
                    "estudio_id": estudio.id,
                    "muestra_id": muestra.id,
                    "estado": estudio.estado.value,
                    "es_pompe_urgente": estudio.es_pompe_urgente,
                    "sample_set_id": muestra.sample_set_id,
                    "paciente": f"{u_pac.nombre} {u_pac.apellido}",
                    "email": u_pac.email,
                    "dni": paciente.dni,
                }
            )

        db.session.commit()

    return resumen


if __name__ == "__main__":
    filas = cargar_estudios_remuestreo()
    print(f"Cargados {len(filas)} estudios con muestra vigente para remuestreo (password: {PASSWORD_DEFAULT}):")
    for f in filas:
        lote_txt = f"SampleSet #{f['sample_set_id']}" if f["sample_set_id"] else "Sin lote"
        urg_txt = " [POMPE URGENTE]" if f["es_pompe_urgente"] else ""
        print(
            f" - Estudio #{f['estudio_id']} | Muestra #{f['muestra_id']} | "
            f"{f['estado']}{urg_txt} | {f['paciente']} ({f['email']}, DNI {f['dni']}) | {lote_txt}"
        )
