"""Script idempotente para cargar datos de prueba del flujo de Turnos (Escenario 7 y 8)."""
from __future__ import annotations

import argparse
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
    Estudio,
    Medico,
    Muestra,
    OrdenDelDiaParada,
    Paciente,
    Pago,
    Patologia,
    Presupuesto,
    ResultadoAutorizacion,
    Rol,
    TipoPago,
    Turno,
    Usuario,
)
from src.core.services.seguridad import hashear_password, sha256_hex

PASSWORD_PACIENTE = "Clave1234"
EMAIL_PACIENTE = "paciente.turnos@hospital.com"
DISPOSITIVO_PACIENTE = "pc-paciente"

CENTROS_OBSOLETOS = (
    "Laboratorio Rossi - Sede Belgrano",
    "Centro Medico Diagnos - Centro",
    "Centro Extraccion Zona Norte",
)

CENTROS_SEED: list[dict] = [
    {
        "nombre": "Laboratorio BioGen - La Plata Centro",
        "direccion": "Calle 7 Nro 850, La Plata",
        "provincia": "Buenos Aires",
        "latitud": -34.9205,
        "longitud": -57.9536,
    },
    {
        "nombre": "Centro Extraccion Plaza Italia",
        "direccion": "Diag. 74 Nro 1520, La Plata",
        "provincia": "Buenos Aires",
        "latitud": -34.9102,
        "longitud": -57.9554,
    },
    {
        "nombre": "Centro Medico City Bell",
        "direccion": "Cantilo Nro 420, City Bell",
        "provincia": "Buenos Aires",
        "latitud": -34.8682,
        "longitud": -58.0468,
    },
    {
        "nombre": "Laboratorio Sur - Berisso",
        "direccion": "Av. Montevideo 1180, Berisso",
        "provincia": "Buenos Aires",
        "latitud": -34.8728,
        "longitud": -57.8842,
    },
    {
        "nombre": "Centro Diagnostico Ensenada",
        "direccion": "La Merced 240, Ensenada",
        "provincia": "Buenos Aires",
        "latitud": -34.8644,
        "longitud": -57.9114,
    },
]


