"""
Compras a proveedores (admin): registrar compras con su forma de pago (contado o a pagar en
N meses), estimar ganancia y precio con la brecha cambiaria, registrar el pago y ver los lotes.
"""
import calendar
from datetime import date

from PyQt5.QtCore import QDate, QSize, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QAbstractItemView, QButtonGroup, QComboBox, QCompleter, QDateEdit, QDialog,
                             QDoubleSpinBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QRadioButton,
                             QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from .. import estimacion, formato, tema
from ..tareas import ejecutar
from ..widgets import Columna, Tabla, Tarjeta, TarjetaCifra, boton, confirmar, etiqueta, mostrar_error
from .base import Pagina
from .dialogos import Dialogo

FORMAS_PAGO = [
    ('bs_usdt', 'En Bs a tasa USDT del día de pago'),
    ('bs_bcv', 'En Bs a tasa BCV del día de pago'),
    ('dolares', 'En dólares o USDT'),
    ('bs_fijos', 'Monto fijo en Bs'),
]
NOMBRE_FORMA = dict(FORMAS_PAGO)


def texto_plazo(meses):
    meses = int(meses or 0)
    return 'Contado' if not meses else 'A pagar en {} mes{}'.format(meses, '' if meses == 1 else 'es')


def sumar_meses(d, meses):
    anio, mes = divmod(d.month - 1 + meses, 12)
    anio, mes = d.year + anio, mes + 1
    return d.replace(year=anio, month=mes, day=min(d.day, calendar.monthrange(anio, mes)[1]))


def importe_factura(valor, forma):
    return formato.bolivares(valor) if forma == 'bs_fijos' else formato.dinero(valor)


def texto_estado(compra):
    estado = compra['estado']
    if estado == 'anulada':
        return 'Anulada'
    if estado == 'pagada':
        return 'Pagada'
    dias = compra['dias_para_vencer']
    if dias < 0:
        return 'Vencida hace {} día{}'.format(-dias, '' if dias == -1 else 's')
    if dias == 0:
        return 'Vence hoy'
    return 'Vence en {} día{}'.format(dias, '' if dias == 1 else 's')


def color_estado(compra):
    if compra['estado'] == 'pagada':
        return tema.VERDE
    if compra['estado'] == 'anulada':
        return tema.TEXTO_SUAVE
    return tema.ROJO if compra['dias_para_vencer'] <= 7 else tema.AMBAR


def _decimal_spin(maximo=99999999, decimales=2, sufijo='', minimo=0):
    s = QDoubleSpinBox()
    s.setRange(minimo, maximo)
    s.setDecimals(decimales)
    s.setGroupSeparatorShown(True)
    if sufijo:
        s.setSuffix(sufijo)
    return s


def _pct(valor):
    return '—' if valor is None else '{} %'.format(formato.numero(valor, 1))


def _color_margen(valor, objetivo):
    if valor is None:
        return tema.TEXTO_SUAVE
    if valor >= objetivo:
        return tema.VERDE
    if valor >= objetivo - 10:
        return tema.AMBAR
    return tema.ROJO


# --- Nueva compra ----------------------------------------------------------------------

def _redondear_precio(valor):
    """Precio sugerido redondeado hacia arriba a 0,50 $ (precios de tienda)."""
    medio = formato.decimal('0.5')
    valor = formato.decimal(valor)
    return (valor / medio).to_integral_value(rounding='ROUND_CEILING') * medio


def _ajustar_columnas(tabla, estirar=0, fijas=None):
    """
    Columnas al ancho de su contenido y de su título (sin recortes); 'estirar' ocupa el resto.
    Con estirar=None ninguna se estrecha: la última se alarga hasta el borde.
    """
    cab = tabla.horizontalHeader()
    cab.setStretchLastSection(estirar is None)
    for col in range(tabla.columnCount()):
        if col == estirar:
            cab.setSectionResizeMode(col, QHeaderView.Stretch)
        elif fijas and col in fijas:
            cab.setSectionResizeMode(col, QHeaderView.Fixed)
            tabla.setColumnWidth(col, fijas[col])
        else:
            cab.setSectionResizeMode(col, QHeaderView.ResizeToContents)


