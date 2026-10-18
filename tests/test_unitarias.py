"""Pruebas unitarias: reglas de negocio y funciones puras."""
from factores import calcular_factores, validar_factores
from models import Usuario
import app as nuam

EJEMPLO_EXCEL = {8: 192770580, 9: 64161878, 10: 0, 11: 111812860, 25: 71298705, 30: 15837333}


def test_calculo_coincide_con_excel_del_profesor():
    f = calcular_factores(EJEMPLO_EXCEL)
    assert f[8] == 0.52277431
    assert f[9] == 0.17400052
    assert f[11] == 0.30322517
    assert f[25] == 0.19335488
    assert f[30] == 0.04294924


def test_suma_factores_8_a_19_es_uno():
    f = calcular_factores({8: 50, 9: 30, 11: 20})
    assert abs(sum(f[n] for n in range(8, 20)) - 1) < 1e-7


def test_factores_redondeados_a_8_decimales():
    f = calcular_factores({8: 1, 9: 2})
    assert f[8] == 0.33333333 and f[9] == 0.66666667


def test_total_cero_no_divide_por_cero():
    f = calcular_factores({})
    assert all(v == 0 for v in f.values())


def test_factores_34_a_37_se_copian_sin_dividir():
    f = calcular_factores({8: 100, 35: 0.25})
    assert f[35] == 0.25


def test_validacion_suma_8_a_16_mayor_que_uno():
    errores = validar_factores({8: 0.7, 9: 0.5})
    assert any("suma de los factores 8 al 16" in e for e in errores)


def test_validacion_factor_fuera_de_rango():
    assert validar_factores({8: 1.5}) != []
    assert validar_factores({8: -0.1}) != []


def test_validacion_correcta_no_devuelve_errores():
    assert validar_factores({8: 0.5, 9: 0.5}) == []


def test_a_numero_acepta_coma_decimal_y_vacio():
    assert nuam.a_numero("0,25", "x") == 0.25
    assert nuam.a_numero("", "x") == 0.0


def test_a_numero_rechaza_texto():
    import pytest
    with pytest.raises(ValueError):
        nuam.a_numero("abc", "Monto 8")


def test_contrasena_se_guarda_con_hash():
    u = Usuario(nombre="T", correo="t@t.cl")
    u.set_password("Secreta123")
    assert u.password_hash != "Secreta123"
    assert u.check_password("Secreta123") and not u.check_password("otra")
