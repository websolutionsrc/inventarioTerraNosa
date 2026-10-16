from distutils.core import setup
import py2exe

setup(
    windows=[{'script': 'interfaz.py'}],
    options={
        "py2exe": {
            "includes": ["sip", "PyQt5.QtCore", "PyQt5.QtWidgets", "PyQt5.QtGui"],
            "excludes": [],
            "dll_excludes": ["MSVCP90.dll"],
            "compressed": True,
            "optimize": 2,
            "bundle_files": 1,
        }
    },
    zipfile=None,
)