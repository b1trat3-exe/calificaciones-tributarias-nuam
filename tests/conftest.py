import os
import re
import sys
import tempfile

import pytest

# Base de datos y bitácora temporales: las pruebas nunca tocan los datos reales.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_tmp, "prueba.db")
os.environ["LOG_DIR"] = os.path.join(_tmp, "datos")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as nuam  # noqa: E402
from models import db  # noqa: E402


@pytest.fixture()
def app():
    with nuam.app.app_context():
        db.drop_all()
        nuam.inicializar_bd()
    yield nuam.app


def token(cliente, url="/login"):
    html = cliente.get(url).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def iniciar_sesion(app, correo="admin@nuam.cl", clave="Admin1234"):
    c = app.test_client()
    r = c.post("/login", data={"csrf_token": token(c), "correo": correo, "clave": clave})
    return c, r


@pytest.fixture()
def admin(app):
    return iniciar_sesion(app)[0]


@pytest.fixture()
def corredor(app):
    return iniciar_sesion(app, "corredor1@nuam.cl", "Corredor1234")[0]


def datos_calificacion(**extra):
    d = {"mercado": "Acciones", "instrumento": "CHILE", "ejercicio": "2025",
         "secuencia_evento": "10050", "fecha_pago": "2025-05-10", "dividendo": "0",
         "valor_historico": "0", "factor_actualizacion": "0", "descripcion": "Prueba",
         "modo": "montos"}
    montos = {8: "192770580", 9: "64161878", 11: "111812860"}
    for n in range(8, 38):
        d[f"monto_{n}"] = montos.get(n, "0")
        d[f"factor_{n}"] = "0"
    d.update(extra)
    return d
