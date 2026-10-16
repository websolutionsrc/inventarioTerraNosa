"""
Cliente de la API REST del backend. Todas las llamadas al servidor pasan por aquí.

Los métodos devuelven el JSON ya convertido o lanzan ErrorApi con un mensaje en
español que se puede mostrar tal cual. Se llaman desde tareas en segundo plano
(ver tareas.py), nunca directamente desde la interfaz.
"""
import requests

TIMEOUT = (6, 25)  # (conectar, leer) en segundos


class ErrorApi(Exception):
    def __init__(self, mensaje, estado=None):
        super(ErrorApi, self).__init__(mensaje)
        self.mensaje = mensaje
        self.estado = estado

    @property
    def sesion_caducada(self):
        return self.estado == 401


def _mensaje_de_error(respuesta):
    try:
        datos = respuesta.json()
    except ValueError:
        datos = None
    if isinstance(datos, dict):
        if 'detail' in datos:
            return str(datos['detail'])
        partes = []
        for campo, errores in datos.items():
            if isinstance(errores, list):
                errores = ' '.join(str(e) for e in errores)
            partes.append(str(errores) if campo in ('non_field_errors', 'detail') else '{}: {}'.format(campo, errores))
        if partes:
            return '\n'.join(partes)
    if isinstance(datos, list) and datos:
        return ' '.join(str(d) for d in datos)
    if respuesta.status_code == 401:
        return 'La sesión ha caducado. Vuelve a entrar.'
    if respuesta.status_code == 403:
        return 'No tienes permiso para hacer esto.'
    if respuesta.status_code == 404:
        return 'No se encontró. Puede que ya no exista o que no tengas acceso.'
    if respuesta.status_code >= 500:
        return 'El servidor tuvo un error ({}). Inténtalo de nuevo.'.format(respuesta.status_code)
    return 'Error {} del servidor.'.format(respuesta.status_code)


class Api(object):
    def __init__(self, url_base):
        self.url_base = url_base.rstrip('/')
        self.token = None
        self.usuario = None  # {"id", "username", "is_staff"}
        self.opciones = None  # respuesta de /config/
        self._sesion = requests.Session()
        self._sesion.headers.update({'Accept': 'application/json'})

    @property
    def es_admin(self):
        return bool(self.usuario and self.usuario.get('is_staff'))

    def _url(self, ruta):
        return '{}/api/{}'.format(self.url_base, ruta.lstrip('/'))

    def _pedir(self, metodo, ruta, datos=None, params=None):
        cabeceras = {}
        if self.token:
            cabeceras['Authorization'] = 'Token ' + self.token
        try:
            r = self._sesion.request(metodo, self._url(ruta), json=datos, params=params,
                                     headers=cabeceras, timeout=TIMEOUT)
        except requests.exceptions.Timeout:
            raise ErrorApi('El servidor tarda demasiado en responder. Revisa la conexión a internet.')
        except requests.exceptions.SSLError:
            raise ErrorApi('No se pudo establecer una conexión segura con el servidor.')
        except requests.exceptions.ConnectionError:
            raise ErrorApi('No se pudo conectar con el servidor ({}).\nRevisa la conexión a internet '
                           'o la dirección del servidor.'.format(self.url_base))
        except requests.exceptions.RequestException as e:
            raise ErrorApi('Error de conexión: {}'.format(e))
        if r.status_code >= 400:
            raise ErrorApi(_mensaje_de_error(r), r.status_code)
        if r.status_code == 204 or not r.content:
            return None
        try:
            return r.json()
        except ValueError:
            raise ErrorApi('El servidor respondió algo inesperado. ¿La dirección del servidor es correcta?')

    # --- Sesión ---

    def login(self, username, password):
        datos = self._pedir('POST', 'login/', {'username': username, 'password': password})
        self.token = datos['token']
        self.usuario = datos.get('usuario') or {'username': username, 'is_staff': datos.get('is_staff')}
        self.opciones = self._pedir('GET', 'config/')
        return self.usuario

    def olvidar_sesion(self):
        """
        Cierra la sesión solo en este PC. No se llama a /logout/ porque el token es el mismo
        para todos los PC donde entra ese usuario y los echaría a todos.
        """
        self.token = None
        self.usuario = None

    def config(self):
        self.opciones = self._pedir('GET', 'config/')
        return self.opciones

    def tasas(self):
        """Tasas Bs/USD de referencia: {'bcv': {...}, 'bdv': {...}}."""
        return self._pedir('GET', 'tasas/')

    # --- Productos ---

    def productos(self, incluir_inactivos=False):
        return self._pedir('GET', 'productos/', params={'incluir_inactivos': '1'} if incluir_inactivos else None)

    def crear_producto(self, datos):
        return self._pedir('POST', 'productos/', datos)

    def editar_producto(self, producto_id, datos):
        return self._pedir('PATCH', 'productos/{}/'.format(producto_id), datos)

    def desactivar_producto(self, producto_id):
        return self._pedir('DELETE', 'productos/{}/'.format(producto_id))

    def reactivar_producto(self, producto_id):
        return self._pedir('POST', 'productos/{}/reactivar/'.format(producto_id))

    def mover_stock(self, producto_id, tipo, cantidad, motivo=''):
        return self._pedir('POST', 'productos/{}/mover_stock/'.format(producto_id),
                           {'tipo': tipo, 'cantidad': cantidad, 'motivo': motivo})

    def movimientos(self, producto_id=None, desde=None, hasta=None):
        params = {k: v for k, v in (('producto', producto_id), ('desde', desde), ('hasta', hasta)) if v}
        return self._pedir('GET', 'movimientos/', params=params)

    # --- Ventas ---

    def ventas(self, **filtros):
        """Sin filtros: ventas de hoy. Admin: fecha, desde, hasta, estado, usuario, metodo_pago, canal."""
        return self._pedir('GET', 'ventas/', params={k: v for k, v in filtros.items() if v})

    def resumen_ventas(self, **filtros):
        return self._pedir('GET', 'ventas/resumen/', params={k: v for k, v in filtros.items() if v})

    def vender(self, lineas, metodo_pago, canal):
        return self._pedir('POST', 'ventas/', {'lineas': lineas, 'metodo_pago': metodo_pago, 'canal': canal})

    def anular_venta(self, venta_id, motivo):
        return self._pedir('POST', 'ventas/{}/anular/'.format(venta_id), {'motivo': motivo})

    # --- Usuarios ---

    def usuarios(self):
        return self._pedir('GET', 'usuarios/')

    def crear_usuario(self, username, password, is_staff):
        return self._pedir('POST', 'usuarios/', {'username': username, 'password': password, 'is_staff': is_staff})

    def editar_usuario(self, usuario_id, datos):
        return self._pedir('PATCH', 'usuarios/{}/'.format(usuario_id), datos)
