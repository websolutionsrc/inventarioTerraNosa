"""
Gráficos sencillos dibujados con QPainter (sin librerías extra, para que funcione igual en Windows 7).

- BarrasAgrupadas: barras por categoría (meses), una o varias series, con texto encima y línea de referencia.
- Lineas: series a lo largo de los días (tasas), con guía vertical y valores al pasar el ratón.
- BarrasHorizontales: una barra por fila con su nombre y su valor (rankings).

Al pasar el ratón por encima de una barra o un punto se ve el detalle.
"""
import math

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QSizePolicy, QToolTip, QWidget

from . import tema

MESES_CORTOS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
REJILLA = '#EEF1F4'


def escala_redonda(maximo, divisiones=4):
    """Un tope "redondo" para el eje (p. ej. 337 → 400) y el paso entre líneas."""
    if maximo <= 0:
        return 1.0 * divisiones, 1.0
    bruto = maximo / divisiones
    magnitud = 10 ** math.floor(math.log10(bruto))
    for m in (1, 2, 2.5, 5, 10):
        paso = m * magnitud
        if paso * divisiones >= maximo:
            return paso * divisiones, paso
    return 10 * magnitud * divisiones, 10 * magnitud


def nombre_mes(clave, con_anio=False):
    """'2026-10' → 'oct' (o 'oct 2026')."""
    anio, mes = clave.split('-')
    texto = MESES_CORTOS[int(mes) - 1]
    return '{} {}'.format(texto, anio) if con_anio else texto


class Grafico(QWidget):
    """Base: fondo, mensaje cuando no hay datos y consejos al pasar el ratón por las zonas marcadas."""

    def __init__(self, alto=240, parent=None):
        super(Grafico, self).__init__(parent)
        self.setMinimumHeight(alto)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self.zonas = []  # (QRectF, texto)
        self.vacio = 'Todavía no hay datos.'
        self.pequena = QFont(self.font())
        self.pequena.setPointSizeF(max(7.5, self.font().pointSizeF() - 1.5))

    def sizeHint(self):
        sugerido = super(Grafico, self).sizeHint()
        sugerido.setHeight(self.minimumHeight())
        return sugerido

    def hay_datos(self):
        return False

    def paintEvent(self, evento):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self.zonas = []
        if self.hay_datos():
            self.dibujar(p, QRectF(self.rect()))
        else:
            p.setPen(QColor(tema.TEXTO_SUAVE))
            p.drawText(QRectF(self.rect()), Qt.AlignCenter, self.vacio)
        p.end()

    def dibujar(self, p, area):
        pass

    def consejo_en(self, punto):
        for zona, texto in self.zonas:
            if zona.contains(punto):
                return texto
        return None

    def mouseMoveEvent(self, evento):
        texto = self.consejo_en(QPointF(evento.pos()))
        if texto:
            QToolTip.showText(evento.globalPos(), texto, self)
        else:
            QToolTip.hideText()

    def leaveEvent(self, evento):
        QToolTip.hideText()

    # --- Ayudas de dibujo ---

    def leyenda(self, p, x, y, series):
        """Cuadradito de color y nombre de cada serie, en fila. Devuelve la x final."""
        p.setFont(self.pequena)
        fm = QFontMetrics(self.pequena)
        for nombre, color in series:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color))
            p.drawRoundedRect(QRectF(x, y + 3, 11, 11), 3, 3)
            p.setPen(QColor(tema.TEXTO_SUAVE))
            p.drawText(QRectF(x + 16, y, fm.width(nombre) + 4, 17), Qt.AlignLeft | Qt.AlignVCenter, nombre)
            x += 16 + fm.width(nombre) + 18
        return x

    def eje_y(self, p, area, bajo, alto, paso, texto):
        """Líneas horizontales de la rejilla con su valor a la izquierda."""
        p.setFont(self.pequena)
        v = bajo
        while v <= alto + paso / 1000.0:
            y = area.bottom() - (v - bajo) / (alto - bajo) * area.height()
            p.setPen(QPen(QColor(REJILLA), 1))
            p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            p.setPen(QColor(tema.TEXTO_SUAVE))
            p.drawText(QRectF(0, y - 9, area.left() - 8, 18), Qt.AlignRight | Qt.AlignVCenter, texto(v))
            v += paso


