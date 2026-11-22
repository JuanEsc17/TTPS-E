"""Generador PDF vectorial deterministico (ISO A4) para informes clinicos de resultado de exoma."""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

from fpdf import FPDF
from fpdf.enums import MethodReturnValue, XPos, YPos
from src.core.models import (
    Analisis,
    ClasificacionVariante,
    ConclusionDiagnostica,
    Estudio,
    TipoAnalisis,
    Variante,
)

# shortcut: usa fpdf2 con fuentes Type 1 vectoriales (ya instalado y requerido por tests); migrar a Playwright+pikepdf si se exige PDF/UA-1 o PDF/A-2b

# Geometria euclidiana ISO A4 (210.00 x 297.00 mm = 595.28 x 841.89 pt)
ANCHO_A4_MM = 210.0
MARGEN_X_MM = 16.0
MARGEN_TOP_MM = 16.0
MARGEN_BOTTOM_MM = 20.0
ANCHO_CONTENIDO_MM = ANCHO_A4_MM - 2 * MARGEN_X_MM  # 178.00 mm exactos
EPSILON_SALTO_MM = 0.5  # Margen de seguridad contra paginas fantasma por redondeo

# Paleta institucional alineada con frontend/src/index.css y ResultadoEstudioPage.jsx
_AZUL_MARCA = (11, 79, 138)        # #0B4F8A
_FONDO_TARJETA = (248, 250, 252)   # #F8FAFC
_FONDO_CEBRA = (248, 250, 252)     # #F8FAFC
_TEXTO_PRINCIPAL = (15, 23, 42)    # #0F172A
_TEXTO_SECUNDARIO = (71, 85, 105)  # #475569
_TEXTO_ATENUADO = (100, 116, 139)  # #64748B
_BORDE_SUAVE = (203, 213, 225)     # #CBD5E1
_BORDE_FILA = (226, 232, 240)      # #E2E8F0
_BLANCO = (255, 255, 255)

_ESTILO_DIAGNOSTICO: dict[ConclusionDiagnostica, dict[str, Any]] = {
    ConclusionDiagnostica.POSITIVO: {
        "badge": "POSITIVO",
        "titular": "POSITIVO (variante patogénica detectada)",
        "subtitulo": "Se detectó al menos una variante clasificada como patogénica en los genes analizados.",
        "acento": (185, 28, 28),      # #B91C1C
        "fondo": (254, 242, 242),     # #FEF2F2
        "borde": (254, 202, 202),     # #FECACA
        "texto": (127, 29, 29),       # #7F1D1D
        "pill_fondo": (254, 226, 226),
    },
    ConclusionDiagnostica.VUS: {
        "badge": "VUS",
        "titular": "VUS (Variante de Significado Incierto)",
        "subtitulo": "Sin variantes patogénicas confirmadas. Se sugiere seguimiento y reevaluación al año.",
        "acento": (180, 83, 9),       # #B45309
        "fondo": (255, 251, 235),     # #FFFBEB
        "borde": (253, 230, 138),     # #FDE68A
        "texto": (120, 53, 15),       # #78350F
        "pill_fondo": (254, 243, 199),
    },
    ConclusionDiagnostica.NEGATIVO: {
        "badge": "NEGATIVO",
        "titular": "NEGATIVO (sin variantes patogénicas ni VUS)",
        "subtitulo": "No se detectaron variantes patogénicas ni de significado incierto (VUS) en los genes evaluados.",
        "acento": (4, 120, 87),       # #047857
        "fondo": (236, 253, 245),     # #ECFDF5
        "borde": (167, 243, 208),     # #A7F3D0
        "texto": (6, 78, 59),         # #064E3B
        "pill_fondo": (209, 250, 229),
    },
}

_ESTILO_CLASIFICACION: dict[ClasificacionVariante, tuple[str, tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]] = {
    ClasificacionVariante.PATOGENICA: ("Patogénica", (254, 242, 242), (252, 165, 165), (185, 28, 28)),
    ClasificacionVariante.VUS: ("VUS", (255, 251, 235), (252, 211, 77), (146, 64, 14)),
    ClasificacionVariante.BENIGNA: ("Benigna", (236, 253, 245), (110, 231, 183), (4, 120, 87)),
    ClasificacionVariante.INOCUA: ("Inocua", (241, 245, 249), (203, 213, 225), (71, 85, 105)),
}

