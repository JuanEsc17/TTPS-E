"""Script idempotente para crear la tabla, indices, backfill y datos de prueba del Escenario 40."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select, text
from src import create_app
from src.core.database import create_tables, db
from src.core.models import (
    Aviso,
    CanalAviso,
    DispositivoConocido,
    EntidadAuditable,
    Especialidad,
    Familiar,
    Medico,
    Paciente,
    PacienteMedicoAutorizado,
    PacienteSintoma,
    Patologia,
    PatologiaSintoma,
    RegistroModificacion,
    Rol,
    Sintoma,
    TipoAccionAuditoria,
    Usuario,
)
from src.core.services.seguridad import hashear_password, sha256_hex

PASSWORD_PRUEBA = "Clave1234"
DISPOSITIVOS_POR_DEFECTO = ("pc-lab", "pc-oficina")

ESPECIALIDADES_SEED = (
    "Genética Médica",
    "Hematología",
    "Neurología",
    "Cardiología",
    "Pediatría",
    "Nefrología",
    "Clínica Médica",
)

MEDICOS_DEMO = (
    {
        "email": "hematologa@lab.com",
        "nombre": "Lucía",
        "apellido": "Benítez",
        "telefono": "2215400101",
        "matricula": "MP-40101",
        "especialidades": ("Hematología", "Genética Médica"),
    },
    {
        "email": "neurologo@lab.com",
        "nombre": "Martín",
        "apellido": "Castro",
        "telefono": "2215400102",
        "matricula": "MP-40102",
        "especialidades": ("Neurología",),
    },
    {
        "email": "cardiologa@lab.com",
        "nombre": "Valentina",
        "apellido": "Romero",
        "telefono": "2215400103",
        "matricula": "MP-40103",
        "especialidades": ("Cardiología", "Clínica Médica"),
    },
    {
        "email": "pediatra@lab.com",
        "nombre": "Santiago",
        "apellido": "Herrera",
        "telefono": "2215400104",
        "matricula": "MP-40104",
        "especialidades": ("Pediatría", "Nefrología"),
    },
)


def _ahora_utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _asegurar_especialidades() -> dict[str, Especialidad]:
    mapa: dict[str, Especialidad] = {}
    for nombre in ESPECIALIDADES_SEED:
        esp = db.session.scalar(select(Especialidad).where(Especialidad.nombre == nombre))
        if esp is None:
            esp = Especialidad(nombre=nombre)
            db.session.add(esp)
            db.session.flush()
        mapa[nombre] = esp
    return mapa


def _asegurar_patologia(nombre: str, descripcion: str) -> Patologia:
    pat = db.session.scalar(select(Patologia).where(Patologia.nombre == nombre))
    if pat is None:
        pat = Patologia(nombre=nombre, descripcion=descripcion)
        db.session.add(pat)
        db.session.flush()
    return pat


def _asegurar_sintoma(snomed_id: str, descripcion: str) -> Sintoma:
    sin = db.session.scalar(select(Sintoma).where(Sintoma.snomed_id == snomed_id))
    if sin is None:
        sin = Sintoma(snomed_id=snomed_id, descripcion=descripcion)
        db.session.add(sin)
        db.session.flush()
    return sin


def _asegurar_patologia_sintoma(patologia_id: int, sintoma_id: int, es_cardinal: bool) -> None:
    rel = db.session.scalar(
        select(PatologiaSintoma).where(
            PatologiaSintoma.patologia_id == patologia_id,
            PatologiaSintoma.sintoma_id == sintoma_id,
        )
    )
    if rel is None:
        if es_cardinal:
            ya_cardinal = db.session.scalar(
                select(PatologiaSintoma).where(
                    PatologiaSintoma.patologia_id == patologia_id,
                    PatologiaSintoma.es_cardinal.is_(True),
                )
            )
            if ya_cardinal is not None:
                es_cardinal = False
        db.session.add(
            PatologiaSintoma(
                patologia_id=patologia_id,
                sintoma_id=sintoma_id,
                es_cardinal=es_cardinal,
            )
        )
        db.session.flush()


def _asegurar_usuario(
    *,
    email: str,
    rol: Rol,
    nombre: str,
    apellido: str,
    telefono: str,
    hashes_dispositivos: set[str],
) -> Usuario:
    email_norm = email.strip().lower()
    usuario = db.session.scalar(select(Usuario).where(Usuario.email == email_norm))
    password_hash = hashear_password(PASSWORD_PRUEBA)

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
        usuario.debe_cambiar_password = False

    existentes = set(
        db.session.scalars(
            select(DispositivoConocido.identificador).where(
                DispositivoConocido.usuario_id == usuario.id
            )
        ).all()
    )
    ahora = _ahora_utc_naive()
    for dhash in sorted(hashes_dispositivos - existentes):
        db.session.add(
            DispositivoConocido(
                usuario_id=usuario.id,
                identificador=dhash,
                ultimo_acceso=ahora,
            )
        )
    return usuario


def _asegurar_medico(
    usuario: Usuario,
    matricula: str,
    especialidades: list[Especialidad],
) -> Medico:
    medico = db.session.scalar(select(Medico).where(Medico.usuario_id == usuario.id))
    if medico is None:
        ocupada = db.session.scalar(select(Medico).where(Medico.matricula == matricula))
        mat_final = matricula if ocupada is None else f"MP-{40000 + usuario.id}"
        medico = Medico(usuario_id=usuario.id, matricula=mat_final)
        db.session.add(medico)
        db.session.flush()
    for esp in especialidades:
        if esp not in medico.especialidades:
            medico.especialidades.append(esp)
    db.session.flush()
    return medico


def _asegurar_paciente(
    *,
    usuario: Usuario,
    medico_alta: Medico,
    dni: str,
    fecha_nacimiento: date,
    patologia: Patologia,
    historia_clinica: str,
    tipo_sospecha: str,
    sintomas: list[Sintoma],
    familiares: list[dict],
    responsable_nombre: str | None = None,
    responsable_dni: str | None = None,
) -> Paciente:
    paciente = db.session.scalar(select(Paciente).where(Paciente.usuario_id == usuario.id))
    if paciente is None:
        paciente = Paciente(
            usuario_id=usuario.id,
            medico_id=medico_alta.id,
            dni=dni,
            fecha_nacimiento=fecha_nacimiento,
            diagnostico_presuntivo_id=patologia.id,
            historia_clinica=historia_clinica,
            tipo_sospecha=tipo_sospecha,
            responsable_nombre=responsable_nombre,
            responsable_dni=responsable_dni,
        )
        db.session.add(paciente)
        db.session.flush()
    elif "testing de roles" in (paciente.historia_clinica or "").lower():
        paciente.historia_clinica = historia_clinica

    sintomas_actuales = {s.id for s in paciente.sintomas}
    for s in sintomas:
        if s.id not in sintomas_actuales:
            db.session.add(PacienteSintoma(paciente_id=paciente.id, sintoma_id=s.id))

    if not paciente.familiares and familiares:
        for fam in familiares:
            db.session.add(
                Familiar(
                    paciente_id=paciente.id,
                    parentesco=fam["parentesco"],
                    nombre=fam["nombre"],
                    diagnostico_previo=fam.get("diagnostico_previo"),
                )
            )
    db.session.flush()
    return paciente


def _backfill_pacientes_existentes() -> int:
    """Inserta autorizacion inicial para pacientes previos que aun no tengan filas en la tabla."""
    ahora = _ahora_utc_naive()
    creados = 0
    for pac in db.session.scalars(select(Paciente)).all():
        ya_tiene = db.session.scalar(
            select(PacienteMedicoAutorizado.id)
            .where(PacienteMedicoAutorizado.paciente_id == pac.id)
            .limit(1)
        )
        if ya_tiene is None and pac.medico_id is not None:
            med = db.session.get(Medico, pac.medico_id)
            otorgada_por = med.usuario_id if med is not None else pac.usuario_id
            db.session.add(
                PacienteMedicoAutorizado(
                    paciente_id=pac.id,
                    medico_id=pac.medico_id,
                    otorgada_por_usuario_id=otorgada_por,
                    activa=True,
                    otorgada_en=ahora - timedelta(days=10),
                )
            )
            creados += 1
    db.session.flush()
    return creados


def _asegurar_autorizacion_activa(
    *,
    paciente: Paciente,
    medico: Medico,
    otorgada_por_uid: int,
    otorgada_en: datetime,
    motivo: str | None = None,
    crear_aviso: bool = False,
) -> bool:
    activa = db.session.scalar(
        select(PacienteMedicoAutorizado).where(
            PacienteMedicoAutorizado.paciente_id == paciente.id,
            PacienteMedicoAutorizado.medico_id == medico.id,
            PacienteMedicoAutorizado.activa.is_(True),
        )
    )
    if activa is not None:
        return False

    previas = list(
        db.session.scalars(
            select(PacienteMedicoAutorizado.medico_id).where(
                PacienteMedicoAutorizado.paciente_id == paciente.id,
                PacienteMedicoAutorizado.activa.is_(True),
            )
        ).all()
    )
    db.session.add(
        PacienteMedicoAutorizado(
            paciente_id=paciente.id,
            medico_id=medico.id,
            otorgada_por_usuario_id=otorgada_por_uid,
            activa=True,
            otorgada_en=otorgada_en,
            revocada_en=None,
        )
    )
    if motivo:
        db.session.add(
            RegistroModificacion(
                entidad_tipo=EntidadAuditable.PACIENTE,
                entidad_id=paciente.id,
                accion=TipoAccionAuditoria.MODIFICACION,
                usuario_id=otorgada_por_uid,
                origen="usuario",
                cambios={
                    "medicos_autorizados_ids": {
                        "anterior": sorted(previas),
                        "nuevo": sorted(set(previas) | {medico.id}),
                    }
                },
                motivo=motivo,
                fecha=otorgada_en,
            )
        )
    if crear_aviso:
        nombre_pac = f"{paciente.usuario.nombre} {paciente.usuario.apellido}".strip()
        db.session.add(
            Aviso(
                usuario_id=medico.usuario_id,
                mensaje=(
                    f"El paciente {nombre_pac} le otorgo autorizacion para consultar "
                    "su historia clinica."
                ),
                leido=False,
                canal=CanalAviso.APP,
                enviado=True,
                enviado_en=otorgada_en,
            )
        )
    db.session.flush()
    return True


def _asegurar_autorizacion_revocada_historica(
    *,
    paciente: Paciente,
    medico: Medico,
    otorgada_por_uid: int,
    otorgada_en: datetime,
    revocada_en: datetime,
) -> bool:
    existe = db.session.scalar(
        select(PacienteMedicoAutorizado).where(
            PacienteMedicoAutorizado.paciente_id == paciente.id,
            PacienteMedicoAutorizado.medico_id == medico.id,
        )
    )
    if existe is not None:
        return False

    db.session.add(
        PacienteMedicoAutorizado(
            paciente_id=paciente.id,
            medico_id=medico.id,
            otorgada_por_usuario_id=otorgada_por_uid,
            activa=False,
            otorgada_en=otorgada_en,
            revocada_en=revocada_en,
        )
    )
    db.session.add(
        RegistroModificacion(
            entidad_tipo=EntidadAuditable.PACIENTE,
            entidad_id=paciente.id,
            accion=TipoAccionAuditoria.MODIFICACION,
            usuario_id=otorgada_por_uid,
            origen="usuario",
            cambios={
                "medicos_autorizados_ids": {
                    "anterior": [paciente.medico_id, medico.id],
                    "nuevo": [paciente.medico_id],
                }
            },
            motivo="Fin de interconsulta neurologica (ejemplo historico revocado)",
            fecha=revocada_en,
        )
    )
    db.session.flush()
    return True


def _asegurar_indices_postgres() -> None:
    """Garantiza los indices optimizados de pacientes_medicos_autorizados si la tabla ya existia."""
    if db.engine.dialect.name != "postgresql":
        return
    db.session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_pacientes_medicos_autorizados_otorgada_por_usuario_id "
            "ON pacientes_medicos_autorizados (otorgada_por_usuario_id)"
        )
    )
    db.session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_pma_medico_activo "
            "ON pacientes_medicos_autorizados (medico_id, paciente_id) WHERE activa"
        )
    )


def cargar_ejemplos_escenario_40() -> dict:
    """Crea tabla/indices, realiza backfill y carga escenarios de prueba realistas para E40."""
    app = create_app()
    with app.app_context():
        create_tables()
        _asegurar_indices_postgres()

        hashes_dispositivos = {sha256_hex(d) for d in DISPOSITIVOS_POR_DEFECTO}
        hashes_dispositivos.update(
            db.session.scalars(select(DispositivoConocido.identificador).distinct()).all()
        )

        esp_map = _asegurar_especialidades()
        pat_fabry = _asegurar_patologia(
            "Enfermedad de Fabry",
            "Patología lisosomal ligada al cromosoma X por déficit de alfa-galactosidasa A.",
        )
        pat_pompe = _asegurar_patologia(
            "Enfermedad de Pompe",
            "Glucogenosis tipo II por déficit de alfa-glucosidasa ácida (GAA).",
        )
        pat_gaucher = _asegurar_patologia(
            "Enfermedad de Gaucher",
            "Trastorno lisosomal por déficit de glucocerebrosidasa (GBA1).",
        )

        s_acro = _asegurar_sintoma("225566008", "Acroparestesia")
        s_hipo = _asegurar_sintoma("4556007", "Hipohidrosis")
        s_debil = _asegurar_sintoma("26544005", "Debilidad muscular proximal")
        s_hepato = _asegurar_sintoma("80515008", "Hepatoesplenomegalia")
        _asegurar_patologia_sintoma(pat_fabry.id, s_acro.id, True)
        _asegurar_patologia_sintoma(pat_fabry.id, s_hipo.id, False)
        _asegurar_patologia_sintoma(pat_pompe.id, s_debil.id, True)
        _asegurar_patologia_sintoma(pat_gaucher.id, s_hepato.id, True)

        # Medicos base (@lab.com) + especialidades para directorio
        u_med_base = _asegurar_usuario(
            email="medico@lab.com",
            rol=Rol.MEDICO,
            nombre="Medico",
            apellido="Lab",
            telefono="2215100003",
            hashes_dispositivos=hashes_dispositivos,
        )
        m_base = _asegurar_medico(
            u_med_base,
            "MN-20001",
            [esp_map["Genética Médica"], esp_map["Clínica Médica"]],
        )

        u_gerente = _asegurar_usuario(
            email="gerente@lab.com",
            rol=Rol.GERENTE_MEDICO,
            nombre="Gerente",
            apellido="Medico",
            telefono="2215100004",
            hashes_dispositivos=hashes_dispositivos,
        )
        m_gerente = _asegurar_medico(u_gerente, "MN-20002", [esp_map["Genética Médica"]])

        # Asigna especialidad a cualquier otro medico preexistente sin especialidades
        for med_ext in db.session.scalars(select(Medico)).all():
            if not med_ext.especialidades:
                med_ext.especialidades.append(esp_map["Genética Médica"])

        medicos_demo: dict[str, Medico] = {}
        for item in MEDICOS_DEMO:
            u = _asegurar_usuario(
                email=item["email"],
                rol=Rol.MEDICO,
                nombre=item["nombre"],
                apellido=item["apellido"],
                telefono=item["telefono"],
                hashes_dispositivos=hashes_dispositivos,
            )
            medicos_demo[item["email"]] = _asegurar_medico(
                u,
                item["matricula"],
                [esp_map[e] for e in item["especialidades"]],
            )

        # Pacientes de ejemplo
        u_pac_base = _asegurar_usuario(
            email="paciente@lab.com",
            rol=Rol.PACIENTE,
            nombre="Paciente",
            apellido="Lab",
            telefono="2215100007",
            hashes_dispositivos=hashes_dispositivos,
        )
        p_base = _asegurar_paciente(
            usuario=u_pac_base,
            medico_alta=m_base,
            dni="40111222",
            fecha_nacimiento=date(1995, 5, 15),
            patologia=pat_fabry,
            historia_clinica=(
                "Paciente adulto de 31 años con cuadro de acroparestesias en manos y pies "
                "desde la adolescencia, hipohidrosis marcada e intolerancia al ejercicio. "
                "Antecedente materno de enfermedad renal crónica sin diagnóstico etiológico."
            ),
            tipo_sospecha="clinica",
            sintomas=[s_acro, s_hipo],
            familiares=[
                {"parentesco": "madre", "nombre": "Laura Lab", "diagnostico_previo": "Sospecha Fabry"},
                {"parentesco": "hermano", "nombre": "Nicolás Lab", "diagnostico_previo": None},
            ],
        )

        u_sofia = _asegurar_usuario(
            email="paciente.sofia@lab.com",
            rol=Rol.PACIENTE,
            nombre="Sofía",
            apellido="Morales",
            telefono="2215400201",
            hashes_dispositivos=hashes_dispositivos,
        )
        p_sofia = _asegurar_paciente(
            usuario=u_sofia,
            medico_alta=medicos_demo["hematologa@lab.com"],
            dni="40440001",
            fecha_nacimiento=date(1992, 9, 8),
            patologia=pat_pompe,
            historia_clinica=(
                "Paciente femenina de 34 años derivada por debilidad muscular proximal progresiva "
                "de cintura pelviana y elevación persistente de CPK sérica (680 U/L). "
                "Se solicita interconsulta con genética clínica para evaluación de exoma."
            ),
            tipo_sospecha="familiar",
            sintomas=[s_debil],
            familiares=[
                {"parentesco": "padre", "nombre": "Héctor Morales", "diagnostico_previo": "Miopatía proximal"},
            ],
        )

        u_lucas = _asegurar_usuario(
            email="paciente.lucas@lab.com",
            rol=Rol.PACIENTE,
            nombre="Lucas",
            apellido="Fernández",
            telefono="2215400202",
            hashes_dispositivos=hashes_dispositivos,
        )
        p_lucas = _asegurar_paciente(
            usuario=u_lucas,
            medico_alta=medicos_demo["pediatra@lab.com"],
            dni="48440002",
            fecha_nacimiento=date(2016, 3, 22),
            patologia=pat_gaucher,
            historia_clinica=(
                "Paciente pediátrico de 10 años con hepatoesplenomegalia moderada, "
                "trombocitopenia leve y dolor óseo recurrente en fémur izquierdo. "
                "Controlado en pediatría y gerencia médica; sin autorización a terceros."
            ),
            tipo_sospecha="clinica",
            sintomas=[s_hepato],
            familiares=[],
            responsable_nombre="Gustavo Fernández",
            responsable_dni="28440002",
        )

        backfill_count = _backfill_pacientes_existentes()

        ahora = _ahora_utc_naive()
        # Escenarios de autorizaciones iniciales para probar todos los casos de E40:
        # 1) paciente@lab.com: m_base (alta, activa), hematologa (autorizada activa), neurologo (revocada historica)
        _asegurar_autorizacion_activa(
            paciente=p_base,
            medico=medicos_demo["hematologa@lab.com"],
            otorgada_por_uid=u_pac_base.id,
            otorgada_en=ahora - timedelta(days=2),
            motivo="Interconsulta hematológica inicial",
            crear_aviso=True,
        )
        _asegurar_autorizacion_revocada_historica(
            paciente=p_base,
            medico=medicos_demo["neurologo@lab.com"],
            otorgada_por_uid=u_pac_base.id,
            otorgada_en=ahora - timedelta(days=5),
            revocada_en=ahora - timedelta(days=1),
        )

        # 2) paciente.sofia@lab.com: hematologa (alta, activa) + medico@lab.com (autorizado para interconsulta)
        _asegurar_autorizacion_activa(
            paciente=p_sofia,
            medico=m_base,
            otorgada_por_uid=u_sofia.id,
            otorgada_en=ahora - timedelta(hours=12),
            motivo="Interconsulta con médico tratante",
            crear_aviso=True,
        )

        # 3) paciente.lucas@lab.com: pediatra (alta, activa) + gerente@lab.com (autorizado); medico@lab.com NO autorizado (403)
        _asegurar_autorizacion_activa(
            paciente=p_lucas,
            medico=m_gerente,
            otorgada_por_uid=u_lucas.id,
            otorgada_en=ahora - timedelta(hours=6),
            motivo="Supervisión por gerencia médica",
            crear_aviso=True,
        )

        db.session.commit()

        return {
            "backfill_inicial": backfill_count,
            "pacientes": [
                {"id": p_base.id, "email": u_pac_base.email, "nombre": f"{u_pac_base.nombre} {u_pac_base.apellido}"},
                {"id": p_sofia.id, "email": u_sofia.email, "nombre": f"{u_sofia.nombre} {u_sofia.apellido}"},
                {"id": p_lucas.id, "email": u_lucas.email, "nombre": f"{u_lucas.nombre} {u_lucas.apellido}"},
            ],
            "medicos_demo": [
                {"id": m_base.id, "email": u_med_base.email, "matricula": m_base.matricula},
                {"id": m_gerente.id, "email": u_gerente.email, "matricula": m_gerente.matricula},
                *[
                    {"id": med.id, "email": email, "matricula": med.matricula}
                    for email, med in medicos_demo.items()
                ],
            ],
        }


if __name__ == "__main__":
    res = cargar_ejemplos_escenario_40()
    print(f"Escenario 40 sembrado correctamente (password: {PASSWORD_PRUEBA}, backfill={res['backfill_inicial']}):")
    print("Pacientes:")
    for p in res["pacientes"]:
        print(f" - paciente_id={p['id']} | {p['email']} | {p['nombre']}")
    print("Medicos:")
    for m in res["medicos_demo"]:
        print(f" - medico_id={m['id']} | {m['email']} | {m['matricula']}")
