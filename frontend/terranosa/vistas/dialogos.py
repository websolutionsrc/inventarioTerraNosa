"""Ventanas de diálogo: anular venta, producto, stock, movimientos y usuarios."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QButtonGroup, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLineEdit,
                             QRadioButton, QSpinBox, QVBoxLayout)

from .. import formato, tema
from ..tareas import ejecutar
from ..widgets import Columna, Tabla, boton, etiqueta


class Dialogo(QDialog):
    """Base: título, contenido, mensaje de error y botones Cancelar / Aceptar."""

    def __init__(self, parent, titulo, texto_ok='Guardar', tipo_ok='primario', ancho=440):
        super(Dialogo, self).__init__(parent)
        self.setWindowTitle(titulo)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumWidth(ancho)
        self.capa = QVBoxLayout(self)
        self.capa.setContentsMargins(24, 20, 24, 18)
        self.capa.setSpacing(12)
        self.capa.addWidget(etiqueta(titulo, 'seccion'))
        self.cuerpo = QVBoxLayout()
        self.cuerpo.setSpacing(10)
        self.capa.addLayout(self.cuerpo)
        self.error = etiqueta('', 'error', ajustar=True)
        self.error.hide()
        self.capa.addWidget(self.error)
        fila = QHBoxLayout()
        fila.addStretch()
        self.cancelar = boton('Cancelar')
        self.cancelar.clicked.connect(self.reject)
        self.ok = boton(texto_ok, tipo=tipo_ok)
        self.ok.setDefault(True)
        self.ok.clicked.connect(self._aceptar)
        fila.addWidget(self.cancelar)
        fila.addWidget(self.ok)
        self.capa.addLayout(fila)
        self.resultado = None

    def formulario(self):
        f = QFormLayout()
        f.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f.setHorizontalSpacing(14)
        f.setVerticalSpacing(10)
        self.cuerpo.addLayout(f)
        return f

    def mostrar_error(self, texto):
        self.error.setText(texto)
        self.error.setVisible(bool(texto))

    def validar(self):
        """Devuelve un mensaje de error o '' si todo está bien."""
        return ''

    def guardar(self):
        """Función que se ejecuta en segundo plano (llamada a la API). None = solo cerrar."""
        return None

    def _aceptar(self):
        mensaje = self.validar()
        self.mostrar_error(mensaje)
        if mensaje:
            return
        tarea = self.guardar()
        if tarea is None:
            self.accept()
            return
        self.ok.setEnabled(False)
        self.cancelar.setEnabled(False)
        ejecutar(tarea, al_terminar=self._guardado, al_fallar=self._fallo, widget=self)

    def _guardado(self, resultado):
        self.resultado = resultado
        self.accept()

    def _fallo(self, error):
        self.ok.setEnabled(True)
        self.cancelar.setEnabled(True)
        if error.sesion_caducada:
            ventana = self.parentWidget().window() if self.parentWidget() else None
            self.reject()
            if hasattr(ventana, 'sesion_caducada'):
                ventana.sesion_caducada(error)
            return
        self.mostrar_error(error.mensaje)


class SelectorMotivo(object):
    """Lista de motivos frecuentes + detalle. 'Otro motivo' obliga a escribir el detalle."""
    OTRO = 'Otro motivo'

    def __init__(self, dialogo, motivos, texto_detalle='Detalle (opcional)'):
        self.combo = QComboBox()
        self.combo.addItem('Elige un motivo…')
        self.combo.addItems(motivos + [self.OTRO])
        self.detalle = QLineEdit()
        self.detalle.setMaxLength(180)
        self.detalle.setPlaceholderText(texto_detalle)
        self.combo.currentTextChanged.connect(self._cambio)

    def _cambio(self, texto):
        self.detalle.setPlaceholderText('Escribe el motivo' if texto == self.OTRO else 'Detalle (opcional)')

    def texto(self):
        elegido = self.combo.currentText() if self.combo.currentIndex() > 0 else ''
        detalle = self.detalle.text().strip()
        if elegido == self.OTRO:
            return detalle
        if elegido and detalle:
            return '{}: {}'.format(elegido, detalle)
        return elegido

    def error(self):
        if self.combo.currentIndex() <= 0:
            return 'Elige el motivo.'
        if not self.texto():
            return 'Escribe el motivo.'
        return ''


class DialogoAnular(Dialogo):
    MOTIVOS = ['Producto equivocado', 'Cantidad equivocada', 'Método de pago equivocado',
               'El cliente devolvió el producto', 'Venta registrada dos veces']

    def __init__(self, parent, api, venta, corregir=False):
        titulo = 'Anular y corregir la venta #{}' if corregir else 'Anular la venta #{}'
        super(DialogoAnular, self).__init__(parent, titulo.format(venta['id']),
                                            'Anular y corregir' if corregir else 'Anular venta', 'peligro', 480)
        self.api, self.venta = api, venta
        resumen = etiqueta('{} · {} · {}\n{}'.format(
            formato.hora(venta['fecha']), venta['metodo_pago_nombre'], formato.dinero(venta['total']),
            formato.resumen_lineas(venta['lineas'], 6)), ajustar=True)
        self.cuerpo.addWidget(resumen)
        aviso = ('Los productos vuelven al inventario. La anulación queda registrada con tu usuario y el motivo.')
        if corregir:
            aviso += '\nDespués se cargarán en "Vender" para que la cobres bien.'
        nota = etiqueta(aviso, 'subtitulo', ajustar=True)
        self.cuerpo.addWidget(nota)
        self.motivo = SelectorMotivo(self, self.MOTIVOS)
        f = self.formulario()
        f.addRow('Motivo', self.motivo.combo)
        f.addRow('', self.motivo.detalle)
        self.motivo.combo.setFocus()

    def validar(self):
        return self.motivo.error()

    def guardar(self):
        api, venta_id, motivo = self.api, self.venta['id'], self.motivo.texto()
        return lambda: api.anular_venta(venta_id, motivo)


class DialogoProducto(Dialogo):
    def __init__(self, parent, api, producto=None, tipos=(), proveedores=()):
        super(DialogoProducto, self).__init__(parent, 'Editar producto' if producto else 'Nuevo producto',
                                              'Guardar cambios' if producto else 'Crear producto')
        self.api, self.producto = api, producto
        p = producto or {}
        self.nombre = QLineEdit(p.get('nombre', ''))
        self.nombre.setMaxLength(255)
        self.tipo = self._combo_editable(tipos, p.get('tipo', ''))
        self.proveedor = self._combo_editable(proveedores, p.get('proveedor', ''))
        self.precio = QDoubleSpinBox()
        self.precio.setRange(0, 999999)
        self.precio.setDecimals(2)
        self.precio.setPrefix('$ ')
        self.precio.setValue(float(formato.decimal(p.get('precio', 0))))
        self.minimo = QSpinBox()
        self.minimo.setRange(0, 99999)
        self.minimo.setValue(int(p.get('stock_minimo', 0)))
        self.minimo.setToolTip('Si el stock llega a este número, el producto se marca en la lista.')

        f = self.formulario()
        f.addRow('Nombre *', self.nombre)
        f.addRow('Tipo', self.tipo)
        f.addRow('Proveedor', self.proveedor)
        f.addRow('Precio', self.precio)
        f.addRow('Avisar con stock ≤', self.minimo)
        if producto:
            f.addRow('Stock', etiqueta('{}  (se cambia con «Entrada» o «Ajustar stock»)'.format(p['stock']),
                                       'subtitulo'))
        else:
            self.inicial = QSpinBox()
            self.inicial.setRange(0, 99999)
            f.addRow('Stock inicial', self.inicial)
        self.nombre.setFocus()

    def _combo_editable(self, opciones, valor):
        c = QComboBox()
        c.setEditable(True)
        c.addItems(sorted(o for o in set(opciones) if o))
        c.setCurrentText(valor)
        c.lineEdit().setMaxLength(255)
        return c

    def validar(self):
        return '' if self.nombre.text().strip() else 'El nombre es obligatorio.'

    def guardar(self):
        datos = {
            'nombre': self.nombre.text().strip(),
            'tipo': self.tipo.currentText().strip(),
            'proveedor': self.proveedor.currentText().strip(),
            'precio': '{:.2f}'.format(self.precio.value()),
            'stock_minimo': self.minimo.value(),
        }
        api = self.api
        if self.producto:
            producto_id = self.producto['id']
            return lambda: api.editar_producto(producto_id, datos)
        datos['stock_inicial'] = self.inicial.value()
        return lambda: api.crear_producto(datos)


class DialogoStock(Dialogo):
    """Entrada de mercancía (suma unidades) o ajuste (se escribe el stock real contado)."""
    MOTIVOS_AJUSTE = ['Conteo físico', 'Producto dañado', 'Pérdida o robo', 'Corrección de un error anterior']

    def __init__(self, parent, api, producto, tipo):
        es_ajuste = tipo == 'ajuste'
        super(DialogoStock, self).__init__(parent, 'Ajustar stock' if es_ajuste else 'Entrada de mercancía',
                                           'Guardar ajuste' if es_ajuste else 'Registrar entrada')
        self.api, self.producto, self.tipo = api, producto, tipo
        self.actual = int(producto['stock'])
        self.cuerpo.addWidget(etiqueta('{}  ·  stock actual: {}'.format(producto['nombre'], self.actual),
                                       ajustar=True))
        f = self.formulario()
        self.cantidad = QSpinBox()
        self.cantidad.setRange(0 if es_ajuste else 1, 99999)
        self.efecto = etiqueta('', 'subtitulo')
        if es_ajuste:
            self.cantidad.setValue(self.actual)
            f.addRow('Stock real', self.cantidad)
            f.addRow('', self.efecto)
            self.motivo = SelectorMotivo(self, self.MOTIVOS_AJUSTE)
            f.addRow('Motivo', self.motivo.combo)
            f.addRow('', self.motivo.detalle)
        else:
            f.addRow('Unidades recibidas', self.cantidad)
            f.addRow('', self.efecto)
            self.nota = QLineEdit()
            self.nota.setPlaceholderText('Opcional: proveedor, factura…')
            self.nota.setMaxLength(200)
            f.addRow('Nota', self.nota)
        self.cantidad.valueChanged.connect(self._pintar_efecto)
        self._pintar_efecto()
        self.cantidad.setFocus()
        self.cantidad.selectAll()

    def _cambio(self):
        return self.cantidad.value() - self.actual if self.tipo == 'ajuste' else self.cantidad.value()

    def _pintar_efecto(self):
        cambio = self._cambio()
        if cambio == 0:
            self.efecto.setText('Sin cambios')
        else:
            self.efecto.setText('{:+d} unidades  →  quedarán {}'.format(cambio, self.actual + cambio))

    def validar(self):
        if self._cambio() == 0:
            return 'El stock real es igual al actual: no hay nada que ajustar.'
        if self.tipo == 'ajuste':
            return self.motivo.error()
        return ''

    def guardar(self):
        api, pid, tipo, cambio = self.api, self.producto['id'], self.tipo, self._cambio()
        motivo = self.motivo.texto() if tipo == 'ajuste' else self.nota.text().strip()
        return lambda: api.mover_stock(pid, tipo, cambio, motivo)


class DialogoMovimientos(Dialogo):
    TIPOS = {'inicial': 'Stock inicial', 'entrada': 'Entrada', 'ajuste': 'Ajuste'}

    def __init__(self, parent, api, producto):
        super(DialogoMovimientos, self).__init__(parent, 'Entradas y ajustes · ' + producto['nombre'],
                                                 'Cerrar', ancho=760)
        self.cancelar.hide()
        self.setMinimumHeight(420)
        self.tabla = Tabla([
            Columna('Fecha', lambda m: formato.fecha_y_hora(m['fecha']), orden=lambda m: m['fecha'], ancho=170),
            Columna('Tipo', lambda m: self.TIPOS.get(m['tipo'], m['tipo'])),
            Columna('Cambio', lambda m: '{:+d}'.format(m['cantidad']), orden=lambda m: m['cantidad'], alinear='der',
                    color=lambda m: tema.VERDE if m['cantidad'] > 0 else tema.ROJO),
            Columna('Quedó', lambda m: '' if m['stock_resultante'] is None else str(m['stock_resultante']),
                    alinear='der'),
            Columna('Usuario', lambda m: m['usuario']),
            Columna('Motivo / nota', lambda m: m['motivo'], estirar=True),
        ], vacio='Este producto no tiene entradas ni ajustes registrados.\n'
                 'Las ventas y anulaciones se ven en «Historial».')
        self.cuerpo.addWidget(self.tabla)
        self.tabla.poner_cargando()
        ejecutar(lambda: api.movimientos(producto_id=producto['id']), al_terminar=self.tabla.poner_filas,
                 al_fallar=lambda e: (self.tabla.dejar_de_cargar(), self.mostrar_error(e.mensaje)), widget=self)


class DialogoUsuario(Dialogo):
    """Nuevo usuario, o cambio de contraseña de uno existente."""

    def __init__(self, parent, api, usuario=None):
        super(DialogoUsuario, self).__init__(
            parent, 'Contraseña de ' + usuario['username'] if usuario else 'Nuevo usuario',
            'Cambiar contraseña' if usuario else 'Crear usuario')
        self.api, self.usuario = api, usuario
        f = self.formulario()
        if not usuario:
            self.nombre = QLineEdit()
            self.nombre.setMaxLength(150)
            f.addRow('Usuario', self.nombre)
        self.clave = QLineEdit()
        self.clave.setEchoMode(QLineEdit.Password)
        self.clave2 = QLineEdit()
        self.clave2.setEchoMode(QLineEdit.Password)
        f.addRow('Contraseña', self.clave)
        f.addRow('Repítela', self.clave2)
        f.addRow('', etiqueta('Mínimo 8 caracteres, que no sean solo números.', 'subtitulo'))
        if not usuario:
            self.encargado = QRadioButton('Encargado: vende y ve las ventas del día')
            self.admin = QRadioButton('Administrador: acceso a todo')
            self.encargado.setChecked(True)
            grupo = QButtonGroup(self)
            grupo.addButton(self.encargado)
            grupo.addButton(self.admin)
            roles = QVBoxLayout()
            roles.addWidget(self.encargado)
            roles.addWidget(self.admin)
            f.addRow('Rol', roles)
            self.nombre.setFocus()

    def validar(self):
        if not self.usuario and not self.nombre.text().strip():
            return 'Escribe el nombre de usuario.'
        if len(self.clave.text()) < 8:
            return 'La contraseña debe tener al menos 8 caracteres.'
        if self.clave.text() != self.clave2.text():
            return 'Las contraseñas no coinciden.'
        return ''

    def guardar(self):
        api, clave = self.api, self.clave.text()
        if self.usuario:
            uid = self.usuario['id']
            return lambda: api.editar_usuario(uid, {'password': clave})
        nombre, admin = self.nombre.text().strip(), self.admin.isChecked()
        return lambda: api.crear_usuario(nombre, clave, admin)
