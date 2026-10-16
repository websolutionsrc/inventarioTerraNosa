"""
Lectura de los pagos recibidos por Binance Pay (cuenta de la tienda).

Usa GET /sapi/v1/pay/transactions, firmada con HMAC-SHA256. La clave de API solo necesita
permiso de LECTURA. Es una consulta "pesada" para Binance (peso 3000), así que el
resultado se guarda unos segundos y sirve para todos los cobros pendientes a la vez.

Con BINANCE_SIMULADO (solo en local) los pagos salen de la tabla IngresoBinanceSimulado,
que se rellena con "manage.py simular_pago_binance <monto>".
"""
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone as tz
from decimal import Decimal, InvalidOperation

from django.conf import settings

URL = 'https://api.binance.com/sapi/v1/pay/transactions'
CACHE_SEGUNDOS = 5
_cache = {'momento': 0.0, 'desde': None, 'ingresos': []}


class ErrorBinance(Exception):
    pass


def simulado():
    return bool(settings.BINANCE_SIMULADO and settings.DEBUG)


def configurado():
    return simulado() or bool(settings.BINANCE_API_KEY and settings.BINANCE_API_SECRET)


def _firmado(params):
    consulta = urllib.parse.urlencode(params)
    firma = hmac.new(settings.BINANCE_API_SECRET.encode(), consulta.encode(), hashlib.sha256).hexdigest()
    return '{}?{}&signature={}'.format(URL, consulta, firma)


def _monto(registro):
    """Importe en USDT de un registro (positivo = ingreso). Mira también fundsDetail."""
    try:
        if (registro.get('currency') or '').upper() == 'USDT':
            return Decimal(str(registro['amount']))
        for detalle in registro.get('fundsDetail') or []:
            if (detalle.get('currency') or '').upper() == 'USDT':
                monto = Decimal(str(detalle['amount']))
                # fundsDetail viene sin signo: el signo lo da "amount"
                return monto if Decimal(str(registro.get('amount', '1'))) >= 0 else -monto
    except (KeyError, InvalidOperation, TypeError):
        pass
    return None


def interpretar(respuesta):
    """Convierte la respuesta de Binance en ingresos de USDT: [{id, monto, fecha, pagador}]."""
    if str(respuesta.get('code')) != '000000':
        raise ErrorBinance('Binance respondió con error: {} {}'.format(respuesta.get('code'), respuesta.get('message')))
    ingresos = []
    for r in respuesta.get('data') or []:
        monto = _monto(r)
        if monto is None or monto <= 0:
            continue  # pagos que hizo la tienda, otras monedas…
        pagador = r.get('payerInfo') or {}
        ingresos.append({
            'id': str(r.get('transactionId') or r.get('orderId')),
            'monto': monto,
            'fecha': datetime.fromtimestamp(int(r['transactionTime']) / 1000, tz=tz.utc),
            'pagador': pagador.get('name') or pagador.get('binanceId') or '',
            'tipo': r.get('orderType', ''),
        })
    return ingresos


def _consultar_api(desde):
    params = {'startTime': int(desde.timestamp() * 1000), 'limit': 100, 'recvWindow': 10000,
              'timestamp': int(time.time() * 1000)}
    peticion = urllib.request.Request(_firmado(params), headers={'X-MBX-APIKEY': settings.BINANCE_API_KEY})
    try:
        with urllib.request.urlopen(peticion, timeout=15) as r:
            return interpretar(json.loads(r.read().decode('utf-8')))
    except urllib.error.HTTPError as e:
        try:
            detalle = json.loads(e.read().decode('utf-8'))
        except ValueError:
            detalle = {}
        raise ErrorBinance('Binance rechazó la consulta ({}): {}'.format(e.code, detalle.get('msg', e.reason)))
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ErrorBinance('No se pudo consultar Binance: {}'.format(e))


def _consultar_simulado(desde):
    from .models import IngresoBinanceSimulado
    return [{'id': i.transaccion_id, 'monto': i.monto, 'fecha': i.fecha, 'pagador': i.pagador, 'tipo': 'PAY'}
            for i in IngresoBinanceSimulado.objects.filter(fecha__gte=desde)]


def ingresos_desde(desde):
    """Ingresos de USDT desde una fecha. Reutiliza la última consulta si tiene menos de CACHE_SEGUNDOS."""
    if not configurado():
        raise ErrorBinance('La verificación de Binance no está configurada en el servidor.')
    if simulado():
        return _consultar_simulado(desde)
    ahora = time.monotonic()
    if (ahora - _cache['momento'] < CACHE_SEGUNDOS and _cache['desde'] is not None and _cache['desde'] <= desde):
        return [i for i in _cache['ingresos'] if i['fecha'] >= desde]
    ingresos = _consultar_api(desde)
    _cache.update(momento=ahora, desde=desde, ingresos=ingresos)
    return ingresos


def margen(monto):
    """(mínimo, máximo) de USDT que se aceptan para un cobro de 'monto'."""
    abajo = max(Decimal(settings.BINANCE_TOLERANCIA_USDT), monto * Decimal(settings.BINANCE_TOLERANCIA_PCT) / 100)
    arriba = monto * Decimal(settings.BINANCE_EXCESO_PCT) / 100
    return monto - abajo, monto + arriba
