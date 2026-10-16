from PyQt5.QtWidgets import QVBoxLayout, QWidget

from ..widgets import Cabecera


class Pagina(QWidget):
    """Pantalla del menú lateral. al_mostrar() se llama cada vez que se entra en ella."""
    titulo = ''
    icono = ''
    solo_admin = False

    def __init__(self, ventana, subtitulo=''):
        super(Pagina, self).__init__()
        self.ventana = ventana
        self.api = ventana.api
        self.capa = QVBoxLayout(self)
        self.capa.setContentsMargins(28, 22, 28, 22)
        self.capa.setSpacing(14)
        self.cabecera = Cabecera(self.titulo, subtitulo)
        self.capa.addWidget(self.cabecera)

    def al_mostrar(self):
        pass

    def avisar(self, texto, tipo='exito'):
        self.ventana.aviso.mostrar(texto, tipo)

    def error(self, error):
        """Errores de carga: aviso arriba. Si la sesión caducó, vuelve al login."""
        if not self.ventana.sesion_caducada(error):
            self.avisar(error.mensaje, 'error')