class BarrasAgrupadas(Grafico):
    """
    Barras por categoría. series: [(nombre, color)]. valores: una lista por categoría con un valor por serie.
    encima: texto (y color) sobre cada grupo. referencia: (valor, texto) dibuja una línea discontinua.
    consejos: texto emergente de cada grupo.
    """

    def __init__(self, formato_valor, alto=260, parent=None):
        super(BarrasAgrupadas, self).__init__(alto, parent)
        self.formato_valor = formato_valor
        self.series, self.categorias, self.subcategorias, self.valores = [], [], [], []
        self.encima, self.consejos, self.referencia = [], [], None

    def poner(self, series, categorias, valores, subcategorias=None, encima=None, consejos=None, referencia=None):
        self.series, self.categorias, self.valores = series, categorias, valores
        self.subcategorias = subcategorias or [''] * len(categorias)
        self.encima = encima or [None] * len(categorias)
        self.consejos = consejos or [None] * len(categorias)
        self.referencia = referencia
        self.update()

    def hay_datos(self):
        return any(v for fila in self.valores for v in fila)

    def dibujar(self, p, area):
        fm = QFontMetrics(self.pequena)
        valores = [v or 0.0 for fila in self.valores for v in fila]
        maximo = max(valores + [self.referencia[0] if self.referencia else 0.0])
        minimo = min(valores + [0.0])
        tope, paso = escala_redonda(maximo * 1.08)
        bajo = -math.ceil(-minimo / paso) * paso if minimo < 0 else 0.0
        ancho_eje = max(fm.width(self.formato_valor(tope)), fm.width(self.formato_valor(bajo))) + 12
        x_leyenda = self.leyenda(p, ancho_eje, 0, self.series)
        if self.referencia:
            p.setPen(QPen(QColor(tema.MARINO), 1.5, Qt.DashLine))
            p.drawLine(QPointF(x_leyenda, 9), QPointF(x_leyenda + 18, 9))
            p.setPen(QColor(tema.TEXTO_SUAVE))
            p.drawText(QRectF(x_leyenda + 24, 0, area.width(), 17), Qt.AlignLeft | Qt.AlignVCenter,
                       self.referencia[1])
        alto_cat, alto_sub = QFontMetrics(self.font()).height(), fm.height()
        abajo = alto_cat + (alto_sub if any(self.subcategorias) else 0) + 10
        dentro = QRectF(ancho_eje, 44, area.width() - ancho_eje - 4, area.height() - 44 - abajo)
        self.eje_y(p, dentro, bajo, tope, paso, self.formato_valor)

        def y_de(v):
            return dentro.bottom() - (v - bajo) / (tope - bajo) * dentro.height()

        n = len(self.categorias)
        hueco = dentro.width() / max(1, n)
        ancho_barra = min(34.0, hueco * 0.7 / max(1, len(self.series)))
        cero = y_de(0.0)
        for i, categoria in enumerate(self.categorias):
            centro = dentro.left() + hueco * (i + 0.5)
            x = centro - ancho_barra * len(self.series) / 2.0
            arriba = cero
            for j, (nombre, color) in enumerate(self.series):
                v = self.valores[i][j] or 0.0
                if not v:
                    continue  # sin barra: un mes en cero no deja una raya
                y = y_de(v)
                caja = QRectF(x + j * ancho_barra + 1, min(y, cero), ancho_barra - 2, max(1.0, abs(cero - y)))
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(color))
                p.drawRoundedRect(caja, 3, 3)
                arriba = min(arriba, caja.top())
            texto, color = self.encima[i] or (None, None)
            if texto:
                p.setFont(self.pequena)
                p.setPen(QColor(color or tema.TEXTO))
                p.drawText(QRectF(centro - hueco / 2, arriba - 20, hueco, 18), Qt.AlignHCenter | Qt.AlignBottom,
                           texto)
            p.setFont(self.font())
            p.setPen(QColor(tema.TEXTO))
            p.drawText(QRectF(centro - hueco / 2, dentro.bottom() + 4, hueco, alto_cat + 2),
                       Qt.AlignHCenter | Qt.AlignTop, categoria)
            if self.subcategorias[i]:
                p.setFont(self.pequena)
                p.setPen(QColor(tema.TEXTO_SUAVE))
                p.drawText(QRectF(centro - hueco / 2, dentro.bottom() + 4 + alto_cat, hueco, alto_sub + 2),
                           Qt.AlignHCenter | Qt.AlignTop, self.subcategorias[i])
            if self.consejos[i]:
                self.zonas.append((QRectF(centro - hueco / 2, dentro.top(), hueco, dentro.height() + abajo),
                                   self.consejos[i]))
        if self.referencia:
            y = y_de(self.referencia[0])
            p.setPen(QPen(QColor(tema.MARINO), 1.5, Qt.DashLine))
            p.drawLine(QPointF(dentro.left(), y), QPointF(dentro.right(), y))
        p.setPen(QPen(QColor(tema.BORDE), 1))
        p.drawLine(QPointF(dentro.left(), cero), QPointF(dentro.right(), cero))


