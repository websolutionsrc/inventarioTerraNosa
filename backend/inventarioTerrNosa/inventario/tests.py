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
        self._tasa_bcv()
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

    def _tasa_bcv(self, valor='880.1159'):
        from .models import TasaCambio
        TasaCambio.objects.create(fuente='bcv', fecha_valor=timezone.localdate(), compra=Decimal(valor),
                                  venta=Decimal(valor))

    def test_venta_en_bolivares_guarda_la_tasa_bcv(self):
        self._tasa_bcv()
        self.como(self.encargado)
        r = self.vender([{'producto': self.bolso.id, 'cantidad': 2}], metodo='pago_movil')  # 36 $
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['moneda'], 'VES')
        self.assertEqual((r.data['tasa_cambio'], r.data['tasa_bcv']), ('880.1159', '880.1159'))
        self.assertEqual(r.data['total_bs'], '31684.17')

    def test_venta_en_bolivares_con_tasa_propia(self):
        self._tasa_bcv()
        self.como(self.encargado)
        r = self.client.post('/api/ventas/', {'lineas': [{'producto': self.bolso.id, 'cantidad': 1}],
                                              'metodo_pago': 'efectivo_bs', 'tasa': '950'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual((r.data['tasa_cambio'], r.data['tasa_bcv'], r.data['total_bs']),
                         ('950.0000', '880.1159', '17100.00'))
        resumen = self.client.get('/api/ventas/resumen/').data
        self.assertEqual(resumen['total_bs'], '17100.00')
        self.assertEqual(resumen['por_metodo_pago'][0]['total_bs'], '17100.00')

    def test_venta_en_dolares_no_guarda_tasa(self):
        self._tasa_bcv()
        self.como(self.encargado)
        r = self.client.post('/api/ventas/', {'lineas': [{'producto': self.bolso.id, 'cantidad': 1}],
                                              'metodo_pago': 'efectivo_usd', 'tasa': '950'}, format='json')
        self.assertEqual(r.data['moneda'], 'USD')
        self.assertIsNone(r.data['tasa_cambio'])
        self.assertIsNone(r.data['total_bs'])

    def test_sin_tasa_no_se_cobra_en_bolivares(self):
        self.como(self.encargado)
        r = self.vender([{'producto': self.bolso.id, 'cantidad': 1}], metodo='efectivo_bs')
        self.assertEqual(r.status_code, 400)
        self.bolso.refresh_from_db()
        self.assertEqual(self.bolso.stock, 3)
        r = self.client.post('/api/ventas/', {'lineas': [{'producto': self.bolso.id, 'cantidad': 1}],
                                              'metodo_pago': 'efectivo_bs', 'tasa': '0'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_config_indica_la_moneda_de_cada_metodo(self):
        self.como(self.encargado)
        monedas = {m['id']: m['moneda'] for m in self.client.get('/api/config/').data['metodos_pago']}
        self.assertEqual((monedas['pago_movil'], monedas['efectivo_bs'], monedas['efectivo_usd'], monedas['binance']),
                         ('VES', 'VES', 'USD', 'USDT'))

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
        self.vender([{'producto': self.bolso.id, 'cantidad': 1}], metodo='efectivo_usd')
        self.anular()
        r = self.client.get('/api/ventas/resumen/')
        self.assertEqual(r.data['ventas'], 1)
        self.assertEqual(r.data['total'], '18.00')
        self.assertEqual(r.data['por_metodo_pago'][0]['id'], 'efectivo_usd')
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


def _binance_json(precios):
    import json
    return json.dumps({'code': '000000', 'data': [{'adv': {'price': p}} for p in precios]})


BINANCE = {'BUY': _binance_json(['994.50', '996.00', '996.00', '1200.00', '996.10']),
           'SELL': _binance_json(['995.00', '993.50', '993.00', '700.00'])}


def _webs_falsas(url, datos=None):
    from . import tasas
    if url == tasas.URL_BINANCE:
        return BINANCE[datos['tradeType']]
    return {tasas.URL_BCV: HTML_BCV}[url]


class TasasTests(BaseAPI):
    def test_lee_las_fuentes(self):
        from . import tasas
        self.assertEqual(tasas.leer_bcv(HTML_BCV), (Decimal('880.11590000'), date(2026, 10, 16)))
        # Mediana: un anuncio raro (1200 o 700) no mueve la tasa
        self.assertEqual(tasas.leer_binance(BINANCE['BUY']), Decimal('996.00'))
        self.assertEqual(tasas.leer_binance(BINANCE['SELL']), Decimal('993.25'))
        self.assertEqual(tasas._numero('1.234,5'), Decimal('1234.5'))
        with self.assertRaises(tasas.ErrorTasa):
            tasas.leer_bcv('<html>sin datos</html>')
        with self.assertRaises(tasas.ErrorTasa):
            tasas.leer_binance('{"data": []}')

    def test_endpoint_guarda_y_reutiliza(self):
        from unittest import mock
        from . import tasas
        self.como(self.encargado)
        with mock.patch.object(tasas, '_descargar', side_effect=_webs_falsas) as descargar:
            r = self.client.get('/api/tasas/')
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.data['bcv']['venta'], '880.1159')
            self.assertEqual(r.data['bcv']['fecha_valor'], '2026-10-16')
            self.assertTrue(r.data['bcv']['oficial'])
            self.assertNotIn('bdv', r.data)
            self.assertEqual((r.data['binance']['compra'], r.data['binance']['venta']), ('996.0000', '993.2500'))
            self.assertFalse(r.data['binance']['oficial'])
            self.client.get('/api/tasas/')
            self.assertEqual(descargar.call_count, 3)  # BCV y Binance (2); la segunda vez usa lo guardado

    def test_si_una_fuente_falla_devuelve_la_ultima(self):
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
        self.assertIsNone(r.data['binance']['venta'])

    def test_solo_admin_fuerza_la_actualizacion(self):
        from unittest import mock
        from . import tasas
        with mock.patch.object(tasas, '_descargar', side_effect=_webs_falsas) as descargar:
            self.como(self.encargado)
            self.client.get('/api/tasas/')
            self.client.get('/api/tasas/?actualizar=1')
            self.assertEqual(descargar.call_count, 3)
            self.como(self.admin)
            self.client.get('/api/tasas/?actualizar=1')
            self.assertEqual(descargar.call_count, 6)


class ZelleTests(BaseAPI):
    def test_zelle_ya_no_se_ofrece_ni_se_acepta(self):
        self.como(self.encargado)
        metodos = [m['id'] for m in self.client.get('/api/config/').data['metodos_pago']]
        self.assertNotIn('zelle', metodos)
        r = self.vender([{'producto': self.bolso.id, 'cantidad': 1}], metodo='zelle')
        self.assertEqual(r.status_code, 400)


def _ingreso(monto, minutos=0, id_=None, pagador='Ana'):
    return {'id': id_ or 'TX{}{}'.format(monto, minutos), 'monto': Decimal(monto), 'pagador': pagador,
            'fecha': timezone.now() + timedelta(minutes=minutos), 'tipo': 'PAY'}


class CobroBinanceTests(BaseAPI):
    def setUp(self):
        super().setUp()
        from django.test import override_settings
        self._ajustes = override_settings(BINANCE_API_KEY='clave', BINANCE_API_SECRET='secreto')
        self._ajustes.enable()
        self.como(self.encargado)

    def tearDown(self):
        self._ajustes.disable()
        super().tearDown()

    def abrir(self, cantidad=2):  # 2 morrales = 51,00 USDT
        r = self.client.post('/api/cobros-binance/', {'lineas': [{'producto': self.morral.id, 'cantidad': cantidad}]},
                             format='json')
        self.assertEqual(r.status_code, 201, r.data)
        return r.data

    def consultar(self, cobro_id, ingresos):
        from unittest import mock
        from . import binance
        with mock.patch.object(binance, 'ingresos_desde', return_value=ingresos):
            return self.client.get('/api/cobros-binance/{}/'.format(cobro_id)).data

    def test_sin_pago_sigue_esperando_y_no_toca_el_stock(self):
        cobro = self.abrir()
        self.assertEqual((cobro['estado'], cobro['monto']), ('pendiente', '51.00'))
        self.assertEqual(self.consultar(cobro['id'], [])['estado'], 'pendiente')
        self.recargar()
        self.assertEqual(self.morral.stock, 10)

    def test_pago_exacto_crea_la_venta(self):
        cobro = self.abrir()
        datos = self.consultar(cobro['id'], [_ingreso('51.00', 1, 'TX1')])
        self.assertEqual(datos['estado'], 'confirmado')
        self.assertEqual(datos['venta']['metodo_pago'], 'binance')
        self.assertEqual(datos['venta']['pago_binance']['transaccion_id'], 'TX1')
        self.recargar()
        self.assertEqual(self.morral.stock, 8)

    def test_acepta_un_poco_menos_por_comision_pero_no_mucho_menos(self):
        cobro = self.abrir()  # 51 USDT: se acepta desde 50,49 (1 %)
        self.assertEqual(cobro['minimo'], '50.49')
        self.assertEqual(self.consultar(cobro['id'], [_ingreso('50.00', 1)])['estado'], 'pendiente')
        self.assertEqual(self.consultar(cobro['id'], [_ingreso('50.60', 1)])['estado'], 'confirmado')

    def test_no_vale_un_pago_anterior_al_cobro(self):
        cobro = self.abrir()
        self.assertEqual(self.consultar(cobro['id'], [_ingreso('51.00', -10)])['estado'], 'pendiente')

    def test_un_pago_sirve_para_un_solo_cobro(self):
        primero, segundo = self.abrir(), self.abrir()
        pago = [_ingreso('51.00', 1, 'TXUNICO')]
        self.assertEqual(self.consultar(segundo['id'], pago)['estado'], 'pendiente')  # va al más antiguo
        self.assertEqual(self.client.get('/api/cobros-binance/{}/'.format(primero['id'])).data['estado'],
                         'confirmado')
        dos_pagos = pago + [_ingreso('51.00', 2, 'TXOTRO')]
        self.assertEqual(self.consultar(segundo['id'], dos_pagos)['estado'], 'confirmado')

    def test_cancelar_y_caducar(self):
        from unittest import mock
        from . import binance
        from .models import CobroBinance
        cobro = self.abrir()
        with mock.patch.object(binance, 'ingresos_desde', return_value=[]):
            r = self.client.post('/api/cobros-binance/{}/cancelar/'.format(cobro['id']))
        self.assertEqual(r.data['estado'], 'cancelado')
        otro = self.abrir()
        CobroBinance.objects.filter(pk=otro['id']).update(expira=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.consultar(otro['id'], [])['estado'], 'expirado')

    def test_si_se_paga_justo_al_cancelar_gana_el_pago(self):
        from unittest import mock
        from . import binance
        cobro = self.abrir()
        with mock.patch.object(binance, 'ingresos_desde', return_value=[_ingreso('51.00', 1)]):
            r = self.client.post('/api/cobros-binance/{}/cancelar/'.format(cobro['id']))
        self.assertEqual(r.data['estado'], 'confirmado')

    def test_pagado_sin_stock_queda_para_el_admin(self):
        cobro = self.abrir(cantidad=10)
        self.morral.stock = 5
        self.morral.save()
        datos = self.consultar(cobro['id'], [_ingreso('255.00', 1)])
        self.assertEqual(datos['estado'], 'sin_venta')
        self.assertIn('Stock insuficiente', datos['error'])

    def test_binance_falla_y_se_sigue_esperando(self):
        from unittest import mock
        from . import binance
        cobro = self.abrir()
        with mock.patch.object(binance, 'ingresos_desde', side_effect=binance.ErrorBinance('caída')):
            datos = self.client.get('/api/cobros-binance/{}/'.format(cobro['id'])).data
        self.assertEqual((datos['estado'], datos['aviso']), ('pendiente', 'caída'))

    def test_el_encargado_no_puede_saltarse_la_verificacion(self):
        r = self.vender([{'producto': self.bolso.id, 'cantidad': 1}], metodo='binance')
        self.assertEqual(r.status_code, 400)

    def test_otro_encargado_no_ve_mi_cobro(self):
        cobro = self.abrir()
        otro = Usuario.objects.create_user('encargado2', 'clave-encargado-456')
        self.como(otro)
        self.assertEqual(self.client.get('/api/cobros-binance/{}/'.format(cobro['id'])).status_code, 404)

    def test_lee_la_respuesta_de_binance(self):
        from . import binance
        datos = binance.interpretar({'code': '000000', 'data': [
            {'orderType': 'PAY', 'transactionId': 'A1', 'transactionTime': 1760630400000, 'amount': '51.00',
             'currency': 'USDT', 'payerInfo': {'name': 'Ana'}},
            {'orderType': 'PAY', 'transactionId': 'A2', 'transactionTime': 1760630400000, 'amount': '-10',
             'currency': 'USDT'},
            {'orderType': 'C2C', 'transactionId': 'A3', 'transactionTime': 1760630400000, 'amount': '5',
             'currency': 'BNB'},
        ]})
        self.assertEqual([(d['id'], d['monto'], d['pagador']) for d in datos], [('A1', Decimal('51.00'), 'Ana')])
        with self.assertRaises(binance.ErrorBinance):
            binance.interpretar({'code': '-1022', 'message': 'firma no válida'})

    def test_firma_hmac(self):
        import hashlib
        import hmac
        from django.test import override_settings
        from . import binance
        with override_settings(BINANCE_API_SECRET='secreto'):
            url = binance._firmado({'timestamp': 1})
        esperada = hmac.new(b'secreto', b'timestamp=1', hashlib.sha256).hexdigest()
        self.assertTrue(url.endswith('?timestamp=1&signature=' + esperada))


class CompraTests(BaseAPI):
    """Compras al contado o a pagar en N meses, lotes y FIFO."""

    def setUp(self):
        super().setUp()
        from .models import TasaCambio
        TasaCambio.objects.create(fuente='bcv', fecha_valor=timezone.localdate(), compra=Decimal('880'),
                                  venta=Decimal('880'))
        TasaCambio.objects.create(fuente='binance', fecha_valor=timezone.localdate(), compra=Decimal('996'),
                                  venta=Decimal('993'))
        self.como(self.admin)

    def comprar(self, lineas, plazo=0, forma='bs_usdt', **extra):
        datos = {'lineas': lineas, 'plazo_meses': plazo, 'forma_pago': forma, 'proveedor': 'Proveedor X'}
        datos.update(extra)
        r = self.client.post('/api/compras/', datos, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        return r.data

    def lotes(self, producto):
        from .models import LoteCompra
        return [(l.cantidad, l.disponible) for l in LoteCompra.objects.filter(producto=producto).order_by('id')]

    def test_compra_a_pagar_en_3_meses_suma_stock_y_queda_pendiente(self):
        c = self.comprar([{'producto': self.morral.id, 'cantidad': 5, 'costo_unitario': '10.00'}], plazo=3)
        self.recargar()
        self.assertEqual(self.morral.stock, 15)
        self.assertEqual((c['estado'], c['pagada'], c['total_factura']), ('pendiente', False, '50.00'))
        self.assertEqual(c['vence'], services_sumar_meses(timezone.localdate(), 3).isoformat())
        pendientes = self.client.get('/api/compras/?estado=pendientes').data
        self.assertEqual([x['id'] for x in pendientes], [c['id']])

    def test_compra_al_contado_se_paga_en_el_acto_a_tasa_usdt(self):
        c = self.comprar([{'producto': self.morral.id, 'cantidad': 2, 'costo_unitario': '10.00'}])
        self.assertEqual((c['estado'], c['tasa_pago'], c['bs_pagados']), ('pagada', '996.0000', '19920.00'))

    def test_pagar_mas_tarde_con_tasa_propia_y_formas_de_pago(self):
        c = self.comprar([{'producto': self.morral.id, 'cantidad': 2, 'costo_unitario': '10.00'}], plazo=3)
        r = self.client.post('/api/compras/{}/pagar/'.format(c['id']), {'tasa_pago': '1130'}, format='json')
        self.assertEqual((r.data['estado'], r.data['bs_pagados']), ('pagada', '22600.00'))
        self.assertEqual(self.client.post('/api/compras/{}/pagar/'.format(c['id']), {}).status_code, 400)
        bcv = self.comprar([{'producto': self.bolso.id, 'cantidad': 1, 'costo_unitario': '5.00'}], forma='bs_bcv')
        self.assertEqual(bcv['tasa_pago'], '880.0000')
        usd = self.comprar([{'producto': self.bolso.id, 'cantidad': 1, 'costo_unitario': '5.00'}], forma='dolares')
        self.assertEqual((usd['usd_pagados'], usd['bs_pagados']), ('5.00', None))
        fijos = self.comprar([{'producto': self.bolso.id, 'cantidad': 1, 'costo_unitario': '4500.00'}],
                             forma='bs_fijos')
        self.assertEqual(fijos['bs_pagados'], '4500.00')

    def test_fifo_primero_el_stock_sin_compra_y_luego_el_lote_mas_antiguo(self):
        # El bolso tiene 3 unidades sin compra registrada; luego entran dos lotes
        self.comprar([{'producto': self.bolso.id, 'cantidad': 2, 'costo_unitario': '8.00'}], plazo=1,
                     fecha=(timezone.localdate() - timedelta(days=5)).isoformat())
        self.comprar([{'producto': self.bolso.id, 'cantidad': 4, 'costo_unitario': '9.00'}], plazo=1)
        self.como(self.encargado)
        self.vender([{'producto': self.bolso.id, 'cantidad': 4}])  # 3 sin lote + 1 del lote antiguo
        self.assertEqual(self.lotes(self.bolso), [(2, 1), (4, 4)])
        venta = self.vender([{'producto': self.bolso.id, 'cantidad': 3}]).data  # 1 del antiguo + 2 del nuevo
        self.assertEqual(self.lotes(self.bolso), [(2, 0), (4, 2)])
        self.client.post('/api/ventas/{}/anular/'.format(venta['id']), {'motivo': 'Prueba'}, format='json')
        self.assertEqual(self.lotes(self.bolso), [(2, 1), (4, 4)])  # vuelven a su lote

    def test_ajuste_negativo_sale_del_lote(self):
        self.morral.stock = 0
        self.morral.save()
        self.comprar([{'producto': self.morral.id, 'cantidad': 3, 'costo_unitario': '10.00'}])
        self.client.post('/api/productos/{}/mover_stock/'.format(self.morral.id),
                         {'tipo': 'ajuste', 'cantidad': -1, 'motivo': 'Dañado'})
        self.assertEqual(self.lotes(self.morral), [(3, 2)])

    def test_la_venta_guarda_la_tasa_usdt_del_dia(self):
        self.como(self.encargado)
        r = self.vender([{'producto': self.bolso.id, 'cantidad': 1}], metodo='pago_movil')
        self.assertEqual(r.data['tasa_usdt'], '996.0000')

    def test_anular_compra_solo_si_no_salio_nada(self):
        self.morral.stock = 0
        self.morral.save()
        c = self.comprar([{'producto': self.morral.id, 'cantidad': 3, 'costo_unitario': '10.00'}], plazo=2)
        otra = self.comprar([{'producto': self.morral.id, 'cantidad': 2, 'costo_unitario': '11.00'}], plazo=2)
        r = self.client.post('/api/compras/{}/anular/'.format(otra['id']))
        self.assertEqual(r.data['estado'], 'anulada')
        self.recargar()
        self.assertEqual(self.morral.stock, 3)
        self.como(self.encargado)
        self.vender([{'producto': self.morral.id, 'cantidad': 1}])
        self.como(self.admin)
        self.assertEqual(self.client.post('/api/compras/{}/anular/'.format(c['id'])).status_code, 400)

    def test_el_precio_de_venta_de_la_compra_queda_en_el_articulo(self):
        c = self.comprar([{'producto': self.morral.id, 'cantidad': 2, 'costo_unitario': '10.00',
                           'precio_venta': '27.50', 'precio_previsto': '27.50', 'margen_previsto': '51.30'},
                          {'producto': self.bolso.id, 'cantidad': 1, 'costo_unitario': '6.00'}], plazo=3)
        self.recargar()
        self.assertEqual((self.morral.precio, self.bolso.precio), (Decimal('27.50'), Decimal('18.00')))
        self.assertEqual(c['lotes'][0]['margen_previsto'], '51.30')

    def test_articulo_nuevo_entra_al_inventario_con_su_precio(self):
        c = self.comprar([{'nuevo_nombre': 'Morral escolar azul', 'cantidad': 8, 'costo_unitario': '7.00',
                           'precio_venta': '16.50'}], plazo=2)
        nuevo = Producto.objects.get(nombre='Morral escolar azul')
        self.assertEqual((nuevo.stock, nuevo.precio, nuevo.proveedor, nuevo.activo),
                         (8, Decimal('16.50'), 'Proveedor X', True))
        self.assertEqual(c['lotes'][0]['producto_nombre'], 'Morral escolar azul')
        # Sin precio, o con un nombre que ya existe, no se registra
        r = self.client.post('/api/compras/', {'lineas': [{'nuevo_nombre': 'Otro', 'cantidad': 1,
                                                           'costo_unitario': '1'}]}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.client.post('/api/compras/', {'lineas': [{'nuevo_nombre': 'morral nike',
                                                           'cantidad': 1, 'costo_unitario': '1',
                                                           'precio_venta': '5'}]}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Producto.objects.filter(nombre='Otro').exists())

    def test_errores_y_permisos(self):
        r = self.client.post('/api/compras/', {'lineas': [{'producto': self.morral.id, 'cantidad': 1,
                                                           'costo_unitario': '1'},
                                                          {'producto': self.morral.id, 'cantidad': 1,
                                                           'costo_unitario': '1'}]}, format='json')
        self.assertEqual(r.status_code, 400)
        self.como(self.encargado)
        self.assertEqual(self.client.get('/api/compras/').status_code, 403)

    def test_previsiones(self):
        self.como(self.encargado)
        self.vender([{'producto': self.bolso.id, 'cantidad': 1}], metodo='efectivo_usd')   # 18 $
        self.vender([{'producto': self.morral.id, 'cantidad': 1}], metodo='pago_movil')    # 25,50 $
        self.como(self.admin)
        self.comprar([{'producto': self.morral.id, 'cantidad': 1, 'costo_unitario': '10.00'}], plazo=3,
                     proveedor='Distribuidora Valencia')
        d = self.client.get('/api/compras/previsiones/').data
        self.assertEqual((d['bcv'], d['usdt']), ('880.0000', '996.0000'))
        self.assertEqual(d['porcentaje_dolares'], '41.4')
        self.assertIsNone(d['ritmo_usdt'])  # aún no hay historial
        self.assertEqual(d['pendiente_usd'], '10.00')
        self.assertIn('Distribuidora Valencia', d['proveedores'])


def services_sumar_meses(fecha, meses):
    from .services import sumar_meses
    return sumar_meses(fecha, meses)


class HistorialPreciosTests(BaseAPI):
    def setUp(self):
        super().setUp()
        self.como(self.admin)

    def historial(self, producto_id):
        r = self.client.get('/api/productos/{}/precios/'.format(producto_id))
        self.assertEqual(r.status_code, 200)
        return [(h['precio_anterior'], h['precio_nuevo'], h['motivo'], h['usuario']) for h in r.data]

    def test_alta_y_edicion_con_motivo(self):
        r = self.client.post('/api/productos/', {'nombre': 'Lonchera', 'precio': '9.99'})
        pid = r.data['id']
        self.client.patch('/api/productos/{}/'.format(pid), {'precio': '11.50', 'motivo_precio': 'Subió el costo'})
        self.client.patch('/api/productos/{}/'.format(pid), {'nombre': 'Lonchera térmica'})  # sin cambio de precio
        self.client.patch('/api/productos/{}/'.format(pid), {'precio': '12.00'})
        self.assertEqual(self.historial(pid), [
            ('11.50', '12.00', 'Edición del artículo', 'admin'),
            ('9.99', '11.50', 'Subió el costo', 'admin'),
            (None, '9.99', 'Alta del artículo', 'admin'),
        ])

    def test_cambios_desde_una_compra(self):
        r = self.client.post('/api/compras/', {'plazo_meses': 2, 'lineas': [
            {'producto': self.morral.id, 'cantidad': 1, 'costo_unitario': '10', 'precio_venta': '27.00'},
            {'producto': self.bolso.id, 'cantidad': 1, 'costo_unitario': '6', 'precio_venta': '18.00'},
            {'nuevo_nombre': 'Cartera nueva', 'cantidad': 2, 'costo_unitario': '5', 'precio_venta': '14.00'}]},
            format='json')
        compra = r.data['id']
        self.assertEqual(self.historial(self.morral.id), [('25.50', '27.00', 'Compra #{}'.format(compra), 'admin')])
        self.assertEqual(self.historial(self.bolso.id), [])  # el precio no cambió
        nuevo = Producto.objects.get(nombre='Cartera nueva')
        self.assertEqual(self.historial(nuevo.id), [(None, '14.00', 'Alta en la compra #{}'.format(compra), 'admin')])

    def test_las_ventas_conservan_su_precio(self):
        self.como(self.encargado)
        venta = self.vender([{'producto': self.morral.id, 'cantidad': 1}]).data
        self.como(self.admin)
        self.client.patch('/api/productos/{}/'.format(self.morral.id), {'precio': '30.00'})
        self.assertEqual(self.client.get('/api/ventas/{}/'.format(venta['id'])).data['lineas'][0]['precio_unitario'],
                         '25.50')

    def test_solo_admin_ve_el_historial(self):
        self.como(self.encargado)
        self.assertEqual(self.client.get('/api/productos/{}/precios/'.format(self.morral.id)).status_code, 403)


class RentabilidadTests(BaseAPI):
    """El ejemplo del diseño: 10 morrales a 10 $, a pagar en 3 meses en Bs a tasa USDT, vendidos a 25 $."""

    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.clear()  # límites de intentos del PIN
        from .models import TasaCambio
        TasaCambio.objects.create(fuente='bcv', fecha_valor=timezone.localdate(), compra=Decimal('880'),
                                  venta=Decimal('880'))
        TasaCambio.objects.create(fuente='binance', fecha_valor=timezone.localdate(), compra=Decimal('1000'),
                                  venta=Decimal('995'))
        self.mochila = Producto.objects.create(nombre='Morral táctico', precio=Decimal('25.00'), stock=0)
        self.como(self.admin)
        r = self.client.post('/api/compras/', {'plazo_meses': 3, 'forma_pago': 'bs_usdt', 'lineas': [
            {'producto': self.mochila.id, 'cantidad': 10, 'costo_unitario': '10.00'}]}, format='json')
        self.compra = r.data['id']
        self.lote = r.data['lotes'][0]['id']

    def entrar(self, pin='2468'):
        self.como(self.admin)
        self.client.post('/api/rentabilidad/pin/', {'pin_nuevo': pin}, format='json')
        r = self.client.post('/api/rentabilidad/pin/', {'pin': pin}, format='json')
        self.client.credentials(HTTP_X_PIN_GERENCIA=r.data['token'])

    def vender_en_bs(self, tasa, metodo='pago_movil'):
        self.como(self.encargado)
        r = self.client.post('/api/ventas/', {'lineas': [{'producto': self.mochila.id, 'cantidad': 1}],
                                              'metodo_pago': metodo, 'tasa': tasa}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        return r.data

    def test_sin_pin_no_se_ve_nada(self):
        self.assertEqual(self.client.get('/api/rentabilidad/resumen/').status_code, 403)
        self.assertFalse(self.client.get('/api/rentabilidad/pin/').data['definido'])
        self.assertEqual(self.client.post('/api/rentabilidad/pin/', {'pin_nuevo': '12'}, format='json').status_code,
                         400)  # muy corto
        self.entrar()
        self.assertEqual(self.client.get('/api/rentabilidad/resumen/').status_code, 200)
        self.client.credentials()
        self.assertEqual(self.client.post('/api/rentabilidad/pin/', {'pin': '0000'}, format='json').status_code, 400)
        # Cambiar el PIN exige el actual
        r = self.client.post('/api/rentabilidad/pin/', {'pin_nuevo': '1357', 'pin_actual': '9999'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.como(self.encargado)
        self.assertEqual(self.client.get('/api/rentabilidad/pin/').status_code, 403)

    def test_lote_pagado_tasa_media_de_venta_frente_a_tasa_de_pago(self):
        self.vender_en_bs('880')
        self.vender_en_bs('900')
        self.como(self.encargado)
        self.vender([{'producto': self.mochila.id, 'cantidad': 1}], metodo='efectivo_usd')
        self.como(self.admin)
        self.client.post('/api/compras/{}/pagar/'.format(self.compra), {'tasa_pago': '1130', 'tasa_usdt': '1130'},
                         format='json')
        self.entrar()
        r = self.client.get('/api/rentabilidad/lotes/{}/'.format(self.lote)).data
        self.assertEqual((r['estado'], r['vendidas'], r['quedan'], r['tasa_pago']), ('pagado', 3, 7, '1130.00'))
        self.assertEqual(r['margen_estimado'], '60.0')
        # 1 − 11.300/22.000 = 48,6 %; 1 − 11.300/22.500 = 49,8 %; en $ cuenta a 1.130 → 60 %
        self.assertEqual([v['margen'] for v in r['ventas']], ['48.6', '49.8', '60.0'])
        self.assertEqual(r['margen_real'], '52.8')  # 39,60 $ de 75 $
        self.assertEqual(r['ganancia'], '39.60')
        self.assertEqual(r['tasa_media_venta'], '970.00')  # (22.000 + 22.500 + 28.250) / 75
        self.assertEqual((r['peor_venta']['margen'], r['mejor_venta']['margen']), ('48.6', '60.0'))
        self.assertEqual(r['ventas_bajo_objetivo'], 0)

    def test_lote_pendiente_se_estima_si_se_pagase_hoy(self):
        self.vender_en_bs('880')
        self.entrar()
        # A tasa de la factura (USDT de hoy, 1.000): 1 − 10.000/22.000 = 54,5 %
        r = self.client.get('/api/rentabilidad/lotes/{}/'.format(self.lote)).data
        self.assertEqual((r['estado'], r['estimado_pago'], r['margen_real']), ('pendiente', True, '54.5'))
        r = self.client.get('/api/rentabilidad/lotes/{}/?escenario=bcv'.format(self.lote)).data
        self.assertEqual(r['margen_real'], '60.0')
        r = self.client.get('/api/rentabilidad/lotes/{}/?escenario=otra&tasa=1320'.format(self.lote)).data
        self.assertEqual(r['margen_real'], '40.0')

    def test_unidades_perdidas_restan(self):
        self.vender_en_bs('880')
        self.como(self.admin)
        self.client.post('/api/productos/{}/mover_stock/'.format(self.mochila.id),
                         {'tipo': 'ajuste', 'cantidad': -1, 'motivo': 'Dañado'})
        self.entrar()
        r = self.client.get('/api/rentabilidad/lotes/{}/'.format(self.lote)).data
        self.assertEqual(r['perdidas'], 1)
        # 25 − 11,36 (venta) − 11,36 (dañado, a la tasa media 880) = 2,27 $
        self.assertEqual(r['ganancia'], '2.27')

    def test_resumen_y_articulos(self):
        self.vender_en_bs('880')
        self.como(self.encargado)
        self.vender([{'producto': self.bolso.id, 'cantidad': 1}], metodo='efectivo_usd')  # stock sin compra
        self.entrar()
        r = self.client.get('/api/rentabilidad/resumen/').data
        self.assertEqual((r['vendido'], r['vendido_sin_costo'], r['margen_real']),
                         ('25.00', '18.00', '54.5'))
        self.assertEqual(r['brecha'], '3.00')  # 25 − 22.000/1.000
        self.assertEqual(r['pendiente_pagar'], '100.00')
        art = {a['nombre']: a for a in self.client.get('/api/rentabilidad/articulos/').data}
        m = art['Morral táctico']
        self.assertEqual((m['costo_ultimo'], m['margen_estimado'], m['vendidas']),
                         ('10.00', '60.0', 1))
        # Reponerlo hoy: 10 × 1.000 Bs; vendido a 880; para un 40 %: 10.000 / (880 × 0,6) = 18,94 $
        self.assertEqual(m['precio_sugerido'], '18.94')
        self.assertTrue(art['Bolso dama']['sin_compras'])
        r = self.client.patch('/api/rentabilidad/ajustes/', {'margen_objetivo': '50'}, format='json')
        self.assertEqual(r.data['margen_objetivo'], '50')
        self.assertEqual(self.client.get('/api/rentabilidad/lotes/').status_code, 200)

    def test_la_ultima_tasa_es_la_de_fecha_valor_mas_reciente(self):
        from .models import TasaCambio
        from . import services
        # Una tasa antigua guardada después (p. ej. al cargar historia) no pasa a ser "la de hoy"
        TasaCambio.objects.create(fuente='bcv', fecha_valor=timezone.localdate() - timedelta(days=30),
                                  compra=Decimal('700'), venta=Decimal('700'))
        self.assertEqual((services.ultima_tasa_bcv(), services.ultima_tasa_usdt()), (Decimal('880'), Decimal('1000')))

    def test_graficos(self):
        self.vender_en_bs('880')
        self.como(self.encargado)
        self.vender([{'producto': self.bolso.id, 'cantidad': 1}], metodo='efectivo_usd')  # stock sin compra
        self.entrar()
        r = self.client.get('/api/rentabilidad/graficos/').data
        self.assertEqual(len(r['por_mes']), 6)
        mes = r['por_mes'][-1]
        # 1 − 10.000 / 22.000 = 54,5 % de 25 $; el bolso (sin compra) solo cuenta en lo vendido total
        self.assertEqual((mes['vendido'], mes['ganancia'], mes['margen'], mes['vendido_total'], mes['ventas']),
                         ('25.00', '13.64', '54.5', '43.00', 2))
        self.assertEqual(r['tasas'][-1], {'fecha': timezone.localdate().isoformat(), 'bcv': '880.00',
                                          'usdt': '1000.00', 'cobrada': '880.00'})
        self.assertEqual([(m['metodo'], m['total'], m['porcentaje']) for m in r['metodos']],
                         [('pago_movil', '25.00', '58.1'), ('efectivo_usd', '18.00', '41.9')])
        self.assertEqual(r['articulos'], [{'nombre': 'Morral táctico', 'unidades': 1, 'vendido': '25.00',
                                           'ganancia': '13.64', 'margen': '54.5'}])
        # La compra vence a los 3 meses: cae en el cuarto mes de la lista de pagos
        self.assertEqual([p['a_pagar'] for p in r['pagos']], ['0.00', '0.00', '0.00', '100.00', '0.00', '0.00'])
        self.assertEqual(r['venta_media_mensual'], '43.00')  # aún no hay meses completos: el actual
        self.assertEqual(len(self.client.get('/api/rentabilidad/graficos/?meses=12').data['por_mes']), 12)
        self.assertEqual(len(self.client.get('/api/rentabilidad/graficos/?meses=x').data['por_mes']), 6)
        self.client.credentials()
        self.assertEqual(self.client.get('/api/rentabilidad/graficos/').status_code, 403)
