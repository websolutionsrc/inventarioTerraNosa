"""
Rentabilidad real de las compras, teniendo en cuenta la brecha cambiaria.

Todo se compara en bolívares, que es lo que de verdad entra y sale:

- Cada venta de un lote aporta los Bs que entraron: precio × cantidad × la tasa con que se cobró.
  Las ventas cobradas en $ o USDT cuentan a la tasa del dólar del día en que se paga al proveedor
  (esos dólares se cambian para pagar).
- Cada unidad cuesta en Bs lo que se pagó al proveedor (costo × tasa de pago Z1). Si la compra
  aún no está pagada, se estima "si se pagase hoy" (a la tasa de la factura, a USDT, a BCV u otra).

    margen real de una venta = 1 − costo en Bs ÷ Bs que entraron
    ganancia real en $ de una venta = margen real × precio de venta en $
    "de cada 100 $ vendidos te quedaron X $" = Σ ganancia real ÷ Σ vendido × 100

La pérdida por brecha de una venta en Bs (solo como medida) es: precio en $ − Bs ÷ tasa USDT del día.
"""
from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from . import services
from .models import AjustesNegocio, AsignacionLote, Compra, LoteCompra, Producto, Venta

CERO = Decimal('0')
CIEN = Decimal('100')
ESCENARIOS = ('factura', 'usdt', 'bcv', 'otra')


def _q(valor, decimales='0.01'):
    return valor.quantize(Decimal(decimales)) if valor is not None else None


def _pct(valor):
    return _q(valor, '0.1') if valor is not None else None


class Contexto(object):
    """Tasas de hoy y escenario para estimar las compras pendientes de pagar."""

    def __init__(self, escenario='factura', tasa=None):
        self.escenario = escenario if escenario in ESCENARIOS else 'factura'
        self.tasa = Decimal(str(tasa)) if tasa else None
        self.bcv = services.ultima_tasa_bcv()
        self.usdt = services.ultima_tasa_usdt()
        self.objetivo = AjustesNegocio.actuales().margen_objetivo

    def tasa_pendiente(self, compra):
        """Tasa a la que se pagaría hoy una compra pendiente según el escenario."""
        if self.escenario == 'otra' and self.tasa:
            return self.tasa
        if self.escenario == 'bcv' or (self.escenario == 'factura' and compra.forma_pago == Compra.FormaPago.BS_BCV):
            return self.bcv
        return self.usdt


class Lote(object):
    """Cálculo de un lote: su costo en Bs por unidad y el resultado de cada venta."""

    def __init__(self, lote, ctx):
        self.lote = lote
        self.compra = compra = lote.compra
        self.ctx = ctx
        f = compra.forma_pago
        total = compra.total_factura
        if compra.pagada:
            self.estimado_pago = False
            self.z = compra.tasa_pago or compra.tasa_usdt_pago or ctx.usdt
            self.z_dolar = compra.tasa_usdt_pago or self.z
            if f == Compra.FormaPago.DOLARES:
                pagado_usd = compra.usd_pagados or total
                self.costo_bs = lote.costo_unitario * pagado_usd / total * self.z_dolar
            else:  # se pagó en Bs: se reparte lo que de verdad se pagó
                self.costo_bs = lote.costo_unitario * compra.bs_pagados / total
        else:
            self.estimado_pago = True
            self.z = ctx.tasa_pendiente(compra)
            self.z_dolar = self.z if (ctx.escenario == 'otra' and ctx.tasa) else ctx.usdt
            if f == Compra.FormaPago.BS_FIJOS:
                self.costo_bs = lote.costo_unitario
            elif f == Compra.FormaPago.DOLARES:
                self.costo_bs = lote.costo_unitario * self.z_dolar
            else:
                self.costo_bs = lote.costo_unitario * (self.z or CERO)
        if f == Compra.FormaPago.BS_FIJOS:
            self.costo_usd = self.costo_bs / self.z_dolar if self.z_dolar else None
            self.z = None  # no hay "tasa de pago": el monto en Bs era fijo
        else:
            self.costo_usd = lote.costo_unitario

    def venta(self, asignacion):
        """Resultado de las unidades de este lote que salieron en una línea de venta."""
        linea = asignacion.linea_venta
        venta = linea.venta
        cantidad = asignacion.cantidad
        precio = linea.precio_unitario or CERO
        vendido = precio * cantidad
        en_bs = Venta.moneda_de(venta.metodo_pago) == 'VES'
        tasa = (venta.tasa_cambio or venta.tasa_bcv) if en_bs else None
        tasa = tasa or self.z_dolar
        entro_bs = vendido * tasa if tasa else CERO
        costo_bs = self.costo_bs * cantidad
        margen = (1 - costo_bs / entro_bs) if entro_bs else None
        ganancia = margen * vendido if margen is not None else None
        brecha = (vendido - entro_bs / venta.tasa_usdt) if (en_bs and venta.tasa_usdt) else CERO
        return {
            'venta': venta.id, 'fecha': venta.fecha, 'metodo_pago': venta.get_metodo_pago_display(),
            'en_bolivares': en_bs, 'cantidad': cantidad, 'precio': precio, 'vendido': vendido, 'tasa': tasa,
            'bs_entraron': entro_bs, 'costo_bs': costo_bs, 'margen': margen, 'ganancia': ganancia, 'brecha': brecha,
        }

    def perdida(self, asignacion):
        """Costo en Bs de unidades que salieron por un ajuste (dañadas, perdidas…)."""
        return self.costo_bs * asignacion.cantidad


