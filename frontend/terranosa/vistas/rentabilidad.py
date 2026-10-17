"""
Panel de rentabilidad (admin, con PIN de gerencia): cuánto se gana de verdad con cada compra
teniendo en cuenta la brecha cambiaria, explicado sin fórmulas.
"""
from datetime import date, timedelta

from PyQt5.QtCore import QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import (QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QLineEdit, QScrollArea,
                             QSplitter, QStackedWidget, QTabWidget, QVBoxLayout, QWidget)

from .. import formato, tema
from ..graficos import BarrasAgrupadas, BarrasHorizontales, Lineas, nombre_mes
from ..tareas import ejecutar
from ..widgets import Columna, Tabla, Tarjeta, TarjetaCifra, boton, etiqueta, mostrar_error
from .base import Pagina

ESTADOS = {'pendiente': 'Pendiente de pagar', 'pagado': 'Pagado', 'cerrado': 'Vendido y pagado'}
ESTADOS_CORTOS = {'pendiente': 'Por pagar', 'pagado': 'Pagado', 'cerrado': 'Cerrado'}  # en la tabla
MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
         'noviembre', 'diciembre']


def _d(valor):
    return formato.decimal(valor) if valor not in (None, '') else None


def _pct(valor, decimales=1):
    v = _d(valor)
    return '—' if v is None else '{} %'.format(formato.numero(v, decimales))


def _color(valor, objetivo):
    v = _d(valor)
    if v is None:
        return tema.TEXTO_SUAVE
    if v >= objetivo:
        return tema.VERDE
    if v >= objetivo - 10:
        return tema.AMBAR
    return tema.ROJO


def _dolares_eje(valor):
    return '{} $'.format(formato.numero(valor, 0))


def _fecha(iso):
    return '{}/{}/{}'.format(iso[8:10], iso[5:7], iso[:4]) if iso else '—'


class BarrasMargen(QWidget):
    """Dos barras: lo que se esperaba ganar (estimado) y lo que se ganó de verdad, con la línea del objetivo."""

    def __init__(self, parent=None):
        super(BarrasMargen, self).__init__(parent)
        self.setMinimumHeight(64)
        self.estimado = self.real = None
        self.objetivo = 40
        self.titulo_real = 'Real'

    def poner(self, estimado, real, objetivo, titulo_real='Real'):
        self.estimado, self.real = _d(estimado), _d(real)
        self.objetivo = float(objetivo)
        self.titulo_real = titulo_real
        self.update()

    def paintEvent(self, evento):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        filas = (('Esperabas (estimado)', self.estimado, QColor('#C6CFD9')),
                 (self.titulo_real, self.real, QColor(_color(self.real, self.objetivo))))
        ancho_texto = max(self.fontMetrics().width(f[0]) for f in filas) + 14  # el rótulo entero, sin recortar
        x0, ancho = ancho_texto, max(10, self.width() - ancho_texto - 60)
        for i, (texto, valor, color) in enumerate(filas):
            y = 6 + i * 28
            p.setPen(QColor(tema.TEXTO_SUAVE))
            p.drawText(QRectF(0, y, ancho_texto - 8, 20), Qt.AlignRight | Qt.AlignVCenter, texto)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor('#EEF1F4'))
            p.drawRoundedRect(QRectF(x0, y + 3, ancho, 14), 7, 7)
            if valor is not None:
                p.setBrush(color)
                p.drawRoundedRect(QRectF(x0, y + 3, ancho * max(0.0, min(float(valor), 100.0)) / 100.0, 14), 7, 7)
            p.setPen(QColor(tema.TEXTO))
            p.drawText(QRectF(x0 + ancho + 6, y, 54, 20), Qt.AlignLeft | Qt.AlignVCenter, _pct(valor, 0))
        # Línea del objetivo
        xo = x0 + ancho * self.objetivo / 100.0
        p.setPen(QColor(tema.MARINO))
        p.drawLine(int(xo), 4, int(xo), 58)
        p.end()