class DialogoCompra(Dialogo):
    """
    Registrar una compra: los artículos (existentes o nuevos) entran al inventario con su costo y su
    precio de venta. El apartado opcional de estimación ayuda a decidir ese precio con la brecha.
    """

    def __init__(self, parent, api, productos, previsiones, producto_inicial=None):
        super(DialogoCompra, self).__init__(parent, 'Nueva compra', 'Revisar y registrar', ancho=1060)
        self.api = api
        self.prev = previsiones or {}
        self.productos = sorted(productos, key=lambda p: p['nombre'].lower())
        self.por_nombre = {p['nombre'].strip().lower(): p for p in self.productos}
        self.lineas = []
        self.setMinimumHeight(660)

        contenido = QWidget()
        capa = QVBoxLayout(contenido)
        capa.setContentsMargins(0, 0, 8, 0)
        capa.setSpacing(12)
        capa.addWidget(self._datos())
        capa.addWidget(etiqueta('ARTÍCULOS', 'etiqueta'))
        capa.addWidget(self._tabla_articulos())
        pista = etiqueta('Elige un artículo de la lista o escribe el nombre de uno nuevo: se creará en el '
                         'inventario. El precio de venta es el que tendrá el artículo al registrar la compra.',
                         'subtitulo', ajustar=True)
        pista.setStyleSheet('font-size: 8.5pt;')
        capa.addWidget(pista)
        fila = QHBoxLayout()
        agregar = boton('Añadir artículo', 'mas', tipo='plano')
        agregar.clicked.connect(lambda: self._agregar_linea())
        fila.addWidget(agregar)
        fila.addStretch()
        fila.addWidget(etiqueta('TOTAL FACTURA', 'etiqueta'))
        self.total = etiqueta('', 'cifra')
        fila.addWidget(self.total)
        capa.addLayout(fila)
        capa.addWidget(self._pago_contado())
        capa.addWidget(self._estimacion())
        capa.addStretch()

        desplazable = QScrollArea()
        desplazable.setWidget(contenido)
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.NoFrame)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cuerpo.addWidget(desplazable)

        self._agregar_linea(producto_inicial)
        self._cambio_forma()

    # Construcción

    def _datos(self):
        caja = QWidget()
        g = QGridLayout(caja)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(8)
        self.proveedor = QComboBox()
        self.proveedor.setEditable(True)
        self.proveedor.addItems(self.prev.get('proveedores') or [])
        self.proveedor.setCurrentText('')
        self.proveedor.lineEdit().setPlaceholderText('Nombre del proveedor')
        self.fecha = QDateEdit(QDate.currentDate())
        self.fecha.setCalendarPopup(True)
        self.fecha.setDisplayFormat('dd/MM/yyyy')
        self.fecha.setMinimumWidth(135)
        self.fecha.dateChanged.connect(self._pintar_vence)
        self.forma = QComboBox()
        for clave, nombre in FORMAS_PAGO:
            self.forma.addItem(nombre, clave)
        self.forma.currentIndexChanged.connect(self._cambio_forma)

        self.contado = QRadioButton('Contado')
        self.a_plazo = QRadioButton('A pagar en')
        grupo = QButtonGroup(self)
        grupo.addButton(self.contado)
        grupo.addButton(self.a_plazo)
        self.a_plazo.setChecked(True)
        self.meses = QSpinBox()
        self.meses.setRange(1, 36)
        self.meses.setValue(3)
        self.meses.setSuffix(' meses')
        self.vence = etiqueta('', 'subtitulo')
        for w in (self.contado, self.a_plazo):
            w.toggled.connect(self._cambio_plazo)
        self.meses.valueChanged.connect(self._cambio_plazo)
        plazo = QHBoxLayout()
        plazo.addWidget(self.contado)
        plazo.addSpacing(10)
        plazo.addWidget(self.a_plazo)
        plazo.addWidget(self.meses)
        plazo.addWidget(self.vence)
        plazo.addStretch()

        g.addWidget(etiqueta('Proveedor'), 0, 0)
        g.addWidget(self.proveedor, 0, 1)
        g.addWidget(etiqueta('Fecha'), 0, 2)
        g.addWidget(self.fecha, 0, 3)
        g.addWidget(etiqueta('Se paga'), 1, 0)
        g.addWidget(self.forma, 1, 1)
        g.addWidget(etiqueta('Plazo'), 2, 0)
        g.addLayout(plazo, 2, 1, 1, 3)
        g.setColumnStretch(1, 1)
        return caja

    def _tabla_articulos(self):
        t = self.tabla = QTableWidget(0, 6)
        t.setHorizontalHeaderLabels(['Artículo', 'Cantidad', 'Costo unitario', 'Precio de venta', 'Subtotal', ''])
        t.verticalHeader().hide()
        t.verticalHeader().setDefaultSectionSize(42)
        t.setShowGrid(False)
        t.setSelectionMode(QAbstractItemView.NoSelection)
        t.setFocusPolicy(Qt.NoFocus)
        t.setMinimumHeight(170)
        _ajustar_columnas(t, 0, {1: 100, 2: 145, 3: 145, 4: 120, 5: 34})
        return t

    def _pago_contado(self):
        self.caja_contado = QWidget()
        fila = QHBoxLayout(self.caja_contado)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.addWidget(etiqueta('Se paga hoy a'))
        self.tasa_contado = _decimal_spin(100000000, 2, ' Bs/$')
        self.tasa_contado.setMinimumWidth(160)
        self.tasa_contado.valueChanged.connect(self._recalcular)
        fila.addWidget(self.tasa_contado)
        self.bs_contado = etiqueta('', 'subtitulo')
        fila.addWidget(self.bs_contado)
        fila.addStretch()
        return self.caja_contado

    def _estimacion(self):
        self.grupo_estimacion = QGroupBox('Ayuda para poner el precio de venta (opcional)')
        self.grupo_estimacion.setCheckable(True)
        self.grupo_estimacion.setChecked(False)
        self.grupo_estimacion.setStyleSheet(
            'QGroupBox { font-weight: 600; color: %s; border: 1px solid %s; border-radius: 8px; margin-top: 10px;'
            ' padding: 14px 10px 10px 10px; background: white; }'
            'QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }' % (tema.MARINO, tema.BORDE))
        capa_grupo = QVBoxLayout(self.grupo_estimacion)
        self.contenido_estimacion = QWidget()
        capa = QVBoxLayout(self.contenido_estimacion)
        capa.setContentsMargins(0, 4, 0, 0)
        capa_grupo.addWidget(self.contenido_estimacion)
        self.grupo_estimacion.toggled.connect(self.contenido_estimacion.setVisible)
        self.grupo_estimacion.toggled.connect(lambda *_: self._recalcular())
        self.contenido_estimacion.hide()

        p = self.prev
        self.ritmo_usdt = _decimal_spin(100, 2, ' %/mes', -50)
        self.ritmo_usdt.setValue(float(p.get('ritmo_usdt') or 4))
        self.ritmo_bcv = _decimal_spin(100, 2, ' %/mes', -50)
        self.ritmo_bcv.setValue(float(p.get('ritmo_bcv') or 3))
        self.meses_venta = QSpinBox()
        self.meses_venta.setRange(1, 24)
        self.meses_venta.setValue(2)
        self.meses_venta.setSuffix(' meses')
        self.pct_dolares = _decimal_spin(100, 0, ' %')
        self.pct_dolares.setValue(float(p.get('porcentaje_dolares') or 30))
        self.margen_obj = _decimal_spin(95, 0, ' %')
        self.margen_obj.setValue(40)
        for w in (self.ritmo_usdt, self.ritmo_bcv, self.meses_venta, self.pct_dolares, self.margen_obj):
            w.valueChanged.connect(self._recalcular)
            w.setFixedWidth(165)

        g = QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(6)
        g.addWidget(etiqueta('USDT hoy {} · sube'.format(formato.numero(p.get('usdt') or 0))), 0, 0)
        g.addWidget(self.ritmo_usdt, 0, 1)
        g.addWidget(etiqueta('BCV hoy {} · sube'.format(formato.numero(p.get('bcv') or 0))), 0, 2)
        g.addWidget(self.ritmo_bcv, 0, 3)
        g.addWidget(etiqueta('Se venderá en'), 1, 0)
        g.addWidget(self.meses_venta, 1, 1)
        g.addWidget(etiqueta('Cobrado en $ o USDT'), 1, 2)
        g.addWidget(self.pct_dolares, 1, 3)
        g.addWidget(etiqueta('Margen que quieres ganar'), 2, 0)
        g.addWidget(self.margen_obj, 2, 1)
        g.setColumnStretch(4, 1)
        capa.addLayout(g)
        origen = []
        if p.get('ritmo_usdt') is None or p.get('ritmo_bcv') is None:
            origen.append('Aún no hay historial de tasas: la subida mensual se pone a mano.')
        if p.get('porcentaje_dolares') is not None:
            origen.append('El % cobrado en $ sale de las ventas de los últimos 30 días.')
        nota = etiqueta(' '.join(origen), 'subtitulo', ajustar=True)
        nota.setStyleSheet('font-size: 8.5pt;')
        capa.addWidget(nota)

        t = self.tabla_estimacion = QTableWidget(0, 7)
        t.setHorizontalHeaderLabels(['Artículo', 'Costo', 'Margen estimado', 'Con la brecha', 'Escenarios',
                                     'Precio sugerido', ''])
        for col, consejo in ((2, 'Solo compara costo y precio de venta, sin tasas'),
                             (3, 'Con la tasa a la que pagarás al proveedor y la tasa media a la que venderás'),
                             (4, 'Margen con la brecha: si no cambia / si sigue como va / si se agranda'),
                             (5, 'Precio para ganar el margen que quieres (redondeado hacia arriba a 0,50 $)')):
            t.horizontalHeaderItem(col).setToolTip(consejo)
        t.verticalHeader().hide()
        t.verticalHeader().setDefaultSectionSize(40)
        t.setShowGrid(False)
        t.setSelectionMode(QAbstractItemView.NoSelection)
        t.setFocusPolicy(Qt.NoFocus)
        t.setMinimumHeight(150)
        _ajustar_columnas(t, 4, {6: 92})
        capa.addWidget(t)
        ayuda = etiqueta('Los márgenes usan el precio de venta de arriba (Artículos). «Aplicar» pone ahí el '
                         'precio sugerido; puedes cambiarlo a mano y la estimación se recalcula.', 'subtitulo',
                         ajustar=True)
        ayuda.setStyleSheet('font-size: 8.5pt;')
        capa.addWidget(ayuda)
        return self.grupo_estimacion

    # Filas de artículos

    def _agregar_linea(self, producto_id=None):
        r = self.tabla.rowCount()
        self.tabla.insertRow(r)
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.addItem('')
        for p in self.productos:
            combo.addItem(p['nombre'] + ('' if p.get('activo', True) else '  (desactivado)'), p['id'])
        combo.lineEdit().setPlaceholderText('Artículo o nombre de uno nuevo')
        completador = QCompleter(combo.model(), combo)
        completador.setFilterMode(Qt.MatchContains)
        completador.setCaseSensitivity(Qt.CaseInsensitive)
        combo.setCompleter(completador)
        if producto_id is not None:
            i = combo.findData(producto_id)
            if i >= 0:
                combo.setCurrentIndex(i)
        cantidad = QSpinBox()
        cantidad.setRange(1, 99999)
        costo = _decimal_spin(99999999, 2)
        precio = _decimal_spin(99999999, 2, ' $')
        precio.setToolTip('Precio de venta con el que el artículo queda en el inventario')
        subtotal = QTableWidgetItem('')
        subtotal.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        quitar = QToolButton()
        quitar.setIcon(tema.icono('quitar', tema.ROJO, 16))
        quitar.setIconSize(QSize(16, 16))
        quitar.setAutoRaise(True)
        quitar.setToolTip('Quitar artículo')
        self.tabla.setCellWidget(r, 0, combo)
        self.tabla.setCellWidget(r, 1, cantidad)
        self.tabla.setCellWidget(r, 2, costo)
        self.tabla.setCellWidget(r, 3, precio)
        self.tabla.setItem(r, 4, subtotal)
        self.tabla.setCellWidget(r, 5, quitar)

        aplicar = boton('Aplicar', tipo='plano')
        aplicar.setToolTip('Poner el precio sugerido como precio de venta')
        linea = {'combo': combo, 'cantidad': cantidad, 'costo': costo, 'precio': precio, 'subtotal': subtotal,
                 'aplicar': aplicar, 'precio_tocado': False, 'estimacion': None, 'producto_anterior': None}
        self.lineas.append(linea)
        e = self.tabla_estimacion
        e.insertRow(r)
        for col in range(6):
            item = QTableWidgetItem('')
            item.setTextAlignment((Qt.AlignLeft if col == 0 else Qt.AlignRight) | Qt.AlignVCenter)
            e.setItem(r, col, item)
        e.setCellWidget(r, 6, aplicar)

        combo.editTextChanged.connect(lambda *_, l=linea: self._cambio_producto(l))
        for w in (cantidad, costo):
            w.valueChanged.connect(self._recalcular)
        precio.valueChanged.connect(lambda *_, l=linea: self._precio_editado(l))
        quitar.clicked.connect(lambda _=False, l=linea: self._quitar_linea(l))
        aplicar.clicked.connect(lambda _=False, l=linea: self._aplicar_sugerido(l))
        self._ajustar_moneda()
        self._cambio_producto(linea)

    def _quitar_linea(self, linea):
        if len(self.lineas) == 1:
            return
        r = self.lineas.index(linea)
        self.lineas.pop(r)
        self.tabla.removeRow(r)
        self.tabla_estimacion.removeRow(r)
        self._recalcular()

    def _nombre(self, linea):
        return linea['combo'].currentText().replace('  (desactivado)', '').strip()

    def _producto(self, linea):
        return self.por_nombre.get(self._nombre(linea).lower())

    def _cambio_producto(self, linea):
        p = self._producto(linea)
        nuevo = bool(self._nombre(linea)) and p is None
        combo = linea['combo']
        combo.setStyleSheet('QComboBox { border-color: %s; background: %s; }' % (tema.CELESTE, tema.CELESTE_CLARO)
                            if nuevo else '')
        combo.setToolTip('Artículo nuevo: se creará en el inventario al registrar la compra' if nuevo else '')
        pid = p['id'] if p else None
        if pid != linea['producto_anterior']:
            linea['producto_anterior'] = pid
            if p and not linea['precio_tocado']:
                self._poner_precio(linea, p['precio'])
        self._recalcular()

    def _poner_precio(self, linea, valor):
        linea['precio'].blockSignals(True)
        linea['precio'].setValue(float(formato.decimal(valor)))
        linea['precio'].blockSignals(False)

    def _precio_editado(self, linea):
        linea['precio_tocado'] = True
        self._recalcular()

    def _aplicar_sugerido(self, linea):
        res = linea.get('estimacion')
        if res and res.get('precio_objetivo'):
            linea['precio_tocado'] = True
            self._poner_precio(linea, _redondear_precio(res['precio_objetivo']))
            self._recalcular()

    # Forma de pago y plazo

    def _forma(self):
        return self.forma.currentData()

    def _plazo(self):
        return 0 if self.contado.isChecked() else self.meses.value()

    def _ajustar_moneda(self):
        sufijo = ' Bs' if self._forma() == 'bs_fijos' else ' $'
        for l in self.lineas:
            l['costo'].setSuffix(sufijo)

    def _cambio_forma(self, *args):
        self._ajustar_moneda()
        tasa = self.prev.get('bcv') if self._forma() == 'bs_bcv' else self.prev.get('usdt')
        self.tasa_contado.blockSignals(True)
        self.tasa_contado.setValue(float(tasa or 0))
        self.tasa_contado.blockSignals(False)
        self._cambio_plazo()

    def _cambio_plazo(self, *args):
        self.meses.setEnabled(self.a_plazo.isChecked())
        self._pintar_vence()
        self.caja_contado.setVisible(self.contado.isChecked() and self._forma() in ('bs_usdt', 'bs_bcv'))
        self._recalcular()

    def _fecha_vence(self):
        d = self.fecha.date()
        return sumar_meses(date(d.year(), d.month(), d.day()), self._plazo())

    def _pintar_vence(self, *args):
        if self.contado.isChecked():
            self.vence.setText('Se paga hoy')
        else:
            self.vence.setText('· vence el {}'.format(self._fecha_vence().strftime('%d/%m/%Y')))

    # Cálculos

    def _total(self):
        return sum((formato.decimal(l['costo'].value()) * l['cantidad'].value() for l in self.lineas),
                   formato.decimal(0))

    def _previsiones(self):
        return estimacion.Previsiones(
            bcv=self.prev.get('bcv') or 0, usdt=self.prev.get('usdt') or 0, ritmo_bcv=self.ritmo_bcv.value(),
            ritmo_usdt=self.ritmo_usdt.value(), meses_venta=self.meses_venta.value(),
            pct_dolares=self.pct_dolares.value(), margen_objetivo=self.margen_obj.value())

    def _recalcular(self, *args):
        forma = self._forma()
        for l in self.lineas:
            sub = formato.decimal(l['costo'].value()) * l['cantidad'].value()
            l['subtotal'].setText(importe_factura(sub, forma))
        total = self._total()
        self.total.setText(importe_factura(total, forma))
        if self.caja_contado.isVisible():
            self.bs_contado.setText('→ {} en total'.format(
                formato.bolivares(total * formato.decimal(self.tasa_contado.value()))))
        if self.grupo_estimacion.isChecked():
            self._pintar_estimacion()

    def _pintar_estimacion(self):
        e = self.tabla_estimacion
        hay_tasas = bool(self.prev.get('usdt') and self.prev.get('bcv'))
        prev = self._previsiones() if hay_tasas else None
        forma, plazo = self._forma(), self._plazo()
        for r, l in enumerate(self.lineas):
            costo, precio = l['costo'].value(), l['precio'].value()
            e.item(r, 0).setText(self._nombre(l) or '—')
            e.item(r, 0).setToolTip('Precio de venta: {}'.format(formato.dinero(precio)))
            e.item(r, 1).setText(importe_factura(costo, forma))
            if not prev or costo <= 0:
                for col in (2, 3, 4, 5):
                    e.item(r, col).setText('—')
                l['estimacion'] = None
                l['aplicar'].setEnabled(False)
                continue
            res = estimacion.estimar(costo, precio, forma, plazo, prev)
            l['estimacion'] = res
            l['aplicar'].setEnabled(bool(res['precio_objetivo']))
            sugerido = _redondear_precio(res['precio_objetivo']) if res['precio_objetivo'] else None
            e.item(r, 5).setText(formato.dinero(sugerido) if sugerido else '—')
            e.item(r, 5).setToolTip('Exacto: {} · para mantener el margen estimado: {}'.format(
                formato.dinero(res['precio_objetivo']) if res['precio_objetivo'] else '—',
                formato.dinero(res['precio_mantener']) if res['precio_mantener'] else '—'))
            if precio <= 0:
                for col in (2, 3, 4):
                    e.item(r, col).setText('—')
                continue
            esc = estimacion.escenarios(costo, precio, forma, plazo, prev)
            e.item(r, 2).setText(_pct(res['estimado']))
            e.item(r, 3).setText(_pct(res['previsto']))
            e.item(r, 3).setForeground(QColor(_color_margen(res['previsto'], prev.margen_objetivo)))
            e.item(r, 3).setToolTip('Pagarás a ~{} Bs/$ y venderás a una media de ~{} Bs/$'.format(
                formato.numero(res['tasa_pago']), formato.numero(res['tasa_venta'])))
            e.item(r, 4).setText(' / '.join(formato.numero(esc[k], 1) for k, _ in estimacion.ESCENARIOS) + ' %')
            e.item(r, 4).setToolTip('\n'.join('{}: {}'.format(nombre, _pct(esc[k]))
                                              for k, nombre in estimacion.ESCENARIOS))

    # Confirmar y guardar

    def validar(self):
        vistos = set()
        for l in self.lineas:
            nombre = self._nombre(l)
            if not nombre:
                return 'Elige el artículo de cada línea o escribe el nombre de uno nuevo.'
            if nombre.lower() in vistos:
                return 'Hay artículos repetidos: junta las cantidades en una sola línea.'
            vistos.add(nombre.lower())
            if l['costo'].value() <= 0:
                return 'Indica el costo de «{}».'.format(nombre)
            if l['precio'].value() <= 0:
                return 'Indica el precio de venta de «{}».'.format(nombre)
        if self.caja_contado.isVisible() and self.tasa_contado.value() <= 0:
            return 'Indica la tasa a la que se paga hoy.'
        return ''

    def _resumen(self):
        forma = self._forma()
        filas = []
        for l in self.lineas:
            p = self._producto(l)
            precio = formato.decimal('{:.2f}'.format(l['precio'].value()))
            anterior = formato.decimal(p['precio']) if p else None
            res = l.get('estimacion') if self.grupo_estimacion.isChecked() else None
            filas.append({
                'nombre': self._nombre(l), 'nuevo': p is None, 'cantidad': l['cantidad'].value(),
                'costo': formato.decimal(l['costo'].value()), 'precio': precio,
                'precio_anterior': anterior if anterior is not None and anterior != precio else None,
                'margen': (precio - formato.decimal(l['costo'].value())) / precio * 100
                if forma != 'bs_fijos' else None,
                'previsto': res['previsto'] if res else None,
            })
        pago = texto_plazo(self._plazo())
        if self._plazo():
            pago += ' · vence el {}'.format(self._fecha_vence().strftime('%d/%m/%Y'))
        elif self.caja_contado.isVisible():
            tasa = formato.decimal(self.tasa_contado.value())
            pago += ' · se paga hoy a {} Bs/$ = {}'.format(formato.numero(tasa), formato.bolivares(self._total() * tasa))
        return {'proveedor': self.proveedor.currentText().strip() or 'Sin proveedor',
                'fecha': self.fecha.date().toString('dd/MM/yyyy'), 'forma': forma, 'pago': pago,
                'filas': filas, 'total': self._total()}

    def _aceptar(self):
        mensaje = self.validar()
        self.mostrar_error(mensaje)
        if mensaje:
            return
        if DialogoConfirmarCompra(self, self._resumen()).exec_() != QDialog.Accepted:
            return
        super(DialogoCompra, self)._aceptar()

    def guardar(self):
        con_estimacion = self.grupo_estimacion.isChecked()
        lineas = []
        for l in self.lineas:
            p = self._producto(l)
            linea = {'cantidad': l['cantidad'].value(), 'costo_unitario': '{:.2f}'.format(l['costo'].value()),
                     'precio_venta': '{:.2f}'.format(l['precio'].value())}
            if p:
                linea['producto'] = p['id']
            else:
                linea['nuevo_nombre'] = self._nombre(l)
            res = l.get('estimacion') if con_estimacion else None
            if res and res.get('previsto') is not None:
                linea['precio_previsto'] = linea['precio_venta']
                linea['margen_previsto'] = '{:.2f}'.format(res['previsto'])
            lineas.append(linea)
        d = self.fecha.date()
        datos = {
            'proveedor': self.proveedor.currentText().strip(),
            'fecha': '{:04d}-{:02d}-{:02d}'.format(d.year(), d.month(), d.day()),
            'plazo_meses': self._plazo(),
            'forma_pago': self._forma(),
            'lineas': lineas,
        }
        if self.caja_contado.isVisible():
            datos['pago'] = {'tasa_pago': '{:.4f}'.format(self.tasa_contado.value())}
        api = self.api
        return lambda: api.crear_compra(datos)


