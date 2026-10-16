from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from .models import EntradaInventario, Producto, Usuario, Venta


class BaseAPI(APITestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user('admin', 'clave-admin-123', is_staff=True)
        self.encargado = Usuario.objects.create_user('encargado', 'clave-encargado-123')
        self.morral = Producto.objects.create(nombre='Morral Nike', precio=Decimal('25.50'), stock=10)
        self.bolso = Producto.objects.create(nombre='Bolso dama', precio=Decimal('18.00'), stock=3)

    def como(self, usuario):
        self.client.force_authenticate(usuario)

    def vender(self, lineas, metodo='efectivo_usd', canal='tienda'):
        return self.client.post('/api/ventas/', {'lineas': lineas, 'metodo_pago': metodo, 'canal': canal},
                                format='json')

    def recargar(self):
        self.morral.refresh_from_db()
        self.bolso.refresh_from_db()


class LoginTests(BaseAPI):
    def test_login_devuelve_token_y_rol(self):
        r = self.client.post('/api/login/', {'username': 'encargado', 'password': 'clave-encargado-123'})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['token'])
        self.assertFalse(r.data['is_staff'])
        self.assertEqual(r.data['usuario']['username'], 'encargado')
        self.encargado.refresh_from_db()
        self.assertIsNotNone(self.encargado.last_login)

    def test_login_incorrecto(self):
        r = self.client.post('/api/login/', {'username': 'encargado', 'password': 'mal'})
        self.assertEqual(r.status_code, 400)

    def test_logout_invalida_el_token(self):
        token = self.client.post('/api/login/', {'username': 'admin', 'password': 'clave-admin-123'}).data['token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')
        self.assertEqual(self.client.post('/api/logout/').status_code, 204)
        self.assertEqual(self.client.get('/api/yo/').status_code, 401)


class VentaTests(BaseAPI):
    def test_venta_descuenta_stock_y_guarda_precio(self):
        self.como(self.encargado)
        r = self.vender([{'producto': self.morral.id, 'cantidad': 2}, {'producto': self.bolso.id, 'cantidad': 1}],
                        metodo='pago_movil', canal='marketplace')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(Decimal(r.data['total']), Decimal('69.00'))
        self.recargar()
        self.assertEqual((self.morral.stock, self.bolso.stock), (8, 2))

        # Cambiar el precio después no altera la venta
        self.morral.precio = Decimal('99.00')
        self.morral.save()
        venta = Venta.objects.get(pk=r.data['id'])
        self.assertEqual(venta.total, Decimal('69.00'))
        self.assertEqual(venta.lineas.get(producto=self.morral).precio_unitario, Decimal('25.50'))

    def test_pago_con_binance(self):
        self.como(self.encargado)
        metodos = [m['id'] for m in self.client.get('/api/config/').data['metodos_pago']]
        self.assertIn('binance', metodos)
        r = self.vender([{'producto': self.bolso.id, 'cantidad': 1}], metodo='binance')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['metodo_pago_nombre'], 'Binance (USDT)')

    def test_el_cliente_no_puede_poner_el_precio(self):
        self.como(self.encargado)
        r = self.client.post('/api/ventas/', {'lineas': [{'producto': self.morral.id, 'cantidad': 1,
                                                          'precio_unitario': '0.01'}],
                                              'metodo_pago': 'efectivo_usd'}, format='json')
        self.assertEqual(Decimal(r.data['total']), Decimal('25.50'))

    def test_stock_insuficiente_no_registra_nada(self):
        self.como(self.encargado)
        r = self.vender([{'producto': self.morral.id, 'cantidad': 1}, {'producto': self.bolso.id, 'cantidad': 4}])
        self.assertEqual(r.status_code, 400)
        self.assertIn('Stock insuficiente', r.data['detail'])
        self.recargar()
        self.assertEqual((self.morral.stock, self.bolso.stock), (10, 3))
        self.assertEqual(Venta.objects.count(), 0)

    def test_lineas_repetidas_se_suman(self):
        self.como(self.encargado)
        r = self.vender([{'producto': self.bolso.id, 'cantidad': 2}, {'producto': self.bolso.id, 'cantidad': 2}])
        self.assertEqual(r.status_code, 400)  # 4 > 3 en stock
        r = self.vender([{'producto': self.bolso.id, 'cantidad': 1}, {'producto': self.bolso.id, 'cantidad': 2}])
        self.assertEqual(r.status_code, 201)
        self.assertEqual(len(r.data['lineas']), 1)

    def test_no_se_vende_producto_inactivo(self):
        self.morral.activo = False
        self.morral.save()
        self.como(self.encargado)
        r = self.vender([{'producto': self.morral.id, 'cantidad': 1}])
        self.assertEqual(r.status_code, 400)

    def test_ventas_no_se_editan_ni_borran(self):
        self.como(self.admin)
        venta_id = self.vender([{'producto': self.morral.id, 'cantidad': 1}]).data['id']
        self.assertEqual(self.client.delete(f'/api/ventas/{venta_id}/').status_code, 405)
        self.assertEqual(self.client.put(f'/api/ventas/{venta_id}/', {}, format='json').status_code, 405)


