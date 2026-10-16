"""
Ejecuta llamadas al servidor en segundo plano para que la ventana no se congele.

    ejecutar(lambda: api.productos(), al_terminar=self.mostrar, al_fallar=self.error, widget=self)

al_terminar y al_fallar se llaman en el hilo de la interfaz. Si el widget que la pidió ya
se cerró cuando llega la respuesta, no se llama a nada.
"""
import traceback

from PyQt5.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt5 import sip

from .api import ErrorApi

_pendientes = set()  # mantiene vivas las señales hasta que llega la respuesta


class _Senales(QObject):
    terminado = pyqtSignal(object)
    fallado = pyqtSignal(object)


class _Tarea(QRunnable):
    def __init__(self, funcion, senales):
        super(_Tarea, self).__init__()
        self.funcion = funcion
        self.senales = senales

    def run(self):
        try:
            resultado = self.funcion()
        except ErrorApi as e:
            self.senales.fallado.emit(e)
        except Exception as e:  # error de programación: se muestra igualmente
            traceback.print_exc()
            self.senales.fallado.emit(ErrorApi('Error inesperado: {}'.format(e)))
        else:
            self.senales.terminado.emit(resultado)


def _vivo(widget):
    return widget is None or not sip.isdeleted(widget)


def ejecutar(funcion, al_terminar=None, al_fallar=None, widget=None):
    senales = _Senales()
    _pendientes.add(senales)

    def terminar(resultado):
        _pendientes.discard(senales)
        if al_terminar and _vivo(widget):
            al_terminar(resultado)

    def fallar(error):
        _pendientes.discard(senales)
        if al_fallar and _vivo(widget):
            al_fallar(error)

    senales.terminado.connect(terminar)
    senales.fallado.connect(fallar)
    QThreadPool.globalInstance().start(_Tarea(funcion, senales))
