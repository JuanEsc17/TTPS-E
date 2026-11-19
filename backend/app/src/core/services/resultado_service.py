"""Servicio para generacion, notificacion, consulta y descarga de resultados de exoma (Escenario 16)."""
from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn

from flask import current_app, has_app_context
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from sqlalchemy.exc import SQLAlchemyError
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
    Rol,
    TipoAccionAuditoria,
    Usuario,
    Variante,
    calcular_conclusion_diagnostica,
)
from src.core.repos import bioinformatica_repo
from src.core.services import auditoria_service
from src.core.services.excepciones import ErrorDominio

logger = logging.getLogger(__name__)
_EMAIL_CLIENT_ORIGINAL = EmailClient
_ROLES_PERMITIDOS_RESULTADO = frozenset(
    {Rol.PACIENTE, Rol.MEDICO, Rol.GERENTE_MEDICO, Rol.BIOINFORMATICO}
)


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
            sorted(
                {
                    f"{ag.gen.simbolo} ({ag.gen.nombre})" if ag.gen.nombre else ag.gen.simbolo
                    for ag in analisis.genes
                    if ag.gen is not None
                }
            )
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

        ruta_tmp = ruta_fisica.with_name(f".{ruta_fisica.name}.{os.getpid()}.{time.time_ns()}.tmp")
        try:
            pdf.output(str(ruta_tmp))
            os.replace(ruta_tmp, ruta_fisica)
        finally:
            ruta_tmp.unlink(missing_ok=True)
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

    try:
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
        if analisis.solicitado_por_id and analisis.solicitado_por_id != estudio.medico_id:
            medico_solicitante = bioinformatica_repo.buscar_medico_por_id(analisis.solicitado_por_id)
            if medico_solicitante and medico_solicitante.usuario:
                usuarios_notificar.append(
                    (medico_solicitante.usuario_id, medico_solicitante.usuario.email)
                )

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
    except Exception:
        ruta_fisica.unlink(missing_ok=True)
        raise

    logger.info(
        '[resultado_service] resultado_persistido estudio_id=%s resultado_id=%s estado="%s"',
        estudio.id,
        resultado.id,
        estudio.estado.value,
    )

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
    if enviado:
        logger.info(
            "[mail_client] resultado_notificado estudio_id=%s resultado_id=%s destinatarios=%s",
            contexto_mail["estudio_id"],
            contexto_mail["resultado_id"],
            contexto_mail["destinatarios"],
        )
        if avisos_mail:
            try:
                bioinformatica_repo.marcar_avisos_enviados(avisos_mail, ahora_utc_naive())
                bioinformatica_repo.guardar_cambios()
            except SQLAlchemyError as exc:
                bioinformatica_repo.deshacer_cambios()
                logger.warning(
                    "[resultado_service] error_marcar_avisos_enviados resultado_id=%s err=%s",
                    contexto_mail["resultado_id"],
                    exc,
                )
    return enviado


def _denegar_acceso_resultado(estudio_id: int, usuario: Usuario) -> NoReturn:
    logger.warning(
        '[resultado_service] acceso_denegado_resultado estudio_id=%s usuario_id=%s rol="%s"',
        estudio_id,
        usuario.id,
        usuario.rol.value,
    )
    raise ErrorDominio(
        "No tiene permisos para acceder al resultado genetico de este estudio.",
        codigo="FORBIDDEN_RESULTADO_GENETICO",
        http_status=403,
    )


def _verificar_acceso_resultado(estudio: Estudio, usuario: Usuario) -> None:
    if usuario.rol == Rol.BIOINFORMATICO:
        return
    if usuario.rol == Rol.PACIENTE:
        if estudio.paciente is not None and estudio.paciente.usuario_id == usuario.id:
            return
        _denegar_acceso_resultado(estudio.id, usuario)
    if usuario.rol in (Rol.MEDICO, Rol.GERENTE_MEDICO):
        if estudio.medico is not None and estudio.medico.usuario_id == usuario.id:
            return
        medico = bioinformatica_repo.buscar_medico_por_usuario_id(usuario.id)
        if medico is not None and any(a.solicitado_por_id == medico.id for a in estudio.analisis):
            return
        # shortcut: pacientes_medicos_autorizados (Escenario 40) y estudios_familiares_vinculados (Escenario 41) aun no existen en models/; extender aqui al implementarlos
        _denegar_acceso_resultado(estudio.id, usuario)
    _denegar_acceso_resultado(estudio.id, usuario)


