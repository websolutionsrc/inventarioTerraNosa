# -*- mode: python ; coding: utf-8 -*-
# Receta de PyInstaller para TerraNosa. No se usa directamente: la llama construir.py,
# que elige el Python (3.8 para Windows 7, 3.13 para Windows 11) y empaqueta el resultado.
# Funciona con PyInstaller 5.13 (Windows 7) y 6.x (Windows 11).
import os
import sys

from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                 VarFileInfo, VarStruct, VSVersionInfo)

sys.path.insert(0, SPECPATH)
from terranosa import VERSION  # noqa: E402

numeros = tuple(int(n) for n in VERSION.split('.')) + (0,)
version = VSVersionInfo(
    ffi=FixedFileInfo(filevers=numeros, prodvers=numeros),
    kids=[
        StringFileInfo([StringTable('0C0A04B0', [
            StringStruct('CompanyName', 'Inversiones TerraNosa C.A.'),
            StringStruct('FileDescription', 'TerraNosa - Inventario y ventas'),
            StringStruct('FileVersion', VERSION),
            StringStruct('ProductName', 'TerraNosa'),
            StringStruct('ProductVersion', VERSION),
            StringStruct('OriginalFilename', 'TerraNosa.exe'),
        ])]),
        VarFileInfo([VarStruct('Translation', [0x0C0A, 1200])]),
    ],
)

a = Analysis(
    ['main.py'],
    pathex=[SPECPATH],
    datas=[(os.path.join(SPECPATH, 'recursos'), 'recursos')],
    hiddenimports=['PyQt5.QtSvg'],
    excludes=['tkinter', 'unittest', 'pydoc', 'PyQt5.QtWebEngineWidgets', 'PyQt5.QtQml', 'PyQt5.QtQuick'],
    noarchive=False,
)

# Partes de Qt que la app no usa (OpenGL por software, Qt Quick/QML, red de Qt): ~40 MB menos
SOBRAN = {'opengl32sw.dll', 'd3dcompiler_47.dll', 'libegl.dll', 'libglesv2.dll', 'qt5quick.dll', 'qt5qml.dll',
          'qt5qmlmodels.dll', 'qt5websockets.dll', 'qt5network.dll', 'qt5dbus.dll', 'qwebgl.dll', 'qminimal.dll',
          'qoffscreen.dll', 'qtuiotouchplugin.dll', 'qxdgdesktopportal.dll'}


def _sirve(entrada):
    destino = entrada[0].replace('\\', '/').lower()
    nombre = destino.rsplit('/', 1)[-1]
    if nombre in SOBRAN:
        return False
    if '/translations/' in destino:  # solo las traducciones al español
        return nombre.startswith(('qtbase_es', 'qt_es'))
    return True


a.binaries = [b for b in a.binaries if _sirve(b)]
a.datas = [d for d in a.datas if _sirve(d)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TerraNosa',
    icon=os.path.join(SPECPATH, 'recursos', 'terranosa.ico'),
    version=version,
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name='TerraNosa', upx=False)
