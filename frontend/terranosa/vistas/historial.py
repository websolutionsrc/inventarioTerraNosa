"""Historial (admin): todas las ventas por fechas, con las anuladas y quién las anuló."""
import csv
from datetime import timedelta

from PyQt5.QtCore import QDate, Qt, QTimer
from PyQt5.QtWidgets import QComboBox, QDateEdit, QDialog, QFileDialog, QHBoxLayout

from .. import formato, tema
from ..tareas import ejecutar
from ..widgets import Columna, Tabla, Tarjeta, TarjetaCifra, boton, etiqueta, mostrar_error
from .base import Pagina
from .detalle_venta import DetalleVenta
from .dialogos import DialogoAnular


def _qdate(d):
    return QDate(d.year, d.month, d.day)


class PaginaHistorial(Pagina):
    titulo = 'Historial'
    icono = 'historial'
    solo_admin = True

    def __init__(self, ventana):
        super(PaginaHistorial, self).__init__(ventana, 'Todas las ventas, también las anuladas')
        self.ventas = []
        self._cargados_usuarios = False
        refrescar = self.cabecera.agregar(boton('Actualizar', 'refrescar'))
        refrescar.clicked.connect(self.cargar)
        exportar = self.cabecera.agregar(boton('Exportar para Excel', 'descargar'))
        exportar.clicked.connect(self.exportar)

        # Filtros
        filtros = Tarjeta(12)
        fila = QHBoxLayout()
        fila.setSpacing(8)
        hoy = formato.hoy(self.api)
        self.desde = self._fecha(hoy - timedelta(days=6))
        self.hasta = self._fecha(hoy)
        fila.addWidget(etiqueta('Desde'))
        fila.addWidget(self.desde)
        fila.addWidget(etiqueta('hasta'))
        fila.addWidget(self.hasta)
        for texto, dias in (('Hoy', 0), ('7 días', 6), ('30 días', 29)):
            b = boton(texto, tipo='plano')
            b.clicked.connect(lambda _=False, d=dias: self._rango(d))
            fila.addWidget(b)
        b = boton('Este mes', tipo='plano')
        b.clicked.connect(self._este_mes)
        fila.addWidget(b)
        fila.addStretch()
        filtros.capa.addLayout(fila)
        fila = QHBoxLayout()
        fila.setSpacing(8)
        fila.addWidget(etiqueta('Mostrar'))
        self.estado = self._combo([('Todas', ''), ('Solo activas', 'activas'), ('Solo anuladas', 'anuladas')])
        opciones = self.api.opciones or {}
        self.metodo = self._combo([('Todos los pagos', '')] + [(m['nombre'], m['id'])
                                                               for m in opciones.get('metodos_pago', [])])
        self.canal = self._combo([('Todos los canales', '')] + [(c['nombre'], c['id'])
                                                                for c in opciones.get('canales', [])])
        self.vendedor = self._combo([('Todos los usuarios', '')])
        for w in (self.estado, self.metodo, self.canal, self.vendedor):
            w.setSizeAdjustPolicy(QComboBox.AdjustToContents)
            w.setMinimumWidth(150)
            fila.addWidget(w)
        fila.addStretch()
        filtros.capa.addLayout(fila)
        self.capa.addWidget(filtros)

        cifras = QHBoxLayout()
        cifras.setSpacing(14)
        self.c_total = TarjetaCifra('Total vendido', detalle=' ')
        self.c_ventas = TarjetaCifra('Ventas', detalle=' ')
        self.c_media = TarjetaCifra('Venta media', detalle=' ')
        self.c_anuladas = TarjetaCifra('Anuladas', detalle=' ')
        for c in (self.c_total, self.c_ventas, self.c_media, self.c_anuladas):
            cifras.addWidget(c, 1)
        self.capa.addLayout(cifras)

        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(16)
        self.tabla = Tabla([
            Columna('Fecha', lambda v: formato.fecha_y_hora(v['fecha'], corta=True), orden=lambda v: v['fecha']),
            Columna('Nº', lambda v: str(v['id']), orden=lambda v: v['id'], alinear='der'),
            Columna('Productos', lambda v: formato.resumen_lineas(v['lineas'], 2), estirar=True),
            Columna('Vendió', lambda v: v['usuario']),
            Columna('Total', lambda v: formato.dinero(v['total']), orden=lambda v: float(v['total']),
                    alinear='der', color=lambda v: tema.TEXTO_SUAVE if v['anulada'] else None),
            Columna('Estado', lambda v: 'Anulada' if v['anulada'] else 'Activa',
                    color=lambda v: tema.ROJO if v['anulada'] else tema.VERDE),
        ], fondo=lambda v: tema.ROJO_CLARO if v['anulada'] else None,
            consejo=lambda v: 'Anulada por {}: {}'.format(v['anulada_por'], v['motivo_anulacion'])
            if v['anulada'] else None,
            vacio='No hay ventas con estos filtros.')
        self.tabla.sortByColumn(0, Qt.DescendingOrder)
        self.tabla.selectionModel().selectionChanged.connect(
            lambda *a: self.detalle.mostrar(self.tabla.fila_seleccionada()))
        self.detalle = DetalleVenta()
        self.detalle.anular.connect(lambda v: self.anular(v, False))
        self.detalle.corregir.connect(lambda v: self.anular(v, True))
        cuerpo.addWidget(self.tabla, 2)
        cuerpo.addWidget(self.detalle, 1)
        self.capa.addLayout(cuerpo, 1)

        # Recarga al cambiar un filtro (con una pequeña espera por si se cambian varios)
        self._espera = QTimer(self)
        self._espera.setSingleShot(True)
        self._espera.setInterval(300)
        self._espera.timeout.connect(self.cargar)
        for w in (self.desde, self.hasta):
            w.dateChanged.connect(lambda *_: self._espera.start())
        for w in (self.estado, self.metodo, self.canal, self.vendedor):
            w.currentIndexChanged.connect(lambda *_: self._espera.start())

    def _fecha(self, d):
        w = QDateEdit(_qdate(d))
        w.setCalendarPopup(True)
        w.setDisplayFormat('dd/MM/yyyy')
        w.setMinimumWidth(130)
        return w

    def _combo(self, opciones):
        c = QComboBox()
        for texto, valor in opciones:
            c.addItem(texto, valor)
        return c

    def _rango(self, dias):
        hoy = formato.hoy(self.api)
        self.hasta.setDate(_qdate(hoy))
        self.desde.setDate(_qdate(hoy - timedelta(days=dias)))

    def _este_mes(self):
        hoy = formato.hoy(self.api)
        self.hasta.setDate(_qdate(hoy))
        self.desde.setDate(_qdate(hoy.replace(day=1)))

    def al_mostrar(self):
        if not self._cargados_usuarios:
            ejecutar(self.api.usuarios, al_terminar=self._usuarios, widget=self)
        self.cargar()

    def _usuarios(self, usuarios):
        self._cargados_usuarios = True
        self.vendedor.blockSignals(True)
        for u in usuarios:
            self.vendedor.addItem(u['username'], u['username'])
        self.vendedor.blockSignals(False)

    def _filtros(self):
        if self.hasta.date() < self.desde.date():
            self.hasta.setDate(self.desde.date())
        return {
            'desde': self.desde.date().toString('yyyy-MM-dd'),
            'hasta': self.hasta.date().toString('yyyy-MM-dd'),
            'estado': self.estado.currentData(),
            'metodo_pago': self.metodo.currentData(),
            'canal': self.canal.currentData(),
            'usuario': self.vendedor.currentData(),
        }

    def cargar(self):
        self.tabla.poner_cargando()
        filtros, api = self._filtros(), self.api
        ejecutar(lambda: (api.ventas(**filtros), api.resumen_ventas(**filtros)), al_terminar=self._cargado,
                 al_fallar=self.error, widget=self)

    def _cargado(self, datos):
        self.ventas, resumen = datos
        self.tabla.poner_filas(self.ventas)
        self.detalle.mostrar(self.tabla.fila_seleccionada())
        n = resumen['ventas']
        self.c_total.poner(formato.dinero(resumen['total']), self._periodo())
        unidades = sum(l['cantidad'] for v in self.ventas if not v['anulada'] for l in v['lineas'])
        self.c_ventas.poner(str(n), '{} productos'.format(unidades))
        media = formato.decimal(resumen['total']) / n if n else 0
        self.c_media.poner(formato.dinero(media), '')
        anuladas = resumen.get('anuladas') or {'ventas': 0, 'total': 0}
        self.c_anuladas.poner(str(anuladas['ventas']), formato.dinero(anuladas['total']) + ' sin contar')
        self.c_anuladas.valor.setStyleSheet('color: {};'.format(tema.ROJO if anuladas['ventas'] else tema.MARINO))

    def _periodo(self):
        d, h = self.desde.date().toString('dd/MM/yyyy'), self.hasta.date().toString('dd/MM/yyyy')
        return d if d == h else '{} – {}'.format(d, h)

    def anular(self, venta, corregir):
        if DialogoAnular(self, self.api, venta, corregir).exec_() != QDialog.Accepted:
            return
        self.avisar('Venta #{} anulada. Los productos volvieron al inventario.'.format(venta['id']))
        self.cargar()
        if corregir:
            self.ventana.corregir_venta(venta)

    def exportar(self):
        if not self.ventas:
            self.avisar('No hay ventas para exportar con estos filtros.', 'info')
            return
        f = self._filtros()
        nombre = 'ventas_{}_a_{}.csv'.format(f['desde'], f['hasta'])
        ruta, _ = QFileDialog.getSaveFileName(self, 'Exportar ventas', nombre, 'CSV para Excel (*.csv)')
        if not ruta:
            return
        try:
            # Una fila por producto vendido; separador ";" y coma decimal para Excel en español
            with open(ruta, 'w', newline='', encoding='utf-8-sig') as archivo:
                w = csv.writer(archivo, delimiter=';')
                w.writerow(['Fecha', 'Hora', 'Venta', 'Vendedor', 'Método de pago', 'Canal', 'Producto', 'Cantidad',
                            'Precio', 'Subtotal', 'Total venta', 'Tasa Bs/$', 'Tasa BCV', 'Total Bs', 'Estado',
                            'Anulada por', 'Motivo anulación'])
                for v in sorted(self.ventas, key=lambda v: v['fecha']):
                    for l in v['lineas']:
                        w.writerow([formato.fecha_corta(v['fecha']), formato.hora(v['fecha']), v['id'], v['usuario'],
                                    v['metodo_pago_nombre'], v['canal_nombre'], l['producto_nombre'], l['cantidad'],
                                    formato.numero(l['precio_unitario']), formato.numero(l['subtotal']),
                                    formato.numero(v['total']),
                                    formato.numero(v['tasa_cambio']) if v.get('tasa_cambio') else '',
                                    formato.numero(v['tasa_bcv']) if v.get('tasa_bcv') else '',
                                    formato.numero(v['total_bs']) if v.get('total_bs') else '',
                                    'Anulada' if v['anulada'] else 'Activa',
                                    v['anulada_por'] or '', v['motivo_anulacion']])
        except OSError as e:
            mostrar_error(self, e, 'No se pudo guardar el archivo')
            return
        self.avisar('Exportadas {} ventas a {}'.format(len(self.ventas), ruta))
