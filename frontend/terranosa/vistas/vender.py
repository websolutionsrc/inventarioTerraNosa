"""Punto de venta: buscar productos, armar el carrito y cobrar."""
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (QAbstractItemView, QComboBox, QFormLayout, QFrame, QHBoxLayout, QHeaderView,
                             QLineEdit, QShortcut, QSpinBox, QTableWidget, QTableWidgetItem, QToolButton,
                             QVBoxLayout, QWidget)

from .. import formato, tema
from ..tareas import ejecutar
from ..widgets import Columna, EtiquetaRecortada, Tabla, Tarjeta, boton, confirmar, etiqueta, mostrar_error
from .base import Pagina


def _color_stock(p):
    if p['stock'] <= 0:
        return tema.ROJO
    if p.get('stock_bajo'):
        return tema.AMBAR
    return None


class PaginaVender(Pagina):
    titulo = 'Vender'
    icono = 'vender'

    def __init__(self, ventana):
        super(PaginaVender, self).__init__(ventana, formato.fecha_larga(formato.hoy(ventana.api)).capitalize())
        self.productos = {}
        self.carrito = []  # [{"producto": {...}, "cantidad": n}]
        self._venta_pendiente = None

        refrescar = self.cabecera.agregar(boton('Actualizar productos', 'refrescar'))
        refrescar.clicked.connect(self.cargar_productos)

        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(16)
        cuerpo.addWidget(self._catalogo(), 11)
        cuerpo.addWidget(self._panel_carrito(), 9)
        self.capa.addLayout(cuerpo, 1)

        QShortcut(QKeySequence('Ctrl+F'), self, activated=self._enfocar_busqueda)
        QShortcut(QKeySequence('F12'), self, activated=self.cobrar)
        self._pintar_carrito()

    # --- Catálogo ---

    def _catalogo(self):
        tarjeta = Tarjeta()
        self.busqueda = QLineEdit()
        self.busqueda.setPlaceholderText('Buscar por nombre, tipo o proveedor…   (Ctrl+F)')
        self.busqueda.setMinimumHeight(38)
        self.busqueda.addAction(tema.icono('buscar', tema.TEXTO_SUAVE, 18), QLineEdit.LeadingPosition)
        self.busqueda.setClearButtonEnabled(True)
        self.busqueda.textChanged.connect(self._filtrar)
        self.busqueda.returnPressed.connect(self._agregar_primero)
        tarjeta.capa.addWidget(self.busqueda)

        self.tabla = Tabla([
            Columna('Producto', lambda p: p['nombre'], estirar=True),
            Columna('Tipo', lambda p: p['tipo']),
            Columna('Precio', lambda p: formato.dinero(p['precio']), orden=lambda p: float(p['precio']),
                    alinear='der'),
            Columna('Stock', lambda p: str(p['stock']), orden=lambda p: p['stock'], alinear='der',
                    color=_color_stock),
        ], consejo=lambda p: '{} · {}'.format(p['proveedor'] or 'Sin proveedor', 'Sin stock' if p['stock'] <= 0
                                              else 'doble clic o Enter para añadir'),
            vacio='No hay productos.', buscar_tambien=lambda p: p['proveedor'])
        self.tabla.sortByColumn(0, Qt.AscendingOrder)
        self.tabla.doubleClicked.connect(lambda _: self._agregar_seleccionado())
        QShortcut(QKeySequence(Qt.Key_Return), self.tabla, activated=self._agregar_seleccionado,
                  context=Qt.WidgetShortcut)
        tarjeta.capa.addWidget(self.tabla, 1)
        pista = etiqueta('Doble clic o Enter para añadir al carrito. En rojo, sin stock; en ámbar, stock bajo.',
                         'subtitulo')
        pista.setStyleSheet('font-size: 8.5pt;')
        tarjeta.capa.addWidget(pista)
        return tarjeta

    def _enfocar_busqueda(self):
        self.busqueda.setFocus()
        self.busqueda.selectAll()

    def _filtrar(self, texto):
        self.tabla.filtro.buscar(texto)
        if self.tabla.filtro.rowCount():
            self.tabla.selectRow(0)

    def keyPressEvent(self, evento):
        if self.busqueda.hasFocus() and evento.key() == Qt.Key_Down:
            self.tabla.setFocus()
            return
        super(PaginaVender, self).keyPressEvent(evento)

    def al_mostrar(self):
        self.cargar_productos()
        self._enfocar_busqueda()

    def cargar_productos(self):
        if not self.productos:
            self.tabla.poner_cargando()
        ejecutar(self.api.productos, al_terminar=self._productos_cargados, al_fallar=self.error, widget=self)

    def _productos_cargados(self, productos):
        self.productos = {p['id']: p for p in productos}
        self.tabla.poner_filas(productos)
        # El carrito usa los datos nuevos (precio y stock) y quita lo que ya no se vende
        quitados = []
        for linea in list(self.carrito):
            p = self.productos.get(linea['producto']['id'])
            if not p or p['stock'] <= 0:
                quitados.append(linea['producto']['nombre'])
                self.carrito.remove(linea)
            else:
                linea['producto'] = p
                linea['cantidad'] = min(linea['cantidad'], p['stock'])
        self._pintar_carrito()
        if quitados:
            self.avisar('Se quitó del carrito por falta de stock: ' + ', '.join(quitados), 'error')
        if self._venta_pendiente:
            venta, self._venta_pendiente = self._venta_pendiente, None
            self._aplicar_venta(venta)

    def _agregar_primero(self):
        if self.tabla.filtro.rowCount() == 1 or self.tabla.fila_seleccionada() is None:
            self.tabla.selectRow(0)
        self._agregar_seleccionado()

    def _agregar_seleccionado(self):
        p = self.tabla.fila_seleccionada()
        if p:
            self.agregar(p)

    def agregar(self, producto, cantidad=1):
        if producto['stock'] <= 0:
            self.avisar('«{}» no tiene stock.'.format(producto['nombre']), 'error')
            return
        for linea in self.carrito:
            if linea['producto']['id'] == producto['id']:
                if linea['cantidad'] >= producto['stock']:
                    self.avisar('Solo quedan {} de «{}».'.format(producto['stock'], producto['nombre']), 'error')
                    return
                linea['cantidad'] = min(linea['cantidad'] + cantidad, producto['stock'])
                break
        else:
            self.carrito.append({'producto': producto, 'cantidad': min(cantidad, producto['stock'])})
        self._pintar_carrito()

    # --- Carrito ---

    def _panel_carrito(self):
        tarjeta = Tarjeta()
        cab = QHBoxLayout()
        cab.addWidget(etiqueta('Venta actual', 'seccion'))
        cab.addStretch()
        self.vaciar = boton('Vaciar', 'quitar', tipo='plano')
        self.vaciar.clicked.connect(self._vaciar)
        cab.addWidget(self.vaciar)
        tarjeta.capa.addLayout(cab)

        self.tabla_carrito = QTableWidget(0, 4)
        self.tabla_carrito.setHorizontalHeaderLabels(['Producto', 'Cant.', 'Subtotal', ''])
        self.tabla_carrito.verticalHeader().hide()
        self.tabla_carrito.verticalHeader().setDefaultSectionSize(48)
        self.tabla_carrito.setShowGrid(False)
        self.tabla_carrito.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_carrito.setSelectionMode(QAbstractItemView.NoSelection)
        self.tabla_carrito.setFocusPolicy(Qt.NoFocus)
        cab_t = self.tabla_carrito.horizontalHeader()
        cab_t.setSectionResizeMode(0, QHeaderView.Stretch)
        for col, ancho in ((1, 104), (2, 86), (3, 34)):
            cab_t.setSectionResizeMode(col, QHeaderView.Fixed)
            self.tabla_carrito.setColumnWidth(col, ancho)
        tarjeta.capa.addWidget(self.tabla_carrito, 1)

        self.carrito_vacio = etiqueta('El carrito está vacío.\nBusca un producto y pulsa Enter para añadirlo.',
                                      'subtitulo')
        self.carrito_vacio.setAlignment(Qt.AlignCenter)
        tarjeta.capa.addWidget(self.carrito_vacio, 1)

        opciones = self.api.opciones or {}
        self.metodo = QComboBox()
        for m in opciones.get('metodos_pago', []):
            self.metodo.addItem(m['nombre'], m['id'])
        self.canal = QComboBox()
        for c in opciones.get('canales', []):
            self.canal.addItem(c['nombre'], c['id'])
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.addRow('Método de pago', self.metodo)
        form.addRow('Canal', self.canal)
        tarjeta.capa.addLayout(form)

        linea = QFrame()
        linea.setFrameShape(QFrame.HLine)
        linea.setStyleSheet('color: {};'.format(tema.BORDE))
        tarjeta.capa.addWidget(linea)

        fila_total = QHBoxLayout()
        self.unidades = etiqueta('', 'subtitulo')
        fila_total.addWidget(self.unidades)
        fila_total.addStretch()
        fila_total.addWidget(etiqueta('TOTAL', 'etiqueta'))
        self.total = etiqueta(formato.dinero(0), 'total')
        fila_total.addWidget(self.total)
        tarjeta.capa.addLayout(fila_total)

        self.boton_cobrar = boton('Cobrar   (F12)', 'activar', tipo='exito', grande=True)
        self.boton_cobrar.setMinimumHeight(52)
        self.boton_cobrar.clicked.connect(self.cobrar)
        tarjeta.capa.addWidget(self.boton_cobrar)
        return tarjeta

    def _total(self):
        return sum((formato.decimal(l['producto']['precio']) * l['cantidad'] for l in self.carrito),
                   formato.decimal(0))

    def _pintar_carrito(self):
        t = self.tabla_carrito
        t.setRowCount(0)  # borra las celdas anteriores antes de pintar las nuevas
        t.setRowCount(len(self.carrito))
        for fila, linea in enumerate(self.carrito):
            p = linea['producto']
            t.setCellWidget(fila, 0, self._celda_nombre(p))
            t.setCellWidget(fila, 1, self._celda_cantidad(linea))

            subtotal = QTableWidgetItem(formato.dinero(formato.decimal(p['precio']) * linea['cantidad']))
            subtotal.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            t.setItem(fila, 2, subtotal)

            quitar = QToolButton()
            quitar.setIcon(tema.icono('quitar', tema.ROJO, 16))
            quitar.setIconSize(QSize(16, 16))
            quitar.setAutoRaise(True)
            quitar.setCursor(Qt.PointingHandCursor)
            quitar.setToolTip('Quitar del carrito')
            quitar.clicked.connect(lambda _=False, l=linea: self._quitar(l))
            t.setCellWidget(fila, 3, quitar)

        vacio = not self.carrito
        t.setVisible(not vacio)
        self.carrito_vacio.setVisible(vacio)
        self.vaciar.setEnabled(not vacio)
        self.boton_cobrar.setEnabled(not vacio)
        self._pintar_total()

    def _celda_nombre(self, p):
        celda = QWidget()
        capa = QVBoxLayout(celda)
        capa.setContentsMargins(8, 2, 4, 2)
        capa.setSpacing(0)
        nombre = EtiquetaRecortada(p['nombre'])
        nombre.setStyleSheet('font-weight: 600;')
        precio = etiqueta('{} c/u · quedan {}'.format(formato.dinero(p['precio']), p['stock']), 'subtitulo')
        precio.setStyleSheet('font-size: 8.5pt;')
        capa.addWidget(nombre)
        capa.addWidget(precio)
        return celda

    def _celda_cantidad(self, linea):
        celda = QWidget()
        capa = QHBoxLayout(celda)
        capa.setContentsMargins(0, 6, 0, 6)
        capa.setSpacing(2)
        cantidad = QSpinBox()
        cantidad.setButtonSymbols(QSpinBox.NoButtons)
        cantidad.setProperty('sinBotones', True)
        cantidad.setAlignment(Qt.AlignCenter)
        cantidad.setFixedWidth(40)
        cantidad.setRange(1, max(1, linea['producto']['stock']))
        cantidad.setValue(linea['cantidad'])
        cantidad.valueChanged.connect(lambda v, l=linea: self._cambiar_cantidad(l, v))
        for icono, paso in (('menos', -1), ('mas', 1)):
            b = QToolButton()
            b.setIcon(tema.icono(icono, tema.CELESTE_OSCURO, 14))
            b.setAutoRaise(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, c=cantidad, d=paso: c.setValue(c.value() + d))
            capa.addWidget(b)
            if paso < 0:
                capa.addWidget(cantidad)
        return celda

    def _pintar_total(self):
        unidades = sum(l['cantidad'] for l in self.carrito)
        self.unidades.setText('{} producto{}'.format(unidades, '' if unidades == 1 else 's') if unidades else '')
        self.total.setText(formato.dinero(self._total()))

    def _cambiar_cantidad(self, linea, valor):
        linea['cantidad'] = valor
        fila = self.carrito.index(linea)
        item = self.tabla_carrito.item(fila, 2)
        if item:
            item.setText(formato.dinero(formato.decimal(linea['producto']['precio']) * valor))
        self._pintar_total()

    def _quitar(self, linea):
        if linea in self.carrito:
            self.carrito.remove(linea)
        self._pintar_carrito()

    def _vaciar(self):
        if self.carrito and confirmar(self, 'Vaciar carrito', '¿Quitar todos los productos del carrito?',
                                      si='Vaciar'):
            self.limpiar()

    def limpiar(self):
        self.carrito = []
        self.metodo.setCurrentIndex(0)
        self.canal.setCurrentIndex(0)
        self._pintar_carrito()

    def cargar_venta(self, venta):
        """Carga los productos de una venta (anulada) para volver a cobrarla, con el stock ya devuelto."""
        self._venta_pendiente = venta
        self.cargar_productos()

    def _aplicar_venta(self, venta):
        self.carrito = []
        faltan = []
        for l in venta['lineas']:
            p = self.productos.get(l['producto'])
            if p and p['stock'] > 0:
                self.carrito.append({'producto': p, 'cantidad': min(l['cantidad'], p['stock'])})
            else:
                faltan.append(l['producto_nombre'])
        for combo, valor in ((self.metodo, venta.get('metodo_pago')), (self.canal, venta.get('canal'))):
            i = combo.findData(valor)
            if i >= 0:
                combo.setCurrentIndex(i)
        self._pintar_carrito()
        mensaje = 'Productos de la venta #{} cargados. Corrige lo necesario y cobra de nuevo.'.format(venta['id'])
        if faltan:
            mensaje += ' Sin stock: ' + ', '.join(faltan) + '.'
        self.avisar(mensaje, 'info')

    def cobrar(self):
        if not self.carrito or not self.boton_cobrar.isEnabled():
            return
        total = formato.dinero(self._total())
        detalle = '\n'.join('{} × {}  =  {}'.format(l['cantidad'], l['producto']['nombre'], formato.dinero(
            formato.decimal(l['producto']['precio']) * l['cantidad'])) for l in self.carrito)
        texto = '{}\n\nTotal: {}\nPago: {} · {}'.format(detalle, total, self.metodo.currentText(),
                                                        self.canal.currentText())
        if not confirmar(self, 'Confirmar venta', texto, si='Cobrar ' + total):
            return
        lineas = [{'producto': l['producto']['id'], 'cantidad': l['cantidad']} for l in self.carrito]
        metodo, canal = self.metodo.currentData(), self.canal.currentData()
        self.boton_cobrar.setEnabled(False)
        self.boton_cobrar.setText('Registrando…')
        ejecutar(lambda: self.api.vender(lineas, metodo, canal), al_terminar=self._vendido,
                 al_fallar=self._fallo_venta, widget=self)

    def _restaurar_boton(self):
        self.boton_cobrar.setText('Cobrar   (F12)')
        self.boton_cobrar.setEnabled(bool(self.carrito))

    def _vendido(self, venta):
        self._restaurar_boton()
        self.limpiar()
        self.avisar('Venta #{} registrada · {}'.format(venta['id'], formato.dinero(venta['total'])))
        self.cargar_productos()
        self._enfocar_busqueda()

    def _fallo_venta(self, error):
        self._restaurar_boton()
        if self.ventana.sesion_caducada(error):
            return
        mostrar_error(self, error, 'No se registró la venta')
        self.cargar_productos()
