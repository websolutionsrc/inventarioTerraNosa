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

from .models import (AsignacionLote, CambioPrecio, Compra, EntradaInventario, LoteCompra, Producto, SalidaInventario, TasaCambio,
                     Venta)


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
    tasa = TasaCambio.objects.filter(fuente=TasaCambio.Fuente.BCV).order_by('-fecha_valor', '-obtenida_en').first()
    return tasa.venta if tasa else None


def ultima_tasa_usdt():
    """Última tasa USDT guardada: lo que cuesta comprar un USDT en Binance P2P."""
    tasa = (TasaCambio.objects.filter(fuente=TasaCambio.Fuente.BINANCE)
            .order_by('-fecha_valor', '-obtenida_en').first())
    return tasa.compra if tasa else None


def anotar_precio(producto, usuario, anterior, nuevo, motivo='', compra=None):
    """Deja constancia de un cambio del precio de venta (o del precio con que se da de alta)."""
    if anterior is not None and Decimal(anterior) == Decimal(nuevo):
        return None
    return CambioPrecio.objects.create(producto=producto, usuario=usuario, precio_anterior=anterior,
                                       precio_nuevo=nuevo, motivo=(motivo or '')[:255], compra=compra)


# --- Lotes (FIFO) ---------------------------------------------------------------------

def _sacar_de_lotes(producto, cantidad, stock_antes, linea=None, movimiento=None):
    """
    Saca 'cantidad' unidades de los lotes del producto, del más antiguo al más nuevo (FIFO).
    Primero salen las unidades que no tienen lote (stock anterior a registrar compras).
    """
    lotes = list(LoteCompra.objects.select_for_update()
                 .filter(producto=producto, disponible__gt=0, compra__anulada=False)
                 .order_by('compra__fecha', 'compra_id', 'id'))
    sin_lote = max(0, stock_antes - sum(l.disponible for l in lotes))
    pendiente = cantidad - min(sin_lote, cantidad)
    for lote in lotes:
        if pendiente <= 0:
            break
        n = min(lote.disponible, pendiente)
        lote.disponible -= n
        lote.save(update_fields=['disponible'])
        AsignacionLote.objects.create(lote=lote, linea_venta=linea, movimiento=movimiento, cantidad=n)
        pendiente -= n


def _devolver_a_lotes(asignaciones):
    for asignacion in list(asignaciones):
        lote = LoteCompra.objects.select_for_update().get(pk=asignacion.lote_id)
        lote.disponible += asignacion.cantidad
        lote.save(update_fields=['disponible'])
        asignacion.delete()


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

    venta = Venta.objects.create(usuario=usuario, metodo_pago=metodo_pago, canal=canal,
                                 tasa_usdt=ultima_tasa_usdt())
    total = Decimal('0.00')
    for pid, cantidad in cantidades.items():
        producto = productos[pid]
        linea = SalidaInventario.objects.create(venta=venta, producto=producto, cantidad=cantidad,
                                                precio_unitario=producto.precio)
        _sacar_de_lotes(producto, cantidad, producto.stock, linea=linea)
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
        _devolver_a_lotes(linea.asignaciones.all())  # las unidades vuelven a su lote

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

    stock_antes = producto.stock
    producto.stock += cantidad
    producto.save(update_fields=['stock', 'actualizado'])
    movimiento = EntradaInventario.objects.create(producto=producto, usuario_admin=usuario, tipo=tipo,
                                                  cantidad=cantidad, stock_resultante=producto.stock,
                                                  motivo=motivo[:255])
    if cantidad < 0:  # las unidades perdidas o dañadas también salen de su lote
        _sacar_de_lotes(producto, -cantidad, stock_antes, movimiento=movimiento)
    return movimiento


