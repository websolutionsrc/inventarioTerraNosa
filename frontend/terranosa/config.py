"""
Configuración de la app en un archivo config.ini.

Se busca primero junto al .exe (para repartir la app ya configurada) y después en
%APPDATA%/TerraNosa/config.ini, que es donde se guardan los cambios.
"""
import configparser
import os
import sys

URL_POR_DEFECTO = 'http://127.0.0.1:8000'


def _carpeta_programa():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ruta_usuario():
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    return os.path.join(base, 'TerraNosa', 'config.ini')


class Config(object):
    def __init__(self):
        self._ini = configparser.ConfigParser()
        self._ini.read([os.path.join(_carpeta_programa(), 'config.ini'), _ruta_usuario()], encoding='utf-8')

    def _get(self, seccion, clave, defecto=''):
        return self._ini.get(seccion, clave, fallback=defecto)

    def _set(self, seccion, clave, valor):
        if not self._ini.has_section(seccion):
            self._ini.add_section(seccion)
        self._ini.set(seccion, clave, valor)
        self.guardar()

    @property
    def url_servidor(self):
        return normalizar_url(self._get('servidor', 'url', URL_POR_DEFECTO))

    @url_servidor.setter
    def url_servidor(self, valor):
        self._set('servidor', 'url', normalizar_url(valor))

    @property
    def ultimo_usuario(self):
        return self._get('sesion', 'ultimo_usuario')

    @ultimo_usuario.setter
    def ultimo_usuario(self, valor):
        self._set('sesion', 'ultimo_usuario', valor)

    def guardar(self):
        ruta = _ruta_usuario()
        try:
            os.makedirs(os.path.dirname(ruta), exist_ok=True)
            with open(ruta, 'w', encoding='utf-8') as f:
                self._ini.write(f)
        except OSError:
            pass  # sin permisos: se usa la configuración en memoria


def normalizar_url(url):
    url = (url or '').strip().rstrip('/')
    if not url:
        return URL_POR_DEFECTO
    if '://' not in url:
        url = 'http://' + url
    return url