class DialogoConfirmarCompra(QDialog):
    """Resumen de la compra para revisarla antes de registrarla."""

    def __init__(self, parent, resumen):
        super(DialogoConfirmarCompra, self).__init__(parent)
        self.setWindowTitle('Revisa la compra')
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumWidth(1080)
        forma = resumen['forma']
        capa = QVBoxLayout(self)
        capa.setContentsMargins(24, 20, 24, 18)
        capa.setSpacing(10)
        capa.addWidget(etiqueta('Revisa la compra antes de registrarla', 'seccion'))
        datos = QGridLayout()
        datos.setHorizontalSpacing(14)
        for i, (titulo, valor) in enumerate((('Proveedor', resumen['proveedor']), ('Fecha', resumen['fecha']),
                                              ('Se paga', NOMBRE_FORMA.get(forma, forma)), ('Pago', resumen['pago']))):
            datos.addWidget(etiqueta(titulo.upper(), 'etiqueta'), i, 0)
            datos.addWidget(etiqueta(valor), i, 1)
        datos.setColumnStretch(1, 1)
        capa.addLayout(datos)

        t = QTableWidget(len(resumen['filas']), 7)
        t.setHorizontalHeaderLabels(['Artículo', 'Cantidad', 'Costo u.', 'Subtotal', 'Precio de venta',
                                     'Margen estimado', 'Con la brecha'])
        t.verticalHeader().hide()
        t.verticalHeader().setDefaultSectionSize(34)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionMode(QAbstractItemView.NoSelection)
        t.setFocusPolicy(Qt.NoFocus)
        t.setShowGrid(False)
        for r, f in enumerate(resumen['filas']):
            precio = formato.dinero(f['precio'])
            if f['precio_anterior'] is not None:
                precio += '  (antes {})'.format(formato.dinero(f['precio_anterior']))
            valores = [f['nombre'] + ('  · NUEVO' if f['nuevo'] else ''), str(f['cantidad']),
                       importe_factura(f['costo'], forma), importe_factura(f['costo'] * f['cantidad'], forma), precio,
                       _pct(f['margen']), _pct(f['previsto'])]
            for c, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                item.setTextAlignment((Qt.AlignLeft if c in (0, 4) else Qt.AlignRight) | Qt.AlignVCenter)
                if c == 0 and f['nuevo']:
                    item.setForeground(QColor(tema.CELESTE_OSCURO))
                if c == 4 and f['precio_anterior'] is not None:
                    item.setForeground(QColor(tema.AMBAR))
                t.setItem(r, c, item)
        _ajustar_columnas(t, None)
        t.setMinimumHeight(min(320, 46 + 34 * len(resumen['filas'])))
        capa.addWidget(t)

        unidades = sum(f['cantidad'] for f in resumen['filas'])
        nuevos = sum(1 for f in resumen['filas'] if f['nuevo'])
        cambios = sum(1 for f in resumen['filas'] if f['precio_anterior'] is not None)
        fila = QHBoxLayout()
        partes = ['Entrarán {} unidad{} al inventario'.format(unidades, '' if unidades == 1 else 'es')]
        if nuevos:
            partes.append('se crearán {} artículo{} nuevo{}'.format(nuevos, '' if nuevos == 1 else 's',
                                                                   '' if nuevos == 1 else 's'))
        if cambios:
            partes.append('cambiará el precio de venta de {}'.format(cambios))
        fila.addWidget(etiqueta(', '.join(partes) + '.', 'subtitulo', ajustar=True), 1)
        fila.addWidget(etiqueta('TOTAL FACTURA', 'etiqueta'))
        fila.addWidget(etiqueta(importe_factura(resumen['total'], forma), 'cifra'))
        capa.addLayout(fila)

        botones = QHBoxLayout()
        botones.addStretch()
        volver = boton('Volver a editar')
        volver.clicked.connect(self.reject)
        registrar = boton('Registrar compra', 'activar', tipo='primario')
        registrar.setDefault(True)
        registrar.clicked.connect(self.accept)
        botones.addWidget(volver)
        botones.addWidget(registrar)
        capa.addLayout(botones)