@transaction.atomic
def crear_producto(usuario, datos, stock_inicial=0):
    stock_inicial = int(stock_inicial or 0)
    if stock_inicial < 0:
        raise ErrorNegocio("El stock inicial no puede ser negativo.")
    producto = Producto.objects.create(stock=stock_inicial, **datos)
    anotar_precio(producto, usuario, None, producto.precio, 'Alta del artículo')
    if stock_inicial:
        EntradaInventario.objects.create(producto=producto, usuario_admin=usuario,
                                         tipo=EntradaInventario.Tipo.INICIAL, cantidad=stock_inicial,
                                         stock_resultante=stock_inicial, motivo='Alta del producto')
    return producto


# --- Cobros con Binance Pay ---------------------------------------------------------

def _validar_lineas(lineas):
    """Comprueba productos y stock (sin bloquear) y devuelve el total en USD."""
    cantidades = OrderedDict()
    for linea in lineas or []:
        cantidad = int(linea['cantidad'])
        if cantidad <= 0:
            raise ErrorNegocio("Las cantidades deben ser mayores que cero.")
        cantidades[int(linea['producto'])] = cantidades.get(int(linea['producto']), 0) + cantidad
    if not cantidades:
        raise ErrorNegocio("La venta no tiene productos.")
    productos = {p.id: p for p in Producto.objects.filter(id__in=cantidades)}
    total = Decimal('0.00')
    for pid, cantidad in cantidades.items():
        p = productos.get(pid)
        if not p or not p.activo:
            raise ErrorNegocio("Hay un producto que ya no está a la venta.")
        if cantidad > p.stock:
            raise ErrorNegocio(f"Stock insuficiente: «{p.nombre}» (quedan {p.stock}, pides {cantidad}).")
        total += p.precio * cantidad
    return [{'producto': pid, 'cantidad': c} for pid, c in cantidades.items()], total


def crear_cobro_binance(usuario, lineas, canal):
    from django.conf import settings
    from . import binance
    from .models import CobroBinance
    if not binance.configurado():
        raise ErrorNegocio("La verificación de Binance no está configurada en el servidor.")
    lineas, total = _validar_lineas(lineas)
    if total <= 0:
        raise ErrorNegocio("El total debe ser mayor que cero.")
    return CobroBinance.objects.create(
        usuario=usuario, lineas=lineas, canal=canal, monto=total,
        expira=timezone.now() + timedelta(minutes=settings.BINANCE_MINUTOS_COBRO))


def conciliar_binance():
    """
    Busca en Binance los pagos de los cobros pendientes. Cada ingreso de USDT se asigna a un
    solo cobro: al más antiguo cuyo importe encaje (con su margen) y que se creó antes del pago.
    Después caduca los cobros pendientes que pasaron su hora. Devuelve un error de Binance o None.
    """
    from . import binance
    from .models import CobroBinance

    pendientes = list(CobroBinance.objects.filter(estado=CobroBinance.Estado.PENDIENTE).order_by('creado', 'id'))
    if not pendientes:
        return None
    error = None
    try:
        desde = min(c.creado for c in pendientes) - timedelta(minutes=1)
        ingresos = sorted(binance.ingresos_desde(desde), key=lambda i: i['fecha'])
    except binance.ErrorBinance as e:
        ingresos, error = [], str(e)

    usados = set(CobroBinance.objects.filter(transaccion_id__isnull=False).values_list('transaccion_id', flat=True))
    for cobro in pendientes:
        minimo, maximo = binance.margen(cobro.monto)
        for ingreso in ingresos:
            if ingreso['id'] in usados or ingreso['fecha'] < cobro.creado - timedelta(minutes=1):
                continue
            if minimo <= ingreso['monto'] <= maximo:
                if _confirmar_cobro(cobro.pk, ingreso):
                    usados.add(ingreso['id'])
                break

    CobroBinance.objects.filter(estado=CobroBinance.Estado.PENDIENTE, expira__lt=timezone.now()).update(
        estado=CobroBinance.Estado.EXPIRADO)
    return error


