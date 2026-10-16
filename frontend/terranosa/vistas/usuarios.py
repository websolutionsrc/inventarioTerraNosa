"""Usuarios (admin): crear, cambiar contraseña o rol y desactivar."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QHBoxLayout

from .. import formato, tema
from ..tareas import ejecutar
from ..widgets import Columna, Tabla, boton, confirmar
from .base import Pagina
from .dialogos import DialogoUsuario


class PaginaUsuarios(Pagina):
    titulo = 'Usuarios'
    icono = 'usuarios'
    solo_admin = True

    def __init__(self, ventana):
        super(PaginaUsuarios, self).__init__(ventana, 'Quién puede entrar en la app')
        refrescar = self.cabecera.agregar(boton('Actualizar', 'refrescar'))
        refrescar.clicked.connect(self.cargar)
        nuevo = self.cabecera.agregar(boton('Nuevo usuario', 'mas', tipo='primario'))
        nuevo.clicked.connect(self.nuevo)

        self.tabla = Tabla([
            Columna('Usuario', lambda u: u['username'], estirar=True),
            Columna('Rol', lambda u: 'Administrador' if u['is_staff'] else 'Encargado', ancho=140),
            Columna('Estado', lambda u: 'Activo' if u['is_active'] else 'Desactivado', ancho=120,
                    color=lambda u: tema.VERDE if u['is_active'] else tema.TEXTO_SUAVE),
            Columna('Último acceso', lambda u: formato.fecha_y_hora(u['last_login']) or 'Nunca',
                    orden=lambda u: u['last_login'] or '', ancho=180),
        ], vacio='No hay usuarios.')
        self.tabla.sortByColumn(0, Qt.AscendingOrder)
        self.tabla.selectionModel().selectionChanged.connect(self._seleccion)
        self.capa.addWidget(self.tabla, 1)

        acciones = QHBoxLayout()
        self.b_clave = boton('Cambiar contraseña', 'editar')
        self.b_rol = boton('Hacer administrador', 'usuarios')
        self.b_estado = boton('Desactivar', 'quitar', tipo='peligro')
        self.b_clave.clicked.connect(self.cambiar_clave)
        self.b_rol.clicked.connect(self.cambiar_rol)
        self.b_estado.clicked.connect(self.cambiar_estado)
        acciones.addWidget(self.b_clave)
        acciones.addWidget(self.b_rol)
        acciones.addStretch()
        acciones.addWidget(self.b_estado)
        self.capa.addLayout(acciones)
        self._seleccion()

    def al_mostrar(self):
        self.cargar()

    def cargar(self):
        ejecutar(self.api.usuarios, al_terminar=self._cargado, al_fallar=self.error, widget=self)

    def _cargado(self, usuarios):
        self.tabla.poner_filas(usuarios)
        self._seleccion()

    def _seleccion(self, *args):
        u = self.tabla.fila_seleccionada()
        yo = bool(u and u['id'] == self.api.usuario.get('id'))
        self.b_clave.setEnabled(u is not None)
        self.b_rol.setEnabled(bool(u) and not yo)
        self.b_estado.setEnabled(bool(u) and not yo)
        if u:
            self.b_rol.setText('Hacer encargado' if u['is_staff'] else 'Hacer administrador')
            self.b_estado.setText('Desactivar' if u['is_active'] else 'Activar')
        tip = 'No puedes quitarte el acceso a ti mismo.' if yo else ''
        self.b_rol.setToolTip(tip)
        self.b_estado.setToolTip(tip)

    def nuevo(self):
        d = DialogoUsuario(self, self.api)
        if d.exec_() == QDialog.Accepted:
            self.avisar('Usuario «{}» creado.'.format(d.resultado['username']))
            self.cargar()

    def cambiar_clave(self):
        u = self.tabla.fila_seleccionada()
        if u and DialogoUsuario(self, self.api, u).exec_() == QDialog.Accepted:
            self.avisar('Contraseña de «{}» cambiada.'.format(u['username']))

    def _editar(self, u, datos, texto):
        ejecutar(lambda: self.api.editar_usuario(u['id'], datos),
                 al_terminar=lambda _: (self.avisar(texto), self.cargar()), al_fallar=self.error, widget=self)

    def cambiar_rol(self):
        u = self.tabla.fila_seleccionada()
        if not u:
            return
        nuevo = 'encargado' if u['is_staff'] else 'administrador'
        if confirmar(self, 'Cambiar rol', '¿Hacer {} a «{}»?'.format(nuevo, u['username']), si='Sí, cambiar'):
            self._editar(u, {'is_staff': not u['is_staff']}, '«{}» ahora es {}.'.format(u['username'], nuevo))

    def cambiar_estado(self):
        u = self.tabla.fila_seleccionada()
        if not u:
            return
        if u['is_active']:
            if not confirmar(self, 'Desactivar usuario', '«{}» no podrá entrar en la app. Sus ventas se '
                             'conservan.'.format(u['username']), si='Desactivar', peligro=True):
                return
            self._editar(u, {'is_active': False}, '«{}» desactivado.'.format(u['username']))
        else:
            self._editar(u, {'is_active': True}, '«{}» activado.'.format(u['username']))
