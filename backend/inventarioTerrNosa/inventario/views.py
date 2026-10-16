from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import EntradaInventario, Producto, Usuario, Venta
from .serializers import (AnularVentaSerializer, MovimientoStockSerializer, MoverStockSerializer,
                          NuevaVentaSerializer, ProductoSerializer, UsuarioSerializer, VentaSerializer)

VERSION_API = '2.0.0'


class SoloAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class LecturaTodosEscrituraAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_staff


def _error(mensaje):
    return Response({'detail': str(mensaje)}, status=status.HTTP_400_BAD_REQUEST)


def _fecha(valor, nombre):
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError):
        raise ValidationError({nombre: 'Usa el formato AAAA-MM-DD.'})


def _datos_usuario(user):
    return {'id': user.id, 'username': user.username, 'is_staff': user.is_staff}


# --- Sesión -------------------------------------------------------------------------

class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'login'

    def post(self, request):
        user = authenticate(username=request.data.get("username"), password=request.data.get("password"))
        if not user:
            return Response({"detail": "Usuario o contraseña incorrectos."}, status=status.HTTP_400_BAD_REQUEST)
        token, _ = Token.objects.get_or_create(user=user)
        update_last_login(None, user)
        # "token" e "is_staff" en la raíz se mantienen para la app 1.x
        return Response({"token": token.key, "is_staff": user.is_staff, "usuario": _datos_usuario(user)})


class LogoutView(APIView):
    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class YoView(APIView):
    def get(self, request):
        return Response(_datos_usuario(request.user))


class ConfigView(APIView):
    """Opciones que la app muestra en desplegables, para no tenerlas repetidas en el cliente."""

    def get(self, request):
        return Response({
            'version_api': VERSION_API,
            'zona_horaria': settings.TIME_ZONE,
            'hoy': timezone.localdate().isoformat(),
            'moneda': 'USD',
            'metodos_pago': [{'id': k, 'nombre': v} for k, v in Venta.MetodoPago.choices],
            'canales': [{'id': k, 'nombre': v} for k, v in Venta.Canal.choices],
        })


# --- Productos y stock --------------------------------------------------------------