@transaction.atomic
def _confirmar_cobro(cobro_id, ingreso):
    from .models import CobroBinance
    cobro = CobroBinance.objects.select_for_update().get(pk=cobro_id)
    if cobro.estado != CobroBinance.Estado.PENDIENTE:
        return False
    cobro.transaccion_id = ingreso['id']
    cobro.monto_recibido = ingreso['monto']
    cobro.pagador = (ingreso.get('pagador') or '')[:150]
    cobro.pagado_en = ingreso['fecha']
    try:
        with transaction.atomic():
            cobro.venta = registrar_venta(cobro.usuario, cobro.lineas, Venta.MetodoPago.BINANCE, cobro.canal)
        cobro.estado = CobroBinance.Estado.CONFIRMADO
    except ErrorNegocio as e:
        # El dinero llegó pero no se pudo vender (p. ej. sin stock): queda a la vista del admin
        cobro.estado = CobroBinance.Estado.SIN_VENTA
        cobro.error = str(e)[:255]
    cobro.save()
    return True


@transaction.atomic
def cancelar_cobro_binance(cobro_id):
    from .models import CobroBinance
    cobro = CobroBinance.objects.select_for_update().get(pk=cobro_id)
    if cobro.estado == CobroBinance.Estado.PENDIENTE:
        cobro.estado = CobroBinance.Estado.CANCELADO
        cobro.save(update_fields=['estado'])
    return cobro


# --- Compras a proveedores --------------------------------------------------------------

def sumar_meses(fecha, meses):
    import calendar
    anio, mes = divmod(fecha.month - 1 + meses, 12)
    anio, mes = fecha.year + anio, mes + 1
    return fecha.replace(year=anio, month=mes, day=min(fecha.day, calendar.monthrange(anio, mes)[1]))


