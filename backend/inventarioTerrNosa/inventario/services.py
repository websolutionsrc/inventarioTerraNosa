"""
Operaciones que cambian el stock. Cada una va en una transacción: o se hace entera
o no se hace nada, y el stock se bloquea mientras tanto para que dos ventas a la
vez no vendan la misma unidad.
"""
from collections import OrderedDict
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import EntradaInventario, Producto, SalidaInventario, TasaCambio, Venta


class ErrorNegocio(Exception):
    """Error que se le puede mostrar tal cual al usuario."""


def rango_del_dia(dia=None):
    """Inicio y fin (fechas con zona horaria) de un día en la hora de la tienda."""
    dia = dia or timezone.localdate()
    inicio = timezone.make_aware(datetime.combine(dia, time.min))
    return inicio, inicio + timedelta(days=1)


def es_de_hoy(venta):
    inicio, fin = rango_del_dia()
    return inicio <= venta.fecha < fin


def ultima_tasa_bcv():
    """Última tasa del BCV guardada (sin consultar la web: no debe frenar una venta)."""
    tasa = TasaCambio.objects.filter(fuente=TasaCambio.Fuente.BCV).order_by('-obtenida_en').first()
    return tasa.venta if tasa else None


@transaction.atomic
def registrar_venta(usuario, lineas, metodo_pago, canal, tasa=None):
    """
    lineas: lista de {"producto": id, "cantidad": n}. El precio lo pone el servidor.
    Si un producto aparece varias veces se suman las cantidades.
    tasa: Bs por dólar a la que se cobra, solo en métodos en bolívares. Si no viene, se usa la
    del BCV. Se guarda en la venta junto a la del BCV para saber a cuánto se vendió.
    """
    if not lineas:
        raise ErrorNegocio("La venta no tiene productos.")

    en_bolivares = Venta.moneda_de(metodo_pago) == 'VES'
    tasa_bcv = ultima_tasa_bcv() if en_bolivares else None
    if en_bolivares:
        tasa = Decimal(tasa) if tasa is not None else tasa_bcv
        if tasa is None:
            raise ErrorNegocio("No hay tasa de cambio para cobrar en bolívares. Indica la tasa.")
        if tasa <= 0:
            raise ErrorNegocio("La tasa de cambio debe ser mayor que cero.")
    else:
        tasa = None

    cantidades = OrderedDict()
    for linea in lineas:
        cantidad = int(linea['cantidad'])
        if cantidad <= 0:
            raise ErrorNegocio("Las cantidades deben ser mayores que cero.")
        cantidades[linea['producto']] = cantidades.get(linea['producto'], 0) + cantidad

    # Se bloquean en orden de id para que dos ventas simultáneas no se esperen en cruz
    productos = {p.id: p for p in Producto.objects.select_for_update().filter(id__in=cantidades).order_by('id')}

    faltan = [str(pid) for pid in cantidades if pid not in productos]
    if faltan:
        raise ErrorNegocio(f"Producto no encontrado: {', '.join(faltan)}.")

    sin_stock = []
    for pid, cantidad in cantidades.items():
        producto = productos[pid]
        if not producto.activo:
            raise ErrorNegocio(f"«{producto.nombre}» ya no está a la venta.")
        if cantidad > producto.stock:
            sin_stock.append(f"«{producto.nombre}» (quedan {producto.stock}, pides {cantidad})")
    if sin_stock:
        raise ErrorNegocio("Stock insuficiente: " + "; ".join(sin_stock) + ".")

    venta = Venta.objects.create(usuario=usuario, metodo_pago=metodo_pago, canal=canal)
    total = Decimal('0.00')
    for pid, cantidad in cantidades.items():
        producto = productos[pid]
        SalidaInventario.objects.create(venta=venta, producto=producto, cantidad=cantidad,
                                        precio_unitario=producto.precio)
        producto.stock -= cantidad
        producto.save(update_fields=['stock', 'actualizado'])
        total += producto.precio * cantidad

    venta.total = total
    campos = ['total']
    if en_bolivares:
        venta.tasa_cambio = tasa
        venta.tasa_bcv = tasa_bcv
        venta.total_bs = (total * tasa).quantize(Decimal('0.01'))
        campos += ['tasa_cambio', 'tasa_bcv', 'total_bs']
    venta.save(update_fields=campos)
    return venta


@transaction.atomic
def anular_venta(venta_id, usuario, motivo):
    """
    Marca la venta como anulada y devuelve el stock de todas sus líneas.
    El encargado solo puede anular ventas de hoy; el admin, cualquiera.
    """
    motivo = (motivo or '').strip()
    if not motivo:
        raise ErrorNegocio("Indica el motivo de la anulación.")

    venta = Venta.objects.select_for_update().get(pk=venta_id)
    if venta.anulada:
        raise ErrorNegocio("Esta venta ya estaba anulada.")
    if not usuario.is_staff and not es_de_hoy(venta):
        raise ErrorNegocio("Solo se pueden anular ventas de hoy. Para otras, habla con el administrador.")

    lineas = list(venta.lineas.all())
    productos = {p.id: p for p in Producto.objects.select_for_update()
                 .filter(id__in=[l.producto_id for l in lineas]).order_by('id')}
    for linea in lineas:
        producto = productos[linea.producto_id]
        producto.stock += linea.cantidad
        producto.save(update_fields=['stock', 'actualizado'])

    venta.anulada = True
    venta.anulada_por = usuario
    venta.anulada_en = timezone.now()
    venta.motivo_anulacion = motivo[:255]
    venta.save(update_fields=['anulada', 'anulada_por', 'anulada_en', 'motivo_anulacion'])
    return venta


@transaction.atomic
def mover_stock(producto_id, usuario, tipo, cantidad, motivo=''):
    """Entrada de mercancía (suma) o ajuste (suma o resta, con motivo)."""
    cantidad = int(cantidad)
    motivo = (motivo or '').strip()
    if tipo == EntradaInventario.Tipo.ENTRADA and cantidad <= 0:
        raise ErrorNegocio("Una entrada de mercancía debe sumar al menos una unidad.")
    if tipo == EntradaInventario.Tipo.AJUSTE:
        if cantidad == 0:
            raise ErrorNegocio("El ajuste no cambia nada.")
        if not motivo:
            raise ErrorNegocio("Indica el motivo del ajuste.")

    producto = Producto.objects.select_for_update().get(pk=producto_id)
    if producto.stock + cantidad < 0:
        raise ErrorNegocio(f"El stock no puede quedar negativo (hay {producto.stock}).")

    producto.stock += cantidad
    producto.save(update_fields=['stock', 'actualizado'])
    return EntradaInventario.objects.create(producto=producto, usuario_admin=usuario, tipo=tipo,
                                            cantidad=cantidad, stock_resultante=producto.stock,
                                            motivo=motivo[:255])


@transaction.atomic
def crear_producto(usuario, datos, stock_inicial=0):
    stock_inicial = int(stock_inicial or 0)
    if stock_inicial < 0:
        raise ErrorNegocio("El stock inicial no puede ser negativo.")
    producto = Producto.objects.create(stock=stock_inicial, **datos)
    if stock_inicial:
        EntradaInventario.objects.create(producto=producto, usuario_admin=usuario,
                                         tipo=EntradaInventario.Tipo.INICIAL, cantidad=stock_inicial,
                                         stock_resultante=stock_inicial, motivo='Alta del producto')
    return producto