def _obtener_estudio_y_resultado_autorizado(
    *,
    estudio_id: int,
    usuario: Usuario,
    analisis_id: int | None = None,
) -> tuple[Estudio, Analisis, Resultado, list[Analisis]]:
    if usuario.rol not in _ROLES_PERMITIDOS_RESULTADO:
        _denegar_acceso_resultado(estudio_id, usuario)

    estudio = bioinformatica_repo.buscar_estudio_por_id(estudio_id)
    if estudio is None:
        raise ErrorDominio("Estudio no encontrado.", codigo="ESTUDIO_NO_ENCONTRADO", http_status=404)

    _verificar_acceso_resultado(estudio, usuario)

    if estudio.estado != EstadoEstudio.RESULTADO_CARGADO:
        raise ErrorDominio(
            "El resultado de este estudio aun no se encuentra disponible.",
            codigo="RESULTADO_AUN_NO_DISPONIBLE",
            http_status=409,
        )

    completados = [a for a in estudio.analisis if a.resultado is not None]
    if not completados:
        raise ErrorDominio(
            "El resultado de este estudio aun no se encuentra disponible.",
            codigo="RESULTADO_AUN_NO_DISPONIBLE",
            http_status=409,
        )

    if analisis_id is not None:
        analisis = next((a for a in completados if a.id == analisis_id), None)
        if analisis is None:
            raise ErrorDominio(
                "No se encontro un resultado para el analisis solicitado en este estudio.",
                codigo="RESULTADO_NO_ENCONTRADO",
                http_status=404,
            )
    else:
        analisis = completados[-1]

    assert analisis.resultado is not None
    return estudio, analisis, analisis.resultado, completados


def _serializar_resultado_analisis(
    estudio_id: int,
    analisis: Analisis,
    *,
    con_query_analisis: bool = False,
) -> dict[str, Any]:
    res = analisis.resultado
    assert res is not None
    pdf_url = f"/api/estudios/{estudio_id}/resultado/pdf"
    if con_query_analisis:
        pdf_url = f"{pdf_url}?analisis_id={analisis.id}"

    variantes_ordenadas = sorted(
        (av.variante for av in analisis.variantes if av.variante is not None),
        key=lambda v: v.id,
    )
    return {
        "resultado_id": res.id,
        "analisis_id": analisis.id,
        "tipo_analisis": analisis.tipo.value,
        "positivo": bool(res.positivo),
        "diagnostico": res.diagnostico.value,
        "fecha_proximo_estudio": (
            res.fecha_proximo_estudio.isoformat() if res.fecha_proximo_estudio else None
        ),
        "generado_en": res.generado_en.isoformat() if res.generado_en else None,
        "pdf_url": pdf_url,
        "variantes": [
            {
                "variante_id": v.id,
                "gen_simbolo": v.gen.simbolo if v.gen else "",
                "notacion": v.notacion,
                "clinvar_id": v.clinvar_id,
                "clasificacion": v.clasificacion.value,
            }
            for v in variantes_ordenadas
        ],
    }


def listar_estudios_usuario(*, usuario: Usuario) -> list[dict[str, Any]]:
    """Lista los estudios visibles para el usuario autenticado junto al resumen de su resultado."""
    if usuario.rol not in _ROLES_PERMITIDOS_RESULTADO:
        _denegar_acceso_resultado(0, usuario)

    if usuario.rol == Rol.PACIENTE:
        estudios = bioinformatica_repo.listar_estudios_de_paciente(usuario.id)
    elif usuario.rol in (Rol.MEDICO, Rol.GERENTE_MEDICO):
        medico = bioinformatica_repo.buscar_medico_por_usuario_id(usuario.id)
        estudios = bioinformatica_repo.listar_estudios_de_medico(medico.id) if medico else []
    else:
        estudios = bioinformatica_repo.listar_estudios_por_estado(EstadoEstudio.RESULTADO_CARGADO)

    items: list[dict[str, Any]] = []
    for est in estudios:
        completados = [a for a in est.analisis if a.resultado is not None]
        tiene_resultado = est.estado == EstadoEstudio.RESULTADO_CARGADO and bool(completados)
        ultimo = completados[-1] if tiene_resultado else None
        res = ultimo.resultado if ultimo else None
        pac_u = est.paciente.usuario if est.paciente else None
        med_u = est.medico.usuario if est.medico else None

        items.append(
            {
                "estudio_id": est.id,
                "estado": est.estado.value,
                "patologia": est.patologia_sospechada.nombre if est.patologia_sospechada else "",
                "es_pompe_urgente": bool(est.es_pompe_urgente),
                "paciente": {
                    "id": est.paciente_id,
                    "nombre": f"{pac_u.nombre} {pac_u.apellido}".strip() if pac_u else "",
                    "dni": est.paciente.dni if est.paciente else "",
                },
                "medico_nombre": f"{med_u.nombre} {med_u.apellido}".strip() if med_u else "",
                "fecha_reevaluacion_vus": (
                    est.fecha_reevaluacion_vus.isoformat() if est.fecha_reevaluacion_vus else None
                ),
                "tiene_resultado": tiene_resultado,
                "resultado": (
                    {
                        "resultado_id": res.id,
                        "analisis_id": ultimo.id,
                        "tipo_analisis": ultimo.tipo.value,
                        "positivo": bool(res.positivo),
                        "diagnostico": res.diagnostico.value,
                        "fecha_proximo_estudio": (
                            res.fecha_proximo_estudio.isoformat()
                            if res.fecha_proximo_estudio
                            else None
                        ),
                        "generado_en": res.generado_en.isoformat() if res.generado_en else None,
                        "cantidad_variantes": len(ultimo.variantes),
                    }
                    if (ultimo is not None and res is not None)
                    else None
                ),
                "updated_at": est.updated_at.isoformat() if est.updated_at else None,
            }
        )
    return items


