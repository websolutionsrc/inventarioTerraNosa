from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
from django.db import transaction
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from . import binance, rentabilidad, services, tasas
from .models import AjustesNegocio, CobroBinance, Compra, EntradaInventario, LoteCompra, Producto, Usuario, Venta
from .serializers import (AnularVentaSerializer, CambioPrecioSerializer, CobroBinanceSerializer, CompraSerializer, MovimientoStockSerializer,
                          NuevaCompraSerializer, PagoCompraSerializer,
                          MoverStockSerializer, NuevoCobroBinanceSerializer,
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
            'metodos_pago': [{'id': k, 'nombre': v, 'moneda': Venta.moneda_de(k)}
                             for k, v in Venta.MetodoPago.choices if k not in Venta.METODOS_RETIRADOS],
            'binance': {
                'verificacion': binance.configurado(),
                'simulado': binance.simulado(),
                'pay_id': settings.BINANCE_PAY_ID,
                'minutos': settings.BINANCE_MINUTOS_COBRO,
            },
            'canales': [{'id': k, 'nombre': v} for k, v in Venta.Canal.choices],
        })


class TasasView(APIView):
    """
    Tasas de referencia Bs/USD: BCV (oficial) y Banco de Venezuela (no oficial).
    Se refrescan como mucho cada 30 minutos; ?actualizar=1 fuerza la consulta (solo admin).
    """

    def get(self, request):
        forzar = request.user.is_staff and request.query_params.get('actualizar') == '1'
        return Response(tasas.resumen(forzar=forzar))


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
        datos.pop('motivo_precio', None)
        try:
            producto = services.crear_producto(request.user, datos, stock_inicial)
        except services.ErrorNegocio as e:
            return _error(e)
        return Response(self.get_serializer(producto).data, status=status.HTTP_201_CREATED)

    @transaction.atomic
    def perform_update(self, serializer):
        serializer.validated_data.pop('stock_inicial', None)
        motivo = serializer.validated_data.pop('motivo_precio', '') or 'Edición del artículo'
        anterior = serializer.instance.precio
        producto = serializer.save()
        services.anotar_precio(producto, self.request.user, anterior, producto.precio, motivo)

    @action(detail=True, methods=['get'])
    def precios(self, request, pk=None):
        """Historial de cambios del precio de venta (solo admin)."""
        if not request.user.is_staff:
            return Response(status=status.HTTP_403_FORBIDDEN)
        producto = get_object_or_404(Producto, pk=pk)
        return Response(CambioPrecioSerializer(producto.cambios_precio.select_related('usuario'), many=True).data)

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
        if (datos.validated_data['metodo_pago'] == Venta.MetodoPago.BINANCE and binance.configurado()
                and not request.user.is_staff):
            return _error('Los pagos con Binance se verifican: usa el cobro con Binance de la app.')
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
            filas = (activas.values(campo).annotate(ventas=Count('id'), total=Sum('total'), total_bs=Sum('total_bs'))
                     .order_by(campo))
            nombres = dict(opciones)
            return [{'id': f[campo], 'nombre': nombres.get(f[campo], f[campo]), 'ventas': f['ventas'],
                     'total': importe(f['total']),
                     'total_bs': importe(f['total_bs']) if f['total_bs'] is not None else None} for f in filas]

        inicio, fin = self._rango()
        datos = {
            'desde': timezone.localtime(inicio).date().isoformat(),
            'hasta': (timezone.localtime(fin) - timedelta(days=1)).date().isoformat(),
            'ventas': activas.count(),
            'total': importe(activas.aggregate(t=Sum('total'))['t']),
            'total_bs': importe(activas.aggregate(t=Sum('total_bs'))['t']),  # lo cobrado en bolívares
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


# --- Cobros con Binance Pay ---------------------------------------------------------

class CobroBinanceViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    POST {lineas, canal}: abre un cobro y devuelve el monto en USDT que hay que recibir.
    GET {id}: consulta Binance (si sigue pendiente) y devuelve el estado; al confirmarse
    trae la venta creada. POST {id}/cancelar/: cancela el cobro si aún no se pagó.
    """
    serializer_class = CobroBinanceSerializer

    def get_queryset(self):
        qs = CobroBinance.objects.select_related('venta')
        return qs if self.request.user.is_staff else qs.filter(usuario=self.request.user)

    def create(self, request, *args, **kwargs):
        datos = NuevoCobroBinanceSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            cobro = services.crear_cobro_binance(request.user, **datos.validated_data)
        except services.ErrorNegocio as e:
            return _error(e)
        return Response(self.get_serializer(cobro).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        cobro = self.get_object()
        error = None
        if cobro.estado == CobroBinance.Estado.PENDIENTE:
            error = services.conciliar_binance()
            cobro.refresh_from_db()
        datos = self.get_serializer(cobro).data
        datos['aviso'] = error  # p. ej. Binance no responde: se sigue intentando
        return Response(datos)

    @action(detail=True, methods=['post'])
    def cancelar(self, request, pk=None):
        cobro = self.get_object()
        services.conciliar_binance()  # por si el pago llegó justo ahora
        cobro = services.cancelar_cobro_binance(cobro.pk)
        return Response(self.get_serializer(cobro).data)


# --- Compras a proveedores (solo admin) -------------------------------------------------

class CompraViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                    viewsets.GenericViewSet):
    """
    Compras con sus lotes. Filtro ?estado=pendientes|pagadas|anuladas. Se pagan de una vez
    (contado o a los N meses) con POST {id}/pagar/; POST {id}/anular/ si no salió nada.
    GET previsiones/: tasas de hoy, ritmo de subida y % cobrado en dólares (para estimar precios).
    """
    serializer_class = CompraSerializer
    permission_classes = [SoloAdmin]

    def get_queryset(self):
        qs = Compra.objects.select_related('usuario').prefetch_related('lotes__producto')
        estado = self.request.query_params.get('estado')
        if estado == 'pendientes':
            qs = qs.filter(pagada=False, anulada=False)
        elif estado == 'pagadas':
            qs = qs.filter(pagada=True, anulada=False)
        elif estado == 'anuladas':
            qs = qs.filter(anulada=True)
        return qs

    def create(self, request, *args, **kwargs):
        datos = NuevaCompraSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        d = dict(datos.validated_data)
        lineas = [dict(l) for l in d.pop('lineas')]
        try:
            compra = services.registrar_compra(request.user, lineas, **d)
        except services.ErrorNegocio as e:
            return _error(e)
        return Response(self.get_serializer(Compra.objects.get(pk=compra.pk)).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def pagar(self, request, pk=None):
        compra = self.get_object()
        datos = PagoCompraSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            services.registrar_pago_compra(compra.pk, **datos.validated_data)
        except services.ErrorNegocio as e:
            return _error(e)
        return Response(self.get_serializer(Compra.objects.get(pk=compra.pk)).data)

    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        compra = self.get_object()
        try:
            services.anular_compra(compra.pk, request.user)
        except services.ErrorNegocio as e:
            return _error(e)
        return Response(self.get_serializer(Compra.objects.get(pk=compra.pk)).data)

    @action(detail=False, methods=['get'])
    def previsiones(self, request):
        datos = services.previsiones_compra()
        pendientes = Compra.objects.filter(pagada=False, anulada=False)
        datos['pendiente_usd'] = sum((c.total_factura for c in pendientes if not c.en_bolivares_fijos), Decimal('0'))
        datos['pendiente_bs'] = sum((c.total_factura for c in pendientes if c.en_bolivares_fijos), Decimal('0'))
        proxima = pendientes.order_by('vence').first()
        datos['proximo_vencimiento'] = CompraSerializer(proxima).data if proxima else None
        datos['proveedores'] = sorted({p for p in Compra.objects.values_list('proveedor', flat=True) if p})
        return Response({k: (str(v) if isinstance(v, Decimal) else v) for k, v in datos.items()})


# --- Panel de rentabilidad (admin + PIN de gerencia) ------------------------------------

PIN_MINUTOS = 15
CABECERA_PIN = 'HTTP_X_PIN_GERENCIA'


def _token_pin(usuario):
    from django.core import signing
    return signing.dumps({'u': usuario.id}, salt='rentabilidad')


def _pin_valido(request):
    from django.core import signing
    token = request.META.get(CABECERA_PIN, '')
    try:
        datos = signing.loads(token, salt='rentabilidad', max_age=PIN_MINUTOS * 60)
    except signing.BadSignature:
        return False
    return datos.get('u') == request.user.id


class ConPinDeGerencia(permissions.BasePermission):
    message = 'Introduce el PIN de gerencia (caduca a los {} minutos).'.format(PIN_MINUTOS)

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff and _pin_valido(request))


class PinView(APIView):
    """
    GET: si ya hay PIN definido. POST {pin}: entra y devuelve un token de 15 minutos.
    POST {pin_nuevo, pin_actual?}: define o cambia el PIN (pin_actual obligatorio para cambiarlo).
    """
    permission_classes = [SoloAdmin]
    throttle_scope = 'pin'

    def get_throttles(self):
        # Solo cuentan los intentos de entrar o cambiar el PIN
        return super(PinView, self).get_throttles() if self.request.method == 'POST' else []

    def get(self, request):
        return Response({'definido': bool(AjustesNegocio.actuales().pin_hash), 'minutos': PIN_MINUTOS})

    def post(self, request):
        from django.contrib.auth.hashers import check_password, make_password
        ajustes = AjustesNegocio.actuales()
        nuevo = (request.data.get('pin_nuevo') or '').strip()
        if nuevo:
            if not nuevo.isdigit() or not 4 <= len(nuevo) <= 8:
                return _error('El PIN debe tener entre 4 y 8 números.')
            if ajustes.pin_hash and not check_password(request.data.get('pin_actual') or '', ajustes.pin_hash):
                return _error('El PIN actual no es correcto.')
            ajustes.pin_hash = make_password(nuevo)
            ajustes.save(update_fields=['pin_hash', 'actualizado'])
            return Response({'token': _token_pin(request.user), 'minutos': PIN_MINUTOS})
        if not ajustes.pin_hash:
            return _error('Aún no hay PIN de gerencia: defínelo primero.')
        if not check_password(request.data.get('pin') or '', ajustes.pin_hash):
            return _error('PIN incorrecto.')
        return Response({'token': _token_pin(request.user), 'minutos': PIN_MINUTOS})


def _como_texto(dato):
    """Decimales y fechas como texto, igual que en el resto de la API."""
    from datetime import date as _date, datetime as _datetime
    if isinstance(dato, dict):
        return {k: _como_texto(v) for k, v in dato.items()}
    if isinstance(dato, (list, tuple)):
        return [_como_texto(v) for v in dato]
    if isinstance(dato, Decimal):
        return str(dato)
    if isinstance(dato, _datetime):
        return timezone.localtime(dato).isoformat()
    if isinstance(dato, _date):
        return dato.isoformat()
    return dato


class RentabilidadViewSet(viewsets.ViewSet):
    """
    Panel de rentabilidad. Todas las consultas aceptan ?escenario=factura|usdt|bcv|otra&tasa=…
    para estimar las compras pendientes de pagar "si se pagasen hoy".
    """
    permission_classes = [ConPinDeGerencia]

    def _ctx(self, request):
        p = request.query_params
        try:
            return rentabilidad.Contexto(p.get('escenario', 'factura'), p.get('tasa') or None)
        except Exception:
            raise ValidationError({'tasa': 'Tasa no válida.'})

    @action(detail=False, methods=['get'])
    def resumen(self, request):
        p = request.query_params
        hoy = timezone.localdate()
        desde = _fecha(p['desde'], 'desde') if p.get('desde') else hoy.replace(day=1)
        hasta = _fecha(p['hasta'], 'hasta') if p.get('hasta') else hoy
        return Response(_como_texto(rentabilidad.resumen(self._ctx(request), desde, hasta)))

    @action(detail=False, methods=['get'])
    def lotes(self, request):
        return Response(_como_texto(rentabilidad.lotes(self._ctx(request), request.query_params.get('estado'))))

    @action(detail=False, methods=['get'], url_path=r'lotes/(?P<lote_id>\d+)')
    def lote(self, request, lote_id=None):
        lote = get_object_or_404(LoteCompra.objects.select_related('compra', 'producto'), pk=lote_id)
        return Response(_como_texto(rentabilidad.analizar_lote(lote, self._ctx(request))))

    @action(detail=False, methods=['get'])
    def articulos(self, request):
        return Response(_como_texto(rentabilidad.articulos(self._ctx(request))))

    @action(detail=False, methods=['patch'])
    def ajustes(self, request):
        ajustes = AjustesNegocio.actuales()
        try:
            margen = Decimal(str(request.data.get('margen_objetivo')))
        except Exception:
            return _error('Margen objetivo no válido.')
        if not 0 < margen < 100:
            return _error('El margen objetivo debe estar entre 0 y 100 %.')
        ajustes.margen_objetivo = margen
        ajustes.save(update_fields=['margen_objetivo', 'actualizado'])
        return Response({'margen_objetivo': str(ajustes.margen_objetivo)})
