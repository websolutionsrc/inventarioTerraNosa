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
- Los precios están en **USD**. Los métodos **en bolívares** (efectivo Bs, pago móvil, punto de venta y
  transferencia) guardan en la venta la **tasa cobrada**, la **tasa BCV** de ese momento y el **total en Bs**.
  La tasa cobrada puede subirse (recargo) desde la app. El resumen del día suma lo cobrado en Bs por método.
- Tasas Bs/USD de referencia:
  - **BCV:** se lee de bcv.org.ve. Su web no envía el certificado intermedio de Sectigo, que va
    incluido en `inventario/certificados/` para poder verificar HTTPS.
  - **Binance P2P (USDT):** mediana de los 10 primeros anuncios de compra y de venta de USDT/VES,
    con la búsqueda pública que usa la web de Binance P2P. Referencia de mercado **no oficial**.
  - Cada tasa se consulta como mucho cada 30 minutos y se guarda la última buena (`TasaCambio`).

## Endpoints (`/api/`, con cabecera `Authorization: Token <token>`)

| Método y ruta | Quién | Para qué |
|---|---|---|
| `POST login/` | Todos | `{username, password}` → `{token, is_staff, usuario}` |
| `POST logout/` | Autenticado | Invalida el token |
| `GET yo/` | Autenticado | Datos del usuario conectado |
| `GET config/` | Autenticado | Métodos de pago, canales, fecha de hoy y versión |
| `GET tasas/` | Autenticado | Tasas Bs/USD: BCV (oficial) y USDT en Binance P2P (no oficial). Admin: `?actualizar=1` |
| `GET productos/` | Autenticado | Productos activos (admin: `?incluir_inactivos=1`) |
| `POST/PUT/PATCH productos/` | Admin | Crear (con `stock_inicial`) o editar. El stock no se edita aquí |
| `DELETE productos/{id}/` | Admin | Desactiva el producto |
| `POST productos/{id}/reactivar/` | Admin | Vuelve a activarlo |
| `GET productos/{id}/precios/` | Admin | Historial del precio de venta: cuándo, de cuánto a cuánto, quién y por qué |
| `POST productos/{id}/mover_stock/` | Admin | `{tipo: entrada\|ajuste, cantidad, motivo}` |
| `GET movimientos/` | Admin | Registro de entradas y ajustes (`?producto=`, `?desde=`, `?hasta=`) |
| `GET ventas/` | Autenticado | Encargado: las de hoy. Admin: `?fecha=` o `?desde=&hasta=`, `?estado=activas\|anuladas\|todas`, `?usuario=`, `?metodo_pago=`, `?canal=` |
| `POST ventas/` | Autenticado | `{lineas: [{producto, cantidad}], metodo_pago, canal, tasa?}`. `tasa` (Bs/$) solo cuenta en métodos en bolívares; si no viene, se usa la del BCV |
| `POST ventas/{id}/anular/` | Autenticado | `{motivo}`: anula y devuelve el stock |
| `GET ventas/resumen/` | Autenticado | Totales del día (o del periodo, si es admin) por método de pago y por canal |
| `POST cobros-binance/` | Autenticado | `{lineas, canal}`: abre un cobro con Binance y devuelve el monto en USDT |
| `GET cobros-binance/{id}/` | Autenticado | Mira en Binance si llegó el pago; al confirmarse trae la venta creada |
| `POST cobros-binance/{id}/cancelar/` | Autenticado | Cancela el cobro si aún no se pagó |
| `GET/POST compras/` | Admin | Compras con sus lotes (`?estado=pendientes\|pagadas\|anuladas`). Crear: `{proveedor, fecha, plazo_meses, forma_pago, lineas: [{producto o nuevo_nombre, cantidad, costo_unitario, precio_venta, precio_previsto?, margen_previsto?}], pago?}`. Los artículos nuevos se crean en el inventario |
| `POST compras/{id}/pagar/` | Admin | Pago único: `{fecha, tasa_pago, bs_pagados}` (o `usd_pagados`) |
| `POST compras/{id}/anular/` | Admin | Solo si no salió ninguna unidad |
| `GET compras/previsiones/` | Admin | Tasas de hoy, ritmo de subida, % cobrado en $, pendiente de pagar y proveedores |
| `GET/POST/PATCH usuarios/` | Admin | Gestión de usuarios. No se borran: se desactivan |
| `GET/POST rentabilidad/pin/` | Admin | `GET`: si el PIN de gerencia ya existe. `POST {pin}` entra; `{pin_nuevo, pin_actual?}` lo crea o cambia. Devuelve un token que caduca a los 15 min (máx. 6 intentos por minuto) |
| `GET rentabilidad/resumen/` | Admin + PIN | De cada 100 $ vendidos, ganancia real, brecha, pendiente de pagar y próximo vencimiento (`?desde=&hasta=`, por defecto el mes en curso) |
| `GET rentabilidad/lotes/` y `lotes/{id}/` | Admin + PIN | Lotes con margen estimado y real (`?estado=pendiente\|pagado\|cerrado`); la ficha trae el detalle venta por venta |
| `GET rentabilidad/articulos/` | Admin + PIN | Por artículo: costo último, margen estimado y real, vendidas y precio sugerido para el margen objetivo |
| `PATCH rentabilidad/ajustes/` | Admin + PIN | `{margen_objetivo}` |

