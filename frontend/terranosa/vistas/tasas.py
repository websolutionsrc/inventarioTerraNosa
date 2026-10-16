"""Indicador de las tasas de referencia Bs/USD (BCV oficial y Banco de Venezuela)."""
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


def en_bolivares(monto_usd, tasas):
    """'≈ Bs 75.689,96 a tasa BCV' o '' si no hay tasa."""
    tasa = tasa_bcv(tasas)
    if not tasa:
        return ''
    return '≈ {} a tasa BCV'.format(formato.bolivares(formato.decimal(monto_usd) * tasa))


class IndicadorTasas(QWidget):
    """Dos etiquetas: «BCV 880,12 Bs/$» y «BDV 865,18 / 890,68». Se actualiza con poner()."""

    def __init__(self, parent=None):
        super(IndicadorTasas, self).__init__(parent)
        capa = QHBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(6)
        self.bcv = QLabel('BCV …')
        self.bdv = QLabel('BDV …')
        for l in (self.bcv, self.bdv):
            l.setProperty('rol', 'chip')
            l.setTextFormat(Qt.RichText)
            l.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            capa.addWidget(l, 0, Qt.AlignVCenter)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.bdv.setStyleSheet('background: #EEF1F4; color: {};'.format(tema.TEXTO))
        self.poner(None)

    def poner(self, tasas):
        bcv = (tasas or {}).get('bcv') or {}
        bdv = (tasas or {}).get('bdv') or {}
        if bcv.get('venta'):
            self.bcv.setText('<b>BCV</b> {} Bs/$'.format(formato.numero(bcv['venta'])))
            self.bcv.setToolTip('Tasa oficial del Banco Central de Venezuela\nFecha valor: {}\n'
                                'Fuente: bcv.org.ve{}'.format(_fecha(bcv['fecha_valor']), _aviso(bcv)))
        else:
            self.bcv.setText('<b>BCV</b> sin datos')
            self.bcv.setToolTip('No se pudo obtener la tasa del BCV.')
        if bdv.get('venta'):
            self.bdv.setText('<b>BDV</b> {} / {}'.format(formato.numero(bdv['compra']), formato.numero(bdv['venta'])))
            self.bdv.setToolTip('Banco de Venezuela: compra / venta\nReferencia NO oficial (dolarhoy.net)\n'
                                'Actualizada: {}{}'.format(formato.fecha_y_hora(bdv['obtenida_en']), _aviso(bdv)))
        else:
            self.bdv.setText('<b>BDV</b> sin datos')
            self.bdv.setToolTip('No se pudo obtener la tasa del Banco de Venezuela.')


def _fecha(iso):
    return '{}/{}/{}'.format(iso[8:10], iso[5:7], iso[:4]) if iso else '—'


def _aviso(dato):
    return '\n(No se pudo actualizar: se muestra la última conocida)' if dato.get('desactualizada') else ''