class AnulacionTests(BaseAPI):
    def setUp(self):
        super().setUp()
        self.como(self.encargado)
        self.venta_id = self.vender([{'producto': self.morral.id, 'cantidad': 3}]).data['id']

    def anular(self, venta_id=None, motivo='Me equivoqué de producto'):
        return self.client.post(f'/api/ventas/{venta_id or self.venta_id}/anular/', {'motivo': motivo}, format='json')

    def test_encargado_anula_y_vuelve_el_stock(self):
        r = self.anular()
        self.assertEqual(r.status_code, 200, r.data)
        self.recargar()
        self.assertEqual(self.morral.stock, 10)
        venta = Venta.objects.get(pk=self.venta_id)
        self.assertTrue(venta.anulada)
        self.assertEqual(venta.anulada_por, self.encargado)
        self.assertEqual(venta.motivo_anulacion, 'Me equivoqué de producto')

    def test_motivo_obligatorio(self):
        self.assertEqual(self.anular(motivo='  ').status_code, 400)
        self.recargar()
        self.assertEqual(self.morral.stock, 7)

    def test_no_se_anula_dos_veces(self):
        self.anular()
        self.como(self.admin)
        r = self.anular()
        self.assertEqual(r.status_code, 400)
        self.recargar()
        self.assertEqual(self.morral.stock, 10)

    def test_encargado_no_ve_las_anuladas_y_admin_si(self):
        otra = self.vender([{'producto': self.bolso.id, 'cantidad': 1}]).data['id']
        self.anular()
        ids = [v['id'] for v in self.client.get('/api/ventas/').data]
        self.assertEqual(ids, [otra])
        self.assertNotIn('anulada', self.client.get(f'/api/ventas/{otra}/').data)
        self.assertEqual(self.client.get(f'/api/ventas/{self.venta_id}/').status_code, 404)

        self.como(self.admin)
        datos = {v['id']: v for v in self.client.get('/api/ventas/').data}
        self.assertTrue(datos[self.venta_id]['anulada'])
        self.assertEqual(datos[self.venta_id]['anulada_por'], 'encargado')
        self.assertEqual([v['id'] for v in self.client.get('/api/ventas/?estado=anuladas').data], [self.venta_id])

    def test_encargado_puede_anular_ventas_de_otro_del_mismo_dia(self):
        otro = Usuario.objects.create_user('encargado2', 'clave-encargado-456')
        self.como(otro)
        self.assertEqual(self.anular().status_code, 200)

    def test_encargado_no_anula_ni_ve_ventas_de_ayer(self):
        Venta.objects.filter(pk=self.venta_id).update(fecha=timezone.now() - timedelta(days=1))
        self.assertEqual(self.anular().status_code, 404)
        self.assertEqual(self.client.get('/api/ventas/').data, [])
        self.como(self.admin)
        ayer = (timezone.localdate() - timedelta(days=1)).isoformat()
        self.assertEqual(len(self.client.get(f'/api/ventas/?fecha={ayer}').data), 1)
        self.assertEqual(self.anular().status_code, 200)

    def test_resumen_del_dia(self):
        self.vender([{'producto': self.bolso.id, 'cantidad': 1}], metodo='zelle')
        self.anular()
        r = self.client.get('/api/ventas/resumen/')
        self.assertEqual(r.data['ventas'], 1)
        self.assertEqual(r.data['total'], '18.00')
        self.assertEqual(r.data['por_metodo_pago'][0]['id'], 'zelle')
        self.assertNotIn('anuladas', r.data)
        self.como(self.admin)
        r = self.client.get('/api/ventas/resumen/')
        self.assertEqual(r.data['anuladas']['ventas'], 1)

    def test_resumen_del_admin_respeta_las_fechas(self):
        Venta.objects.filter(pk=self.venta_id).update(fecha=timezone.now() - timedelta(days=1))
        self.vender([{'producto': self.bolso.id, 'cantidad': 1}])
        self.como(self.admin)
        hoy = self.client.get('/api/ventas/resumen/').data
        self.assertEqual((hoy['ventas'], hoy['total']), (1, '18.00'))
        ayer = (timezone.localdate() - timedelta(days=1)).isoformat()
        dos_dias = self.client.get(f'/api/ventas/resumen/?desde={ayer}').data
        self.assertEqual((dos_dias['ventas'], dos_dias['total']), (2, '94.50'))


