from rest_framework import serializers
from .models import Usuario, Producto, EntradaInventario, Venta, SalidaInventario

class UsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = '__all__'
        extra_kwargs = {'password': {'write_only': True}}  # Hide password in GET responses

    def create(self, validated_data):
        user = Usuario.objects.create(username=validated_data['username'])
        user.set_password(validated_data['password'])  # Hash the password
        user.save()
        return user

class ProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Producto
        fields = '__all__'

class EntradaInventarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntradaInventario
        fields = '__all__'
        extra_kwargs = {'usuario_admin': {'required': False}}
        
    def create(self, validated_data):
        validated_data['usuario_admin'] = self.context['request'].user  # Assign user from token
        return super().create(validated_data)
        

class VentaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Venta
        fields = '__all__'
        extra_kwargs = {'usuario': {'required': False}}
        
    def create(self, validated_data):
        validated_data['usuario'] = self.context['request'].user  # Assign user from token
        return super().create(validated_data)

class SalidaInventarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalidaInventario
        fields = '__all__'
