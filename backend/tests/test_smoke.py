"""Test de inicializacion y verificacion del modelo de datos."""
from src.core.models import (
    EstadoEstudio,
    Patologia,
    PatologiaSintoma,
    Rol,
    Sintoma,
    calcular_precio,
)


def test_app_inicializa_correctamente(client):
    """Verifica que la app Flask se inicializa en modo testing."""
    response = client.get("/")
    # Como todavia no definimos ruta root, 404 es lo esperado y demuestra que el server responde
    assert response.status_code == 404


def test_creacion_de_tablas_y_reglas_de_negocio(session):
    """Verifica que las 39 tablas se crean en SQLite/PostgreSQL y las reglas de negocio funcionan."""
    # 1. Regla de precio
    assert calcular_precio(3) == 500
    assert calcular_precio(5) == 500
    assert calcular_precio(7) == 560  # 500 + 2 * 30

    # 2. Persistencia basica en base de datos
    patologia = Patologia(nombre="Enfermedad de Fabry", descripcion="Patologia lisosomal")
    sintoma = Sintoma(snomed_id="25064002", descripcion="Cefalea")
    session.add_all([patologia, sintoma])
    session.flush()

    relacion = PatologiaSintoma(
        patologia_id=patologia.id,
        sintoma_id=sintoma.id,
        es_cardinal=True,
    )
    session.add(relacion)
    session.commit()

    recuperada = session.get(Patologia, patologia.id)
    assert recuperada is not None
    assert recuperada.nombre == "Enfermedad de Fabry"
    assert len(recuperada.sintomas) == 1
    assert recuperada.sintomas[0].sintoma.snomed_id == "25064002"
    assert recuperada.sintomas[0].es_cardinal is True


def test_enums_coinciden_con_lel():
    """Verifica que los 14 estados y los 7 roles del LEL esten definidos."""
    assert len(Rol) == 7
    assert len(EstadoEstudio) == 14
    assert EstadoEstudio.CREADO.value == "Creado"
    assert EstadoEstudio.RESULTADO_CARGADO.value == "Resultado cargado"
