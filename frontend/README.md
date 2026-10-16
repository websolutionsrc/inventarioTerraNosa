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
| **Vender** (F1) | Todos | Buscador y lista de productos con stock. Carrito con − y +, método de pago y canal, total y **Cobrar** (F12), con confirmación |
| **Ventas de hoy** (F2) | Todos | Total del día, número de ventas y totales por método de pago. Detalle de cada venta, **Anular venta** (motivo obligatorio; el stock vuelve) y **Corregir** (anula y carga los productos en Vender) |
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
- Las compilaciones a `.exe` para Windows 7 y Windows 11 son la fase 3
  (`requirements-win7.txt` y `requirements-win11.txt`).
