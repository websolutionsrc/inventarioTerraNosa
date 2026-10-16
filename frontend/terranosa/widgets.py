"""Piezas de interfaz que se repiten en todas las pantallas."""
from PyQt5.QtCore import QAbstractTableModel, QModelIndex, QSize, QSortFilterProxyModel, Qt, QTimer
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                             QPushButton, QSizePolicy, QTableView, QVBoxLayout, QWidget)

from . import tema


def refrescar_estilo(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def boton(texto, icono=None, tipo=None, grande=False, color_icono=None):
    b = QPushButton(texto)
    b.setCursor(Qt.PointingHandCursor)
    if tipo:
        b.setProperty('tipo', tipo)
    if grande:
        b.setProperty('grande', True)
    if icono:
        color = color_icono or {'primario': 'white', 'exito': 'white', 'peligro': tema.ROJO,
                                'plano': tema.CELESTE_OSCURO}.get(tipo, tema.TEXTO)
        tam = 20 if grande else 16
        b.setIcon(tema.icono(icono, color, tam))
        b.setIconSize(QSize(tam, tam))
    return b


def etiqueta(texto='', rol=None, ajustar=False):
    l = QLabel(texto)
    if rol:
        l.setProperty('rol', rol)
    if ajustar:
        l.setWordWrap(True)
    return l


class Tarjeta(QFrame):
    """Recuadro blanco con borde redondeado."""

    def __init__(self, margen=16, parent=None):
        super(Tarjeta, self).__init__(parent)
        self.setObjectName('tarjeta')
        self.capa = QVBoxLayout(self)
        self.capa.setContentsMargins(margen, margen, margen, margen)
        self.capa.setSpacing(10)


class TarjetaCifra(Tarjeta):
    """Tarjeta con un dato grande: 'Total del día  $ 116,00'."""

    def __init__(self, titulo, valor='—', detalle='', parent=None):
        super(TarjetaCifra, self).__init__(14, parent)
        self.capa.setSpacing(2)
        self.titulo = etiqueta(titulo.upper(), 'etiqueta')
        self.valor = etiqueta(valor, 'cifra')
        self.detalle = etiqueta(detalle or ' ', 'subtitulo')
        for w in (self.titulo, self.valor, self.detalle):
            self.capa.addWidget(w)

    def poner(self, valor, detalle=None):
        self.valor.setText(valor)
        if detalle is not None:
            self.detalle.setText(detalle or ' ')  # siempre ocupa su línea: las tarjetas quedan alineadas


class EtiquetaRecortada(QLabel):
    """Etiqueta de una línea que termina en «…» si no cabe (el texto completo va en el consejo)."""

    def __init__(self, texto='', parent=None):
        super(EtiquetaRecortada, self).__init__(texto, parent)
        self._texto = texto
        self.setToolTip(texto)
        self.setMinimumWidth(40)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def paintEvent(self, evento):
        p = QPainter(self)
        p.setPen(self.palette().color(self.foregroundRole()))
        p.setFont(self.font())
        texto = self.fontMetrics().elidedText(self._texto, Qt.ElideRight, self.width())
        p.drawText(self.rect(), int(Qt.AlignLeft | Qt.AlignVCenter), texto)
        p.end()


class Cabecera(QWidget):
    """Título de la pantalla con subtítulo y botones a la derecha."""

    def __init__(self, titulo, subtitulo='', parent=None):
        super(Cabecera, self).__init__(parent)
        capa = QHBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        textos = QVBoxLayout()
        textos.setSpacing(0)
        self.titulo = etiqueta(titulo, 'titulo')
        self.subtitulo = etiqueta(subtitulo, 'subtitulo')
        textos.addWidget(self.titulo)
        textos.addWidget(self.subtitulo)
        capa.addLayout(textos)
        capa.addStretch()
        self.botones = QHBoxLayout()
        self.botones.setSpacing(8)
        capa.addLayout(self.botones)

    def agregar(self, widget):
        self.botones.addWidget(widget)
        return widget


class Aviso(QLabel):
    """Mensaje de confirmación o error arriba del contenido, que se oculta solo."""

    def __init__(self, parent=None):
        super(Aviso, self).__init__(parent)
        self.setObjectName('aviso')
        self.setWordWrap(True)
        self.hide()
        self._temporizador = QTimer(self)
        self._temporizador.setSingleShot(True)
        self._temporizador.timeout.connect(self.hide)

    def mostrar(self, texto, tipo='exito', segundos=6):
        self.setProperty('tipo', tipo)
        refrescar_estilo(self)
        self.setText(texto)
        self.show()
        self._temporizador.start(int(segundos * 1000))

    def mousePressEvent(self, evento):
        self.hide()


# --- Tablas ---------------------------------------------------------------------------

ORDEN = Qt.UserRole
BUSQUEDA = Qt.UserRole + 1
FILA = Qt.UserRole + 2


class Columna(object):
    def __init__(self, titulo, valor, orden=None, alinear='izq', ancho=None, estirar=False, color=None):
        """
        valor: función fila -> texto. orden: función fila -> valor para ordenar (por defecto, el texto).
        color: función fila -> color del texto (o None).
        """
        self.titulo = titulo
        self.valor = valor
        self.orden = orden
        self.alinear = {'izq': Qt.AlignLeft, 'der': Qt.AlignRight, 'centro': Qt.AlignHCenter}[alinear] | Qt.AlignVCenter
        self.ancho = ancho
        self.estirar = estirar
        self.color = color


class ModeloTabla(QAbstractTableModel):
    def __init__(self, columnas, fondo=None, consejo=None, buscar_tambien=None, parent=None):
        """
        fondo: función fila -> color de fondo (o None). consejo: función fila -> texto emergente.
        buscar_tambien: función fila -> texto que también encuentra la búsqueda aunque no sea una columna.
        """
        super(ModeloTabla, self).__init__(parent)
        self.columnas = columnas
        self.filas = []
        self.fondo = fondo
        self.consejo = consejo
        self.buscar_tambien = buscar_tambien

    def poner_filas(self, filas):
        self.beginResetModel()
        self.filas = list(filas)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.filas)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columnas)

    def headerData(self, seccion, orientacion, rol=Qt.DisplayRole):
        if orientacion == Qt.Horizontal:
            if rol == Qt.DisplayRole:
                return self.columnas[seccion].titulo
            if rol == Qt.TextAlignmentRole:
                return int(self.columnas[seccion].alinear)
        return None

    def data(self, indice, rol=Qt.DisplayRole):
        if not indice.isValid():
            return None
        fila = self.filas[indice.row()]
        col = self.columnas[indice.column()]
        if rol == Qt.DisplayRole:
            return col.valor(fila)
        if rol == ORDEN:
            return col.orden(fila) if col.orden else col.valor(fila)
        if rol == Qt.TextAlignmentRole:
            return int(col.alinear)
        if rol == Qt.ForegroundRole and col.color:
            c = col.color(fila)
            return QColor(c) if c else None
        if rol == Qt.BackgroundRole and self.fondo:
            c = self.fondo(fila)
            return QColor(c) if c else None
        if rol == Qt.ToolTipRole and self.consejo:
            return self.consejo(fila)
        if rol == BUSQUEDA:
            textos = [str(c.valor(fila)) for c in self.columnas]
            if self.buscar_tambien:
                textos.append(str(self.buscar_tambien(fila)))
            return ' '.join(textos).lower()
        if rol == FILA:
            return fila
        return None


