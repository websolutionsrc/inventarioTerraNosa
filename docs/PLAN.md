# Plan: compras, rentabilidad y brecha cambiaria

Acordado el 17/10/2026. Objetivo: saber cuánto se gana de verdad con cada compra, teniendo en
cuenta que se cobra en bolívares a una tasa y se paga al proveedor a otra (la brecha), y ayudar a
poner precios.

## Vocabulario

- **Contado** o **a pagar en N meses**: la compra se paga **toda de una vez** al vencimiento. No hay
  cuotas. En la app no se usa la palabra "crédito".
- **Margen**: siempre **sobre el precio de venta** ("de cada 100 $ vendidos te quedaron X $").
- **Margen estimado** = (precio − costo) ÷ precio. Sin tasas.
- **Margen real**: con las tasas a las que de verdad se cobró y se pagó.

## Fase 1 · Compras y lotes ✅ (hecha el 17/10/2026)

- **Nueva compra** (sustituye a "Entrada de mercancía"):
  - proveedor, fecha, y artículos con cantidad y costo unitario en $;
  - forma de pago: **Bs a tasa USDT del día de pago** (por defecto), Bs a tasa BCV, en $ o USDT,
    o monto fijo en Bs;
  - **Contado** o **a pagar en N meses**, con la fecha de vencimiento.
- **Estimar ganancia y precio** (apartado opcional y plegable de la compra), por artículo:
  - previsiones editables:
    - tasa de pago al vencimiento: USDT de hoy proyectada;
    - tasa media de venta: BCV proyectada durante la venta del lote;
    - % cobrado en $ o USDT: de los últimos 30 días;
  - resultado en vivo: margen estimado, **margen previsto con la brecha**, precio mínimo para el
    margen objetivo y precio para mantener el margen estimado;
  - tres escenarios: la brecha no cambia, sigue como va, se agranda;
  - botón **"Usar este precio"**;
  - mientras no haya historial de tasas, el ritmo de subida mensual se escribe a mano
    (por defecto, 3 % al mes).
- **Pantalla Compras** (admin): estado (pagada, vence en N días, vencida), total pendiente de
  pagar, **Registrar pago** (uno solo: Bs pagados y tasa Z1 de ese día) y **Anular compra** (solo
  si no se vendió nada).
- **FIFO**: cada venta toma las unidades del lote más antiguo; anular una venta las devuelve; los
  ajustes negativos también descuentan del lote. El stock que ya existe queda "sin costo" hasta
  cargarlo como compra de *Inventario inicial*.
- Cada venta guarda la **tasa USDT del día** (referencia de la brecha).

## Fase 2 · Panel de rentabilidad (con PIN) ✅ (hecha el 17/10/2026)

Hecho como se describe abajo, con estas diferencias: el resultado de un lote vendido y pagado
entero se calcula al vuelo (no se guarda aparte) y en el detalle venta por venta se marcan en
ámbar o rojo las ventas por debajo del margen objetivo.

- **PIN de gerencia** aparte de la contraseña; caduca a los 15 minutos; solo administradores.
- **Vista general**: "de cada 100 $ vendidos te quedaron X $", ganancia real del mes, pendiente de
  pagar, próximo vencimiento y lista de lotes con semáforo.
- **Ficha del lote**:
  - **Pendiente de pagar**: estimación "si se pagase hoy" a tasa USDT, BCV u otra.
  - **Pagado**: análisis real. Tasa media de venta ponderada (X̄) frente a tasa de pago (Z1):
    - margen real = 1 − (costo × Z1) ÷ (precio × X̄);
    - las ventas cobradas en $ o USDT cuentan a la tasa Z1;
    - detalle venta por venta, con las de tasa más baja en rojo.
  - **Pagado y vendido entero**: resultado definitivo y guardado. Incluye lo previsto en la compra
    frente a lo que pasó.
  - Pérdida por brecha de cada venta en Bs = precio en $ − Bs cobrados ÷ tasa USDT del día (solo
    como medida; no supone que los Bs se cambiaran ese día).
- **Por artículo**: costo, precio, margen estimado, margen real de sus lotes y precio mínimo
  sugerido para el margen objetivo (editable en el panel).

## Fase 3 · Análisis avanzado (gráficos)

Margen real por mes y por artículo, ventas por método de pago, evolución de la brecha BCV/USDT,
artículos más y menos rentables, y pendiente de pagar frente a ventas.

## Futura mejora (BETA) · Catálogo central y Marketplace

Para probar y optimizar más adelante:

- productos con fotos, descripción y categoría en el sistema;
- la web lee catálogo y stock de la API, en vez de copiar Marketplace cada día;
- **asistente de publicación**: deja listo el título, la descripción, el precio y las fotos, y abre
  la página de crear publicación de Facebook. Facebook no tiene una API pública para publicar en
  Marketplace, y automatizar el navegador pone en riesgo la cuenta;
- aviso de "marcar como vendido" cuando un producto se queda sin stock.

## Pendientes abiertos

- Clave de API de Binance (solo lectura) en el `.env` para cobros reales.
- Probar la versión de Windows 7 en el PC de la tienda.
- Subir el servidor al hosting.
