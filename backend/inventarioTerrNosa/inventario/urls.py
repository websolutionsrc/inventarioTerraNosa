from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (CobroBinanceViewSet, CompraViewSet, ConfigView, PinView, RentabilidadViewSet, LoginView, LogoutView, MovimientoStockViewSet, ProductoViewSet, TasasView,
                    UsuarioViewSet, VentaViewSet, YoView)

router = DefaultRouter()
router.register(r'usuarios', UsuarioViewSet)
router.register(r'productos', ProductoViewSet, basename='producto')
router.register(r'movimientos', MovimientoStockViewSet, basename='movimiento')
router.register(r'ventas', VentaViewSet, basename='venta')
router.register(r'cobros-binance', CobroBinanceViewSet, basename='cobro-binance')
router.register(r'compras', CompraViewSet, basename='compra')
router.register(r'rentabilidad', RentabilidadViewSet, basename='rentabilidad')

urlpatterns = [
    path('api/login/', LoginView.as_view(), name='api-login'),
    path('api/logout/', LogoutView.as_view(), name='api-logout'),
    path('api/yo/', YoView.as_view(), name='api-yo'),
    path('api/config/', ConfigView.as_view(), name='api-config'),
    path('api/tasas/', TasasView.as_view(), name='api-tasas'),
    path('api/rentabilidad/pin/', PinView.as_view(), name='api-pin'),
    path('api/', include(router.urls)),
]
