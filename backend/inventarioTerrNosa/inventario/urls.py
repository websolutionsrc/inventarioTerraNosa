from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EntradaInventarioViewSet, UsuarioViewSet, ProductoViewSet, VentaViewSet, SalidaInventarioViewSet, VentaAdminViewSet, SalidaInventarioAdminViewSet, LoginView

# Create a router and register viewsets
router = DefaultRouter()
router.register(r'usuarios', UsuarioViewSet)
router.register(r'productos', ProductoViewSet)
router.register(r'entradas', EntradaInventarioViewSet)  # This now has GET/POST for staff, DELETE for all
router.register(r'ventas', VentaViewSet)
router.register(r'salidas', SalidaInventarioViewSet)


router.register(r'admin/ventas', VentaAdminViewSet, basename='admin-venta')
router.register(r'admin/salidas', SalidaInventarioAdminViewSet, basename='admin-salidas')
# Include router-generated URLs
urlpatterns = [
    path('api/', include(router.urls)), # Main API endpoint
    path('api/login', LoginView.as_view(), name="api-login"),
]