# Anchos exactos de columnas de la tabla de variantes (suma = 178.0 mm)
_COLS_VARIANTES = (34.0, 64.0, 42.0, 38.0)


def _texto_latin1(valor: Any) -> str:
    """Normaliza texto a ISO-8859-1 para fuentes vectoriales Type 1 sin caracteres '?' espurios."""
    texto = str(valor if valor is not None else "-")
    texto = (
        texto.replace("—", "-")
        .replace("–", "-")
        .replace("•", "-")
        .replace("…", "...")
        .replace("“", '"')
        .replace("”", '"')
        .replace("’", "'")
    )
    return texto.encode("latin-1", "replace").decode("latin-1")


def _formatear_fecha(valor: Any) -> str:
    if isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    return str(valor or "-")


def _etiqueta_tipo_analisis(tipo: TipoAnalisis) -> str:
    return "Reanálisis" if tipo == TipoAnalisis.REANALISIS else "Inicial"


def _dibujar_logo_adn(pdf: FPDF, x: float, y: float, tam: float = 10.5) -> None:
    """Dibuja el emblema vectorial de doble helice ADN (paridad con LogoAdn.jsx)."""
    pdf.set_fill_color(*_AZUL_MARCA)
    pdf.rect(x, y, tam, tam, style="F", round_corners=True, corner_radius=2.2)

    pad_x = tam * 0.28
    pad_y = tam * 0.16
    cx = x + tam / 2.0
    amp = (tam / 2.0) - pad_x
    alto = tam - 2.0 * pad_y

    hebra_a: list[tuple[float, float]] = []
    hebra_b: list[tuple[float, float]] = []
    pasos = 14
    for i in range(pasos + 1):
        t = i / pasos
        py = y + pad_y + t * alto
        desplazamiento = math.cos(t * 2.0 * math.pi) * amp
        hebra_a.append((cx - desplazamiento, py))
        hebra_b.append((cx + desplazamiento, py))

    pdf.set_draw_color(*_BLANCO)
    pdf.set_line_width(0.45)
    pdf.polyline(hebra_a)
    pdf.polyline(hebra_b)

    pdf.set_line_width(0.35)
    for t_peldaño in (0.22, 0.50, 0.78):
        py = y + pad_y + t_peldaño * alto
        dx = abs(math.cos(t_peldaño * 2.0 * math.pi) * amp)
        ancho_barra = max(dx * 0.85, tam * 0.14)
        pdf.line(cx - ancho_barra, py, cx + ancho_barra, py)


