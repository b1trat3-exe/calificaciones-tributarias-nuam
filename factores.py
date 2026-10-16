"""Reglas de negocio: conversión de montos a factores (hoja 3.2 Homologación del HDU)."""

# Etiquetas de los factores 8 al 37 (según el certificado 70 / DJ 1948)
ETIQUETAS = {
    8: "Con crédito por IDPC generados a contar del 01.01.2017",
    9: "Con crédito por IDPC acumulados hasta el 31.12.2016",
    10: "Con derecho a crédito por pago de IDPC voluntario",
    11: "Sin derecho a crédito",
    12: "Rentas provenientes del registro RAP y Diferencia Inicial (ex Art. 14 TER A)",
    13: "Otras rentas percibidas sin prioridad en su orden de imputación",
    14: "Exceso distribuciones desproporcionadas (N°9 Art. 14 A)",
    15: "Utilidades afectadas con ISFUT Ley N°20.780",
    16: "Rentas generadas hasta el 31.12.1983 y/o ISFUT Ley N°21.210",
    17: "Rentas exentas de IGC (Art. 11 Ley 18.401), afectas a Impuesto Adicional",
    18: "Rentas exentas de IGC y/o Impuesto Adicional",
    19: "Ingresos no constitutivos de renta",
    20: "Créd. desde 2017, rentas afectas, no sujetos a restitución hasta 2019, sin devolución",
    21: "Créd. desde 2017, rentas afectas, no sujetos a restitución hasta 2019, con devolución",
    22: "Créd. desde 2017, rentas afectas, no sujetos a restitución desde 2020, sin devolución",
    23: "Créd. desde 2017, rentas afectas, no sujetos a restitución desde 2020, con devolución",
    24: "Créd. desde 2017, rentas afectas, sujetos a restitución, sin devolución",
    25: "Créd. desde 2017, rentas afectas, sujetos a restitución, con devolución",
    26: "Créd. desde 2017, rentas exentas, sujetos a restitución, sin devolución",
    27: "Créd. desde 2017, rentas exentas, sujetos a restitución, con devolución",
    28: "Créd. desde 2017: Crédito por IPE",
    29: "Créd. hasta 2016, rentas afectas, sin derecho a devolución",
    30: "Créd. hasta 2016, rentas afectas, con derecho a devolución",
    31: "Créd. hasta 2016, rentas exentas (Art. 11 Ley 18.401), sin devolución",
    32: "Créd. hasta 2016, rentas exentas (Art. 11 Ley 18.401), con devolución",
    33: "Créd. hasta 2016: Crédito por IPE",
    34: "Crédito por impuesto tasa adicional, Ex. Art. 21 LIR",
    35: "Tasa efectiva del crédito del FUT (TEF)",
    36: "Tasa efectiva del crédito del FUNT (TEX)",
    37: "Devolución de capital Art. 17 N°7 LIR",
}

NUMEROS = list(range(8, 38))          # 8..37
HASTA_DIVISOR = range(8, 20)          # suma de montos 8..19 (denominador)
CALCULADOS = range(8, 34)             # 8..33 se calculan; 34..37 se ingresan tal cual
TOLERANCIA = 1e-7


def calcular_factores(montos):
    """montos: dict {n: float}. Devuelve dict {n: factor} con 8 decimales."""
    total = sum(montos.get(n, 0.0) for n in HASTA_DIVISOR)
    factores = {}
    for n in NUMEROS:
        if n in CALCULADOS:
            factores[n] = round(montos.get(n, 0.0) / total, 8) if total > 0 else 0.0
        else:
            factores[n] = round(montos.get(n, 0.0), 8)
    return factores


def validar_factores(factores):
    """Devuelve lista de errores (vacía si todo está bien)."""
    errores = []
    for n in NUMEROS:
        v = factores.get(n, 0.0)
        if v < 0 or v > 1 + TOLERANCIA:
            errores.append(f"El factor {n} debe estar entre 0 y 1.")
    suma = sum(factores.get(n, 0.0) for n in range(8, 17))
    if suma > 1 + TOLERANCIA:
        errores.append(f"La suma de los factores 8 al 16 no puede superar 1 (actual: {suma:.8f}).")
    return errores
