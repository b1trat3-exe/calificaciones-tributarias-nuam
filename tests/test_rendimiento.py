"""Pruebas de rendimiento básicas (tiempos medidos con el cliente de pruebas de Flask)."""
import time

from conftest import token, datos_calificacion
from factores import calcular_factores
from models import db, Calificacion
import app as nuam


def test_rendimiento_calculo_de_factores():
    montos = {n: 1000.0 + n for n in range(8, 38)}
    t0 = time.perf_counter()
    for _ in range(5000):
        calcular_factores(montos)
    total = time.perf_counter() - t0
    print(f"\n[PERF] 5000 cálculos de factores: {total*1000:.1f} ms (promedio {total/5000*1000:.3f} ms)")
    assert total < 2.0


def test_rendimiento_ingreso_de_100_calificaciones(admin):
    tiempos = []
    for i in range(100):
        t = token(admin, "/calificaciones/nueva")
        d = datos_calificacion(csrf_token=t, secuencia_evento=str(10100 + i), instrumento=f"INST{i}")
        t0 = time.perf_counter()
        assert admin.post("/calificaciones/nueva", data=d).status_code == 302
        tiempos.append(time.perf_counter() - t0)
    prom, mx = sum(tiempos) / len(tiempos), max(tiempos)
    print(f"\n[PERF] 100 ingresos: promedio {prom*1000:.1f} ms, máximo {mx*1000:.1f} ms")
    assert prom < 0.5


def test_rendimiento_grilla_con_300_registros(admin, app):
    with app.app_context():
        for i in range(300):
            db.session.add(Calificacion(mercado="Acciones", instrumento=f"X{i}", ejercicio=2025,
                                        secuencia_evento=20000 + i, fecha_pago=__import__("datetime").date(2025, 5, 1),
                                        usuario_id=1))
        db.session.commit()
    tiempos = []
    for _ in range(20):
        t0 = time.perf_counter()
        assert admin.get("/mantenedor").status_code == 200
        tiempos.append(time.perf_counter() - t0)
    prom, mx = sum(tiempos) / len(tiempos), max(tiempos)
    print(f"\n[PERF] Grilla con 300 registros (20 cargas): promedio {prom*1000:.1f} ms, máximo {mx*1000:.1f} ms")
    assert prom < 1.0
