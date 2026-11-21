"""Tests de integridad geometrica/vectorial del PDF de resultados y formato de correos."""
from __future__ import annotations

import re
import zlib
from datetime import date, datetime
from types import SimpleNamespace

from src.core.models import (
    ClasificacionVariante,
    ConclusionDiagnostica,
    TipoAnalisis,
)
from src.core.services.formato_correo import asunto_correo, formatear_correo
from src.core.services.pdf_resultado import construir_pdf_resultado


def _extraer_texto_streams(pdf_bytes: bytes) -> list[str]:
    streams: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf_bytes, flags=re.DOTALL):
        crudo = match.group(1)
        try:
            descomprimido = zlib.decompress(crudo)
        except zlib.error:
            descomprimido = crudo
        texto = descomprimido.decode("latin-1", errors="ignore")
        texto = texto.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
        streams.append(texto)
    return streams


def _estudio_demo(*, es_pompe_urgente: bool = False, cantidad_variantes: int = 2):
    gen_gaa = SimpleNamespace(id=1, simbolo="GAA", nombre="Alpha glucosidase", es_hallazgo_secundario=False)
    gen_brca = SimpleNamespace(id=2, simbolo="BRCA1", nombre="BRCA1 DNA repair", es_hallazgo_secundario=True)
    estudio = SimpleNamespace(
        id=42,
        es_pompe_urgente=es_pompe_urgente,
        paciente=SimpleNamespace(
            dni="40161616",
            fecha_nacimiento=date(1995, 4, 12),
            usuario=SimpleNamespace(nombre="Sofía", apellido="Pérez"),
        ),
        medico=SimpleNamespace(
            matricula="MN-16001",
            usuario=SimpleNamespace(nombre="Juan", apellido="Escudero"),
        ),
        patologia_sospechada=SimpleNamespace(nombre="Enfermedad de Pompe"),
    )
    analisis = SimpleNamespace(
        id=108,
        tipo=TipoAnalisis.INICIAL,
        genes=[SimpleNamespace(gen=gen_gaa), SimpleNamespace(gen=gen_brca)],
    )
    clasificaciones = [
        ClasificacionVariante.PATOGENICA,
        ClasificacionVariante.VUS,
        ClasificacionVariante.BENIGNA,
        ClasificacionVariante.INOCUA,
    ]
    variantes = [
        SimpleNamespace(
            gen_id=1 if i % 2 == 0 else 2,
            gen=gen_gaa if i % 2 == 0 else gen_brca,
            notacion=f"c.{1000 + i}G>A (p.Arg{300 + i}His)",
            clinvar_id=f"VCV0000{10000 + i}",
            clasificacion=clasificaciones[i % len(clasificaciones)],
        )
        for i in range(cantidad_variantes)
    ]
    return estudio, analisis, variantes


def test_pdf_resultado_geometria_a4_vectorial_una_pagina_y_sin_reemplazos():
    estudio, analisis, variantes = _estudio_demo(es_pompe_urgente=True, cantidad_variantes=3)
    pdf = construir_pdf_resultado(
        estudio=estudio,
        analisis=analisis,
        variantes=variantes,
        diagnostico=ConclusionDiagnostica.VUS,
        fecha_proximo_estudio=date(2027, 11, 21),
        generado_en=datetime(2026, 11, 21, 14, 30),
    )
    pdf_bytes = bytes(pdf.output())

    assert pdf_bytes.startswith(b"%PDF-")
    # ISO A4 exacto (595.28 x 841.89 pt), sin pagina fantasma y 100% vectorial (sin imagenes raster)
    assert b"/MediaBox [0 0 595.28 841.89]" in pdf_bytes
    assert pdf.page_no() == 1
    assert b"/Subtype /Image" not in pdf_bytes
    assert b"/Title" in pdf_bytes and b"/Author" in pdf_bytes

    texto = "\n".join(_extraer_texto_streams(pdf_bytes))
    assert "POMPE URGENTE" in texto
    assert "VUS (Variante de Significado Incierto)" in texto
    assert "Recomendacion de nuevo estudio / reevaluacion VUS" in texto
    assert "2027-11-21" in texto
    assert "Hallazgo secundario" in texto
    # Ningun caracter no-latin1 degradado a '?'
    assert "?" not in texto


def test_pdf_resultado_multipagina_repite_cabecera_tabla_sin_pagina_fantasma():
    estudio, analisis, variantes = _estudio_demo(cantidad_variantes=28)
    pdf = construir_pdf_resultado(
        estudio=estudio,
        analisis=analisis,
        variantes=variantes,
        diagnostico=ConclusionDiagnostica.POSITIVO,
        fecha_proximo_estudio=None,
        generado_en=datetime(2026, 11, 21, 14, 30),
    )
    pdf_bytes = bytes(pdf.output())
    streams = _extraer_texto_streams(pdf_bytes)

    assert pdf.page_no() >= 2
    assert b"/Subtype /Image" not in pdf_bytes
    # La ultima pagina contiene contenido clinico real (no es una pagina fantasma en blanco)
    texto_total = "\n".join(streams)
    assert "c.1027G>A" in texto_total
    assert texto_total.count("CLINVAR ID") >= 2
    assert "?" not in texto_total


def test_formato_correo_respeta_contrato_texto_plano_y_limites():
    asunto = asunto_correo("  Resultado   disponible  ")
    assert asunto == "[Exoma Clínico] Resultado disponible"
    assert asunto_correo(asunto) == asunto
    assert len(asunto_correo("A" * 300)) <= 200

    cuerpo = formatear_correo(
        titulo="Resultado disponible",
        saludo="Hola Sofía,",
        introduccion="Tu informe ya está listo.",
        destacado=["Conclusión: NEGATIVO"],
        secciones=[("Resumen", ["Estudio: #42", "Patología: Pompe"])],
        cierre="Consultá con tu médico.",
    )
    assert "EXOMA CLÍNICO" in cuerpo
    assert "RESULTADO DISPONIBLE" in cuerpo
    assert "• Estudio: #42" in cuerpo
    assert "<html" not in cuerpo.lower() and "<div" not in cuerpo.lower()
    assert len(cuerpo) <= 10_000

    cuerpo_largo = formatear_correo(titulo="Test", introduccion="X" * 12_000)
    assert len(cuerpo_largo) <= 10_000