## Compras y lotes

- Cada **compra** se paga **de una sola vez**: al contado o **a pagar en N meses** (vence a los N
  meses de la fecha). Formas de pago: en Bs a tasa USDT del día de pago (por defecto), en Bs a tasa
  BCV, en dólares/USDT o un monto fijo en Bs. Al contado, el pago se registra en el acto.
- Cada artículo comprado es un **lote**. Las ventas salen **FIFO**: primero las unidades que ya
  había antes de registrar compras (sin costo conocido) y después el lote más antiguo. Anular una
  venta devuelve las unidades a su lote; un ajuste negativo también sale del lote.
- **Historial de precios** (`CambioPrecio`): cada cambio del precio de venta queda anotado (alta, edición con
  motivo opcional `motivo_precio`, o desde una compra). Las ventas guardan siempre el precio al que se vendieron.
- Cada venta guarda la **tasa USDT del día** (referencia para medir la pérdida por brecha).
- El plan completo del análisis de rentabilidad está en `../docs/PLAN.md`.

## Rentabilidad (`inventario/rentabilidad.py`)

- Las rutas `rentabilidad/` piden, además del token de sesión de un admin, la cabecera
  `X-Pin-Gerencia` con el token que da `rentabilidad/pin/` (firmado, 15 minutos). El PIN se guarda
  cifrado en `AjustesNegocio`, junto con el margen objetivo (40 % por defecto).
- Margen de cada venta de un lote = 1 − (costo × Z) ÷ Bs cobrados, con Z la tasa a la que se pagó
  al proveedor. Las ventas cobradas en $ o USDT cuentan a la tasa Z. Ganancia = margen × lo vendido.
- Lotes **pendientes de pagar**: se estiman como si se pagasen hoy (`?escenario=factura|usdt|bcv|otra&tasa=`).
- Las unidades perdidas en ajustes restan su costo. La **brecha** de una venta en Bs es precio en $ −
  Bs ÷ tasa USDT de ese día (solo como medida).
- Todo se calcula al pedirlo; no hay resultados guardados que puedan quedar desfasados.

## Cobros con Binance Pay verificados

1. Al cobrar con Binance, la app abre un **cobro** con el total en USDT y espera.
2. Cada pocos segundos el servidor lee los **pagos recibidos en la cuenta de Binance de la
   tienda** (`GET /sapi/v1/pay/transactions`, firmada) y busca uno que:
   - llegue **después** de abrir el cobro (con un minuto de margen por desajustes de reloj);
   - tenga el **monto** esperado con margen: hasta un 1 % o 0,10 USDT de menos (por si hay
     comisión) y hasta un 10 % de más;
   - **no se haya usado** en otro cobro. Si dos cobros esperan el mismo monto, el pago va al más
     antiguo.
3. Al encontrarlo crea la venta (método Binance) y guarda el ID de la transacción y quién pagó.
   Si el producto se agotó mientras tanto, el cobro queda como «pagado pero sin venta» (se ve en
   `/admin/`).
4. El cobro caduca a los 15 minutos y se puede cancelar. Si el pago llega justo al cancelar, gana
   el pago.

**Para activarlo:** en el `.env`, `BINANCE_API_KEY` y `BINANCE_API_SECRET` de la cuenta de la
tienda, con una clave de **solo lectura** (sin operar ni retirar), limitada a la IP del servidor.
`BINANCE_PAY_ID` es opcional: solo se muestra al cajero. Los márgenes y los minutos se cambian con
las variables `BINANCE_*` de `.env.ejemplo`.

**Para probar sin clave (solo en local):** con `BINANCE_SIMULADO=true`, cada pago se simula con
`python manage.py simular_pago_binance 46.00`.

Con la verificación activa, el encargado no puede registrar ventas con Binance sin pasar por el
cobro. Zelle ya no se ofrece como método de pago; las ventas antiguas con Zelle se siguen viendo.

## Pasar al hosting

1. Crear `inventarioTerrNosa/.env` a partir de `.env.ejemplo`, con `DJANGO_DEBUG=false`,
   una `DJANGO_SECRET_KEY` nueva, el dominio y los datos de MySQL.
2. `pip install -r requirements-mysql.txt`.
3. `python manage.py migrate`. La migración `0004` convierte los datos de la v1: pone
   precio a las líneas antiguas, calcula los totales y convierte las ventas borradas
   en anuladas.
4. `python manage.py collectstatic`, solo si se usa el panel `/admin/`.
5. `python manage.py createsuperuser` para crear el primer admin.
6. El servidor tiene que poder conectarse a `www.bcv.org.ve` y `p2p.binance.com` para las tasas, y a `api.binance.com` para los cobros. En
   PythonAnywhere, la cuenta gratuita solo permite una lista de sitios autorizados: hace falta el
   plan de pago.
