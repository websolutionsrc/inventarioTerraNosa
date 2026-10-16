"""Formatos de importes y fechas para mostrar (estilo Venezuela: 1.234,50)."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

DIAS = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
         'septiembre', 'octubre', 'noviembre', 'diciembre']


def decimal(valor):
    try:
        return Decimal(str(valor if valor is not None else '0'))
    except InvalidOperation:
        return Decimal('0')


def numero(valor, decimales=2):
    texto = '{:,.{}f}'.format(decimal(valor), decimales)
    return texto.replace(',', '_').replace('.', ',').replace('_', '.')


def dinero(valor):
    return '$ ' + numero(valor)


def fecha_hora(texto):
    """Fecha ISO del servidor (ya en hora de Venezuela) a datetime."""
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto.replace('Z', '+00:00'))
    except ValueError:
        return None


def hora(texto):
    f = fecha_hora(texto)
    return f.strftime('%I:%M %p').lstrip('0').replace('AM', 'a. m.').replace('PM', 'p. m.') if f else ''


def fecha_corta(texto):
    f = fecha_hora(texto)
    return f.strftime('%d/%m/%Y') if f else ''


def fecha_y_hora(texto, corta=False):
    f = fecha_hora(texto)
    return '{} {}'.format(f.strftime('%d/%m/%y' if corta else '%d/%m/%Y'), hora(texto)) if f else ''


def hoy(api):
    """Fecha de hoy según el servidor (hora de Venezuela), o la del PC si no se sabe."""
    try:
        return date.fromisoformat((api.opciones or {}).get('hoy'))
    except (TypeError, ValueError):
        return date.today()


def fecha_larga(d):
    """date o datetime → 'viernes, 16 de octubre de 2026'."""
    return '{}, {} de {} de {}'.format(DIAS[d.weekday()], d.day, MESES[d.month - 1], d.year)


def resumen_lineas(lineas, maximo=3):
    partes = ['{}× {}'.format(l['cantidad'], l['producto_nombre']) for l in lineas[:maximo]]
    if len(lineas) > maximo:
        partes.append('y {} más'.format(len(lineas) - maximo))
    return ', '.join(partes)
