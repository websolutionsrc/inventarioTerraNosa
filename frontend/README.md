# App de escritorio TerraNosa (v2)

Punto de venta e inventario con PyQt5. Habla con el backend (`../backend`) por su API REST.

Un solo código para **Windows 7 y Windows 11**: PyQt5 (Qt 5.15, el último Qt que funciona en
Windows 7) y sintaxis compatible con **Python 3.8**. Para comprobar que nada nuevo rompe la
compatibilidad:

```
.venv\Scripts\vermin -t=3.8- --no-tips main.py terranosa
```

## Arrancar en desarrollo

Con el backend local en marcha (ver `../backend/README.md`):

```
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python main.py
```

Para entrar, usa los usuarios de prueba de `datos_demo` (admin o encargado).
La dirección del servidor se cambia en la pantalla de entrada, con el botón «Cambiar», o con
un `config.ini` junto al programa (ver `config.ini.ejemplo`).

## Pantallas

| Pantalla | Quién | Qué hace |
|---|---|---|
| **Vender** (F1) | Todos | Buscador y lista de productos con stock. Carrito con − y +, método de pago y canal, total y **Cobrar** (F12), con confirmación. Tasas **BCV** y **USDT** (Binance P2P) arriba. Con métodos en bolívares: **tasa editable** (viene la del BCV, se puede subir) y **total en Bs**, que se guardan en la venta |
| **Ventas de hoy** (F2) | Todos | Total del día y lo cobrado en Bs, número de ventas y totales por método de pago (con Bs). Detalle de cada venta, **Anular venta** (motivo obligatorio; el stock vuelve) y **Corregir** (anula y carga los productos en Vender) |
| **Inventario** (F3) | Admin | Productos con stock bajo resaltado. Nuevo, editar, **entrada de mercancía**, **ajustar stock** (con motivo), ver entradas y ajustes, desactivar y reactivar |
| **Historial** (F4) | Admin | Ventas por fechas y filtros, **anuladas en rojo** con quién, cuándo y por qué. Totales y **exportación a CSV para Excel** |
| **Usuarios** (F5) | Admin | Crear, cambiar contraseña o rol, desactivar |

Atajos: Ctrl+F para buscar en Vender; Enter o doble clic para añadir al carrito; F12 para cobrar.

## Estructura

```
main.py                 punto de entrada
terranosa/
  api.py                cliente de la API (todas las llamadas al servidor)
  tareas.py             llamadas en segundo plano para que la ventana no se congele
  config.py             config.ini (dirección del servidor, último usuario)
  tema.py               colores de la marca, hoja de estilos e iconos SVG
  widgets.py            tablas, tarjetas, botones y diálogos de confirmación
  formato.py            importes ($ 1.234,50) y fechas en español
  vistas/               login, ventana principal y una pantalla por archivo
recursos/               logos, icono y fuente Marcellus (los mismos de la web)
```

## Notas

- La app usa el estilo «Fusion» de Qt para verse igual en Windows 7 y 11, y no usa emojis
  (Windows 7 no los muestra bien).
- «Cerrar sesión» solo olvida la sesión en este PC: el token es el mismo para todos los PC en
  los que entra un usuario, y anularlo echaría a los demás.

## Compilar los .exe

`construir.py` compila con PyInstaller (receta en `terranosa.spec`) y deja en `dist/` un
`.zip` con la carpeta `TerraNosa` (`TerraNosa.exe`, `LEEME.txt` y `config.ini.ejemplo`), listo para
copiarlo al PC de la tienda. Se usa una carpeta en vez de un solo `.exe` porque arranca más
rápido en ordenadores antiguos.

| Versión | Python | PyInstaller | Resultado |
|---|---|---|---|
| Windows 10/11 (64 bits) | 3.13 (`.venv`) | 6.x | `TerraNosa-<versión>-win11-64bits.zip` (~22 MB) |
| Windows 7 (32 bits) | 3.8.10 portátil (`.venv-win7`) | 5.13.2 | `TerraNosa-<versión>-win7-32bits.zip` (~15 MB) |

**Windows 11:**

```
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python construir.py win11
```

**Windows 7.** La primera vez, prepara el Python 3.8.10 portátil de 32 bits (el paquete oficial
`pythonx86` de nuget.org; no instala nada en Windows):

```
curl -L -o python38.nupkg https://www.nuget.org/api/v2/package/pythonx86/3.8.10
mkdir .python38-32
tar -xf python38.nupkg -C .python38-32
.python38-32\tools\python.exe -m venv .venv-win7
.venv-win7\Scripts\python -m pip install -r requirements-win7.txt
```

Después, cada vez que quieras compilar:

```
.venv-win7\Scripts\python construir.py win7
```

En el PC con Windows 7 hacen falta el **Service Pack 1** y la actualización **KB2999226**
(Universal C Runtime), que casi siempre ya vienen con Windows Update. Si al abrir sale un error
sobre `api-ms-win-crt-runtime-l1-1-0.dll`, hay que instalar esa actualización.

La receta deja fuera las partes de Qt que la app no usa (OpenGL por software, Qt Quick/QML,
red de Qt y traducciones a otros idiomas).
