from django.urls import path
from . import views
from . import document_export

urlpatterns = [
    path('', views.inicio, name="inicio"),
    path('login/', views.loginPage, name="login"),
    path('logout/', views.logoutUser, name="logout"),
    #--------Gestion de inventario--------------------------------------
    path('inventario/list/', views.inventario_list, name="inventario_list"),
    path('inventario/add/', views.inventario_add, name="inventario_add"),
    path('inventario/detalle/<int:id_inventario>/', views.inventario_detail, name="inventario_detail"),
    path('inventario/editar/<int:id_inventario>/', views.inventario_edit, name="inventario_edit"),
    path('inventario/eliminar/<int:id_inventario>/', views.inventario_delete, name="inventario_delete"),
    path('inventario/nacionalizar-desde-aduana/', views.nacionalizar_desde_aduana, name="nacionalizar_desde_aduana"),
    path('inventario/rectificar/', views.verify_inventario, name="inventario_rectificar"),
    path('inventario/fisico/', views.inventario_fisico, name="inventario_fisico"),
    path('inventario/no-existente/', views.inventario_no_existente_list, name="inventario_no_existente"),
    #------------Manifiestos------------------------------------------
    path('manifiestos/', views.manifiesto_list, name="manifiesto_list"),
    path('manifiestos/eliminar', views.manifiesto_eliminar, name="manifiesto_eliminar"),
    path('manifiestos/resumen/<int:id>', views.resumen_manifiesto, name="resumen_manifiesto"),
    path('manifiestos/reporte-historico-agencia/', views.reporte_historico_agencia, name="reporte_historico_agencia"),
    #--------Gestion de entregas--------------------------------------
    path('entrega/lista/', views.entrega_list, name="entrega_list"),
    path('entrega/add/', views.entrega_add, name="entrega_add"),
    path('entrega/add/monta-facturacion/', views.entrega_monta_facturacion_add, name="entrega_monta_facturacion_add"),
    path('entrega/detalle/<int:id_entrega>/', views.entrega_detail, name="entrega_detail"),
    path('entrega/editar/<int:id_entrega>/', views.entrega_edit, name="entrega_edit"),
    path('entrega/programadas/', views.entrega_programadas, name="entrega_programadas"),
    path('entrega/ejecutar/<int:id_entrega>/', views.ejecutar_entrega, name="ejecutar_entrega"),
    path('entrega/concluir/<int:id_entrega>/', views.concluir_entrega, name="concluir_entrega"),
    #--------Gestion de mercancias no nacionalizadas--------------------------------------
    path('mercancia-no-nacionalizada/lista/', views.no_nacionalizada_list, name="no_nacionalizada_list"),
    path('mercancia-no-nacionalizada/importar-manifiesto/', views.importar_manifiesto, name="importar_manifiesto"),
    path('mercancia-no-nacionalizada/importar-no-manifestados/', views.importar_no_manifestados, name="importar_no_manifestados"),
    #--------Gestion de citas--------------------------------------
    path('cita/lista/', views.cita_list, name="cita_list"),
    path('cita/add/', views.cita_add, name="cita_add"),
    path('cita/detalle/<int:id_cita>/', views.cita_detail, name="cita_detail"),
    path('cita/editar/<int:id_cita>/', views.cita_edit, name="cita_edit"),
    path('cita/programadas/', views.cita_programadas, name="cita_programadas"),
    #--------Gestion de operaciones a mercancias--------------------------------------
    path('operacion-mercancia/ingresar-inventario/<int:id_inventario>/', views.operacion_entrada_inventario, name="operacion_entrada_inventario"),
    path('operacion-mercancia/entregar/<int:id_inventario>/', views.operacion_entregar_inventario, name="operacion_entregar_inventario"),
    path('operacion-mercancia/devolucion/<int:id_inventario>/', views.operacion_devolucion_inventario, name="operacion_devolucion_inventario"),
    path('operacion-mercancia/no-localizable/<int:id_inventario>/', views.operacion_no_localizable_inventario, name="operacion_no_localizable_inventario"),
    path('operacion-mercancia/nacionalizar/<int:id_inventario>/', views.operacion_nacionalizar_inventario, name="operacion_nacionalizar_inventario"),
    #--------Gestion de mercancias entregadas--------------------------------------
    path('mercancias-entregadas/list/', views.inventarios_entregados_list, name="inventarios_entregados_list"),
    #--------Gestion de mercancias en devolucion--------------------------------------
    path('mercancias-devolucion/list/', views.inventarios_devolucion_list, name="inventarios_devolucion_list"),
    #--------Gestion de mercancias no localizable--------------------------------------
    path('mercancias-no-localizables/list/', views.inventarios_no_localizable_list, name="inventarios_no_localizable_list"),
    #--------Ajax loads--------------------------------------
    path('inventario/ajax-load/', views.ajax_inventario_load, name="ajax_inventario_load"),
    path('inventario/ajax-punteo-load/', views.ajax_punteo_inventario_load, name="ajax_punteo_inventario_load"),
    path('inventario/ajax-punteo-confirmacion-load/', views.ajax_punteo_confirmacion_inventario_load, name="ajax_punteo_confirmacion_inventario_load"),
    path('inventario/ajax-hbls-confirmado-punteo-load/', views.ajax_hbls_confirmado_punteo_load, name="ajax_hbls_confirmado_punteo_load"),
    path('inventario/ajax-hbl-duplicado-load/', views.ajax_hbl_duplicado_load, name="ajax_hbl_duplicado_load"),
    path('municipios/ajax-load/', views.ajax_municipio_load, name="ajax_municipio_load"),
    path('inventario/cantidad-nacionalizar-ajax/', views.ajax_load_cantidad_registros_a_nacionalizar, name="ajax_load_cantidad_registros_a_nacionalizar"),
    path('inventario/info-grafico-barras/', views.ajax_load_grafico_entrada_salida_cargas, name="ajax_load_grafico_entrada_salida_cargas"),
    path('inventario/test-aduana-conection/', views.test_aduana_conection, name="test_aduana_conection"),
    path('transportista/ajax-load/', views.ajax_transportistas_load, name="ajax_transportistas_load"),
    path('chapa/ajax-load/', views.ajax_existe_chapa_load, name="ajax_existe_chapa_load"),
    #--------Comprobante de entrega de destinatario--------------------------------------
    path('comprobante-entrega/envio/', views.comprobante_entrega_envios_pdf, name="comprobante_entrega_envios_pdf"),
    path('cancelar-comprobante-entrega-escaner/envio/', views.cancelar_generacion_automatica_comprobantes_destinatarios, name="cancelar_comprobante_entrega_envios"),
    
    #--------Comprobante de entrega de operadores--------------------------------------
    path('comprobante-entrega-operadores/', views.comprobante_entrega_operadores, name="comprobante_entrega_operadores"),
    path('comprobante-entrega-operadores-cobrados/', views.comprobante_entrega_operadores_cobrados, name="comprobante_entrega_operadores_cobrados"),
    path('comprobante-entrega-pago-parcial/<int:id_comprobante>/', views.comprobante_entrega_pago_parcial, name="comprobante_entrega_pago_parcial"),
    path('comprobante-entrega-detalles-pago/<int:id_comprobante>/', views.comprobante_entrega_detalles_pago, name="comprobante_entrega_detalles_pago"),

    #--------Gestion de PDF--------------------------------------
    path('entrega/detalle-pdf/<int:id_entrega>/', views.lista_entregas_pdf, name="lista_entregas_pdf"),
    path('entrega/facturas-pdf/<int:id_entrega>/', views.lista_facturas_por_entrega_pdf, name="lista_facturas_por_entrega_pdf"),
    path('entrega/facturas-multiple-envio-pdf/<int:id_entrega>/', views.facturacion_multiple_envios_pdf, name="facturacion_multiple_envios_pdf"),
    path('entrega/facturas-multiple-ena-menaje-pdf/<int:id_entrega>/', views.facturacion_multiple_ena_menaje_pdf, name="facturacion_multiple_ena_menaje_pdf"),
    path('inventario/factura-pdf/<int:id_inventario>/', views.generar_factura_de_inventario_pdf, name="generar_factura_de_inventario_pdf"),
    #--------Tracking--------------------------------------
    path('tracking/', views.tracking_view, name="tracking_view"),
    #--------Gestion de facturas--------------------------------------
    path('facturas/', views.facturas_list, name="facturas_list"),
    path('facturas/desestimadas/', views.facturas_desestimadas_list, name="facturas_desestimadas_list"),
    path('facturas/cobradas/', views.facturas_cobradas_list, name="facturas_cobradas_list"),
    path('factura/detalle/<int:id_factura>/', views.factura_detalle_pdf, name="factura_detalle_pdf"),
    path('factura/slit/<int:id_factura>/', views.factura_detalle_img, name="factura_detalle_img"),
    path('factura/operador/detalle/<int:id_factura>/', views.factura_operador_detalle_pdf, name="factura_operador_detalle_pdf"),
    path('factura/exportar/', views.exportar_facturas_to_dbf, name="exportar_facturas_to_dbf"),
    path('exportar-documento/', document_export.exportar_documento, name="exportar_documento"),
    #--------Despacho electrónico--------------------------
    path('despacho-electronico/', views.despacho_electronico, name="despacho_electronico"),
    #--------Reportes--------------------------------------
    path('inventario/reportes/', views.inventarios_reportes, name="inventarios_reportes"),
    path('reportes/ingresos-diarios/', views.reporte_ingresos_diarios, name="reporte_ingresos_diarios"),
    path('reportes/reporte-contable/', views.reporte_contable, name="reporte_contable"),
    path('reportes/contro-de-ingresos/', views.control_de_ingresos, name="control_de_ingresos"),
    path('reportes/reporte-contable-aduana/', views.reporte_contable_aduana, name="reporte_contable_aduana"),
    path('inventario/reportes/cargas_traslado_mayor_cinco_dias/', views.cargas_traslado_mayor_cinco_dias, name="reporte_inventario_cargas_traslado_mayor_cinco_dias"),
    path('reportes/devoluciones/', views.reporte_devoluciones, name="reporte_devoluciones"),
    path('reportes/cargas-en-desagrupe/', views.reporte_cargas_en_desagrupe, name="cargas_desagrupe"),
    path('inventario/reportes/cargas-con-incidencias/', views.inventario_incidencias, name="mercancia_inventario_incidencias"),
    path('inventario/reportes/trasbordo/', views.inventario_trasbordo, name="mercancia_trasbordo"),
    path('reportes/parte-diario/', views.reporte_parte_diario, name="parte_diario"),
    path('reportes/parte-operativo/', views.reporte_parte_operativo, name="parte_operativo"),
    path('reportes/desempeno/', views.reporte_desempeno, name="reporte_desempeno"),
    path('reportes/cargas-transportadas/', views.reporte_cargas_transportistas, name="reporte_transportistas"),
    path('reportes/levantamiento-inventario/', views.levantamiento_inventario, name="levantamiento_inventario"),
    path('inventario/canal-rojo/', views.cargas_canal_rojo, name="canal_rojo"),
    # ---------Manual----------------------------------------
    path('manual-de-ayuda/pagina-inicial/', views.pagina_inicio_manual, name="pagina_inicio_manual"),
    path('manual-de-ayuda/modulo-inventario/', views.modulo_inventario, name="modulo_inventario"),
    path('manual-de-ayuda/modulo-facturacion/', views.modulo_facturacion, name="modulo_facturacion"),
    path('manual-de-ayuda/reportes/', views.manual_reportes, name="manual_reportes"),
    #--------------------Rectificar peso----------------------------
    path('rectificar-peso/', views.rectificar_peso, name="rectificar_peso"),
    #--------------------Desglose Aéreo-----------------------------
    path('desglosar-guia-aerea/', views.generar_desglose, name="desglose"),
    #--------------------Generación de boletas ---------------------
    path('generar-boleta/<int:id>', views.generar_boleta, name="generar_boleta"),
    path('generar-etiquetas/<int:id>', views.generar_etiquetas, name="generar_etiquetas"),
    # ---------Administrar Inventario------------------------
    path('administrar-inventario/', views.administrar_inventario, name="administrar_inventario"),
    # ---------Administrar Manifiesto------------------------
    path('administrar-manifiesto/', views.administrar_manifiesto, name="administrar_manifiesto"),
    # ---------Permisos de Usuario --------------------------
    path('permisos-usuario/', views.permisos_usuario_list, name="permisos_usuario_list"),
   
    #path('reportes/ingresos-diarios-noviembre/', views.reporte_ingresos_diarios_noviembre, name="reporte_ingresos_diarios_noviembre"),
    #path('reportes/reporte-contable-noviembre/', views.reporte_contable_noviembre, name="reporte_contable_noviembre"),
    #ELIMINAR
    #path('valorizar-desde-aduana/', views.valorizar_desde_aduana, name="valorizar_desde_aduana"),

]