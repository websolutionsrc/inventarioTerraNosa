"""
Pantalla de espera de un cobro con Binance Pay.

Abre el cobro en el servidor y le pregunta cada pocos segundos si ya llegó el pago (el
servidor lo comprueba en la cuenta de Binance de la tienda). Al confirmarse muestra un
check verde y la venta ya queda registrada. Se puede cancelar mientras se espera.
"""
from PyQt5.QtCore import QEasingCurve, QPointF, Qt, QTimer, QVariantAnimation
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QApplication, QDialog, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from .. import formato, tema
from ..tareas import ejecutar
from ..widgets import Rueda, boton, confirmar, etiqueta

CONSULTAR_CADA_MS = 4000
CERRAR_TRAS_PAGO_MS = 4000


class Insignia(QWidget):
    """Círculo con check (verde) o con exclamación (ámbar), con una pequeña animación al aparecer."""

    def __init__(self, tam=96, parent=None):
        super(Insignia, self).__init__(parent)
        self.setFixedSize(tam, tam)
        self.tipo = 'check'
        self.progreso = 1.0
        self._animacion = QVariantAnimation(self)
        self._animacion.setStartValue(0.0)
        self._animacion.setEndValue(1.0)
        self._animacion.setDuration(650)
        self._animacion.setEasingCurve(QEasingCurve.OutCubic)
        self._animacion.valueChanged.connect(self._avanzar)

    def mostrar(self, tipo):
        self.tipo = tipo
        self._animacion.stop()
        self._animacion.start()

    def _avanzar(self, valor):
        self.progreso = float(valor)
        self.update()

    def paintEvent(self, evento):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        lado = float(self.width())
        color = QColor(tema.VERDE if self.tipo == 'check' else tema.AMBAR)
        # El círculo crece en el primer tercio de la animación
        escala = min(1.0, self.progreso * 3)
        radio = (lado / 2 - 2) * escala
        centro = QPointF(lado / 2, lado / 2)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawEllipse(centro, radio, radio)
        trazo = max(0.0, (self.progreso - 0.33) / 0.67)
        if trazo <= 0:
            return
        lapiz = QPen(QColor('white'), lado * 0.085)
        lapiz.setCapStyle(Qt.RoundCap)
        lapiz.setJoinStyle(Qt.RoundJoin)
        p.setPen(lapiz)
        p.setBrush(Qt.NoBrush)
        if self.tipo == 'check':
            camino = QPainterPath(QPointF(lado * 0.28, lado * 0.52))
            camino.lineTo(QPointF(lado * 0.44, lado * 0.67))
            camino.lineTo(QPointF(lado * 0.73, lado * 0.36))
            # Se dibuja solo la parte ya recorrida del check
            parcial = QPainterPath(camino.pointAtPercent(0))
            pasos = 40
            for i in range(1, int(pasos * trazo) + 1):
                parcial.lineTo(camino.pointAtPercent(i / float(pasos)))
            p.drawPath(parcial)
        else:
            p.drawLine(QPointF(lado / 2, lado * 0.27), QPointF(lado / 2, lado * (0.27 + 0.28 * trazo)))
            if trazo >= 1:
                p.drawPoint(QPointF(lado / 2, lado * 0.72))