class ProductoViewSet(viewsets.ModelViewSet):
    """
    GET para todos (el encargado solo ve los activos). Crear, editar y desactivar: admin.
    El stock no se edita aquí: usa /productos/{id}/mover_stock/.
    """
    serializer_class = ProductoSerializer
    permission_classes = [permissions.IsAuthenticated, LecturaTodosEscrituraAdmin]

    def get_queryset(self):
        qs = Producto.objects.all()
        if not (self.request.user.is_staff and self.request.query_params.get('incluir_inactivos') == '1'):
            qs = qs.filter(activo=True)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = dict(serializer.validated_data)
        stock_inicial = datos.pop('stock_inicial', 0)
        try:
            producto = services.crear_producto(request.user, datos, stock_inicial)
        except services.ErrorNegocio as e:
            return _error(e)
        return Response(self.get_serializer(producto).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        serializer.validated_data.pop('stock_inicial', None)
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        """No se borra: se desactiva para conservar ventas y movimientos."""
        producto = self.get_object()
        producto.activo = False
        producto.save(update_fields=['activo', 'actualizado'])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def reactivar(self, request, pk=None):
        producto = get_object_or_404(Producto, pk=pk)
        producto.activo = True
        producto.save(update_fields=['activo', 'actualizado'])
        return Response(self.get_serializer(producto).data)

    @action(detail=True, methods=['post'])
    def mover_stock(self, request, pk=None):
        """{"tipo": "entrada"|"ajuste", "cantidad": n, "motivo": "..."}"""
        self.get_object()
        datos = MoverStockSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            movimiento = services.mover_stock(pk, request.user, **datos.validated_data)
        except services.ErrorNegocio as e:
            return _error(e)
        return Response(MovimientoStockSerializer(movimiento).data, status=status.HTTP_201_CREATED)


class MovimientoStockViewSet(viewsets.ReadOnlyModelViewSet):
    """Registro de entradas y ajustes de stock (solo admin). Filtros: producto, desde, hasta."""
    serializer_class = MovimientoStockSerializer
    permission_classes = [SoloAdmin]

    def get_queryset(self):
        qs = EntradaInventario.objects.select_related('producto', 'usuario_admin')
        params = self.request.query_params
        if params.get('producto'):
            qs = qs.filter(producto_id=params['producto'])
        if params.get('desde'):
            qs = qs.filter(fecha__gte=services.rango_del_dia(_fecha(params['desde'], 'desde'))[0])
        if params.get('hasta'):
            qs = qs.filter(fecha__lt=services.rango_del_dia(_fecha(params['hasta'], 'hasta'))[1])
        return qs


# --- Ventas -------------------------------------------------------------------------

class VentaViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                   viewsets.GenericViewSet):
    """
    Encargado: ve solo las ventas de hoy que no están anuladas, y puede anularlas.
    Admin: ve todas, anuladas incluidas. Filtros: fecha o desde/hasta (AAAA-MM-DD; por
    defecto hoy), estado (activas|anuladas|todas), usuario, metodo_pago, canal.
    Las ventas no se editan ni se borran.
    """
    serializer_class = VentaSerializer

    def _rango(self):
        params = self.request.query_params
        if not self.request.user.is_staff:
            return services.rango_del_dia()
        if params.get('fecha'):
            return services.rango_del_dia(_fecha(params['fecha'], 'fecha'))
        desde = _fecha(params['desde'], 'desde') if params.get('desde') else None
        hasta = _fecha(params['hasta'], 'hasta') if params.get('hasta') else None
        if not desde and not hasta:
            return services.rango_del_dia()
        desde = desde or hasta
        hasta = hasta or timezone.localdate()
        if hasta < desde:
            raise ValidationError({'hasta': 'Debe ser posterior a "desde".'})
        return services.rango_del_dia(desde)[0], services.rango_del_dia(hasta)[1]

    def get_queryset(self):
        qs = (Venta.objects.select_related('usuario', 'anulada_por')
              .prefetch_related('lineas__producto'))
        user = self.request.user
        params = self.request.query_params

        if self.action in ('list', 'resumen') or not user.is_staff:
            inicio, fin = self._rango()
            qs = qs.filter(fecha__gte=inicio, fecha__lt=fin)

        if not user.is_staff:
            return qs.filter(anulada=False)

        estado = params.get('estado', 'todas')
        if estado == 'activas':
            qs = qs.filter(anulada=False)
        elif estado == 'anuladas':
            qs = qs.filter(anulada=True)
        for campo in ('metodo_pago', 'canal'):
            if params.get(campo):
                qs = qs.filter(**{campo: params[campo]})
        if params.get('usuario'):
            qs = qs.filter(usuario__username=params['usuario'])
        return qs

    def create(self, request, *args, **kwargs):
        datos = NuevaVentaSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            venta = services.registrar_venta(request.user, **datos.validated_data)
        except services.ErrorNegocio as e:
            return _error(e)
        venta = Venta.objects.prefetch_related('lineas__producto').get(pk=venta.pk)
        return Response(self.get_serializer(venta).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        """{"motivo": "..."}: anula la venta y devuelve el stock."""
        venta = self.get_object()
        datos = AnularVentaSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            services.anular_venta(venta.pk, request.user, datos.validated_data['motivo'])
        except services.ErrorNegocio as e:
            return _error(e)
        return Response({'detail': 'Venta anulada y stock devuelto.', 'id': venta.pk})

    @action(detail=False, methods=['get'])
    def resumen(self, request):
        """Totales del periodo (por defecto hoy), por método de pago y por canal."""
        def importe(valor):
            return str((valor or Decimal('0')).quantize(Decimal('0.01')))

        qs = self.get_queryset()
        activas = qs.filter(anulada=False)

        def agrupar(campo, opciones):
            filas = activas.values(campo).annotate(ventas=Count('id'), total=Sum('total')).order_by(campo)
            nombres = dict(opciones)
            return [{'id': f[campo], 'nombre': nombres.get(f[campo], f[campo]),
                     'ventas': f['ventas'], 'total': importe(f['total'])} for f in filas]

        inicio, fin = self._rango()
        datos = {
            'desde': timezone.localtime(inicio).date().isoformat(),
            'hasta': (timezone.localtime(fin) - timedelta(days=1)).date().isoformat(),
            'ventas': activas.count(),
            'total': importe(activas.aggregate(t=Sum('total'))['t']),
            'por_metodo_pago': agrupar('metodo_pago', Venta.MetodoPago.choices),
            'por_canal': agrupar('canal', Venta.Canal.choices),
        }
        if request.user.is_staff:
            anuladas = qs.filter(anulada=True).aggregate(n=Count('id'), t=Sum('total'))
            datos['anuladas'] = {'ventas': anuladas['n'], 'total': importe(anuladas['t'])}
        return Response(datos)


# --- Usuarios -----------------------------------------------------------------------

class UsuarioViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                     mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Solo admin. Los usuarios no se borran: se desactivan (is_active=false)."""
    queryset = Usuario.objects.all().order_by('username')
    serializer_class = UsuarioSerializer
    permission_classes = [SoloAdmin]

    def perform_update(self, serializer):
        if serializer.instance == self.request.user and (
                serializer.validated_data.get('is_active') is False
                or serializer.validated_data.get('is_staff') is False):
            raise ValidationError({'detail': 'No puedes quitarte el acceso de admin a ti mismo.'})
        user = serializer.save()
        if not user.is_active:
            Token.objects.filter(user=user).delete()