@transaction.atomic
def registrar_compra(usuario, lineas, forma_pago, plazo_meses=0, fecha=None, proveedor='', notas='', pago=None):
    """
    lineas: [{"producto" (id) o "nuevo_nombre", "cantidad", "costo_unitario", "precio_venta"?,
              "precio_previsto"?, "margen_previsto"?}].
    Los artículos nuevos se crean en el inventario. Suma el stock, crea un lote por artículo y pone
    el precio de venta indicado. Al contado se registra el pago en el acto (pago: datos opcionales
    de registrar_pago_compra).
    """
    if not lineas:
        raise ErrorNegocio("La compra no tiene artículos.")
    fecha = fecha or timezone.localdate()
    plazo_meses = int(plazo_meses or 0)
    if plazo_meses < 0:
        raise ErrorNegocio("El plazo no puede ser negativo.")

    ids = [int(l['producto']) for l in lineas if l.get('producto')]
    nuevos = [(l.get('nuevo_nombre') or '').strip() for l in lineas if not l.get('producto')]
    if len(set(ids)) != len(ids) or len({n.lower() for n in nuevos}) != len(nuevos):
        raise ErrorNegocio("Hay artículos repetidos en la compra: junta las cantidades en una sola línea.")
    for nombre in nuevos:
        if not nombre:
            raise ErrorNegocio("Falta el nombre de un artículo nuevo.")
        if Producto.objects.filter(nombre__iexact=nombre).exists():
            raise ErrorNegocio("Ya existe un artículo llamado «{}»: elígelo de la lista.".format(nombre))
    productos = {p.id: p for p in Producto.objects.select_for_update().filter(id__in=ids).order_by('id')}
    total = Decimal('0.00')
    for l in lineas:
        if l.get('producto') and int(l['producto']) not in productos:
            raise ErrorNegocio("Producto no encontrado: {}.".format(l['producto']))
        if int(l['cantidad']) <= 0 or Decimal(l['costo_unitario']) <= 0:
            raise ErrorNegocio("Cantidades y costos deben ser mayores que cero.")
        precio = l.get('precio_venta')
        if precio is not None and Decimal(precio) <= 0:
            raise ErrorNegocio("El precio de venta debe ser mayor que cero.")
        if not l.get('producto') and precio is None:
            raise ErrorNegocio("Pon el precio de venta de «{}».".format(l.get('nuevo_nombre')))
        total += Decimal(l['costo_unitario']) * int(l['cantidad'])

    compra = Compra.objects.create(
        usuario=usuario, proveedor=(proveedor or '').strip()[:150], fecha=fecha, plazo_meses=plazo_meses,
        vence=sumar_meses(fecha, plazo_meses), forma_pago=forma_pago, total_factura=total,
        notas=(notas or '')[:255])
    motivo = 'Compra #{}'.format(compra.id) + (' · {}'.format(compra.proveedor) if compra.proveedor else '')

    for l in lineas:
        if l.get('producto'):
            producto = productos[int(l['producto'])]
        else:
            producto = Producto.objects.create(nombre=l['nuevo_nombre'].strip()[:255], proveedor=compra.proveedor,
                                               precio=Decimal(l['precio_venta']), stock=0)
            anotar_precio(producto, usuario, None, producto.precio, 'Alta en la compra #{}'.format(compra.id),
                          compra)
        cantidad = int(l['cantidad'])
        LoteCompra.objects.create(compra=compra, producto=producto, cantidad=cantidad, disponible=cantidad,
                                  costo_unitario=Decimal(l['costo_unitario']),
                                  precio_previsto=l.get('precio_previsto'),
                                  margen_previsto=l.get('margen_previsto'))
        producto.stock += cantidad
        campos = ['stock', 'actualizado']
        if l.get('precio_venta') is not None and Decimal(l['precio_venta']) != producto.precio:
            anotar_precio(producto, usuario, producto.precio, Decimal(l['precio_venta']),
                          'Compra #{}'.format(compra.id), compra)
            producto.precio = Decimal(l['precio_venta'])
            campos.append('precio')
        if not producto.activo:  # comprar un artículo desactivado lo vuelve a poner a la venta
            producto.activo = True
            campos.append('activo')
        producto.save(update_fields=campos)
        EntradaInventario.objects.create(producto=producto, usuario_admin=usuario,
                                         tipo=EntradaInventario.Tipo.ENTRADA, cantidad=cantidad,
                                         stock_resultante=producto.stock, compra=compra, motivo=motivo)
    if plazo_meses == 0:
        registrar_pago_compra(compra.id, **(pago or {}))
        compra.refresh_from_db()
    return compra


@transaction.atomic
def registrar_pago_compra(compra_id, fecha=None, tasa_pago=None, bs_pagados=None, usd_pagados=None,
                          tasa_usdt=None):
    """
    Registra el pago (único) de una compra. Si no se indican, la tasa de pago (Z1) es la USDT o
    la BCV guardada más reciente según la forma de pago, y los Bs pagados = total × tasa.
    """
    compra = Compra.objects.select_for_update().get(pk=compra_id)
    if compra.anulada:
        raise ErrorNegocio("La compra está anulada.")
    if compra.pagada:
        raise ErrorNegocio("Esta compra ya está pagada.")
    forma = compra.forma_pago
    tasa_usdt = Decimal(tasa_usdt) if tasa_usdt else ultima_tasa_usdt()

    if forma == Compra.FormaPago.DOLARES:
        usd_pagados = Decimal(usd_pagados) if usd_pagados is not None else compra.total_factura
        tasa_pago = None
        bs_pagados = None
    elif forma == Compra.FormaPago.BS_FIJOS:
        bs_pagados = Decimal(bs_pagados) if bs_pagados is not None else compra.total_factura
        tasa_pago = None
        usd_pagados = None
    else:
        if tasa_pago is None:
            tasa_pago = ultima_tasa_usdt() if forma == Compra.FormaPago.BS_USDT else ultima_tasa_bcv()
        if not tasa_pago:
            raise ErrorNegocio("No hay tasa del día guardada: indica la tasa a la que se pagó.")
        tasa_pago = Decimal(tasa_pago)
        if tasa_pago <= 0:
            raise ErrorNegocio("La tasa de pago debe ser mayor que cero.")
        bs_pagados = Decimal(bs_pagados) if bs_pagados is not None else compra.total_factura * tasa_pago
        usd_pagados = None
    if (bs_pagados is not None and bs_pagados <= 0) or (usd_pagados is not None and usd_pagados <= 0):
        raise ErrorNegocio("El importe pagado debe ser mayor que cero.")

    compra.pagada = True
    compra.pagada_el = fecha or timezone.localdate()
    compra.tasa_pago = tasa_pago
    compra.bs_pagados = bs_pagados.quantize(Decimal('0.01')) if bs_pagados is not None else None
    compra.usd_pagados = usd_pagados
    compra.tasa_usdt_pago = tasa_usdt
    compra.save()
    return compra