class ProductoYStockTests(BaseAPI):
    def test_encargado_no_modifica_productos(self):
        self.como(self.encargado)
        self.assertEqual(self.client.get('/api/productos/').status_code, 200)
        self.assertEqual(self.client.post('/api/productos/', {'nombre': 'X'}).status_code, 403)
        self.assertEqual(self.client.post(f'/api/productos/{self.morral.id}/mover_stock/',
                                          {'tipo': 'entrada', 'cantidad': 5}).status_code, 403)

    def test_crear_con_stock_inicial_deja_registro(self):
        self.como(self.admin)
        r = self.client.post('/api/productos/', {'nombre': 'Lonchera', 'precio': '9.99', 'stock_inicial': 4})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['stock'], 4)
        mov = EntradaInventario.objects.get(producto_id=r.data['id'])
        self.assertEqual((mov.tipo, mov.cantidad, mov.usuario_admin), ('inicial', 4, self.admin))

    def test_el_stock_no_se_edita_directo(self):
        self.como(self.admin)
        r = self.client.patch(f'/api/productos/{self.morral.id}/', {'stock': 999, 'precio': '30.00'})
        self.assertEqual(r.status_code, 200)
        self.recargar()
        self.assertEqual((self.morral.stock, self.morral.precio), (10, Decimal('30.00')))

    def test_entrada_y_ajuste(self):
        self.como(self.admin)
        url = f'/api/productos/{self.morral.id}/mover_stock/'
        self.assertEqual(self.client.post(url, {'tipo': 'entrada', 'cantidad': 5}).status_code, 201)
        self.assertEqual(self.client.post(url, {'tipo': 'ajuste', 'cantidad': -2}).status_code, 400)  # sin motivo
        r = self.client.post(url, {'tipo': 'ajuste', 'cantidad': -2, 'motivo': 'Dañado'})
        self.assertEqual(r.data['stock_resultante'], 13)
        self.assertEqual(self.client.post(url, {'tipo': 'ajuste', 'cantidad': -50, 'motivo': 'x'}).status_code, 400)
        self.assertEqual(len(self.client.get(f'/api/movimientos/?producto={self.morral.id}').data), 2)

    def test_eliminar_desactiva_y_conserva_historial(self):
        self.como(self.encargado)
        self.vender([{'producto': self.morral.id, 'cantidad': 1}])
        self.como(self.admin)
        self.assertEqual(self.client.delete(f'/api/productos/{self.morral.id}/').status_code, 204)
        self.assertTrue(Producto.objects.filter(pk=self.morral.id, activo=False).exists())
        self.assertEqual(len(self.client.get('/api/ventas/').data), 1)
        self.como(self.encargado)
        self.assertEqual([p['id'] for p in self.client.get('/api/productos/').data], [self.bolso.id])


