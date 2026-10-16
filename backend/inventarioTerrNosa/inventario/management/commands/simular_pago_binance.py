"""
Simula que llega un pago por Binance Pay (solo en local, con BINANCE_SIMULADO=true y DEBUG).

    python manage.py simular_pago_binance 30
    python manage.py simular_pago_binance 29.95 --pagador "Ana P."
"""
import uuid
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from inventario import binance
from inventario.models import IngresoBinanceSimulado


class Command(BaseCommand):
    help = 'Simula un ingreso de USDT por Binance Pay para probar los cobros sin clave de API.'

    def add_arguments(self, parser):
        parser.add_argument('monto', type=Decimal)
        parser.add_argument('--pagador', default='Cliente de prueba')

    def handle(self, *args, **opciones):
        if not binance.simulado():
            raise CommandError('Activa BINANCE_SIMULADO=true (y DEBUG) en el .env para simular pagos.')
        ingreso = IngresoBinanceSimulado.objects.create(
            transaccion_id='SIM-' + uuid.uuid4().hex[:12], monto=opciones['monto'], pagador=opciones['pagador'])
        self.stdout.write(self.style.SUCCESS('Pago simulado: {} USDT de {} ({})'.format(
            ingreso.monto, ingreso.pagador, ingreso.transaccion_id)))
