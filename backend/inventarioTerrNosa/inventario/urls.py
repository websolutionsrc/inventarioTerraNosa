from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (ConfigView, LoginView, LogoutView, MovimientoStockViewSet, ProductoViewSet, TasasView,
                    UsuarioViewSet, VentaViewSet, YoView)

router = DefaultRouter()
router.register(r'usuarios', UsuarioViewSet)
router.register(r'productos', ProductoViewSet, basename='producto')
router.register(r'movimientos', MovimientoStockViewSet, basename='movimiento')
router.register(r'ventas', VentaViewSet, basename='venta')

urlpatterns = [
    path('api/login/', LoginView.as_view(), name='api-login'),
    path('api/logout/', LogoutView.as_view(), name='api-logout'),
    path('api/yo/', YoView.as_view(), name='api-yo'),
    path('api/config/', ConfigView.as_view(), name='api-config'),
    path('api/tasas/', TasasView.as_view(), name='api-tasas'),
    path('api/', include(router.urls)),
]