class UsuarioTests(BaseAPI):
    def test_solo_admin_gestiona_usuarios(self):
        self.como(self.encargado)
        self.assertEqual(self.client.get('/api/usuarios/').status_code, 403)
        self.como(self.admin)
        r = self.client.post('/api/usuarios/', {'username': 'nuevo', 'password': 'una-clave-larga-1'})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertNotIn('password', r.data)
        self.assertTrue(Usuario.objects.get(username='nuevo').check_password('una-clave-larga-1'))

    def test_admin_no_se_quita_el_acceso(self):
        self.como(self.admin)
        r = self.client.patch(f'/api/usuarios/{self.admin.id}/', {'is_staff': False})
        self.assertEqual(r.status_code, 400)


HTML_BCV = '''<div id="dolar" class="col-sm-12"><div class="field-content"><span> USD</span></div>
<div class="centrado"><strong class="strong-tb"> 880,11590000 </strong></div></div>
<div class="pull-right dinpro">Fecha Valor: <span class="date-display-single"
content="2026-10-16T00:00:00-04:00">Viernes, 16 Octubre 2026</span></div>'''

HTML_BDV = '''<div>Compra</div><div>Bs.S 865,18</div><div>Venta</div><div>Bs.S 890,68</div>
<div>Spread 2,95%</div>'''


class TasasTests(BaseAPI):
    def test_lee_las_paginas(self):
        from . import tasas
        self.assertEqual(tasas.leer_bcv(HTML_BCV), (Decimal('880.11590000'), date(2026, 10, 16)))
        self.assertEqual(tasas.leer_bdv(HTML_BDV), (Decimal('865.18'), Decimal('890.68')))
        self.assertEqual(tasas._numero('1.234,5'), Decimal('1234.5'))
        with self.assertRaises(tasas.ErrorTasa):
            tasas.leer_bcv('<html>sin datos</html>')

    def test_endpoint_guarda_y_reutiliza(self):
        from unittest import mock
        from . import tasas
        paginas = {tasas.URL_BCV: HTML_BCV, tasas.URL_BDV: HTML_BDV}
        self.como(self.encargado)
        with mock.patch.object(tasas, '_descargar', side_effect=lambda url: paginas[url]) as descargar:
            r = self.client.get('/api/tasas/')
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.data['bcv']['venta'], '880.1159')
            self.assertEqual(r.data['bcv']['fecha_valor'], '2026-10-16')
            self.assertTrue(r.data['bcv']['oficial'])
            self.assertEqual((r.data['bdv']['compra'], r.data['bdv']['venta']), ('865.1800', '890.6800'))
            self.assertFalse(r.data['bdv']['oficial'])
            self.client.get('/api/tasas/')
            self.assertEqual(descargar.call_count, 2)  # la segunda vez usa lo guardado

    def test_si_la_web_falla_devuelve_la_ultima(self):
        from unittest import mock
        from . import tasas
        from .models import TasaCambio
        TasaCambio.objects.create(fuente='bcv', fecha_valor=date(2026, 10, 15), compra=Decimal('879'),
                                  venta=Decimal('879'))
        TasaCambio.objects.filter(fuente='bcv').update(obtenida_en=timezone.now() - timedelta(hours=2))
        self.como(self.encargado)
        with mock.patch.object(tasas, '_descargar', side_effect=tasas.ErrorTasa('sin conexión')):
            r = self.client.get('/api/tasas/')
        self.assertEqual(r.data['bcv']['venta'], '879.0000')
        self.assertTrue(r.data['bcv']['desactualizada'])
        self.assertIsNone(r.data['bdv']['venta'])

    def test_solo_admin_fuerza_la_actualizacion(self):
        from unittest import mock
        from . import tasas
        paginas = {tasas.URL_BCV: HTML_BCV, tasas.URL_BDV: HTML_BDV}
        with mock.patch.object(tasas, '_descargar', side_effect=lambda url: paginas[url]) as descargar:
            self.como(self.encargado)
            self.client.get('/api/tasas/')
            self.client.get('/api/tasas/?actualizar=1')
            self.assertEqual(descargar.call_count, 2)
            self.como(self.admin)
            self.client.get('/api/tasas/?actualizar=1')
            self.assertEqual(descargar.call_count, 4)
