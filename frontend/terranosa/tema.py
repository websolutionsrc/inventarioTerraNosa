"""
Aspecto de la app: colores de la web de TerraNosa, hoja de estilos e iconos.

Se usa el estilo "Fusion" de Qt para que la app se vea igual en Windows 7 y Windows 11.
Los iconos son SVG dibujados aquí mismo (sin emojis, que Windows 7 no muestra bien).
"""
import os
import tempfile

from PyQt5.QtCore import QByteArray, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPalette, QPixmap
from PyQt5.QtSvg import QSvgRenderer

from . import recursos

MARINO = '#0E2A47'
MARINO_HONDO = '#091D33'
CELESTE = '#1A9AD6'
CELESTE_OSCURO = '#1381B5'
CELESTE_CLARO = '#EAF6FC'
ARENA = '#F8F5F0'
TEXTO = '#1B2638'
TEXTO_SUAVE = '#5A6678'
BORDE = '#DDE3EA'
VERDE = '#1E8E5A'
VERDE_OSCURO = '#177249'
VERDE_CLARO = '#E7F5EE'
ROJO = '#C0392B'
ROJO_CLARO = '#FDEDEB'
AMBAR = '#B7791F'
AMBAR_CLARO = '#FFF6E0'

FUENTE_TITULOS = 'Georgia'  # se cambia por Marcellus si se carga bien