class Lineas(Grafico):
    """Series por día. series: [(nombre, color, [valor o None por día])]; etiquetas: texto de cada día."""

    def __init__(self, formato_valor, alto=240, parent=None):
        super(Lineas, self).__init__(alto, parent)
        self.formato_valor = formato_valor
        self.series, self.etiquetas, self.detalles = [], [], []
        self.marcado = None
        self.xs = []

    def poner(self, series, etiquetas, detalles=None):
        """detalles: texto emergente de cada día (si no, se arma con los valores)."""
        self.series, self.etiquetas, self.detalles = series, etiquetas, detalles or []
        self.marcado = None
        self.update()

    def hay_datos(self):
        return any(v is not None for _, _, valores in self.series for v in valores)

    def dibujar(self, p, area):
        fm = QFontMetrics(self.pequena)
        todos = [v for _, _, valores in self.series for v in valores if v is not None]
        bajo, alto = min(todos), max(todos)
        margen = (alto - bajo) * 0.08 or alto * 0.05 or 1.0
        _, paso = escala_redonda(alto - bajo + 2 * margen)
        bajo = math.floor((bajo - margen) / paso) * paso
        alto = math.ceil((alto + margen) / paso) * paso
        ancho_eje = fm.width(self.formato_valor(alto)) + 12
        self.leyenda(p, ancho_eje, 0, [(n, c) for n, c, _ in self.series])
        dentro = QRectF(ancho_eje, 30, area.width() - ancho_eje - 8, area.height() - 30 - fm.height() - 12)
        self.eje_y(p, dentro, bajo, alto, paso, self.formato_valor)
        n = len(self.etiquetas)
        self.xs = [dentro.left() + (dentro.width() * i / (n - 1) if n > 1 else dentro.width() / 2) for i in range(n)]

        def y_de(v):
            return dentro.bottom() - (v - bajo) / (alto - bajo) * dentro.height()

        # Fechas abajo: unas 6, repartidas
        p.setFont(self.pequena)
        p.setPen(QColor(tema.TEXTO_SUAVE))
        cada = max(1, int(math.ceil(n / 6.0)))
        for i in range(0, n, cada):
            p.drawText(QRectF(self.xs[i] - 40, dentro.bottom() + 6, 80, fm.height() + 2),
                       Qt.AlignHCenter | Qt.AlignTop, self.etiquetas[i])
        for nombre, color, valores in self.series:
            camino = QPainterPath()
            empezado = False
            sueltos = []
            for i, v in enumerate(valores):
                if v is None:
                    empezado = False
                    continue
                punto = QPointF(self.xs[i], y_de(v))
                if empezado:
                    camino.lineTo(punto)
                else:
                    camino.moveTo(punto)
                    empezado = True
                    sueltos.append(punto)
            p.setPen(QPen(QColor(color), 2.2))
            p.setBrush(Qt.NoBrush)
            p.drawPath(camino)
            p.setBrush(QColor(color))
            p.setPen(Qt.NoPen)
            for punto in sueltos:  # un día suelto también se ve
                p.drawEllipse(punto, 3.5, 3.5)
        if self.marcado is not None and self.marcado < n:
            x = self.xs[self.marcado]
            p.setPen(QPen(QColor(tema.TEXTO_SUAVE), 1, Qt.DotLine))
            p.drawLine(QPointF(x, dentro.top()), QPointF(x, dentro.bottom()))
            for _, color, valores in self.series:
                v = valores[self.marcado]
                if v is not None:
                    p.setPen(QPen(QColor('white'), 2))
                    p.setBrush(QColor(color))
                    p.drawEllipse(QPointF(x, y_de(v)), 4.5, 4.5)
        self.zonas = [(QRectF(dentro.left() - 6, dentro.top(), dentro.width() + 12, dentro.height()), None)]

    def _detalle(self, i):
        if i < len(self.detalles) and self.detalles[i]:
            return self.detalles[i]
        lineas = ['<b>{}</b>'.format(self.etiquetas[i])]
        for nombre, _, valores in self.series:
            if valores[i] is not None:
                lineas.append('{}: {}'.format(nombre, self.formato_valor(valores[i])))
        return '<br>'.join(lineas)

    def mouseMoveEvent(self, evento):
        punto = QPointF(evento.pos())
        if not self.xs or not self.zonas or not self.zonas[0][0].contains(punto):
            if self.marcado is not None:
                self.marcado = None
                self.update()
            QToolTip.hideText()
            return
        i = min(range(len(self.xs)), key=lambda k: abs(self.xs[k] - punto.x()))
        if i != self.marcado:
            self.marcado = i
            self.update()
        QToolTip.showText(evento.globalPos(), self._detalle(i), self)

    def leaveEvent(self, evento):
        self.marcado = None
        self.update()
        QToolTip.hideText()


