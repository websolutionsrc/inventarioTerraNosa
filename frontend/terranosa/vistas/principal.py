from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QKeySequence, QPixmap
from PyQt5.QtWidgets import (QButtonGroup, QHBoxLayout, QLabel, QMainWindow, QPushButton, QShortcut,
                             QStackedWidget, QVBoxLayout, QWidget)

from .. import recursos, tema
from ..widgets import Aviso, confirmar
from .historial import PaginaHistorial
from .inventario import PaginaInventario
from .usuarios import PaginaUsuarios
from .vender import PaginaVender
from .ventas_hoy import PaginaVentasHoy


class VentanaPrincipal(QMainWindow):
    """Menú lateral + pantallas. Emite 'salir' (con un mensaje) al cerrar sesión."""
    salir = pyqtSignal(str)

    def __init__(self, api):
        super(VentanaPrincipal, self).__init__()
        self.api = api
        self._cerrando = False
        self.setWindowTitle('TerraNosa · Inventario y ventas')
        self.setMinimumSize(980, 620)

        central = QWidget()
        self.setCentralWidget(central)
        capa = QHBoxLayout(central)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(0)

        capa.addWidget(self._barra_lateral())

        contenido = QWidget()
        contenido.setObjectName('contenido')
        contenido.setAttribute(Qt.WA_StyledBackground, True)
        capa_contenido = QVBoxLayout(contenido)
        capa_contenido.setContentsMargins(0, 0, 0, 0)
        capa_contenido.setSpacing(0)
        self.aviso = Aviso()
        marco_aviso = QHBoxLayout()
        marco_aviso.setContentsMargins(28, 14, 28, 0)
        marco_aviso.addWidget(self.aviso)
        capa_contenido.addLayout(marco_aviso)
        self.pilas = QStackedWidget()
        capa_contenido.addWidget(self.pilas)
        capa.addWidget(contenido, 1)

        clases = [PaginaVender, PaginaVentasHoy, PaginaInventario, PaginaHistorial, PaginaUsuarios]
        self.paginas = []
        for i, clase in enumerate(c for c in clases if api.es_admin or not c.solo_admin):
            pagina = clase(self)
            self.paginas.append(pagina)
            self.pilas.addWidget(pagina)
            b = self._boton_nav(pagina.titulo, pagina.icono, 'F{}'.format(i + 1))
            self.grupo.addButton(b, i)
            self.menu.addWidget(b)
            QShortcut(QKeySequence('F{}'.format(i + 1)), self, activated=b.click)
        self.grupo.buttonClicked[int].connect(self.ir_a)
        self.ir_a(0)

    def _barra_lateral(self):
        barra = QWidget()
        barra.setObjectName('barraLateral')
        barra.setAttribute(Qt.WA_StyledBackground, True)
        barra.setFixedWidth(230)
        capa = QVBoxLayout(barra)
        capa.setContentsMargins(16, 22, 16, 18)
        capa.setSpacing(4)

        logo = QLabel()
        pm = QPixmap(recursos.ruta('terranosa-logo-blanco.png'))
        escala = self.devicePixelRatioF()
        pm = pm.scaledToWidth(int(190 * escala), Qt.SmoothTransformation)
        pm.setDevicePixelRatio(escala)
        logo.setPixmap(pm)
        capa.addWidget(logo)
        capa.addSpacing(22)

        self.grupo = QButtonGroup(self)
        self.grupo.setExclusive(True)
        self.menu = QVBoxLayout()
        self.menu.setSpacing(4)
        capa.addLayout(self.menu)
        capa.addStretch()

        nombre = QLabel(self.api.usuario['username'])
        nombre.setProperty('rol', 'usuario')
        rol = QLabel('Administrador' if self.api.es_admin else 'Encargado')
        capa.addWidget(nombre)
        capa.addWidget(rol)
        capa.addSpacing(6)
        salir = self._boton_nav('Cerrar sesión', 'salir')
        salir.setCheckable(False)
        salir.clicked.connect(self.cerrar_sesion)
        capa.addWidget(salir)
        return barra

    def _boton_nav(self, texto, icono, atajo=None):
        b = QPushButton('  ' + texto)
        b.setProperty('nav', True)
        b.setCheckable(True)
        b.setCursor(Qt.PointingHandCursor)
        b.setIcon(tema.icono(icono, '#C9D6E3', 20, color_activo='white'))
        b.setIconSize(QSize(20, 20))
        if atajo:
            b.setToolTip('{} ({})'.format(texto, atajo))
        return b

    def ir_a(self, i):
        self.grupo.button(i).setChecked(True)
        self.pilas.setCurrentIndex(i)
        self.paginas[i].al_mostrar()

    def pagina(self, clase):
        for i, p in enumerate(self.paginas):
            if isinstance(p, clase):
                return i, p
        return None, None

    def corregir_venta(self, venta):
        """Lleva los productos de una venta anulada al carrito para cobrarla bien."""
        i, vender = self.pagina(PaginaVender)
        self.ir_a(i)
        vender.cargar_venta(venta)

    def sesion_caducada(self, error):
        if getattr(error, 'sesion_caducada', False):
            self._salir('Tu sesión ha caducado. Vuelve a entrar.')
            return True
        return False

    def cerrar_sesion(self):
        if confirmar(self, 'Cerrar sesión', '¿Quieres cerrar la sesión?', si='Cerrar sesión'):
            self.api.olvidar_sesion()
            self._salir('')

    def _salir(self, mensaje):
        if self._cerrando:
            return
        self._cerrando = True
        self.salir.emit(mensaje)
