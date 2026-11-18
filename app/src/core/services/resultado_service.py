"""Servicio para generacion y notificacion de resultados de exoma (Escenario 16)."""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flask import current_app, has_app_context
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from src.clients import (
    ClienteConexionError,
    ClienteError,
    ClienteServicioError,
    EmailClient,
)
from src.core.models import (
    Analisis,
    Aviso,
    CanalAviso,
    ConclusionDiagnostica,
    EntidadAuditable,
    EstadoEstudio,
    Estudio,
    Resultado,
    TipoAccionAuditoria,
    Variante,
    calcular_conclusion_diagnostica,
)
from src.core.repos import bioinformatica_repo
from src.core.services import auditoria_service
from src.core.services.excepciones import ErrorDominio

logger = logging.getLogger(__name__)
_EMAIL_CLIENT_ORIGINAL = EmailClient


def ahora_utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def resolver_ruta_storage(ruta_relativa: str) -> Path:
    """Resuelve una ruta logica 'storage/...' dentro del directorio de almacenamiento configurado."""
    if has_app_context() and current_app.config.get("STORAGE_DIR"):
        base_dir = Path(str(current_app.config["STORAGE_DIR"])).resolve()
    else:
        base_dir = (Path(__file__).resolve().parents[3] / "storage").resolve()

    limpia = ruta_relativa.replace("\\", "/").lstrip("/")
    limpia = limpia.removeprefix("storage/")

    ruta_fisica = (base_dir / limpia).resolve()
    if not ruta_fisica.is_relative_to(base_dir):
        raise ErrorDominio(
            "Ruta de archivo fuera del directorio permitido.",
            codigo="RUTA_ARCHIVO_INVALIDA",
            http_status=400,
        )
    return ruta_fisica


def resolver_email_client(
    email_client: EmailClient | None = None,
    *,
    cliente_cls: type[EmailClient] = EmailClient,
) -> EmailClient | None:
    """Resuelve el cliente de correo respetando mocks inyectados y modo TESTING."""
    if email_client is not None:
        return email_client
    if has_app_context():
        configurado = (
            current_app.config.get("EMAIL_CLIENT")
            or current_app.extensions.get("email_client")
        )
        if configurado is not None:
            return configurado
        if (
            current_app.config.get("TESTING")
            and cliente_cls is _EMAIL_CLIENT_ORIGINAL
            and EmailClient is _EMAIL_CLIENT_ORIGINAL
        ):
            return None
    return cliente_cls()


def enviar_email_resiliente(
    cliente: EmailClient | None,
    *,
    asunto: str,
    mensaje: str,
    destinatarios: list[str],
    referencia: str,
    idempotency_key: str | None = None,
) -> bool:
    """Envia correo con 3 reintentos ante errores transitorios sin romper el flujo principal."""
    destinos_limpios = [d.strip() for d in destinatarios if d and d.strip()]
    if cliente is None or not destinos_limpios:
        return False

    for intento in range(3):
        try:
            cliente.enviar_aviso(
                asunto=asunto,
                mensaje=mensaje,
                destinatarios=destinos_limpios,
                referencia=referencia,
                idempotency_key=idempotency_key,
            )
            return True
        except (ClienteConexionError, ClienteServicioError) as exc:
            logger.warning(
                "[mail_client] fallo transitorio envio referencia=%s intento=%s err=%s",
                referencia,
                intento + 1,
                exc,
            )
            if intento < 2:
                time.sleep(2 ** intento)
        except (ClienteError, OSError) as exc:
            logger.warning(
                "[mail_client] error envio referencia=%s err=%s",
                referencia,
                exc,
            )
            return False
    return False


def _texto_latin1(valor: Any) -> str:
    return str(valor or "-").encode("latin-1", "replace").decode("latin-1")


