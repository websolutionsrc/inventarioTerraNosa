"""
Modelos del inventario de TerraNosa.

El stock de un producto solo cambia a través de inventario/services.py, que deja
siempre un registro: una línea de venta (SalidaInventario) o un movimiento manual
(EntradaInventario). Nada se borra de verdad: los productos se desactivan y las
ventas se anulan, para que el admin pueda ver qué pasó.
"""
from decimal import Decimal

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UsuarioManager(BaseUserManager):
    def create_user(self, username, password, is_staff=False, is_active=True):
        if not username:
            raise ValueError("El usuario debe tener un nombre de usuario")
        if not password:
            raise ValueError("El usuario debe tener una contraseña")
        user = self.model(username=username, is_staff=is_staff, is_admin=is_staff, is_active=is_active)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password):
        user = self.create_user(username, password, is_staff=True)
        user.is_superuser = True
        user.save(using=self._db)
        return user


class Usuario(AbstractBaseUser, PermissionsMixin):
    """is_staff = admin (inventario, historial, usuarios). Sin is_staff = encargado."""
    username = models.CharField(max_length=150, unique=True)
    is_admin = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    groups = models.ManyToManyField(
        "auth.Group",
        related_name="usuario_set",
        blank=True
    )
    user_permissions = models.ManyToManyField(
        "auth.Permission",
        related_name="usuario_permission_set",
        blank=True
    )

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []

    objects = UsuarioManager()

    def __str__(self):
        return self.username


class Producto(models.Model):
    nombre = models.CharField(max_length=255)
    tipo = models.CharField(max_length=255, blank=True, default='')
    proveedor = models.CharField(max_length=255, blank=True, default='')
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))  # USD
    stock = models.IntegerField(default=0)
    stock_minimo = models.PositiveIntegerField(default=0)  # se resalta cuando stock <= stock_minimo
    activo = models.BooleanField(default=True)  # "eliminar" lo desactiva y conserva su historial
    creado = models.DateTimeField(auto_now_add=True, null=True)
    actualizado = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} - Stock: {self.stock}"


class EntradaInventario(models.Model):
    """Movimiento manual de stock hecho por un admin: entrada de mercancía o ajuste."""

    class Tipo(models.TextChoices):
        INICIAL = 'inicial', 'Stock inicial'
        ENTRADA = 'entrada', 'Entrada de mercancía'
        AJUSTE = 'ajuste', 'Ajuste'

    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='movimientos')
    usuario_admin = models.ForeignKey(Usuario, on_delete=models.PROTECT)
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.ENTRADA)
    cantidad = models.IntegerField()  # negativa en ajustes que restan
    stock_resultante = models.IntegerField(null=True, blank=True)
    motivo = models.CharField(max_length=255, blank=True, default='')
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha', '-id']


class Venta(models.Model):

    class MetodoPago(models.TextChoices):
        EFECTIVO_USD = 'efectivo_usd', 'Efectivo $'
        EFECTIVO_BS = 'efectivo_bs', 'Efectivo Bs'
        PAGO_MOVIL = 'pago_movil', 'Pago móvil'
        PUNTO = 'punto', 'Punto de venta'
        TRANSFERENCIA = 'transferencia', 'Transferencia'
        ZELLE = 'zelle', 'Zelle'
        BINANCE = 'binance', 'Binance (USDT)'
        OTRO = 'otro', 'Otro'

    class Canal(models.TextChoices):
        TIENDA = 'tienda', 'Tienda'
        MARKETPLACE = 'marketplace', 'Marketplace'
        WHATSAPP = 'whatsapp', 'WhatsApp'
        OTRO = 'otro', 'Otro'

    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name='ventas')
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)
    metodo_pago = models.CharField(max_length=20, choices=MetodoPago.choices, default=MetodoPago.EFECTIVO_USD)
    canal = models.CharField(max_length=20, choices=Canal.choices, default=Canal.TIENDA)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))  # USD

    # Anulación: la venta sigue en la base de datos; el encargado deja de verla y el admin
    # la ve marcada con quién, cuándo y por qué.
    anulada = models.BooleanField(default=False)
    anulada_por = models.ForeignKey(Usuario, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name='ventas_anuladas')
    anulada_en = models.DateTimeField(null=True, blank=True)
    motivo_anulacion = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['-fecha', '-id']

    def delete(self, *args, **kwargs):
        raise RuntimeError("Las ventas no se borran: se anulan con services.anular_venta().")


class TasaCambio(models.Model):
    """Última tasa conocida de cada fuente (Bs por USD). La rellena inventario/tasas.py."""

    class Fuente(models.TextChoices):
        BCV = 'bcv', 'BCV (oficial)'
        BDV = 'bdv', 'Banco de Venezuela'
        BINANCE = 'binance', 'Binance P2P (USDT)'

    fuente = models.CharField(max_length=10, choices=Fuente.choices)
    fecha_valor = models.DateField()
    compra = models.DecimalField(max_digits=16, decimal_places=4)
    venta = models.DecimalField(max_digits=16, decimal_places=4)
    obtenida_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-obtenida_en']
        constraints = [models.UniqueConstraint(fields=['fuente', 'fecha_valor'], name='tasa_unica_por_dia')]

    def __str__(self):
        return '{} {} {}/{}'.format(self.fuente, self.fecha_valor, self.compra, self.venta)


class SalidaInventario(models.Model):
    """Línea de una venta. Guarda el precio del momento para que el historial no cambie."""
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='lineas')
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='salidas')
    cantidad = models.IntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)  # null en ventas antiguas
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    @property
    def subtotal(self):
        return (self.precio_unitario or Decimal('0')) * self.cantidad
