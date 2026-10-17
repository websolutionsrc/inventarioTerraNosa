# Cambios

## 2.1.0 · 17/10/2026

**Cobros**
- Binance (USDT) como método de pago, con **verificación automática** del pago: pantalla de espera,
  check verde al llegar y opción de cancelar (falta poner la clave de API de solo lectura en el servidor).
- Tasas de referencia **BCV** y **USDT** (Binance P2P) en Vender.
- Cobro en bolívares (efectivo Bs, pago móvil, punto, transferencia) con **tasa editable** y total en Bs,
  guardados en la venta.
- Importes como «30,00 $». Zelle retirado.
- Rueda de carga en el login, las tablas y el botón Cobrar.

**Compras e inventario**
- Pantalla **Compras**: al contado o a pagar en N meses, en Bs (tasa USDT o BCV), en dólares o en Bs fijos;
  registrar el pago y anular.
- Cada compra crea **lotes** y las ventas salen por **FIFO**.
- Artículos nuevos desde la compra, con su precio de venta; ayuda opcional para poner el precio según la
  brecha y ventana de confirmación antes de registrar.
- **Historial de cambios de precio** de cada artículo (cuándo, de cuánto a cuánto, quién y por qué).

**Rentabilidad** (admin, con PIN de gerencia)
- Resumen: de cada 100 $ vendidos cuánto quedó, ganancia real, lo que se llevó la brecha y lo pendiente
  de pagar.
- Lotes con margen estimado frente a real y ficha explicada venta por venta; compras pendientes estimadas
  «si se pagasen hoy».
- Por artículo, con precio sugerido para el margen objetivo.
- Gráficos: ganancia por mes, brecha día a día, cómo te pagan, qué artículos dejan más y pagos a proveedores
  que vienen.

**Arreglos**
- La «última tasa» es la de fecha valor más reciente, no la última consultada.

## 2.0.0 · 16/10/2026

- Backend: ventas en una sola operación con el precio guardado, método de pago y canal; anulación con motivo
  que devuelve el stock; stock solo por entradas y ajustes; configuración por variables de entorno.
- App de escritorio nueva (PyQt5, Python 3.8): Vender, Ventas de hoy (anular o corregir), Inventario,
  Historial con exportación a CSV y Usuarios.
- Compilaciones para Windows 7 (32 bits) y Windows 10/11 (64 bits).
