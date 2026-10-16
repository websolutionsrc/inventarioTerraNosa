"""
Compila la app y la deja en un .zip listo para copiar al PC de la tienda.

    .venv\\Scripts\\python construir.py win11        (Python 3.13, Windows 10/11)
    .venv-win7\\Scripts\\python construir.py win7    (Python 3.8, Windows 7)

Resultado: dist/<variante>/TerraNosa/TerraNosa.exe y dist/TerraNosa-<versión>-<variante>.zip
"""
import os
import platform
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from terranosa import VERSION  # noqa: E402

LEEME = """TerraNosa {version} para {sistema}
==============================

1. Copia la carpeta "TerraNosa" donde quieras (por ejemplo, en C:\\TerraNosa).
2. Abre TerraNosa.exe. Puedes crear un acceso directo en el escritorio.
3. En la pantalla de entrada pulsa "Cambiar" para poner la dirección del servidor,
   o copia "config.ini.ejemplo" como "config.ini" en esta carpeta y escríbela ahí.
{extra}"""

EXTRA_WIN7 = """
Windows 7: necesita el Service Pack 1 y la actualización KB2999226 (Universal C Runtime).
Si al abrir sale un error sobre "api-ms-win-crt-runtime-l1-1-0.dll", instala esa
actualización (o el "Microsoft Visual C++ Redistributable 2015-2019") y vuelve a probar.
"""


def main():
    variante = sys.argv[1] if len(sys.argv) > 1 else ''
    if variante not in ('win7', 'win11'):
        sys.exit('Uso: python construir.py win7|win11')
    if variante == 'win7' and sys.version_info[:2] != (3, 8):
        sys.exit('La versión para Windows 7 se compila con Python 3.8 (estás usando {}).'.format(
            platform.python_version()))
    if variante == 'win11' and sys.version_info < (3, 9):
        sys.exit('La versión para Windows 11 se compila con Python 3.9 o superior.')

    bits = '64' if sys.maxsize > 2 ** 32 else '32'
    nombre = 'TerraNosa-{}-{}-{}bits'.format(VERSION, variante, bits)
    dist = os.path.join(AQUI, 'dist', variante)
    trabajo = os.path.join(AQUI, 'build', variante)
    shutil.rmtree(dist, ignore_errors=True)

    subprocess.check_call([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                           '--distpath', dist, '--workpath', trabajo, os.path.join(AQUI, 'terranosa.spec')],
                          cwd=AQUI)

    carpeta = os.path.join(dist, 'TerraNosa')
    shutil.copy(os.path.join(AQUI, 'config.ini.ejemplo'), carpeta)
    sistema = 'Windows 7 (SP1)' if variante == 'win7' else 'Windows 10 y 11'
    with open(os.path.join(carpeta, 'LEEME.txt'), 'w', encoding='utf-8-sig') as f:
        f.write(LEEME.format(version=VERSION, sistema=sistema, extra=EXTRA_WIN7 if variante == 'win7' else ''))

    zip_base = os.path.join(AQUI, 'dist', nombre)
    shutil.make_archive(zip_base, 'zip', dist, 'TerraNosa')
    tam = os.path.getsize(zip_base + '.zip') / 1048576
    print('\nListo: {}.zip ({:.1f} MB)'.format(zip_base, tam))


if __name__ == '__main__':
    main()