class _InformeResultadoPDF(FPDF):
    """Documento ISO A4 vectorial para informes clinicos de resultado de exoma."""

    def __init__(self, *, estudio_id: int, analisis_id: int, tipo_etiqueta: str, emitido_str: str):
        super().__init__(orientation="P", unit="mm", format="A4")
        self._estudio_id = estudio_id
        self._analisis_id = analisis_id
        self._tipo_etiqueta = tipo_etiqueta
        self._emitido_str = emitido_str
        self.alias_nb_pages()
        self.set_margins(MARGEN_X_MM, MARGEN_TOP_MM, MARGEN_X_MM)
        self.set_auto_page_break(auto=True, margin=MARGEN_BOTTOM_MM)

    def header(self) -> None:
        if self.page_no() == 1:
            # Barra superior institucional a sangre completa
            self.set_fill_color(*_AZUL_MARCA)
            self.rect(0.0, 0.0, ANCHO_A4_MM, 3.0, style="F")

            _dibujar_logo_adn(self, MARGEN_X_MM, 8.0, tam=10.5)

            self.set_xy(MARGEN_X_MM + 13.5, 8.2)
            self.set_font("Times", "B", 15)
            self.set_text_color(*_TEXTO_PRINCIPAL)
            self.cell(85.0, 5.8, _texto_latin1("Exoma Clínico"))

            self.set_xy(MARGEN_X_MM + 13.5, 14.2)
            self.set_font("Helvetica", "B", 7.2)
            self.set_text_color(*_AZUL_MARCA)
            self.cell(95.0, 4.0, _texto_latin1("COORDINACIÓN DE LABORATORIO · INFORME DE RESULTADO"))

            # Metadatos de emision alineados a la derecha
            self.set_xy(MARGEN_X_MM + 104.0, 8.4)
            self.set_font("Helvetica", "B", 8.5)
            self.set_text_color(*_TEXTO_PRINCIPAL)
            self.cell(
                74.0,
                4.8,
                _texto_latin1(
                    f"Estudio #{self._estudio_id} · Análisis #{self._analisis_id} ({self._tipo_etiqueta})"
                ),
                align="R",
            )
            self.set_xy(MARGEN_X_MM + 104.0, 13.6)
            self.set_font("Helvetica", "", 8.0)
            self.set_text_color(*_TEXTO_ATENUADO)
            self.cell(74.0, 4.4, _texto_latin1(f"Emitido: {self._emitido_str}"), align="R")

            self.set_draw_color(*_BORDE_SUAVE)
            self.set_line_width(0.3)
            self.line(MARGEN_X_MM, 21.8, ANCHO_A4_MM - MARGEN_X_MM, 21.8)
            self.set_y(26.0)
            return

        # Encabezado compacto en paginas de continuacion
        self.set_fill_color(*_AZUL_MARCA)
        self.rect(0.0, 0.0, ANCHO_A4_MM, 2.0, style="F")
        self.set_xy(MARGEN_X_MM, 5.5)
        self.set_font("Helvetica", "B", 8.0)
        self.set_text_color(*_AZUL_MARCA)
        self.cell(90.0, 4.5, _texto_latin1("Exoma Clínico · Informe de Resultado"))
        self.set_font("Helvetica", "", 8.0)
        self.set_text_color(*_TEXTO_ATENUADO)
        self.cell(
            88.0,
            4.5,
            _texto_latin1(f"Estudio #{self._estudio_id} · Análisis #{self._analisis_id}"),
            align="R",
        )
        self.set_draw_color(*_BORDE_SUAVE)
        self.set_line_width(0.25)
        self.line(MARGEN_X_MM, 11.2, ANCHO_A4_MM - MARGEN_X_MM, 11.2)
        self.set_y(15.0)

    def footer(self) -> None:
        auto_prev = self.auto_page_break
        margen_prev = self.b_margin
        self.set_auto_page_break(False)
        try:
            y_linea = self.h - 14.0
            self.set_draw_color(*_BORDE_SUAVE)
            self.set_line_width(0.25)
            self.line(MARGEN_X_MM, y_linea, ANCHO_A4_MM - MARGEN_X_MM, y_linea)

            self.set_xy(MARGEN_X_MM, y_linea + 2.2)
            self.set_font("Helvetica", "", 7.5)
            self.set_text_color(*_TEXTO_ATENUADO)
            self.cell(
                120.0,
                4.2,
                _texto_latin1(f"Exoma Clínico · Documento clínico confidencial · Estudio #{self._estudio_id}"),
            )
            self.cell(58.0, 4.2, _texto_latin1(f"Página {self.page_no()} de {{nb}}"), align="R")
        finally:
            self.set_auto_page_break(auto_prev, margin=margen_prev)

    def medir_lineas(self, texto: str, ancho: float, alto_linea: float) -> list[str]:
        """Pre-calcula los cortes de linea exactos sin modificar el cursor."""
        return list(
            self.multi_cell(
                ancho,
                alto_linea,
                _texto_latin1(texto),
                dry_run=True,
                output=MethodReturnValue.LINES,
            )
        )

    def asegurar_espacio(self, altura_necesaria: float) -> bool:
        """Salta de pagina si el bloque excede el presupuesto vertical disponible."""
        if self.get_y() + altura_necesaria > self.page_break_trigger - EPSILON_SALTO_MM:
            self.add_page()
            return True
        return False


def _dibujar_encabezado_seccion(pdf: _InformeResultadoPDF, titulo: str, detalle_derecho: str = "") -> None:
    pdf.asegurar_espacio(12.0)
    y = pdf.get_y()
    pdf.set_fill_color(*_AZUL_MARCA)
    pdf.rect(MARGEN_X_MM, y + 1.1, 2.2, 3.6, style="F", round_corners=True, corner_radius=0.8)

    pdf.set_xy(MARGEN_X_MM + 4.2, y)
    pdf.set_font("Helvetica", "B", 9.2)
    pdf.set_text_color(*_AZUL_MARCA)
    pdf.cell(120.0, 5.8, _texto_latin1(titulo.upper()))

    if detalle_derecho:
        pdf.set_font("Helvetica", "", 8.2)
        pdf.set_text_color(*_TEXTO_ATENUADO)
        pdf.cell(53.8, 5.8, _texto_latin1(detalle_derecho), align="R")

    pdf.set_y(y + 7.2)


