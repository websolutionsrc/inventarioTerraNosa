from django.contrib import admin

from .models import EntradaInventario, Producto, SalidaInventario, Usuario, Venta


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ('username', 'is_staff', 'is_active', 'last_login')
    exclude = ('password',)


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'proveedor', 'precio', 'stock', 'activo')
    list_filter = ('activo', 'tipo')
    search_fields = ('nombre', 'proveedor')
    readonly_fields = ('stock',)


class LineaInline(admin.TabularInline):
    model = SalidaInventario
    extra = 0
    can_delete = False
    readonly_fields = ('producto', 'cantidad', 'precio_unitario')


@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    """Solo consulta: las ventas se crean y anulan desde la app."""
    list_display = ('id', 'fecha', 'usuario', 'metodo_pago', 'canal', 'total', 'anulada', 'anulada_por')
    list_filter = ('anulada', 'metodo_pago', 'canal')
    inlines = [LineaInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EntradaInventario)
class MovimientoAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'producto', 'tipo', 'cantidad', 'stock_resultante', 'usuario_admin', 'motivo')
    list_filter = ('tipo',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
