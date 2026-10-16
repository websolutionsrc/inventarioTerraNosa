"""Ventas del día: totales para cuadrar caja y anulación de ventas con error."""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QDialog, QHBoxLayout

from .. import formato
from ..tareas import ejecutar
from ..widgets import Columna, Tabla, TarjetaCifra, boton
from .base import Pagina
from .detalle_venta import DetalleVenta
from .dialogos import DialogoAnular
from .tasas import en_bolivares


class PaginaVentasHoy(Pagina):
    titulo = 'Ventas de hoy'
    icono = 'ventas'

    def __init__(self, ventana):
        super(PaginaVentasHoy, self).__init__(ventana)
        self._total_dia = 0
        ventana.tasas_cambiadas.connect(self._pintar_total_bs)
        refrescar = self.cabecera.agregar(boton('Actualizar', 'refrescar'))
        refrescar.clicked.connect(self.cargar)

        cifras = QHBoxLayout()
        cifras.setSpacing(14)
        self.cifra_total = TarjetaCifra('Total del día', detalle=' ')
        self.cifra_ventas = TarjetaCifra('Ventas', detalle=' ')
        self.cifra_metodos = TarjetaCifra('Por método de pago', '', ' ')
        self.cifra_metodos.valor.setProperty('rol', 'subtitulo')
        self.cifra_metodos.valor.setWordWrap(True)
        cifras.addWidget(self.cifra_total, 1)
        cifras.addWidget(self.cifra_ventas, 1)
        cifras.addWidget(self.cifra_metodos, 2)
        self.capa.addLayout(cifras)

        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(16)
        self.tabla = Tabla([
            Columna('Hora', lambda v: formato.hora(v['fecha']), orden=lambda v: v['fecha']),
            Columna('Nº', lambda v: str(v['id']), orden=lambda v: v['id'], alinear='der'),
            Columna('Productos', lambda v: formato.resumen_lineas(v['lineas']), estirar=True),
            Columna('Pago', lambda v: v['metodo_pago_nombre']),
            Columna('Total', lambda v: formato.dinero(v['total']), orden=lambda v: float(v['total']),
                    alinear='der'),
        ], vacio='Todavía no hay ventas hoy.')
        self.tabla.sortByColumn(0, Qt.DescendingOrder)  # más recientes arriba
        self.tabla.selectionModel().selectionChanged.connect(self._seleccion)
        self.detalle = DetalleVenta()
        self.detalle.anular.connect(lambda v: self.anular(v, corregir=False))
        self.detalle.corregir.connect(lambda v: self.anular(v, corregir=True))
        cuerpo.addWidget(self.tabla, 2)
        cuerpo.addWidget(self.detalle, 1)
        self.capa.addLayout(cuerpo, 1)

        # Se actualiza sola cada minuto mientras está a la vista
        self._reloj = QTimer(self)
        self._reloj.setInterval(60 * 1000)
        self._reloj.timeout.connect(lambda: self.isVisible() and self.cargar())
        self._reloj.start()

    def al_mostrar(self):
        self.cabecera.subtitulo.setText(formato.fecha_larga(formato.hoy(self.api)).capitalize())
        self.cargar()

    def cargar(self):
        if not self.tabla.modelo.rowCount():
            self.tabla.poner_cargando()
        filtros = {'estado': 'activas'}  # las anuladas solo se ven en el Historial del admin
        api = self.api
        ejecutar(lambda: (api.ventas(**filtros), api.resumen_ventas(**filtros), api.config()),
                 al_terminar=self._cargado, al_fallar=self.error, widget=self)

    def _cargado(self, datos):
        ventas, resumen, _ = datos
        self.tabla.poner_filas(ventas)
        self._seleccion()
        self._total_dia = resumen['total']
        self._pintar_total_bs()
        self.cifra_ventas.poner(str(resumen['ventas']), '{} producto{} vendido{}'.format(
            *self._unidades(ventas)))
        metodos = ['{}: {}'.format(m['nombre'], formato.dinero(m['total'])) for m in resumen['por_metodo_pago']]
        self.cifra_metodos.poner('    '.join(metodos) or 'Sin ventas todavía', '')

    def _pintar_total_bs(self, *args):
        bs = en_bolivares(self._total_dia, self.ventana.tasas)
        self.cifra_total.poner(formato.dinero(self._total_dia), bs or 'Sin contar las anuladas')

    @staticmethod
    def _unidades(ventas):
        n = sum(l['cantidad'] for v in ventas for l in v['lineas'])
        s = '' if n == 1 else 's'
        return n, s, s

    def _seleccion(self, *args):
        self.detalle.mostrar(self.tabla.fila_seleccionada())

    def anular(self, venta, corregir):
        dialogo = DialogoAnular(self, self.api, venta, corregir)
        if dialogo.exec_() != QDialog.Accepted:
            return
        self.avisar('Venta #{} anulada. Los productos volvieron al inventario.'.format(venta['id']))
        self.detalle.mostrar(None)
        self.cargar()
        if corregir:
            self.ventana.corregir_venta(venta)