class FichaLote(Tarjeta):
    """Lo que pasó con un lote, contado de forma sencilla, y el detalle venta por venta."""

    def __init__(self, parent=None):
        super(FichaLote, self).__init__(18, parent)
        self.setMinimumWidth(400)
        self.vacio = etiqueta('Elige un lote para ver qué pasó con él.', 'subtitulo')
        self.vacio.setAlignment(Qt.AlignCenter)
        self.capa.addWidget(self.vacio, 1)

        self.contenido = QWidget()
        capa = QVBoxLayout(self.contenido)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(6)
        self.titulo = etiqueta('', 'seccion')
        self.subtitulo = etiqueta('', 'subtitulo', ajustar=True)
        self.titular = etiqueta('', ajustar=True)
        self.titular.setStyleSheet('font-size: 15pt; font-weight: 700;')
        self.esperabas = etiqueta('', 'subtitulo', ajustar=True)
        self.barras = BarrasMargen()
        self.explicacion = etiqueta('', ajustar=True)
        self.explicacion.setTextFormat(Qt.RichText)
        self.ventas = Tabla([
            Columna('Venta', lambda v: '#{}'.format(v['venta']), orden=lambda v: v['venta']),
            Columna('Fecha', lambda v: formato.fecha_corta(v['fecha'])[:5], orden=lambda v: v['fecha']),
            Columna('Cobro', lambda v: v['metodo_pago']),
            Columna('Tasa', lambda v: formato.numero(v['tasa']) if v.get('tasa') else '—', alinear='der'),
            Columna('Ganancia', lambda v: formato.dinero(v['ganancia']) if v.get('ganancia') else '—', alinear='der'),
            Columna('Margen', lambda v: _pct(v['margen']), alinear='der',
                    color=lambda v: _color(v['margen'], self.objetivo)),
        ], consejo=lambda v: '{} × {} · entraron {}'.format(
            v['cantidad'], formato.dinero(v['precio']), formato.bolivares(v['bs_entraron'])),
            vacio='Todavía no se ha vendido nada de este lote.', ordenable=False)
        self.ventas.setMinimumHeight(150)
        for w in (self.titulo, self.subtitulo, self.titular, self.esperabas, self.barras, self.explicacion):
            capa.addWidget(w)
        capa.addWidget(etiqueta('VENTA POR VENTA', 'etiqueta'))
        capa.addWidget(self.ventas, 1)
        desplazable = QScrollArea()
        desplazable.setWidget(self.contenido)
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.NoFrame)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        desplazable.setStyleSheet('QScrollArea, QScrollArea > QWidget > QWidget { background: white; }')
        self.desplazable = desplazable
        self.capa.addWidget(desplazable, 1)
        self.objetivo = 40
        self.mostrar(None)

    def mostrar(self, lote, objetivo=40):
        self.objetivo = float(objetivo)
        self.vacio.setVisible(lote is None)
        self.desplazable.setVisible(lote is not None)
        if not lote:
            return
        estado = lote['estado']
        self.titulo.setText(lote['producto_nombre'])
        self.subtitulo.setText('Compra #{} · {} · {} uds a {} · {}'.format(
            lote['compra'], _fecha(lote['fecha_compra']), lote['cantidad'],
            formato.bolivares(lote['costo_unitario']) if lote['forma_pago'] == 'bs_fijos'
            else formato.dinero(lote['costo_unitario']),
            ESTADOS.get(estado, estado) + (' (estimado si se pagase hoy)' if lote['estimado_pago'] else '')))
        real, estimado = _d(lote['margen_real']), _d(lote['margen_estimado'])
        if real is None:
            self.titular.setText('Aún no hay ventas de este lote')
            self.titular.setStyleSheet('font-size: 15pt; font-weight: 700; color: {};'.format(tema.TEXTO_SUAVE))
        else:
            self.titular.setText('De cada 100 $ vendidos te {} {}'.format(
                'quedarían' if lote['estimado_pago'] else 'quedaron', '{} $'.format(formato.numero(real, 0))))
            self.titular.setStyleSheet('font-size: 15pt; font-weight: 700; color: {};'.format(
                _color(real, self.objetivo)))
        self.esperabas.setText('Esperabas {} (solo costo y precio, sin tasas). Objetivo: {}.'.format(
            _pct(estimado, 0), _pct(self.objetivo, 0)))
        self.barras.poner(estimado, real, self.objetivo, 'Estimado si se pagase hoy' if lote['estimado_pago']
                          else 'Lo que pasó')

        partes = []
        tasa_media, tasa_pago = _d(lote['tasa_media_venta']), _d(lote['tasa_pago'])
        if tasa_media and tasa_pago:
            verbo = 'pagarías hoy' if lote['estimado_pago'] else 'pagaste'
            comparacion = 'más alta' if tasa_pago > tasa_media else 'más baja'
            partes.append('Vendiste a una tasa media de <b>{}</b> Bs/$ y {} al proveedor a <b>{}</b> Bs/$ '
                          '({} que la de venta).'.format(formato.numero(tasa_media), verbo, formato.numero(tasa_pago),
                                                         comparacion))
        costo_real, costo = _d(lote['costo_real_usd']), _d(lote['costo_usd'])
        if costo_real and costo:
            partes.append('Por eso cada unidad te costó de verdad <b>{}</b>, no {}.'.format(
                formato.dinero(costo_real), formato.dinero(costo)))
        if lote.get('mejor_venta') and lote['ventas_contadas'] > 1:
            partes.append('Mejor venta: #{} ({}) · peor: #{} ({}).'.format(
                lote['mejor_venta']['venta'], _pct(lote['mejor_venta']['margen']), lote['peor_venta']['venta'],
                _pct(lote['peor_venta']['margen'])))
        if lote['ventas_bajo_objetivo']:
            partes.append('<span style="color:{}">{} de {} ventas quedaron por debajo del objetivo.</span>'.format(
                tema.ROJO, lote['ventas_bajo_objetivo'], lote['ventas_contadas']))
        if lote['perdidas']:
            partes.append('Se perdieron o dañaron {} unidad{}: su costo ya está descontado.'.format(
                lote['perdidas'], '' if lote['perdidas'] == 1 else 'es'))
        if _d(lote['brecha']):
            partes.append('Medido a la tasa USDT del día de cada venta, la brecha se llevó {}.'.format(
                formato.dinero(lote['brecha'])))
        if lote.get('margen_previsto'):
            partes.append('Al comprar habías previsto un {} con la brecha.'.format(_pct(lote['margen_previsto'])))
        partes.append('Vendidas {} de {}{}.'.format(lote['vendidas'], lote['cantidad'],
                                                    ' · quedan {}'.format(lote['quedan']) if lote['quedan'] else ''))
        self.explicacion.setText('<br>'.join(partes))
        self.ventas.poner_filas(lote.get('ventas') or [], mantener_seleccion=False)


