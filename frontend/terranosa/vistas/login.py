from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (QAction, QGraphicsDropShadowEffect, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                             QVBoxLayout, QWidget)

from .. import VERSION, recursos, tema
from ..api import Api
from ..config import normalizar_url
from ..tareas import ejecutar
from ..widgets import boton, etiqueta, rueda_en_boton


class PantallaLogin(QWidget):
    """Entrada a la app. Emite 'entrado' con la Api ya autenticada."""
    entrado = pyqtSignal(object)

    def __init__(self, config, parent=None):
        super(PantallaLogin, self).__init__(parent)
        self.config = config
        self.setObjectName('fondoLogin')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setWindowTitle('TerraNosa · Entrar')

        tarjeta = QWidget()
        tarjeta.setObjectName('tarjetaLogin')
        tarjeta.setAttribute(Qt.WA_StyledBackground, True)
        tarjeta.setFixedWidth(400)
        sombra = QGraphicsDropShadowEffect(tarjeta)
        sombra.setBlurRadius(40)
        sombra.setOffset(0, 12)
        sombra.setColor(Qt.black)
        tarjeta.setGraphicsEffect(sombra)

        capa = QVBoxLayout(tarjeta)
        capa.setContentsMargins(36, 32, 36, 26)
        capa.setSpacing(8)

        logo = QLabel()
        logo.setPixmap(self._logo(300))
        logo.setAlignment(Qt.AlignCenter)
        capa.addWidget(logo)
        sub = etiqueta('Inventario y ventas', 'subtitulo')
        sub.setAlignment(Qt.AlignCenter)
        capa.addWidget(sub)
        capa.addSpacing(16)

        capa.addWidget(etiqueta('USUARIO', 'etiqueta'))
        self.usuario = QLineEdit(config.ultimo_usuario)
        self.usuario.setPlaceholderText('Tu usuario')
        self.usuario.setMinimumHeight(36)
        capa.addWidget(self.usuario)
        capa.addSpacing(4)

        capa.addWidget(etiqueta('CONTRASEÑA', 'etiqueta'))
        self.clave = QLineEdit()
        self.clave.setPlaceholderText('Tu contraseña')
        self.clave.setEchoMode(QLineEdit.Password)
        self.clave.setMinimumHeight(36)
        ver = QAction(tema.icono('ojo', tema.TEXTO_SUAVE, 18), 'Mostrar contraseña', self.clave)
        ver.setCheckable(True)
        ver.toggled.connect(lambda si: self.clave.setEchoMode(QLineEdit.Normal if si else QLineEdit.Password))
        self.clave.addAction(ver, QLineEdit.TrailingPosition)
        capa.addWidget(self.clave)

        self.error = etiqueta('', 'error', ajustar=True)
        self.error.hide()
        capa.addWidget(self.error)
        capa.addSpacing(10)

        self.entrar = boton('Entrar', tipo='primario', grande=True)
        self.entrar.clicked.connect(self.intentar)
        self.rueda = rueda_en_boton(self.entrar, tam=22)
        self.ocupado = False
        capa.addWidget(self.entrar)
        capa.addSpacing(12)

        pie = QHBoxLayout()
        self.servidor = etiqueta('', 'subtitulo')
        self.servidor.setStyleSheet('font-size: 8.5pt;')
        cambiar = boton('Cambiar', tipo='plano')
        cambiar.setStyleSheet('font-size: 8.5pt;')
        cambiar.clicked.connect(self.cambiar_servidor)
        pie.addWidget(self.servidor)
        pie.addStretch()
        pie.addWidget(cambiar)
        capa.addLayout(pie)
        self._pintar_servidor()

        version = QLabel('Versión ' + VERSION)
        version.setStyleSheet('color: rgba(255,255,255,0.45); font-size: 8.5pt;')

        fondo = QVBoxLayout(self)
        fondo.addStretch()
        fila = QHBoxLayout()
        fila.addStretch()
        fila.addWidget(tarjeta)
        fila.addStretch()
        fondo.addLayout(fila)
        fondo.addStretch()
        fondo.addWidget(version, alignment=Qt.AlignRight)

        self.usuario.returnPressed.connect(self.clave.setFocus)
        self.clave.returnPressed.connect(self.intentar)
        self.resize(960, 660)

    def _logo(self, ancho):
        pm = QPixmap(recursos.ruta('terranosa-logo.png'))
        escala = self.devicePixelRatioF()
        pm = pm.scaledToWidth(int(ancho * escala), Qt.SmoothTransformation)
        pm.setDevicePixelRatio(escala)
        return pm

    def showEvent(self, evento):
        super(PantallaLogin, self).showEvent(evento)
        (self.clave if self.usuario.text() else self.usuario).setFocus()

    def _pintar_servidor(self):
        self.servidor.setText('Servidor: ' + self.config.url_servidor)

    def cambiar_servidor(self):
        url, ok = QInputDialog.getText(self, 'Servidor', 'Dirección del servidor (por ejemplo, '
                                       'https://tuusuario.pythonanywhere.com):', text=self.config.url_servidor)
        if ok and url.strip():
            self.config.url_servidor = normalizar_url(url)
            self._pintar_servidor()

    def _mostrar_error(self, texto):
        self.error.setText(texto)
        self.error.setVisible(bool(texto))

    def _ocupado(self, si):
        # El botón conserva su color mientras gira la rueda; los campos solo se bloquean
        self.ocupado = si
        self.entrar.setText('Entrando…' if si else 'Entrar')
        if si:
            self.rueda.iniciar()
        else:
            self.rueda.detener()
        self.usuario.setReadOnly(si)
        self.clave.setReadOnly(si)

    def intentar(self):
        if self.ocupado:
            return
        usuario, clave = self.usuario.text().strip(), self.clave.text()
        if not usuario or not clave:
            self._mostrar_error('Escribe tu usuario y tu contraseña.')
            return
        self._mostrar_error('')
        self._ocupado(True)
        api = Api(self.config.url_servidor)
        ejecutar(lambda: api.login(usuario, clave),
                 al_terminar=lambda _: self._listo(api, usuario),
                 al_fallar=self._fallo, widget=self)

    def _listo(self, api, usuario):
        self._ocupado(False)
        self.config.ultimo_usuario = usuario
        self.clave.clear()
        self.entrado.emit(api)

    def _fallo(self, error):
        self._ocupado(False)
        self._mostrar_error(error.mensaje)
        self.clave.selectAll()
        self.clave.setFocus()

    def reiniciar(self, mensaje=''):
        self._ocupado(False)
        self.clave.clear()
        self._mostrar_error(mensaje)