class BarrasHorizontales(Grafico):
    """Una barra por fila: [(nombre, valor, color, texto a la derecha, consejo)]. Admite valores negativos."""

    ALTO_FILA = 30

    def __init__(self, parent=None):
        super(BarrasHorizontales, self).__init__(self.ALTO_FILA * 3, parent)
        self.filas = []

    def poner(self, filas):
        self.filas = filas
        self.setMinimumHeight(max(3, len(filas)) * self.ALTO_FILA + 6)
        self.updateGeometry()
        self.update()

    def hay_datos(self):
        return bool(self.filas)

    def dibujar(self, p, area):
        fm = self.fontMetrics()
        fm_p = QFontMetrics(self.pequena)
        ancho_nombre = min(area.width() * 0.5, max(fm.width(f[0]) for f in self.filas) + 12)
        ancho_texto = max(fm_p.width(f[3]) for f in self.filas) + 10
        x0 = ancho_nombre
        ancho = max(20.0, area.width() - ancho_nombre - ancho_texto)
        bajo = min([0.0] + [f[1] for f in self.filas])
        alto = max([0.0] + [f[1] for f in self.filas]) or 1.0

        def x_de(v):
            return x0 + (v - bajo) / ((alto - bajo) or 1.0) * ancho

        cero = x_de(0.0)
        for i, (nombre, valor, color, texto, consejo) in enumerate(self.filas):
            y = 3 + i * self.ALTO_FILA
            p.setFont(self.font())
            p.setPen(QColor(tema.TEXTO))
            p.drawText(QRectF(0, y, ancho_nombre - 10, self.ALTO_FILA - 6), Qt.AlignRight | Qt.AlignVCenter,
                       fm.elidedText(nombre, Qt.ElideRight, int(ancho_nombre - 10)))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(REJILLA))
            p.drawRoundedRect(QRectF(x0, y + 5, ancho, self.ALTO_FILA - 16), 4, 4)
            xv = x_de(valor)
            p.setBrush(QColor(color))
            p.drawRoundedRect(QRectF(min(cero, xv), y + 5, max(2.0, abs(xv - cero)), self.ALTO_FILA - 16), 4, 4)
            p.setFont(self.pequena)
            p.setPen(QColor(tema.TEXTO_SUAVE))
            p.drawText(QRectF(x0 + ancho + 8, y, ancho_texto, self.ALTO_FILA - 6), Qt.AlignLeft | Qt.AlignVCenter,
                       texto)
            if consejo or fm.width(nombre) > ancho_nombre - 10:
                self.zonas.append((QRectF(0, y, area.width(), self.ALTO_FILA), consejo or nombre))