# --- Registrar pago ---------------------------------------------------------------------

class DialogoPagoCompra(Dialogo):
    def __init__(self, parent, api, compra, previsiones):
        super(DialogoPagoCompra, self).__init__(parent, 'Registrar pago de la compra #{}'.format(compra['id']),
                                                'Registrar pago', ancho=480)
        self.api, self.compra = api, compra
        forma = compra['forma_pago']
        self.forma = forma
        total = formato.decimal(compra['total_factura'])
        self.total = total
        resumen = etiqueta('{} · {}\nFactura: {} · {}'.format(
            compra['proveedor'] or 'Sin proveedor', texto_plazo(compra['plazo_meses']),
            importe_factura(total, forma), NOMBRE_FORMA.get(forma, forma)), ajustar=True)
        self.cuerpo.addWidget(resumen)
        self.nota = etiqueta('', 'subtitulo', ajustar=True)
        f = self.formulario()
        self.fecha = QDateEdit(QDate.currentDate())
        self.fecha.setCalendarPopup(True)
        self.fecha.setDisplayFormat('dd/MM/yyyy')
        f.addRow('Pagado el', self.fecha)
        self.tasa = self.importe = None
        self._bs_tocado = False
        if forma in ('bs_usdt', 'bs_bcv'):
            self.tasa = _decimal_spin(100000000, 2, ' Bs/$')
            tasa = previsiones.get('usdt') if forma == 'bs_usdt' else previsiones.get('bcv')
            self.tasa.setValue(float(tasa or 0))
            self.importe = _decimal_spin(9999999999, 2, ' Bs')
            self.tasa.valueChanged.connect(self._tasa_cambiada)
            self.importe.valueChanged.connect(self._importe_editado)
            f.addRow('Tasa a la que se pagó', self.tasa)
            f.addRow('Bs pagados', self.importe)
            self._tasa_cambiada()
        elif forma == 'dolares':
            self.importe = _decimal_spin(99999999, 2, ' $')
            self.importe.setValue(float(total))
            f.addRow('Dólares pagados', self.importe)
        else:
            self.importe = _decimal_spin(9999999999, 2, ' Bs')
            self.importe.setValue(float(total))
            f.addRow('Bs pagados', self.importe)
        self.cuerpo.addWidget(self.nota)

    def _tasa_cambiada(self, *args):
        if not self._bs_tocado:
            self.importe.blockSignals(True)
            self.importe.setValue(float(self.total * formato.decimal(self.tasa.value())))
            self.importe.blockSignals(False)
        self.nota.setText('Esta es la tasa con la que se analizará el margen real del lote.')

    def _importe_editado(self, *args):
        self._bs_tocado = True

    def validar(self):
        if self.tasa is not None and self.tasa.value() <= 0:
            return 'Indica la tasa a la que se pagó.'
        if self.importe.value() <= 0:
            return 'Indica el importe pagado.'
        return ''

    def guardar(self):
        d = self.fecha.date()
        datos = {'fecha': '{:04d}-{:02d}-{:02d}'.format(d.year(), d.month(), d.day())}
        if self.forma in ('bs_usdt', 'bs_bcv'):
            datos['tasa_pago'] = '{:.4f}'.format(self.tasa.value())
            datos['bs_pagados'] = '{:.2f}'.format(self.importe.value())
        elif self.forma == 'dolares':
            datos['usd_pagados'] = '{:.2f}'.format(self.importe.value())
        else:
            datos['bs_pagados'] = '{:.2f}'.format(self.importe.value())
        api, cid = self.api, self.compra['id']
        return lambda: api.pagar_compra(cid, datos)


