"""
Estimación de ganancia y precio al comprar, teniendo en cuenta la brecha cambiaria.

Todo se lleva a bolívares, que es lo que de verdad entra y sale:
- Lo que costará pagar al proveedor: costo × tasa prevista el día del pago (Z).
- Lo que entrará al vender: precio × tasa media de venta prevista (X̄). Las ventas cobradas
  en $ o USDT valen Z (esos dólares se cambian el día del pago).

    margen previsto = 1 − costo en Bs ÷ (precio × X̄)
    precio para un margen m = costo en Bs ÷ (X̄ × (1 − m))

El margen estimado, en cambio, es solo (precio − costo) ÷ precio, sin tasas.
"""
from decimal import Decimal

CIEN = Decimal(100)

# Escenarios: cuánto sube el USDT al mes respecto a lo previsto
ESCENARIOS = (
    ('no_cambia', 'Si la brecha no cambia'),
    ('sigue', 'Si sigue como va'),
    ('se_agranda', 'Si se agranda'),
)
AGRANDA_PUNTOS = Decimal(2)  # "se agranda": el USDT sube 2 puntos más al mes


def _d(valor):
    return Decimal(str(valor if valor is not None else 0))


def proyectar(tasa, ritmo_pct, meses):
    """Tasa dentro de 'meses' si sube 'ritmo_pct' % al mes (interés compuesto)."""
    return _d(tasa) * Decimal(str((1 + float(ritmo_pct) / 100) ** float(meses)))


class Previsiones(object):
    def __init__(self, bcv, usdt, ritmo_bcv=3, ritmo_usdt=4, meses_venta=2, pct_dolares=30, margen_objetivo=40):
        self.bcv = _d(bcv)
        self.usdt = _d(usdt)
        self.ritmo_bcv = _d(ritmo_bcv)
        self.ritmo_usdt = _d(ritmo_usdt)
        self.meses_venta = _d(meses_venta)
        self.pct_dolares = _d(pct_dolares)
        self.margen_objetivo = _d(margen_objetivo)


def _tasas(prev, forma_pago, plazo_meses, ritmo_usdt):
    """(Z, X̄): tasa prevista de pago y tasa media de venta prevista."""
    usdt_al_pagar = proyectar(prev.usdt, ritmo_usdt, plazo_meses)
    if forma_pago == 'bs_bcv':
        z = proyectar(prev.bcv, prev.ritmo_bcv, plazo_meses)
    else:  # bs_usdt; en dólares también: los dólares cuestan USDT
        z = usdt_al_pagar
    x_bs = proyectar(prev.bcv, prev.ritmo_bcv, float(prev.meses_venta) / 2)  # a mitad del periodo de venta
    s = prev.pct_dolares / CIEN
    x_media = s * usdt_al_pagar + (1 - s) * x_bs
    return z, x_media


def estimar(costo, precio, forma_pago, plazo_meses, prev, ritmo_usdt=None):
    """
    costo: en $ (en Bs si forma_pago es 'bs_fijos'). Devuelve un dict con los márgenes en %
    (Decimal o None) y los precios sugeridos en $.
    """
    costo, precio = _d(costo), _d(precio)
    ritmo_usdt = prev.ritmo_usdt if ritmo_usdt is None else _d(ritmo_usdt)
    z, x_media = _tasas(prev, forma_pago, plazo_meses, ritmo_usdt)
    if forma_pago == 'bs_fijos':
        costo_bs = costo
        costo_usd = costo / prev.bcv if prev.bcv else Decimal(0)
    else:
        costo_bs = costo * z
        costo_usd = costo
    r = {'tasa_pago': z, 'tasa_venta': x_media, 'costo_bs': costo_bs,
         'estimado': None, 'previsto': None, 'precio_objetivo': None, 'precio_mantener': None}
    if precio > 0:
        r['estimado'] = (precio - costo_usd) / precio * CIEN
    if precio > 0 and x_media > 0:
        r['previsto'] = (1 - costo_bs / (precio * x_media)) * CIEN
    if x_media > 0 and prev.margen_objetivo < CIEN:
        r['precio_objetivo'] = costo_bs / (x_media * (1 - prev.margen_objetivo / CIEN))
        if r['estimado'] is not None and r['estimado'] < CIEN:
            r['precio_mantener'] = costo_bs / (x_media * (1 - r['estimado'] / CIEN))
    return r


def escenarios(costo, precio, forma_pago, plazo_meses, prev):
    """Margen previsto (%) en los tres escenarios de brecha."""
    ritmos = {
        'no_cambia': prev.ritmo_bcv,                    # el USDT sube igual que el BCV
        'sigue': prev.ritmo_usdt,
        'se_agranda': prev.ritmo_usdt + AGRANDA_PUNTOS,
    }
    return {clave: estimar(costo, precio, forma_pago, plazo_meses, prev, ritmo)['previsto']
            for clave, ritmo in ritmos.items()}