class DialogoCobroBinance(QDialog):
    """exec_() devuelve Accepted si el pago se confirmó; la venta queda en self.venta."""

    def __init__(self, parent, api, lineas, canal, total):
        super(DialogoCobroBinance, self).__init__(parent)
        self.api, self.lineas, self.canal, self.total = api, lineas, canal, total
        self.cobro = None
        self.venta = None
        self._consultando = False
        self._restantes = 0
        self._cerrado = False
        self.setWindowTitle('Cobro con Binance Pay')
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumWidth(480)
        self.setModal(True)

        capa = QVBoxLayout(self)
        capa.setContentsMargins(28, 24, 28, 22)
        capa.setSpacing(12)
        capa.addWidget(etiqueta('Cobro con Binance Pay', 'seccion'), 0, Qt.AlignHCenter)
        self.paginas = QStackedWidget()
        capa.addWidget(self.paginas)
        self.paginas.addWidget(self._pagina_espera())
        self.paginas.addWidget(self._pagina_resultado())

        self._reloj_consulta = QTimer(self)
        self._reloj_consulta.setInterval(CONSULTAR_CADA_MS)
        self._reloj_consulta.timeout.connect(self._consultar)
        self._reloj_segundos = QTimer(self)
        self._reloj_segundos.setInterval(1000)
        self._reloj_segundos.timeout.connect(self._contar)

        self._abrir_cobro()

    # --- Construcción ---

    def _pagina_espera(self):
        pagina = QWidget()
        capa = QVBoxLayout(pagina)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(8)
        self.monto = etiqueta(self._usdt(self.total), 'total')
        self.monto.setAlignment(Qt.AlignCenter)
        capa.addWidget(self.monto)
        pay_id = ((self.api.opciones or {}).get('binance') or {}).get('pay_id')
        self.instruccion = etiqueta('Pide al cliente que envíe este monto por Binance Pay' +
                                    (' al Pay ID <b>{}</b>'.format(pay_id) if pay_id else '') + '.', 'subtitulo',
                                    ajustar=True)
        self.instruccion.setTextFormat(Qt.RichText)
        self.instruccion.setAlignment(Qt.AlignCenter)
        capa.addWidget(self.instruccion)
        capa.addSpacing(10)

        fila = QHBoxLayout()
        fila.addStretch()
        self.rueda = Rueda(56, tema.CELESTE, 5, pista='#E1E6EC')
        fila.addWidget(self.rueda)
        fila.addStretch()
        capa.addLayout(fila)
        self.estado = etiqueta('Preparando el cobro…')
        self.estado.setAlignment(Qt.AlignCenter)
        self.estado.setStyleSheet('font-size: 12pt; font-weight: 600; color: {};'.format(tema.MARINO))
        capa.addWidget(self.estado)
        self.detalle = etiqueta('', 'subtitulo', ajustar=True)
        self.detalle.setAlignment(Qt.AlignCenter)
        capa.addWidget(self.detalle)
        self.aviso = etiqueta('', 'error', ajustar=True)
        self.aviso.setAlignment(Qt.AlignCenter)
        self.aviso.hide()
        capa.addWidget(self.aviso)

        self.prueba = etiqueta('', 'chip', ajustar=True)
        self.prueba.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.prueba.setMinimumHeight(54)
        self.prueba.hide()
        capa.addWidget(self.prueba)
        capa.addSpacing(8)

        botones = QHBoxLayout()
        botones.addStretch()
        self.boton_cancelar = boton('Cancelar cobro', 'quitar', tipo='peligro')
        self.boton_cancelar.clicked.connect(self.cancelar)
        botones.addWidget(self.boton_cancelar)
        botones.addStretch()
        capa.addLayout(botones)
        return pagina

    def _pagina_resultado(self):
        pagina = QWidget()
        capa = QVBoxLayout(pagina)
        capa.setContentsMargins(0, 8, 0, 0)
        capa.setSpacing(8)
        fila = QHBoxLayout()
        fila.addStretch()
        self.insignia = Insignia(96)
        fila.addWidget(self.insignia)
        fila.addStretch()
        capa.addLayout(fila)
        self.titulo_resultado = etiqueta('')
        self.titulo_resultado.setAlignment(Qt.AlignCenter)
        capa.addWidget(self.titulo_resultado)
        self.texto_resultado = etiqueta('', 'subtitulo', ajustar=True)
        self.texto_resultado.setAlignment(Qt.AlignCenter)
        capa.addWidget(self.texto_resultado)
        capa.addSpacing(8)
        botones = QHBoxLayout()
        botones.addStretch()
        self.boton_reintentar = boton('Volver a intentar', 'refrescar')
        self.boton_reintentar.clicked.connect(self._reintentar)
        self.boton_cerrar = boton('Listo', tipo='primario')
        self.boton_cerrar.setMinimumWidth(140)
        self.boton_cerrar.clicked.connect(self._cerrar_resultado)
        botones.addWidget(self.boton_reintentar)
        botones.addWidget(self.boton_cerrar)
        botones.addStretch()
        capa.addLayout(botones)
        return pagina

    @staticmethod
    def _usdt(valor):
        return '{} USDT'.format(formato.numero(valor))

    # --- Flujo ---

    def _abrir_cobro(self):
        self.paginas.setCurrentIndex(0)
        self.rueda.iniciar()
        self.estado.setText('Preparando el cobro…')
        self.detalle.setText('')
        self.boton_cancelar.setEnabled(False)
        ejecutar(lambda: self.api.crear_cobro_binance(self.lineas, self.canal),
                 al_terminar=self._cobro_abierto, al_fallar=self._fallo_al_abrir, widget=self)

    def _cobro_abierto(self, cobro):
        if self._cerrado:  # se cerró la ventana mientras se creaba: no dejar el cobro abierto
            ejecutar(lambda: self.api.cancelar_cobro_binance(cobro['id']))
            return
        self.cobro = cobro
        self.monto.setText(self._usdt(cobro['monto']))
        self.boton_cancelar.setEnabled(True)
        if ((self.api.opciones or {}).get('binance') or {}).get('simulado'):
            self.prueba.setText('MODO PRUEBA · simula el pago en el servidor con:\n'
                                'python manage.py simular_pago_binance {}'.format(cobro['monto']))
            self.prueba.show()
        self._pintar(cobro)
        self._reloj_consulta.start()
        self._reloj_segundos.start()

    def _fallo_al_abrir(self, error):
        self._mostrar_resultado('error', 'No se pudo abrir el cobro', error.mensaje, reintentar=True,
                                texto_cerrar='Cerrar')

    def _consultar(self):
        if self._consultando or not self.cobro:
            return
        self._consultando = True
        cobro_id = self.cobro['id']
        ejecutar(lambda: self.api.cobro_binance(cobro_id), al_terminar=self._consultado,
                 al_fallar=self._fallo_consulta, widget=self)

    def _consultado(self, cobro):
        self._consultando = False
        self.cobro = cobro
        self._pintar(cobro)

    def _fallo_consulta(self, error):
        self._consultando = False
        self.aviso.setText('Sin conexión con el servidor; se sigue intentando…\n' + error.mensaje)
        self.aviso.show()

    def _pintar(self, cobro):
        estado = cobro['estado']
        if estado == 'pendiente':
            self.estado.setText('Esperando el pago…')
            self.detalle.setText('Se acepta desde {} (por si hay comisión).'.format(self._usdt(cobro['minimo'])))
            self._restantes = cobro.get('segundos_restantes', 0)
            self._contar(descontar=False)
            aviso = cobro.get('aviso')
            self.aviso.setText('Binance no responde; se sigue intentando…' if aviso else '')
            self.aviso.setVisible(bool(aviso))
            return
        self._detener()
        if estado == 'confirmado':
            self.venta = cobro['venta']
            pagador = ' de {}'.format(cobro['pagador']) if cobro.get('pagador') else ''
            llegada = 'Llegaron {}{}'.format(self._usdt(cobro['monto_recibido']), pagador).rstrip('.')
            self._mostrar_resultado('check', '¡Pago recibido!', '{}.\nVenta #{} registrada.'.format(
                llegada, self.venta['id']))
            QApplication.beep()
            QTimer.singleShot(CERRAR_TRAS_PAGO_MS, self._cerrar_resultado)
        elif estado == 'expirado':
            self._mostrar_resultado('error', 'El cobro caducó', 'No llegó ningún pago de {} a tiempo.\n'
                                    'Si el cliente ya pagó, vuelve a intentarlo.'.format(self._usdt(cobro['monto'])),
                                    reintentar=True, texto_cerrar='Cerrar')
        elif estado == 'sin_venta':
            self._mostrar_resultado('error', 'Pago recibido, pero sin venta',
                                    'Llegaron {}, pero no se pudo registrar la venta:\n{}\n'
                                    'Avisa al administrador.'.format(self._usdt(cobro['monto_recibido']),
                                                                     cobro.get('error', '')),
                                    texto_cerrar='Entendido')
        else:  # cancelado
            self.reject()

    def _contar(self, descontar=True):
        if descontar and self._restantes > 0:
            self._restantes -= 1
        m, s = divmod(max(0, self._restantes), 60)
        texto = self.detalle.text().split('\n')[0]
        self.detalle.setText('{}\nCaduca en {}:{:02d}'.format(texto, m, s))

    def _detener(self):
        self._reloj_consulta.stop()
        self._reloj_segundos.stop()
        self.rueda.detener()

    def _mostrar_resultado(self, tipo, titulo, texto, reintentar=False, texto_cerrar='Listo'):
        self._detener()
        self.paginas.setCurrentIndex(1)
        self.insignia.mostrar(tipo)
        color = tema.VERDE if tipo == 'check' else tema.AMBAR
        self.titulo_resultado.setText(titulo)
        self.titulo_resultado.setStyleSheet('font-size: 16pt; font-weight: 700; color: {};'.format(color))
        self.texto_resultado.setText(texto)
        self.boton_reintentar.setVisible(reintentar)
        self.boton_cerrar.setText(texto_cerrar)
        self.boton_cerrar.setFocus()

    def _reintentar(self):
        self.cobro = None
        self.aviso.hide()
        self._abrir_cobro()

    def _cerrar_resultado(self):
        if not self.isVisible():
            return
        if self.venta:
            self._cerrado = True
            self.accept()
        else:
            self.reject()

    # --- Cancelar ---

    def cancelar(self):
        if not self.cobro or self.cobro['estado'] != 'pendiente':
            self.reject()
            return
        if not confirmar(self, 'Cancelar cobro', '¿Cancelar el cobro de {}?\n\nSi el cliente ya pagó, '
                         'espera unos segundos a que se confirme.'.format(self._usdt(self.cobro['monto'])),
                         si='Cancelar cobro', no='Seguir esperando', peligro=True):
            return
        self.boton_cancelar.setEnabled(False)
        self.estado.setText('Cancelando…')
        self._reloj_consulta.stop()
        cobro_id = self.cobro['id']
        ejecutar(lambda: self.api.cancelar_cobro_binance(cobro_id), al_terminar=self._consultado,
                 al_fallar=self._fallo_cancelar, widget=self)

    def _fallo_cancelar(self, error):
        self.boton_cancelar.setEnabled(True)
        self._reloj_consulta.start()
        self.aviso.setText('No se pudo cancelar: ' + error.mensaje)
        self.aviso.show()

    def reject(self):
        # Cerrar con la X o Esc mientras se espera = cancelar (preguntando antes)
        if self.cobro and self.cobro['estado'] == 'pendiente' and self.paginas.currentIndex() == 0:
            self.cancelar()
            return
        self._cerrado = True
        self._detener()
        super(DialogoCobroBinance, self).reject()
