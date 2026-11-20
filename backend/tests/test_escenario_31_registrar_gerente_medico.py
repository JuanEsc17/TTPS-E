from src.core.models import Especialidad, Usuario
from src.core.services.seguridad import (
    SCOPE_ACCESO_COMPLETO,
    emitir_token,
    hashear_password,
)

URL = "/api/v1/admin/gerentes-medicos"

def _seed_especialidades(session):              # crea 2 especialidades en la BD
    e1, e2 = Especialidad(nombre="Genetica Medica"), Especialidad(nombre="Pediatria")
    session.add_all([e1, e2]); session.commit()
    return e1, e2

def _crear_usuario(session, rol, email="admin@exoma.com"):   # crea un usuario cualquiera
    u = Usuario(email=email, password_hash=hashear_password("Clave1234"), rol=rol,
                nombre="X", apellido="Y", telefono="1", debe_cambiar_password=False)
    session.add(u); session.commit()
    return u

def _headers(app, usuario):                     # "inicia sesion" generando un token (igual que test_escenario_11)
    token = emitir_token(str(app.config["SECRET_KEY"]), usuario_id=usuario.id,
                         rol=usuario.rol.value, scope=SCOPE_ACCESO_COMPLETO, ttl_segundos=3600)
    return {"Authorization": f"Bearer {token}"}

def _payload(ids):
    return {"nombre": "Laura", "apellido": "Gómez", "telefono": "+5492214556677",
            "email": "laura.gomez@exoma.com", "password": "ClaveSegura2026!",
            "matricula": "MP-114589", "especialidades_ids": ids}