# Backend del inventario TerraNosa (v2)

API REST con Django 5.2 LTS y Django REST Framework.
En local usa SQLite; en el hosting, MySQL (ver `.env.ejemplo`).

## Arrancar en local

Desde la carpeta `backend`:

```
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
cd inventarioTerrNosa
..\.venv\Scripts\python manage.py migrate
..\.venv\Scripts\python manage.py datos_demo
..\.venv\Scripts\python manage.py runserver 127.0.0.1:8000
```

- `datos_demo` crea dos usuarios de prueba (admin y encargado), 15 productos y
  algunas ventas de hoy y de ayer, una de ellas anulada. Las contraseñas están al
  principio de `inventario/management/commands/datos_demo.py`.
  Solo funciona con `DEBUG` activado.
- `datos_demo --borrar` vuelve a empezar de cero.
- Pruebas: `..\.venv\Scripts\python manage.py test inventario`.
- La API navegable está en http://127.0.0.1:8000/api/ y el panel de Django en `/admin/`.

## Reglas de negocio

- El **stock** solo cambia con ventas, anulaciones, entradas de mercancía o ajustes.
  Cada cambio queda registrado. Desde la ficha del producto no se puede editar.
- Cada **venta** se crea en una sola operación: si falta stock de algún producto, no
  se registra nada. El precio lo pone el servidor y queda guardado en cada línea.
- Las ventas **no se editan ni se borran: se anulan** con un motivo obligatorio. Al
  anular, el stock vuelve.
- El **encargado** solo ve las ventas de hoy que no están anuladas, y puede anular
  cualquiera de ellas. El **admin** ve todas, también las anuladas, con quién la
  anuló, cuándo y por qué.
- "Hoy" es el día en Venezuela (`America/Caracas`).
- Los **productos** no se borran: se desactivan y conservan su historial.
- Los precios están en **USD**.

## Endpoints (`/api/`, con cabecera `Authorization: Token <token>`)

| Método y ruta | Quién | Para qué |
|---|---|---|
| `POST login/` | Todos | `{username, password}` → `{token, is_staff, usuario}` |
| `POST logout/` | Autenticado | Invalida el token |
| `GET yo/` | Autenticado | Datos del usuario conectado |
| `GET config/` | Autenticado | Métodos de pago, canales, fecha de hoy y versión |
| `GET productos/` | Autenticado | Productos activos (admin: `?incluir_inactivos=1`) |
| `POST/PUT/PATCH productos/` | Admin | Crear (con `stock_inicial`) o editar. El stock no se edita aquí |
| `DELETE productos/{id}/` | Admin | Desactiva el producto |
| `POST productos/{id}/reactivar/` | Admin | Vuelve a activarlo |
| `POST productos/{id}/mover_stock/` | Admin | `{tipo: entrada\|ajuste, cantidad, motivo}` |
| `GET movimientos/` | Admin | Registro de entradas y ajustes (`?producto=`, `?desde=`, `?hasta=`) |
| `GET ventas/` | Autenticado | Encargado: las de hoy. Admin: `?fecha=` o `?desde=&hasta=`, `?estado=activas\|anuladas\|todas`, `?usuario=`, `?metodo_pago=`, `?canal=` |
| `POST ventas/` | Autenticado | `{lineas: [{producto, cantidad}], metodo_pago, canal}` |
| `POST ventas/{id}/anular/` | Autenticado | `{motivo}`: anula y devuelve el stock |
| `GET ventas/resumen/` | Autenticado | Totales del día (o del periodo, si es admin) por método de pago y por canal |
| `GET/POST/PATCH usuarios/` | Admin | Gestión de usuarios. No se borran: se desactivan |

## Pasar al hosting

1. Crear `inventarioTerrNosa/.env` a partir de `.env.ejemplo`, con `DJANGO_DEBUG=false`,
   una `DJANGO_SECRET_KEY` nueva, el dominio y los datos de MySQL.
2. `pip install -r requirements-mysql.txt`.
3. `python manage.py migrate`. La migración `0004` convierte los datos de la v1: pone
   precio a las líneas antiguas, calcula los totales y convierte las ventas borradas
   en anuladas.
4. `python manage.py collectstatic`, solo si se usa el panel `/admin/`.
5. `python manage.py createsuperuser` para crear el primer admin.
