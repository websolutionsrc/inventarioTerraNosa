"""Rutas a los archivos de recursos, tanto en desarrollo como dentro del .exe."""
import os
import sys


def carpeta_base():
    # PyInstaller descomprime los datos en sys._MEIPASS
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ruta(*partes):
    return os.path.join(carpeta_base(), 'recursos', *partes)
