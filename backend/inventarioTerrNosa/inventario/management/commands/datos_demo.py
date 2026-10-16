"""
Carga datos de prueba en la base de datos LOCAL: usuarios, productos y algunas ventas.

    python manage.py datos_demo            (solo si la base está vacía)
    python manage.py datos_demo --borrar   (borra ventas, movimientos y productos antes)

Usuarios de prueba (solo para desarrollo, cámbialos en el hosting):
    admin / admin-terranosa         (admin)
    encargado / encargado-terranosa (encargado)
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from inventario import services
from inventario.models import (CobroBinance, EntradaInventario, IngresoBinanceSimulado, Producto, SalidaInventario,
                               TasaCambio, Usuario, Venta)

USUARIOS = [('admin', 'admin-terranosa', True), ('encargado', 'encargado-terranosa', False)]

# nombre, tipo, proveedor, precio USD, stock, stock mínimo
PRODUCTOS = [
    ('Morral Nike impermeable', 'Morrales', 'Nike', '25.00', 12, 3),
    ('Morral táctico 55L', 'Morrales', 'Genérico', '38.00', 6, 2),
    ('Morral montañero 75L', 'Morrales', 'Genérico', '45.00', 4, 2),
    ('Morral juvenil estampado', 'Morrales', 'Totto', '18.50', 15, 4),
    ('Morral de malla transparente', 'Morrales', 'Genérico', '12.00', 8, 2),
    ('Bolso cruzado de caballero', 'Caballero', 'Genérico', '16.00', 7, 2),
    ('Billetera de cuero caballero', 'Billeteras', 'Artesanal', '14.00', 20, 5),
    ('Cartera de dama con asa', 'Dama', 'Genérico', '22.00', 9, 3),
    ('Bolso tote de dama', 'Dama', 'Genérico', '19.90', 2, 3),
    ('Lonchera térmica infantil', 'Loncheras', 'Genérico', '9.50', 10, 3),
    ('Maleta de viaje 20"', 'Viaje', 'Samsonite', '65.00', 3, 1),
    ('Bolso de viaje con ruedas', 'Viaje', 'Genérico', '42.00', 1, 1),
    ('Maletín ejecutivo', 'Maletines', 'Genérico', '35.00', 5, 2),
    ('Cartuchera escolar', 'Cartucheras', 'Totto', '6.00', 25, 5),
    ('Paraguas plegable', 'Accesorios', 'Genérico', '8.00', 0, 2),
]


class Command(BaseCommand):
    help = 'Carga usuarios, productos y ventas de prueba en la base de datos local.'

    def add_arguments(self, parser):
        parser.add_argument('--borrar', action='store_true', help='Borra ventas, movimientos y productos antes.')

    def handle(self, *args, **opciones):
        if not settings.DEBUG:
            raise CommandError('datos_demo solo se usa en local (DEBUG activado).')

        if opciones['borrar']:
            CobroBinance.objects.all().delete()
            IngresoBinanceSimulado.objects.all().delete()
            SalidaInventario.objects.all().delete()
            Venta.objects.all().delete()
            EntradaInventario.objects.all().delete()
            Producto.objects.all().delete()
        elif Producto.objects.exists():
            raise CommandError('Ya hay productos. Usa --borrar para empezar de cero.')

        for username, clave, staff in USUARIOS:
            user = Usuario.objects.filter(username=username).first()
            if not user:
                user = Usuario.objects.create_user(username, clave, is_staff=staff)
                if staff:
                    user.is_superuser = True
                    user.save()
        admin = Usuario.objects.get(username='admin')
        encargado = Usuario.objects.get(username='encargado')

        productos = []
        for nombre, tipo, proveedor, precio, stock, minimo in PRODUCTOS:
            productos.append(services.crear_producto(admin, {
                'nombre': nombre, 'tipo': tipo, 'proveedor': proveedor,
                'precio': Decimal(precio), 'stock_minimo': minimo}, stock))

        # Las ventas en bolívares necesitan una tasa del BCV; si aún no se consultó, una de ejemplo
        if not TasaCambio.objects.filter(fuente=TasaCambio.Fuente.BCV).exists():
            TasaCambio.objects.create(fuente=TasaCambio.Fuente.BCV, fecha_valor=timezone.localdate(),
                                      compra=Decimal('880.1159'), venta=Decimal('880.1159'))

        p = {i: prod.id for i, prod in enumerate(productos)}
        # Ventas de ayer (se mueven de fecha después de crearlas)
        ayer = [
            services.registrar_venta(encargado, [{'producto': p[0], 'cantidad': 1}], 'efectivo_usd', 'tienda'),
            services.registrar_venta(encargado, [{'producto': p[6], 'cantidad': 2}], 'pago_movil', 'marketplace'),
        ]
        Venta.objects.filter(id__in=[v.id for v in ayer]).update(fecha=timezone.now() - timedelta(days=1))

        # Ventas de hoy, una anulada
        services.registrar_venta(encargado, [{'producto': p[3], 'cantidad': 2}, {'producto': p[13], 'cantidad': 2}],
                                 'efectivo_usd', 'tienda')
        services.registrar_venta(encargado, [{'producto': p[7], 'cantidad': 1}], 'punto', 'tienda')
        mal = services.registrar_venta(encargado, [{'producto': p[1], 'cantidad': 1}], 'pago_movil', 'whatsapp')
        services.anular_venta(mal.id, encargado, 'Se cobró el morral equivocado')
        services.registrar_venta(encargado, [{'producto': p[2], 'cantidad': 1}], 'transferencia', 'whatsapp')
        services.mover_stock(p[4], admin, EntradaInventario.Tipo.AJUSTE, -1, 'Llegó con el cierre roto')

        self.stdout.write(self.style.SUCCESS(
            f'Listo: {len(productos)} productos, {Venta.objects.count()} ventas y {len(USUARIOS)} usuarios '
            '(ver contraseñas en inventario/management/commands/datos_demo.py).'))
