from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from .. import formato, tema
from ..widgets import Columna, Tabla, Tarjeta, boton, etiqueta


class DetalleVenta(Tarjeta):
    """Panel con el detalle de la venta seleccionada y los botones para anularla."""
    anular = pyqtSignal(dict)
    corregir = pyqtSignal(dict)

    def __init__(self, parent=None):
        super(DetalleVenta, self).__init__(18, parent)
        self.setMinimumWidth(330)
        self.venta = None

        self.vacio = etiqueta('Selecciona una venta para ver el detalle.', 'subtitulo')
        self.vacio.setAlignment(Qt.AlignCenter)
        self.capa.addWidget(self.vacio, 1)

        self.titulo = etiqueta('', 'seccion')
        self.datos = etiqueta('', 'subtitulo', ajustar=True)
        self.estado = etiqueta('', 'chipRojo', ajustar=True)
        self.estado.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.lineas = Tabla([
            Columna('Producto', lambda l: l['producto_nombre'], estirar=True),
            Columna('Cant.', lambda l: str(l['cantidad']), alinear='der'),
            Columna('Subtotal', lambda l: formato.dinero(l['subtotal']), alinear='der'),
        ], consejo=lambda l: '{} × {} = {}'.format(l['cantidad'], formato.dinero(l['precio_unitario']),
                                                   formato.dinero(l['subtotal'])), ordenable=False)
        self.lineas.setMinimumHeight(110)
        self.lineas.setSelectionMode(Tabla.NoSelection)
        self.lineas.setFocusPolicy(Qt.NoFocus)

        fila_total = QHBoxLayout()
        fila_total.addStretch()
        fila_total.addWidget(etiqueta('TOTAL', 'etiqueta'))
        self.total = etiqueta('', 'cifra')
        fila_total.addWidget(self.total)

        self.botones = QHBoxLayout()
        self.boton_corregir = boton('Corregir', 'editar')
        self.boton_corregir.setToolTip('Anula la venta y carga sus productos en «Vender» para cobrarla bien')
        self.boton_anular = boton('Anular venta', 'anular', tipo='peligro')
        self.boton_corregir.clicked.connect(lambda: self.corregir.emit(self.venta))
        self.boton_anular.clicked.connect(lambda: self.anular.emit(self.venta))
        self.botones.addWidget(self.boton_corregir)
        self.botones.addStretch()
        self.botones.addWidget(self.boton_anular)

        self.contenido = QWidget()
        capa = QVBoxLayout(self.contenido)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(10)
        for w in (self.titulo, self.datos, self.estado, self.lineas):
            capa.addWidget(w, 1 if w is self.lineas else 0)
        capa.addLayout(fila_total)
        capa.addLayout(self.botones)
        # En pantallas bajas el detalle se desplaza en vez de recortarse
        self.desplazable = QScrollArea()
        self.desplazable.setWidget(self.contenido)
        self.desplazable.setWidgetResizable(True)
        self.desplazable.setFrameShape(QFrame.NoFrame)
        self.desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.desplazable.setStyleSheet('QScrollArea, QScrollArea > QWidget > QWidget { background: white; }')
        self.capa.addWidget(self.desplazable, 1)
        self.mostrar(None)

    def mostrar(self, venta):
        self.venta = venta
        hay = venta is not None
        self.vacio.setVisible(not hay)
        self.desplazable.setVisible(hay)
        if not hay:
            return
        self.titulo.setText('Venta #{}'.format(venta['id']))
        self.datos.setText('{}\nVendió {}\n{}  ·  {}'.format(
            formato.fecha_y_hora(venta['fecha']), venta['usuario'],
            venta['metodo_pago_nombre'], venta['canal_nombre']))
        anulada = venta.get('anulada')
        if anulada:
            self.estado.setText('ANULADA por {} el {}\nMotivo: {}'.format(
                venta['anulada_por'] or '—', formato.fecha_y_hora(venta['anulada_en']), venta['motivo_anulacion']))
        self.estado.setVisible(bool(anulada))
        self.lineas.poner_filas(venta['lineas'], mantener_seleccion=False)
        self.total.setText(formato.dinero(venta['total']))
        self.total.setStyleSheet('color: {}; text-decoration: {};'.format(
            tema.TEXTO_SUAVE if anulada else tema.MARINO, 'line-through' if anulada else 'none'))
        self.boton_anular.setVisible(not anulada)
        self.boton_corregir.setVisible(not anulada)
