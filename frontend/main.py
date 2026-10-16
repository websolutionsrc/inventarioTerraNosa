"""Punto de entrada de la app de escritorio de TerraNosa."""
import sys

from PyQt5.QtCore import QLibraryInfo, QLocale, Qt, QTranslator
from PyQt5.QtWidgets import QApplication

# Pantallas de alta resolución (Windows 10/11). En Windows 7 no cambia nada.
QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

from terranosa import tema  # noqa: E402
from terranosa.config import Config  # noqa: E402
from terranosa.vistas.login import PantallaLogin  # noqa: E402
from terranosa.vistas.principal import VentanaPrincipal  # noqa: E402


class App(object):
    def __init__(self):
        self.config = Config()
        self.login = PantallaLogin(self.config)
        self.login.entrado.connect(self.abrir)
        self.ventana = None

    def iniciar(self):
        self.login.show()

    def abrir(self, api):
        self.login.hide()
        self.ventana = VentanaPrincipal(api)
        self.ventana.salir.connect(self.salir)
        self.ventana.showMaximized()

    def salir(self, mensaje):
        ventana, self.ventana = self.ventana, None
        self.login.reiniciar(mensaje)
        self.login.show()
        if ventana:
            ventana.close()
            ventana.deleteLater()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('TerraNosa')
    app.setQuitOnLastWindowClosed(True)
    # Textos estándar de Qt en español (menú Copiar/Pegar, calendario, diálogos de archivo)
    traductor = QTranslator(app)
    if traductor.load(QLocale('es'), 'qtbase', '_', QLibraryInfo.location(QLibraryInfo.TranslationsPath)):
        app.installTranslator(traductor)
    QLocale.setDefault(QLocale(QLocale.Spanish, QLocale.Venezuela))
    tema.aplicar(app)
    controlador = App()
    controlador.iniciar()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