HOJA_ESTILOS = """
QWidget { font-family: "Segoe UI"; font-size: 10pt; color: %(TEXTO)s; }
QMainWindow, QDialog, #contenido { background: %(ARENA)s; }
QToolTip { background: %(MARINO)s; color: white; border: none; padding: 6px; }

/* Barra lateral */
#barraLateral { background: %(MARINO)s; }
#barraLateral QLabel { color: #C9D6E3; }
#barraLateral QLabel[rol="usuario"] { color: white; font-weight: 600; }
QPushButton[nav="true"] {
    color: #C9D6E3; background: transparent; border: none; border-radius: 8px;
    text-align: left; padding: 10px 14px; font-size: 10.5pt;
}
QPushButton[nav="true"]:hover { background: rgba(255, 255, 255, 0.09); color: white; }
QPushButton[nav="true"]:checked { background: %(CELESTE)s; color: white; font-weight: 600; }

/* Botones */
QPushButton {
    background: white; border: 1px solid #C9D2DC; border-radius: 6px; padding: 7px 14px;
}
QPushButton:hover { border-color: %(CELESTE)s; background: %(CELESTE_CLARO)s; }
QPushButton:pressed { background: #D7EEF9; }
QPushButton:disabled { color: #9AA5B4; background: #EEF1F4; border-color: #E1E6EC; }
QPushButton[tipo="primario"] { background: %(CELESTE)s; color: white; border: none; font-weight: 600; }
QPushButton[tipo="primario"]:hover { background: %(CELESTE_OSCURO)s; }
QPushButton[tipo="exito"] { background: %(VERDE)s; color: white; border: none; font-weight: 600; }
QPushButton[tipo="exito"]:hover { background: %(VERDE_OSCURO)s; }
QPushButton[tipo="peligro"] { color: %(ROJO)s; border-color: #E8B9B3; }
QPushButton[tipo="peligro"]:hover { background: %(ROJO_CLARO)s; border-color: %(ROJO)s; }
QPushButton[tipo="peligro"]:disabled { color: #9AA5B4; border-color: #E1E6EC; }
QPushButton[tipo="plano"] { border: none; background: transparent; color: %(CELESTE_OSCURO)s; padding: 4px 6px; }
QPushButton[tipo="plano"]:hover { text-decoration: underline; }
QPushButton[tipo="primario"]:disabled, QPushButton[tipo="exito"]:disabled { background: #B9C3CE; color: white; }
QPushButton[grande="true"] { font-size: 13pt; padding: 12px 18px; border-radius: 8px; }

/* Campos */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QPlainTextEdit {
    background: white; border: 1px solid #C9D2DC; border-radius: 6px; padding: 5px 8px;
    selection-background-color: %(CELESTE)s; selection-color: white;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QPlainTextEdit:focus {
    border-color: %(CELESTE)s;
}
QLineEdit:disabled, QComboBox:disabled { background: #EEF1F4; color: #8A96A6; }
QComboBox QAbstractItemView {
    background: white; border: 1px solid %(BORDE)s; selection-background-color: %(CELESTE_CLARO)s;
    selection-color: %(MARINO)s; outline: 0;
}
QCheckBox { spacing: 6px; }
QComboBox { padding-right: 26px; }
QDateEdit { padding-right: 4px; }
QComboBox::drop-down, QDateEdit::drop-down {
    subcontrol-origin: padding; subcontrol-position: top right; width: 26px; border: none;
}
QComboBox::down-arrow, QDateEdit::down-arrow { image: url(%(FLECHA_ABAJO)s); width: 12px; height: 12px; }
QSpinBox, QDoubleSpinBox { padding-right: 24px; }
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border; subcontrol-position: top right; width: 22px; border: none;
    border-left: 1px solid #E1E6EC; border-top-right-radius: 6px; background: #F6F8FA;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border; subcontrol-position: bottom right; width: 22px; border: none;
    border-left: 1px solid #E1E6EC; border-bottom-right-radius: 6px; background: #F6F8FA;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background: %(CELESTE_CLARO)s; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url(%(FLECHA_ARRIBA)s); width: 10px; height: 10px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url(%(FLECHA_ABAJO)s); width: 10px; height: 10px; }
QSpinBox[sinBotones="true"] { padding: 2px; }
QSpinBox[sinBotones="true"]::up-button, QSpinBox[sinBotones="true"]::down-button { width: 0; border: none; }

/* Tablas */
QTableView {
    background: white; border: 1px solid %(BORDE)s; border-radius: 8px; gridline-color: transparent;
    alternate-background-color: #F8FAFC; selection-background-color: %(CELESTE_CLARO)s;
    selection-color: %(MARINO)s; outline: 0;
}
QTableView::item { padding: 4px 8px; border-bottom: 1px solid #EEF1F4; }
QHeaderView::section {
    background: white; border: none; border-bottom: 2px solid %(BORDE)s; padding: 8px;
    font-weight: 600; color: %(TEXTO_SUAVE)s;
}
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #C6CFD9; border-radius: 4px; min-height: 30px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #C6CFD9; border-radius: 4px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }

/* Tarjetas y textos */
#tarjeta { background: white; border: 1px solid %(BORDE)s; border-radius: 10px; }
QLabel[rol="titulo"] { font-family: "%(FUENTE_TITULOS)s"; font-size: 21pt; color: %(MARINO)s; }
QLabel[rol="subtitulo"] { color: %(TEXTO_SUAVE)s; }
QLabel[rol="seccion"] { font-family: "%(FUENTE_TITULOS)s"; font-size: 14pt; color: %(MARINO)s; }
QLabel[rol="etiqueta"] { color: %(TEXTO_SUAVE)s; font-size: 9pt; font-weight: 600; }
QLabel[rol="cifra"] { font-size: 17pt; font-weight: 600; color: %(MARINO)s; }
QLabel[rol="total"] { font-size: 24pt; font-weight: 700; color: %(MARINO)s; }
QLabel[rol="error"] { color: %(ROJO)s; }
QLabel[rol="chip"] {
    background: %(CELESTE_CLARO)s; color: %(MARINO)s; border-radius: 10px; padding: 3px 10px;
}
QLabel[rol="chipRojo"] { background: %(ROJO_CLARO)s; color: %(ROJO)s; border-radius: 10px; padding: 3px 10px; }

/* Aviso superior */
#aviso { border-radius: 8px; padding: 10px 14px; font-weight: 600; }
#aviso[tipo="exito"] { background: %(VERDE_CLARO)s; color: %(VERDE_OSCURO)s; border: 1px solid #B7E0CB; }
#aviso[tipo="error"] { background: %(ROJO_CLARO)s; color: %(ROJO)s; border: 1px solid #F1C3BD; }
#aviso[tipo="info"] { background: %(CELESTE_CLARO)s; color: %(MARINO)s; border: 1px solid #BFE3F5; }

/* Login */
#fondoLogin { background: %(MARINO)s; }
#tarjetaLogin { background: white; border-radius: 14px; }
"""