def _ahora_utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _asegurar_datos_ausencias_y_historial(
    paciente: Paciente,
    medico: Medico,
    patologia: Patologia,
    centros: list[CentroExtraccion],
    estudio_principal: Estudio,
    u_paciente: Usuario,
) -> dict:
    """Carga estudios y turnos para probar historial completo y ausencias (1..4 y 5ta)."""
    ayer = date.today() - timedelta(days=1)
    hace_3_dias = date.today() - timedelta(days=3)
    hace_5_dias = date.today() - timedelta(days=5)

    # Limpiamos estudios extra previos del mismo paciente para evitar duplicados al re-ejecutar
    estudios_extra = list(
        db.session.scalars(
            select(Estudio).where(
                Estudio.paciente_id == paciente.id,
                Estudio.id != estudio_principal.id,
            )
        ).all()
    )
    for est in estudios_extra:
        db.session.execute(delete(Muestra).where(Muestra.estudio_id == est.id))
        db.session.execute(delete(Turno).where(Turno.estudio_id == est.id))
        pres = db.session.scalar(select(Presupuesto).where(Presupuesto.estudio_id == est.id))
        if pres is not None:
            db.session.execute(delete(Pago).where(Pago.presupuesto_id == pres.id))
            db.session.delete(pres)
        db.session.execute(delete(Autorizacion).where(Autorizacion.estudio_id == est.id))
        db.session.delete(est)
    db.session.flush()

    # En el estudio principal agregamos 1 turno cancelado previo para verlo en Mis Turnos -> Cancelados
    db.session.add(
        Turno(
            centro_id=centros[1 % len(centros)].id,
            paciente_id=paciente.id,
            estudio_id=estudio_principal.id,
            inicio=datetime.combine(hace_5_dias, time(10, 30)),
            activo=False,
            asistio=None,
        )
    )

    # Estudio 2: Turno ASISTIDO (con muestra tomada) -> visible en Mis Turnos -> Activos (Asistido)
    est_asistido = Estudio(
        paciente_id=paciente.id,
        medico_id=medico.id,
        patologia_sospechada_id=patologia.id,
        estado=EstadoEstudio.LISTA_PARA_RETIRAR,
        ausencias=0,
    )
    db.session.add(est_asistido)
    db.session.flush()
    t_asistido = Turno(
        centro_id=centros[0].id,
        paciente_id=paciente.id,
        estudio_id=est_asistido.id,
        inicio=datetime.combine(hace_3_dias, time(9, 45)),
        activo=True,
        asistio=True,
    )
    db.session.add(t_asistido)
    db.session.flush()
    db.session.add(
        Muestra(
            estudio_id=est_asistido.id,
            turno_id=t_asistido.id,
            tomada_en=datetime.combine(hace_3_dias, time(10, 5)),
        )
    )

    # Estudio 3: Turno vencido de ayer (0 -> 1 ausencia al correr procesar-ausencias)
    est_primera_ausencia = Estudio(
        paciente_id=paciente.id,
        medico_id=medico.id,
        patologia_sospechada_id=patologia.id,
        estado=EstadoEstudio.TURNO_SACADO,
        ausencias=0,
    )
    db.session.add(est_primera_ausencia)
    db.session.flush()
    db.session.add(
        Autorizacion(
            estudio_id=est_primera_ausencia.id,
            resultado=ResultadoAutorizacion.AUTORIZADA,
        )
    )
    t_vencido_1 = Turno(
        centro_id=centros[2 % len(centros)].id,
        paciente_id=paciente.id,
        estudio_id=est_primera_ausencia.id,
        inicio=datetime.combine(ayer, time(10, 0)),
        activo=True,
        asistio=None,
    )
    db.session.add(t_vencido_1)

    # Estudio 4: Al borde del limite (4 ausencias previas + Pago vigente + turno vencido de ayer -> 5ta ausencia anula pago)
    est_quinta_ausencia = Estudio(
        paciente_id=paciente.id,
        medico_id=medico.id,
        patologia_sospechada_id=patologia.id,
        estado=EstadoEstudio.TURNO_SACADO,
        ausencias=4,
    )
    db.session.add(est_quinta_ausencia)
    db.session.flush()
    presupuesto = Presupuesto(
        estudio_id=est_quinta_ausencia.id,
        emitido_por_id=u_paciente.id,
        cantidad_genes=5,
        monto_total_usd=Decimal("500.00"),
    )
    db.session.add(presupuesto)
    db.session.flush()
    pago = Pago(
        presupuesto_id=presupuesto.id,
        tipo=TipoPago.PARTICULAR,
        monto_usd=Decimal("500.00"),
        anulado=False,
    )
    db.session.add(pago)
    t_vencido_5 = Turno(
        centro_id=centros[3 % len(centros)].id,
        paciente_id=paciente.id,
        estudio_id=est_quinta_ausencia.id,
        inicio=datetime.combine(ayer, time(11, 15)),
        activo=True,
        asistio=None,
    )
    db.session.add(t_vencido_5)
    db.session.flush()

    return {
        "estudio_asistido_id": est_asistido.id,
        "estudio_vencido_1_id": est_primera_ausencia.id,
        "turno_vencido_1_id": t_vencido_1.id,
        "estudio_vencido_5_id": est_quinta_ausencia.id,
        "turno_vencido_5_id": t_vencido_5.id,
    }


