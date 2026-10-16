"""
Tasas de cambio de referencia (bolívares por dólar).

- BCV: tasa oficial publicada en www.bcv.org.ve. Su web no envía el certificado intermedio
  de Sectigo, así que se incluye en certificados/ para poder verificar HTTPS igualmente.
- Binance: precio del USDT en Binance P2P (Bs por USDT). Es la mediana de los primeros
  anuncios de compra y de venta, usando la misma búsqueda pública que la web de Binance P2P.
  Es una referencia de mercado, NO oficial.

Cada fuente se consulta como mucho cada VIGENCIA y la última lectura buena se guarda en la
base de datos (TasaCambio). Si una fuente no responde se devuelve la última conocida, marcada
como desactualizada.
"""
import json
import re
import ssl
import statistics
import urllib.request
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.utils import timezone

from .models import TasaCambio

VIGENCIA = timedelta(minutes=30)
TIEMPO_ESPERA = 10  # segundos por consulta
NAVEGADOR = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) TerraNosa/2.0'
CERTIFICADO_SECTIGO = Path(__file__).resolve().parent / 'certificados' / 'sectigo-dv-r36.pem'

URL_BCV = 'https://www.bcv.org.ve/'
URL_BINANCE = 'https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search'
URL_BINANCE_WEB = 'https://p2p.binance.com/es/trade/all-payments/USDT?fiat=VES'
ANUNCIOS_BINANCE = 10


class ErrorTasa(Exception):
    pass


def _numero(texto):
    """'1.234,5678' -> Decimal('1234.5678')"""
    try:
        return Decimal(texto.strip().replace('.', '').replace(',', '.'))
    except (InvalidOperation, AttributeError):
        raise ErrorTasa('Número no válido: {!r}'.format(texto))


def _descargar(url, datos=None):
    """GET (o POST con JSON si hay datos) verificando HTTPS. Devuelve el texto de la respuesta."""
    contexto = ssl.create_default_context()
    if CERTIFICADO_SECTIGO.exists():
        contexto.load_verify_locations(str(CERTIFICADO_SECTIGO))
    cabeceras = {'User-Agent': NAVEGADOR, 'Accept-Language': 'es'}
    cuerpo = None
    if datos is not None:
        cuerpo = json.dumps(datos).encode('utf-8')
        cabeceras['Content-Type'] = 'application/json'
    peticion = urllib.request.Request(url, data=cuerpo, headers=cabeceras)
    try:
        with urllib.request.urlopen(peticion, context=contexto, timeout=TIEMPO_ESPERA) as r:
            return r.read().decode('utf-8', 'replace')
    except Exception as e:  # red, SSL, HTTP...
        raise ErrorTasa('No se pudo leer {}: {}'.format(url, e))


def leer_bcv(html):
    """Devuelve (tasa, fecha_valor) del bloque del dólar de la portada del BCV."""
    m = re.search(r'id="dolar".*?<strong[^>]*>\s*([\d.,]+)\s*</strong>', html, re.S)
    if not m:
        raise ErrorTasa('No se encontró la tasa del dólar en la web del BCV.')
    tasa = _numero(m.group(1))
    f = re.search(r'Fecha Valor:.*?content="(\d{4}-\d{2}-\d{2})', html, re.S)
    fecha = date.fromisoformat(f.group(1)) if f else timezone.localdate()
    return tasa, fecha


def leer_binance(texto_json):
    """Mediana de los precios (Bs por USDT) de una respuesta de la búsqueda de Binance P2P."""
    try:
        datos = json.loads(texto_json)
        precios = [Decimal(a['adv']['price']) for a in datos.get('data') or []]
    except (ValueError, KeyError, TypeError, InvalidOperation):
        raise ErrorTasa('Respuesta inesperada de Binance P2P.')
    if not precios:
        raise ErrorTasa('Binance P2P no devolvió anuncios de USDT/VES.')
    return Decimal(statistics.median(precios))


def _binance(tipo):
    """tipo BUY: anuncios para comprar USDT (lo que cuesta un USDT). SELL: para venderlos."""
    return leer_binance(_descargar(URL_BINANCE, {
        'asset': 'USDT', 'fiat': 'VES', 'tradeType': tipo, 'page': 1, 'rows': ANUNCIOS_BINANCE,
        'payTypes': [], 'publisherType': None,
    }))


def _actualizar(fuente):
    if fuente == TasaCambio.Fuente.BCV:
        tasa, fecha = leer_bcv(_descargar(URL_BCV))
        compra = venta = tasa
    else:
        compra, venta = _binance('BUY'), _binance('SELL')
        fecha = timezone.localdate()
    if not (Decimal('0.01') <= compra <= Decimal('100000000') and Decimal('0.01') <= venta <= Decimal('100000000')):
        raise ErrorTasa('Tasa fuera de rango: {} / {}'.format(compra, venta))
    obj, _ = TasaCambio.objects.update_or_create(
        fuente=fuente, fecha_valor=fecha, defaults={'compra': compra, 'venta': venta})
    return obj


def obtener(fuente, forzar=False):
    """Última tasa de una fuente: la refresca si tiene más de VIGENCIA. Nunca lanza errores de red."""
    ultima = TasaCambio.objects.filter(fuente=fuente).order_by('-obtenida_en').first()
    error = None
    if forzar or ultima is None or timezone.now() - ultima.obtenida_en > VIGENCIA:
        try:
            ultima = _actualizar(fuente)
        except ErrorTasa as e:
            error = str(e)
    return ultima, error


def _cuatro(valor):
    return str(Decimal(valor).quantize(Decimal('0.0001'))) if valor is not None else None


def resumen(forzar=False):
    datos = {}
    for fuente, url, oficial in ((TasaCambio.Fuente.BCV, URL_BCV, True),
                                 (TasaCambio.Fuente.BINANCE, URL_BINANCE_WEB, False)):
        tasa, error = obtener(fuente, forzar)
        datos[fuente] = {
            'nombre': TasaCambio.Fuente(fuente).label,
            'oficial': oficial,
            'fuente_url': url,
            'compra': _cuatro(tasa.compra) if tasa else None,
            'venta': _cuatro(tasa.venta) if tasa else None,
            'fecha_valor': tasa.fecha_valor.isoformat() if tasa else None,
            'obtenida_en': timezone.localtime(tasa.obtenida_en).isoformat() if tasa else None,
            'desactualizada': bool(error),
            'error': error,
        }
    return datos