# Iconos de 24x24 con trazo (estilo de línea, como los de la web)
_ICONOS = {
    'vender': '<circle cx="8" cy="21" r="1"/><circle cx="19" cy="21" r="1"/>'
              '<path d="M2 2h2l2.7 12.4a2 2 0 0 0 2 1.6h9.7a2 2 0 0 0 2-1.6L22 7H5.1"/>',
    'ventas': '<path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1z"/>'
              '<path d="M16 8h-8"/><path d="M16 12h-8"/><path d="M13 16h-5"/>',
    'inventario': '<path d="M21 16V8a2 2 0 0 0-1-1.7l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.7l7 4'
                  'a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><path d="M3.3 7L12 12l8.7-5"/><path d="M12 22V12"/>',
    'historial': '<path d="M3 12a9 9 0 1 0 9-9 9.7 9.7 0 0 0-6.7 2.7L3 8"/><path d="M3 3v5h5"/>'
                 '<path d="M12 7v5l4 2"/>',
    'usuarios': '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
                '<path d="M22 21v-2a4 4 0 0 0-3-3.9"/><path d="M16 3.1a4 4 0 0 1 0 7.8"/>',
    'salir': '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/>',
    'refrescar': '<path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/>'
                 '<path d="M21 12a9 9 0 0 1-15 6.7L3 16"/>',
    'buscar': '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
    'mas': '<path d="M12 5v14"/><path d="M5 12h14"/>',
    'menos': '<path d="M5 12h14"/>',
    'quitar': '<path d="M18 6L6 18"/><path d="M6 6l12 12"/>',
    'editar': '<path d="M17 3a2.8 2.8 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z"/>',
    'anular': '<path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/>',
    'entrada': '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/>',
    'ajuste': '<path d="M4 21v-7"/><path d="M4 10V3"/><path d="M12 21v-9"/><path d="M12 8V3"/>'
              '<path d="M20 21v-5"/><path d="M20 12V3"/><path d="M1 14h6"/><path d="M9 8h6"/><path d="M17 16h6"/>',
    'descargar': '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/>',
    'servidor': '<rect x="2" y="3" width="20" height="7" rx="2"/><rect x="2" y="14" width="20" height="7" rx="2"/>'
                '<path d="M6 6.5h.01"/><path d="M6 17.5h.01"/>',
    'ojo': '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>',
    'lista': '<path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/>'
             '<path d="M3 12h.01"/><path d="M3 18h.01"/>',
    'activar': '<path d="M20 6L9 17l-5-5"/>',
    'arriba': '<path d="M6 15l6-6 6 6"/>',
    'grafica': '<path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 5-6"/>',
    'candado': '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    'abajo': '<path d="M6 9l6 6 6-6"/>',
    'carrito_vacio': '<circle cx="8" cy="21" r="1"/><circle cx="19" cy="21" r="1"/>'
                     '<path d="M2 2h2l2.7 12.4a2 2 0 0 0 2 1.6h9.7a2 2 0 0 0 2-1.6L22 7H5.1"/>',
}

_cache = {}


def pixmap_icono(nombre, color=TEXTO, tam=20, grosor=2):
    clave = (nombre, color, tam, grosor)
    if clave not in _cache:
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{}" '
               'stroke-width="{}" stroke-linecap="round" stroke-linejoin="round">{}</svg>'
               ).format(color, grosor, _ICONOS[nombre])
        renderer = QSvgRenderer(QByteArray(svg.encode('utf-8')))
        escala = 2  # nitidez en pantallas de alta resolución
        pm = QPixmap(tam * escala, tam * escala)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        renderer.render(p, QRectF(0, 0, tam * escala, tam * escala))
        p.end()
        pm.setDevicePixelRatio(escala)
        _cache[clave] = pm
    return _cache[clave]


def icono(nombre, color=TEXTO, tam=20, color_activo=None):
    ic = QIcon(pixmap_icono(nombre, color, tam))
    if color_activo:
        ic.addPixmap(pixmap_icono(nombre, color_activo, tam), QIcon.Normal, QIcon.On)
        ic.addPixmap(pixmap_icono(nombre, color_activo, tam), QIcon.Active, QIcon.Off)
    ic.addPixmap(pixmap_icono(nombre, '#9AA5B4', tam), QIcon.Disabled)
    return ic


def _flechas():
    """Las hojas de estilo solo aceptan imágenes en archivo: se guardan en la carpeta temporal."""
    carpeta = os.path.join(tempfile.gettempdir(), 'terranosa-iconos')
    rutas = {}
    try:
        os.makedirs(carpeta, exist_ok=True)
        for clave, nombre in (('FLECHA_ARRIBA', 'arriba'), ('FLECHA_ABAJO', 'abajo')):
            ruta = os.path.join(carpeta, nombre + '.png')
            pixmap_icono(nombre, TEXTO_SUAVE, 16, 2.5).save(ruta)
            rutas[clave] = ruta.replace(os.sep, '/')
    except OSError:
        rutas = {'FLECHA_ARRIBA': '', 'FLECHA_ABAJO': ''}
    return rutas


def aplicar(app):
    global FUENTE_TITULOS
    app.setStyle('Fusion')
    id_fuente = QFontDatabase.addApplicationFont(recursos.ruta('Marcellus-Regular.ttf'))
    familias = QFontDatabase.applicationFontFamilies(id_fuente) if id_fuente >= 0 else []
    if familias:
        FUENTE_TITULOS = familias[0]
    app.setFont(QFont('Segoe UI', 10))

    paleta = app.palette()
    paleta.setColor(QPalette.Window, QColor(ARENA))
    paleta.setColor(QPalette.Highlight, QColor(CELESTE))
    paleta.setColor(QPalette.HighlightedText, QColor('white'))
    paleta.setColor(QPalette.Link, QColor(CELESTE_OSCURO))
    app.setPalette(paleta)

    colores = {k: v for k, v in globals().items() if k.isupper() and isinstance(v, str)}
    colores.update(_flechas())
    app.setStyleSheet(HOJA_ESTILOS % colores)
    app.setWindowIcon(QIcon(recursos.ruta('favicon-512.png')))