def consultar_resultado_estudio(*, estudio_id: int, usuario: Usuario) -> dict[str, Any]:
    """STEP 4: Devuelve el detalle del resultado actual y el historial de resultados del estudio."""
    estudio, analisis_actual, resultado_actual, completados = (
        _obtener_estudio_y_resultado_autorizado(estudio_id=estudio_id, usuario=usuario)
    )
    logger.info(
        '[resultado_service] resultado_consultado estudio_id=%s resultado_id=%s usuario_id=%s rol="%s"',
        estudio.id,
        resultado_actual.id,
        usuario.id,
        usuario.rol.value,
    )
    return {
        "estudio_id": estudio.id,
        "estado_estudio": estudio.estado.value,
        "fecha_reevaluacion_vus": (
            estudio.fecha_reevaluacion_vus.isoformat()
            if estudio.fecha_reevaluacion_vus
            else None
        ),
        "resultado_actual": _serializar_resultado_analisis(estudio.id, analisis_actual),
        "historial_resultados": [
            _serializar_resultado_analisis(estudio.id, a, con_query_analisis=True)
            for a in completados
        ],
    }


def descargar_pdf_resultado(
    *,
    estudio_id: int,
    usuario: Usuario,
    analisis_id: int | None = None,
) -> tuple[bytes, str]:
    """STEP 4: Verifica permisos, regenera el PDF si falta en disco y retorna sus bytes."""
    estudio, analisis, resultado, _ = _obtener_estudio_y_resultado_autorizado(
        estudio_id=estudio_id,
        usuario=usuario,
        analisis_id=analisis_id,
    )

    ruta_fisica = resolver_ruta_storage(resultado.pdf_path)
    if not ruta_fisica.is_file():
        logger.warning(
            "[resultado_service] pdf_faltante_regenerando estudio_id=%s analisis_id=%s path=%r",
            estudio.id,
            analisis.id,
            resultado.pdf_path,
        )
        variantes = sorted(
            (av.variante for av in analisis.variantes if av.variante is not None),
            key=lambda v: v.id,
        )
        _generar_pdf_resultado(
            estudio=estudio,
            analisis=analisis,
            variantes=variantes,
            diagnostico=resultado.diagnostico,
            fecha_proximo_estudio=resultado.fecha_proximo_estudio,
            generado_en=resultado.generado_en or ahora_utc_naive(),
            ruta_fisica=ruta_fisica,
        )

    try:
        pdf_bytes = ruta_fisica.read_bytes()
    except OSError as exc:
        logger.error(
            "[resultado_service] error_lectura_pdf estudio_id=%s resultado_id=%s path=%r err=%s",
            estudio.id,
            resultado.id,
            resultado.pdf_path,
            exc,
        )
        raise ErrorDominio(
            "No se pudo leer el informe PDF del resultado. Intente nuevamente.",
            codigo="ERROR_LECTURA_PDF_RESULTADO",
            http_status=500,
            reintentable=True,
        ) from exc

    logger.info(
        '[resultado_service] resultado_descargado estudio_id=%s resultado_id=%s usuario_id=%s rol="%s"',
        estudio.id,
        resultado.id,
        usuario.id,
        usuario.rol.value,
    )
    return pdf_bytes, f"resultado_estudio_{estudio.id}.pdf"
