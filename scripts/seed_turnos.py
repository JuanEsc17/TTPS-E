"""Script para cargar en la BD los datos necesarios para probar el flujo de Turnos en Postman."""
from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import delete, select
from src import create_app
from src.core.database import create_tables, db
from src.core.models import (
    CentroExtraccion,
    DispositivoConocido,
    EstadoEstudio,
    Estudio,
    Medico,
    Paciente,
    Patologia,
    Rol,
    Turno,
    Usuario,
)
from src.core.services.seguridad import hashear_password, sha256_hex

PASSWORD_PACIENTE = "Clave1234"
EMAIL_PACIENTE = "paciente.turnos@hospital.com"
DISPOSITIVO_PACIENTE = "pc-paciente"


def _ahora_utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def cargar_datos_turnos() -> dict:
    app = create_app()
    with app.app_context():
        create_tables()

        # 1. Patologia base
        patologia = db.session.scalar(select(Patologia).where(Patologia.nombre == "Enfermedad de Fabry"))
        if patologia is None:
            patologia = Patologia(
                nombre="Enfermedad de Fabry",
                descripcion="Patologia lisosomal para pruebas.",
            )
            db.session.add(patologia)
            db.session.flush()

        # 2. Medico base
        u_medico = db.session.scalar(select(Usuario).where(Usuario.email == "medico.turnos@hospital.com"))
        if u_medico is None:
            u_medico = Usuario(
                email="medico.turnos@hospital.com",
                password_hash=hashear_password(PASSWORD_PACIENTE),
                rol=Rol.MEDICO,
                nombre="Carlos",
                apellido="Gomez",
                telefono="1122334455",
                debe_cambiar_password=False,
            )
            db.session.add(u_medico)
            db.session.flush()

        medico = db.session.scalar(select(Medico).where(Medico.usuario_id == u_medico.id))
        if medico is None:
            medico = Medico(usuario_id=u_medico.id, matricula="MN-45001")
            db.session.add(medico)
            db.session.flush()

        # 3. Paciente titular
        u_paciente = db.session.scalar(select(Usuario).where(Usuario.email == EMAIL_PACIENTE))
        if u_paciente is None:
            u_paciente = Usuario(
                email=EMAIL_PACIENTE,
                password_hash=hashear_password(PASSWORD_PACIENTE),
                rol=Rol.PACIENTE,
                nombre="Juan",
                apellido="Perez",
                telefono="1144556677",
                debe_cambiar_password=False,
            )
            db.session.add(u_paciente)
            db.session.flush()
        else:
            u_paciente.password_hash = hashear_password(PASSWORD_PACIENTE)
            u_paciente.debe_cambiar_password = False

        # Registrar dispositivo conocido para que el login devuelva AUTENTICADO directamente
        disp = db.session.scalar(
            select(DispositivoConocido).where(
                DispositivoConocido.usuario_id == u_paciente.id,
                DispositivoConocido.identificador == sha256_hex(DISPOSITIVO_PACIENTE),
            )
        )
        if disp is None:
            disp = DispositivoConocido(
                usuario_id=u_paciente.id,
                identificador=sha256_hex(DISPOSITIVO_PACIENTE),
                ultimo_acceso=_ahora_utc_naive(),
            )
            db.session.add(disp)

        paciente = db.session.scalar(select(Paciente).where(Paciente.usuario_id == u_paciente.id))
        if paciente is None:
            paciente = Paciente(
                usuario_id=u_paciente.id,
                medico_id=medico.id,
                dni="32444555",
                fecha_nacimiento=date(1992, 4, 10),
                diagnostico_presuntivo_id=patologia.id,
                historia_clinica="Paciente para pruebas de turnos en Postman.",
                tipo_sospecha="clinica",
            )
            db.session.add(paciente)
            db.session.flush()

        # 4. Centro de extraccion
        centro = db.session.scalar(select(CentroExtraccion).where(CentroExtraccion.nombre == "Laboratorio Rossi - Sede Belgrano"))
        if centro is None:
            centro = CentroExtraccion(
                nombre="Laboratorio Rossi - Sede Belgrano",
                direccion="Av. Cabildo 2040, CABA",
                provincia="Buenos Aires",
                latitud=-34.5612,
                longitud=-58.4567,
            )
            db.session.add(centro)
            db.session.flush()

        # 5. Estudio en estado AUTORIZADO (limpiando turnos previos del estudio si existieran para resetear la prueba)
        estudio = db.session.scalar(
            select(Estudio).where(
                Estudio.paciente_id == paciente.id,
                Estudio.estado.in_([EstadoEstudio.AUTORIZADO, EstadoEstudio.TURNO_SACADO]),
            )
        )
        if estudio is None:
            estudio = Estudio(
                paciente_id=paciente.id,
                medico_id=medico.id,
                patologia_sospechada_id=patologia.id,
                estado=EstadoEstudio.AUTORIZADO,
            )
            db.session.add(estudio)
            db.session.flush()
        else:
            # Resetear para volver a probar
            db.session.execute(delete(Turno).where(Turno.estudio_id == estudio.id))
            estudio.estado = EstadoEstudio.AUTORIZADO
            estudio.ausencias = 0

        db.session.commit()

        return {
            "usuario_email": u_paciente.email,
            "password": PASSWORD_PACIENTE,
            "dispositivo": DISPOSITIVO_PACIENTE,
            "estudio_id": estudio.id,
            "centro_id": centro.id,
            "centro_nombre": centro.nombre,
        }


if __name__ == "__main__":
    datos = cargar_datos_turnos()
    print("=========================================================")
    print("DATOS SEMILLA CARGADOS PARA POSTMAN:")
    print("=========================================================")
    print(f"Login Email:     {datos['usuario_email']}")
    print(f"Login Password:  {datos['password']}")
    print(f"Dispositivo ID:  {datos['dispositivo']}")
    print(f"Estudio ID:      {datos['estudio_id']} (Estado: Autorizado)")
    print(f"Centro ID:       {datos['centro_id']} ({datos['centro_nombre']})")
    print("=========================================================")