def _dibujar_banner_diagnostico(
    pdf: _InformeResultadoPDF,
    *,
    diagnostico: ConclusionDiagnostica,
    fecha_proximo_estudio: Any,
) -> None:
    estilo = _ESTILO_DIAGNOSTICO[diagnostico]
    ancho_texto = ANCHO_CONTENIDO_MM - 12.0

    pdf.set_font("Helvetica", "", 8.8)
    lineas_sub = pdf.medir_lineas(estilo["subtitulo"], ancho_texto, 4.4)

    texto_vus = ""
    lineas_vus: list[str] = []
    if diagnostico == ConclusionDiagnostica.VUS and fecha_proximo_estudio is not None:
        texto_vus = (
            "Recomendacion de nuevo estudio / reevaluacion VUS: "
            f"{_formatear_fecha(fecha_proximo_estudio)} ({fecha_proximo_estudio.isoformat()})"
        )
        pdf.set_font("Helvetica", "B", 8.8)
        lineas_vus = pdf.medir_lineas(texto_vus, ancho_texto, 4.5)

    altura = 16.5 + len(lineas_sub) * 4.4
    if lineas_vus:
        altura += 4.5 + len(lineas_vus) * 4.5

    y0 = pdf.get_y()
    pdf.set_fill_color(*estilo["fondo"])
    pdf.set_draw_color(*estilo["borde"])
    pdf.set_line_width(0.35)
    pdf.rect(MARGEN_X_MM, y0, ANCHO_CONTENIDO_MM, altura, style="DF", round_corners=True, corner_radius=2.2)

    # Franja lateral semantica interior (100% vectorial, sin desenfoque)
    pdf.set_fill_color(*estilo["acento"])
    pdf.rect(MARGEN_X_MM + 2.0, y0 + 2.4, 2.0, altura - 4.8, style="F", round_corners=True, corner_radius=1.0)

    # Etiqueta superior y badge de estado a la derecha
    x_texto = MARGEN_X_MM + 7.2
    pdf.set_xy(x_texto, y0 + 3.0)
    pdf.set_font("Helvetica", "B", 7.4)
    pdf.set_text_color(*estilo["acento"])
    pdf.cell(110.0, 4.0, _texto_latin1("CONCLUSIÓN DIAGNÓSTICA"))

    badge_w = 26.0
    pdf.set_fill_color(*estilo["pill_fondo"])
    pdf.set_draw_color(*estilo["borde"])
    pdf.set_line_width(0.25)
    pdf.rect(
        MARGEN_X_MM + ANCHO_CONTENIDO_MM - badge_w - 3.5,
        y0 + 2.8,
        badge_w,
        5.2,
        style="DF",
        round_corners=True,
        corner_radius=1.8,
    )
    pdf.set_xy(MARGEN_X_MM + ANCHO_CONTENIDO_MM - badge_w - 3.5, y0 + 2.9)
    pdf.set_font("Helvetica", "B", 7.6)
    pdf.set_text_color(*estilo["acento"])
    pdf.cell(badge_w, 5.0, _texto_latin1(estilo["badge"]), align="C")

    # Titular y subtitulo
    pdf.set_xy(x_texto, y0 + 7.6)
    pdf.set_font("Helvetica", "B", 11.5)
    pdf.set_text_color(*estilo["texto"])
    pdf.cell(ancho_texto - 28.0, 5.8, _texto_latin1(estilo["titular"]))

    pdf.set_xy(x_texto, y0 + 13.8)
    pdf.set_font("Helvetica", "", 8.8)
    pdf.set_text_color(*_TEXTO_SECUNDARIO)
    pdf.multi_cell(ancho_texto, 4.4, _texto_latin1(estilo["subtitulo"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    if lineas_vus:
        y_sep = y0 + 15.0 + len(lineas_sub) * 4.4
        pdf.set_draw_color(*estilo["borde"])
        pdf.set_line_width(0.25)
        pdf.line(x_texto, y_sep, MARGEN_X_MM + ANCHO_CONTENIDO_MM - 4.0, y_sep)
        pdf.set_xy(x_texto, y_sep + 2.0)
        pdf.set_font("Helvetica", "B", 8.8)
        pdf.set_text_color(*estilo["texto"])
        pdf.multi_cell(ancho_texto, 4.5, _texto_latin1(texto_vus), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_y(y0 + altura + 5.5)


def _dibujar_tarjeta_datos_clinicos(
    pdf: _InformeResultadoPDF,
    *,
    estudio: Estudio,
    analisis: Analisis,
) -> None:
    _dibujar_encabezado_seccion(pdf, "Datos clínicos del estudio")

    paciente_u = estudio.paciente.usuario if estudio.paciente else None
    medico_u = estudio.medico.usuario if estudio.medico else None
    patologia = estudio.patologia_sospechada

    nombre_paciente = f"{paciente_u.nombre} {paciente_u.apellido}".strip() if paciente_u else "No informado"
    sub_paciente = (
        f"DNI: {estudio.paciente.dni} · Nacimiento: {_formatear_fecha(estudio.paciente.fecha_nacimiento)}"
        if estudio.paciente
        else "-"
    )
    nombre_medico = f"{medico_u.nombre} {medico_u.apellido}".strip() if medico_u else "No informado"
    sub_medico = f"Matrícula: {estudio.medico.matricula}" if estudio.medico else "-"
    nombre_patologia = patologia.nombre if patologia else "No especificada"
    tipo_texto = f"{_etiqueta_tipo_analisis(analisis.tipo)} · Análisis #{analisis.id}"

    genes_ordenados = sorted(
        {
            f"{ag.gen.simbolo} ({ag.gen.nombre})" if ag.gen.nombre else ag.gen.simbolo
            for ag in analisis.genes
            if ag.gen is not None
        }
    )
    texto_genes = ", ".join(genes_ordenados) or "Sin genes asociados"

    ancho_col = 82.0
    ancho_genes = ANCHO_CONTENIDO_MM - 8.0
    pdf.set_font("Helvetica", "", 8.8)
    lineas_genes = pdf.medir_lineas(texto_genes, ancho_genes, 4.4)
    pdf.set_font("Helvetica", "B", 9.5)
    lineas_pat = pdf.medir_lineas(nombre_patologia, ancho_col, 4.6)

    alto_fila_1 = 15.8
    alto_fila_2 = max(11.0, 5.2 + len(lineas_pat) * 4.6 + (5.2 if estudio.es_pompe_urgente else 0.0))
    alto_genes = 6.2 + len(lineas_genes) * 4.4
    altura_total = 4.0 + alto_fila_1 + alto_fila_2 + 3.0 + alto_genes + 3.5

    pdf.asegurar_espacio(altura_total)
    y0 = pdf.get_y()

    pdf.set_fill_color(*_FONDO_TARJETA)
    pdf.set_draw_color(*_BORDE_SUAVE)
    pdf.set_line_width(0.28)
    pdf.rect(MARGEN_X_MM, y0, ANCHO_CONTENIDO_MM, altura_total, style="DF", round_corners=True, corner_radius=2.0)

    x_col1 = MARGEN_X_MM + 4.0
    x_col2 = MARGEN_X_MM + 92.0
    y_f1 = y0 + 3.5

    # Fila 1: Paciente | Medico tratante
    pdf.set_xy(x_col1, y_f1)
    pdf.set_font("Helvetica", "B", 7.0)
    pdf.set_text_color(*_TEXTO_ATENUADO)
    pdf.cell(ancho_col, 3.6, _texto_latin1("PACIENTE"))
    pdf.set_xy(x_col1, y_f1 + 3.6)
    pdf.set_font("Helvetica", "B", 9.8)
    pdf.set_text_color(*_TEXTO_PRINCIPAL)
    pdf.cell(ancho_col, 4.8, _texto_latin1(nombre_paciente))
    pdf.set_xy(x_col1, y_f1 + 8.4)
    pdf.set_font("Helvetica", "", 8.2)
    pdf.set_text_color(*_TEXTO_SECUNDARIO)
    pdf.cell(ancho_col, 4.2, _texto_latin1(sub_paciente))

    pdf.set_xy(x_col2, y_f1)
    pdf.set_font("Helvetica", "B", 7.0)
    pdf.set_text_color(*_TEXTO_ATENUADO)
    pdf.cell(ancho_col, 3.6, _texto_latin1("MÉDICO TRATANTE"))
    pdf.set_xy(x_col2, y_f1 + 3.6)
    pdf.set_font("Helvetica", "B", 9.8)
    pdf.set_text_color(*_TEXTO_PRINCIPAL)
    pdf.cell(ancho_col, 4.8, _texto_latin1(nombre_medico))
    pdf.set_xy(x_col2, y_f1 + 8.4)
    pdf.set_font("Helvetica", "", 8.2)
    pdf.set_text_color(*_TEXTO_SECUNDARIO)
    pdf.cell(ancho_col, 4.2, _texto_latin1(sub_medico))

    # Fila 2: Patologia sospechada | Tipo de analisis
    y_f2 = y_f1 + alto_fila_1
    pdf.set_xy(x_col1, y_f2)
    pdf.set_font("Helvetica", "B", 7.0)
    pdf.set_text_color(*_TEXTO_ATENUADO)
    pdf.cell(ancho_col, 3.6, _texto_latin1("PATOLOGÍA SOSPECHADA"))
    pdf.set_xy(x_col1, y_f2 + 3.8)
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_text_color(*_TEXTO_PRINCIPAL)
    pdf.multi_cell(ancho_col, 4.6, _texto_latin1(nombre_patologia))

    if estudio.es_pompe_urgente:
        y_badge = y_f2 + 4.4 + len(lineas_pat) * 4.6
        pdf.set_fill_color(254, 226, 226)
        pdf.set_draw_color(252, 165, 165)
        pdf.set_line_width(0.25)
        pdf.rect(x_col1, y_badge, 30.0, 4.6, style="DF", round_corners=True, corner_radius=1.5)
        pdf.set_xy(x_col1, y_badge + 0.1)
        pdf.set_font("Helvetica", "B", 7.0)
        pdf.set_text_color(185, 28, 28)
        pdf.cell(30.0, 4.4, _texto_latin1("POMPE URGENTE"), align="C")

    pdf.set_xy(x_col2, y_f2)
    pdf.set_font("Helvetica", "B", 7.0)
    pdf.set_text_color(*_TEXTO_ATENUADO)
    pdf.cell(ancho_col, 3.6, _texto_latin1("TIPO DE ANÁLISIS"))
    pdf.set_xy(x_col2, y_f2 + 3.8)
    pdf.set_font("Helvetica", "", 9.2)
    pdf.set_text_color(*_TEXTO_PRINCIPAL)
    pdf.cell(ancho_col, 4.6, _texto_latin1(tipo_texto))

    # Separador + Genes analizados
    y_sep = y_f2 + alto_fila_2 + 1.2
    pdf.set_draw_color(*_BORDE_FILA)
    pdf.set_line_width(0.25)
    pdf.line(x_col1, y_sep, MARGEN_X_MM + ANCHO_CONTENIDO_MM - 4.0, y_sep)

    y_genes = y_sep + 2.2
    pdf.set_xy(x_col1, y_genes)
    pdf.set_font("Helvetica", "B", 7.0)
    pdf.set_text_color(*_TEXTO_ATENUADO)
    pdf.cell(ancho_genes, 3.6, _texto_latin1(f"GENES ANALIZADOS ({len(genes_ordenados)})"))
    pdf.set_xy(x_col1, y_genes + 4.0)
    pdf.set_font("Helvetica", "", 8.8)
    pdf.set_text_color(*_TEXTO_PRINCIPAL)
    pdf.multi_cell(ancho_genes, 4.4, _texto_latin1(texto_genes), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_y(y0 + altura_total + 6.0)


def _dibujar_cabecera_tabla_variantes(pdf: _InformeResultadoPDF) -> None:
    y = pdf.get_y()
    alto_hdr = 7.4
    pdf.set_fill_color(*_AZUL_MARCA)
    pdf.rect(MARGEN_X_MM, y, ANCHO_CONTENIDO_MM, alto_hdr, style="F", round_corners=True, corner_radius=1.4)

    pdf.set_font("Helvetica", "B", 8.0)
    pdf.set_text_color(*_BLANCO)
    titulos = ("GEN", "NOTACIÓN HGVS", "CLINVAR ID", "CLASIFICACIÓN")
    alineaciones = ("L", "L", "L", "C")
    x = MARGEN_X_MM
    for ancho, titulo, alig in zip(_COLS_VARIANTES, titulos, alineaciones, strict=True):
        pad = 2.5 if alig == "L" else 0.0
        pdf.set_xy(x + pad, y + 0.2)
        pdf.cell(ancho - pad * 2, alto_hdr - 0.4, _texto_latin1(titulo), align=alig)
        x += ancho
    pdf.set_y(y + alto_hdr)


def _dibujar_tabla_variantes(pdf: _InformeResultadoPDF, variantes: list[Variante]) -> None:
    resumen = "Sin hallazgos" if not variantes else (
        "1 variante" if len(variantes) == 1 else f"{len(variantes)} variantes"
    )
    _dibujar_encabezado_seccion(pdf, "Variantes encontradas", detalle_derecho=resumen)

    if not variantes:
        pdf.asegurar_espacio(14.0)
        y = pdf.get_y()
        pdf.set_fill_color(*_FONDO_TARJETA)
        pdf.set_draw_color(*_BORDE_SUAVE)
        pdf.set_line_width(0.25)
        pdf.rect(MARGEN_X_MM, y, ANCHO_CONTENIDO_MM, 12.0, style="DF", round_corners=True, corner_radius=2.0)
        pdf.set_xy(MARGEN_X_MM + 4.0, y + 3.4)
        pdf.set_font("Helvetica", "", 9.2)
        pdf.set_text_color(*_TEXTO_SECUNDARIO)
        pdf.cell(
            ANCHO_CONTENIDO_MM - 8.0,
            5.2,
            _texto_latin1("No se detectaron variantes respecto al genoma de referencia."),
        )
        pdf.set_y(y + 16.0)
        return

    # Evitar cabecera huerfana: exige espacio para cabecera + al menos una fila
    pdf.asegurar_espacio(18.0)
    _dibujar_cabecera_tabla_variantes(pdf)

    w_gen, w_not, w_clin, w_clas = _COLS_VARIANTES
    for idx, var in enumerate(variantes):
        simbolo = var.gen.simbolo if var.gen else f"Gen#{var.gen_id}"
        es_hs = bool(var.gen and var.gen.es_hallazgo_secundario)
        clinvar = var.clinvar_id or "-"

        pdf.set_font("Courier", "", 8.6)
        lineas_not = pdf.medir_lineas(var.notacion, w_not - 5.0, 4.3)
        pdf.set_font("Courier", "", 8.2)
        lineas_clin = pdf.medir_lineas(clinvar, w_clin - 5.0, 4.3)

        alto_gen = 8.4 if es_hs else 4.6
        alto_fila = max(9.0, alto_gen + 3.2, max(len(lineas_not), len(lineas_clin)) * 4.3 + 4.0)

        if pdf.asegurar_espacio(alto_fila):
            _dibujar_cabecera_tabla_variantes(pdf)

        y = pdf.get_y()
        if idx % 2 == 1:
            pdf.set_fill_color(*_FONDO_CEBRA)
            pdf.rect(MARGEN_X_MM, y, ANCHO_CONTENIDO_MM, alto_fila, style="F")

        pdf.set_draw_color(*_BORDE_FILA)
        pdf.set_line_width(0.22)
        pdf.line(MARGEN_X_MM, y + alto_fila, MARGEN_X_MM + ANCHO_CONTENIDO_MM, y + alto_fila)

        # Col 1: Gen (+ marca discreta de hallazgo secundario si aplica)
        x = MARGEN_X_MM
        pdf.set_xy(x + 2.5, y + (1.8 if es_hs else (alto_fila - 4.6) / 2.0))
        pdf.set_font("Helvetica", "B", 9.0)
        pdf.set_text_color(*_TEXTO_PRINCIPAL)
        pdf.cell(w_gen - 5.0, 4.6, _texto_latin1(simbolo))
        if es_hs:
            pdf.set_xy(x + 2.5, y + 6.0)
            pdf.set_font("Helvetica", "", 6.8)
            pdf.set_text_color(*_TEXTO_ATENUADO)
            pdf.cell(w_gen - 5.0, 3.4, _texto_latin1("Hallazgo secundario"))

        # Col 2: Notacion HGVS en fuente monoespaciada
        x += w_gen
        y_not = y + max(2.0, (alto_fila - len(lineas_not) * 4.3) / 2.0)
        pdf.set_xy(x + 2.5, y_not)
        pdf.set_font("Courier", "", 8.6)
        pdf.set_text_color(*_TEXTO_PRINCIPAL)
        pdf.multi_cell(w_not - 5.0, 4.3, _texto_latin1(var.notacion))

        # Col 3: ClinVar ID
        x += w_not
        y_clin = y + max(2.0, (alto_fila - len(lineas_clin) * 4.3) / 2.0)
        pdf.set_xy(x + 2.5, y_clin)
        pdf.set_font("Courier", "", 8.2)
        pdf.set_text_color(*_TEXTO_SECUNDARIO)
        pdf.multi_cell(w_clin - 5.0, 4.3, _texto_latin1(clinvar))

        # Col 4: Pill de clasificacion clinica
        x += w_clin
        etiqueta, fondo_p, borde_p, texto_p = _ESTILO_CLASIFICACION.get(
            var.clasificacion,
            (var.clasificacion.value.capitalize(), _FONDO_TARJETA, _BORDE_SUAVE, _TEXTO_SECUNDARIO),
        )
        pill_w = 27.0
        pill_h = 5.4
        px = x + (w_clas - pill_w) / 2.0
        py = y + (alto_fila - pill_h) / 2.0
        pdf.set_fill_color(*fondo_p)
        pdf.set_draw_color(*borde_p)
        pdf.set_line_width(0.25)
        pdf.rect(px, py, pill_w, pill_h, style="DF", round_corners=True, corner_radius=1.8)
        pdf.set_xy(px, py + 0.1)
        pdf.set_font("Helvetica", "B", 7.6)
        pdf.set_text_color(*texto_p)
        pdf.cell(pill_w, pill_h - 0.2, _texto_latin1(etiqueta), align="C")

        pdf.set_y(y + alto_fila)

    pdf.ln(4.0)


def construir_pdf_resultado(
    *,
    estudio: Estudio,
    analisis: Analisis,
    variantes: list[Variante],
    diagnostico: ConclusionDiagnostica,
    fecha_proximo_estudio: Any,
    generado_en: datetime,
) -> _InformeResultadoPDF:
    """Construye el documento PDF vectorial ISO A4 listo para escribirse en disco."""
    tipo_etiqueta = _etiqueta_tipo_analisis(analisis.tipo)
    emitido_str = generado_en.strftime("%d/%m/%Y %H:%M")

    pdf = _InformeResultadoPDF(
        estudio_id=estudio.id,
        analisis_id=analisis.id,
        tipo_etiqueta=tipo_etiqueta,
        emitido_str=emitido_str,
    )
    pdf.set_title(_texto_latin1(f"Informe de Resultado - Estudio #{estudio.id}"))
    pdf.set_author(_texto_latin1("Exoma Clínico - Coordinación de Laboratorio"))
    pdf.set_subject(_texto_latin1(f"Resultado de estudio de exoma clínico ({diagnostico.value})"))
    pdf.set_creator(_texto_latin1("Sistema de Seguimiento de Estudios de Exoma Clínico"))

    pdf.add_page()
    _dibujar_banner_diagnostico(
        pdf,
        diagnostico=diagnostico,
        fecha_proximo_estudio=fecha_proximo_estudio,
    )
    _dibujar_tarjeta_datos_clinicos(pdf, estudio=estudio, analisis=analisis)
    _dibujar_tabla_variantes(pdf, variantes)

    # Nota de cierre clinico: se ubica en la pagina actual si cabe, evitando paginas casi vacias
    nota = (
        "Nota clínica: Este informe debe interpretarse en el contexto de la historia clínica del paciente "
        "y bajo asesoramiento genético profesional. Documento generado electrónicamente por el "
        "Sistema de Seguimiento de Estudios de Exoma Clínico."
    )
    pdf.set_font("Helvetica", "I", 7.8)
    lineas_nota = pdf.medir_lineas(nota, ANCHO_CONTENIDO_MM - 6.0, 3.8)
    alto_nota = len(lineas_nota) * 3.8 + 5.0
    pdf.asegurar_espacio(alto_nota)
    y_nota = pdf.get_y() + 1.0
    pdf.set_fill_color(*_FONDO_TARJETA)
    pdf.set_draw_color(*_BORDE_FILA)
    pdf.set_line_width(0.22)
    pdf.rect(MARGEN_X_MM, y_nota, ANCHO_CONTENIDO_MM, alto_nota, style="DF", round_corners=True, corner_radius=1.6)
    pdf.set_xy(MARGEN_X_MM + 3.0, y_nota + 2.4)
    pdf.set_text_color(*_TEXTO_ATENUADO)
    pdf.multi_cell(ANCHO_CONTENIDO_MM - 6.0, 3.8, _texto_latin1(nota))

    return pdf