@transaction.atomic
def anular_compra(compra_id, usuario):
    """Solo si no ha salido ninguna unidad de sus lotes: quita el stock y deja la compra anulada."""
    compra = Compra.objects.select_for_update().get(pk=compra_id)
    if compra.anulada:
        raise ErrorNegocio("La compra ya estaba anulada.")
    lotes = list(compra.lotes.select_for_update())
    if any(l.disponible != l.cantidad for l in lotes):
        raise ErrorNegocio("No se puede anular: ya se vendieron o ajustaron unidades de esta compra.")
    for lote in lotes:
        producto = Producto.objects.select_for_update().get(pk=lote.producto_id)
        if producto.stock < lote.cantidad:
            raise ErrorNegocio("No se puede anular: «{}» tiene menos stock que lo comprado.".format(producto.nombre))
        producto.stock -= lote.cantidad
        producto.save(update_fields=['stock', 'actualizado'])
        EntradaInventario.objects.create(producto=producto, usuario_admin=usuario,
                                         tipo=EntradaInventario.Tipo.AJUSTE, cantidad=-lote.cantidad,
                                         stock_resultante=producto.stock, compra=compra,
                                         motivo='Compra #{} anulada'.format(compra.id))
        lote.disponible = 0
        lote.save(update_fields=['disponible'])
    compra.anulada = True
    compra.save(update_fields=['anulada'])
    return compra


def _ritmo_mensual(fuente, campo):
    """Subida media mensual (%) según el historial guardado, o None si hay menos de 25 días."""
    filas = list(TasaCambio.objects.filter(fuente=fuente).order_by('fecha_valor'))
    if len(filas) < 2:
        return None
    primera, ultima = filas[0], filas[-1]
    dias = (ultima.fecha_valor - primera.fecha_valor).days
    if dias < 25 or not getattr(primera, campo):
        return None
    factor = float(getattr(ultima, campo) / getattr(primera, campo)) ** (30.0 / dias)
    return Decimal(str(round((factor - 1) * 100, 2)))


def previsiones_compra():
    """Datos para estimar ganancia y precio al comprar: tasas de hoy, su ritmo y cómo se cobra."""
    from django.db.models import Sum
    desde = timezone.now() - timedelta(days=30)
    ventas = Venta.objects.filter(anulada=False, fecha__gte=desde)
    total = ventas.aggregate(t=Sum('total'))['t'] or Decimal('0')
    en_dolares = (ventas.exclude(metodo_pago__in=Venta.METODOS_EN_BOLIVARES).aggregate(t=Sum('total'))['t']
                  or Decimal('0'))
    return {
        'bcv': ultima_tasa_bcv(),
        'usdt': ultima_tasa_usdt(),
        'ritmo_bcv': _ritmo_mensual(TasaCambio.Fuente.BCV, 'venta'),
        'ritmo_usdt': _ritmo_mensual(TasaCambio.Fuente.BINANCE, 'compra'),
        'porcentaje_dolares': ((en_dolares / total) * 100).quantize(Decimal('0.1')) if total else None,
        'ventas_analizadas': ventas.count(),
    }
