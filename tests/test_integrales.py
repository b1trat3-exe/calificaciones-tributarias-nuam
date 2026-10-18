"""Pruebas integrales: flujos completos contra la aplicación (rutas, base de datos, sesión)."""
import json
import os
import re

from conftest import token, iniciar_sesion, datos_calificacion
from models import db, Calificacion, LogAuditoria, Usuario
import app as nuam


def nueva(cli, **extra):
    t = token(cli, "/calificaciones/nueva")
    return cli.post("/calificaciones/nueva", data=datos_calificacion(csrf_token=t, **extra))


# ---------- Autenticación ----------
def test_login_correcto_redirige_al_mantenedor(app):
    c, r = iniciar_sesion(app)
    assert r.status_code == 302 and r.headers["Location"].endswith("/mantenedor")


def test_login_incorrecto_no_inicia_sesion(app):
    c, r = iniciar_sesion(app, clave="mala")
    assert r.status_code == 200
    assert c.get("/mantenedor").status_code == 302


def test_acceso_sin_sesion_redirige_a_login(app):
    r = app.test_client().get("/mantenedor")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_bloqueo_tras_cinco_intentos_fallidos(app):
    for _ in range(5):
        iniciar_sesion(app, clave="mala")
    c, r = iniciar_sesion(app, clave="Admin1234")     # clave correcta, pero cuenta bloqueada
    assert c.get("/mantenedor").status_code == 302
    with app.app_context():
        assert Usuario.query.filter_by(correo="admin@nuam.cl").first().bloqueado_hasta is not None


def test_post_sin_token_csrf_es_rechazado(app):
    c = app.test_client()
    c.get("/login")
    assert c.post("/login", data={"correo": "admin@nuam.cl", "clave": "Admin1234"}).status_code == 400


def test_cabeceras_de_seguridad(admin):
    h = admin.get("/mantenedor").headers
    assert h["X-Frame-Options"] == "DENY" and h["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'self'" in h["Content-Security-Policy"]


# ---------- Mantenedor ----------
def test_ingreso_por_montos_calcula_y_guarda_factores(admin, app):
    assert nueva(admin).status_code == 302
    with app.app_context():
        c = Calificacion.query.one()
        assert c.factor_8 == 0.52277431 and c.origen == "manual"


def test_ingreso_por_factores(admin, app):
    d = {"modo": "factores", "factor_8": "0.6", "factor_9": "0.4"}
    assert nueva(admin, **d).status_code == 302
    with app.app_context():
        assert Calificacion.query.one().factor_9 == 0.4


def test_rechaza_suma_de_factores_mayor_a_uno(admin, app):
    r = nueva(admin, modo="factores", factor_8="0.7", factor_9="0.5")
    assert r.status_code == 200 and "superar 1" in r.get_data(as_text=True)
    with app.app_context():
        assert Calificacion.query.count() == 0


def test_rechaza_secuencia_menor_o_igual_a_10000(admin):
    r = nueva(admin, secuencia_evento="500")
    assert r.status_code == 200 and "10.000" in r.get_data(as_text=True)


def test_rechaza_calificacion_duplicada(admin, app):
    nueva(admin)
    r = nueva(admin)
    assert r.status_code == 200 and "Ya existe" in r.get_data(as_text=True)
    with app.app_context():
        assert Calificacion.query.count() == 1


def test_modificar_calificacion(admin, app):
    nueva(admin)
    with app.app_context():
        cid = Calificacion.query.one().id
    t = token(admin, f"/calificaciones/{cid}/editar")
    r = admin.post(f"/calificaciones/{cid}/editar",
                   data=datos_calificacion(csrf_token=t, descripcion="Modificada"))
    assert r.status_code == 302
    with app.app_context():
        assert db.session.get(Calificacion, cid).descripcion == "Modificada"


def test_eliminar_calificacion(admin, app):
    nueva(admin)
    with app.app_context():
        cid = Calificacion.query.one().id
    t = token(admin, "/mantenedor")
    assert admin.post(f"/calificaciones/{cid}/eliminar", data={"csrf_token": t}).status_code == 302
    with app.app_context():
        assert Calificacion.query.count() == 0


def test_filtros_de_la_grilla(admin):
    nueva(admin)
    assert "CHILE" in admin.get("/mantenedor?mercado=Acciones&ejercicio=2025").get_data(as_text=True)
    assert "No hay calificaciones" in admin.get("/mantenedor?mercado=CFI").get_data(as_text=True)
    assert "No hay calificaciones" in admin.get("/mantenedor?ejercicio=2024").get_data(as_text=True)


def test_api_calcular_devuelve_factores(admin):
    t = token(admin, "/calificaciones/nueva")
    r = admin.post("/api/calcular", json={"8": 100, "9": 100}, headers={"X-CSRF-Token": t})
    assert r.status_code == 200 and r.get_json()["factores"]["8"] == 0.5


# ---------- Autorización ----------
def test_corredor_no_ve_calificaciones_de_otro(admin, corredor):
    nueva(admin)
    assert "No hay calificaciones" in corredor.get("/mantenedor").get_data(as_text=True)


def test_corredor_no_puede_editar_ni_eliminar_ajenas(admin, corredor, app):
    nueva(admin)
    with app.app_context():
        cid = Calificacion.query.one().id
    assert corredor.get(f"/calificaciones/{cid}/editar").status_code == 403
    t = token(corredor, "/mantenedor")
    assert corredor.post(f"/calificaciones/{cid}/eliminar", data={"csrf_token": t}).status_code == 403


def test_solo_administrador_ve_el_log(admin, corredor):
    assert admin.get("/log").status_code == 200
    assert corredor.get("/log").status_code == 403


# ---------- Auditoría ----------
def test_operaciones_quedan_en_log_relacional_y_json(admin, app):
    nueva(admin)
    with app.app_context():
        acciones = [l.accion for l in LogAuditoria.query.all()]
        assert "LOGIN" in acciones and "INGRESO" in acciones
    ruta = os.path.join(os.environ["LOG_DIR"], "auditoria.jsonl")
    eventos = [json.loads(l) for l in open(ruta, encoding="utf-8")]
    assert any(e["accion"] == "INGRESO" for e in eventos)


# ---------- Amenazas comunes ----------
def test_xss_se_escapa_en_la_grilla(admin):
    nueva(admin, instrumento="<script>alert(1)</script>")
    html = admin.get("/mantenedor").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


def test_inyeccion_sql_en_login_y_filtros(app, admin):
    c, _ = iniciar_sesion(app, correo="' OR '1'='1", clave="' OR '1'='1")
    assert c.get("/mantenedor").status_code == 302
    assert admin.get("/mantenedor?ejercicio=1;DROP TABLE calificaciones").status_code == 200
    with app.app_context():
        assert Calificacion.query.count() == 0   # la tabla sigue existiendo
