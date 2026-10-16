"""Inventario (admin): productos, precios, entradas de mercancía y ajustes de stock."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLineEdit

from .. import formato, tema
from ..tareas import ejecutar
from ..widgets import Columna, Tabla, boton, confirmar, etiqueta
from .base import Pagina
from .dialogos import DialogoMovimientos, DialogoProducto, DialogoStock


def _fondo(p):
    if not p['activo']:
        return '#F1F3F6'
    return None


def _color_stock(p):
    if p['stock'] <= 0:
        return tema.ROJO
    if p['stock_bajo']:
        return tema.AMBAR
    return None


class PaginaInventario(Pagina):
    titulo = 'Inventario'
    icono = 'inventario'
    solo_admin = True

    def __init__(self, ventana):
        super(PaginaInventario, self).__init__(ventana, 'Productos, precios y stock')
        self.productos = []
        self._por_seleccionar = None
        refrescar = self.cabecera.agregar(boton('Actualizar', 'refrescar'))
        refrescar.clicked.connect(self.cargar)
        nuevo = self.cabecera.agregar(boton('Nuevo producto', 'mas', tipo='primario'))
        nuevo.clicked.connect(self.nuevo)

        filtros = QHBoxLayout()
        self.busqueda = QLineEdit()
        self.busqueda.setPlaceholderText('Buscar por nombre, tipo o proveedor…')
        self.busqueda.addAction(tema.icono('buscar', tema.TEXTO_SUAVE, 18), QLineEdit.LeadingPosition)
        self.busqueda.setClearButtonEnabled(True)
        self.busqueda.setMinimumHeight(36)
        self.busqueda.textChanged.connect(self._filtrar)
        self.solo_bajo = QCheckBox('Solo stock bajo')
        self.solo_bajo.toggled.connect(self._filtrar)
        self.inactivos = QCheckBox('Mostrar desactivados')
        self.inactivos.toggled.connect(self.cargar)
        self.contador = etiqueta('', 'subtitulo')
        filtros.addWidget(self.busqueda, 1)
        filtros.addSpacing(10)
        filtros.addWidget(self.solo_bajo)
        filtros.addWidget(self.inactivos)
        filtros.addSpacing(10)
        filtros.addWidget(self.contador)
        self.capa.addLayout(filtros)

        self.tabla = Tabla([
            Columna('Producto', lambda p: p['nombre'], estirar=True),
            Columna('Tipo', lambda p: p['tipo'], ancho=130),
            Columna('Proveedor', lambda p: p['proveedor'], ancho=130),
            Columna('Precio', lambda p: formato.dinero(p['precio']), orden=lambda p: float(p['precio']),
                    alinear='der', ancho=100),
            Columna('Stock', lambda p: str(p['stock']), orden=lambda p: p['stock'], alinear='der',
                    color=_color_stock),
            Columna('Mínimo', lambda p: str(p['stock_minimo']), orden=lambda p: p['stock_minimo'], alinear='der'),
            Columna('Estado', lambda p: 'Activo' if p['activo'] else 'Desactivado', ancho=100,
                    color=lambda p: None if p['activo'] else tema.TEXTO_SUAVE),
        ], fondo=_fondo, vacio='No hay productos. Crea el primero con «Nuevo producto».')
        self.tabla.sortByColumn(0, Qt.AscendingOrder)
        self.tabla.doubleClicked.connect(lambda _: self.editar())
        self.tabla.selectionModel().selectionChanged.connect(self._seleccion)
        self.capa.addWidget(self.tabla, 1)

        acciones = QHBoxLayout()
        self.b_editar = boton('Editar', 'editar')
        self.b_entrada = boton('Entrada de mercancía', 'entrada')
        self.b_ajuste = boton('Ajustar stock', 'ajuste')
        self.b_movimientos = boton('Entradas y ajustes', 'lista')
        self.b_estado = boton('Desactivar', 'quitar', tipo='peligro')
        self.b_editar.clicked.connect(self.editar)
        self.b_entrada.clicked.connect(lambda: self.mover_stock('entrada'))
        self.b_ajuste.clicked.connect(lambda: self.mover_stock('ajuste'))
        self.b_movimientos.clicked.connect(self.ver_movimientos)
        self.b_estado.clicked.connect(self.cambiar_estado)
        for b in (self.b_editar, self.b_entrada, self.b_ajuste, self.b_movimientos):
            acciones.addWidget(b)
        acciones.addStretch()
        acciones.addWidget(self.b_estado)
        self.capa.addLayout(acciones)
        self._seleccion()

    def al_mostrar(self):
        self.cargar()

    def cargar(self):
        if not self.productos:
            self.tabla.poner_cargando()
        incluir = self.inactivos.isChecked()
        ejecutar(lambda: self.api.productos(incluir_inactivos=incluir), al_terminar=self._cargado,
                 al_fallar=self.error, widget=self)

    def _cargado(self, productos):
        self.productos = productos
        self.tabla.poner_filas(productos)
        self._filtrar()
        if self._por_seleccionar:
            self.tabla.seleccionar_id(self._por_seleccionar)
            self._por_seleccionar = None

    def _filtrar(self, *args):
        self.tabla.filtro.poner_condicion((lambda p: p['activo'] and p['stock_bajo']) if self.solo_bajo.isChecked()
                                          else None)
        self.tabla.filtro.buscar(self.busqueda.text())
        activos = [p for p in self.productos if p['activo']]
        bajos = sum(1 for p in activos if p['stock_bajo'])
        unidades = sum(p['stock'] for p in activos)
        self.contador.setText('{} productos · {} unidades · {} con stock bajo'.format(len(activos), unidades, bajos))
        self._seleccion()

    def _seleccion(self, *args):
        p = self.tabla.fila_seleccionada()
        for b in (self.b_editar, self.b_movimientos, self.b_estado):
            b.setEnabled(p is not None)
        for b in (self.b_entrada, self.b_ajuste):
            b.setEnabled(bool(p and p['activo']))
        if p:
            activo = p['activo']
            self.b_estado.setText('Desactivar' if activo else 'Reactivar')
            self.b_estado.setProperty('tipo', 'peligro' if activo else None)
            self.b_estado.setIcon(tema.icono('quitar' if activo else 'activar', tema.ROJO if activo else tema.TEXTO,
                                             16))
            self.b_estado.style().unpolish(self.b_estado)
            self.b_estado.style().polish(self.b_estado)

    def _listas(self):
        return [p['tipo'] for p in self.productos], [p['proveedor'] for p in self.productos]

    def nuevo(self):
        tipos, proveedores = self._listas()
        d = DialogoProducto(self, self.api, tipos=tipos, proveedores=proveedores)
        if d.exec_() == QDialog.Accepted:
            self.avisar('Producto «{}» creado.'.format(d.resultado['nombre']))
            self._por_seleccionar = d.resultado['id']
            self.cargar()

    def editar(self):
        p = self.tabla.fila_seleccionada()
        if not p:
            return
        tipos, proveedores = self._listas()
        d = DialogoProducto(self, self.api, p, tipos, proveedores)
        if d.exec_() == QDialog.Accepted:
            self.avisar('Cambios guardados en «{}».'.format(d.resultado['nombre']))
            self.cargar()

    def mover_stock(self, tipo):
        p = self.tabla.fila_seleccionada()
        if not p:
            return
        d = DialogoStock(self, self.api, p, tipo)
        if d.exec_() == QDialog.Accepted:
            m = d.resultado
            self.avisar('{} de «{}»: {:+d}. Stock actual: {}.'.format(
                'Entrada' if tipo == 'entrada' else 'Ajuste', p['nombre'], m['cantidad'], m['stock_resultante']))
            self.cargar()

    def ver_movimientos(self):
        p = self.tabla.fila_seleccionada()
        if p:
            DialogoMovimientos(self, self.api, p).exec_()

    def cambiar_estado(self):
        p = self.tabla.fila_seleccionada()
        if not p:
            return
        if p['activo']:
            if not confirmar(self, 'Desactivar producto',
                             '«{}» dejará de aparecer en Vender. Sus ventas y movimientos se conservan '
                             'y puedes reactivarlo cuando quieras.'.format(p['nombre']), si='Desactivar',
                             peligro=True):
                return
            tarea, texto = (lambda: self.api.desactivar_producto(p['id'])), '«{}» desactivado.'
        else:
            tarea, texto = (lambda: self.api.reactivar_producto(p['id'])), '«{}» reactivado.'
        ejecutar(tarea, al_terminar=lambda _: (self.avisar(texto.format(p['nombre'])), self.cargar()),
                 al_fallar=self.error, widget=self)