def abrir_nueva_compra(pagina, producto_inicial=None, al_terminar=None):
    """Carga productos y previsiones en segundo plano y abre el diálogo de nueva compra."""
    api = pagina.api

    def abrir(datos):
        productos, previsiones = datos
        dialogo = DialogoCompra(pagina, api, productos, previsiones, producto_inicial)
        if dialogo.exec_() == QDialog.Accepted:
            compra = dialogo.resultado
            pagina.avisar('Compra #{} registrada · {} · {}'.format(
                compra['id'], importe_factura(compra['total_factura'], compra['forma_pago']),
                texto_plazo(compra['plazo_meses'])))
            if al_terminar:
                al_terminar(compra)

    ejecutar(lambda: (api.productos(incluir_inactivos=True), api.previsiones_compra()), al_terminar=abrir,
             al_fallar=pagina.error, widget=pagina)


# --- Pantalla Compras -------------------------------------------------------------------

class DetalleCompra(Tarjeta):
    def __init__(self, pagina):
        super(DetalleCompra, self).__init__(18)
        self.pagina = pagina
        self.compra = None
        self.setMinimumWidth(380)
        self.vacio = etiqueta('Selecciona una compra para ver sus artículos y el pago.', 'subtitulo')
        self.vacio.setAlignment(Qt.AlignCenter)
        self.capa.addWidget(self.vacio, 1)
        self.contenido = QWidget()
        capa = QVBoxLayout(self.contenido)
        capa.setContentsMargins(0, 0, 0, 0)
        self.titulo = etiqueta('', 'seccion')
        self.datos = etiqueta('', 'subtitulo', ajustar=True)
        self.estado = etiqueta('', ajustar=True)
        self.lotes = Tabla([
            Columna('Artículo', lambda l: l['producto_nombre'], estirar=True),
            Columna('Cant.', lambda l: str(l['cantidad']), alinear='der'),
            Columna('Salieron', lambda l: str(l['salidas']), alinear='der'),
            Columna('Costo u.', lambda l: importe_factura(l['costo_unitario'], self.compra['forma_pago']),
                    alinear='der'),
        ], consejo=lambda l: 'Previsto al comprar: precio {} · margen con la brecha {}'.format(
            formato.dinero(l['precio_previsto']), _pct(formato.decimal(l['margen_previsto'])))
            if l.get('precio_previsto') else None, ordenable=False)
        self.lotes.setMinimumHeight(140)
        botones = QHBoxLayout()
        self.b_pagar = boton('Registrar pago', 'activar', tipo='primario')
        self.b_anular = boton('Anular compra', 'quitar', tipo='peligro')
        self.b_pagar.clicked.connect(lambda: pagina.pagar(self.compra))
        self.b_anular.clicked.connect(lambda: pagina.anular(self.compra))
        botones.addWidget(self.b_pagar)
        botones.addStretch()
        botones.addWidget(self.b_anular)
        for w in (self.titulo, self.datos, self.estado):
            capa.addWidget(w)
        capa.addWidget(self.lotes, 1)
        capa.addLayout(botones)
        self.capa.addWidget(self.contenido, 1)
        self.mostrar(None)

    def mostrar(self, compra):
        self.compra = compra
        self.vacio.setVisible(compra is None)
        self.contenido.setVisible(compra is not None)
        if not compra:
            return
        forma = compra['forma_pago']
        self.titulo.setText('Compra #{}'.format(compra['id']))
        self.datos.setText('{} · {}\n{}\nFactura: {} · {}'.format(
            compra['proveedor'] or 'Sin proveedor', formato.fecha_corta(compra['fecha'] + 'T00:00:00'),
            NOMBRE_FORMA.get(forma, forma), importe_factura(compra['total_factura'], forma),
            texto_plazo(compra['plazo_meses'])))
        if compra['estado'] == 'pagada':
            if compra.get('tasa_pago'):
                pago = '{} a {} Bs/$'.format(formato.bolivares(compra['bs_pagados']), formato.numero(compra['tasa_pago']))
            elif compra.get('usd_pagados'):
                pago = formato.dinero(compra['usd_pagados'])
            else:
                pago = formato.bolivares(compra['bs_pagados'])
            texto = 'Pagada el {}: {}'.format(formato.fecha_corta(compra['pagada_el'] + 'T00:00:00'), pago)
        elif compra['estado'] == 'anulada':
            texto = 'Anulada'
        else:
            texto = '{} (vence el {})'.format(texto_estado(compra), formato.fecha_corta(compra['vence'] + 'T00:00:00'))
        self.estado.setText(texto)
        self.estado.setStyleSheet('font-weight: 600; color: {};'.format(color_estado(compra)))
        self.lotes.poner_filas(compra['lotes'], mantener_seleccion=False)
        activa = compra['estado'] not in ('anulada',)
        self.b_pagar.setVisible(activa and compra['estado'] != 'pagada')
        sin_salidas = all(l['salidas'] == 0 for l in compra['lotes'])
        self.b_anular.setVisible(activa and sin_salidas)