def _generar_pdf_resultado(
    *,
    estudio: Estudio,
    analisis: Analisis,
    variantes: list[Variante],
    diagnostico: ConclusionDiagnostica,
    fecha_proximo_estudio: Any,
    generado_en: datetime,
    ruta_fisica: Path,
) -> None:
    """Compila el informe clinico del estudio en PDF usando fpdf2."""
    try:
        ruta_fisica.parent.mkdir(parents=True, exist_ok=True)
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        pdf.set_font("Helvetica", "B", 15)
        pdf.cell(
            0,
            10,
            _texto_latin1("Laboratorio de Exoma Clinico - Informe de Resultado"),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )

        pdf.set_font("Helvetica", "", 10)
        pdf.cell(
            0,
            6,
            _texto_latin1(
                f"Estudio #{estudio.id} | Analisis #{analisis.id} ({analisis.tipo.value}) | "
                f"Fecha: {generado_en.strftime('%d/%m/%Y %H:%M')}"
            ),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.ln(3)

        paciente_u = estudio.paciente.usuario if estudio.paciente else None
        medico_u = estudio.medico.usuario if estudio.medico else None
        patologia = estudio.patologia_sospechada

        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, _texto_latin1("Datos clinicos"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 10)
        if paciente_u and estudio.paciente:
            pdf.cell(
                0,
                6,
                _texto_latin1(
                    f"Paciente: {paciente_u.nombre} {paciente_u.apellido} | "
                    f"DNI: {estudio.paciente.dni} | Nacimiento: {estudio.paciente.fecha_nacimiento}"
                ),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
        if medico_u and estudio.medico:
            pdf.cell(
                0,
                6,
                _texto_latin1(
                    f"Medico tratante: {medico_u.nombre} {medico_u.apellido} (Mat. {estudio.medico.matricula})"
                ),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
        if patologia:
            pdf.cell(
                0,
                6,
                _texto_latin1(f"Patologia sospechada: {patologia.nombre}"),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )

        simbolos_genes = ", ".join(
            sorted({ag.gen.simbolo for ag in analisis.genes if ag.gen is not None})
        ) or "Sin genes asociados"
        pdf.multi_cell(
            0,
            6,
            _texto_latin1(f"Genes analizados: {simbolos_genes}"),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.ln(3)

        etiqueta_diag = {
            ConclusionDiagnostica.POSITIVO: "POSITIVO (variante patogenica detectada)",
            ConclusionDiagnostica.VUS: "VUS (Variante de Significado Incierto)",
            ConclusionDiagnostica.NEGATIVO: "NEGATIVO (sin variantes patogenicas ni VUS)",
        }[diagnostico]
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(
            0,
            8,
            _texto_latin1(f"Conclusion diagnostica: {etiqueta_diag}"),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )

        if diagnostico == ConclusionDiagnostica.VUS and fecha_proximo_estudio is not None:
            pdf.set_font("Helvetica", "B", 10)
            pdf.multi_cell(
                0,
                6,
                _texto_latin1(
                    f"Recomendacion de nuevo estudio / reevaluacion VUS: "
                    f"{fecha_proximo_estudio.strftime('%d/%m/%Y')} ({fecha_proximo_estudio.isoformat()})"
                ),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
        pdf.ln(3)

        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, _texto_latin1("Variantes encontradas"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 10)
        if not variantes:
            pdf.cell(
                0,
                6,
                _texto_latin1("No se detectaron variantes respecto al genoma de referencia."),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
        else:
            for v in variantes:
                simbolo = v.gen.simbolo if v.gen else f"Gen#{v.gen_id}"
                clinvar = v.clinvar_id or "-"
                pdf.multi_cell(
                    0,
                    6,
                    _texto_latin1(
                        f"- {simbolo} | {v.notacion} | ClinVar: {clinvar} | Clasificacion: {v.clasificacion.value}"
                    ),
                    new_x=XPos.LMARGIN,
                    new_y=YPos.NEXT,
                )

        pdf.output(str(ruta_fisica))
    except Exception as exc:
        ruta_fisica.unlink(missing_ok=True)
        raise ErrorDominio(
            "No se pudo generar el informe PDF del resultado. Intente nuevamente.",
            codigo="ERROR_GENERACION_PDF_RESULTADO",
            http_status=500,
            reintentable=True,
        ) from exc


def preparar_resultado_en_transaccion(
    *,
    estudio: Estudio,
    analisis: Analisis,
    variantes: list[Variante],
    usuario_bioinformatico_id: int,
    ip_origen: str | None = None,
) -> tuple[Resultado, Path, list[Aviso], dict[str, Any]]:
    """Genera el PDF, crea Resultado, pasa el Estudio a Resultado cargado y encola Avisos."""
    ahora = ahora_utc_naive()
    positivo, diagnostico, fecha_proximo_estudio = calcular_conclusion_diagnostica(
        variantes,
        fecha_base=ahora.date(),
    )

    pdf_path_rel = f"storage/resultados/resultado_analisis_{analisis.id}.pdf"
    ruta_fisica = resolver_ruta_storage(pdf_path_rel)
    _generar_pdf_resultado(
        estudio=estudio,
        analisis=analisis,
        variantes=variantes,
        diagnostico=diagnostico,
        fecha_proximo_estudio=fecha_proximo_estudio,
        generado_en=ahora,
        ruta_fisica=ruta_fisica,
    )

    logger.info(
        "[resultado_service] pdf_generado estudio_id=%s analisis_id=%s positivo=%s path=%r",
        estudio.id,
        analisis.id,
        positivo,
        pdf_path_rel,
    )

    resultado = bioinformatica_repo.crear_resultado(
        analisis_id=analisis.id,
        positivo=positivo,
        diagnostico=diagnostico,
        fecha_proximo_estudio=fecha_proximo_estudio,
        pdf_path=pdf_path_rel,
        generado_en=ahora,
    )

    estado_anterior = estudio.estado.value
    fecha_vus_anterior = (
        estudio.fecha_reevaluacion_vus.isoformat()
        if estudio.fecha_reevaluacion_vus
        else None
    )
    estudio.estado = EstadoEstudio.RESULTADO_CARGADO
    estudio.fecha_reevaluacion_vus = fecha_proximo_estudio
    fecha_vus_nueva = fecha_proximo_estudio.isoformat() if fecha_proximo_estudio else None

    auditoria_service.registrar_modificacion(
        entidad_tipo=EntidadAuditable.ESTUDIO,
        entidad_id=estudio.id,
        accion=TipoAccionAuditoria.CAMBIO_ESTADO,
        usuario_id=usuario_bioinformatico_id,
        origen="usuario",
        cambios={
            "estado": {"anterior": estado_anterior, "nuevo": EstadoEstudio.RESULTADO_CARGADO.value},
            "resultado_id": {"anterior": None, "nuevo": resultado.id},
            "diagnostico": {"anterior": None, "nuevo": diagnostico.value},
            "fecha_reevaluacion_vus": {"anterior": fecha_vus_anterior, "nuevo": fecha_vus_nueva},
        },
        motivo="Carga de resultado bioinformatico",
        ip_origen=ip_origen,
    )

    aviso_texto = (
        f"El resultado del estudio #{estudio.id} ya esta disponible (diagnostico: {diagnostico.value})."
    )
    if diagnostico == ConclusionDiagnostica.VUS and fecha_proximo_estudio is not None:
        aviso_texto += (
            f" Se programo un nuevo estudio / reevaluacion VUS para el {fecha_proximo_estudio.isoformat()}."
        )

    usuarios_notificar: list[tuple[int, str]] = []
    if estudio.paciente and estudio.paciente.usuario:
        usuarios_notificar.append((estudio.paciente.usuario_id, estudio.paciente.usuario.email))
    if estudio.medico and estudio.medico.usuario:
        usuarios_notificar.append((estudio.medico.usuario_id, estudio.medico.usuario.email))

    avisos_mail: list[Aviso] = []
    emails_unicos: list[str] = []
    vistos_uid: set[int] = set()
    for uid, email in usuarios_notificar:
        if uid in vistos_uid:
            continue
        vistos_uid.add(uid)
        bioinformatica_repo.crear_aviso(
            usuario_id=uid,
            mensaje=aviso_texto,
            canal=CanalAviso.APP,
            enviado=True,
            enviado_en=ahora,
        )
        avisos_mail.append(
            bioinformatica_repo.crear_aviso(
                usuario_id=uid,
                mensaje=aviso_texto,
                canal=CanalAviso.MAIL,
                enviado=False,
            )
        )
        if email:
            emails_unicos.append(email)

    contexto_mail = {
        "estudio_id": estudio.id,
        "resultado_id": resultado.id,
        "diagnostico": diagnostico.value,
        "fecha_proximo_estudio": fecha_vus_nueva,
        "destinatarios": emails_unicos,
        "mensaje": aviso_texto,
    }
    return resultado, ruta_fisica, avisos_mail, contexto_mail


def despachar_correos_resultado(
    *,
    avisos_mail: list[Aviso],
    contexto_mail: dict[str, Any],
    email_client: EmailClient | None = None,
    cliente_cls: type[EmailClient] = EmailClient,
) -> bool:
    """Envia los correos de resultado disponible sin revertir la BD si el SMTP falla."""
    cliente = resolver_email_client(email_client, cliente_cls=cliente_cls)
    enviado = enviar_email_resiliente(
        cliente,
        asunto=f"Resultado disponible - Estudio #{contexto_mail['estudio_id']}",
        mensaje=contexto_mail["mensaje"],
        destinatarios=contexto_mail["destinatarios"],
        referencia=f"RESULTADO-{contexto_mail['resultado_id']}",
        idempotency_key=f"resultado-{contexto_mail['resultado_id']}-aviso",
    )
    if enviado and avisos_mail:
        bioinformatica_repo.marcar_avisos_enviados(avisos_mail, ahora_utc_naive())
        bioinformatica_repo.guardar_cambios()
    return enviado