class PaginaRentabilidad(Pagina):
    titulo = 'Rentabilidad'
    icono = 'grafica'
    solo_admin = True

    def __init__(self, ventana):
        super(PaginaRentabilidad, self).__init__(ventana, 'Cuánto se gana de verdad, con la brecha incluida')
        self.objetivo = 40
        self.bloquear_b = self.cabecera.agregar(boton('Bloquear', 'candado'))
        self.bloquear_b.clicked.connect(self.bloquear)
        self.actualizar_b = self.cabecera.agregar(boton('Actualizar', 'refrescar'))
        self.actualizar_b.clicked.connect(self.cargar)

        self.pilas = QStackedWidget()
        self.pilas.addWidget(self._bloqueo())
        self.pilas.addWidget(self._panel())
        self.capa.addWidget(self.pilas, 1)

        self._reloj = QTimer(self)
        self._reloj.setInterval(20 * 1000)
        self._reloj.timeout.connect(self._vigilar_pin)
        self._reloj.start()

    # --- Bloqueo con PIN ---

    def _bloqueo(self):
        fondo = QWidget()
        capa = QVBoxLayout(fondo)
        capa.addStretch()
        fila = QHBoxLayout()
        fila.addStretch()
        tarjeta = Tarjeta(28)
        tarjeta.setFixedWidth(420)
        self.bloqueo_titulo = etiqueta('Panel protegido', 'seccion')
        self.bloqueo_texto = etiqueta('Aquí se ven costos y márgenes. Introduce el PIN de gerencia.', 'subtitulo',
                                      ajustar=True)
        self.pin = QLineEdit()
        self.pin.setEchoMode(QLineEdit.Password)
        self.pin.setMaxLength(8)
        self.pin.setMinimumHeight(38)
        self.pin.setPlaceholderText('PIN')
        self.pin2 = QLineEdit()
        self.pin2.setEchoMode(QLineEdit.Password)
        self.pin2.setMaxLength(8)
        self.pin2.setMinimumHeight(38)
        self.pin2.setPlaceholderText('Repite el PIN')
        self.pin_error = etiqueta('', 'error', ajustar=True)
        self.pin_error.hide()
        self.entrar_b = boton('Entrar', 'candado', tipo='primario', grande=True)
        self.entrar_b.clicked.connect(self._entrar)
        self.pin.returnPressed.connect(self._entrar)
        self.pin2.returnPressed.connect(self._entrar)
        for w in (self.bloqueo_titulo, self.bloqueo_texto, self.pin, self.pin2, self.pin_error, self.entrar_b):
            tarjeta.capa.addWidget(w)
        fila.addWidget(tarjeta)
        fila.addStretch()
        capa.addLayout(fila)
        capa.addStretch()
        self._pin_definido = True
        return fondo

    def _pintar_bloqueo(self, definido):
        self._pin_definido = definido
        self.pin.clear()
        self.pin2.clear()
        self.pin2.setVisible(not definido)
        if definido:
            self.bloqueo_titulo.setText('Panel protegido')
            self.bloqueo_texto.setText('Aquí se ven costos y márgenes. Introduce el PIN de gerencia.')
            self.entrar_b.setText('Entrar')
        else:
            self.bloqueo_titulo.setText('Crea el PIN de gerencia')
            self.bloqueo_texto.setText('Este panel muestra costos y márgenes. Elige un PIN de 4 a 8 números: se '
                                       'pedirá cada vez que se abra y caduca a los 15 minutos.')
            self.entrar_b.setText('Guardar PIN y entrar')
        self.pin.setFocus()

    def _entrar(self):
        pin = self.pin.text().strip()
        if not self._pin_definido:
            if pin != self.pin2.text().strip():
                return self._error_pin('Los dos PIN no coinciden.')
            tarea = lambda: self.api.definir_pin(pin)  # noqa: E731
        else:
            tarea = lambda: self.api.entrar_panel(pin)  # noqa: E731
        if not pin:
            return self._error_pin('Escribe el PIN.')
        self.entrar_b.setEnabled(False)
        ejecutar(tarea, al_terminar=lambda _: self._abierto(), al_fallar=self._fallo_pin, widget=self)

    def _error_pin(self, texto):
        self.pin_error.setText(texto)
        self.pin_error.setVisible(bool(texto))

    def _fallo_pin(self, error):
        self.entrar_b.setEnabled(True)
        if not self.ventana.sesion_caducada(error):
            self._error_pin(error.mensaje)
            self.pin.selectAll()

    def _abierto(self):
        self.entrar_b.setEnabled(True)
        self._error_pin('')
        self.pilas.setCurrentIndex(1)
        self.bloquear_b.setVisible(True)
        self.actualizar_b.setVisible(True)
        self.cargar()

    def bloquear(self):
        self.api.bloquear_panel()
        self._mostrar_bloqueo()

    def _mostrar_bloqueo(self):
        self.pilas.setCurrentIndex(0)
        self.bloquear_b.setVisible(False)
        self.actualizar_b.setVisible(False)
        ejecutar(self.api.estado_pin, al_terminar=lambda d: self._pintar_bloqueo(d['definido']),
                 al_fallar=self.error, widget=self)

    def _vigilar_pin(self):
        if self.pilas.currentIndex() == 1 and not self.api.panel_abierto:
            self.avisar('El acceso al panel caducó: vuelve a introducir el PIN.', 'info')
            self._mostrar_bloqueo()

    def al_mostrar(self):
        if self.api.panel_abierto:
            self._abierto()
        else:
            self._mostrar_bloqueo()

    # --- Panel ---

    def _panel(self):
        panel = QWidget()
        capa = QVBoxLayout(panel)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(12)

        filtros = QHBoxLayout()
        filtros.addWidget(etiqueta('Compras pendientes, si se pagasen hoy a'))
        self.escenario = QComboBox()
        for texto, valor in (('la tasa de su factura', 'factura'), ('la tasa USDT', 'usdt'), ('la tasa BCV', 'bcv'),
                             ('otra tasa', 'otra')):
            self.escenario.addItem(texto, valor)
        self.escenario.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.tasa_otra = QDoubleSpinBox()
        self.tasa_otra.setRange(1, 100000000)
        self.tasa_otra.setDecimals(2)
        self.tasa_otra.setSuffix(' Bs/$')
        self.tasa_otra.setValue(1000)
        self.tasa_otra.setMinimumWidth(140)
        self.tasa_otra.hide()
        self.escenario.currentIndexChanged.connect(self._cambio_escenario)
        self.tasa_otra.editingFinished.connect(self.cargar)
        filtros.addWidget(self.escenario)
        filtros.addWidget(self.tasa_otra)
        filtros.addStretch()
        filtros.addWidget(etiqueta('Margen objetivo'))
        self.margen_obj = QDoubleSpinBox()
        self.margen_obj.setRange(1, 95)
        self.margen_obj.setDecimals(0)
        self.margen_obj.setSuffix(' %')
        self.margen_obj.setMinimumWidth(90)
        self.margen_obj.editingFinished.connect(self._guardar_objetivo)
        filtros.addWidget(self.margen_obj)
        capa.addLayout(filtros)

        self.pestanas = QTabWidget()
        self.pestanas.setStyleSheet('QTabWidget::pane { border: none; } QTabBar::tab { padding: 8px 18px; }')
        self.pestanas.addTab(self._resumen(), 'Resumen')
        self.pestanas.addTab(self._lotes(), 'Lotes')
        self.pestanas.addTab(self._articulos(), 'Por artículo')
        self.pestanas.addTab(self._graficos(), 'Gráficos')
        capa.addWidget(self.pestanas, 1)
        return panel

    def _resumen(self):
        caja = QWidget()
        capa = QVBoxLayout(caja)
        capa.setContentsMargins(0, 8, 0, 0)
        capa.setSpacing(12)
        fila = QHBoxLayout()
        fila.addWidget(etiqueta('Periodo'))
        self.periodo = QComboBox()
        for texto in ('Este mes', 'Mes anterior', 'Últimos 30 días', 'Este año'):
            self.periodo.addItem(texto)
        self.periodo.currentIndexChanged.connect(lambda *_: self._cargar_resumen())
        fila.addWidget(self.periodo)
        fila.addStretch()
        capa.addLayout(fila)
        cifras = QHBoxLayout()
        cifras.setSpacing(14)
        self.c_cada100 = TarjetaCifra('De cada 100 $ vendidos', detalle=' ')
        self.c_ganancia = TarjetaCifra('Ganancia real', detalle=' ')
        self.c_brecha = TarjetaCifra('Se lo llevó la brecha', detalle=' ')
        self.c_pendiente = TarjetaCifra('Pendiente de pagar', detalle=' ')
        for c in (self.c_cada100, self.c_ganancia, self.c_brecha, self.c_pendiente):
            cifras.addWidget(c, 1)
        capa.addLayout(cifras)
        tarjeta = Tarjeta(20)
        self.texto_resumen = etiqueta('', ajustar=True)
        self.texto_resumen.setTextFormat(Qt.RichText)
        self.texto_resumen.setStyleSheet('font-size: 11pt;')
        tarjeta.capa.addWidget(self.texto_resumen)
        capa.addWidget(tarjeta)
        capa.addStretch()
        return caja

    def _lotes(self):
        caja = QWidget()
        capa = QHBoxLayout(caja)
        capa.setContentsMargins(0, 8, 0, 0)
        capa.setSpacing(16)
        self.tabla_lotes = Tabla([
            Columna('Artículo', lambda l: l['producto_nombre'], estirar=True),
            Columna('Estado', lambda l: ESTADOS_CORTOS.get(l['estado'], l['estado']),
                    color=lambda l: tema.AMBAR if l['estado'] == 'pendiente' else None),
            Columna('Estimado', lambda l: _pct(l['margen_estimado'], 0), alinear='der',
                    orden=lambda l: float(l['margen_estimado'] or 0)),
            Columna('Real', lambda l: _pct(l['margen_real'], 0), alinear='der',
                    orden=lambda l: float(l['margen_real'] or -999),
                    color=lambda l: _color(l['margen_real'], self.objetivo)),
        ], consejo=lambda l: 'Compra #{} · {} · vendidas {} de {}{}'.format(
            l['compra'], _fecha(l['fecha_compra']), l['vendidas'], l['cantidad'],
            ' · Real = estimado si se pagase hoy' if l['estimado_pago'] else ''),
            vacio='No hay compras registradas.')
        self.tabla_lotes.selectionModel().selectionChanged.connect(self._lote_elegido)
        self.ficha = FichaLote()
        division = QSplitter(Qt.Horizontal)  # se puede arrastrar para dar más sitio a uno u otro
        division.setChildrenCollapsible(False)
        division.setHandleWidth(16)
        division.addWidget(self.tabla_lotes)
        division.addWidget(self.ficha)
        division.setStretchFactor(0, 1)
        division.setStretchFactor(1, 1)
        division.setSizes([560, 520])  # que los nombres de los artículos se lean enteros
        capa.addWidget(division)
        return caja

    def _articulos(self):
        caja = QWidget()
        capa = QVBoxLayout(caja)
        capa.setContentsMargins(0, 8, 0, 0)
        self.tabla_articulos = Tabla([
            Columna('Artículo', lambda a: a['nombre'], estirar=True),
            Columna('Precio', lambda a: formato.dinero(a['precio']), alinear='der', orden=lambda a: float(a['precio'])),
            Columna('Costo último', lambda a: '—' if a['sin_compras'] else formato.dinero(a['costo_ultimo']),
                    alinear='der'),
            Columna('Estimado', lambda a: '—' if a['sin_compras'] else _pct(a['margen_estimado'], 0), alinear='der'),
            Columna('Real', lambda a: '—' if a['sin_compras'] else _pct(a['margen_real'], 0), alinear='der',
                    color=lambda a: None if a['sin_compras'] else _color(a['margen_real'], self.objetivo)),
            Columna('Vendidas', lambda a: '—' if a['sin_compras'] else str(a['vendidas']), alinear='der'),
            Columna('Precio sugerido', self._texto_sugerido, alinear='der', color=self._color_sugerido),
        ], consejo=lambda a: 'Sin compras registradas: no se conoce su costo.' if a['sin_compras'] else
            'Precio para ganar el margen objetivo si lo repusieras hoy a la tasa USDT y lo vendieras a la tasa '
            'media reciente.', vacio='No hay artículos.')
        capa.addWidget(self.tabla_articulos, 1)
        nota = etiqueta('En ámbar, los artículos cuyo precio actual está por debajo del sugerido.', 'subtitulo')
        nota.setStyleSheet('font-size: 8.5pt;')
        capa.addWidget(nota)
        return caja

    def _texto_sugerido(self, a):
        if a['sin_compras'] or not a.get('precio_sugerido'):
            return '—'
        return formato.dinero(a['precio_sugerido'])

    def _color_sugerido(self, a):
        if a['sin_compras'] or not a.get('precio_sugerido'):
            return None
        return tema.AMBAR if _d(a['precio']) < _d(a['precio_sugerido']) else tema.VERDE

    # --- Gráficos ---

    def _tarjeta_grafico(self, titulo, explicacion, grafico, conclusion):
        t = Tarjeta(18)
        t.capa.setSpacing(6)
        t.capa.addWidget(etiqueta(titulo, 'seccion'))
        t.capa.addWidget(etiqueta(explicacion, 'subtitulo', ajustar=True))
        t.capa.addSpacing(8)
        t.capa.addWidget(grafico)
        conclusion.setTextFormat(Qt.RichText)
        conclusion.setWordWrap(True)
        t.capa.addWidget(conclusion)
        t.capa.addStretch()
        return t

    def _graficos(self):
        contenido = QWidget()
        contenido.setObjectName('lienzo')
        capa = QGridLayout(contenido)
        capa.setContentsMargins(0, 8, 10, 8)
        capa.setHorizontalSpacing(14)
        capa.setVerticalSpacing(14)

        fila = QHBoxLayout()
        fila.addWidget(etiqueta('Mostrar'))
        self.meses_graficos = QComboBox()
        for texto, n in (('los últimos 3 meses', 3), ('los últimos 6 meses', 6), ('los últimos 12 meses', 12)):
            self.meses_graficos.addItem(texto, n)
        self.meses_graficos.setCurrentIndex(1)
        self.meses_graficos.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.meses_graficos.currentIndexChanged.connect(lambda *_: self._cargar_graficos())
        fila.addWidget(self.meses_graficos)
        fila.addStretch()
        fila.addWidget(etiqueta('Pasa el ratón por encima de los gráficos para ver el detalle.', 'subtitulo'))
        capa.addLayout(fila, 0, 0, 1, 2)

        self.g_meses = BarrasAgrupadas(_dolares_eje, alto=270)
        self.t_meses = etiqueta('')
        capa.addWidget(self._tarjeta_grafico(
            'Ganancia por mes', 'Lo vendido de artículos con compra registrada, lo que te quedó después de pagar al '
            'proveedor y lo que se llevó la brecha. Encima de cada mes: de cada 100 $ vendidos, cuánto te quedó.',
            self.g_meses, self.t_meses), 1, 0, 1, 2)

        self.g_tasas = Lineas(lambda v: formato.numero(v, 0), alto=240)
        self.t_tasas = etiqueta('')
        capa.addWidget(self._tarjeta_grafico(
            'La brecha, día a día', 'Tasa BCV, tasa USDT (Binance) y la tasa media a la que cobraste en bolívares '
            'cada día, en Bs por dólar. Cuanto más se separan, más pierden los bolívares que cobras.',
            self.g_tasas, self.t_tasas), 2, 0, 1, 2)

        self.g_metodos = BarrasHorizontales()
        self.t_metodos = etiqueta('')
        capa.addWidget(self._tarjeta_grafico(
            'Cómo te pagan', 'Todo lo vendido, por método de pago. Celeste: bolívares · verde: dólares · '
            'ámbar: USDT.', self.g_metodos, self.t_metodos), 3, 0)

        self.g_articulos = BarrasHorizontales()
        self.t_articulos = etiqueta('')
        capa.addWidget(self._tarjeta_grafico(
            'Qué artículos dejan más', 'Ganancia real de cada artículo con compra registrada. El color es su '
            'margen frente al objetivo.', self.g_articulos, self.t_articulos), 3, 1)

        self.g_pagos = BarrasAgrupadas(_dolares_eje, alto=230)
        self.t_pagos = etiqueta('')
        capa.addWidget(self._tarjeta_grafico(
            'Pagos a proveedores que vienen', 'Lo que vence cada mes, en dólares (lo ya vencido cuenta en este '
            'mes), frente a lo que vendes en un mes normal.', self.g_pagos, self.t_pagos), 4, 0, 1, 2)
        capa.setColumnStretch(0, 1)
        capa.setColumnStretch(1, 1)
        capa.setRowStretch(5, 1)

        desplazable = QScrollArea()
        desplazable.setWidget(contenido)
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.NoFrame)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        desplazable.viewport().setObjectName('lienzo')
        desplazable.setStyleSheet('QScrollArea, QWidget#lienzo { background: transparent; }')
        return desplazable

    def _pintar_graficos(self, d):
        objetivo = self.objetivo
        self._pintar_meses(d['por_mes'], objetivo)
        self._pintar_tasas(d['tasas'])
        self._pintar_metodos(d['metodos'])
        self._pintar_articulos(d['articulos'], objetivo)
        self._pintar_pagos(d['pagos'], _d(d.get('venta_media_mensual')))

    def _pintar_meses(self, meses, objetivo):
        categorias = [nombre_mes(m['mes']) for m in meses]
        anios = [m['mes'][:4] if (i == 0 or m['mes'].endswith('-01')) else '' for i, m in enumerate(meses)]
        valores = [[float(_d(m['vendido']) or 0), float(_d(m['ganancia']) or 0), float(_d(m['brecha']) or 0)]
                   for m in meses]
        encima = [('{} $'.format(formato.numero(m['margen'], 0)), _color(m['margen'], objetivo))
                  if m.get('margen') else None for m in meses]
        consejos = []
        for m in meses:
            texto = '<b>{}</b>'.format(nombre_mes(m['mes'], con_anio=True))
            if m.get('margen'):
                texto += ('<br>Vendido (con compra): {}<br>Te quedó: {} · de cada 100 $, {} $'
                          '<br>Se llevó la brecha: {}').format(
                    formato.dinero(m['vendido']), formato.dinero(m['ganancia']), formato.numero(m['margen'], 0),
                    formato.dinero(m['brecha']))
            texto += '<br>Todas las ventas: {} en {} ventas'.format(formato.dinero(m['vendido_total']), m['ventas'])
            consejos.append(texto)
        self.g_meses.poner([('Vendido', '#BFD7EA'), ('Te quedó', tema.VERDE), ('Se llevó la brecha', '#E39A92')],
                           categorias, valores, anios, encima, consejos)
        con_margen = [m for m in meses if m.get('margen')]
        if not con_margen:
            self.t_meses.setText('')
        elif len(con_margen) == 1:
            m = con_margen[0]
            self.t_meses.setText('En {}, de cada 100 $ vendidos te quedaron <b>{} $</b>.'.format(
                MESES[int(m['mes'][5:]) - 1], formato.numero(m['margen'], 0)))
        else:
            mejor = max(con_margen, key=lambda m: _d(m['margen']))
            peor = min(con_margen, key=lambda m: _d(m['margen']))
            self.t_meses.setText(
                'Tu mejor mes fue <b>{}</b>: de cada 100 $ te quedaron {} $. El más flojo, {}: {} $.'.format(
                    MESES[int(mejor['mes'][5:]) - 1], formato.numero(mejor['margen'], 0),
                    MESES[int(peor['mes'][5:]) - 1], formato.numero(peor['margen'], 0)))

    def _pintar_tasas(self, tasas):
        def serie(campo):
            return [float(t[campo]) if t.get(campo) else None for t in tasas]

        def separacion(t):
            bcv, usdt = _d(t.get('bcv')), _d(t.get('usdt'))
            return (usdt / bcv - 1) * 100 if bcv and usdt else None

        etiquetas = ['{}/{}'.format(t['fecha'][8:10], t['fecha'][5:7]) for t in tasas]
        detalles = []
        for t in tasas:
            lineas = ['<b>{}</b>'.format(_fecha(t['fecha']))]
            for nombre, campo in (('BCV', 'bcv'), ('USDT', 'usdt'), ('Cobrada en Bs', 'cobrada')):
                if t.get(campo):
                    lineas.append('{}: {} Bs/$'.format(nombre, formato.numero(t[campo])))
            sep = separacion(t)
            if sep is not None:
                lineas.append('El USDT, un {} % por encima del BCV'.format(formato.numero(sep, 1)))
            detalles.append('<br>'.join(lineas))
        self.g_tasas.poner([('BCV', tema.MARINO, serie('bcv')), ('USDT', tema.AMBAR, serie('usdt')),
                            ('Cobrada en Bs', tema.CELESTE, serie('cobrada'))], etiquetas, detalles)
        con_ambas = [t for t in tasas if separacion(t) is not None]
        partes = []
        if con_ambas:
            ultima, primera = con_ambas[-1], con_ambas[0]
            partes.append('El <b>{}</b> el USDT estaba un <b>{} %</b> por encima del BCV'.format(
                _fecha(ultima['fecha']), formato.numero(separacion(ultima), 1)))
            if primera is not ultima:
                partes[-1] += ' (el {}, un {} %)'.format(_fecha(primera['fecha']),
                                                         formato.numero(separacion(primera), 1))
            partes[-1] += '.'
        cobradas = [_d(t['cobrada']) for t in tasas if t.get('cobrada')]
        if cobradas:
            partes.append('Cobraste en bolívares a una media de {} Bs/$.'.format(
                formato.numero(sum(cobradas) / len(cobradas))))
        self.t_tasas.setText(' '.join(partes))

    def _pintar_metodos(self, metodos):
        colores = {'VES': tema.CELESTE, 'USD': tema.VERDE, 'USDT': tema.AMBAR}
        filas = [(m['nombre'], float(_d(m['total'])), colores.get(m['moneda'], tema.MARINO),
                  '{} · {} %'.format(formato.dinero(m['total']), formato.numero(m['porcentaje'] or 0, 0)),
                  '{}: {} en {} ventas'.format(m['nombre'], formato.dinero(m['total']), m['ventas']))
                 for m in metodos]
        self.g_metodos.poner(filas)
        en_bs = sum((_d(m['porcentaje']) or 0 for m in metodos if m['moneda'] == 'VES'), 0)
        self.t_metodos.setText('El <b>{} %</b> de lo vendido entró en bolívares.'.format(formato.numero(en_bs, 0))
                               if metodos else '')

    def _pintar_articulos(self, articulos, objetivo):
        mostrar = articulos if len(articulos) <= 10 else articulos[:5] + articulos[-5:]
        filas = [(a['nombre'], float(_d(a['ganancia'])), _color(a['margen'], objetivo),
                  '{} · {}'.format(formato.dinero(a['ganancia']), _pct(a['margen'], 0)),
                  '{}<br>{} uds · vendido {} · ganancia {} · margen {}'.format(
                      a['nombre'], a['unidades'], formato.dinero(a['vendido']), formato.dinero(a['ganancia']),
                      _pct(a['margen'], 0)))
                 for a in mostrar]
        self.g_articulos.poner(filas)
        if not articulos:
            self.t_articulos.setText('')
            return
        texto = 'El que más deja: <b>{}</b> ({}).'.format(articulos[0]['nombre'],
                                                           formato.dinero(articulos[0]['ganancia']))
        bajos = [a['nombre'] for a in articulos if a.get('margen') and _d(a['margen']) < objetivo]
        if bajos:
            texto += ' <span style="color:{}">Por debajo del objetivo: {}.</span>'.format(tema.AMBAR, ', '.join(bajos))
        if len(articulos) > 10:
            texto += ' Se muestran los 5 que más y los 5 que menos dejan.'
        self.t_articulos.setText(texto)

    def _pintar_pagos(self, pagos, venta_media):
        valores = [[float(_d(p['a_pagar']) or 0)] for p in pagos]
        encima = [(formato.dinero(p['a_pagar']), tema.AMBAR if venta_media and _d(p['a_pagar']) > venta_media
                   else tema.TEXTO) if _d(p['a_pagar']) else None for p in pagos]
        consejos = ['<b>{}</b><br>Vence: {} ({} compra{})'.format(
            nombre_mes(p['mes'], con_anio=True), formato.dinero(p['a_pagar']), p['compras'],
            '' if p['compras'] == 1 else 's') for p in pagos]
        referencia = ((float(venta_media), 'Vendes unos {} al mes'.format(_dolares_eje(venta_media)))
                      if venta_media else None)
        self.g_pagos.vacio = 'No hay pagos pendientes a proveedores en estos meses.'
        self.g_pagos.poner([('A pagar', tema.AMBAR)], [nombre_mes(p['mes']) for p in pagos], valores,
                           [p['mes'][:4] if (i == 0 or p['mes'].endswith('-01')) else '' for i, p in enumerate(pagos)],
                           encima, consejos, referencia)
        con_pago = [p for p in pagos if _d(p['a_pagar'])]
        if not con_pago:
            self.t_pagos.setText('')
            return
        p = con_pago[0]
        mes, monto = MESES[int(p['mes'][5:]) - 1], _d(p['a_pagar'])
        if venta_media and monto > venta_media:
            texto = ('<span style="color:{}">En <b>{}</b> vencen {}, más de lo que vendes en un mes: conviene ir '
                     'apartando.</span>').format(tema.AMBAR, mes, formato.dinero(monto))
        elif venta_media:
            texto = 'En <b>{}</b> vencen {}: el {} % de lo que vendes en un mes.'.format(
                mes, formato.dinero(monto), formato.numero(monto / venta_media * 100, 0))
        else:
            texto = 'En <b>{}</b> vencen {}.'.format(mes, formato.dinero(monto))
        self.t_pagos.setText(texto)

    def _cargar_graficos(self):
        if not self.api.panel_abierto:
            return
        api, params, meses = self.api, self._params(), self.meses_graficos.currentData()
        ejecutar(lambda: api.rentabilidad('graficos', meses=meses, **params),
                 al_terminar=self._pintar_graficos, al_fallar=self._fallo_carga, widget=self)

    # --- Datos ---

    def _params(self):
        escenario = self.escenario.currentData()
        p = {'escenario': escenario}
        if escenario == 'otra':
            p['tasa'] = '{:.2f}'.format(self.tasa_otra.value())
        return p

    def _cambio_escenario(self, *args):
        self.tasa_otra.setVisible(self.escenario.currentData() == 'otra')
        self.cargar()

    def _rango(self):
        hoy = date.today()
        i = self.periodo.currentIndex()
        if i == 1:
            fin = hoy.replace(day=1) - timedelta(days=1)
            return fin.replace(day=1), fin
        if i == 2:
            return hoy - timedelta(days=29), hoy
        if i == 3:
            return hoy.replace(month=1, day=1), hoy
        return hoy.replace(day=1), hoy

    def cargar(self):
        if not self.api.panel_abierto:
            self._mostrar_bloqueo()
            return
        api, params = self.api, self._params()
        for t in (self.tabla_lotes, self.tabla_articulos):
            if not t.modelo.rowCount():
                t.poner_cargando()
        desde, hasta = self._rango()
        meses = self.meses_graficos.currentData()
        ejecutar(lambda: (api.rentabilidad('resumen', desde=desde.isoformat(), hasta=hasta.isoformat(), **params),
                          api.rentabilidad('lotes', **params), api.rentabilidad('articulos', **params),
                          api.rentabilidad('graficos', meses=meses, **params)),
                 al_terminar=self._cargado, al_fallar=self._fallo_carga, widget=self)

    def _cargar_resumen(self):
        if not self.api.panel_abierto:
            return
        desde, hasta = self._rango()
        api, params = self.api, self._params()
        ejecutar(lambda: api.rentabilidad('resumen', desde=desde.isoformat(), hasta=hasta.isoformat(), **params),
                 al_terminar=self._pintar_resumen, al_fallar=self._fallo_carga, widget=self)

    def _fallo_carga(self, error):
        for t in (self.tabla_lotes, self.tabla_articulos):
            t.dejar_de_cargar()
        if getattr(error, 'estado', None) == 403 and not self.ventana.sesion_caducada(error):
            self.api.bloquear_panel()
            self._mostrar_bloqueo()
            return
        self.error(error)

    def _cargado(self, datos):
        resumen, lotes, articulos, graficos = datos
        self._pintar_resumen(resumen)
        self._pintar_graficos(graficos)
        self.tabla_lotes.poner_filas(lotes)
        if self.tabla_lotes.fila_seleccionada() is None and lotes:
            self.tabla_lotes.selectRow(0)
        else:
            self._lote_elegido()
        self.tabla_articulos.poner_filas(articulos)

    def _pintar_resumen(self, r):
        self.objetivo = float(r['margen_objetivo'])
        self.margen_obj.blockSignals(True)
        self.margen_obj.setValue(self.objetivo)
        self.margen_obj.blockSignals(False)
        real = _d(r['margen_real'])
        self.c_cada100.poner('{} $'.format(formato.numero(real, 0)) if real is not None else '—',
                             'te quedaron · objetivo {}'.format(_pct(self.objetivo, 0)))
        self.c_cada100.valor.setStyleSheet('color: {};'.format(_color(real, self.objetivo)))
        self.c_ganancia.poner(formato.dinero(r['ganancia']), 'de {} vendidos'.format(formato.dinero(r['vendido'])))
        self.c_brecha.poner(formato.dinero(r['brecha']), 'medida a la tasa USDT de cada día')
        prox = r.get('proximo_vencimiento')
        self.c_pendiente.poner(formato.dinero(r['pendiente_pagar']),
                               'el próximo vence el {}'.format(_fecha(prox['vence'])) if prox else 'nada pendiente')
        self.c_pendiente.setToolTip('Próximo pago: {} · {}'.format(_fecha(prox['vence']), prox['proveedor'] or
                                                                  'sin proveedor') if prox else '')
        desde, hasta = self._rango()
        periodo = self.periodo.currentText().lower()
        if real is None:
            texto = 'En {} todavía no hay ventas de artículos con compra registrada.'.format(periodo)
        else:
            if real >= self.objetivo:
                juicio = '<span style="color:{}">Vas por encima de tu objetivo del {}.</span>'.format(
                    tema.VERDE, _pct(self.objetivo, 0))
            else:
                juicio = '<span style="color:{}">Vas por debajo de tu objetivo del {}: revisa los precios en «Por ' \
                         'artículo».</span>'.format(tema.ROJO, _pct(self.objetivo, 0))
            texto = ('En {} vendiste <b>{}</b> ({} unidades de artículos con compra registrada). Después de pagar a '
                     'los proveedores a la tasa que les toca, te quedaron <b>{}</b>: de cada 100 $, <b>{} $</b>. '
                     '{}').format(periodo, formato.dinero(r['vendido']), r['unidades'], formato.dinero(r['ganancia']),
                                  formato.numero(real, 0), juicio)
        sin_costo = _d(r['vendido_sin_costo'])
        if sin_costo:
            texto += ('<br><br><span style="color:{}">Además vendiste {} de artículos sin compra registrada: no se '
                      'conoce su costo. Cárgalos como una compra de «Inventario inicial» para incluirlos.</span>'
                      ).format(tema.TEXTO_SUAVE, formato.dinero(sin_costo))
        if self.escenario.currentData() != 'factura':
            texto += '<br><br>Las compras pendientes se calculan como si se pagasen hoy a {}.'.format(
                self.escenario.currentText())
        self.texto_resumen.setText(texto)

    def _lote_elegido(self, *args):
        lote = self.tabla_lotes.fila_seleccionada()
        if not lote:
            self.ficha.mostrar(None)
            return
        api, params, lid = self.api, self._params(), lote['id']
        ejecutar(lambda: api.rentabilidad('lotes/{}'.format(lid), **params),
                 al_terminar=lambda d: self.ficha.mostrar(d, self.objetivo), al_fallar=self._fallo_carga, widget=self)

    def _guardar_objetivo(self):
        margen = int(self.margen_obj.value())
        if margen == int(self.objetivo):
            return
        ejecutar(lambda: self.api.guardar_margen_objetivo(margen),
                 al_terminar=lambda _: (self.avisar('Margen objetivo: {} %.'.format(margen)), self.cargar()),
                 al_fallar=lambda e: mostrar_error(self, e), widget=self)