def _asignaciones_de_venta(qs):
    return (qs.filter(linea_venta__isnull=False, linea_venta__venta__anulada=False)
            .select_related('linea_venta__venta', 'lote__compra', 'lote__producto'))


def analizar_lote(lote, ctx, con_ventas=True):
    calc = Lote(lote, ctx)
    ventas = [calc.venta(a) for a in _asignaciones_de_venta(lote.asignaciones.all())]
    perdidas = list(lote.asignaciones.filter(movimiento__isnull=False))
    unidades_perdidas = sum(a.cantidad for a in perdidas)
    costo_perdidas_bs = sum((calc.perdida(a) for a in perdidas), CERO)

    vendidas = sum(v['cantidad'] for v in ventas)
    vendido = sum((v['vendido'] for v in ventas), CERO)
    entro_bs = sum((v['bs_entraron'] for v in ventas), CERO)
    ganancia = sum((v['ganancia'] or CERO for v in ventas), CERO)
    tasa_media = entro_bs / vendido if vendido else None
    if costo_perdidas_bs and (tasa_media or calc.z_dolar):
        ganancia -= costo_perdidas_bs / (tasa_media or calc.z_dolar)
    brecha = sum((v['brecha'] for v in ventas), CERO)

    precio_medio = vendido / vendidas if vendidas else lote.producto.precio
    estimado = ((precio_medio - calc.costo_usd) / precio_medio * CIEN
                if precio_medio and calc.costo_usd is not None else None)
    real = ganancia / vendido * CIEN if vendido else None
    costo_real_usd = calc.costo_bs / tasa_media if tasa_media else None

    if lote.compra.pagada:
        estado = 'cerrado' if lote.disponible == 0 else 'pagado'
    else:
        estado = 'pendiente'
    margenes = [v for v in ventas if v['margen'] is not None]
    mejor = max(margenes, key=lambda v: v['margen']) if margenes else None
    peor = min(margenes, key=lambda v: v['margen']) if margenes else None
    bajo_objetivo = sum(1 for v in margenes if v['margen'] * CIEN < ctx.objetivo)

    datos = OrderedDict([
        ('id', lote.id), ('compra', lote.compra_id), ('fecha_compra', lote.compra.fecha),
        ('proveedor', lote.compra.proveedor), ('producto', lote.producto_id), ('producto_nombre', lote.producto.nombre),
        ('forma_pago', lote.compra.forma_pago), ('plazo_meses', lote.compra.plazo_meses), ('vence', lote.compra.vence),
        ('estado', estado), ('estimado_pago', calc.estimado_pago),
        ('cantidad', lote.cantidad), ('vendidas', vendidas), ('quedan', lote.disponible),
        ('perdidas', unidades_perdidas),
        ('costo_unitario', lote.costo_unitario), ('costo_usd', _q(calc.costo_usd)),
        ('tasa_pago', _q(calc.z)), ('tasa_media_venta', _q(tasa_media)),
        ('costo_real_usd', _q(costo_real_usd)),
        ('vendido', _q(vendido)), ('ganancia', _q(ganancia)),
        ('margen_estimado', _pct(estimado)), ('margen_real', _pct(real)),
        ('margen_previsto', lote.margen_previsto), ('brecha', _q(brecha)),
        ('mejor_venta', mejor and {'venta': mejor['venta'], 'margen': _pct(mejor['margen'] * CIEN)}),
        ('peor_venta', peor and {'venta': peor['venta'], 'margen': _pct(peor['margen'] * CIEN)}),
        ('ventas_bajo_objetivo', bajo_objetivo), ('ventas_contadas', len(margenes)),
    ])
    if con_ventas:
        datos['ventas'] = [OrderedDict([
            ('venta', v['venta']), ('fecha', v['fecha']), ('metodo_pago', v['metodo_pago']),
            ('en_bolivares', v['en_bolivares']), ('cantidad', v['cantidad']), ('precio', v['precio']),
            ('tasa', _q(v['tasa'])), ('bs_entraron', _q(v['bs_entraron'])), ('ganancia', _q(v['ganancia'])),
            ('margen', _pct(v['margen'] * CIEN) if v['margen'] is not None else None),
        ]) for v in sorted(ventas, key=lambda v: v['fecha'])]
    return datos