class FiltroTabla(QSortFilterProxyModel):
    """Busca todas las palabras escritas en cualquier columna, sin importar mayúsculas."""

    def __init__(self, parent=None):
        super(FiltroTabla, self).__init__(parent)
        self.palabras = []
        self.condicion = None  # función fila -> bool, filtro adicional
        self.setSortRole(ORDEN)

    def buscar(self, texto):
        self.palabras = [p for p in texto.lower().split() if p]
        self.invalidateFilter()

    def poner_condicion(self, condicion):
        self.condicion = condicion
        self.invalidateFilter()

    def filterAcceptsRow(self, fila, padre):
        modelo = self.sourceModel()
        indice = modelo.index(fila, 0, padre)
        if self.condicion and not self.condicion(modelo.data(indice, FILA)):
            return False
        texto = modelo.data(indice, BUSQUEDA) or ''
        return all(p in texto for p in self.palabras)

    def lessThan(self, a, b):
        va, vb = a.data(ORDEN), b.data(ORDEN)
        try:
            return va < vb
        except TypeError:
            return str(va) < str(vb)


class Tabla(QTableView):
    """Tabla de solo lectura con selección por filas y un texto cuando está vacía."""

    def __init__(self, columnas, fondo=None, consejo=None, vacio='No hay datos.', ordenable=True,
                 buscar_tambien=None, parent=None):
        super(Tabla, self).__init__(parent)
        self.modelo = ModeloTabla(columnas, fondo, consejo, buscar_tambien, self)
        self.filtro = FiltroTabla(self)
        self.filtro.setSourceModel(self.modelo)
        self.setModel(self.filtro)
        self.texto_vacio = vacio
        self.cargando = False

        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setSortingEnabled(ordenable)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(34)
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        cab = self.horizontalHeader()
        for i, col in enumerate(columnas):
            if col.estirar:
                cab.setSectionResizeMode(i, QHeaderView.Stretch)
            elif col.ancho:
                cab.setSectionResizeMode(i, QHeaderView.Interactive)
                self.setColumnWidth(i, col.ancho)
            else:
                cab.setSectionResizeMode(i, QHeaderView.ResizeToContents)

    def poner_filas(self, filas, mantener_seleccion=True):
        anterior = self.fila_seleccionada() if mantener_seleccion else None
        self.cargando = False
        self.modelo.poner_filas(filas)
        if anterior is not None and 'id' in anterior:
            self.seleccionar_id(anterior['id'])
        self.viewport().update()

    def poner_cargando(self):
        self.cargando = True
        self.viewport().update()

    def fila_seleccionada(self):
        indices = self.selectionModel().selectedRows()
        return indices[0].data(FILA) if indices else None

    def seleccionar_id(self, id_):
        for r in range(self.filtro.rowCount()):
            fila = self.filtro.index(r, 0).data(FILA)
            if fila and fila.get('id') == id_:
                self.selectRow(r)
                return True
        return False

    def filas_visibles(self):
        return [self.filtro.index(r, 0).data(FILA) for r in range(self.filtro.rowCount())]

    def paintEvent(self, evento):
        super(Tabla, self).paintEvent(evento)
        if self.filtro.rowCount() == 0:
            p = QPainter(self.viewport())
            p.setPen(QColor(tema.TEXTO_SUAVE))
            texto = 'Cargando…' if self.cargando else (
                'Ningún resultado para la búsqueda.' if self.modelo.rowCount() else self.texto_vacio)
            p.drawText(self.viewport().rect().adjusted(20, 20, -20, -20), Qt.AlignCenter | Qt.TextWordWrap, texto)
            p.end()


# --- Diálogos rápidos ----------------------------------------------------------------

def confirmar(parent, titulo, texto, si='Sí', no='Cancelar', peligro=False):
    caja = QMessageBox(parent)
    caja.setWindowTitle(titulo)
    caja.setText(texto)
    caja.setIcon(QMessageBox.Warning if peligro else QMessageBox.Question)
    boton_si = caja.addButton(si, QMessageBox.AcceptRole)
    boton_no = caja.addButton(no, QMessageBox.RejectRole)
    boton_si.setProperty('tipo', 'peligro' if peligro else 'primario')
    caja.setDefaultButton(boton_no if peligro else boton_si)
    caja.exec_()
    return caja.clickedButton() is boton_si


def mostrar_error(parent, error, titulo='No se pudo completar'):
    caja = QMessageBox(parent)
    caja.setWindowTitle(titulo)
    caja.setIcon(QMessageBox.Warning)
    caja.setText(getattr(error, 'mensaje', None) or str(error))
    caja.addButton('Entendido', QMessageBox.AcceptRole)
    caja.exec_()
