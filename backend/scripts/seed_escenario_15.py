"""Script idempotente para preparar 4 estudios de prueba para Escenario 15 (Bioinformatica)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import Enum, inspect, select, text
from src import create_app
from src.core.database import create_tables, db
from src.core.models import (
    Analisis,
    AnalisisGen,
    ConclusionDiagnostica,
    DatosCrudos,
    EstadoEstudio,
    Estudio,
    EstudioGen,
    Gen,
    Medico,
    OrigenGen,
    Paciente,
    Patologia,
    PatologiaGen,
    TipoAnalisis,
    Usuario,
)
from src.core.services import resultado_service

ESTUDIOS_PRUEBA: list[dict] = [
    {
        "patologia": "Enfermedad de Fabry",
        "patologia_desc": "Patologia lisosomal ligada al X.",
        "estado": EstadoEstudio.EN_VIAJE_COREA,
        "es_pompe_urgente": False,
        "quiere_hallazgos_secundarios": True,
        "genes": [
            ("GLA", "Galactosidasa alfa", False, OrigenGen.PATOLOGIA),
            ("BRCA1", "BRCA1 DNA repair associated", True, OrigenGen.HALLAZGO_SECUNDARIO),
        ],
        "offset_horas": -3,
        "caso": "Listo en administrativo para cargar ACTG (normal)",
    },
    {
        "patologia": "Enfermedad de Pompe",
        "patologia_desc": "Glucogenosis tipo II por deficit de GAA.",
        "estado": EstadoEstudio.EN_VIAJE_COREA,
        "es_pompe_urgente": True,
        "quiere_hallazgos_secundarios": True,
        "genes": [
            ("GAA", "Glucosidasa alfa acida", False, OrigenGen.PATOLOGIA),
            ("BRCA2", "BRCA2 DNA repair associated", True, OrigenGen.HALLAZGO_SECUNDARIO),
        ],
        "offset_horas": -1,
        "caso": "Listo en administrativo para cargar ACTG (Pompe urgente)",
    },
    {
        "patologia": "Enfermedad de Pompe",
        "patologia_desc": "Glucogenosis tipo II por deficit de GAA.",
        "estado": EstadoEstudio.EN_ANALISIS_BIOINFORMATICA,
        "es_pompe_urgente": True,
        "quiere_hallazgos_secundarios": True,
        "genes": [
            ("GAA", "Glucosidasa alfa acida", False, OrigenGen.PATOLOGIA),
            ("BRCA1", "BRCA1 DNA repair associated", True, OrigenGen.HALLAZGO_SECUNDARIO),
        ],
        "offset_horas": 0,
        "caso": "En bandeja de bioinformatica (Pompe urgente, debe salir primero)",
    },
    {
        "patologia": "Enfermedad de Gaucher",
        "patologia_desc": "Patologia lisosomal por deficit de glucocerebrosidasa.",
        "estado": EstadoEstudio.EN_ANALISIS_BIOINFORMATICA,
        "es_pompe_urgente": False,
        "quiere_hallazgos_secundarios": False,
        "genes": [
            ("GBA1", "Glucosilceramidasa beta 1", False, OrigenGen.PATOLOGIA),
            ("SMPD1", "Esfingomielinasa acida", False, OrigenGen.MANUAL),
        ],
        "offset_horas": -2,
        "caso": "En bandeja de bioinformatica (normal, multi-gen)",
    },
]


def _ahora_utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _asegurar_columnas_escenario_15() -> None:
    """Sincroniza columnas nuevas de Escenario 15 si la BD PostgreSQL ya existia."""
    if db.engine.dialect.name != "postgresql":
        return

    insp = inspect(db.engine)
    cols_estudios = {c["name"] for c in insp.get_columns("estudios")}
    cols_resultados = {c["name"] for c in insp.get_columns("resultados")}

    if "fecha_reevaluacion_vus" not in cols_estudios:
        db.session.execute(
            text("ALTER TABLE estudios ADD COLUMN IF NOT EXISTS fecha_reevaluacion_vus DATE")
        )
        db.session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_estudios_fecha_reevaluacion_vus "
                "ON estudios (fecha_reevaluacion_vus)"
            )
        )

    if "diagnostico" not in cols_resultados or "fecha_proximo_estudio" not in cols_resultados:
        Enum(ConclusionDiagnostica).create(db.engine, checkfirst=True)
        db.session.execute(
            text(
                "ALTER TABLE resultados ADD COLUMN IF NOT EXISTS "
                "diagnostico conclusiondiagnostica NOT NULL DEFAULT 'NEGATIVO'"
            )
        )
        db.session.execute(
            text("ALTER TABLE resultados ADD COLUMN IF NOT EXISTS fecha_proximo_estudio DATE")
        )
        db.session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_resultados_fecha_proximo_estudio "
                "ON resultados (fecha_proximo_estudio)"
            )
        )

    db.session.commit()


def _asegurar_patologia(nombre: str, descripcion: str) -> Patologia:
    patologia = db.session.scalar(select(Patologia).where(Patologia.nombre == nombre))
    if patologia is None:
        patologia = Patologia(nombre=nombre, descripcion=descripcion)
        db.session.add(patologia)
        db.session.flush()
    return patologia


def _asegurar_gen(simbolo: str, nombre: str, es_hallazgo_secundario: bool) -> Gen:
    gen = db.session.scalar(select(Gen).where(Gen.simbolo == simbolo))
    if gen is None:
        gen = Gen(
            simbolo=simbolo,
            nombre=nombre,
            es_hallazgo_secundario=es_hallazgo_secundario,
        )
        db.session.add(gen)
        db.session.flush()
    return gen


def _asegurar_patologia_gen(patologia_id: int, gen_id: int) -> None:
    rel = db.session.scalar(
        select(PatologiaGen).where(
            PatologiaGen.patologia_id == patologia_id,
            PatologiaGen.gen_id == gen_id,
        )
    )
    if rel is None:
        db.session.add(PatologiaGen(patologia_id=patologia_id, gen_id=gen_id))


def cargar_estudios_escenario_15() -> tuple[bool, list[dict]]:
    """Carga 4 estudios de prueba si el paciente de laboratorio aun no tiene estudios."""
    app = create_app()
    resumen: list[dict] = []

    with app.app_context():
        create_tables()
        _asegurar_columnas_escenario_15()

        u_admin = db.session.scalar(select(Usuario).where(Usuario.email == "administrativo@lab.com"))
        u_medico = db.session.scalar(select(Usuario).where(Usuario.email == "medico@lab.com"))
        u_paciente = db.session.scalar(select(Usuario).where(Usuario.email == "paciente@lab.com"))

        if not (u_admin and u_medico and u_paciente):
            raise RuntimeError(
                "Faltan usuarios @lab.com. Ejecuta primero: poetry run python scripts/seed_roles.py"
            )

        medico = db.session.scalar(select(Medico).where(Medico.usuario_id == u_medico.id))
        paciente = db.session.scalar(select(Paciente).where(Paciente.usuario_id == u_paciente.id))
        if not (medico and paciente):
            raise RuntimeError(
                "Faltan perfiles de medico/paciente @lab.com. Ejecuta primero scripts/seed_roles.py"
            )

        existentes = list(
            db.session.scalars(
                select(Estudio)
                .where(Estudio.paciente_id == paciente.id)
                .order_by(Estudio.id.asc())
            ).all()
        )
        if len(existentes) >= len(ESTUDIOS_PRUEBA):
            for est in existentes[: len(ESTUDIOS_PRUEBA)]:
                resumen.append(
                    {
                        "id": est.id,
                        "estado": est.estado.value,
                        "patologia": est.patologia_sospechada.nombre,
                        "pompe_urgente": est.es_pompe_urgente,
                        "caso": "Ya existente en BD",
                    }
                )
            return False, resumen

        ahora = _ahora_utc_naive()
        archivos_escritos: list = []
        try:
            for spec in ESTUDIOS_PRUEBA:
                patologia = _asegurar_patologia(spec["patologia"], spec["patologia_desc"])
                ts = ahora + timedelta(hours=spec["offset_horas"])

                estudio = Estudio(
                    paciente_id=paciente.id,
                    medico_id=medico.id,
                    patologia_sospechada_id=patologia.id,
                    estado=spec["estado"],
                    quiere_hallazgos_secundarios=spec["quiere_hallazgos_secundarios"],
                    es_pompe_urgente=spec["es_pompe_urgente"],
                    created_at=ts,
                    updated_at=ts,
                )
                db.session.add(estudio)
                db.session.flush()

                genes_ids: list[int] = []
                for simbolo, nombre_gen, es_hs, origen in spec["genes"]:
                    gen = _asegurar_gen(simbolo, nombre_gen, es_hs)
                    if origen == OrigenGen.PATOLOGIA:
                        _asegurar_patologia_gen(patologia.id, gen.id)
                    db.session.add(
                        EstudioGen(estudio_id=estudio.id, gen_id=gen.id, origen=origen)
                    )
                    genes_ids.append(gen.id)

                if spec["estado"] == EstadoEstudio.EN_ANALISIS_BIOINFORMATICA:
                    archivo_rel = f"storage/datos_crudos/estudio_{estudio.id}.txt"
                    ruta_fisica = resultado_service.resolver_ruta_storage(archivo_rel)
                    ruta_fisica.parent.mkdir(parents=True, exist_ok=True)
                    contenido = (
                        f">estudio_{estudio.id}_{patologia.nombre.replace(' ', '_')}\n"
                        + ("ATCGGCTAGCTAGCTAATCGATCGATCGATCG\n" * 4)
                    )
                    ruta_fisica.write_text(contenido, encoding="utf-8")
                    archivos_escritos.append(ruta_fisica)

                    db.session.add(
                        DatosCrudos(
                            estudio_id=estudio.id,
                            cargado_por_id=u_admin.id,
                            archivo_path=archivo_rel,
                            cargado_en=ts,
                        )
                    )
                    analisis = Analisis(
                        estudio_id=estudio.id,
                        tipo=TipoAnalisis.INICIAL,
                        bioinformatico_id=None,
                        created_at=ts,
                    )
                    db.session.add(analisis)
                    db.session.flush()
                    for gid in genes_ids:
                        db.session.add(AnalisisGen(analisis_id=analisis.id, gen_id=gid))

                resumen.append(
                    {
                        "id": estudio.id,
                        "estado": estudio.estado.value,
                        "patologia": patologia.nombre,
                        "pompe_urgente": estudio.es_pompe_urgente,
                        "caso": spec["caso"],
                    }
                )

            db.session.commit()
        except Exception:
            db.session.rollback()
            for ruta in archivos_escritos:
                ruta.unlink(missing_ok=True)
            raise

    return True, resumen


if __name__ == "__main__":
    creados, filas = cargar_estudios_escenario_15()
    titulo = (
        "4 estudios de prueba creados para Escenario 15:"
        if creados
        else "Estudios de prueba ya existentes en BD:"
    )
    print(titulo)
    for fila in filas:
        print(
            f" - Estudio #{fila['id']} | {fila['estado']} | {fila['patologia']} | "
            f"pompe_urgente={fila['pompe_urgente']} | {fila['caso']}"
        )