def lotes(ctx, estado=None):
    qs = (LoteCompra.objects.filter(compra__anulada=False).select_related('compra', 'producto')
          .order_by('-compra__fecha', '-compra_id', 'id'))
    resultado = [analizar_lote(l, ctx, con_ventas=False) for l in qs]
    if estado:
        resultado = [r for r in resultado if r['estado'] == estado]
    return resultado


def resumen(ctx, desde, hasta):
    """Resultado de las ventas de un periodo (fechas en hora de Venezuela, ambas incluidas)."""
    inicio = services.rango_del_dia(desde)[0]
    fin = services.rango_del_dia(hasta)[1]
    asignaciones = _asignaciones_de_venta(AsignacionLote.objects.filter(
        linea_venta__venta__fecha__gte=inicio, linea_venta__venta__fecha__lt=fin))
    calculos = {}
    vendido = ganancia = brecha = CERO
    unidades = 0
    for a in asignaciones:
        if a.lote_id not in calculos:
            calculos[a.lote_id] = Lote(a.lote, ctx)
        v = calculos[a.lote_id].venta(a)
        vendido += v['vendido']
        ganancia += v['ganancia'] or CERO
        brecha += v['brecha']
        unidades += v['cantidad']

    # Lo vendido de stock sin compra registrada (sin costo conocido)
    from .models import SalidaInventario
    lineas = SalidaInventario.objects.filter(venta__anulada=False, venta__fecha__gte=inicio, venta__fecha__lt=fin)
    total_lineas = sum(((l.precio_unitario or CERO) * l.cantidad for l in lineas), CERO)
    sin_costo = total_lineas - vendido

    pendientes = Compra.objects.filter(pagada=False, anulada=False)
    pendiente_usd = sum((c.total_factura for c in pendientes if not c.en_bolivares_fijos), CERO)
    proxima = pendientes.order_by('vence').first()
    return OrderedDict([
        ('desde', desde), ('hasta', hasta), ('vendido', _q(vendido)), ('unidades', unidades),
        ('ganancia', _q(ganancia)), ('margen_real', _pct(ganancia / vendido * CIEN) if vendido else None),
        ('brecha', _q(brecha)), ('vendido_sin_costo', _q(sin_costo)), ('vendido_total', _q(total_lineas)),
        ('pendiente_pagar', _q(pendiente_usd)),
        ('proximo_vencimiento', proxima and {'compra': proxima.id, 'vence': proxima.vence,
                                             'proveedor': proxima.proveedor, 'total': proxima.total_factura}),
        ('margen_objetivo', ctx.objetivo), ('tasa_bcv', ctx.bcv), ('tasa_usdt', ctx.usdt),
    ])


def articulos(ctx):
    """Por artículo: costo del último lote, margen estimado, margen real de lo vendido y precio sugerido."""
    resultado = []
    desde = timezone.now() - timedelta(days=30)
    for producto in Producto.objects.filter(activo=True).order_by('nombre'):
        lotes_p = list(LoteCompra.objects.filter(producto=producto, compra__anulada=False)
                       .select_related('compra').order_by('compra__fecha', 'compra_id', 'id'))
        if not lotes_p:
            resultado.append(OrderedDict([('producto', producto.id), ('nombre', producto.nombre),
                                          ('precio', producto.precio), ('stock', producto.stock),
                                          ('sin_compras', True)]))
            continue
        ultimo = Lote(lotes_p[-1], ctx)
        vendido = ganancia = entro_bs = CERO
        vendidas = 0
        for l in lotes_p:
            calc = Lote(l, ctx)
            for a in _asignaciones_de_venta(l.asignaciones.all()):
                v = calc.venta(a)
                vendido += v['vendido']
                ganancia += v['ganancia'] or CERO
                vendidas += v['cantidad']
                if a.linea_venta.venta.fecha >= desde:
                    entro_bs += v['bs_entraron']
        precio = producto.precio
        estimado = (precio - ultimo.costo_usd) / precio * CIEN if precio and ultimo.costo_usd is not None else None
        # Precio sugerido: el costo de reponerlo hoy en Bs, vendido a la tasa media reciente
        reposicion_bs = (lotes_p[-1].costo_unitario * ctx.usdt
                         if lotes_p[-1].compra.forma_pago != Compra.FormaPago.BS_FIJOS else ultimo.costo_bs)
        tasa_venta = (entro_bs / vendido) if (vendido and entro_bs) else ctx.bcv
        sugerido = None
        if reposicion_bs and tasa_venta and ctx.objetivo < CIEN:
            sugerido = reposicion_bs / (tasa_venta * (1 - ctx.objetivo / CIEN))
        resultado.append(OrderedDict([
            ('producto', producto.id), ('nombre', producto.nombre), ('precio', precio), ('stock', producto.stock),
            ('sin_compras', False), ('costo_ultimo', _q(ultimo.costo_usd)),
            ('margen_estimado', _pct(estimado)),
            ('margen_real', _pct(ganancia / vendido * CIEN) if vendido else None),
            ('vendidas', vendidas), ('precio_sugerido', _q(sugerido)),
        ]))
    return resultado