class PaginaCompras(Pagina):
    titulo = 'Compras'
    icono = 'entrada'
    solo_admin = True

    def __init__(self, ventana):
        super(PaginaCompras, self).__init__(ventana, 'Lo comprado a proveedores y lo pendiente de pagar')
        self.previsiones = {}
        refrescar = self.cabecera.agregar(boton('Actualizar', 'refrescar'))
        refrescar.clicked.connect(self.cargar)
        nueva = self.cabecera.agregar(boton('Nueva compra', 'mas', tipo='primario'))
        nueva.clicked.connect(lambda: abrir_nueva_compra(self, al_terminar=lambda c: self.cargar(c['id'])))

        cifras = QHBoxLayout()
        cifras.setSpacing(14)
        self.c_pendiente = TarjetaCifra('Pendiente de pagar', detalle=' ')
        self.c_proximo = TarjetaCifra('Próximo vencimiento', detalle=' ')
        self.c_mes = TarjetaCifra('Compras este mes', detalle=' ')
        for c in (self.c_pendiente, self.c_proximo, self.c_mes):
            cifras.addWidget(c, 1)
        self.capa.addLayout(cifras)

        filtro = QHBoxLayout()
        filtro.addWidget(etiqueta('Mostrar'))
        self.filtro = QComboBox()
        for texto, valor in (('Todas', ''), ('Pendientes de pagar', 'pendientes'), ('Pagadas', 'pagadas'),
                             ('Anuladas', 'anuladas')):
            self.filtro.addItem(texto, valor)
        self.filtro.currentIndexChanged.connect(lambda *_: self.cargar())
        filtro.addWidget(self.filtro)
        filtro.addStretch()
        self.capa.addLayout(filtro)

        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(16)
        self.tabla = Tabla([
            Columna('Fecha', lambda c: formato.fecha_corta(c['fecha'] + 'T00:00:00'), orden=lambda c: c['fecha']),
            Columna('Proveedor', lambda c: c['proveedor'] or '—', estirar=True),
            Columna('Total', lambda c: importe_factura(c['total_factura'], c['forma_pago']),
                    orden=lambda c: float(c['total_factura']), alinear='der'),
            Columna('Pago', lambda c: texto_plazo(c['plazo_meses'])),
            Columna('Estado', texto_estado, orden=lambda c: (c['estado'] != 'pendiente', c['vence']),
                    color=color_estado),
        ], consejo=lambda c: 'Compra #{}: {}'.format(c['id'], ', '.join(
            '{}× {}'.format(l['cantidad'], l['producto_nombre']) for l in c['lotes'])),
            vacio='No hay compras registradas. Pulsa «Nueva compra».')
        self.tabla.sortByColumn(0, Qt.DescendingOrder)
        self.tabla.selectionModel().selectionChanged.connect(
            lambda *a: self.detalle.mostrar(self.tabla.fila_seleccionada()))
        self.detalle = DetalleCompra(self)
        cuerpo.addWidget(self.tabla, 3)
        cuerpo.addWidget(self.detalle, 2)
        self.capa.addLayout(cuerpo, 1)
        self._seleccionar = None

    def al_mostrar(self):
        self.cargar()

    def cargar(self, seleccionar=None):
        self._seleccionar = seleccionar
        if not self.tabla.modelo.rowCount():
            self.tabla.poner_cargando()
        estado, api = self.filtro.currentData(), self.api
        ejecutar(lambda: (api.compras(estado), api.previsiones_compra()), al_terminar=self._cargado,
                 al_fallar=self.error, widget=self)

    def _cargado(self, datos):
        compras, self.previsiones = datos
        self.tabla.poner_filas(compras)
        if self._seleccionar:
            self.tabla.seleccionar_id(self._seleccionar)
        self.detalle.mostrar(self.tabla.fila_seleccionada())
        p = self.previsiones
        bs = formato.decimal(p.get('pendiente_bs'))
        self.c_pendiente.poner(formato.dinero(p.get('pendiente_usd')),
                               'y {} en montos fijos'.format(formato.bolivares(bs)) if bs else 'De todas las compras')
        prox = p.get('proximo_vencimiento')
        if prox:
            self.c_proximo.poner(formato.fecha_corta(prox['vence'] + 'T00:00:00'), '{} · {}'.format(
                texto_estado(prox), prox['proveedor'] or 'Sin proveedor'))
            self.c_proximo.valor.setStyleSheet('color: {};'.format(color_estado(prox)))
        else:
            self.c_proximo.poner('Nada pendiente', ' ')
            self.c_proximo.valor.setStyleSheet('')
        hoy = date.today()
        del_mes = [c for c in compras if c['fecha'][:7] == hoy.strftime('%Y-%m') and c['estado'] != 'anulada']
        total_usd = sum((formato.decimal(c['total_factura']) for c in del_mes if c['forma_pago'] != 'bs_fijos'),
                        formato.decimal(0))
        self.c_mes.poner(str(len(del_mes)), formato.dinero(total_usd) + ' en facturas en $')

    def pagar(self, compra):
        if not compra:
            return
        d = DialogoPagoCompra(self, self.api, compra, self.previsiones)
        if d.exec_() == QDialog.Accepted:
            self.avisar('Pago de la compra #{} registrado.'.format(compra['id']))
            self.cargar(compra['id'])

    def anular(self, compra):
        if not compra or not confirmar(self, 'Anular compra', '¿Anular la compra #{}? Se quitará del stock lo '
                                       'que entró con ella.'.format(compra['id']), si='Anular compra', peligro=True):
            return
        ejecutar(lambda: self.api.anular_compra(compra['id']),
                 al_terminar=lambda _: (self.avisar('Compra #{} anulada.'.format(compra['id'])),
                                        self.cargar(compra['id'])),
                 al_fallar=lambda e: mostrar_error(self, e), widget=self)
