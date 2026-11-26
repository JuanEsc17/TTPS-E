"""Generador vectorial del PDF de Orden de Extraccion y Consentimiento Informado (Escenario 7)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fpdf import FPDF

ANCHO_A4_MM = 210.0
ALTO_A4_MM = 297.0
MARGEN_X_MM = 14.0
MARGEN_TOP_MM = 10.0
ANCHO_CONTENIDO_MM = ANCHO_A4_MM - 2.0 * MARGEN_X_MM

_AZUL_MARCA = (11, 79, 138)
_FONDO_SUAVE = (248, 250, 252)
_BORDE_GRIS = (203, 213, 225)
_TEXTO_PRINCIPAL = (15, 23, 42)
_TEXTO_ATENUADO = (71, 85, 105)
_BLANCO = (255, 255, 255)


def _texto_latin1(valor: Any) -> str:
    """Convierte caracteres Unicode fuera de Latin-1 para las fuentes core de FPDF."""
    texto = str(valor or "").replace("\u2014", "-").replace("\u2013", "-").replace("\u2022", "-")
    texto = (
        texto.replace("…", "...")
        .replace("“", '"')
        .replace("”", '"')
        .replace("’", "'")
        .replace("\u00a0", " ")
    )
    return texto.encode("latin-1", "replace").decode("latin-1")


def _formatear_fecha(valor: date | datetime | None) -> str:
    if isinstance(valor, (datetime, date)):
        return valor.strftime("%d / %m / %Y")
    return "____ / ____ / ______"


def _dibujar_celda_etiqueta_valor(
    pdf: FPDF,
    *,
    x: float,
    y: float,
    w: float,
    h: float,
    etiqueta: str,
    valor: str,
    linea_completa: bool = False,
) -> None:
    """Dibuja una celda tabular con etiqueta sutil arriba y valor abajo (o en linea)."""
    pdf.set_draw_color(*_BORDE_GRIS)
    pdf.set_line_width(0.25)
    pdf.rect(x, y, w, h)

    if linea_completa:
        pdf.set_xy(x + 2.0, y + 1.5)
        pdf.set_font("Helvetica", "B", 7.8)
        pdf.set_text_color(*_TEXTO_PRINCIPAL)
        ancho_etiq = pdf.get_string_width(_texto_latin1(etiqueta)) + 2.5
        pdf.cell(ancho_etiq, h - 3.0, _texto_latin1(etiqueta))
        pdf.set_font("Helvetica", "", 7.8)
        pdf.set_text_color(*_TEXTO_PRINCIPAL)
        pdf.cell(max(w - ancho_etiq - 4.0, 10.0), h - 3.0, _texto_latin1(valor))
        return

    pdf.set_xy(x + 2.0, y + 1.2)
    pdf.set_font("Helvetica", "B", 6.8)
    pdf.set_text_color(*_TEXTO_ATENUADO)
    pdf.cell(w - 4.0, 3.3, _texto_latin1(etiqueta))

    pdf.set_xy(x + 2.0, y + 4.4)
    pdf.set_font("Helvetica", "", 8.0)
    pdf.set_text_color(*_TEXTO_PRINCIPAL)
    pdf.cell(w - 4.0, 4.2, _texto_latin1(valor))


def _nombre_usuario(usuario: Any, fallback: str = "-") -> str:
    if not usuario:
        return fallback
    apellido = (getattr(usuario, "apellido", "") or "").strip()
    nombre = (getattr(usuario, "nombre", "") or "").strip()
    if apellido and nombre:
        return f"{apellido}, {nombre}"
    return nombre or apellido or fallback


def _construir_texto_determinaciones(estudio: Any) -> str:
    patologia = (
        estudio.patologia_sospechada.nombre
        if (estudio and getattr(estudio, "patologia_sospechada", None))
        else "Exoma clínico"
    )
    simbolos_genes = sorted(
        {
            eg.gen.simbolo
            for eg in (getattr(estudio, "genes", None) or [])
            if getattr(eg, "gen", None) and getattr(eg.gen, "simbolo", None)
        }
    )
    if simbolos_genes:
        resumen_genes = ", ".join(simbolos_genes[:8])
        if len(simbolos_genes) > 8:
            resumen_genes += f" (+{len(simbolos_genes) - 8})"
        return f"Exoma clínico ({patologia}) · Genes: {resumen_genes}"
    return f"Secuenciación de Exoma Clínico · Patología sospechada: {patologia}"


def construir_pdf_orden_y_consentimiento(*, turno: Any, estudio: Any, centro: Any) -> bytes:
    """Genera el PDF A4 de una hoja con la Orden de Extracción y el Consentimiento Informado."""
    paciente = getattr(estudio, "paciente", None) or getattr(turno, "paciente", None)
    usuario_paciente = getattr(paciente, "usuario", None)
    medico = getattr(estudio, "medico", None)
    usuario_medico = getattr(medico, "usuario", None)

    patologia_nombre = (
        estudio.patologia_sospechada.nombre
        if getattr(estudio, "patologia_sospechada", None)
        else "patología genética en estudio"
    )
    institucion_txt = f"{centro.nombre} ({centro.direccion}, {centro.provincia})"
    estudio_protocolo_txt = f"Exoma Clínico · Estudio #{estudio.id}"
    medico_txt = (
        f"Dr./Dra. {getattr(usuario_medico, 'nombre', '')} {getattr(usuario_medico, 'apellido', '')}".strip()
        if usuario_medico
        else "Profesional solicitante asignado"
    )
    contacto_medico_txt = (
        f"{usuario_medico.email} · {usuario_medico.telefono}"
        if (usuario_medico and getattr(usuario_medico, "telefono", None))
        else (getattr(usuario_medico, "email", None) or "Coordinación de Laboratorio")
    )
    participante_txt = _nombre_usuario(usuario_paciente, fallback="-")
    if getattr(paciente, "responsable_nombre", None):
        participante_txt = f"{participante_txt} (Resp.: {paciente.responsable_nombre})"
    dni_txt = getattr(paciente, "dni", None) or "-"
    fecha_nac_txt = _formatear_fecha(getattr(paciente, "fecha_nacimiento", None))
    codigo_txt = f"EST-{estudio.id:05d}"
    inicio_dt: datetime | None = getattr(turno, "inicio", None)
    fecha_extraccion_txt = (
        f"{inicio_dt.strftime('%d / %m / %Y')} · {inicio_dt.strftime('%H:%M hs')}"
        if inicio_dt
        else "____ / ____ / ______"
    )
    matricula_txt = getattr(medico, "matricula", None) or "-"
    determinaciones_txt = _construir_texto_determinaciones(estudio)

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(MARGEN_X_MM, MARGEN_TOP_MM, MARGEN_X_MM)
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    # Barra superior y cabecera
    pdf.set_fill_color(*_AZUL_MARCA)
    pdf.rect(0.0, 0.0, ANCHO_A4_MM, 2.8, style="F")

    pdf.set_xy(MARGEN_X_MM, 6.5)
    pdf.set_font("Helvetica", "B", 13.5)
    pdf.set_text_color(*_TEXTO_PRINCIPAL)
    pdf.cell(
        ANCHO_CONTENIDO_MM,
        6.0,
        _texto_latin1("ORDEN DE EXTRACCIÓN Y CONSENTIMIENTO INFORMADO"),
        align="C",
    )

    pdf.set_xy(MARGEN_X_MM, 12.6)
    pdf.set_font("Helvetica", "", 8.2)
    pdf.set_text_color(*_TEXTO_ATENUADO)
    pdf.cell(
        ANCHO_CONTENIDO_MM,
        4.2,
        _texto_latin1("Extracción de sangre para estudio de exoma clínico | Formulario oficial del turno"),
        align="C",
    )

    # Grilla superior de identificacion (4 filas x 2 columnas)
    y = 18.5
    mitad_w = ANCHO_CONTENIDO_MM / 2.0
    alto_fila = 9.2

    _dibujar_celda_etiqueta_valor(
        pdf,
        x=MARGEN_X_MM,
        y=y,
        w=mitad_w,
        h=alto_fila,
        etiqueta="Institución / centro:",
        valor=institucion_txt[:54],
    )
    _dibujar_celda_etiqueta_valor(
        pdf,
        x=MARGEN_X_MM + mitad_w,
        y=y,
        w=mitad_w,
        h=alto_fila,
        etiqueta="Estudio / protocolo:",
        valor=estudio_protocolo_txt,
    )
    y += alto_fila

    _dibujar_celda_etiqueta_valor(
        pdf,
        x=MARGEN_X_MM,
        y=y,
        w=mitad_w,
        h=alto_fila,
        etiqueta="Profesional / investigador responsable:",
        valor=medico_txt[:52],
    )
    _dibujar_celda_etiqueta_valor(
        pdf,
        x=MARGEN_X_MM + mitad_w,
        y=y,
        w=mitad_w,
        h=alto_fila,
        etiqueta="Contacto:",
        valor=contacto_medico_txt[:52],
    )
    y += alto_fila

    _dibujar_celda_etiqueta_valor(
        pdf,
        x=MARGEN_X_MM,
        y=y,
        w=mitad_w,
        h=alto_fila,
        etiqueta="Participante (apellido y nombre):",
        valor=participante_txt[:52],
    )
    _dibujar_celda_etiqueta_valor(
        pdf,
        x=MARGEN_X_MM + mitad_w,
        y=y,
        w=mitad_w,
        h=alto_fila,
        etiqueta="DNI:",
        valor=str(dni_txt),
    )
    y += alto_fila

    _dibujar_celda_etiqueta_valor(
        pdf,
        x=MARGEN_X_MM,
        y=y,
        w=mitad_w,
        h=alto_fila,
        etiqueta="Fecha de nacimiento y código:",
        valor=f"{fecha_nac_txt}   |   Código: {codigo_txt}",
    )
    _dibujar_celda_etiqueta_valor(
        pdf,
        x=MARGEN_X_MM + mitad_w,
        y=y,
        w=mitad_w,
        h=alto_fila,
        etiqueta="Fecha y hora de extracción:",
        valor=fecha_extraccion_txt,
    )
    y += alto_fila + 4.0

    # Seccion 1: ORDEN DE EXTRACCION
    pdf.set_xy(MARGEN_X_MM, y)
    pdf.set_font("Helvetica", "B", 10.0)
    pdf.set_text_color(*_AZUL_MARCA)
    pdf.cell(ANCHO_CONTENIDO_MM, 5.5, _texto_latin1("1. ORDEN DE EXTRACCIÓN"))
    y += 6.0

    alto_orden = 7.4
    _dibujar_celda_etiqueta_valor(
        pdf,
        x=MARGEN_X_MM,
        y=y,
        w=ANCHO_CONTENIDO_MM,
        h=alto_orden,
        etiqueta="Análisis / determinaciones solicitadas:",
        valor=determinaciones_txt[:95],
        linea_completa=True,
    )
    y += alto_orden

    _dibujar_celda_etiqueta_valor(
        pdf,
        x=MARGEN_X_MM,
        y=y,
        w=ANCHO_CONTENIDO_MM,
        h=alto_orden,
        etiqueta="Indicaciones previas / observaciones:",
        valor="No requiere ayuno ni preparación especial. Presentar este documento impreso y firmado.",
        linea_completa=True,
    )
    y += alto_orden

    _dibujar_celda_etiqueta_valor(
        pdf,
        x=MARGEN_X_MM,
        y=y,
        w=ANCHO_CONTENIDO_MM,
        h=alto_orden,
        etiqueta="Profesional solicitante:",
        valor=f"{medico_txt[:38]}   |   Matrícula: {matricula_txt}   |   Firma: _____________________",
        linea_completa=True,
    )
    y += alto_orden + 4.5

    # Seccion 2: INFORMACION Y CONSENTIMIENTO
    pdf.set_xy(MARGEN_X_MM, y)
    pdf.set_font("Helvetica", "B", 10.0)
    pdf.set_text_color(*_AZUL_MARCA)
    pdf.cell(ANCHO_CONTENIDO_MM, 5.5, _texto_latin1("2. INFORMACIÓN Y CONSENTIMIENTO"))
    y += 6.2

    pdf.set_font("Helvetica", "", 8.2)
    pdf.set_text_color(*_TEXTO_PRINCIPAL)
    parrafos = [
        (
            f"Se me explicó que se solicita una muestra de sangre para el estudio indicado en este formulario, "
            f"con el objetivo de analizar variantes genéticas vinculadas a {patologia_nombre} mediante secuenciación "
            f"de exoma clínico. La extracción será realizada por personal capacitado mediante una punción en una vena "
            f"y se prevé obtener aproximadamente 5 mL de sangre. La muestra se utilizará para extracción de ADN y análisis "
            f"genómico diagnóstico autorizado para el Estudio #{estudio.id}. La extracción puede causar molestia o dolor breve, "
            f"hematoma, sangrado leve y, ocasionalmente, mareo o desmayo; raramente, infección en el sitio de punción. "
            f"Se aplicarán medidas habituales de higiene y seguridad. Pude informar antecedentes relevantes (por ejemplo, "
            f"desmayos, problemas de coagulación o uso de anticoagulantes) y realizar preguntas."
        ),
        (
            "Entiendo que mi participación es voluntaria y que puedo negarme o retirar mi consentimiento sin sanciones ni "
            "pérdida de la atención o los beneficios que me correspondan. Comprendo que puede no haber un beneficio directo "
            "para mí. Mis datos y la muestra serán tratados confidencialmente y solo podrán utilizarse para los fines aquí "
            "descriptos y autorizados por el protocolo; cualquier uso diferente requerirá la autorización que corresponda. "
            "Conservación y destino final de la muestra: resguardo codificado en biobanco/laboratorio durante el procesamiento "
            "y archivo clínico conforme normativa sanitaria vigente."
        ),
        (
            "Declaro que recibí información clara, pude hacer preguntas y acepto voluntariamente la extracción y el uso de "
            "la muestra para los fines especificados. Recibiré una copia de este documento firmado."
        ),
    ]
    for p in parrafos:
        pdf.set_x(MARGEN_X_MM)
        pdf.multi_cell(ANCHO_CONTENIDO_MM, 4.0, _texto_latin1(p), align="J")
        pdf.ln(1.8)

    y = pdf.get_y() + 0.5
    pdf.set_xy(MARGEN_X_MM, y)
    pdf.set_font("Helvetica", "B", 8.4)
    pdf.cell(
        ANCHO_CONTENIDO_MM,
        5.0,
        _texto_latin1(
            "Decisión de la persona participante:   [ ] Acepto la extracción y el uso de la muestra según lo explicado.   [ ] No acepto."
        ),
    )
    y += 6.5

    # Bloque de firmas (4 filas x 2 columnas)
    alto_firma = 10.0
    etiqueta_firmante = (
        f"{participante_txt[:48]}"
        if not getattr(paciente, "responsable_nombre", None)
        else f"{paciente.responsable_nombre} (Resp. DNI {getattr(paciente, 'responsable_dni', '-')})"
    )
    _dibujar_celda_etiqueta_valor(
        pdf,
        x=MARGEN_X_MM,
        y=y,
        w=mitad_w,
        h=alto_firma,
        etiqueta="Participante / responsable legal:",
        valor=etiqueta_firmante[:52],
    )
    _dibujar_celda_etiqueta_valor(
        pdf,
        x=MARGEN_X_MM + mitad_w,
        y=y,
        w=mitad_w,
        h=alto_firma,
        etiqueta="Firma:",
        valor="________________________________________",
    )
    y += alto_firma

    _dibujar_celda_etiqueta_valor(
        pdf,
        x=MARGEN_X_MM,
        y=y,
        w=mitad_w,
        h=alto_firma,
        etiqueta="Lugar y fecha:",
        valor=f"{centro.provincia}, ____ / ____ / ______",
    )
    _dibujar_celda_etiqueta_valor(
        pdf,
        x=MARGEN_X_MM + mitad_w,
        y=y,
        w=mitad_w,
        h=alto_firma,
        etiqueta="Hora:",
        valor="____ : ____ hs",
    )
    y += alto_firma

    _dibujar_celda_etiqueta_valor(
        pdf,
        x=MARGEN_X_MM,
        y=y,
        w=mitad_w,
        h=alto_firma,
        etiqueta="Profesional que obtuvo el consentimiento:",
        valor="________________________________________",
    )
    _dibujar_celda_etiqueta_valor(
        pdf,
        x=MARGEN_X_MM + mitad_w,
        y=y,
        w=mitad_w,
        h=alto_firma,
        etiqueta="Firma:",
        valor="________________________________________",
    )
    y += alto_firma

    _dibujar_celda_etiqueta_valor(
        pdf,
        x=MARGEN_X_MM,
        y=y,
        w=mitad_w,
        h=alto_firma,
        etiqueta="Personal que realizó la extracción:",
        valor="________________________________________",
    )
    _dibujar_celda_etiqueta_valor(
        pdf,
        x=MARGEN_X_MM + mitad_w,
        y=y,
        w=mitad_w,
        h=alto_firma,
        etiqueta="Fecha / hora:",
        valor="____ / ____ / ______   ____ : ____ hs",
    )
    y += alto_firma + 3.5

    # Contacto y nota al pie
    pdf.set_xy(MARGEN_X_MM, y)
    pdf.set_font("Helvetica", "B", 7.4)
    pdf.set_text_color(*_TEXTO_PRINCIPAL)
    pdf.cell(
        ANCHO_CONTENIDO_MM,
        4.0,
        _texto_latin1(
            f"Contacto para consultas: Coordinación de Exoma Clínico · {centro.nombre} · {contacto_medico_txt[:52]}"
        ),
    )
    y += 4.5

    pdf.set_xy(MARGEN_X_MM, y)
    pdf.set_font("Helvetica", "", 7.0)
    pdf.set_text_color(*_TEXTO_ATENUADO)
    pdf.multi_cell(
        ANCHO_CONTENIDO_MM,
        3.4,
        _texto_latin1(
            "Nota: Llevar este documento impreso y firmado al asistir al turno de extracción. "
            "Para menores de edad o personas que requieran representación legal debe firmar el padre, madre o responsable legal."
        ),
    )

    # Pie institucional fijo
    pdf.set_draw_color(*_BORDE_GRIS)
    pdf.line(MARGEN_X_MM, 282.0, MARGEN_X_MM + ANCHO_CONTENIDO_MM, 282.0)
    pdf.set_xy(MARGEN_X_MM, 283.5)
    pdf.set_font("Helvetica", "", 7.2)
    pdf.set_text_color(*_TEXTO_ATENUADO)
    pdf.cell(
        ANCHO_CONTENIDO_MM / 2.0,
        4.0,
        _texto_latin1(f"Exoma Clínico · Estudio #{estudio.id}"),
    )
    pdf.cell(
        ANCHO_CONTENIDO_MM / 2.0,
        4.0,
        _texto_latin1("Página 1"),
        align="R",
    )

    salida = pdf.output()
    return bytes(salida) if not isinstance(salida, bytes) else salida
