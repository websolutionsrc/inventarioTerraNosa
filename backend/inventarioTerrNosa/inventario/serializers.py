from decimal import Decimal

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import CobroBinance, EntradaInventario, Producto, SalidaInventario, Usuario, Venta


class UsuarioSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=8)

    class Meta:
        model = Usuario
        fields = ['id', 'username', 'is_staff', 'is_active', 'password', 'created_at', 'last_login']
        read_only_fields = ['created_at', 'last_login']

    def validate(self, attrs):
        if self.instance is None and not attrs.get('password'):
            raise serializers.ValidationError({'password': 'La contraseña es obligatoria.'})
        if attrs.get('password'):
            validate_password(attrs['password'], Usuario(username=attrs.get('username', '')))
        return attrs

    def create(self, validated_data):
        return Usuario.objects.create_user(validated_data['username'], validated_data['password'],
                                           is_staff=validated_data.get('is_staff', False),
                                           is_active=validated_data.get('is_active', True))

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for campo, valor in validated_data.items():
            setattr(instance, campo, valor)
        instance.is_admin = instance.is_staff
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class ProductoSerializer(serializers.ModelSerializer):
    # El stock solo se fija al crear; después cambia con ventas, entradas o ajustes.
    stock_inicial = serializers.IntegerField(write_only=True, required=False, min_value=0)
    stock_bajo = serializers.SerializerMethodField()

    class Meta:
        model = Producto
        fields = ['id', 'nombre', 'tipo', 'proveedor', 'precio', 'stock', 'stock_minimo', 'stock_bajo',
                  'activo', 'stock_inicial', 'creado', 'actualizado']
        read_only_fields = ['stock', 'activo', 'creado', 'actualizado']

    def get_stock_bajo(self, obj):
        return obj.stock <= obj.stock_minimo

    def validate_precio(self, valor):
        if valor < 0:
            raise serializers.ValidationError('El precio no puede ser negativo.')
        return valor


class MovimientoStockSerializer(serializers.ModelSerializer):
    usuario = serializers.CharField(source='usuario_admin.username', read_only=True)
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)

    class Meta:
        model = EntradaInventario
        fields = ['id', 'producto', 'producto_nombre', 'tipo', 'cantidad', 'stock_resultante', 'motivo',
                  'usuario', 'fecha']


class MoverStockSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=[EntradaInventario.Tipo.ENTRADA, EntradaInventario.Tipo.AJUSTE])
    cantidad = serializers.IntegerField()
    motivo = serializers.CharField(required=False, allow_blank=True, max_length=255)


class LineaVentaSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = SalidaInventario
        fields = ['producto', 'producto_nombre', 'cantidad', 'precio_unitario', 'subtotal']


class VentaSerializer(serializers.ModelSerializer):
    """Lectura de ventas. Los datos de anulación solo se incluyen para el admin (ver la vista)."""
    usuario = serializers.CharField(source='usuario.username', read_only=True)
    lineas = LineaVentaSerializer(many=True, read_only=True)
    metodo_pago_nombre = serializers.CharField(source='get_metodo_pago_display', read_only=True)
    canal_nombre = serializers.CharField(source='get_canal_display', read_only=True)
    anulada_por = serializers.CharField(source='anulada_por.username', read_only=True, default=None)
    moneda = serializers.SerializerMethodField()
    pago_binance = serializers.SerializerMethodField()

    class Meta:
        model = Venta
        fields = ['id', 'fecha', 'usuario', 'metodo_pago', 'metodo_pago_nombre', 'moneda', 'canal', 'canal_nombre',
                  'total', 'tasa_cambio', 'tasa_bcv', 'total_bs', 'pago_binance', 'lineas', 'anulada', 'anulada_por',
                  'anulada_en', 'motivo_anulacion']

    def get_moneda(self, obj):
        return Venta.moneda_de(obj.metodo_pago)

    def get_pago_binance(self, obj):
        cobro = getattr(obj, 'cobro_binance', None)
        if not cobro:
            return None
        return {'monto_recibido': str(cobro.monto_recibido), 'pagador': cobro.pagador,
                'transaccion_id': cobro.transaccion_id}

    CAMPOS_ANULACION = ('anulada', 'anulada_por', 'anulada_en', 'motivo_anulacion')

    def to_representation(self, instance):
        datos = super().to_representation(instance)
        usuario = self.context['request'].user
        if not usuario.is_staff:
            for campo in self.CAMPOS_ANULACION:
                datos.pop(campo, None)
        return datos


class NuevaLineaSerializer(serializers.Serializer):
    producto = serializers.IntegerField()
    cantidad = serializers.IntegerField(min_value=1, max_value=9999)


class NuevaVentaSerializer(serializers.Serializer):
    lineas = NuevaLineaSerializer(many=True, allow_empty=False)
    metodo_pago = serializers.ChoiceField(choices=Venta.MetodoPago.choices)
    canal = serializers.ChoiceField(choices=Venta.Canal.choices, default=Venta.Canal.TIENDA)

    def validate_metodo_pago(self, valor):
        if valor in Venta.METODOS_RETIRADOS:
            raise serializers.ValidationError('Este método de pago ya no se acepta.')
        return valor

    # Bs por dólar para cobros en bolívares; si no viene se usa la del BCV
    tasa = serializers.DecimalField(max_digits=16, decimal_places=4, required=False, allow_null=True,
                                    min_value=Decimal('0.0001'))


class AnularVentaSerializer(serializers.Serializer):
    motivo = serializers.CharField(max_length=255, allow_blank=False, trim_whitespace=True)


class CobroBinanceSerializer(serializers.ModelSerializer):
    estado_nombre = serializers.CharField(source='get_estado_display', read_only=True)
    segundos_restantes = serializers.SerializerMethodField()
    minimo = serializers.SerializerMethodField()
    venta = serializers.SerializerMethodField()

    class Meta:
        model = CobroBinance
        fields = ['id', 'estado', 'estado_nombre', 'monto', 'minimo', 'creado', 'expira', 'segundos_restantes',
                  'transaccion_id', 'monto_recibido', 'pagador', 'pagado_en', 'venta', 'error']

    def get_segundos_restantes(self, obj):
        from django.utils import timezone
        return max(0, int((obj.expira - timezone.now()).total_seconds()))

    def get_minimo(self, obj):
        from . import binance
        return str(binance.margen(obj.monto)[0].quantize(Decimal('0.01')))

    def get_venta(self, obj):
        return VentaSerializer(obj.venta, context=self.context).data if obj.venta else None


class NuevoCobroBinanceSerializer(serializers.Serializer):
    lineas = NuevaLineaSerializer(many=True, allow_empty=False)
    canal = serializers.ChoiceField(choices=Venta.Canal.choices, default=Venta.Canal.TIENDA)