def cargar_datos_turnos(
    email_paciente: str = EMAIL_PACIENTE,
    password: str = PASSWORD_PACIENTE,
    dispositivo_id: str | None = None,
    con_ausencias: bool = False,
) -> dict:
    email_norm = email_paciente.strip().lower()
    dispositivo = (dispositivo_id or DISPOSITIVO_PACIENTE).strip()

    app = create_app()
    with app.app_context():
        create_tables()

        # 1. Patologia base
        patologia = db.session.scalar(
            select(Patologia).where(Patologia.nombre == "Enfermedad de Fabry")
        )
        if patologia is None:
            patologia = Patologia(
                nombre="Enfermedad de Fabry",
                descripcion="Patologia lisosomal para pruebas.",
            )
            db.session.add(patologia)
            db.session.flush()

        # 2. Medico base
        u_medico = db.session.scalar(
            select(Usuario).where(Usuario.email == "medico.turnos@hospital.com")
        )
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

        # 3. Paciente titular (nuevo o existente por email)
        u_paciente = db.session.scalar(select(Usuario).where(Usuario.email == email_norm))
        if u_paciente is None:
            u_paciente = Usuario(
                email=email_norm,
                password_hash=hashear_password(password),
                rol=Rol.PACIENTE,
                nombre="Juan",
                apellido="Perez",
                telefono="1144556677",
                debe_cambiar_password=False,
            )
            db.session.add(u_paciente)
            db.session.flush()
        else:
            if u_paciente.rol != Rol.PACIENTE:
                raise ValueError(
                    f"El usuario {email_norm} ya existe con rol '{u_paciente.rol.value}' (se esperaba 'paciente')."
                )
            u_paciente.password_hash = hashear_password(password)
            u_paciente.debe_cambiar_password = False

        # Registrar dispositivo conocido si se especifico o el por defecto
        disp = db.session.scalar(
            select(DispositivoConocido).where(
                DispositivoConocido.usuario_id == u_paciente.id,
                DispositivoConocido.identificador == sha256_hex(dispositivo),
            )
        )
        if disp is None:
            disp = DispositivoConocido(
                usuario_id=u_paciente.id,
                identificador=sha256_hex(dispositivo),
                ultimo_acceso=_ahora_utc_naive(),
            )
            db.session.add(disp)

        paciente = db.session.scalar(select(Paciente).where(Paciente.usuario_id == u_paciente.id))
        if paciente is None:
            dni_base = "32444555"
            dni_ocupado = db.session.scalar(select(Paciente.id).where(Paciente.dni == dni_base))
            dni_nuevo = f"90{u_paciente.id:06d}" if dni_ocupado is not None else dni_base
            paciente = Paciente(
                usuario_id=u_paciente.id,
                medico_id=medico.id,
                dni=dni_nuevo,
                fecha_nacimiento=date(1992, 4, 10),
                diagnostico_presuntivo_id=patologia.id,
                historia_clinica="Paciente para pruebas de turnos.",
                tipo_sospecha="clinica",
            )
            db.session.add(paciente)
            db.session.flush()

        # 4. Limpiar centros obsoletos de CABA si no tienen turnos ni paradas asociadas
        for nombre_viejo in CENTROS_OBSOLETOS:
            viejo = db.session.scalar(
                select(CentroExtraccion).where(CentroExtraccion.nombre == nombre_viejo)
            )
            if viejo is None:
                continue
            tiene_turnos = db.session.scalar(
                select(Turno.id).where(Turno.centro_id == viejo.id).limit(1)
            )
            tiene_paradas = db.session.scalar(
                select(OrdenDelDiaParada.id).where(OrdenDelDiaParada.centro_id == viejo.id).limit(1)
            )
            if tiene_turnos is None and tiene_paradas is None:
                db.session.delete(viejo)
        db.session.flush()

        # 5. Centros de extraccion en La Plata y alrededores
        centros_creados: list[CentroExtraccion] = []
        for datos_centro in CENTROS_SEED:
            centro = db.session.scalar(
                select(CentroExtraccion).where(CentroExtraccion.nombre == datos_centro["nombre"])
            )
            if centro is None:
                centro = CentroExtraccion(**datos_centro)
                db.session.add(centro)
                db.session.flush()
            centros_creados.append(centro)

        # 6. Estudio en estado AUTORIZADO (con su Autorizacion real para que soporte cancelacion/reprogramacion)
        estudio = db.session.scalar(
            select(Estudio)
            .where(
                Estudio.paciente_id == paciente.id,
                Estudio.estado.in_(
                    [EstadoEstudio.CREADO, EstadoEstudio.AUTORIZADO, EstadoEstudio.TURNO_SACADO]
                ),
            )
            .order_by(Estudio.id.desc())
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
            db.session.execute(delete(Turno).where(Turno.estudio_id == estudio.id))
            estudio.estado = EstadoEstudio.AUTORIZADO
            estudio.ausencias = 0

        autorizacion = db.session.scalar(
            select(Autorizacion).where(
                Autorizacion.estudio_id == estudio.id,
                Autorizacion.resultado == ResultadoAutorizacion.AUTORIZADA,
            )
        )
        if autorizacion is None:
            db.session.add(
                Autorizacion(
                    estudio_id=estudio.id,
                    resultado=ResultadoAutorizacion.AUTORIZADA,
                )
            )

        extra_ausencias = None
        if con_ausencias:
            extra_ausencias = _asegurar_datos_ausencias_y_historial(
                paciente=paciente,
                medico=medico,
                patologia=patologia,
                centros=centros_creados,
                estudio_principal=estudio,
                u_paciente=u_paciente,
            )

        db.session.commit()

        return {
            "usuario_email": u_paciente.email,
            "password": password,
            "dispositivo": dispositivo,
            "estudio_id": estudio.id,
            "centro_id": centros_creados[0].id,
            "centro_nombre": centros_creados[0].nombre,
            "total_centros": len(centros_creados),
            "extra_ausencias": extra_ausencias,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga datos de prueba para Solicitar Turno.")
    parser.add_argument(
        "--email",
        default=EMAIL_PACIENTE,
        help="Email del paciente (puede ser uno nuevo o uno existente; usa tu mail real si queres recibir el codigo 2FA).",
    )
    parser.add_argument(
        "--password",
        default=PASSWORD_PACIENTE,
        help="Contrasena del paciente (por defecto: Clave1234).",
    )
    parser.add_argument(
        "--dispositivo-id",
        default=None,
        help="UUID de localStorage 'exoma_dispositivo_id' para omitir verificacion 2FA de maquina nueva.",
    )
    parser.add_argument(
        "--con-ausencias",
        action="store_true",
        help="Carga ademas turnos asistidos, cancelados y 2 turnos vencidos listos para probar procesar-ausencias (1ra y 5ta ausencia).",
    )
    args = parser.parse_args()

    datos = cargar_datos_turnos(
        email_paciente=args.email,
        password=args.password,
        dispositivo_id=args.dispositivo_id,
        con_ausencias=args.con_ausencias,
    )
    print("=========================================================")
    print("DATOS SEMILLA CARGADOS PARA TURNOS (LA PLATA):")
    print("=========================================================")
    print(f"Login Email:     {datos['usuario_email']}")
    print(f"Login Password:  {datos['password']}")
    print(f"Dispositivo ID:  {datos['dispositivo']}")
    print(f"Estudio ID:      {datos['estudio_id']} (Estado: Autorizado)")
    print(f"Centros listos:  {datos['total_centros']} (principal: #{datos['centro_id']} {datos['centro_nombre']})")
    if datos["extra_ausencias"]:
        ext = datos["extra_ausencias"]
        print("---------------------------------------------------------")
        print("ESCENARIOS DE HISTORIAL Y AUSENCIAS CARGADOS:")
        print(f" - Estudio #{ext['estudio_asistido_id']}: turno Asistido (con muestra)")
        print(f" - Estudio #{ext['estudio_vencido_1_id']}: turno vencido #{ext['turno_vencido_1_id']} (0->1 ausencia)")
        print(f" - Estudio #{ext['estudio_vencido_5_id']}: turno vencido #{ext['turno_vencido_5_id']} (4->5 ausencia, anula pago)")
        print("Ejecuta: poetry run flask --app main procesar-ausencias")
    print("=========================================================")


if __name__ == "__main__":
    main()
