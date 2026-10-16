"""Indicador de las tasas de referencia Bs/USD (BCV oficial y USDT en Binance P2P)."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from .. import formato, tema


def tasa_bcv(tasas):
    """Tasa oficial del BCV como Decimal, o None si no se conoce."""
    try:
        valor = tasas['bcv']['venta']
    except (TypeError, KeyError):
        return None
    return formato.decimal(valor) if valor else None


class IndicadorTasas(QWidget):
    """Etiquetas «BCV 880,12 Bs/$» y «USDT 995,95 / 994,15». Se actualiza con poner()."""

    def __init__(self, parent=None):
        super(IndicadorTasas, self).__init__(parent)
        capa = QHBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(6)
        self.bcv = QLabel('BCV …')
        self.usdt = QLabel('USDT …')
        for l in (self.bcv, self.usdt):
            l.setProperty('rol', 'chip')
            l.setTextFormat(Qt.RichText)
            l.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            capa.addWidget(l, 0, Qt.AlignVCenter)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.usdt.setStyleSheet('background: #FDF3D1; color: {};'.format(tema.TEXTO))
        self.poner(None)

    def poner(self, tasas):
        bcv = (tasas or {}).get('bcv') or {}
        usdt = (tasas or {}).get('binance') or {}
        if bcv.get('venta'):
            self.bcv.setText('<b>BCV</b> {} Bs/$'.format(formato.numero(bcv['venta'])))
            self.bcv.setToolTip('Tasa oficial del Banco Central de Venezuela\nFecha valor: {}\n'
                                'Fuente: bcv.org.ve{}'.format(_fecha(bcv['fecha_valor']), _aviso(bcv)))
        else:
            self.bcv.setText('<b>BCV</b> sin datos')
            self.bcv.setToolTip('No se pudo obtener la tasa del BCV.')
        if usdt.get('venta'):
            self.usdt.setText('<b>USDT</b> {} / {}'.format(formato.numero(usdt['compra']),
                                                            formato.numero(usdt['venta'])))
            self.usdt.setToolTip('Binance P2P: Bs por USDT al comprar / al vender\n'
                                 'Mediana de los primeros anuncios. Referencia de mercado, NO oficial\n'
                                 'Actualizada: {}{}'.format(formato.fecha_y_hora(usdt['obtenida_en']), _aviso(usdt)))
        else:
            self.usdt.setText('<b>USDT</b> sin datos')
            self.usdt.setToolTip('No se pudo obtener el precio del USDT en Binance P2P.')


def _fecha(iso):
    return '{}/{}/{}'.format(iso[8:10], iso[5:7], iso[:4]) if iso else '—'


def _aviso(dato):
    return '\n(No se pudo actualizar: se muestra la última conocida)' if dato.get('desactualizada') else ''
