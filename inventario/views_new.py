from io import BytesIO
from re import escape, split
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse, Http404, JsonResponse
from django.db.models import Q
from django.db.models import Sum,Count
from django.contrib.auth import authenticate, login, logout
from django.template.loader import get_template
from django.urls import reverse
from .forms import *
from .filters import *
from django.utils.timezone import now
from tablib import Dataset
from datetime import datetime, timedelta, date
from django.core.paginator import Paginator
from django.shortcuts import render
from xhtml2pdf import pisa
import logging
from auditoria.views import save_addition, save_edition, save_deletion
from django.core.files.storage import FileSystemStorage
import zeep
from requests import Session
from requests.auth import HTTPBasicAuth  # or HTTPDigestAuth, or OAuth1, etc.
from zeep import Client
from zeep.transports import Transport
import requests
import json
from django.utils.html import strip_tags
import re
from django.db import transaction
import unicodedata
import json
from django.core import serializers
import math
import qrcode
import qrcode.image.svg
from django.contrib.admin.models import LogEntry
from django.db import connection
# from inventario.views import *
import itertools
import operator
import threading
import time
import openpyxl
# Create your views here.
@login_required(login_url='login')
def inicio(request):
    #correccion(request)

    #Lista de inventarios
    inventario = Inventario.objects.all()

    #Datos relevantes
    cantidad_inventarios_no_nacionalizados = inventario.filter(Q(Estado = 'Inventario'), Q(Nacionalizado = False)).count()
    cantidad_inventarios = inventario.filter(Estado = 'Inventario').count()
    inventario_no_nacionalizado_fuera_tiempo = inventario.filter(~Q(Estado = 'Entregado'), Q(Fecha_Entrada_Puerto__lt = datetime.now() - timedelta(days=30))).count()
    incidencias_del_dia = inventario.filter(Q(Estado = 'Inventario'), ~Q(Incidencia = None)).count()
    # nacionalizar_cargas(request)
    ctx = {'cantidad_inventarios': cantidad_inventarios, 'inventario_no_nacionalizado_fuera_tiempo': inventario_no_nacionalizado_fuera_tiempo, 'incidencias_del_dia': incidencias_del_dia, 'cantidad_inventarios_no_nacionalizados': cantidad_inventarios_no_nacionalizados}
    return render(request, 'base_template.html', ctx)

#----Gestion de Inventarios---------------------------------------------------
@login_required(login_url='login')
def inventario_list(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Formulario de tabla
    form_trasladar_almacen = Operacion_Trasladar_De_Almacen_Form()
    form_nacionalizar_carga   = Operacion_Nacionalizar_Inventario_Form()

    #Ejecutando operaciones de las tablas
    operaciones_de_tablas(request)   
    #Informacion para el template
    header_text     = 'Inventarios nacionalizados'
    breadcrumb_text = 'Inventarios nacionalizados'
    #Definiendo menu activo
    active_menu = 'mercancia_inventario'

    inventarios = Inventario.objects.all().filter(Q(Estado = 'Inventario'), Q(Nacionalizado = True)).order_by('HBL')

    #Aplicacion de filtros
    inventario_filter = InventarioFilter(request.GET, queryset=inventarios)
    inventarios = inventario_filter.qs

    #Paginator
    paginator = Paginator(inventarios, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj, 'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'form_trasladar_almacen': form_trasladar_almacen, 'inventario_filter': inventario_filter, 'form_nacionalizar_carga': form_nacionalizar_carga}
    return render(request, 'inventario/inventario_list.html', ctx)

@login_required(login_url='login')
def inventario_add(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Definiendo menu activo
    active_menu = 'mercancia_inventario'

    action = 'add'
    form_inventario   = Inventario_Form()
    form_destinatario = Destinatario_Form()
    form_remitente    = Remitente_Form()

    if request.method == 'POST':
        form_inventario   = Inventario_Form(request.POST)
        form_destinatario = Destinatario_Form(request.POST)
        form_remitente    = Remitente_Form(request.POST)

        if form_inventario.is_valid() and form_destinatario.is_valid() and form_remitente.is_valid():
            #Instanciando los formularios
            form_inventario_instance    = form_inventario.save(commit = False)
            form_destinatario_instance  = form_destinatario.save(commit = False)
            form_remitente_instance     = form_remitente.save(commit = False)

            #Fecha de entrada al inventario
            form_inventario_instance.Estado = 'Inventario'
            form_inventario_instance.Fecha_Entrada = now()

            #Asignando destinatario
            form_inventario_instance.Destinatario = form_destinatario_instance
            form_destinatario_instance.save()
            
            #Asignando remitente
            form_inventario_instance.Remitente = form_remitente_instance
            form_remitente_instance.save()

            #Almacenando el inventario
            form_inventario_instance.save()

            HBL_No_Manifestados.objects.filter(HBL=form_inventario_instance.HBL).delete()

            #Salvando Tracking
            traking = Traking()
            traking.Inventario      = form_inventario_instance
            traking.Estado          = 'En almacén'
            traking.Observaciones   = 'Inventario en el almacén en espera de distribución'
            traking.Fecha           = now()
            traking.save()
            # Registro de trazas
            save_addition(request.user, 'traking', traking.id, str(model_to_dict(traking)))

            # Registro de trazas
            save_addition(request.user, 'inventario', form_inventario_instance.id, str(model_to_dict(form_inventario_instance)))

            messages.success(request, 'Inventario agregado satisfactoriamente')
            return redirect('inventario_list')

    ctx = {'action': action, 'form_inventario': form_inventario, 'form_destinatario': form_destinatario, 'form_remitente': form_remitente, 'active_menu': active_menu}
    return render(request, 'inventario/inventario_edit.html', ctx)

@login_required(login_url='login')
def inventario_edit(request, id_inventario):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    action = 'edit'
    #Instanciando formularios
    current_inventario = get_object_or_404(Inventario, pk = id_inventario)
    current_id_municipio = current_inventario.Destinatario.Municipio
    isPrepago = getattr(current_inventario,'isPrepago')
    if not current_inventario.Estado == 'Inventario':
        raise Http404

    form_inventario   = Inventario_Form(instance=current_inventario)
    form_destinatario = Destinatario_Form(instance=current_inventario.Destinatario)
    form_remitente    = Remitente_Form(instance=current_inventario.Remitente)

    if request.method == 'POST':
        form_inventario   = Inventario_Form(request.POST, instance=current_inventario)
        form_destinatario = Destinatario_Form(request.POST, instance=current_inventario.Destinatario)
        form_remitente    = Remitente_Form(request.POST, instance=current_inventario.Remitente)
        
        if request.user.groups.filter(name='Comercial').exists() or request.user.is_superuser:
            current_id_municipio = Municipio.objects.get(pk = request.POST.get('Municipio')) 

            if form_inventario.is_valid() and form_destinatario.is_valid() and form_remitente.is_valid():
                #Instanciando los formularios
                form_inventario_instance    = form_inventario.save(commit = False)
                form_destinatario_instance  = form_destinatario.save(commit = False)
                form_remitente_instance     = form_remitente.save(commit = False)

                #Asignando destinatario
                form_inventario_instance.Destinatario = form_destinatario_instance
                form_destinatario_instance.save()
                
                #Asignando remitente
                form_inventario_instance.Remitente = form_remitente_instance
                form_remitente_instance.save()
                    
                #Almacenando el inventario
                form_inventario_instance.isPrepago=isPrepago
                print(form_inventario_instance.isPrepago)
                form_inventario_instance.save()

                # Registro de trazas
                save_edition(request.user, 'inventario', form_inventario_instance.id, str(model_to_dict(form_inventario_instance)))

                messages.success(request, 'Inventario modificado satisfactoriamente')
                return redirect(reverse('inventario_detail', kwargs={"id_inventario": id_inventario}))

        if request.user.groups.filter(name='Operador').exists() or request.user.groups.filter(name='Cajero').exists() or request.user.groups.filter(name='Facturador').exists():
            inventario = Inventario.objects.get(id=current_inventario.id)
            destinatario = inventario.Destinatario
            remitente = inventario.Remitente
            if form_inventario.is_valid():
                #Instanciando los formularios
                form_inventario_instance    = form_inventario.save(commit = False)
                    
                #Obteniendo datos actuales de la carga
                form_inventario_instance.isPrepago=isPrepago
                form_inventario_instance.Destinatario=destinatario
                form_inventario_instance.Remitente=remitente
                # print(form_inventario_instance.isPrepago)
                form_inventario_instance.save()

                # Registro de trazas
                save_edition(request.user, 'inventario', form_inventario_instance.id, str(model_to_dict(form_inventario_instance)))

                messages.success(request, 'Inventario modificado satisfactoriamente')
                return redirect(reverse('inventario_detail', kwargs={"id_inventario": id_inventario}))


    ctx = {'action': action, 'form_inventario': form_inventario, 'form_destinatario': form_destinatario, 'form_remitente': form_remitente, 'id_inventario': id_inventario, 'current_id_municipio': current_id_municipio}
    return render(request, 'inventario/inventario_edit.html', ctx)

@login_required(login_url='login')
def inventario_detail(request, id_inventario):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    current_registro = get_object_or_404(Inventario, pk = id_inventario)
    
    ctx = {'current_registro': current_registro}
    return render(request, 'inventario/inventario_detail.html', ctx)
    

#----Cargas no nacionalizadas-------------------------------------------------------------
@login_required(login_url='login')
def no_nacionalizada_list(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Formulario de tabla
    form_trasladar_almacen    = Operacion_Trasladar_De_Almacen_Form()
    form_nacionalizar_carga   = Operacion_Nacionalizar_Inventario_Form()
    
    #IF POST: ------  Ejecutando operaciones de las tablas
    operaciones_de_tablas(request)   

    header_text     = 'Inventarios no nacionalizados'
    breadcrumb_text = 'Inventarios no nacionalizados'
    #Definiendo menu activo
    active_menu = 'mercancia_inventario'

    inventarios = Inventario.objects.all().filter(Q(Estado = 'Inventario'), Q(Nacionalizado = False)).order_by('HBL')
    # inventarios = Inventario.objects.all().filter(Q(Estado = 'Inventario'), Q(Nacionalizado = False), Q(Incidencia__isnull=False) | Q(Estado = 'Inventario'), Q(Nacionalizado = False), Q(Incidencia__isnull=True),Q(rectificacion_aduana__isnull=False)).order_by('HBL')
    # inventarios = Inventario.objects.all().filter(Q(Estado = 'Inventario',exist=True), Q(Nacionalizado = False)).order_by('HBL')

    #Aplicacion de filtros
    inventario_filter = InventarioFilter(request.GET, queryset=inventarios)
    inventarios = inventario_filter.qs

    #Paginator
    paginator = Paginator(inventarios, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj, 'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'form_trasladar_almacen': form_trasladar_almacen, 'form_nacionalizar_carga': form_nacionalizar_carga, 'inventario_filter': inventario_filter}
    return render(request, 'inventario/inventario_list.html', ctx)

@login_required(login_url='login')
def importar_manifiesto(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Definiendo menu activo
    active_menu = 'mercancia_inventario'
    form = Operacion_Importar_Manifiesto_Form()

    if request.method == 'POST':
        form = Operacion_Importar_Manifiesto_Form(request.POST, request.FILES)
        if form.is_valid():
            #Fichero de manifiesto
            file = request.FILES['File']

            #Comprobando que no se haya importado ese manifiesto
            try:
                current_manifiesto = Manifiesto.objects.get(Q(No_Contenedor = form.cleaned_data['No_Contenedor']), Q(Manifiesto = form.cleaned_data['Manifiesto']))
                if current_manifiesto:
                    messages.error(request, 'El manifiesto que desea importar ya se encuentra registrado en el sistema')
                    ctx = {'active_menu': active_menu, 'form': form}
                    return render(request, 'operacion_mercancia/operacion_importar_manifiesto.html', ctx)
            except:
                pass
            
            #Valores generales
            No_fila = 0
            try:
                with transaction.atomic():
                    dataset = Dataset()

                    #Comprobando la extension del archivo
                    if not file.name.endswith('.xls'):
                        messages.error(request, 'La extensión del archivo no es correcta, debe ser .xls')
                        ctx = {'active_menu': active_menu, 'form': form}
                        return render(request, 'operacion_mercancia/operacion_importar_manifiesto.html', ctx)

                    #Carga de archivo excel
                    imported_data = dataset.load(file.read(), format='xls')
                    
                    #Relacion de columnas
                    Col_HBL = 0
                    Col_Cant_Bultos = 1
                    Col_Peso = 2
                    Col_Volumen = 3
                    Col_Remitente_Nombre = 4
                    Col_Destinatario_Nombre = 5
                    Col_Destinatario_Direccion = 6
                    Col_Destinatario_Provincia = 7
                    Col_Destinatario_Municipio = 8
                    Col_Destinatario_Telefono = 9
                    Col_Destinatario_Pasaporte = 10
                    Col_Destinatario_CI = 11
                    Col_Destinatario_Email = 12
                    Col_Contenido = 13
                    Col_Categoria_Operacion = 14

                    for data in imported_data:
                        if No_fila >= 0:
                            #Gestionando remitentes----------------
                            current_remitente = Remitente()
                            current_remitente.Nombre_Remitente = data[Col_Remitente_Nombre]
                            current_remitente.save()
                            
                            #Gestionando destinatario----------------
                            current_destinatario = Destinatario()
                            current_destinatario.Nombre = data[Col_Destinatario_Nombre]
                            current_destinatario.Pasaporte_DNI = data[Col_Destinatario_Pasaporte]
                            current_destinatario.Direccion = data[Col_Destinatario_Direccion]
                            current_destinatario.Email = data[Col_Destinatario_Email]

                            if str(data[Col_Destinatario_CI]).endswith('.0'):
                                current_destinatario.CI = str(data[Col_Destinatario_CI]).replace('.0', '')
                            else:
                                current_destinatario.CI = str(data[Col_Destinatario_CI])
                            
                            if str(data[Col_Destinatario_Telefono]).endswith('.0'):
                                current_destinatario.Telefono = str(data[Col_Destinatario_Telefono]).replace('.0', '')
                            else:
                                current_destinatario.Telefono = str(data[Col_Destinatario_Telefono])

                            #Manejo de provincias
                            if not data[Col_Destinatario_Provincia]:
                                raise ValueError('Error importando provincia')

                            provincia_destinatario_id = Provincia.objects.all().filter(Q(Nombre__icontains = str(data[Col_Destinatario_Provincia]).lower().strip()) | Q(search_text__icontains = str(data[Col_Destinatario_Provincia]).lower().strip())).first()

                            if not provincia_destinatario_id:
                                raise ValueError('Error importando provincia')
                            
                            current_destinatario.Provincia = provincia_destinatario_id

                            #Manejo de municipios
                            if not data[Col_Destinatario_Municipio]:
                                raise ValueError('Error importando municipio') 
                            #Opcion de la Habana
                            if current_destinatario.Provincia and current_destinatario.Provincia.id == 2:
                                destinatario_municipio_id = Municipio.objects.all().filter(Q(Provincia = provincia_destinatario_id), (Q(Nombre__icontains = str(data[Col_Destinatario_Municipio]).lower().strip()) | Q(search_text__icontains = str(data[Col_Destinatario_Municipio]).lower().strip()))).first()

                                if not destinatario_municipio_id:
                                    raise ValueError('Error importando municipio') 
                                
                                current_destinatario.Municipio = destinatario_municipio_id
                            else:
                                try:
                                    current_destinatario.Municipio = Municipio.objects.all().filter(Q(Provincia = provincia_destinatario_id)).first()
                                except:
                                    raise ValueError('Error importando municipio') 

                            current_destinatario.save()
                            
                            #Gestionando inventarios----------------------
                            current_inventario = Inventario()
                            current_inventario.No_Contenedor = form.cleaned_data['No_Contenedor']
                            #current_inventario.Corresponsal = 
                            #current_inventario.Pais_Origen = 
                            if str(data[Col_HBL]).endswith('.0'):
                                current_inventario.HBL = str(data[Col_HBL]).replace('.0', '')
                            else:
                                current_inventario.HBL = str(data[Col_HBL])
                            current_inventario.Manifiesto = form.cleaned_data['Manifiesto']
                            current_inventario.Cantidad_Bultos = data[Col_Cant_Bultos]
                            current_inventario.Peso = data[Col_Peso]
                            current_inventario.Volumen = data[Col_Volumen]
                            current_inventario.Contenido = data[Col_Contenido]
                            current_inventario.Categoria_Operacion = data[Col_Categoria_Operacion]
                            current_inventario.Destinatario = current_destinatario
                            current_inventario.Remitente = current_remitente
                            current_inventario.Estado = 'Desagrupe'
                            current_inventario.Fecha_Entrada_Puerto = form.cleaned_data['Fecha_Entrada_Puerto']
                            current_inventario.Almacen = form.cleaned_data['Almacen']
                            current_inventario.Fecha_Entrada = form.cleaned_data['Fecha_Entrada']
                            if request.POST.get('isPrepago') == 'on':
                                current_inventario.isPrepago = True
                            else:
                                current_inventario.isPrepago = False
                            current_inventario.save()
                            HBL_No_Manifestados.objects.filter(HBL=current_inventario.HBL).delete()

                            #Salvando Tracking
                            traking = Traking()
                            traking.Inventario      = current_inventario
                            traking.Estado          = 'En depósito'
                            traking.Observaciones   = 'Sin despachar por aduana'
                            traking.Fecha           = now()
                            traking.save()
                            # Registro de trazas
                            save_addition(request.user, 'traking', traking.id, str(model_to_dict(traking)))

                            # Registro de trazas
                            save_addition(request.user, 'inventario', current_inventario.id, str(model_to_dict(current_inventario)))

                        #Incrementando contador de la fila
                        No_fila = No_fila + 1

                    #Almacenando manifiesto en servidor    
                    nombre_archivo = 'Manifiesto-' + str(form.cleaned_data['Manifiesto']) + '-Contenedor-' + str(form.cleaned_data['No_Contenedor']) + '.xls'
                    try:
                        fs = FileSystemStorage(location=MEDIA_ROOT + '/manifiestos/') #defaults to MEDIA_ROOT  
                        fs.save(nombre_archivo, file)
                    except:
                        raise ValueError('Ha ocurrido un error almacenando el archivo en el servidor. Por favor, comuníquese con su proveedor de servicios') 
                        
                    #Registrando manifiesto
                    registro_manifiesto = Manifiesto()
                    registro_manifiesto.No_Contenedor = form.cleaned_data['No_Contenedor']
                    registro_manifiesto.Manifiesto = form.cleaned_data['Manifiesto']
                    registro_manifiesto.Fecha_Importacion = now()
                    registro_manifiesto.File = 'manifiestos/' + nombre_archivo
                    if request.POST.get('isPrepago') == 'on':
                        registro_manifiesto.isPrepago = True
                    else:
                        registro_manifiesto.isPrepago = False
                    registro_manifiesto.save()
                    # Registro de trazas
                    save_addition(request.user, 'manifiesto', registro_manifiesto.id, str(model_to_dict(registro_manifiesto)))

                    messages.success(request, 'Se han importado ' + str(No_fila) + ' registros satisfactoriamente')  
                    return redirect(request.path)  
            except Exception as inst:
                messages.error(request, 'Ha ocurrido un error importando el manifiesto. Por favor revise la línea ' + str(int(No_fila) + 2))
                messages.error(request, inst)
          
    ctx = {'active_menu': active_menu, 'form': form}
    return render(request, 'operacion_mercancia/operacion_importar_manifiesto.html', ctx)


#----Gestion de entregas------------------------------------------------------
@login_required(login_url='login')
def entrega_list(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Formulario de tabla
    form_trasladar_almacen = Operacion_Trasladar_De_Almacen_Form()
    #Ejecutando operaciones de las tablas
    #operaciones_de_tablas(request)
    if request.method == 'POST':
        if len(request.POST.getlist('inventario_id')) == 0:
            messages.error(request, 'Debe seleccionar al menos un inventario.')  
            return redirect(request.path)  

        #Procedimiento de reincorporacion a almacen
        try:
            with transaction.atomic():
                #Se reincorporan los inventarios seleccionados al almacen
                for current_inventario_id in request.POST.getlist('inventario_id'):
                    current_inventario = Inventario.objects.get(pk = current_inventario_id)
                    current_inventario.Estado = 'Inventario'
                    current_inventario.Almacen = Almacen.objects.get(pk = request.POST.get('id_almacen_tabla'))
                    current_inventario.save()

                    #Salvando Tracking
                    traking = Traking()
                    traking.Inventario      = current_inventario
                    traking.Estado          = 'En almacén'
                    traking.Observaciones   = 'Inventario en almacén en espera de distribución'
                    traking.Fecha           = now()
                    traking.save()
                    # Registro de trazas
                    save_addition(request.user, 'traking', traking.id, str(model_to_dict(traking)))

                    # Registro de trazas
                    save_edition(request.user, 'inventario', current_inventario.id, str(model_to_dict(current_inventario)))

                    #Se obtienen los comprobantes de destinatarios que contienen el inventario que se esta reincorporando
                    factura_destinatario = Factura.objects.filter(Inventario = current_inventario)
                    
                    for current_factura_destinatario in factura_destinatario:
                        #Se buscan los comprobantes de operador en que se esa factura
                        factura_operador = Factura_Operador.objects.filter(Facturas_Destinatarios = current_factura_destinatario)

                        #Si la factura tiene solo 1 inventario se resta el valor de toda la factura
                        if current_factura_destinatario.Inventario.all().count() == 1:
                            for current_factura_operador in factura_operador:
                                current_factura_operador.Importe = current_factura_operador.Importe - current_factura_destinatario.Importe_Total_Factura
                                current_factura_operador.save()

                                # Registro de trazas
                                save_addition(request.user, 'factura_operador', current_factura_operador.id, str(model_to_dict(current_factura_operador)))

                                #Se declara la reincorporacion
                                inventario_reincorporado = Inventario_Reincorporado()
                                inventario_reincorporado.Factura_Operador = current_factura_operador
                                inventario_reincorporado.Inventario = current_inventario
                                inventario_reincorporado.Observaciones = request.POST.get('Observaciones')
                                inventario_reincorporado.Fecha = now()
                                inventario_reincorporado.Importe                     = current_factura_destinatario.Importe_Total_Factura
                                inventario_reincorporado.Importe_Transcargo          = current_factura_destinatario.Importe_Transcargo_Total 
                                inventario_reincorporado.Importe_Seguro_Carga        = current_factura_destinatario.Importe_Seguro_Carga_Total  
                                inventario_reincorporado.Importe_Transportacion      = current_factura_destinatario.Importe_Transportacion_Total 
                                inventario_reincorporado.Importe_Derecho_Aduanal     = current_factura_destinatario.Importe_Derecho_Aduanal_Total
                                inventario_reincorporado.Importe_Servicio_Aduanal    = current_factura_destinatario.Importe_Servicio_Aduanal_Total
                                inventario_reincorporado.save()
                                # Registro de trazas
                                save_addition(request.user, 'inventario_reincorporado', inventario_reincorporado.id, str(model_to_dict(inventario_reincorporado)))

                            #Se elimina la relación de la factura con la del operador
                            with connection.cursor() as cursor:
                                cursor.execute(""" delete from "inventario_factura_operador_Facturas_Destinatarios" where "factura_id" = '%s' """%(current_factura_destinatario.id))

                            #Se desestima la factura
                            current_factura_destinatario.Estado = 'Desestimada'
                            current_factura_destinatario.save()
                            # Registro de trazas
                            save_edition(request.user, 'factura', current_factura_destinatario.id, str(model_to_dict(current_factura_destinatario)))
                        
                        #Si la factura tiene mas de este inventario se resta el valor de este inventario
                        else:
                            #Se busca el comprobante de destinatario en que se encuentra el inventario
                            with connection.cursor() as cursor:
                                cursor.execute(""" select "inventario_factura_inventario".* from "inventario_factura_inventario" 
                                                WHERE "inventario_factura_inventario"."Inventario_id" = '%s' AND "inventario_factura_inventario"."Factura_id" = '%s' """%(current_inventario.id, current_factura_destinatario.id))
                                factura_inventario = cursor.fetchall()
                                
                                #Importes del inventario
                                seguro_carga = 0 
                                sobredimension = 0
                                transportacion = 0
                                transcargo = 0
                                corresponsalia = 0
                                
                                if factura_inventario[0][1]:
                                    seguro_carga = float(factura_inventario[0][1])
                                if factura_inventario[0][2]:
                                    sobredimension = float(factura_inventario[0][2])
                                if factura_inventario[0][3]:
                                    transportacion = float(factura_inventario[0][3]) 
                                if factura_inventario[0][4]:
                                    transcargo = float(factura_inventario[0][4])   
                                if factura_inventario[0][5]:
                                    corresponsalia = float(factura_inventario[0][5])    

                                current_factura_destinatario.Importe_Total_Factura = current_factura_destinatario.Importe_Total_Factura - (seguro_carga + sobredimension + transportacion + transcargo + corresponsalia)
                                current_factura_destinatario.Importe_Transcargo_Total = current_factura_destinatario.Importe_Transcargo_Total - transcargo
                                current_factura_destinatario.Importe_Seguro_Carga_Total = current_factura_destinatario.Importe_Seguro_Carga_Total - seguro_carga
                                current_factura_destinatario.Importe_Transportacion_Total = current_factura_destinatario.Importe_Transportacion_Total - transportacion
                                current_factura_destinatario.Importe_Derecho_Aduanal_Total = current_factura_destinatario.Importe_Derecho_Aduanal_Total - current_inventario.Importe_Derecho_aduanal
                                current_factura_destinatario.Importe_Servicio_Aduanal_Total = current_factura_destinatario.Importe_Servicio_Aduanal_Total - current_inventario.Importe_Servicio_aduanal
                                current_factura_destinatario.save()
                                # Registro de trazas
                                save_addition(request.user, 'factura', current_factura_destinatario.id, str(model_to_dict(current_factura_destinatario)))

                                for current_factura_operador in factura_operador:
                                    current_factura_operador.Importe = current_factura_operador.Importe - (seguro_carga + sobredimension + transportacion + transcargo + corresponsalia)
                                    current_factura_operador.save()
                                    # Registro de trazas
                                    save_addition(request.user, 'factura_operador', current_factura_operador.id, str(model_to_dict(current_factura_operador)))

                                    #Se declara la reincorporacion
                                    inventario_reincorporado = Inventario_Reincorporado()
                                    inventario_reincorporado.Factura_Operador = current_factura_operador
                                    inventario_reincorporado.Inventario = current_inventario
                                    inventario_reincorporado.Observaciones = request.POST.get('Observaciones')
                                    inventario_reincorporado.Fecha = now()
                                    inventario_reincorporado.Importe                     = seguro_carga + sobredimension + transportacion + transcargo + corresponsalia
                                    inventario_reincorporado.Importe_Transcargo          = transcargo 
                                    inventario_reincorporado.Importe_Seguro_Carga        = seguro_carga 
                                    inventario_reincorporado.Importe_Transportacion      = transportacion
                                    inventario_reincorporado.Importe_Derecho_Aduanal     = current_inventario.Importe_Derecho_aduanal
                                    inventario_reincorporado.Importe_Servicio_Aduanal    = current_inventario.Importe_Servicio_aduanal
                                    inventario_reincorporado.save()
                                    # Registro de trazas
                                    save_addition(request.user, 'inventario_reincorporado', inventario_reincorporado.id, str(model_to_dict(inventario_reincorporado)))
                                
                                #Se elimina la relacion del inventario con la factura
                                with connection.cursor() as cursor:
                                    cursor.execute(""" delete from "inventario_factura_inventario" WHERE "inventario_factura_inventario"."Inventario_id" = '%s' AND "inventario_factura_inventario"."Factura_id" = '%s' """%(current_inventario.id, current_factura_destinatario.id))
                    
                messages.success(request, 'Mercancías reincorporadas al inventario satisfactoriamente.')  
                return redirect(request.path)  

        except Exception as inst:
            print(inst)
            messages.error(request, 'Ha ocurrido un error reincorporando los inventarios al almacén.')
            return redirect(request.path) 

    #Definiendo menu activo
    active_menu = 'mercancia_traslado'

    header_text     = 'Lista de mercancias en traslado'
    breadcrumb_text = 'Mercancias en traslado'

    inventarios = Inventario.objects.all().filter(Estado = 'Traslado')

    #Aplicacion de filtros
    inventario_filter = InventarioFilter(request.GET, queryset=inventarios)
    inventarios = inventario_filter.qs

    #Paginator
    paginator = Paginator(inventarios, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj, 'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'form_trasladar_almacen': form_trasladar_almacen, 'inventario_filter': inventario_filter}
    return render(request, 'entrega/mercancias_en_traslado.html', ctx)

@login_required(login_url='login')
def entrega_add(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Definiendo menu activo
    active_menu = 'mercancia_traslado'

    action = 'add'
    form_entrega   = Entrega_Form(initial={'Fecha_Entrega': now().date(), 'Hora_Salida': datetime.now().strftime('%H:%M')})
    form_empresa = Empresa_Form()
    form_hbl_escaneados = HBL_Escaneados_Form()
    #list_inventario = Inventario.objects.all().filter(Q(Estado = 'Inventario'), Q(Nacionalizado = True)).order_by('Destinatario__Municipio', 'Destinatario__CI')
    #Buscando comprobantes de entregas de destinatarios que no estan relacionados en comprobantes de entrega de operadores
    facturas_disponibles = []
    with connection.cursor() as cursor:
        cursor.execute(""" SELECT * FROM "inventario_factura" WHERE id not in 
                        (
                        SELECT "inventario_factura_operador_Facturas_Destinatarios"."factura_id" FROM "inventario_factura_operador_Facturas_Destinatarios" 
                        INNER JOIN "inventario_factura_operador" ON "inventario_factura_operador_Facturas_Destinatarios"."factura_operador_id" = "inventario_factura_operador"."id" 
                        WHERE not "inventario_factura_operador"."Estado" = 'Desestimada'
                        ) AND "inventario_factura"."Estado" = 'Creada' """)

        row = cursor.fetchall()
        for current in row:
            facturas_disponibles.append(list(current)[0])
    
    facturas = Factura.objects.all().filter(Q(id__in = facturas_disponibles)).order_by('id')
    
    if request.method == 'POST':
        form_entrega   = Entrega_Form(request.POST)
        hbl_escaneados = request.POST.get('crear_traslado_escaner')            

        if form_entrega.is_valid():
            chapa = request.POST.get('Chapa')
            transportista = request.POST.get('Transportista')
            if chapa:
                existe = Transportista.objects.filter(id=transportista,Chapa=chapa)
                if not existe:
                    messages.error(request, 'La chapa introduciada no corresponde al transportista seleccionado ')
                    return redirect(request.path) 
            if not hbl_escaneados:
                if len(request.POST.getlist('factura')) == 0:
                    messages.error(request, 'Debe seleccionar al menos una factura')
                    return redirect(request.path) 
            try:
                with transaction.atomic():
                    form_entrega_instance = form_entrega.save(commit=False)

                    #Almacenando valores
                    #Factura de operador
                    factura_operador = Factura_Operador()
                    factura_operador.Fecha_Creacion = now()
                    factura_operador.Estado = 'En espera'
                    factura_operador.Operador = form_entrega.cleaned_data['Operador']
                    factura_operador.User_Facturador = request.user
                    factura_operador.save()
                    # #Traslado
                    form_entrega_instance.Estado = 'Programado'
                    form_entrega_instance.Factura_Operador = factura_operador
                    form_entrega_instance.save()
                    # crear_factura_operador= False

                    if not hbl_escaneados:
                        #Agregando listado de comprobantes
                        for current_comprobante_id in request.POST.getlist('factura'):
                            current_comprobante = Factura.objects.get(pk = current_comprobante_id)
                            current_comprobante.Estado = 'Asignada'
                            current_comprobante.save()
                            factura_operador.Facturas_Destinatarios.add(current_comprobante)
                            factura_operador.Importe += current_comprobante.Importe_Total_Factura
                            factura_operador.save()
                    else:
                        hbl_regex = re.compile(r'([0-9]*)')
                        # hbl_regex = re.compile(r'("id_transaccion":)([ 0-9]*)')
                        # hbl_regex1 = re.compile(r'(transaccion)\S*([ 0-9]*)')
                        #HBL escaneados
                        list_comprobantes = request.POST.get('HBL')   
                        seleccion = re.findall(hbl_regex,list_comprobantes)
                        seleccion = set(seleccion)
                        for hbl in seleccion:
                            if hbl:
                                current_comprobante = Factura.objects.get(pk = hbl)
                                current_comprobante.Estado = 'Asignada'
                                current_comprobante.save()
                                factura_operador.Facturas_Destinatarios.add(current_comprobante)
                                factura_operador.Importe += current_comprobante.Importe_Total_Factura
                                factura_operador.save()

                    # Registro de trazas
                    save_addition(request.user, 'entrega', form_entrega_instance.id, str(model_to_dict(form_entrega_instance)))
                    save_addition(request.user, 'factura_operador', factura_operador.id, str(model_to_dict(factura_operador)))
                    save_addition(request.user, 'factura', current_comprobante.id, str(model_to_dict(current_comprobante)))

                    messages.success(request, 'Traslado programado satisfactoriamente')
                    return redirect(reverse('entrega_detail', kwargs={"id_entrega": form_entrega_instance.id}))
            except Exception as inst:
                print(inst)
                messages.error(request, 'Ha ocurrido un error programando el traslado')
                return redirect(request.path) 

    ctx = {'action': action, 'form_entrega': form_entrega,'form_hbl_escaneados':form_hbl_escaneados,'form_empresa':form_empresa, 'active_menu': active_menu, 'facturas': facturas}
    return render(request, 'entrega/entrega_edit.html', ctx)

@login_required(login_url='login')
def entrega_edit(request, id_entrega):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    action = 'edit'

    current_entrega = get_object_or_404(Entrega, pk = id_entrega)
    form_entrega   = Entrega_Form(instance=current_entrega)
    list_inventario = Inventario.objects.all().filter(Q(Estado = 'Inventario'), Q(Nacionalizado = True)).order_by('Destinatario__Municipio', 'Destinatario__CI')

    #Aplicacion de filtros
    inventario_filter = Entrega_Add_Filter(request.GET, queryset=list_inventario)
    list_inventario = inventario_filter.qs

    if request.method == 'POST':
        form_entrega   = Entrega_Form(request.POST, instance=current_entrega)

        if form_entrega.is_valid():
            form_entrega_instance = form_entrega.save(commit=False)

            #Almacenando valores
            form_entrega_instance.Estado = 'Programado'
            form_entrega_instance.save()

            #Capturando los inventarios seleccionados
            list_inventario_selected = request.POST.getlist('inventario')
            if list_inventario_selected:
                inventarios_selected_objects = Inventario.objects.all().filter(pk__in = list_inventario_selected)
                current_entrega.set_inventarios(inventarios_selected_objects)

            # Registro de trazas
            save_edition(request.user, 'entrega', current_entrega.id, str(model_to_dict(current_entrega)))
                
            messages.success(request, 'Traslado modificado satisfactoriamente')
            return redirect(reverse('entrega_detail', kwargs={"id_entrega": id_entrega}))

    #Paginator
    size = 400
    if request.GET.get('Municipio_Destinatario') and list_inventario.count() > 0:
        size = list_inventario.count()
        
    paginator = Paginator(list_inventario, size) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'action': action, 'form_entrega': form_entrega, 'page_obj': page_obj, 'current_entrega': current_entrega, 'inventario_filter': inventario_filter}
    return render(request, 'entrega/entrega_edit.html', ctx)

@login_required(login_url='login')
def entrega_detail(request, id_entrega):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    current_entrega = get_object_or_404(Entrega, pk = id_entrega)

    if request.method == 'POST':
        if request.POST.get('action') == 'action_cancelar':
            current_entrega.Estado = 'Cancelado'
            current_entrega.save()
            # Registro de trazas
            save_edition(request.user, 'entrega', current_entrega.id, str(model_to_dict(current_entrega)))

            factura_operador = Factura_Operador.objects.get(pk = current_entrega.Factura_Operador.id)
            factura_operador.Estado = 'Desestimada'
            factura_operador.save()
            # Registro de trazas
            save_edition(request.user, 'factura_operador', factura_operador.id, str(model_to_dict(factura_operador)))

            for current_factura in factura_operador.Facturas_Destinatarios.all():
                current_factura.Estado = 'Creada'
                current_factura.save()
                # Registro de trazas
                save_edition(request.user, 'factura', current_factura.id, str(model_to_dict(current_factura)))

            messages.success(request, 'Traslado cancelado satisfactoriamente')
            return redirect('entrega_programadas')
    
    ctx = {'current_entrega': current_entrega}
    return render(request, 'entrega/entrega_detail.html', ctx)

@login_required(login_url='login')
def entrega_programadas(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    entregas = Entrega.objects.all().order_by('Fecha_Entrega')

    if not request.GET.get('Estado'):
        entregas = entregas.filter(~Q(Estado = 'Cancelado'), ~Q(Estado = 'Concluido'))

    #Definiendo menu activo
    active_menu = 'mercancia_traslado'

    #Aplicacion de filtros
    entregas_filter = Traslados_Programados_Filter(request.GET, queryset=entregas)
    entregas = entregas_filter.qs

    #Paginator
    paginator = Paginator(entregas, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj, 'active_menu': active_menu, 'entregas_filter': entregas_filter}
    return render(request, 'entrega/entrega_list.html', ctx)

@login_required(login_url='login')
def ejecutar_entrega(request, id_entrega):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    current_entrega = Entrega.objects.get(id = id_entrega)
    current_entrega.Fecha_Entrega = now().date()
    current_entrega.Hora_Salida = datetime.now().strftime('%H:%M')
    form_entrega   = Entrega_Ejecutar_Form(instance= current_entrega)

    if request.method == 'POST':
        form_entrega   = Entrega_Ejecutar_Form(request.POST, instance= current_entrega)

        if form_entrega.is_valid():
            try:
                with transaction.atomic():
                    form_entrega_instance = form_entrega.save(commit=False)
                    form_entrega_instance.Estado = 'Ejecucion'
                    form_entrega_instance.save()

                    #Actualizando el comprobante del transportista
                    form_entrega_instance.Factura_Operador.Estado = 'Pendiente de cobro'
                    form_entrega_instance.Factura_Operador.save()

                    #Capturando las facturas asociadas
                    for current_factura_destinatario in form_entrega_instance.Factura_Operador.Facturas_Destinatarios.all():
                        #Capturando los inventarios seleccionados
                        for current_inventario in current_factura_destinatario.Inventario.all():
                            current_inventario.Estado = 'Traslado'
                            current_inventario.Fecha_Traslado = now()
                            current_inventario.save()

                            #Salvando Tracking
                            traking = Traking()
                            traking.Inventario      = current_inventario
                            traking.Estado          = 'En tránsito'
                            traking.Observaciones   = 'Inventario en tránsito'
                            traking.Fecha           = now()
                            traking.save()
                            # Registro de trazas
                            save_addition(request.user, 'traking', traking.id, str(model_to_dict(traking)))

                            # Registro de trazas
                            save_edition(request.user, 'inventario', current_inventario.id, str(model_to_dict(current_inventario)))

                    # Registro de trazas
                    save_edition(request.user, 'entrega', form_entrega_instance.id, str(model_to_dict(form_entrega_instance)))
                        
                    messages.success(request, 'Traslado en ejecución')
                    return redirect(reverse('entrega_detail', kwargs={"id_entrega": id_entrega}))
            except Exception as inst:
                print(inst)
                messages.error(request, 'Ha ocurrido un error ejecutando el traslado')
                return redirect(request.path) 
    
    ctx = {'current_entrega': current_entrega, 'form_entrega': form_entrega}
    return render(request, 'entrega/ejecutar_entrega.html', ctx)

def concluir_entrega(request, id_entrega):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    current_entrega = Entrega.objects.get(id = id_entrega)
    form_entrega   = Entrega_Concluir_Form(instance= current_entrega)
    
    if request.method == 'POST':
        form_entrega   = Entrega_Concluir_Form(request.POST, instance= current_entrega)

        if form_entrega.is_valid():
            form_entrega_instance = form_entrega.save(commit=False)
            form_entrega_instance.Estado = 'Concluido'
            form_entrega_instance.save()

            # Registro de trazas
            save_edition(request.user, 'entrega', form_entrega_instance.id, str(model_to_dict(form_entrega_instance)))

            messages.success(request, 'Traslado concluido satisfactoriamente')
            return redirect(reverse('entrega_detail', kwargs={"id_entrega": id_entrega}))
    
    ctx = {'current_entrega': current_entrega, 'form_entrega': form_entrega}
    return render(request, 'operacion_mercancia/operacion_concluir_entrega_inventario.html', ctx)


#----Gestion de citas------------------------------------------------------
@login_required(login_url='login')
def cita_list(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    header_text     = 'Lista de mercancias con citas programadas'
    breadcrumb_text = 'Mercancias con citas'
    #Definiendo menu activo
    active_menu = 'mercancia_citas'

    inventarios = Inventario.objects.all().filter(Estado = 'Inventario')

    #Aplicacion de filtros
    inventario_filter = InventarioFilter(request.GET, queryset=inventarios)
    inventarios = inventario_filter.qs

    #Paginator
    paginator = Paginator(inventarios, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj, 'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'inventario_filter': inventario_filter}
    return render(request, 'inventario/inventario_list.html', ctx)

@login_required(login_url='login')
def cita_add(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Definiendo menu activo
    active_menu = 'mercancia_citas'

    action = 'add'
    form_cita   = Cita_Form()
    list_inventario = Inventario.objects.all().filter(Q(Estado = 'Inventario'), Q(Nacionalizado = True))

    if request.method == 'POST':
        form_cita   = Cita_Form(request.POST)
        
        if form_cita.is_valid():
            form_cita_instance = form_cita.save(commit=False)

            #Almacenando valores
            form_cita_instance.save()
            current_cita = Cita.objects.get(id = form_cita_instance.id)

            #Capturando los inventarios seleccionados
            list_inventario_selected = request.POST.getlist('inventario')
            if list_inventario_selected:
                inventarios_selected_objects = Inventario.objects.all().filter(pk__in = list_inventario_selected)
                current_cita.set_inventarios(inventarios_selected_objects)

            # Registro de trazas
            save_addition(request.user, 'cita', current_cita.id, str(model_to_dict(current_cita)))

            messages.success(request, 'Cita programada satisfactoriamente')
            return redirect('cita_list')

    #Paginator
    paginator = Paginator(list_inventario, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'action': action, 'form_cita': form_cita, 'active_menu': active_menu, 'page_obj': page_obj}
    return render(request, 'cita/cita_edit.html', ctx)

@login_required(login_url='login')
def cita_edit(request, id_cita):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    action = 'edit'

    current_cita = get_object_or_404(Cita, pk = id_cita)
    form_cita   = Cita_Form(instance=current_cita)
    list_inventario = Inventario.objects.all().filter(Estado = 'Inventario')

    if request.method == 'POST':
        form_cita   = Cita_Form(request.POST, instance=current_cita)

        if form_cita.is_valid():
            form_cita_instance = form_cita.save(commit=False)

            #Almacenando valores
            form_cita_instance.save()

            #Capturando los inventarios seleccionados
            list_inventario_selected = request.POST.getlist('inventario')
            if list_inventario_selected:
                inventarios_selected_objects = Inventario.objects.all().filter(pk__in = list_inventario_selected)
                current_cita.set_inventarios(inventarios_selected_objects)

            # Registro de trazas
            save_edition(request.user, 'cita', current_cita.id, str(model_to_dict(current_cita)))
                
            messages.success(request, 'Cita modificada satisfactoriamente')
            return redirect(reverse('cita_detail', kwargs={"id_cita": id_cita}))

    #Paginator
    paginator = Paginator(list_inventario, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'action': action, 'form_cita': form_cita, 'page_obj': page_obj, 'current_cita': current_cita}
    return render(request, 'cita/cita_edit.html', ctx)

@login_required(login_url='login')
def cita_detail(request, id_cita):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    current_cita = get_object_or_404(Cita, pk = id_cita)
    
    ctx = {'current_cita': current_cita}
    return render(request, 'cita/cita_detail.html', ctx)

def cita_programadas(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    citas = Cita.objects.all()

    #Definiendo menu activo
    active_menu = 'mercancia_citas'

    #Aplicacion de filtros
    citas_filter = Citas_Filter(request.GET, queryset=citas)
    citas = citas_filter.qs

    #Paginator
    paginator = Paginator(citas, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj, 'active_menu': active_menu, 'citas_filter': citas_filter}
    return render(request, 'cita/cita_list.html', ctx)


#----Operaciones de mercancia---------------------------------------------------
@login_required(login_url='login')
def operacion_entrada_inventario(request, id_inventario):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    inventario = get_object_or_404(Inventario, pk = id_inventario)

    form = Operacion_Entrar_Inventario_Form(instance= inventario)

    if request.method == 'POST':
        form = Operacion_Entrar_Inventario_Form(request.POST, instance= inventario)
        
        if form.is_valid():
            form_instance = form.save(commit=False)

            form_instance.Estado = 'Inventario'
            form_instance.save()

            #Salvando Tracking
            traking = Traking()
            traking.Inventario      = form_instance
            traking.Estado          = 'En almacén'
            traking.Observaciones   = 'Inventario reincorporado al almacén'
            traking.Fecha           = now()
            traking.save()
            # Registro de trazas
            save_addition(request.user, 'traking', traking.id, str(model_to_dict(traking)))

            # Registro de trazas
            save_edition(request.user, 'inventario', form_instance.id, str(model_to_dict(form_instance)))
            
            messages.success(request, 'Mercancía agregada al inventario satisfactoriamente')
            return redirect(reverse('inventario_detail', kwargs={"id_inventario": id_inventario}))

    ctx = {'inventario': inventario, 'form': form}
    return render(request, 'operacion_mercancia/operacion_entrada_inventario.html', ctx)

def operacion_nacionalizar_inventario(request, id_inventario):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    inventario = get_object_or_404(Inventario, pk = id_inventario)

    if request.method == 'POST':
        #Nacionalizando inventario
        inventario.Nacionalizado = True
        inventario.Fecha_Nacionalizacion = now()

        try:
            #Capturando valores de la aduana
            man = str(inventario.Manifiesto)
            if len(man.split('/')[0]) < 4:
                man = str(inventario.Manifiesto).zfill(4)
                    
            if len(man.split('/')) == 1:
                man = man + '/' + str(inventario.Fecha_Entrada_Puerto.year)

            #dicto = {'success': True, 'despachos': [{'BOLETIN_DERECHO': '171021047035915000007', 'NO_BLGA': 'MAY21110540', 'MANIFIESTOS': '0358/2021', 'VALOR_DERECHOS': '0', 'VALOR_SERVICIO': '50'}]}
            USUARIO = 'aerov'
            PASS = 'eh7443fx'
            MANIFIESTO = man
            HBL = inventario.HBL
            CODIGO_ADUANA = '0200'

            URL= 'https://sua.aduana.cu/GINASUA/serviciosExternos.php'
            headers = {
                'Content-Type': 'application/xml',
                'Accept': 'application/xml',
            }
            data = '<?xml version=\"1.0\" encoding=\"utf-8\"?><soap:Envelope xmlns:soap=\"http://schemas.xmlsoap.org/soap/envelope/\"><soap:Body><GABLDespachado><usuario>'+ USUARIO +'</usuario><clave>'+ PASS +'</clave><manifiesto>'+ MANIFIESTO +'</manifiesto><blga>'+ HBL +'</blga><codigoaduana>'+ CODIGO_ADUANA +'</codigoaduana></GABLDespachado></soap:Body></soap:Envelope>'
                            
            resp = requests.get( URL, headers = headers, data = data, verify=False )
            resp_strip = strip_tags(resp.content)
            dict = resp_strip.replace('\\', '').replace("b'n", ""). replace("n'", "")
            dicto = json.loads(dict)

            if dicto['success'] == True:
                inventario.Importe_Derecho_aduanal = float(dicto['despachos'][0]['VALOR_DERECHOS'])
                inventario.Importe_Servicio_aduanal = float(dicto['despachos'][0]['VALOR_SERVICIO'])
                inventario.Precio = 0
                inventario.Categoria_Operacion = 'ENVIO'
            else:
                inventario.Importe_Derecho_aduanal = 0
                inventario.Importe_Servicio_aduanal = 0
                inventario.Precio = 0
                if inventario.Categoria_Operacion == None:
                    inventario.Categoria_Operacion = 'E.N.A'
        except:
            inventario.Importe_Derecho_aduanal = 0
            inventario.Importe_Servicio_aduanal = 0
            inventario.Precio = 0

        inventario.save()

        # Registro de trazas
        save_edition(request.user, 'inventario', inventario.id, str(model_to_dict(inventario)))
            
        messages.success(request, 'Mercancía nacionalizada satisfactoriamente')
        return redirect(reverse('inventario_detail', kwargs={"id_inventario": id_inventario}))

    ctx = {'inventario': inventario}
    return render(request, 'operacion_mercancia/operacion_nacionalizar_inventario.html', ctx)

@login_required(login_url='login')
def operacion_entregar_inventario(request, id_inventario):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    inventario = get_object_or_404(Inventario, pk = id_inventario)

    form = Operacion_Entregar_Inventario_Form(instance= inventario)

    if request.method == 'POST':
        form = Operacion_Entregar_Inventario_Form(request.POST, instance= inventario)
        
        if form.is_valid():
            form_instance = form.save(commit=False)

            if inventario.Nacionalizado == False:
                form_instance.Nacionalizado = True
                form_instance.Fecha_Nacionalizacion = now()

            if form_instance.Estado == 'Traslado':
                form_instance.Tipo_Entrega = 'Puerta a puerta'
            else:
                form_instance.Tipo_Entrega = 'Presencial'

            form_instance.Estado = 'Entregado'
            form_instance.Fecha_Entrega = now()
            form_instance.save()

            #Salvando Tracking
            traking = Traking()
            traking.Inventario      = form_instance
            traking.Estado          = 'Entregado'
            traking.Observaciones   = 'Inventario entregado al destinatario'
            traking.Fecha           = now()
            traking.save()
            # Registro de trazas
            save_addition(request.user, 'traking', traking.id, str(model_to_dict(traking)))

            #Eliminacion de transportaciones de la carga entregada
            lista_entrega = Entrega.objects.all().filter(Q(Inventario = form_instance), Q(Estado = 'Programado'))
            for current_entrega in lista_entrega:
                current_entrega.Inventario.remove(form_instance.id)
                current_entrega.save()
                
            # Registro de trazas
            save_edition(request.user, 'inventario', form_instance.id, str(model_to_dict(form_instance)))
            
            messages.success(request, 'Mercancía entregada satisfactoriamente')
            return redirect(reverse('inventario_detail', kwargs={"id_inventario": id_inventario}))

    ctx = {'inventario': inventario, 'form': form}
    return render(request, 'operacion_mercancia/operacion_entrega_inventario.html', ctx)

@login_required(login_url='login')
def operacion_devolucion_inventario(request, id_inventario):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    inventario = get_object_or_404(Inventario, pk = id_inventario)

    if inventario.Estado == 'Entregado':
        raise Http404

    form = Operacion_Devolucion_Inventario_Form(instance= inventario)

    if request.method == 'POST':
        form = Operacion_Devolucion_Inventario_Form(request.POST, instance= inventario)
        
        if form.is_valid():
            form_instance = form.save(commit=False)

            form_instance.Fecha_Devolución = now()
            form_instance.Estado = 'Salida de inventario'
            form_instance.save()

            #Eliminacion de transportaciones de la carga entregada
            lista_entrega = Entrega.objects.all().filter(Q(Inventario = form_instance), Q(Estado = 'Programado'))
            for current_entrega in lista_entrega:
                current_entrega.Inventario.remove(form_instance.id)
                current_entrega.save()

            # Registro de trazas
            save_edition(request.user, 'inventario', form_instance.id, str(model_to_dict(form_instance)))
            
            messages.success(request, 'Mercancía eliminada del inventario satisfactoriamente')
            return redirect(reverse('inventario_detail', kwargs={"id_inventario": id_inventario}))

    ctx = {'inventario': inventario, 'form': form}
    return render(request, 'operacion_mercancia/operacion_devolucion_inventario.html', ctx)

@login_required(login_url='login')
def operacion_no_localizable_inventario(request, id_inventario):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    inventario = get_object_or_404(Inventario, pk = id_inventario)

    if inventario.Estado == 'Entregado':
        raise Http404

    form = Operacion_No_Localizable_Inventario_Form(instance= inventario)

    if request.method == 'POST':
        form = Operacion_No_Localizable_Inventario_Form(request.POST, instance= inventario)
        
        if form.is_valid():
            form_instance = form.save(commit=False)

            form_instance.Estado = 'No localizable'
            form_instance.Fecha_No_Localizable = now()
            form_instance.save()

            #Salvando Tracking
            traking = Traking()
            traking.Inventario      = form_instance
            traking.Estado          = 'No localizable'
            traking.Observaciones   = 'El inventario no se encuentra localizable en estos momentos'
            traking.Fecha           = now()
            traking.save()
            # Registro de trazas
            save_addition(request.user, 'traking', traking.id, str(model_to_dict(traking)))

            #Eliminacion de transportaciones de la carga entregada
            lista_entrega = Entrega.objects.all().filter(Q(Inventario = form_instance), Q(Estado = 'Programado'))
            for current_entrega in lista_entrega:
                current_entrega.Inventario.remove(form_instance.id)
                current_entrega.save()

            # Registro de trazas
            save_edition(request.user, 'inventario', form_instance.id, str(model_to_dict(form_instance)))
            
            messages.success(request, 'Mercancía declarada no localizable satisfactoriamente')
            return redirect(reverse('inventario_detail', kwargs={"id_inventario": id_inventario}))

    ctx = {'inventario': inventario, 'form': form}
    return render(request, 'operacion_mercancia/operacion_no_localizable_inventario.html', ctx)

#----Gestion de mercancias entregadas------------------------------------------------------
def inventarios_entregados_list(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    header_text     = 'Lista de mercancías entregadas'
    breadcrumb_text = 'Mercancías entergadas'

    #Definiendo menu activo
    active_menu = 'mercancia_entregadas'

    inventarios = Inventario.objects.all().filter(Estado = 'Entregado')

    #Aplicacion de filtros
    inventario_filter = InventarioFilter(request.GET, queryset=inventarios)
    inventarios = inventario_filter.qs

    #Paginator
    paginator = Paginator(inventarios, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj, 'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'inventario_filter': inventario_filter}
    return render(request, 'inventario/inventario_list.html', ctx)

#----Gestion de mercancias en devolucion------------------------------------------------------
def inventarios_devolucion_list(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    header_text     = 'Cargas eliminadas del inventario'
    breadcrumb_text = 'Cargas eliminadas del inventario'

    #Definiendo menu activo
    active_menu = 'mercancia_devolucion'

    inventarios = Inventario.objects.all().filter(Estado = 'Salida de inventario')

    #Aplicacion de filtros
    inventario_filter = InventarioFilter(request.GET, queryset=inventarios)
    inventarios = inventario_filter.qs

    #Paginator
    paginator = Paginator(inventarios, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj, 'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'inventario_filter': inventario_filter}
    return render(request, 'inventario/inventario_list.html', ctx)

#----Gestion de mercancias no localizables------------------------------------------------------
def inventarios_no_localizable_list(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    header_text     = 'Lista de mercancías no localizables'
    breadcrumb_text = 'Mercancías no localizables'

    #Formulario de tabla
    form_trasladar_almacen = Operacion_Trasladar_De_Almacen_Form()
    form_nacionalizar_carga   = Operacion_Nacionalizar_Inventario_Form()

    #Ejecutando operaciones de las tablas
    operaciones_de_tablas(request) 

    #Definiendo menu activo
    active_menu = 'mercancia_no_localizable'

    inventarios = Inventario.objects.all().filter(Estado = 'No localizable')

    #Aplicacion de filtros
    inventario_filter = InventarioFilter(request.GET, queryset=inventarios)
    inventarios = inventario_filter.qs

    #Paginator
    paginator = Paginator(inventarios, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj, 'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'inventario_filter': inventario_filter, 'form_trasladar_almacen': form_trasladar_almacen, 'form_nacionalizar_carga': form_nacionalizar_carga}
    return render(request, 'inventario/inventario_list.html', ctx)

#----Gestion de Acceso--------------------------------------------------------
def loginPage(request):
    if request.user.is_authenticated:
        return redirect('inicio')
    else:
        if request.method == 'POST':
            username = request.POST['username']
            password = request.POST['password']

            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)
                return redirect('inicio')
            else:
                messages.error(request, 'Usuario o contraseña incorrecta')
                return redirect('login')

        ctx = {}
        return render(request, 'others/login.html', ctx)

def logoutUser(request):
    logout(request)
    return redirect('login')

#----Gestion de reportes------------------------------------------------------
@login_required(login_url='login')
def inventarios_reportes(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Definiendo menu activo
    active_menu = 'reportes'
    
    #Lista de inventarios
    inventarios = Inventario.objects.all()

    #Aplicacion de filtros
    inventario_filter = Inventario_Reporte_Filter(request.GET, queryset=inventarios)
    inventarios = inventario_filter.qs

    #Paginator
    paginator = Paginator(inventarios, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj, 'active_menu': active_menu, 'inventario_filter': inventario_filter}
    return render(request, 'inventario/inventario_reportes.html', ctx)

@login_required(login_url='login')
def control_de_ingresos(request): 
    #Validando roles
    if not (request.user.groups.filter(name__in=['Contabilidad']).exists()) and not request.user.is_superuser:
        raise Http404

    #Definiendo menu activo
    active_menu = 'reportes'
    #Formulario de captura de informacion
    form = Reporte_Control_Ingresos_Form()
    #Info de listado
    data = []

    #Captura de fechas
    if request.method == 'POST':
        form = Reporte_Control_Ingresos_Form(request.POST)
        if form.is_valid():
            fecha_desde = datetime.strptime(str(form.cleaned_data.get('Fecha_Desde')), '%Y-%m-%d')
            fecha_hasta = datetime.strptime(str(form.cleaned_data.get('Fecha_Hasta')), '%Y-%m-%d')
            operador = request.POST.get('Operador')
            for current_date in range(fecha_desde.timetuple().tm_yday, fecha_hasta.timetuple().tm_yday + 1):
                #Diccionario
                dicto = {}
                # Initializing start date
                strt_date = date(int(fecha_desde.year), 1, 1)
                # converting to date
                res_date = strt_date + timedelta(days=int(current_date) - 1)
                fecha = res_date
                #Valores de cada fila
                #Fecha
                dicto['fecha'] = fecha
                #Cantidad de facturas a procesar por fila
                comprobantes_operadores = Factura_Operador.objects.filter(Q(Fecha_Creacion__year = fecha.year), Q(Fecha_Creacion__month = fecha.month), Q(Fecha_Creacion__day = fecha.day), Q(Estado = 'Pendiente de cobro') | Q(Estado = 'Cobrada'), Operador = operador)
                #Informacion preliminar
                #Envios
                envios_pequenos = 0
                envios_medianos = 0
                envios_grandes = 0
                #ENA
                ena_cantidad = 0
                ena_metros_cubicos_cantidad = 0
                #Menaje
                menaje_cantidad = 0
                menaje_metros_cubicos_cantidad = 0
                for current_comprobante_operador in comprobantes_operadores:
                    for current_factura in current_comprobante_operador.Facturas_Destinatarios.all():
                        for current_inventario in current_factura.Inventario.all():
                            #Envios
                            if current_factura.isEnvio:
                                if current_inventario.Peso <= 1.5:
                                    envios_pequenos = envios_pequenos + 1
                                if current_inventario.Peso > 1.5 and current_inventario.Peso <= 50:
                                    envios_medianos = envios_medianos + 1
                                if current_inventario.Peso > 50:
                                    envios_grandes = envios_grandes + 1
                            #ENA o Menaje
                            if not current_factura.isEnvio:
                                if current_inventario.Categoria_Operacion == 'ENA' or current_inventario.Categoria_Operacion == 'ena' or current_inventario.Categoria_Operacion == 'Ena' or current_inventario.Categoria_Operacion == 'E.N.A' or current_inventario.Categoria_Operacion == 'e.n.a' or current_inventario.Categoria_Operacion == 'E.n.a': 
                                    ena_cantidad = ena_cantidad + 1
                                    ena_metros_cubicos_cantidad = ena_metros_cubicos_cantidad + current_inventario.Volumen
                                if current_inventario.Categoria_Operacion == 'MENAJE' or current_inventario.Categoria_Operacion == 'Menaje' or current_inventario.Categoria_Operacion == 'menaje':
                                    menaje_cantidad = menaje_cantidad + 1
                                    menaje_metros_cubicos_cantidad = menaje_metros_cubicos_cantidad + menaje_metros_cubicos_cantidad * current_inventario.Volumen        

                #Completamiento de informacion
                #Envios
                dicto['envios_pequenos'] = envios_pequenos
                dicto['envios_medianos'] = envios_medianos
                dicto['envios_grandes'] = envios_grandes
                dicto['envios_plus'] = 0.04 * (dicto['envios_pequenos'] + dicto['envios_medianos'] + dicto['envios_grandes'])
                dicto['envios_pequenos_importe'] = dicto['envios_pequenos'] * 12.00
                dicto['envios_medianos_importe'] = dicto['envios_medianos'] * 12.00 #DEFINIR VALOR
                dicto['envios_grandes_importe'] = dicto['envios_grandes'] * 12.00
                #ENA
                dicto['ena_cantidad'] = ena_cantidad
                dicto['ena_plus'] = dicto['ena_cantidad'] * 14.96
                dicto['ena_metros_cubicos_importe'] = ena_metros_cubicos_cantidad * 765.00
                #Menaje
                dicto['menaje_cantidad'] = menaje_cantidad
                dicto['menaje_plus'] = dicto['menaje_cantidad'] * 22.30
                dicto['menaje_metros_cubicos_importe'] = menaje_metros_cubicos_cantidad * 765.00
                data.append(dicto)
                
    ctx = {'active_menu': active_menu, 'form': form, 'data': data}
    return render(request, 'reportes/control_de_ingresos.html', ctx)

@login_required(login_url='login')
def reporte_ingresos_diarios(request): 
    #Validando roles
    if not (request.user.groups.filter(name__in=['Contabilidad']).exists()) and not request.user.is_superuser:
        raise Http404

    #Definiendo menu activo
    active_menu = 'reportes'
    #Formulario de captura de informacion
    form = Reporte_Control_Ingresos_Form()
    #Info de listado
    data = []
    #Valores totales del reporte
    valores_totales = {}

    #Captura de fechas
    if request.method == 'POST':
        form = Reporte_Control_Ingresos_Form(request.POST)
        if form.is_valid():
            fecha_desde = datetime.strptime(str(form.cleaned_data.get('Fecha_Desde')), '%Y-%m-%d')
            fecha_hasta = datetime.strptime(str(form.cleaned_data.get('Fecha_Hasta')), '%Y-%m-%d')

            #Valores totales del reporte
            valores_totales['importe_transcargo_total'] = 0
            valores_totales['seguro_carga_total'] = 0
            valores_totales['recargo_total'] = 0
            valores_totales['transportacion_total'] = 0
            valores_totales['derecho_aduanal_total'] = 0
            valores_totales['servicio_aduanal_total'] = 0
            valores_totales['sobredimension_total'] = 0
            valores_totales['corresponsalia_total'] = 0
            valores_totales['cantidad_HBL_total'] = 0
            valores_totales['total_total'] = 0
            
            for current_date in range(fecha_desde.timetuple().tm_yday, fecha_hasta.timetuple().tm_yday + 1):
                #Diccionario
                dicto = {}
                # Initializing start date
                strt_date = date(int(fecha_desde.year), 1, 1)
                # converting to date
                res_date = strt_date + timedelta(days=int(current_date) - 1)
                fecha = res_date
                #Valores de cada fila
                dicto['fecha'] = fecha
                dicto['importe_transcargo'] = 0
                dicto['seguro_carga'] = 0
                dicto['recargo'] = 0
                dicto['transportacion'] = 0
                dicto['derecho_aduanal'] = 0
                dicto['servicio_aduanal'] = 0
                dicto['sobredimension'] = 0
                dicto['corresponsalia'] = 0
                dicto['cantidad_HBL'] = 0
                dicto['total'] = 0

                #Cantidad de facturas a procesar por fila
                comprobantes_operadores = Factura_Operador.objects.filter(Q(Fecha_Creacion__year = fecha.year), Q(Fecha_Creacion__month = fecha.month), Q(Fecha_Creacion__day = fecha.day), Q(Estado = 'Pendiente de cobro') | Q(Estado = 'Cobrada'))
                lista_facturas_destinatarios = []

                for current_comprobante_operador in comprobantes_operadores:
                    for current_factura in current_comprobante_operador.Facturas_Destinatarios.all():
                        lista_facturas_destinatarios.append(current_factura)

                comprobantes_destinatario = Factura.objects.filter(Q(Fecha_cobro__year = fecha.year), Q(Fecha_cobro__month = fecha.month), Q(Fecha_cobro__day = fecha.day), Q(Estado = 'Cobrada'))
                for current_comprobante in comprobantes_destinatario:
                    if lista_facturas_destinatarios.count(current_comprobante) == 0:
                           lista_facturas_destinatarios.append(current_comprobante)
                
                for current_factura in lista_facturas_destinatarios:
                    if current_factura.Importe_Total_Factura > 0:
                        if current_factura.Importe_Transcargo_Total:
                            dicto['importe_transcargo'] += current_factura.Importe_Transcargo_Total
                        if current_factura.Importe_Seguro_Carga_Total:
                            dicto['seguro_carga'] += current_factura.Importe_Seguro_Carga_Total
                        if current_factura.Importe_Recargo_Total:    
                            dicto['recargo'] += current_factura.Importe_Recargo_Total
                        if current_factura.Importe_Transportacion_Total:    
                            dicto['transportacion'] += current_factura.Importe_Transportacion_Total
                        if current_factura.Importe_Derecho_Aduanal_Total:    
                            dicto['derecho_aduanal'] += current_factura.Importe_Derecho_Aduanal_Total
                        if current_factura.Importe_Servicio_Aduanal_Total:    
                            dicto['servicio_aduanal'] += current_factura.Importe_Servicio_Aduanal_Total
                        if current_factura.Importe_Sobredimension_Total:    
                            dicto['sobredimension'] += current_factura.Importe_Sobredimension_Total
                        if current_factura.Importe_Servicio_Corresponsalia_Total:
                            dicto['corresponsalia'] += current_factura.Importe_Servicio_Corresponsalia_Total
                        if current_factura.Inventario.all().count():
                            dicto['cantidad_HBL'] += current_factura.Inventario.all().count()
                        if current_factura.Importe_Total_Factura:
                            dicto['total'] += current_factura.Importe_Total_Factura
                
                #Sumando valores totales
                valores_totales['importe_transcargo_total'] += dicto['importe_transcargo']
                valores_totales['seguro_carga_total'] += dicto['seguro_carga']
                valores_totales['recargo_total'] += dicto['recargo']
                valores_totales['transportacion_total'] += dicto['transportacion']
                valores_totales['derecho_aduanal_total'] += dicto['derecho_aduanal']
                valores_totales['servicio_aduanal_total'] += dicto['servicio_aduanal']
                valores_totales['sobredimension_total'] += dicto['sobredimension']
                valores_totales['corresponsalia_total'] += dicto['corresponsalia']
                valores_totales['cantidad_HBL_total'] += dicto['cantidad_HBL']
                valores_totales['total_total'] += dicto['total']
                
                data.append(dicto)
                
    ctx = {'active_menu': active_menu, 'form': form, 'data': data, 'valores_totales': valores_totales}
    return render(request, 'reportes/ingresos_diarios.html', ctx)

@login_required(login_url='login')
def reporte_ingresos_diarios_noviembre(request): 
    #Validando roles
    if not (request.user.groups.filter(name__in=['Contabilidad']).exists()) and not request.user.is_superuser:
        raise Http404

    #Definiendo menu activo
    active_menu = 'reportes'
    #Formulario de captura de informacion
    form = Reporte_Control_Ingresos_Form()
    #Info de listado
    data = []
    #Valores totales del reporte
    valores_totales = {}

    #Captura de fechas
    if request.method == 'POST':
        form = Reporte_Control_Ingresos_Form(request.POST)
        if form.is_valid():
            fecha_desde = datetime.strptime(str(form.cleaned_data.get('Fecha_Desde')), '%Y-%m-%d')
            fecha_hasta = datetime.strptime(str(form.cleaned_data.get('Fecha_Hasta')), '%Y-%m-%d')

            #Valores totales del reporte
            valores_totales['importe_transcargo_total'] = 0
            valores_totales['seguro_carga_total'] = 0
            valores_totales['recargo_total'] = 0
            valores_totales['transportacion_total'] = 0
            valores_totales['derecho_aduanal_total'] = 0
            valores_totales['servicio_aduanal_total'] = 0
            valores_totales['sobredimension_total'] = 0
            valores_totales['corresponsalia_total'] = 0
            valores_totales['cantidad_HBL_total'] = 0
            valores_totales['total_total'] = 0
            
            #PARA FACTURAS CON FECHA
            for current_date in range(fecha_desde.timetuple().tm_yday, fecha_hasta.timetuple().tm_yday + 1):
                #Diccionario
                dicto = {}
                # Initializing start date
                strt_date = date(int(fecha_desde.year), 1, 1)
                # converting to date
                res_date = strt_date + timedelta(days=int(current_date) - 1)
                fecha = res_date
                #Valores de cada fila
                dicto['fecha'] = fecha
                dicto['importe_transcargo'] = 0
                dicto['seguro_carga'] = 0
                dicto['recargo'] = 0
                dicto['transportacion'] = 0
                dicto['derecho_aduanal'] = 0
                dicto['servicio_aduanal'] = 0
                dicto['sobredimension'] = 0
                dicto['corresponsalia'] = 0
                dicto['cantidad_HBL'] = 0
                dicto['total'] = 0

                #Cantidad de facturas a procesar por fila
                facturas_trazas = LogEntry.objects.all().filter(Q(content_type_id = 18), Q(action_flag = 1), action_time__year = fecha.year, action_time__month = fecha.month, action_time__day = fecha.day)
                
                for current_traza in facturas_trazas:
                    try:
                        current_factura = Factura.objects.get(pk = current_traza.object_id)
                    except:
                        current_factura = None

                    if current_factura:
                        if current_factura.Contenido and current_factura.isMultiple:
                            #contenido = "[{'Copias_Facturas': range(0, 1), 'Importe_Transcargo_Total': 1243.91, 'Importe_Seguro_Carga_Total': 12.0, 'Importe_Sobredimension_Total': 0.0, 'Importe_Recargo_Total': 0.0, 'Importe_Transportacion_Total': 390.0, 'Importe_Derecho_Aduanal_Total': 0.0, 'Importe_Servicio_Aduanal_Total': 650.0, 'Destinatario': <Destinatario: Darlyn Veronica Ponce Cabado>, 'Inventarios': [{'Inventario': <Inventario: MXT2050012802001>, 'Importe_Seguro_Carga': 12.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 283.91}, {'Inventario': <Inventario: MXT2050012803001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012804001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012805001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012806001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012807001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012808001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012809001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012810001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012811001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012812001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012813001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012814001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}], 'Precio_Total_Factura': 2295.91}]"
                            contenido_uno = current_factura.Contenido.replace("'Copias_Facturas': range(0, 1), ", '').replace('[', '').replace(']', '').split(', ')
                            if (len(contenido_uno) >= 7):
                                contenido_para_json = contenido_uno[0] + ', ' + contenido_uno[1] + ', ' + contenido_uno[2] + ', ' + contenido_uno[3] + ', ' + contenido_uno[4] + ', ' + contenido_uno[5] + ', ' + contenido_uno[6] + '}'
                                contenido_json = json.loads(contenido_para_json.replace("'", '"'))

                                if contenido_json['Importe_Transcargo_Total']:
                                    dicto['importe_transcargo'] += contenido_json['Importe_Transcargo_Total']

                                if contenido_json['Importe_Seguro_Carga_Total']:
                                    dicto['seguro_carga'] += contenido_json['Importe_Seguro_Carga_Total']

                                if contenido_json['Importe_Recargo_Total']:
                                    dicto['recargo'] += contenido_json['Importe_Recargo_Total']

                                if contenido_json['Importe_Transportacion_Total']:
                                    dicto['transportacion'] += contenido_json['Importe_Transportacion_Total']

                                if contenido_json['Importe_Derecho_Aduanal_Total']:
                                    dicto['derecho_aduanal'] += contenido_json['Importe_Derecho_Aduanal_Total']

                                if contenido_json['Importe_Servicio_Aduanal_Total']:
                                    dicto['servicio_aduanal'] += contenido_json['Importe_Servicio_Aduanal_Total']

                                if current_factura.isEnvio:
                                    if contenido_json['Importe_Sobredimension_Total']:
                                        dicto['sobredimension'] += contenido_json['Importe_Sobredimension_Total']
                                else:
                                    if contenido_json['Importe_Servicio_Corresponsalia_Total']:
                                        dicto['corresponsalia'] += contenido_json['Importe_Servicio_Corresponsalia_Total']
                                
                                dicto['total'] = dicto['importe_transcargo'] + dicto['seguro_carga'] + dicto['recargo'] + dicto['transportacion'] + dicto['derecho_aduanal'] + dicto['servicio_aduanal']
                                
                                if current_factura.isEnvio:
                                    dicto['total'] += dicto['sobredimension']
                                else:
                                    dicto['total'] += dicto['corresponsalia']

                                dicto['cantidad_HBL'] += current_factura.Contenido.count("{'Inventario':")

                        if current_factura.Contenido and not current_factura.isMultiple:
                            #contenido_no_multiple = "{'Inventario': <Inventario: MXT2050008282001>, 'Copias_Facturas': range(0, 1), 'Importe_Transcargo': 765.0, 'Importe_Seguro_Carga': 96.0, 'Importe_Servicio_Corresponsalia': 57.0, 'Importe_Transportacion': 30.0, 'Precio_Total_Factura': 998.0}"
                            contenido_no_multiple_uno = current_factura.Contenido.split(', ')
                            if len(contenido_no_multiple_uno) >= 8:
                                contenido_para_json = '{' + contenido_no_multiple_uno[3] + ', ' + contenido_no_multiple_uno[4] + ', ' + contenido_no_multiple_uno[5] + ', ' + contenido_no_multiple_uno[6] + ', ' + contenido_no_multiple_uno[7]
                                contenido_json = json.loads(contenido_para_json.replace("'", '"'))
                                #Inventario referido
                                HBL_current = contenido_no_multiple_uno[0].replace("{'Inventario': <Inventario: ", '').replace('>', '')
                                current_inventario = Inventario.objects.filter(HBL = HBL_current).first()
                                
                                if contenido_json['Importe_Transcargo']:
                                    dicto['importe_transcargo'] += contenido_json['Importe_Transcargo']

                                if contenido_json['Importe_Seguro_Carga']:
                                    dicto['seguro_carga'] += contenido_json['Importe_Seguro_Carga']

                                if current_inventario.Precio:
                                    dicto['recargo'] += current_inventario.Precio

                                if contenido_json['Importe_Transportacion']:
                                    dicto['transportacion'] += contenido_json['Importe_Transportacion']

                                if current_inventario.Importe_Derecho_aduanal:
                                    dicto['derecho_aduanal'] += current_inventario.Importe_Derecho_aduanal

                                if current_inventario.Importe_Servicio_aduanal:
                                    dicto['servicio_aduanal'] += current_inventario.Importe_Servicio_aduanal

                                if current_factura.isEnvio:
                                    if contenido_json['Importe_Sobredimension']:
                                        dicto['sobredimension'] += contenido_json['Importe_Sobredimension']
                                else:
                                    if contenido_json['Importe_Servicio_Corresponsalia']:
                                        dicto['corresponsalia'] += contenido_json['Importe_Servicio_Corresponsalia']
                                
                                dicto['total'] = dicto['importe_transcargo'] + dicto['seguro_carga'] + dicto['recargo'] + dicto['transportacion'] + dicto['derecho_aduanal'] + dicto['servicio_aduanal']
                                
                                if current_factura.isEnvio:
                                    if contenido_json['Importe_Sobredimension']:
                                        dicto['total'] += contenido_json['Importe_Sobredimension']
                                else:
                                    if contenido_json['Importe_Servicio_Corresponsalia']:
                                        dicto['total'] += contenido_json['Importe_Servicio_Corresponsalia']

                                dicto['cantidad_HBL'] += current_factura.Contenido.count("{'Inventario':")

                #Sumando valores totales
                valores_totales['importe_transcargo_total'] += dicto['importe_transcargo']
                valores_totales['seguro_carga_total'] += dicto['seguro_carga']
                valores_totales['recargo_total'] += dicto['recargo']
                valores_totales['transportacion_total'] += dicto['transportacion']
                valores_totales['derecho_aduanal_total'] += dicto['derecho_aduanal']
                valores_totales['servicio_aduanal_total'] += dicto['servicio_aduanal']
                valores_totales['sobredimension_total'] += dicto['sobredimension']
                valores_totales['corresponsalia_total'] += dicto['corresponsalia']
                valores_totales['cantidad_HBL_total'] += dicto['cantidad_HBL']
                valores_totales['total_total'] += dicto['total']
                
                data.append(dicto)
                
    ctx = {'active_menu': active_menu, 'form': form, 'data': data, 'valores_totales': valores_totales}
    return render(request, 'reportes/ingresos_diarios.html', ctx)

@login_required(login_url='login')
def reporte_contable(request): 
    #Validando roles
    if not (request.user.groups.filter(name__in=['Contabilidad']).exists()) and not request.user.is_superuser:
        raise Http404

    #Definiendo menu activo
    active_menu = 'reportes'
    #Formulario de captura de informacion
    form = Reporte_Control_Ingresos_Form()
    #Info de listado
    data = []
    #Valores totales del reporte
    valores_totales = {}

    #Captura de fechas
    if request.method == 'POST':
        form = Reporte_Control_Ingresos_Form(request.POST)
        if form.is_valid():
            fecha_desde = datetime.strptime(str(form.cleaned_data.get('Fecha_Desde')), '%Y-%m-%d')
            fecha_hasta = datetime.strptime(str(form.cleaned_data.get('Fecha_Hasta')), '%Y-%m-%d')
            operador = request.POST.get('Operador')
            #Obteniendo datos de Transportista
            chapa = request.POST.get('Chapa')
            #Obteniendo datos de Empresa
            empresa = request.POST.get('Empresa')

            #Valores totales del reporte
            valores_totales['importe_transcargo_total'] = 0
            valores_totales['transportacion_total'] = 0
            valores_totales['corresponsalia_total'] = 0
            valores_totales['subtotal_total'] = 0
            valores_totales['derecho_aduanal_total'] = 0
            valores_totales['servicio_aduanal_total'] = 0
            valores_totales['honorarios_transcargo_total'] = 0
            valores_totales['total_total'] = 0
            # honorarios_transcargo = 0
            for current_date in range(fecha_desde.timetuple().tm_yday, fecha_hasta.timetuple().tm_yday + 1):
                #Diccionario
                dicto = {}
                # Initializing start date
                strt_date = date(int(fecha_desde.year), 1, 1)
                # converting to date
                res_date = strt_date + timedelta(days=int(current_date) - 1)
                fecha = res_date
                #Valores de cada fila
                dicto['fecha'] = fecha
                dicto['importe_transcargo'] = 0
                dicto['transportacion'] = 0
                dicto['corresponsalia'] = 0
                dicto['subtotal'] = 0
                dicto['derecho_aduanal'] = 0
                dicto['servicio_aduanal'] = 0
                # dicto['honorarios_transcargo'] = 0
                dicto['total'] = 0

                #Cantidad de facturas a procesar por fila
                comprobantes_operadores = Factura_Operador.objects.filter(Q(Fecha_Creacion__year = fecha.year), Q(Fecha_Creacion__month = fecha.month), Q(Fecha_Creacion__day = fecha.day), Q(Estado = 'Pendiente de cobro') | Q(Estado = 'Cobrada'))
                if operador:
                    comprobantes_operadores = comprobantes_operadores.filter(Operador = operador)
                if chapa:
                    traslados = Entrega.objects.filter(Transportista=chapa)
                    id_facturas_operador =[]
                    for traslado in traslados:
                        id_facturas_operador.append(traslado.Factura_Operador.id)
                    comprobantes_operadores = comprobantes_operadores.filter(id__in=id_facturas_operador)
                if empresa:
                    transportistas = Transportista.objects.filter(Empresa=empresa)
                    id_transportisas = []
                    for transportista in transportistas:
                        id_transportisas.append(transportista.id)
                    traslados = Entrega.objects.filter(Transportista__in=id_transportisas)
                    id_facturas_operador =[]
                    for traslado in traslados:
                        id_facturas_operador.append(traslado.Factura_Operador.id)
                    comprobantes_operadores = comprobantes_operadores.filter(id__in=id_facturas_operador)

                lista_facturas_destinatarios = []

                for current_comprobante_operador in comprobantes_operadores:
                    for current_factura in current_comprobante_operador.Facturas_Destinatarios.all():
                        # honorarios_transcargo += (current_factura.Importe_Derecho_Aduanal_Total + current_factura.Importe_Servicio_Aduanal_Total) * 0.011
                        lista_facturas_destinatarios.append(current_factura)

                comprobantes_destinatario = Factura.objects.filter(Q(Fecha_cobro__year = fecha.year), Q(Fecha_cobro__month = fecha.month), Q(Fecha_cobro__day = fecha.day), Q(Estado = 'Cobrada'))
                for current_comprobante in comprobantes_destinatario:
                    if lista_facturas_destinatarios.count(current_comprobante) == 0:
                           lista_facturas_destinatarios.append(current_comprobante)

                for current_factura in lista_facturas_destinatarios:
                    if current_factura.Importe_Total_Factura > 0:
                        #Inicializando valores
                        importe_transcargo = 0
                        seguro_carga = 0
                        recargo = 0
                        transportacion = 0
                        derecho_aduanal = 0
                        servicio_aduanal = 0
                        sobredimension = 0
                        corresponsalia = 0
                        cantidad_hbl_menor = 0
                        cantidad_hbl_mayor = 0
                        corresponsalia_contable = 0
                        
                        if current_factura.Importe_Transcargo_Total:
                            importe_transcargo = current_factura.Importe_Transcargo_Total
                        if current_factura.Importe_Seguro_Carga_Total:
                            seguro_carga = current_factura.Importe_Seguro_Carga_Total
                        if current_factura.Importe_Recargo_Total:    
                            recargo = current_factura.Importe_Recargo_Total
                        if current_factura.Importe_Transportacion_Total:    
                            transportacion = current_factura.Importe_Transportacion_Total
                        if current_factura.Importe_Derecho_Aduanal_Total:    
                            derecho_aduanal = current_factura.Importe_Derecho_Aduanal_Total
                        if current_factura.Importe_Servicio_Aduanal_Total:    
                            servicio_aduanal = current_factura.Importe_Servicio_Aduanal_Total
                        if current_factura.Importe_Sobredimension_Total:    
                            sobredimension = current_factura.Importe_Sobredimension_Total
                        if current_factura.Importe_Servicio_Corresponsalia_Total:
                            corresponsalia = current_factura.Importe_Servicio_Corresponsalia_Total
                        if current_factura.Inventario:
                            cantidad_hbl_menor = current_factura.Inventario.all().filter(Peso__lte = 1.50).count()
                            cantidad_hbl_mayor = current_factura.Inventario.all().filter(Peso__gt = 1.50).count()

                        #Calculando corresponsalia
                        corresponsalia_contable = round(float(cantidad_hbl_menor * 41.04 + cantidad_hbl_mayor * 133.68), 2)
                        #Calculando   
                        """
                        if current_factura.isEnvio:                             
                            dicto['importe_transcargo'] += importe_transcargo - 57.00 + sobredimension + recargo * 0.7
                            dicto['corresponsalia'] += 57.00 + recargo * 0.3 + seguro_carga
                        else:
                            dicto['importe_transcargo'] += importe_transcargo + sobredimension + recargo * 0.7
                            dicto['corresponsalia'] += corresponsalia + recargo * 0.3 + seguro_carga
                        """
                        dicto['importe_transcargo'] += round(float(importe_transcargo + sobredimension + recargo * 0.7 - corresponsalia_contable), 2)
                        
                        # print('dicto[importe_transcargo] += '+ str(importe_transcargo)+' + '+str(sobredimension)+' + '+str(recargo)+' * 0.7 - '+str(corresponsalia_contable))
                        # print('dicto[importe_transcargo] = ' + str(round(float(importe_transcargo + sobredimension + round(float(recargo * 0.7), 2) - corresponsalia_contable), 2)))

                        dicto['corresponsalia'] += round(float(corresponsalia_contable + recargo * 0.3 + seguro_carga + corresponsalia), 2)
                        # print('dicto[corresponsalia] += '+str(corresponsalia_contable)+' + '+str(recargo)+' * 0.3 + '+str(seguro_carga)+' + '+str(corresponsalia)+'')
                        # print('dicto[corresponsalia] = ' + str(round(float(corresponsalia_contable + round(float(recargo * 0.3), 2) + seguro_carga + corresponsalia), 2)))


                        dicto['transportacion'] += transportacion
                        # dicto['honorarios_transcargo'] = honorarios_transcargo
                        dicto['subtotal'] = dicto['importe_transcargo'] + dicto['transportacion'] + dicto['corresponsalia']
                        dicto['derecho_aduanal'] += derecho_aduanal
                        dicto['servicio_aduanal'] += servicio_aduanal
                        dicto['total'] = dicto['importe_transcargo'] + dicto['transportacion'] + dicto['corresponsalia'] + dicto['derecho_aduanal'] + dicto['servicio_aduanal']
                #Sumando valores totales
                valores_totales['importe_transcargo_total'] += dicto['importe_transcargo']
                valores_totales['transportacion_total'] += dicto['transportacion']
                valores_totales['corresponsalia_total'] += dicto['corresponsalia']
                valores_totales['subtotal_total'] += dicto['subtotal']
                valores_totales['derecho_aduanal_total'] += dicto['derecho_aduanal']
                valores_totales['servicio_aduanal_total'] += dicto['servicio_aduanal']
                # valores_totales['honorarios_transcargo_total'] += dicto['honorarios_transcargo']
                valores_totales['total_total'] += dicto['total']
                
                data.append(dicto)
                
    ctx = {'active_menu': active_menu, 'form': form, 'data': data, 'valores_totales': valores_totales}
    return render(request, 'reportes/reporte_contable.html', ctx)

@login_required(login_url='login')
def reporte_contable_noviembre(request): 
    #Validando roles
    if not (request.user.groups.filter(name__in=['Contabilidad']).exists()) and not request.user.is_superuser:
        raise Http404

    #Definiendo menu activo
    active_menu = 'reportes'
    #Formulario de captura de informacion
    form = Reporte_Control_Ingresos_Form()
    #Info de listado
    data = []
    #Valores totales del reporte
    valores_totales = {}

    #Captura de fechas
    if request.method == 'POST':
        form = Reporte_Control_Ingresos_Form(request.POST)
        if form.is_valid():
            fecha_desde = datetime.strptime(str(form.cleaned_data.get('Fecha_Desde')), '%Y-%m-%d')
            fecha_hasta = datetime.strptime(str(form.cleaned_data.get('Fecha_Hasta')), '%Y-%m-%d')

            #Valores totales del reporte
            valores_totales['importe_transcargo_total'] = 0
            valores_totales['seguro_carga_total'] = 0
            valores_totales['recargo_total'] = 0
            valores_totales['transportacion_total'] = 0
            valores_totales['derecho_aduanal_total'] = 0
            valores_totales['servicio_aduanal_total'] = 0
            valores_totales['sobredimension_total'] = 0
            valores_totales['corresponsalia_total'] = 0
            valores_totales['cantidad_HBL_total'] = 0
            valores_totales['total_total'] = 0

            #Contabilidad
            valores_totales['importe_transcargo_contable_total'] = 0
            valores_totales['transportacion_contable_total'] = 0
            valores_totales['corresponsalia_contable_total'] = 0
            valores_totales['subtotal_contable_total'] = 0
            valores_totales['derecho_aduanal_contable_total'] = 0
            valores_totales['servicio_aduanal_contable_total'] = 0
            valores_totales['total_contable_total'] = 0
            
            #PARA FACTURAS CON FECHA
            for current_date in range(fecha_desde.timetuple().tm_yday, fecha_hasta.timetuple().tm_yday + 1):
                #Diccionario
                dicto = {}
                # Initializing start date
                strt_date = date(int(fecha_desde.year), 1, 1)
                # converting to date
                res_date = strt_date + timedelta(days=int(current_date) - 1)
                fecha = res_date
                #Valores de cada fila
                dicto['fecha'] = fecha
                dicto['importe_transcargo'] = 0
                dicto['seguro_carga'] = 0
                dicto['recargo'] = 0
                dicto['transportacion'] = 0
                dicto['derecho_aduanal'] = 0
                dicto['servicio_aduanal'] = 0
                dicto['sobredimension'] = 0
                dicto['corresponsalia'] = 0
                dicto['cantidad_HBL'] = 0
                dicto['cantidad_HBL_menores'] = 0
                dicto['total'] = 0
                
                #Contabilidad
                dicto['importe_transcargo_contable'] = 0
                dicto['transportacion_contable'] = 0
                dicto['corresponsalia_contable'] = 0
                dicto['subtotal_contable'] = 0
                dicto['derecho_aduanal_contable'] = 0
                dicto['servicio_aduanal_contable'] = 0
                dicto['total_contable'] = 0

                #Cantidad de facturas a procesar por fila
                facturas_trazas = LogEntry.objects.all().filter(Q(content_type_id = 18), Q(action_flag = 1), action_time__year = fecha.year, action_time__month = fecha.month, action_time__day = fecha.day)
                
                for current_traza in facturas_trazas:
                    try:
                        current_factura = Factura.objects.get(pk = current_traza.object_id)
                    except:
                        current_factura = None

                    if current_factura:
                        if current_factura.Contenido and current_factura.isMultiple:
                            #contenido = "[{'Copias_Facturas': range(0, 1), 'Importe_Transcargo_Total': 1243.91, 'Importe_Seguro_Carga_Total': 12.0, 'Importe_Sobredimension_Total': 0.0, 'Importe_Recargo_Total': 0.0, 'Importe_Transportacion_Total': 390.0, 'Importe_Derecho_Aduanal_Total': 0.0, 'Importe_Servicio_Aduanal_Total': 650.0, 'Destinatario': <Destinatario: Darlyn Veronica Ponce Cabado>, 'Inventarios': [{'Inventario': <Inventario: MXT2050012802001>, 'Importe_Seguro_Carga': 12.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 283.91}, {'Inventario': <Inventario: MXT2050012803001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012804001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012805001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012806001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012807001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012808001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012809001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012810001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012811001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012812001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012813001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012814001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}], 'Precio_Total_Factura': 2295.91}]"
                            contenido_uno = current_factura.Contenido.replace("'Copias_Facturas': range(0, 1), ", '').replace('[', '').replace(']', '').split(', ')
                            if (len(contenido_uno) >= 7):
                                contenido_para_json = contenido_uno[0] + ', ' + contenido_uno[1] + ', ' + contenido_uno[2] + ', ' + contenido_uno[3] + ', ' + contenido_uno[4] + ', ' + contenido_uno[5] + ', ' + contenido_uno[6] + '}'
                                contenido_json = json.loads(contenido_para_json.replace("'", '"'))

                                if contenido_json['Importe_Transcargo_Total']:
                                    dicto['importe_transcargo'] += contenido_json['Importe_Transcargo_Total']

                                if contenido_json['Importe_Seguro_Carga_Total']:
                                    dicto['seguro_carga'] += contenido_json['Importe_Seguro_Carga_Total']

                                if contenido_json['Importe_Recargo_Total']:
                                    dicto['recargo'] += contenido_json['Importe_Recargo_Total']

                                if contenido_json['Importe_Transportacion_Total']:
                                    dicto['transportacion'] += contenido_json['Importe_Transportacion_Total']

                                if contenido_json['Importe_Derecho_Aduanal_Total']:
                                    dicto['derecho_aduanal'] += contenido_json['Importe_Derecho_Aduanal_Total']

                                if contenido_json['Importe_Servicio_Aduanal_Total']:
                                    dicto['servicio_aduanal'] += contenido_json['Importe_Servicio_Aduanal_Total']

                                if current_factura.isEnvio:
                                    if contenido_json['Importe_Sobredimension_Total']:
                                        dicto['sobredimension'] += contenido_json['Importe_Sobredimension_Total']
                                else:
                                    if contenido_json['Importe_Servicio_Corresponsalia_Total']:
                                        dicto['corresponsalia'] += contenido_json['Importe_Servicio_Corresponsalia_Total']
                                
                                dicto['total'] = dicto['importe_transcargo'] + dicto['seguro_carga'] + dicto['recargo'] + dicto['transportacion'] + dicto['derecho_aduanal'] + dicto['servicio_aduanal']
                                
                                if current_factura.isEnvio:
                                    dicto['total'] += dicto['sobredimension']
                                else:
                                    dicto['total'] += dicto['corresponsalia']

                                dicto['cantidad_HBL'] += current_factura.Contenido.count("{'Inventario':")

                        if current_factura.Contenido and not current_factura.isMultiple:
                            #contenido_no_multiple = "{'Inventario': <Inventario: MXT2050008282001>, 'Copias_Facturas': range(0, 1), 'Importe_Transcargo': 765.0, 'Importe_Seguro_Carga': 96.0, 'Importe_Servicio_Corresponsalia': 57.0, 'Importe_Transportacion': 30.0, 'Precio_Total_Factura': 998.0}"
                            contenido_no_multiple_uno = current_factura.Contenido.split(', ')
                            if len(contenido_no_multiple_uno) >= 8:
                                contenido_para_json = '{' + contenido_no_multiple_uno[3] + ', ' + contenido_no_multiple_uno[4] + ', ' + contenido_no_multiple_uno[5] + ', ' + contenido_no_multiple_uno[6] + ', ' + contenido_no_multiple_uno[7]
                                contenido_json = json.loads(contenido_para_json.replace("'", '"'))
                                #Inventario referido
                                HBL_current = contenido_no_multiple_uno[0].replace("{'Inventario': <Inventario: ", '').replace('>', '')
                                current_inventario = Inventario.objects.filter(HBL = HBL_current).first()
                                
                                if contenido_json['Importe_Transcargo']:
                                    dicto['importe_transcargo'] += contenido_json['Importe_Transcargo']

                                if contenido_json['Importe_Seguro_Carga']:
                                    dicto['seguro_carga'] += contenido_json['Importe_Seguro_Carga']

                                if current_inventario.Precio:
                                    dicto['recargo'] += current_inventario.Precio

                                if contenido_json['Importe_Transportacion']:
                                    dicto['transportacion'] += contenido_json['Importe_Transportacion']

                                if current_inventario.Importe_Derecho_aduanal:
                                    dicto['derecho_aduanal'] += current_inventario.Importe_Derecho_aduanal

                                if current_inventario.Importe_Servicio_aduanal:
                                    dicto['servicio_aduanal'] += current_inventario.Importe_Servicio_aduanal

                                if current_factura.isEnvio:
                                    if contenido_json['Importe_Sobredimension']:
                                        dicto['sobredimension'] += contenido_json['Importe_Sobredimension']
                                else:
                                    if contenido_json['Importe_Servicio_Corresponsalia']:
                                        dicto['corresponsalia'] += contenido_json['Importe_Servicio_Corresponsalia']
                                
                                dicto['total'] = dicto['importe_transcargo'] + dicto['seguro_carga'] + dicto['recargo'] + dicto['transportacion'] + dicto['derecho_aduanal'] + dicto['servicio_aduanal']
                                
                                if current_factura.isEnvio:
                                    if contenido_json['Importe_Sobredimension']:
                                        dicto['total'] += contenido_json['Importe_Sobredimension']
                                else:
                                    if contenido_json['Importe_Servicio_Corresponsalia']:
                                        dicto['total'] += contenido_json['Importe_Servicio_Corresponsalia']

                                dicto['cantidad_HBL'] += current_factura.Contenido.count("{'Inventario':")

                #Sumando valores totales
                valores_totales['importe_transcargo_total'] += dicto['importe_transcargo']
                valores_totales['seguro_carga_total'] += dicto['seguro_carga']
                valores_totales['recargo_total'] += dicto['recargo']
                valores_totales['transportacion_total'] += dicto['transportacion']
                valores_totales['derecho_aduanal_total'] += dicto['derecho_aduanal']
                valores_totales['servicio_aduanal_total'] += dicto['servicio_aduanal']
                valores_totales['sobredimension_total'] += dicto['sobredimension']
                valores_totales['corresponsalia_total'] += dicto['corresponsalia']
                valores_totales['cantidad_HBL_total'] += dicto['cantidad_HBL']
                valores_totales['total_total'] += dicto['total']

                #Contabilidad
                corresponsalia = dicto['cantidad_HBL'] * 57.00
                
                dicto['importe_transcargo_contable'] = dicto['importe_transcargo'] + dicto['sobredimension'] + (dicto['recargo'] * 0.70) - corresponsalia
                dicto['transportacion_contable'] = dicto['transportacion']
                dicto['corresponsalia_contable'] = corresponsalia + (dicto['recargo'] * 0.30) + dicto['seguro_carga']
                dicto['subtotal_contable'] = dicto['importe_transcargo_contable'] + dicto['transportacion_contable'] + dicto['corresponsalia_contable']
                dicto['derecho_aduanal_contable'] = dicto['derecho_aduanal']
                dicto['servicio_aduanal_contable'] = dicto['servicio_aduanal']
                dicto['total_contable'] = dicto['subtotal_contable'] + dicto['derecho_aduanal_contable'] + dicto['servicio_aduanal_contable']

                valores_totales['importe_transcargo_contable_total'] += dicto['importe_transcargo_contable']
                valores_totales['transportacion_contable_total'] += dicto['transportacion_contable']
                valores_totales['corresponsalia_contable_total'] += dicto['corresponsalia_contable']
                valores_totales['subtotal_contable_total'] += dicto['subtotal_contable']
                valores_totales['derecho_aduanal_contable_total'] += dicto['derecho_aduanal_contable']
                valores_totales['servicio_aduanal_contable_total'] += dicto['servicio_aduanal_contable']
                valores_totales['total_contable_total'] += dicto['total_contable']

                data.append(dicto)

    ctx = {'active_menu': active_menu, 'form': form, 'data': data, 'valores_totales': valores_totales}
    return render(request, 'reportes/reporte_contable_noviembre.html', ctx)

#-------Reporte Aduana

@login_required(login_url='login')
def reporte_contable_aduana(request): 
    #Validando roles
    if not (request.user.groups.filter(name__in=['Contabilidad']).exists()) and not request.user.is_superuser:
        raise Http404

    #Definiendo menu activo
    active_menu = 'reportes'
    #Formulario de captura de informacion
    form = Reporte_Contable_Aduana_Form()
    #Info de listado
    data = []
    #Valores totales del reporte
    valores_totales = {}

    #Captura de fechas
    if request.method == 'POST':
        form = Reporte_Contable_Aduana_Form(request.POST)
        if form.is_valid():
            fecha_desde = datetime.strptime(str(form.cleaned_data.get('Fecha_Desde')), '%Y-%m-%d')
            fecha_hasta = datetime.strptime(str(form.cleaned_data.get('Fecha_Hasta')), '%Y-%m-%d')
            #Valores totales del reporte
            valores_totales['derecho_aduanal_total'] = 0
            valores_totales['servicio_aduanal_total'] = 0
            valores_totales['honorarios_transcargo_total'] = 0
            valores_totales['total_total'] = 0
            for current_date in range(fecha_desde.timetuple().tm_yday, fecha_hasta.timetuple().tm_yday + 1):
                #Diccionario
                dicto = {}
                # Initializing start date
                strt_date = date(int(fecha_desde.year), 1, 1)
                # converting to date
                res_date = strt_date + timedelta(days=int(current_date) - 1)
                fecha = res_date
                #Valores de cada fila
                dicto['fecha'] = fecha
                dicto['derecho_aduanal'] = 0
                dicto['servicio_aduanal'] = 0
                dicto['honorarios_transcargo'] = 0
                dicto['total'] = 0

                #Cantidad de facturas a procesar por fila
                # inventarios = Inventario.objects.filter(Q(Fecha_Nacionalizacion__year = fecha.year), Q(Fecha_Nacionalizacion__month = fecha.month), Q(Fecha_Nacionalizacion__day = fecha.day),Nacionalizado=True)
                inventarios = Inventario.objects.filter(Q(Fecha_Nacionalizacion__year = fecha.year), Q(Fecha_Nacionalizacion__month = fecha.month), Q(Fecha_Nacionalizacion__day = fecha.day),Nacionalizado=True).values('Fecha_Nacionalizacion').order_by('Fecha_Nacionalizacion').annotate(derecho_aduanal=Sum('Importe_Derecho_aduanal')).annotate(servicio_aduanal=Sum('Importe_Servicio_aduanal'))
                # lista_facturas_destinatarios = []

                for inventario in inventarios:
                    dicto['derecho_aduanal'] += inventario['derecho_aduanal']
                    dicto['servicio_aduanal'] += inventario['servicio_aduanal']
                    dicto['honorarios_transcargo'] = (dicto['derecho_aduanal'] + dicto['servicio_aduanal']) * 0.011
                    dicto['total'] = dicto['derecho_aduanal'] + dicto['servicio_aduanal'] + dicto['honorarios_transcargo']
                #Sumando valores totales
                valores_totales['derecho_aduanal_total'] += dicto['derecho_aduanal']
                valores_totales['servicio_aduanal_total'] += dicto['servicio_aduanal']
                valores_totales['honorarios_transcargo_total'] += dicto['honorarios_transcargo']
                valores_totales['total_total'] += dicto['total']
                
                data.append(dicto)
                
    ctx = {'active_menu': active_menu, 'form': form, 'data': data, 'valores_totales': valores_totales}
    return render(request, 'reportes/reporte_contable_aduana.html', ctx)

@login_required(login_url='login')
def reporte_devoluciones(request): 
    #Validando roles
    if not (request.user.groups.filter(name__in=['Contabilidad']).exists()) and not request.user.is_superuser:
        raise Http404

    #Definiendo menu activo
    active_menu = 'reportes'
    #Formulario de captura de informacion
    form = Reporte_Contable_Aduana_Form()
    #Info de listado
    data = []
    #Valores totales del reporte
    valores_totales = {}

    #Captura de fechas
    if request.method == 'POST':
        form = Reporte_Contable_Aduana_Form(request.POST)
        if form.is_valid():
            fecha_desde = datetime.strptime(str(form.cleaned_data.get('Fecha_Desde')), '%Y-%m-%d')
            fecha_hasta = datetime.strptime(str(form.cleaned_data.get('Fecha_Hasta')), '%Y-%m-%d')
            
            #Valores totales del reporte
            valores_totales['importe_transcargo_total'] = 0
            valores_totales['transportacion_total'] = 0
            valores_totales['corresponsalia_total'] = 0
            valores_totales['subtotal_total'] = 0
            valores_totales['derecho_aduanal_total'] = 0
            valores_totales['servicio_aduanal_total'] = 0
            valores_totales['honorarios_transcargo_total'] = 0
            valores_totales['total_total'] = 0
            # honorarios_transcargo = 0
            for current_date in range(fecha_desde.timetuple().tm_yday, fecha_hasta.timetuple().tm_yday + 1):
                #Diccionario
                dicto = {}
                # Initializing start date
                strt_date = date(int(fecha_desde.year), 1, 1)
                # converting to date
                res_date = strt_date + timedelta(days=int(current_date) - 1)
                fecha = res_date
                #Valores de cada fila
                dicto['fecha'] = fecha
                dicto['importe_transcargo'] = 0
                dicto['transportacion'] = 0
                dicto['corresponsalia'] = 0
                dicto['subtotal'] = 0
                dicto['derecho_aduanal'] = 0
                dicto['servicio_aduanal'] = 0
                # dicto['honorarios_transcargo'] = 0
                dicto['total'] = 0

                #Capturando devoluciones
                devoluciones = Inventario_Reincorporado.objects.filter(Q(Fecha__year = fecha.year), Q(Fecha__month = fecha.month), Q(Fecha__day = fecha.day)).order_by('Fecha')

                for current_devolucion in devoluciones:
                    if current_devolucion.Importe > 0:
                        #Inicializando valores
                        importe_transcargo = 0
                        seguro_carga = 0
                        recargo = 0
                        transportacion = 0
                        derecho_aduanal = 0
                        servicio_aduanal = 0
                        
                        if current_devolucion.Importe_Transcargo:
                            importe_transcargo = current_devolucion.Importe_Transcargo
                        if current_devolucion.Importe_Seguro_Carga:
                            seguro_carga = current_devolucion.Importe_Seguro_Carga
                        if current_devolucion.Importe_Transportacion:    
                            transportacion = current_devolucion.Importe_Transportacion
                        if current_devolucion.Importe_Derecho_Aduanal:    
                            derecho_aduanal = current_devolucion.Importe_Derecho_Aduanal
                        if current_devolucion.Importe_Servicio_Aduanal:    
                            servicio_aduanal = current_devolucion.Importe_Servicio_Aduanal
                       
                        dicto['importe_transcargo'] += importe_transcargo
                        dicto['transportacion']     += transportacion
                        dicto['derecho_aduanal']    += derecho_aduanal
                        dicto['servicio_aduanal']   += servicio_aduanal
                        dicto['total'] = current_devolucion.Importe

                        dicto['corresponsalia'] += dicto['total'] - dicto['importe_transcargo'] - dicto['transportacion']
                        dicto['subtotal'] = dicto['importe_transcargo'] + dicto['transportacion'] + dicto['corresponsalia']
                        
                #Sumando valores totales
                valores_totales['importe_transcargo_total'] += dicto['importe_transcargo']
                valores_totales['transportacion_total'] += dicto['transportacion']
                valores_totales['corresponsalia_total'] += dicto['corresponsalia']
                valores_totales['subtotal_total'] += dicto['subtotal']
                valores_totales['derecho_aduanal_total'] += dicto['derecho_aduanal']
                valores_totales['servicio_aduanal_total'] += dicto['servicio_aduanal']
                # valores_totales['honorarios_transcargo_total'] += dicto['honorarios_transcargo']
                valores_totales['total_total'] += dicto['total']
                
                data.append(dicto)
                
    ctx = {'active_menu': active_menu, 'form': form, 'data': data, 'valores_totales': valores_totales}
    return render(request, 'reportes/reporte_devoluciones.html', ctx)

@login_required(login_url='login')
def reporte_cargas_en_desagrupe(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Formulario de tabla
    form_trasladar_almacen = Operacion_Trasladar_De_Almacen_Form()
    # form_nacionalizar_carga   = Operacion_Nacionalizar_Inventario_Form()

    #Ejecutando operaciones de las tablas
    operaciones_de_tablas(request)   
    #Informacion para el template
    header_text     = 'Cargas en desagrupe'
    breadcrumb_text = 'Cargas en desagrupe'
    #Definiendo menu activo
    active_menu = 'cargas_desagrupe'
    inventarios = Inventario.objects.filter(Estado = 'Desagrupe').order_by('HBL')

    #Aplicacion de filtros
    inventario_filter = InventarioFilter(request.GET, queryset=inventarios)
    inventarios = inventario_filter.qs

    #Paginator
    paginator = Paginator(inventarios, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj, 'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'form_trasladar_almacen': form_trasladar_almacen, 'inventario_filter': inventario_filter}
    return render(request, 'inventario/inventario_list.html', ctx)

#-------Gestion de Ajax------------------------------------------------------------------------
def ajax_inventario_load(request):
    id_inventario = request.GET.get('val_inventario')
    data = {}
    if id_inventario:
        inventario = Inventario.objects.get(id=id_inventario)
        #Creando informacion a devolver
        data['Manifiesto']=inventario.Manifiesto
        data['HBL']=inventario.HBL
        data['Cantidad_Bultos']=inventario.Cantidad_Bultos
        data['Peso']=inventario.Peso
        data['Volumen']=inventario.Volumen
        data['Estado']=inventario.Estado

    return JsonResponse(data)

def ajax_municipio_load(request):
    id_provincia = request.GET.get('id_provincia')
    data = {}
    if id_provincia:
        provincia  = Provincia.objects.get(pk = id_provincia)
        municipios = Municipio.objects.all().filter(Provincia = provincia).order_by('Nombre')
        #Creando informacion a devolver
        data = serializers.serialize('json', municipios)

    return JsonResponse(data, safe= False)

def ajax_load_cantidad_registros_a_nacionalizar(request):
    manifiesto = request.GET.get('manifiesto')
    contenedor = request.GET.get('contenedor')
    municipio = request.GET.get('municipio')

    data = {}
    inventarios = Inventario.objects.all().filter(Q(Manifiesto = manifiesto), Q(No_Contenedor = contenedor), Q(Nacionalizado = False))
    if municipio:
        inventarios = inventarios.filter(Q(Destinatario__Municipio = municipio))

    date = str(format(timedelta(seconds=int(inventarios.count())))).split(':')
    
    data['registros'] = inventarios.count()
    data['cantidad'] = date[0] + 'h y ' + date[1] + ' minutos'

    return JsonResponse(data)

def ajax_load_grafico_entrada_salida_cargas(request):
    data = {}
    content = []
    meses = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']

    #Seleccion de inventarios
    inventarios = Inventario.objects.all()

    for i in range(1, now().month + 1):
        month_data = {}
        month_data['Label'] = meses[i-1]
        month_data['Entrada'] = inventarios.filter(Fecha_Entrada__month = i).count()
        month_data['Salida'] = inventarios.filter(Fecha_Entrega__month = i).count()
        #Agregando contenido al arreglo de salida
        content.append(month_data)

    #Salida a la vista
    data['content'] = content
    data['bultos_de_menos'] = inventarios.filter(Q(Peso__lte = 1.5), Q(Fecha_Entrada__year = now().year)).count()
    data['bultos_de_mas'] = inventarios.filter(Q(Peso__gt = 1.5), Q(Fecha_Entrada__year = now().year)).count()

    return JsonResponse(data)

def test_aduana_conection(request):
    response = {}
    try:
        USUARIO = 'aerov'
        PASS = 'eh7443fx'
        MANIFIESTO = '0000'
        HBL = '0000'
        CODIGO_ADUANA = '0200'

        URL= 'https://sua.aduana.cu/GINASUA/serviciosExternos.php'
        headers = {
            'Content-Type': 'application/xml',
            'Accept': 'application/xml',
        }
        data = '<?xml version=\"1.0\" encoding=\"utf-8\"?><soap:Envelope xmlns:soap=\"http://schemas.xmlsoap.org/soap/envelope/\"><soap:Body><GABLDespachado><usuario>'+ USUARIO +'</usuario><clave>'+ PASS +'</clave><manifiesto>'+ MANIFIESTO +'</manifiesto><blga>'+ HBL +'</blga><codigoaduana>'+ CODIGO_ADUANA +'</codigoaduana></GABLDespachado></soap:Body></soap:Envelope>'
        
        resp = requests.get( URL, headers = headers, data = data, verify=False )
        resp_strip = strip_tags(resp.content)
        dict = resp_strip.replace('\\', '').replace("b'n", ""). replace("n'", "")
        dicto = json.loads(dict)
        response['response'] = True
    except:
        response['response'] = False
    
    return JsonResponse(response)

def ajax_transportistas_load(request):
    id_empresa = request.GET.get('id_empresa')
    data = {}
    if id_empresa:
        empresa  = Empresa.objects.get(pk = id_empresa)
        transportistas = Transportista.objects.all().filter(Empresa = empresa.Nombre).order_by('Nombre')
        #Creando informacion a devolver
        data = serializers.serialize('json', transportistas)
    return JsonResponse(data, safe= False) 

def ajax_existe_chapa_load(request):
    id_chapa = request.GET.get('id_Chapa')
    data = {}
    if id_chapa:
        chapa  = Transportista.objects.filter(Chapa = id_chapa)
        if chapa:
            #Creando informacion a devolver
            data = serializers.serialize('json', chapa)
    return JsonResponse(data, safe= False)    
#------------Operaciones--------------------------------
def operaciones_de_tablas(request):
    #Operaciones de la tabla    
    if request.method == 'POST':
        #Accion de mover inventario----------------------------------
        if request.POST.get('operacion_tabla') == 'mover_inventario':
            #Capturando datos del formulario
            id_almacen = request.POST.get('id_almacen_tabla')
            list_inventario = request.POST.getlist('inventario_id')
            
            #Validando que se haya seleccionado un almacen
            if not id_almacen:
                messages.error(request, 'Debe seleccionar un almacén para ubicar las cargas')
                return redirect(request.path)  

            #Obteniendo almacen
            current_almacen = Almacen.objects.get(id = id_almacen)
            
            #Recorriendo todos los inventarios seleccionados
            for id_current_inventario in list_inventario:
                current_inventario = Inventario.objects.get(id = id_current_inventario)
                current_inventario.Almacen = current_almacen
                current_inventario.Ubicacion_Fila = None
                current_inventario.Ubicacion_Columna = None
                current_inventario.Estado = 'Inventario'
                # if trasbordo:
                #     current_inventario.Tipo_Entrega='Trasbordo'
                current_inventario.save()

                # Registro de trazas
                save_edition(request.user, 'inventario', current_inventario.id, str(model_to_dict(current_inventario)))

            messages.success(request, 'Movimientos realizados satisfactoriamente')
            return redirect(request.path)

        #Accion de nacionalizar cargas------------------------------------------
        if request.POST.get('operacion_tabla') == 'nacionalizar_cargas':
            #Capturando datos del formulario
            list_inventario = request.POST.getlist('inventario_id')
            # print('list_inventario',list_inventario)
            #Recorriendo todos los inventarios seleccionados
            for id_current_inventario in list_inventario:
                #Obteniendo inventario
                current_inventario = Inventario.objects.get(id = id_current_inventario)

                #Actualizando inventario
                current_inventario.Nacionalizado = True
                current_inventario.Fecha_Nacionalizacion = now()
                
                try:
                    #Capturando valores de la aduana
                    man = str(current_inventario.Manifiesto)
                    if len(man.split('/')[0]) < 4:
                        man = str(current_inventario.Manifiesto).zfill(4)
                    
                    if len(man.split('/')) == 1:
                        man = man + '/' + str(current_inventario.Fecha_Entrada_Puerto.year)

                    #dicto = {'success': True, 'despachos': [{'BOLETIN_DERECHO': '171021047035915000007', 'NO_BLGA': 'MAY21110540', 'MANIFIESTOS': '0358/2021', 'VALOR_DERECHOS': '0', 'VALOR_SERVICIO': '50'}]}
                    USUARIO = 'aerov'
                    PASS = 'eh7443fx'
                    MANIFIESTO = man
                    HBL = current_inventario.HBL
                    CODIGO_ADUANA = '0200'

                    URL= 'https://sua.aduana.cu/GINASUA/serviciosExternos.php'
                    headers = {
                        'Content-Type': 'application/xml',
                        'Accept': 'application/xml',
                    }
                    data = '<?xml version=\"1.0\" encoding=\"utf-8\"?><soap:Envelope xmlns:soap=\"http://schemas.xmlsoap.org/soap/envelope/\"><soap:Body><GABLDespachado><usuario>'+ USUARIO +'</usuario><clave>'+ PASS +'</clave><manifiesto>'+ MANIFIESTO +'</manifiesto><blga>'+ HBL +'</blga><codigoaduana>'+ CODIGO_ADUANA +'</codigoaduana></GABLDespachado></soap:Body></soap:Envelope>'
                            
                    resp = requests.get( URL, headers = headers, data = data, verify=False )
                    print('resp',resp)

                    resp_strip = strip_tags(resp.content)
                    dict = resp_strip.replace('\\', '').replace("b'n", ""). replace("n'", "")
                    dicto = json.loads(dict)

                    print('-------------- CONSULTA ADUANA ------------------')
                    print(dicto)

                    if dicto['success'] == True:
                        # print('nacionalizacion')
                        current_inventario.Importe_Derecho_aduanal = float(dicto['despachos'][0]['VALOR_DERECHOS'])
                        current_inventario.Importe_Servicio_aduanal = float(dicto['despachos'][0]['VALOR_SERVICIO'])
                        current_inventario.Precio = 0
                        current_inventario.Categoria_Operacion = 'ENVIO'
                        # print('inventario',current_inventario)
                    else:
                        # print('no existe inventario',current_inventario)

                        current_inventario.Importe_Derecho_aduanal = 0
                        current_inventario.Importe_Servicio_aduanal = 0
                        current_inventario.Precio = 0
                        if current_inventario.Categoria_Operacion == None:
                            current_inventario.Categoria_Operacion = 'E.N.A'
                    
                    current_inventario.save()

                except:
                    current_inventario.Importe_Derecho_aduanal = 0
                    current_inventario.Importe_Servicio_aduanal = 0
                    current_inventario.Precio = 0
                    current_inventario.save()
                #Salvando Tracking
                traking = Traking()
                traking.Inventario      = current_inventario
                traking.Estado          = 'Despachado por aduana'
                traking.Observaciones   = 'En desagrupe'
                traking.Fecha           = now()
                traking.save()
                # Registro de trazas
                save_addition(request.user, 'traking', traking.id, str(model_to_dict(traking)))
                print('----------- INVENTARIO SALVADO -------------------')
                # print('HBL: ' + str(current_inventario.HBL) + ' Importe_Derecho_aduanal: ' + str(current_inventario.Importe_Derecho_aduanal) + ' Importe_Servicio_aduanal: ' + str(current_inventario.Importe_Servicio_aduanal))
                
                # Registro de trazas
                save_edition(request.user, 'inventario', current_inventario.id, str(model_to_dict(current_inventario)))

            messages.success(request, 'Cargas nacionalizadas satisfactoriamente')
            return redirect(request.path)
            
        #Accion de entregar inventario------------------------------------------
        if request.POST.get('operacion_tabla') == 'entregar_cargas':
            #Capturando datos del formulario
            list_inventario = request.POST.getlist('inventario_id')

            #Recorriendo todos los inventarios seleccionados
            for id_current_inventario in list_inventario:
                current_inventario = Inventario.objects.get(id = id_current_inventario)
                #Completando informacion de entrega
                if current_inventario.Estado == 'Traslado':
                    current_inventario.Tipo_Entrega = 'Puerta a puerta'
                else:
                    current_inventario.Tipo_Entrega = 'Presencial'
                current_inventario.Estado = 'Entregado'
                current_inventario.Fecha_Entrega = now()
                current_inventario.Nombre_Entrega = current_inventario.Destinatario.Nombre
                current_inventario.CI_Entrega = current_inventario.Destinatario.CI
                current_inventario.Pasaporte_DNI_Entrega = current_inventario.Destinatario.Pasaporte_DNI
                current_inventario.Direccion_Entrega = current_inventario.Destinatario.Direccion
                current_inventario.Provincia_Entrega = current_inventario.Destinatario.Provincia
                current_inventario.Municipio_Entrega = current_inventario.Destinatario.Municipio
                current_inventario.Telefono_Entrega = current_inventario.Destinatario.Telefono
                
                if current_inventario.Nacionalizado == False:
                    current_inventario.Nacionalizado = True
                    current_inventario.Fecha_Nacionalizacion = now()

                #Eliminacion de transportaciones de la carga entregada
                lista_entrega = Entrega.objects.all().filter(Q(Inventario = current_inventario), Q(Estado = 'Programado'))
                for current_entrega in lista_entrega:
                    current_entrega.Inventario.remove(current_inventario.id)
                    current_entrega.save()
                
                current_inventario.save()

                #Salvando Tracking
                traking = Traking()
                traking.Inventario      = current_inventario
                traking.Estado          = 'Entregado'
                traking.Observaciones   = 'Inventario entregado al destinatario'
                traking.Fecha           = now()
                traking.save()
                # Registro de trazas
                save_addition(request.user, 'traking', traking.id, str(model_to_dict(traking)))

                # Registro de trazas
                save_edition(request.user, 'inventario', current_inventario.id, str(model_to_dict(current_inventario)))

            messages.success(request, 'Cargas entregadas satisfactoriamente')
            return redirect(request.path)

        #Accion de confirmar existencia y dar entrada al almacén----------------
        if request.POST.get('operacion_tabla') == 'dar_entrada_almacen':
            #Capturando datos del formulario
            list_inventario = request.POST.getlist('inventario_id')
            #Validando que se haya seleccionado una carga
            if not list_inventario:
                messages.error(request, 'Debe seleccionar al menos una carga')
                return redirect(request.path)  
            
            #Recorriendo todos los inventarios seleccionados
            for id_current_inventario in list_inventario:
                current_inventario = Inventario.objects.get(id = id_current_inventario)
                current_inventario.exist = True
                current_inventario.Estado = 'Inventario'
                current_inventario.save()

                # Registro de trazas
                save_edition(request.user, 'inventario', current_inventario.id, str(model_to_dict(current_inventario)))
                #Salvando Tracking
                traking = Traking()
                traking.Inventario      = current_inventario
                traking.Estado          = 'En almacén'
                traking.Observaciones   = 'Pendiente de distribución'
                traking.Fecha           = now()
                traking.save()
            messages.success(request, 'Manifiesto confirmado satisfactoriamente')
            return redirect(request.path)
        
        #Accion de Trasbordar cargas----------------
        if request.POST.get('operacion_tabla') == 'trasbordar_cargas':
            #Capturando datos del formulario
            list_inventario = request.POST.getlist('inventario_id')
            id_almacen = request.POST.get('id_almacen_tabla')
            # print('almacen',id_almacen)
            #Validando que se haya seleccionado un almacen
            if not list_inventario:
                messages.error(request, 'Debe seleccionar al menos una carga')
                return redirect(request.path)  
            if not id_almacen:
                messages.error(request, 'Debe seleccionar un destino para trasbordar las cargas')
                return redirect(request.path)
            #Obteniendo almacen de destino
            current_almacen = Almacen.objects.get(id = id_almacen)
            
            #Recorriendo todos los inventarios seleccionados
            for id_current_inventario in list_inventario:
                current_inventario = Inventario.objects.get(id = id_current_inventario)
                current_inventario.trasbordo = True
                current_inventario.Almacen = current_almacen
                current_inventario.Estado = 'Inventario'
                current_inventario.save()
                # Registro de trazas
                save_edition(request.user, 'inventario', current_inventario.id, str(model_to_dict(current_inventario)))

            messages.success(request, 'Cargas trasbordadas satisfactoriamente')
            return redirect(request.path)

        #Accion de declarar canal rojo-------------------
        if request.POST.get('operacion_tabla') == 'canal_rojo':
            #Capturando datos del formulario
            list_inventario = request.POST.getlist('inventario_id')

            #Recorriendo todos los inventarios seleccionados
            for id_current_inventario in list_inventario:
                current_inventario = Inventario.objects.get(id = id_current_inventario)
                current_inventario.canal_rojo = True
                current_inventario.save()

                # Registro de trazas
                save_edition(request.user, 'inventario', current_inventario.id, str(model_to_dict(current_inventario)))
                #Salvando Tracking
                traking = Traking()
                traking.Inventario      = current_inventario
                traking.Estado          = 'En almacén'
                traking.Observaciones   = 'Pendiente de distribución'
                traking.Fecha           = now()
                traking.save()
            messages.success(request, 'Cargas declaradas en canal rojo satisfactoriamente.')
            return redirect(request.path)


#----Generacion de PDF-------------------------------------------------------
def lista_entregas_pdf(request, id_entrega):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Capturando solicitud
    current_entrega = get_object_or_404(Entrega, pk = id_entrega)
    #Calculando cantidad de bultos
    cantidad_bultos = 0
    for comprobante_destinatario in current_entrega.Factura_Operador.Facturas_Destinatarios.all():             
        for current_inventario in comprobante_destinatario.Inventario.all():             
            cantidad_bultos = cantidad_bultos + current_inventario.Cantidad_Bultos

    #Generando reporte PDF
    template_src = 'pdf/lista_entregas_pdf.html'
    template = get_template(template_src)
    context = {'current_entrega': current_entrega, 'cantidad_bultos': cantidad_bultos, 'request': request}
    html  = template.render(context)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
    if not pdf.err:
        return HttpResponse(result.getvalue(), content_type='application/pdf')
    return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))

def lista_facturas_por_entrega_pdf(request, id_entrega):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Capturando solicitud
    current_entrega = get_object_or_404(Entrega, pk = id_entrega)
    
    #Lista de inventarios a facturar
    inventarios = current_entrega.Inventario.all()

    #Lista de facturas a pasar a la vista
    lista_facturas = []
    
    #Obteniendo lista de destinatarios de la solicitud
    lista_de_destinatarios = [] #Lista de destinatarios
    for current_inventario in inventarios:
        lista_de_destinatarios.append(current_inventario.Destinatario.CI)
    lista_de_destinatarios = list(dict.fromkeys(lista_de_destinatarios))

    for current_destinatario in lista_de_destinatarios:
        current_factura = {}
        current_lista_de_inventarios = []

        #Valores totales
        current_factura['Precio_Aduana_Total'] = 0
        current_factura['Precio_Seguro_Carga_Total'] = 0
        current_factura['Precio_Transcargo_Total'] = 0
        current_factura['Precio_Sobredimension_Total'] = 0
        current_factura['Precio_Transporte_Total'] = 0
        #Importes de aduana
        current_factura['importe_derecho_aduanal'] = round(float(request.GET.get('importe_derecho_aduanal')), 2)
        current_factura['importe_servicio_aduanal'] = round(float(request.GET.get('importe_servicio_aduanal')), 2)
        current_factura['otros_importes'] = round(float(request.GET.get('otros_importes')), 2)

        lista_inventarios_por_persona = inventarios.filter(Destinatario__CI = current_destinatario)
        for current_inventario in lista_inventarios_por_persona:
            current_inventario_dict = {}
            current_inventario_dict['Inventario'] = current_inventario

            #Calculando el precio de la aduana
            """
            if current_inventario.Precio:
                current_factura['Precio_Aduana_Total'] = current_factura['Precio_Aduana_Total'] + current_inventario.Precio
            """

            #Calculando precio por seguro de carga
            if current_inventario.Peso:
                if current_inventario.Peso > 1.5:
                    current_inventario_dict['Precio_Seguro_Carga'] = round(current_inventario.Peso * 12, 2)
                else:
                    current_inventario_dict['Precio_Seguro_Carga'] = 0
                current_factura['Precio_Seguro_Carga_Total'] = current_factura['Precio_Seguro_Carga_Total'] + current_inventario_dict['Precio_Seguro_Carga']

            #Calculando precio de transcargo
            if current_inventario.Peso:
                if current_inventario.Peso <= 1.5:
                    current_inventario_dict['Precio_Transcargo'] = 80
                if current_inventario.Peso > 1.5 and current_inventario.Peso <= 49.9:
                    current_inventario_dict['Precio_Transcargo'] = 199
                if current_inventario.Peso >= 50:
                    current_inventario_dict['Precio_Transcargo'] = 800
                current_factura['Precio_Transcargo_Total'] = current_factura['Precio_Transcargo_Total'] + current_inventario_dict['Precio_Transcargo']

            #Calculando sobredimension
            if current_inventario.Peso:
                if current_inventario.Peso > 30:
                    current_inventario_dict['Precio_Sobredimension'] = 70
                else:
                    current_inventario_dict['Precio_Sobredimension'] = 0
                current_factura['Precio_Sobredimension_Total'] = current_factura['Precio_Sobredimension_Total'] + current_inventario_dict['Precio_Sobredimension']

            #Precio de transporte
            current_inventario_dict['Precio_Transporte'] = current_inventario.Destinatario.Municipio.Importe_por_entrega
            current_factura['Precio_Transporte_Total'] = current_factura['Precio_Transporte_Total'] + current_inventario_dict['Precio_Transporte']

            #Agregando informacion a la lista
            current_lista_de_inventarios.append(current_inventario_dict)

        current_factura['Destinatario'] = Destinatario.objects.filter(CI = current_destinatario).first()
        current_factura['Inventarios'] = current_lista_de_inventarios
        #Valor total de la factura
        #current_factura['Precio_Total_Factura'] = current_factura['Precio_Aduana_Total'] + current_factura['Precio_Seguro_Carga_Total'] + current_factura['Precio_Transcargo_Total'] + current_factura['Precio_Sobredimension_Total'] + current_factura['Precio_Transporte_Total']
        current_factura['Precio_Total_Factura'] = current_factura['otros_importes'] + current_factura['importe_derecho_aduanal'] + current_factura['importe_servicio_aduanal'] + current_factura['Precio_Seguro_Carga_Total'] + current_factura['Precio_Transcargo_Total'] + current_factura['Precio_Sobredimension_Total'] + current_factura['Precio_Transporte_Total']

        #Agregando factura a lista general de facturas
        lista_facturas.append(current_factura)

    #Generando reporte PDF
    template_src = 'pdf/lista_facturas_entregas.html'
    template = get_template(template_src)
    context = {'lista_facturas': lista_facturas, 'request': request}
    html  = template.render(context)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
    if not pdf.err:
        return HttpResponse(result.getvalue(), content_type='application/pdf')
    return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))

def facturacion_multiple_envios_pdf(request, id_entrega):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Capturando solicitud
    current_entrega = get_object_or_404(Entrega, pk = id_entrega)
    
    #Lista de inventarios a facturar
    inventarios = current_entrega.Inventario.all().filter(Q(Categoria_Operacion__icontains = 'envio') | Q(Categoria_Operacion__icontains = 'envío'))

    #Lista de facturas a pasar a la vista
    lista_facturas = []

    #Variable que guardará el valor del QR
    qr_generado = ''

    #Obteniendo lista de destinatarios de la solicitud
    lista_de_destinatarios = [] #Lista de destinatarios
    for current_inventario in inventarios:
        lista_de_destinatarios.append(current_inventario.Destinatario.CI)
    lista_de_destinatarios = list(dict.fromkeys(lista_de_destinatarios))

    for current_destinatario in lista_de_destinatarios:
        current_factura = {}
        current_lista_de_inventarios = []

        #Cantidad de veces que se mostrara la factura 
        current_factura['Copias_Facturas'] = range(1)

        #Valores totales
        current_factura['Importe_Transcargo_Total'] = 0.00 
        current_factura['Importe_Seguro_Carga_Total'] = 0.00 
        current_factura['Importe_Sobredimension_Total'] = 0.00 
        current_factura['Importe_Recargo_Total'] = float(request.GET.get('cargos_extra'))
        current_factura['Importe_Transportacion_Total'] = 0.00 
        current_factura['Importe_Derecho_Aduanal_Total'] = 0.00 
        current_factura['Importe_Servicio_Aduanal_Total'] = 0.00 

        lista_inventarios_por_persona = inventarios.filter(Destinatario__CI = current_destinatario)
        for current_inventario in lista_inventarios_por_persona:
            current_inventario_dict = {}
            current_inventario_dict['Inventario'] = current_inventario

            #Calculando el importe por derechos aduanales
            if current_inventario.Importe_Derecho_aduanal:
                current_factura['Importe_Derecho_Aduanal_Total'] += current_inventario.Importe_Derecho_aduanal

            #Calculando el importe por servicios aduanales
            if current_inventario.Importe_Servicio_aduanal:
                current_factura['Importe_Servicio_Aduanal_Total'] += current_inventario.Importe_Servicio_aduanal

            #Calculando precio por seguro de carga
            if current_inventario.Peso:
                if current_inventario.Peso <= 1.50:
                    current_inventario_dict['Importe_Seguro_Carga'] = 0.00
                if current_inventario.Peso > 1.50:
                    current_inventario_dict['Importe_Seguro_Carga'] = 12.00
                
                current_factura['Importe_Seguro_Carga_Total'] += current_inventario_dict['Importe_Seguro_Carga']

            #Calculando precio por sobredimension
            if current_inventario.Peso:
                if current_inventario.Peso < 30.00:
                    current_inventario_dict['Importe_Sobredimension'] = 0.00
                if current_inventario.Peso >= 30.00:
                    current_inventario_dict['Importe_Sobredimension'] = 70.00

                current_factura['Importe_Sobredimension_Total'] += current_inventario_dict['Importe_Sobredimension']

            #Calculando precio por transportacion
            if current_inventario.Destinatario.Municipio.Importe_por_entrega:
                current_inventario_dict['Importe_Transportacion'] = current_inventario.Destinatario.Municipio.Importe_por_entrega
            else:
                current_inventario_dict['Importe_Transportacion'] = 0
            current_factura['Importe_Transportacion_Total'] += current_inventario_dict['Importe_Transportacion']

            #Calculando el importe de transcargo
            if current_inventario.Peso:
                if current_inventario.Peso <= 1.50:
                    if current_inventario.Importe_Derecho_aduanal > 0:
                        current_inventario_dict['Importe_Transcargo'] = 80.00 + round(float((current_inventario.Importe_Derecho_aduanal * 1.10)/100), 2) + round(float((current_inventario.Importe_Servicio_aduanal * 1.10)/100), 2)
                    else:
                        current_inventario_dict['Importe_Transcargo'] = 80.00

                if current_inventario.Peso > 1.50 and current_inventario.Peso <= 50.00:
                    current_inventario_dict['Importe_Transcargo'] = 199.00 + round(float(current_inventario.Peso * 12.00), 2) + round(float((current_inventario.Importe_Derecho_aduanal * 1.10)/100), 2) + round(float((current_inventario.Importe_Servicio_aduanal * 1.10)/100), 2)
                if current_inventario.Peso > 50.00:
                    current_inventario_dict['Importe_Transcargo'] = 800.00 + round(float((current_inventario.Importe_Derecho_aduanal * 1.10)/100), 2) + round(float((current_inventario.Importe_Servicio_aduanal * 1.10)/100), 2)
            
                current_factura['Importe_Transcargo_Total'] += current_inventario_dict['Importe_Transcargo']

            #Agregando informacion a la lista
            current_lista_de_inventarios.append(current_inventario_dict)

        current_factura['Destinatario'] = Destinatario.objects.filter(CI = current_destinatario).first()
        current_factura['Inventarios'] = current_lista_de_inventarios
        #Valor total de la factura
        current_factura['Precio_Total_Factura'] = current_factura['Importe_Transcargo_Total'] + current_factura['Importe_Seguro_Carga_Total'] + current_factura['Importe_Sobredimension_Total'] + current_factura['Importe_Recargo_Total'] + current_factura['Importe_Transportacion_Total'] + current_factura['Importe_Derecho_Aduanal_Total'] + current_factura['Importe_Servicio_Aduanal_Total']
        
        if current_entrega.Estado == 'Ejecucion':
            try:
                factura_instance = Factura.objects.all().filter(Q(Contenido = str(current_factura)), Q(Estado = 'Pendiente de cobro'))[0]
            except:
                try:
                    with transaction.atomic():
                        #Almacenando la factura en el sistema
                        factura_instance = Factura()
                        factura_instance.Contenido = str(current_factura)
                        factura_instance.isMultiple = True
                        factura_instance.isEnvio = True
                        factura_instance.Fecha = now()
                        factura_instance.Estado = 'Pendiente de cobro'
                        factura_instance.Destinatario = current_factura['Destinatario']
                        factura_instance.Importe_Total_Factura = current_factura['Precio_Total_Factura']
                        factura_instance.Importe_Transcargo_Total = current_factura['Importe_Transcargo_Total']
                        factura_instance.Importe_Seguro_Carga_Total = current_factura['Importe_Seguro_Carga_Total']
                        factura_instance.Importe_Recargo_Total = current_factura['Importe_Recargo_Total']
                        factura_instance.Importe_Transportacion_Total = current_factura['Importe_Transportacion_Total']
                        factura_instance.Importe_Derecho_Aduanal_Total = current_factura['Importe_Derecho_Aduanal_Total']
                        factura_instance.Importe_Servicio_Aduanal_Total = current_factura['Importe_Servicio_Aduanal_Total']
                        factura_instance.Importe_Sobredimension_Total = current_factura['Importe_Sobredimension_Total']
                        #factura_instance.url = str(request.path) + '?cargos_extra=' + str(current_factura['Importe_Recargo_Total'])
                        factura_instance.save()
                        
                        for current_inventario_object in current_factura['Inventarios']:
                            factura_inventario_instance = Factura_Inventario()
                            factura_inventario_instance.Factura = factura_instance
                            factura_inventario_instance.Inventario = current_inventario_object['Inventario']
                            factura_inventario_instance.Importe_Seguro_Carga = current_inventario_object['Importe_Seguro_Carga']
                            factura_inventario_instance.Importe_Sobredimension = current_inventario_object['Importe_Sobredimension']
                            factura_inventario_instance.Importe_Transportacion = current_inventario_object['Importe_Transportacion']
                            factura_inventario_instance.Importe_Transcargo = current_inventario_object['Importe_Transcargo']
                            factura_inventario_instance.save()

                        # Registro de trazas
                        save_addition(request.user, 'factura', factura_instance.id, str(model_to_dict(factura_instance)))
                
                except:
                    raise ValueError('Ha ocurrido un error generando la factura')

            #Generando codigo QR de la factura
            # qr = qrcode.QRCode()
            # qr.add_data('{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}')
            # qr.make()
            # img = qr.make_image()
            # img.save(MEDIA_ROOT +'/QR/factura_' + str(factura_instance.id) +'.png')
            qr_generado = '{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}' 
        #Identificador de la factura
        if current_entrega.Estado == 'Ejecucion':
            current_factura['id_factura'] = factura_instance.id
        else:
            current_factura['id_factura'] = None

        #Agregando factura a lista general de facturas
        lista_facturas.append(current_factura)

    #Generando reporte PDF
    template_src = 'pdf/facturacion_multiple_envios_pdf.html'
    template = get_template(template_src)
    context = {'lista_facturas': lista_facturas, 'fecha_factura': now(), 'request': request, 'qr':qr_generado}
    html  = template.render(context)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
    if not pdf.err:
        return HttpResponse(result.getvalue(), content_type='application/pdf')
    return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))

def facturacion_multiple_ena_menaje_pdf(request, id_entrega):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Capturando solicitud
    current_entrega = get_object_or_404(Entrega, pk = id_entrega)
    
    #Lista de inventarios a facturar
    inventarios = current_entrega.Inventario.all().filter(~Q(Categoria_Operacion__icontains = 'envio'), ~Q(Categoria_Operacion__icontains = 'envío'))

    #Lista de facturas a pasar a la vista
    lista_facturas = []
    
    #Variable donde se guardará información del QR
    qr_generado = ''
    #Obteniendo lista de destinatarios de la solicitud
    lista_de_destinatarios = [] #Lista de destinatarios
    for current_inventario in inventarios:
        lista_de_destinatarios.append(current_inventario.Destinatario.CI)
    lista_de_destinatarios = list(dict.fromkeys(lista_de_destinatarios))

    for current_destinatario in lista_de_destinatarios:
        current_factura = {}
        current_lista_de_inventarios = []

        #Cantidad de veces que se mostrara la factura 
        current_factura['Copias_Facturas'] = range(1)

        #Valores totales
        current_factura['Importe_Transcargo_Total'] = 0.00  #OK
        current_factura['Importe_Seguro_Carga_Total'] = 0.00 #OK
        current_factura['Importe_Servicio_Corresponsalia_Total'] = 0.00 #OK
        current_factura['Importe_Transportacion_Total'] = 0.00 #OK
        current_factura['Importe_Recargo_Total'] = float(request.GET.get('cargos_extra'))
        current_factura['Importe_Derecho_Aduanal_Total'] = float(request.GET.get('importe_derecho_aduanal'))
        current_factura['Importe_Servicio_Aduanal_Total'] = float(request.GET.get('importe_servicio_aduanal'))

        lista_inventarios_por_persona = inventarios.filter(Destinatario__CI = current_destinatario)
        for current_inventario in lista_inventarios_por_persona:
            current_inventario_dict = {}
            current_inventario_dict['Inventario'] = current_inventario

            #Facturacion de ENA
            if current_inventario.Categoria_Operacion == 'ENA' or current_inventario.Categoria_Operacion == 'ena' or current_inventario.Categoria_Operacion == 'Ena' or current_inventario.Categoria_Operacion == 'E.N.A' or current_inventario.Categoria_Operacion == 'e.n.a' or current_inventario.Categoria_Operacion == 'E.n.a': 
                #Calculando el importe de transcargo
                if current_inventario.Volumen:
                    if current_inventario.Volumen <= 1:
                        current_inventario_dict['Importe_Transcargo'] = 765.00
                    if current_inventario.Volumen > 1:
                        current_inventario_dict['Importe_Transcargo'] = round(float(765.00 * current_inventario.Volumen), 2)
                    
                    current_factura['Importe_Transcargo_Total'] += current_inventario_dict['Importe_Transcargo']

                #Calculando precio por seguro de carga
                current_inventario_dict['Importe_Seguro_Carga'] = 96.00
                current_factura['Importe_Seguro_Carga_Total'] += current_inventario_dict['Importe_Seguro_Carga']

                #Calculando precio por servicio de corresponsalia
                current_inventario_dict['Importe_Servicio_Corresponsalia'] = 57.00
                current_factura['Importe_Servicio_Corresponsalia_Total'] += current_inventario_dict['Importe_Servicio_Corresponsalia']

                #Calculando precio por transportacion
                if current_inventario.Destinatario.Municipio.Importe_por_entrega:
                    current_inventario_dict['Importe_Transportacion'] = current_inventario.Destinatario.Municipio.Importe_por_entrega
                else:
                    current_inventario_dict['Importe_Transportacion'] = 0
                current_factura['Importe_Transportacion_Total'] += current_inventario_dict['Importe_Transportacion']

                #Agregando informacion a la lista
                current_lista_de_inventarios.append(current_inventario_dict)

            #Facturacion de Menaje
            if current_inventario.Categoria_Operacion == 'MENAJE' or current_inventario.Categoria_Operacion == 'Menaje' or current_inventario.Categoria_Operacion == 'menaje': 
                #Calculando el importe de transcargo
                if current_inventario.Volumen:
                    if current_inventario.Volumen <= 1:
                        current_inventario_dict['Importe_Transcargo'] = 765.00
                    if current_inventario.Volumen > 1:
                        current_inventario_dict['Importe_Transcargo'] = round(float(765.00 * current_inventario.Volumen), 2)
                    
                    current_factura['Importe_Transcargo_Total'] += current_inventario_dict['Importe_Transcargo']

                #Calculando precio por seguro de carga
                current_inventario_dict['Importe_Seguro_Carga'] = 240.00
                current_factura['Importe_Seguro_Carga_Total'] += current_inventario_dict['Importe_Seguro_Carga']

                #Calculando precio por servicio de corresponsalia
                current_inventario_dict['Importe_Servicio_Corresponsalia'] = 57.00
                current_factura['Importe_Servicio_Corresponsalia_Total'] += current_inventario_dict['Importe_Servicio_Corresponsalia']

                #Calculando precio por transportacion
                if current_inventario.Destinatario.Municipio.Importe_por_entrega:
                    current_inventario_dict['Importe_Transportacion'] = current_inventario.Destinatario.Municipio.Importe_por_entrega
                else:
                    current_inventario_dict['Importe_Transportacion'] = 0
                current_factura['Importe_Transportacion_Total'] += current_inventario_dict['Importe_Transportacion']

                #Agregando informacion a la lista
                current_lista_de_inventarios.append(current_inventario_dict)

        current_factura['Destinatario'] = Destinatario.objects.filter(CI = current_destinatario).first()
        current_factura['Inventarios'] = current_lista_de_inventarios
        #Valor total de la factura
        current_factura['Precio_Total_Factura'] = current_factura['Importe_Transcargo_Total'] + current_factura['Importe_Seguro_Carga_Total'] + current_factura['Importe_Servicio_Corresponsalia_Total'] + current_factura['Importe_Transportacion_Total'] + current_factura['Importe_Recargo_Total'] + current_factura['Importe_Derecho_Aduanal_Total'] + current_factura['Importe_Servicio_Aduanal_Total'] + round(float((current_factura['Importe_Derecho_Aduanal_Total'] * 1.10)/100), 2) + round(float((current_factura['Importe_Servicio_Aduanal_Total'] * 1.10)/100), 2)

        if current_entrega.Estado == 'Ejecucion':
            try:
                factura_instance = Factura.objects.all().filter(Q(Contenido = str(current_factura)), Q(Estado = 'Pendiente de cobro'))[0]
            except:
                try:
                    with transaction.atomic():
                        #Almacenando la factura en el sistema
                        factura_instance = Factura()
                        factura_instance.Contenido = str(current_factura)
                        factura_instance.isMultiple = True
                        factura_instance.isEnvio = False
                        factura_instance.Estado = 'Pendiente de cobro'
                        factura_instance.Fecha = now()
                        factura_instance.Destinatario = current_factura['Destinatario']
                        factura_instance.Importe_Total_Factura = current_factura['Precio_Total_Factura']
                        factura_instance.Importe_Transcargo_Total = current_factura['Importe_Transcargo_Total']
                        factura_instance.Importe_Seguro_Carga_Total = current_factura['Importe_Seguro_Carga_Total']
                        factura_instance.Importe_Recargo_Total = current_factura['Importe_Recargo_Total']
                        factura_instance.Importe_Transportacion_Total = current_factura['Importe_Transportacion_Total']
                        factura_instance.Importe_Derecho_Aduanal_Total = current_factura['Importe_Derecho_Aduanal_Total']
                        factura_instance.Importe_Servicio_Aduanal_Total = current_factura['Importe_Servicio_Aduanal_Total']
                        factura_instance.Importe_Servicio_Corresponsalia_Total = current_factura['Importe_Servicio_Corresponsalia_Total']
                        #factura_instance.url = str(request.path) + '?importe_derecho_aduanal=' + str(current_factura['Importe_Derecho_Aduanal_Total']) + '&importe_servicio_aduanal=' + str(current_factura['Importe_Servicio_Aduanal_Total']) + '&cargos_extra=' + str(current_factura['Importe_Recargo_Total'])
                        factura_instance.save()
                        
                        for current_inventario_object in current_factura['Inventarios']:
                            factura_inventario_instance = Factura_Inventario()
                            factura_inventario_instance.Factura = factura_instance
                            factura_inventario_instance.Inventario = current_inventario_object['Inventario']
                            factura_inventario_instance.Importe_Seguro_Carga = current_inventario_object['Importe_Seguro_Carga']
                            factura_inventario_instance.Importe_Servicio_Corresponsalia = current_inventario_object['Importe_Servicio_Corresponsalia']
                            factura_inventario_instance.Importe_Transportacion = current_inventario_object['Importe_Transportacion']
                            factura_inventario_instance.Importe_Transcargo = current_inventario_object['Importe_Transcargo']
                            factura_inventario_instance.save()
                        
                        # Registro de trazas
                        save_addition(request.user, 'factura', factura_instance.id, str(model_to_dict(factura_instance)))
                except:
                    raise ValueError('Ha ocurrido un error generando la factura') 

            #Generando codigo QR de la factura
            # qr = qrcode.QRCode()
            # qr.add_data('{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}')
            # qr.make()
            # img = qr.make_image()
            # img.save(MEDIA_ROOT +'/QR/factura_' + str(factura_instance.id) +'.png')
            qr_generado = '{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}' 
        #Identificador de la factura
        if current_entrega.Estado == 'Ejecucion':
            current_factura['id_factura'] = factura_instance.id
        else:
            current_factura['id_factura'] = None

        #Agregando factura a lista general de facturas
        lista_facturas.append(current_factura)

    #Generando reporte PDF
    template_src = 'pdf/facturacion_multiple_ena_menaje_pdf.html'
    template = get_template(template_src)
    context = {'lista_facturas': lista_facturas, 'fecha_factura': now(), 'request': request,'qr':qr_generado}
    html  = template.render(context)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
    if not pdf.err:
        return HttpResponse(result.getvalue(), content_type='application/pdf')
    return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))


def generar_factura_de_inventario_pdf(request, id_inventario):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Capturando inventario
    current_inventario = get_object_or_404(Inventario, pk = id_inventario)
    if current_inventario.Precio == None:
        current_inventario.Precio = 0
    
    if current_inventario.Importe_Derecho_aduanal == None:
        current_inventario.Importe_Derecho_aduanal = 0
        
    if current_inventario.Importe_Servicio_aduanal == None:
        current_inventario.Importe_Servicio_aduanal = 0

    isEnvioCheck = False

    current_inventario_dict = {}
    current_inventario_dict['Inventario'] = current_inventario

    #Cantidad de veces que se mostrara la factura 
    current_inventario_dict['Copias_Facturas'] = range(1)

    if current_inventario.Categoria_Operacion == 'ENVIO' or current_inventario.Categoria_Operacion == 'envio' or current_inventario.Categoria_Operacion == 'Envio' or current_inventario.Categoria_Operacion == 'ENVÍO' or current_inventario.Categoria_Operacion == 'envío' or current_inventario.Categoria_Operacion == 'Envío':
        isEnvioCheck = True
        #Calculando precio por seguro de carga
        if current_inventario.Peso:
            if current_inventario.Peso <= 1.50:
                current_inventario_dict['Importe_Seguro_Carga'] = 0.00
            if current_inventario.Peso > 1.50:
                current_inventario_dict['Importe_Seguro_Carga'] = 12.00
                
        #Calculando precio por sobredimension
        if current_inventario.Peso:
            if current_inventario.Peso < 30.00:
                current_inventario_dict['Importe_Sobredimension'] = 0.00
            if current_inventario.Peso >= 30.00:
                current_inventario_dict['Importe_Sobredimension'] = 70.00

        #Calculando precio por transportacion
        if current_inventario.Destinatario.Municipio.Importe_por_entrega:
            current_inventario_dict['Importe_Transportacion'] = current_inventario.Destinatario.Municipio.Importe_por_entrega
        else:
            current_inventario_dict['Importe_Transportacion'] = 0

        #Calculando el importe de transcargo
        if current_inventario.Peso:
            if current_inventario.Peso <= 1.50:
                if current_inventario.Importe_Derecho_aduanal > 0:
                    current_inventario_dict['Importe_Transcargo'] = 80.00 + round(float((current_inventario.Importe_Derecho_aduanal * 1.10)/100), 2) + round(float((current_inventario.Importe_Servicio_aduanal * 1.10)/100), 2)
                else:
                    current_inventario_dict['Importe_Transcargo'] = 80.00
            if current_inventario.Peso > 1.50 and current_inventario.Peso <= 50.00:
                current_inventario_dict['Importe_Transcargo'] = 199.00 + round(float(current_inventario.Peso * 12.00), 2) + round(float((current_inventario.Importe_Derecho_aduanal * 1.10)/100), 2) + round(float((current_inventario.Importe_Servicio_aduanal * 1.10)/100), 2)
            if current_inventario.Peso > 50.00:
                current_inventario_dict['Importe_Transcargo'] = 800.00 + round(float((current_inventario.Importe_Derecho_aduanal * 1.10)/100), 2) + round(float((current_inventario.Importe_Servicio_aduanal * 1.10)/100), 2)
            
        current_inventario_dict['Precio_Total_Factura'] = current_inventario.Importe_Derecho_aduanal + current_inventario.Importe_Servicio_aduanal + current_inventario.Precio + current_inventario_dict['Importe_Seguro_Carga'] + current_inventario_dict['Importe_Sobredimension'] + current_inventario_dict['Importe_Transportacion'] + current_inventario_dict['Importe_Transcargo']

    #Facturacion de ENA
    if current_inventario.Categoria_Operacion == 'ENA' or current_inventario.Categoria_Operacion == 'ena' or current_inventario.Categoria_Operacion == 'Ena' or current_inventario.Categoria_Operacion == 'E.N.A' or current_inventario.Categoria_Operacion == 'e.n.a' or current_inventario.Categoria_Operacion == 'E.n.a': 
        #Calculando el importe de transcargo
        if current_inventario.Volumen:
            if current_inventario.Volumen <= 1:
                current_inventario_dict['Importe_Transcargo'] = 765.00
            if current_inventario.Volumen > 1:
                current_inventario_dict['Importe_Transcargo'] = round(float(765.00 * current_inventario.Volumen), 2)
                    
        #Calculando precio por seguro de carga
        current_inventario_dict['Importe_Seguro_Carga'] = 96.00

        #Calculando precio por servicio de corresponsalia
        current_inventario_dict['Importe_Servicio_Corresponsalia'] = 57.00

        #Calculando precio por transportacion
        if current_inventario.Destinatario.Municipio.Importe_por_entrega:
            current_inventario_dict['Importe_Transportacion'] = current_inventario.Destinatario.Municipio.Importe_por_entrega
        else:
            current_inventario_dict['Importe_Transportacion'] = 0

        current_inventario_dict['Precio_Total_Factura'] = current_inventario.Importe_Derecho_aduanal + current_inventario.Importe_Servicio_aduanal + current_inventario.Precio + current_inventario_dict['Importe_Transcargo'] + current_inventario_dict['Importe_Seguro_Carga'] + current_inventario_dict['Importe_Servicio_Corresponsalia'] + current_inventario_dict['Importe_Transportacion']

    #Facturacion de Menaje
    if current_inventario.Categoria_Operacion == 'MENAJE' or current_inventario.Categoria_Operacion == 'Menaje' or current_inventario.Categoria_Operacion == 'menaje': 
        #Calculando el importe de transcargo
        if current_inventario.Volumen:
            if current_inventario.Volumen <= 1:
                current_inventario_dict['Importe_Transcargo'] = 765.00
            if current_inventario.Volumen > 1:
                current_inventario_dict['Importe_Transcargo'] = round(float(765.00 * current_inventario.Volumen), 2)
                    
        #Calculando precio por seguro de carga
        current_inventario_dict['Importe_Seguro_Carga'] = 240.00

        #Calculando precio por servicio de corresponsalia
        current_inventario_dict['Importe_Servicio_Corresponsalia'] = 57.00

        #Calculando precio por transportacion
        if current_inventario.Destinatario.Municipio.Importe_por_entrega:
            current_inventario_dict['Importe_Transportacion'] = current_inventario.Destinatario.Municipio.Importe_por_entrega
        else:
            current_inventario_dict['Importe_Transportacion'] = 0

        current_inventario_dict['Precio_Total_Factura'] = current_inventario.Importe_Derecho_aduanal + current_inventario.Importe_Servicio_aduanal + current_inventario.Precio + current_inventario_dict['Importe_Transcargo'] + current_inventario_dict['Importe_Seguro_Carga'] + current_inventario_dict['Importe_Servicio_Corresponsalia'] + current_inventario_dict['Importe_Transportacion']

    try:
        factura_instance = Factura.objects.all().filter(Q(Contenido = current_inventario_dict), Q(Estado = 'Pendiente de cobro'))[0]
    except:
        try:
            with transaction.atomic():
                #Almacenando la factura en el sistema
                factura_instance = Factura()
                factura_instance.Contenido = str(current_inventario_dict)
                factura_instance.isMultiple = False
                factura_instance.isEnvio = isEnvioCheck
                factura_instance.Estado = 'Pendiente de cobro'
                factura_instance.Fecha = now()
                factura_instance.Destinatario = current_inventario.Destinatario
                factura_instance.Importe_Total_Factura = current_inventario_dict['Precio_Total_Factura']
                factura_instance.Importe_Transcargo_Total = current_inventario_dict['Importe_Transcargo']
                factura_instance.Importe_Seguro_Carga_Total = current_inventario_dict['Importe_Seguro_Carga']
                factura_instance.Importe_Recargo_Total = current_inventario.Precio
                factura_instance.Importe_Transportacion_Total = current_inventario_dict['Importe_Transportacion']
                factura_instance.Importe_Derecho_Aduanal_Total = current_inventario.Importe_Derecho_aduanal
                factura_instance.Importe_Servicio_Aduanal_Total = current_inventario.Importe_Servicio_aduanal
                if isEnvioCheck:
                    factura_instance.Importe_Sobredimension_Total = current_inventario_dict['Importe_Sobredimension']
                else:
                    factura_instance.Importe_Servicio_Corresponsalia_Total = current_inventario_dict['Importe_Servicio_Corresponsalia']
                #factura_instance.url = str(request.path)
                factura_instance.save()
                
                factura_inventario_instance = Factura_Inventario()
                factura_inventario_instance.Factura = factura_instance
                factura_inventario_instance.Inventario = current_inventario
                factura_inventario_instance.Importe_Seguro_Carga = current_inventario_dict['Importe_Seguro_Carga']
                factura_inventario_instance.Importe_Transportacion = current_inventario_dict['Importe_Transportacion']
                factura_inventario_instance.Importe_Transcargo = current_inventario_dict['Importe_Transcargo']
                if isEnvioCheck:
                    factura_inventario_instance.Importe_Sobredimension = current_inventario_dict['Importe_Sobredimension']   
                else:
                    factura_inventario_instance.Importe_Servicio_Corresponsalia = current_inventario_dict['Importe_Servicio_Corresponsalia']
                factura_inventario_instance.save()
                
                # Registro de trazas
                save_addition(request.user, 'factura', factura_instance.id, str(model_to_dict(factura_instance)))
        except:
                raise ValueError('Ha ocurrido un error generando la factura')
        
    #Identificador de la factura
    current_inventario_dict['id_factura'] = factura_instance.id   

    #Generando codigo QR de la factura
    # qr = qrcode.QRCode()
    # qr.add_data('{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_inventario_dict['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}')
    # qr.make()
    # img = qr.make_image()
    # img.save(MEDIA_ROOT +'/QR/factura_' + str(factura_instance.id) +'.png')
    qr_generado = '{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}' 
    #Generando reporte PDF
    template_src = 'pdf/factura_de_inventario.html'
    template = get_template(template_src)
    context = {'current_inventario_dict': current_inventario_dict, 'fecha_factura': factura_instance.Fecha, 'request': request, 'isEnvio': isEnvioCheck,'qr':qr_generado}
    html  = template.render(context)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
    if not pdf.err:
        return HttpResponse(result.getvalue(), content_type='application/pdf')
    return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))


@login_required(login_url='login')
def nacionalizar_desde_aduana(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Formulario de tabla
    nacionalizad_aduana_form = Nacionalizar_Desde_Aduana_Form()
    #Definiendo menu activo
    active_menu = 'mercancia_inventario'
    #Lista de inventarios nacionalizados
    inventarios_nacionalizados = []

    if request.method == 'POST':
        inventarios_nacionalizados = []
        nacionalizad_aduana_form = Nacionalizar_Desde_Aduana_Form(request.POST)
        if nacionalizad_aduana_form.is_valid():
            try:
                inventarios = Inventario.objects.all().filter(Q(Manifiesto = nacionalizad_aduana_form.cleaned_data['Manifiesto']), Q(No_Contenedor = nacionalizad_aduana_form.cleaned_data['No_Contenedor']), Q(Nacionalizado = False))

                if nacionalizad_aduana_form.cleaned_data['Municipio']:
                    inventarios = inventarios.filter(Q(Destinatario__Municipio = nacionalizad_aduana_form.cleaned_data['Municipio']))
                
                #Trabajo con manifiesto para el servicio de la aduana
                #ESTO SE AGREGARA A LA SALVA DEL MANIFIESTO EN LA DB
                man = str(nacionalizad_aduana_form.cleaned_data['Manifiesto'])
                if len(man.split('/')[0]) < 4:
                    man = str(nacionalizad_aduana_form.cleaned_data['Manifiesto']).zfill(4)
                
                if len(man.split('/')) == 1:
                    man = man + '/' + str(inventarios[0].Fecha_Entrada_Puerto.year)
                #Fin

                for current_inventario in inventarios:
                    #dicto = {'success': True, 'despachos': [{'BOLETIN_DERECHO': '171021047035915000007', 'NO_BLGA': 'MAY21110540', 'MANIFIESTOS': '0358/2021', 'VALOR_DERECHOS': '0', 'VALOR_SERVICIO': '50'}]}
                    try:
                        with transaction.atomic():
                            #Consultar informacion de la aduana
                            USUARIO = 'aerov'
                            PASS = 'eh7443fx'
                            MANIFIESTO = man
                            HBL = current_inventario.HBL
                            CODIGO_ADUANA = '0200'

                            URL= 'https://sua.aduana.cu/GINASUA/serviciosExternos.php'
                            headers = {
                                'Content-Type': 'application/xml',
                                'Accept': 'application/xml',
                            }
                            data = '<?xml version=\"1.0\" encoding=\"utf-8\"?><soap:Envelope xmlns:soap=\"http://schemas.xmlsoap.org/soap/envelope/\"><soap:Body><GABLDespachado><usuario>'+ USUARIO +'</usuario><clave>'+ PASS +'</clave><manifiesto>'+ MANIFIESTO +'</manifiesto><blga>'+ HBL +'</blga><codigoaduana>'+ CODIGO_ADUANA +'</codigoaduana></GABLDespachado></soap:Body></soap:Envelope>'
                            
                            resp = requests.get( URL, headers = headers, data = data, verify=False )
                            resp_strip = strip_tags(resp.content)
                            dict = resp_strip.replace('\\', '').replace("b'n", ""). replace("n'", "")
                            dicto = json.loads(dict)

                            if dicto['success'] == True:
                                current_inventario.Importe_Derecho_aduanal = float(dicto['despachos'][0]['VALOR_DERECHOS'])
                                current_inventario.Importe_Servicio_aduanal = float(dicto['despachos'][0]['VALOR_SERVICIO'])
                                current_inventario.Precio = 0
                                current_inventario.Nacionalizado = True
                                current_inventario.Fecha_Nacionalizacion = now()
                                current_inventario.save()

                                # Registro de trazas
                                save_edition(request.user, 'inventario', current_inventario.id, str(model_to_dict(current_inventario)))
                                
                                #Mostrando inventarios nacionalizados
                                inventarios_nacionalizados.append(current_inventario)                    
                        #Fin de la consulta
                    except:
                        pass
            except:
                pass

    ctx = {'active_menu': active_menu, 'nacionalizad_aduana_form': nacionalizad_aduana_form, 'inventarios_nacionalizados': inventarios_nacionalizados, 'cantidad_nacionalizados': len(inventarios_nacionalizados)}
    return render(request, 'operacion_mercancia/nacionalizar_desde_aduana.html', ctx)


def remove_accents(input_str):
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    only_ascii = nfkd_form.encode('ASCII', 'ignore')
    return only_ascii

#----Gestion de Manifiestos---------------------------------------------------
@login_required(login_url='login')
def manifiesto_list(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Lista de manifiestos
    Manifiestos = Manifiesto.objects.all().order_by('-id')

    #Aplicacion de filtros
    manifiesto_filter = Manifiesto_Filter(request.GET, queryset=Manifiestos)
    Manifiestos = manifiesto_filter.qs
    
    #Paginator
    paginator = Paginator(Manifiestos, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj, 'manifiesto_filter': manifiesto_filter}
    return render(request, 'manifiesto/manifiesto_list.html', ctx)


@login_required(login_url='login')
def manifiesto_eliminar(request):
    if request.method == 'POST':

        #Validando roles
        if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
            messages.error(request, 'Usted no tiene autorización para realizar esta operación')
            return redirect(reverse('manifiesto_list'))

        try:
            with transaction.atomic():
                #Manifiesto a eliminar
                current_manifiesto = get_object_or_404(Manifiesto, pk = request.POST.get('id_manifiesto'))

                #Inicializando cursor
                cursor = connection.cursor()    
                
                #Eliminando entregas
                #cursor.execute('DELETE FROM "inventario_entrega_Inventario" WHERE "inventario_id" in (SELECT id from "inventario_inventario" WHERE "No_Contenedor" = %s AND "Manifiesto" = %s)', [current_manifiesto.No_Contenedor, current_manifiesto.Manifiesto])

                #Eliminando las citas
                #cursor.execute('DELETE FROM "inventario_cita_Inventario" WHERE "inventario_id" in (SELECT id from "inventario_inventario" WHERE "No_Contenedor" = %s AND "Manifiesto" = %s)', [current_manifiesto.No_Contenedor, current_manifiesto.Manifiesto])

                #Eliminando tracking
                cursor.execute('DELETE FROM "inventario_traking" WHERE "Inventario_id" in (SELECT id from "inventario_inventario" WHERE "No_Contenedor" = %s AND "Manifiesto" = %s)', [current_manifiesto.No_Contenedor, current_manifiesto.Manifiesto])

                #Eliminando inventarios
                cursor.execute('DELETE from "inventario_inventario" WHERE "No_Contenedor" = %s AND "Manifiesto" = %s', [current_manifiesto.No_Contenedor, current_manifiesto.Manifiesto])

                #Eliminando manifiesto
                # Registro de trazas
                save_deletion(request.user, 'manifiesto', current_manifiesto.id, str(model_to_dict(current_manifiesto)))
                current_manifiesto.delete()
                
                messages.success(request, 'Manifiesto eliminado satisfactoriamente.')
                return redirect(reverse('manifiesto_list'))
        except Exception as inst:
            print(inst)
            messages.error(request, 'Este manifiesto no puede ser eliminado porque ya se han realizado operaciones con sus inventarios.')
            return redirect(reverse('manifiesto_list'))
    else:
        return redirect(reverse('manifiesto_list'))


#--------Comprobante de entrega de destinatario--------------------------------------
@login_required(login_url='login')
def comprobante_entrega_envios_pdf(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Flags sobre la informacion de inventarios
    isEnvio         = False
    isEna_menaje    = False

    #Informacion para el template
    header_text     = 'Generar comprobantes de pago de destinatarios'
    breadcrumb_text = 'Generar comprobantes de pago de destinatarios'
    #Definiendo menu activo
    active_menu = 'comprobante_pago_destinatario'
    trasbordo_form = Operacion_Trasladar_De_Almacen_Form()
    form_hbl_escaneados = HBL_Escaneados_Form()

    if request.method == 'POST':
        try:
            
            # list_inventario_selected = ''
            # if request.POST.get('HBL'):
            #     #Comprobante desde escaner
            #     hbl_regex = re.compile(r'([A-Z0-9*]*)')
            #     #Obtengo los HBL escaneados
            #     hbl_escaneados_list=request.POST.get('HBL')
            #     no_contenedor=request.POST.get('No_Contenedor')

            #     print('hbl_escaneados_list',hbl_escaneados_list)
            #     list_inventario_selected = re.findall(hbl_regex,hbl_escaneados_list)
                
            #     #Obtengo los inventarios que coinciden con los HBL escaneados
            #     inventarios = Inventario.objects.all().filter(HBL__in = list_inventario_selected,No_Contenedor=no_contenedor)

            #     #Lista de facturas a pasar a la vista
            #     lista_facturas = []
                
            #     #Obteniendo lista de destinatarios de la solicitud
            #     lista_de_destinatarios = [] #Lista de destinatarios
            #     for current_inventario in inventarios:
            #         lista_de_destinatarios.append(current_inventario.Destinatario.CI)
            #     # lista_de_destinatarios = list(dict.fromkeys(lista_de_destinatarios))

            #     hbl_destinatario_no_escaneados = []
            #     #Obtengo todos los HBL de cada destinatario
            #     for destinatario in lista_de_destinatarios:
            #         hbl_destinatario = Inventario.objects.filter(Destinatario=destinatario,No_Contenedor=no_contenedor).values('HBL')
            #         for hbl in hbl_destinatario:
            #             if hbl not in hbl_escaneados_list:
            #                 inventario = Inventario.objects.get_object_or_404(HBL=hbl)
            #                 hbl_destinatario_no_escaneados.append(inventario)
            #     # if hbl_destinatario_no_escaneados:
                           




            # if not request.POST.get('HBL'):
            #     list_inventario_selected = request.POST.getlist('inventario_id')
            list_inventario_selected = request.POST.getlist('inventario_id')        

            if request.POST.get('operacion_tabla') == 'facturar_envios':
                #Lista de inventarios a facturar
                inventarios = Inventario.objects.all().filter((Q(Categoria_Operacion__icontains = 'envio') | Q(Categoria_Operacion__icontains = 'envío')), Q(pk__in = list_inventario_selected))

                #Lista de facturas a pasar a la vista
                lista_facturas = []
                
                #Obteniendo lista de destinatarios de la solicitud
                lista_de_destinatarios = [] #Lista de destinatarios
                for current_inventario in inventarios:
                    lista_de_destinatarios.append(current_inventario.Destinatario.CI)
                lista_de_destinatarios = list(dict.fromkeys(lista_de_destinatarios))

                for current_destinatario in lista_de_destinatarios:
                    current_factura = {}
                    current_lista_de_inventarios = []

                    #Cantidad de veces que se mostrara la factura 
                    current_factura['Copias_Facturas'] = range(1)

                    #Valores totales
                    current_factura['Importe_Transcargo_Total'] = 0.00 
                    current_factura['Importe_Seguro_Carga_Total'] = 0.00 
                    current_factura['Importe_Sobredimension_Total'] = 0.00 
                    current_factura['Importe_Recargo_Total'] = float(request.POST.get('cargos_extra'))
                    current_factura['Importe_Transportacion_Total'] = 0.00 
                    current_factura['Importe_Derecho_Aduanal_Total'] = 0.00 
                    current_factura['Importe_Servicio_Aduanal_Total'] = 0.00 
                    current_factura['Cantidad_Bultos_Total'] = 0 

                    lista_inventarios_por_persona = inventarios.filter(Destinatario__CI = current_destinatario)
                    for current_inventario in lista_inventarios_por_persona:
                        current_inventario_dict = {}
                        current_inventario_dict['Inventario'] = current_inventario

                        #Calculando el importe por derechos aduanales
                        if current_inventario.Importe_Derecho_aduanal:
                            current_factura['Importe_Derecho_Aduanal_Total'] += current_inventario.Importe_Derecho_aduanal

                        #Calculando el importe por servicios aduanales
                        if current_inventario.Importe_Servicio_aduanal:
                            current_factura['Importe_Servicio_Aduanal_Total'] += current_inventario.Importe_Servicio_aduanal
                        if current_inventario.isPrepago:
                            current_factura['Importe_Seguro_Carga_Total'] = 0.00
                            current_factura['Importe_Sobredimension_Total'] = 0.00
                            current_factura['Importe_Transportacion_Total'] = 0.00
                            current_factura['Importe_Transcargo_Total'] = 0.00
                            current_factura['Cantidad_Bultos_Total'] += current_inventario.Cantidad_Bultos
                            
                            #Agregando informacion a la lista
                            current_inventario_dict['Importe_Seguro_Carga'] = 0.00
                            current_inventario_dict['Importe_Sobredimension'] = 0.00
                            current_inventario_dict['Importe_Transportacion'] = 0.00
                            current_inventario_dict['Importe_Transcargo'] = 0.00
                            current_lista_de_inventarios.append(current_inventario_dict)

                        else:    
                            #Calculando precio por seguro de carga
                            if current_inventario.Peso:
                                if current_inventario.Peso <= 1.50:
                                    current_inventario_dict['Importe_Seguro_Carga'] = 0.00
                                if current_inventario.Peso > 1.50:
                                    current_inventario_dict['Importe_Seguro_Carga'] = 12.00

                                current_factura['Importe_Seguro_Carga_Total'] += current_inventario_dict['Importe_Seguro_Carga']
                            else:
                                current_inventario_dict['Importe_Seguro_Carga'] = 0.00
                            
                            #Calculando precio por sobredimension
                            if current_inventario.Peso:
                                if current_inventario.Peso < 30.00:
                                    current_inventario_dict['Importe_Sobredimension'] = 0.00
                                if current_inventario.Peso >= 30.00:
                                    current_inventario_dict['Importe_Sobredimension'] = 70.00

                                current_factura['Importe_Sobredimension_Total'] += current_inventario_dict['Importe_Sobredimension']
                            else:
                                current_inventario_dict['Importe_Sobredimension'] = 0.00
                            #Calculando precio por transportacion
                            if current_inventario.Peso and request.POST.get('incluir_transportacion') == 'on':        
                                if current_inventario.Destinatario.Municipio.Importe_por_entrega:
                                    current_inventario_dict['Importe_Transportacion'] = float(current_inventario.Destinatario.Municipio.Importe_por_entrega)
                                    if request.POST.get('trasbordo') == 'on' or current_inventario.trasbordo == True:
                                        current_inventario.trasbordo = True
                                        current_inventario.save()
                                        if current_inventario.Destinatario.Municipio.Importe_por_trasbordo:                                            
                                            current_inventario_dict['Importe_Transportacion'] += float(current_inventario.Destinatario.Municipio.Importe_por_trasbordo)
                                
                                else:
                                    current_inventario_dict['Importe_Transportacion'] = 0.00
                                current_factura['Importe_Transportacion_Total'] += float(current_inventario_dict['Importe_Transportacion'])
                            
                            else:
                                current_inventario_dict['Importe_Transportacion'] = 0.00
                            #Calculando el importe de transcargo
                            if current_inventario.Peso:
                                if current_inventario.Peso <= 1.50:
                                    if current_inventario.Importe_Derecho_aduanal > 0:
                                        current_inventario_dict['Importe_Transcargo'] = round((80.00 + (float(current_inventario.Importe_Derecho_aduanal) * 1.10)/100 + (float(current_inventario.Importe_Servicio_aduanal) * 1.10)/100), 2)
                                    else:
                                        current_inventario_dict['Importe_Transcargo'] = 80.00

                                if current_inventario.Peso > 1.50 and current_inventario.Peso <= 50.00:
                                    current_inventario_dict['Importe_Transcargo'] = round((199.00 + float(current_inventario.Peso) * 12.00 + (float(current_inventario.Importe_Derecho_aduanal) * 1.10)/100 + (float(current_inventario.Importe_Servicio_aduanal) * 1.10)/100), 2)
                                if current_inventario.Peso > 50.00:
                                    current_inventario_dict['Importe_Transcargo'] = round((800.00 + (float(current_inventario.Importe_Derecho_aduanal) * 1.10)/100 + (float(current_inventario.Importe_Servicio_aduanal) * 1.10)/100), 2)
                            
                                current_factura['Importe_Transcargo_Total'] += current_inventario_dict['Importe_Transcargo']
                            else:
                                current_inventario_dict['Importe_Transcargo'] = 0.00

                            #Calculando total de bultos
                            current_factura['Cantidad_Bultos_Total'] += current_inventario.Cantidad_Bultos

                            #Agregando informacion a la lista
                            current_lista_de_inventarios.append(current_inventario_dict)

                    current_factura['Destinatario'] = Destinatario.objects.filter(CI = current_destinatario).first()
                    current_factura['Inventarios'] = current_lista_de_inventarios
                    #Valor total de la factura
                    current_factura['Precio_Total_Factura'] = current_factura['Importe_Transcargo_Total'] + current_factura['Importe_Seguro_Carga_Total'] + current_factura['Importe_Sobredimension_Total'] + current_factura['Importe_Recargo_Total'] + current_factura['Importe_Transportacion_Total'] + current_factura['Importe_Derecho_Aduanal_Total'] + current_factura['Importe_Servicio_Aduanal_Total']

                    try:
                        with transaction.atomic():
                            #Almacenando la factura en el sistema
                            factura_instance = Factura()
                            factura_instance.Contenido = str(current_factura)
                            factura_instance.isMultiple = True
                            factura_instance.isEnvio = True
                            factura_instance.Fecha = now()
                            factura_instance.User_Facturador = request.user
                            factura_instance.Estado = 'Creada'
                            factura_instance.Destinatario = current_factura['Destinatario']
                            factura_instance.Importe_Total_Factura = current_factura['Precio_Total_Factura']
                            factura_instance.Importe_Transcargo_Total = current_factura['Importe_Transcargo_Total']
                            factura_instance.Importe_Seguro_Carga_Total = current_factura['Importe_Seguro_Carga_Total']
                            factura_instance.Importe_Recargo_Total = current_factura['Importe_Recargo_Total']
                            factura_instance.Importe_Transportacion_Total = current_factura['Importe_Transportacion_Total']
                            factura_instance.Importe_Derecho_Aduanal_Total = current_factura['Importe_Derecho_Aduanal_Total']
                            factura_instance.Importe_Servicio_Aduanal_Total = current_factura['Importe_Servicio_Aduanal_Total']
                            factura_instance.Importe_Sobredimension_Total = current_factura['Importe_Sobredimension_Total']
                            factura_instance.Cantidad_Bultos_Total = current_factura['Cantidad_Bultos_Total']
                            #factura_instance.url = str(request.path) + '?cargos_extra=' + str(current_factura['Importe_Recargo_Total'])
                            factura_instance.save()
                                
                            for current_inventario_object in current_factura['Inventarios']:
                                factura_inventario_instance = Factura_Inventario()
                                factura_inventario_instance.Factura = factura_instance
                                factura_inventario_instance.Inventario = current_inventario_object['Inventario']
                                factura_inventario_instance.Importe_Seguro_Carga = current_inventario_object['Importe_Seguro_Carga']
                                factura_inventario_instance.Importe_Sobredimension = current_inventario_object['Importe_Sobredimension']
                                factura_inventario_instance.Importe_Transportacion = current_inventario_object['Importe_Transportacion']
                                factura_inventario_instance.Importe_Transcargo = current_inventario_object['Importe_Transcargo']
                                factura_inventario_instance.save()

                            # Registro de trazas
                            save_addition(request.user, 'factura', factura_instance.id, str(model_to_dict(factura_instance)))
                    except:
                        raise ValueError('Ha ocurrido un error generando la factura')

                    #Generando codigo QR de la factura
                    # qr = qrcode.QRCode()
                    # qr.add_data('{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}')
                    # qr.make()
                    # img = qr.make_image()
                    # img.save(MEDIA_ROOT +'/QR/factura_' + str(factura_instance.id) +'.png')
                    qr_generado = '{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}'
                    current_factura['id_factura'] = factura_instance.id
                    current_factura['facturador'] = factura_instance.User_Facturador.get_full_name()
                    
                    #Agregando factura a lista general de facturas
                    lista_facturas.append(current_factura)

                #Generando reporte PDF
                template_src = 'pdf/facturacion_multiple_envios_pdf.html'
                template = get_template(template_src)
                context = {'lista_facturas': lista_facturas,'fecha_factura': now(),'request': request,'qr':qr_generado}
                html  = template.render(context)
                result = BytesIO()
                pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
                if not pdf.err:
                    return HttpResponse(result.getvalue(), content_type='application/pdf')
                return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))

            if request.POST.get('operacion_tabla') == 'facturar_ena_menaje':
                #Lista de inventarios a facturar
                inventarios = Inventario.objects.all().filter(~Q(Categoria_Operacion__icontains = 'envio'), ~Q(Categoria_Operacion__icontains = 'envío'), Q(pk__in = list_inventario_selected))

                #Lista de facturas a pasar a la vista
                lista_facturas = []
                
                #Obteniendo lista de destinatarios de la solicitud
                lista_de_destinatarios = [] #Lista de destinatarios
                for current_inventario in inventarios:
                    lista_de_destinatarios.append(current_inventario.Destinatario.CI)
                lista_de_destinatarios = list(dict.fromkeys(lista_de_destinatarios))

                for current_destinatario in lista_de_destinatarios:
                    current_factura = {}
                    current_lista_de_inventarios = []

                    #Cantidad de veces que se mostrara la factura 
                    current_factura['Copias_Facturas'] = range(1)

                    #Valores totales
                    current_factura['Importe_Transcargo_Total'] = 0.00  #OK
                    current_factura['Importe_Seguro_Carga_Total'] = 0.00 #OK
                    current_factura['Importe_Servicio_Corresponsalia_Total'] = 0.00 #OK
                    current_factura['Importe_Transportacion_Total'] = 0.00 #OK
                    current_factura['Importe_Recargo_Total'] = float(request.POST.get('cargos_extra_ena'))
                    current_factura['Importe_Derecho_Aduanal_Total'] = float(request.POST.get('importe_derecho_aduanal'))
                    current_factura['Importe_Servicio_Aduanal_Total'] = float(request.POST.get('importe_servicio_aduanal'))
                    current_factura['Cantidad_Bultos_Total'] = 0

                    lista_inventarios_por_persona = inventarios.filter(Destinatario__CI = current_destinatario)
                    for current_inventario in lista_inventarios_por_persona:
                        current_inventario_dict = {}
                        current_inventario_dict['Inventario'] = current_inventario

                        if current_inventario.isPrepago:
                            current_factura['Importe_Transcargo_Total'] = 0.00
                            current_factura['Importe_Seguro_Carga_Total'] = 0.00
                            current_factura['Importe_Servicio_Corresponsalia_Total'] = 0.00
                            current_factura['Importe_Transportacion_Total'] = 0.00
                            current_factura['Cantidad_Bultos_Total'] += current_inventario.Cantidad_Bultos                            
                            
                            #Agregando informacion a la lista
                            current_inventario_dict['Importe_Transcargo'] = 0.00
                            current_inventario_dict['Importe_Seguro_Carga'] = 0.00
                            current_inventario_dict['Importe_Servicio_Corresponsalia'] = 0.00
                            current_inventario_dict['Importe_Sobredimension'] = 0.00
                            current_inventario_dict['Importe_Transportacion'] = 0.00
                            current_lista_de_inventarios.append(current_inventario_dict)

                        else:
                            #Facturacion de ENA
                            if current_inventario.Categoria_Operacion == 'ENA' or current_inventario.Categoria_Operacion == 'ena' or current_inventario.Categoria_Operacion == 'Ena' or current_inventario.Categoria_Operacion == 'E.N.A' or current_inventario.Categoria_Operacion == 'e.n.a' or current_inventario.Categoria_Operacion == 'E.n.a': 
                                #Calculando el importe de transcargo
                                if current_inventario.Volumen:
                                    if current_inventario.Volumen <= 1:
                                        current_inventario_dict['Importe_Transcargo'] = 765.00
                                    if current_inventario.Volumen > 1:
                                        current_inventario_dict['Importe_Transcargo'] = round(765.00 * float(current_inventario.Volumen), 2)
                                    
                                    current_factura['Importe_Transcargo_Total'] += current_inventario_dict['Importe_Transcargo']
                                else:
                                    current_inventario_dict['Importe_Transcargo'] = 0.00

                                #Calculando precio por seguro de carga
                                if current_inventario.Volumen:
                                    current_inventario_dict['Importe_Seguro_Carga'] = 96.00
                                    current_factura['Importe_Seguro_Carga_Total'] += current_inventario_dict['Importe_Seguro_Carga']
                                else:
                                    current_inventario_dict['Importe_Seguro_Carga'] = 0.00

                                #Calculando precio por servicio de corresponsalia
                                if current_inventario.Volumen:
                                    current_inventario_dict['Importe_Servicio_Corresponsalia'] = 57.00
                                    current_factura['Importe_Servicio_Corresponsalia_Total'] += current_inventario_dict['Importe_Servicio_Corresponsalia']
                                else:
                                    current_inventario_dict['Importe_Servicio_Corresponsalia'] = 0.00

                                #Calculando precio por transportacion
                                if current_inventario.Volumen and request.POST.get('incluir_transportacion_ena') == 'on':
                                    if current_inventario.Destinatario.Municipio.Importe_por_entrega:
                                        current_inventario_dict['Importe_Transportacion'] = current_inventario.Destinatario.Municipio.Importe_por_entrega
                                        # print('importe transportacion',current_inventario_dict['Importe_Transportacion'])
                                        if request.POST.get('trasbordo') == 'on':
                                            current_inventario.trasbordo = True
                                            current_inventario.save()
                                            if current_inventario.Destinatario.Municipio.Importe_por_trasbordo:
                                                # print('importe transportacion',current_inventario_dict['Importe_Transportacion'])
                                                
                                                current_inventario_dict['Importe_Transportacion'] += float(current_inventario.Destinatario.Municipio.Importe_por_trasbordo)
                                                # print('importe transportacion con trasbordo',current_inventario_dict['Importe_Transportacion'])
                                    else:
                                        current_inventario_dict['Importe_Transportacion'] = 0.00
                                    current_factura['Importe_Transportacion_Total'] += current_inventario_dict['Importe_Transportacion']
                                else:
                                    current_inventario_dict['Importe_Transportacion'] = 0.00

                                #Calculando total de bultos
                                current_factura['Cantidad_Bultos_Total'] += current_inventario.Cantidad_Bultos

                                #Agregando informacion a la lista
                                current_lista_de_inventarios.append(current_inventario_dict)

                            #Facturacion de Menaje
                            if current_inventario.Categoria_Operacion == 'MENAJE' or current_inventario.Categoria_Operacion == 'Menaje' or current_inventario.Categoria_Operacion == 'menaje': 
                                #Calculando el importe de transcargo
                                if current_inventario.Volumen:
                                    if current_inventario.Volumen <= 1:
                                        current_inventario_dict['Importe_Transcargo'] = 765.00
                                    if current_inventario.Volumen > 1:
                                        current_inventario_dict['Importe_Transcargo'] = round((765.00 * float(current_inventario.Volumen)), 2)
                                    
                                    current_factura['Importe_Transcargo_Total'] += current_inventario_dict['Importe_Transcargo']
                                else:
                                    current_inventario_dict['Importe_Transcargo'] = 0.00

                                #Calculando precio por seguro de carga
                                if current_inventario.Volumen:
                                    current_inventario_dict['Importe_Seguro_Carga'] = 240.00
                                    current_factura['Importe_Seguro_Carga_Total'] += current_inventario_dict['Importe_Seguro_Carga']
                                else:
                                    current_inventario_dict['Importe_Seguro_Carga'] = 0.00

                                #Calculando precio por servicio de corresponsalia
                                if current_inventario.Volumen:
                                    current_inventario_dict['Importe_Servicio_Corresponsalia'] = 57.00
                                    current_factura['Importe_Servicio_Corresponsalia_Total'] += current_inventario_dict['Importe_Servicio_Corresponsalia']
                                else:
                                    current_inventario_dict['Importe_Servicio_Corresponsalia'] = 0.00

                                #Calculando precio por transportacion
                                if current_inventario.Volumen and request.POST.get('incluir_transportacion_ena') == 'on':
                                    if current_inventario.Destinatario.Municipio.Importe_por_entrega:
                                        current_inventario_dict['Importe_Transportacion'] = current_inventario.Destinatario.Municipio.Importe_por_entrega
                                        if request.POST.get('trasbordo') == 'on':
                                            current_inventario.trasbordo = True
                                            current_inventario.save()
                                            if current_inventario.Destinatario.Municipio.Importe_por_trasbordo:
                                                # print('importe transportacion',current_inventario_dict['Importe_Transportacion'])
                                                
                                                current_inventario_dict['Importe_Transportacion'] += float(current_inventario.Destinatario.Municipio.Importe_por_trasbordo)
                                                # print('importe transportacion con trasbordo',current_inventario_dict['Importe_Transportacion'])
                                    else:
                                        current_inventario_dict['Importe_Transportacion'] = 0.00
                                    current_factura['Importe_Transportacion_Total'] += current_inventario_dict['Importe_Transportacion']
                                else:
                                    current_inventario_dict['Importe_Transportacion'] = 0.00

                                #Calculando total de bultos
                                current_factura['Cantidad_Bultos_Total'] += current_inventario.Cantidad_Bultos

                                #Agregando informacion a la lista
                                current_lista_de_inventarios.append(current_inventario_dict)

                    current_factura['Destinatario'] = Destinatario.objects.filter(CI = current_destinatario).first()
                    current_factura['Inventarios'] = current_lista_de_inventarios
                    #Valor total de la factura

                    if current_inventario.Volumen: 
                        current_factura['Precio_Total_Factura'] = current_factura['Importe_Transcargo_Total'] + current_factura['Importe_Seguro_Carga_Total'] + current_factura['Importe_Servicio_Corresponsalia_Total'] + current_factura['Importe_Transportacion_Total'] + current_factura['Importe_Recargo_Total'] + current_factura['Importe_Derecho_Aduanal_Total'] + current_factura['Importe_Servicio_Aduanal_Total'] + ((current_factura['Importe_Derecho_Aduanal_Total'] * 1.10)/100) + ((current_factura['Importe_Servicio_Aduanal_Total'] * 1.10)/100)
                    else:
                        current_factura['Precio_Total_Factura'] = current_factura['Importe_Recargo_Total'] + current_factura['Importe_Derecho_Aduanal_Total'] + current_factura['Importe_Servicio_Aduanal_Total'] 

                    try:
                        with transaction.atomic():
                            #Almacenando la factura en el sistema
                            factura_instance = Factura()
                            factura_instance.Contenido = str(current_factura)
                            factura_instance.isMultiple = True
                            factura_instance.isEnvio = False
                            factura_instance.Estado = 'Creada'
                            factura_instance.Fecha = now()
                            factura_instance.User_Facturador = request.user
                            factura_instance.Destinatario = current_factura['Destinatario']
                            factura_instance.Importe_Total_Factura = current_factura['Precio_Total_Factura']
                            factura_instance.Importe_Transcargo_Total = current_factura['Importe_Transcargo_Total']
                            factura_instance.Importe_Seguro_Carga_Total = current_factura['Importe_Seguro_Carga_Total']
                            factura_instance.Importe_Recargo_Total = current_factura['Importe_Recargo_Total']
                            factura_instance.Importe_Transportacion_Total = current_factura['Importe_Transportacion_Total']
                            factura_instance.Importe_Derecho_Aduanal_Total = current_factura['Importe_Derecho_Aduanal_Total']
                            factura_instance.Importe_Servicio_Aduanal_Total = current_factura['Importe_Servicio_Aduanal_Total']
                            factura_instance.Importe_Servicio_Corresponsalia_Total = current_factura['Importe_Servicio_Corresponsalia_Total']
                            factura_instance.Cantidad_Bultos_Total = current_factura['Cantidad_Bultos_Total']
                            #factura_instance.url = str(request.path) + '?importe_derecho_aduanal=' + str(current_factura['Importe_Derecho_Aduanal_Total']) + '&importe_servicio_aduanal=' + str(current_factura['Importe_Servicio_Aduanal_Total']) + '&cargos_extra=' + str(current_factura['Importe_Recargo_Total'])
                            factura_instance.save()
                            
                            for current_inventario_object in current_factura['Inventarios']:
                                factura_inventario_instance = Factura_Inventario()
                                factura_inventario_instance.Factura = factura_instance
                                factura_inventario_instance.Inventario = current_inventario_object['Inventario']
                                factura_inventario_instance.Importe_Seguro_Carga = current_inventario_object['Importe_Seguro_Carga']                                
                                factura_inventario_instance.Importe_Servicio_Corresponsalia = current_inventario_object['Importe_Servicio_Corresponsalia']                                
                                factura_inventario_instance.Importe_Transportacion = current_inventario_object['Importe_Transportacion']                                
                                factura_inventario_instance.Importe_Transcargo = current_inventario_object['Importe_Transcargo']
                                factura_inventario_instance.save()
                            
                            # Registro de trazas
                            save_addition(request.user, 'factura', factura_instance.id, str(model_to_dict(factura_instance)))
                    except:
                        raise ValueError('Ha ocurrido un error generando la factura') 

                    #Generando codigo QR de la factura
                    # qr = qrcode.QRCode()
                    # qr.add_data('{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}')
                    # qr.make()
                    # img = qr.make_image()
                    # img.save(MEDIA_ROOT +'/QR/factura_' + str(factura_instance.id) +'.png')
                    qr_generado = "id_transaccion:" + str(factura_instance.id) 
                    #Identificador de la factura
                    current_factura['id_factura'] = factura_instance.id
                    current_factura['facturador'] = factura_instance.User_Facturador.get_full_name()

                    #Agregando factura a lista general de facturas
                    lista_facturas.append(current_factura)

                #Generando reporte PDF
                template_src = 'pdf/facturacion_multiple_ena_menaje_pdf.html'
                template = get_template(template_src)
                context = {'lista_facturas': lista_facturas, 'fecha_factura': now(), 'request': request}
                html  = template.render(context)
                result = BytesIO()
                pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
                if not pdf.err:
                    return HttpResponse(result.getvalue(), content_type='application/pdf')
                return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))
        
        except Exception as inst:
            print(inst)
            messages.error(request, 'Ha ocurrido un error generando el comprobante de pago')
            return redirect(request.path) 

    #Buscando inventarios sin facturar    
    inventarios_sin_facturar = []
    with connection.cursor() as cursor:
        cursor.execute(""" SELECT "inventario_inventario"."id" FROM "inventario_inventario" 
                            WHERE "inventario_inventario"."id" NOT IN (
                            SELECT "inventario_factura_inventario"."Inventario_id" FROM "inventario_factura_inventario"
                            INNER JOIN "inventario_factura" ON "inventario_factura_inventario"."Factura_id" = "inventario_factura"."id"
                            WHERE not "inventario_factura"."Estado" = 'Desestimada'
                            )
                            AND "inventario_inventario"."Nacionalizado" = true """)
        row = cursor.fetchall()
        for current in row:
            inventarios_sin_facturar.append(list(current)[0])
        
    #Lista de inventarios nacionalizados sin facturar    
    inventarios = Inventario.objects.all().filter(Q(Estado = 'Inventario'), Q(id__in = inventarios_sin_facturar)).order_by('HBL')

    #Aplicacion de filtros
    inventario_filter = InventarioFilter(request.GET, queryset=inventarios)
    inventarios = inventario_filter.qs

    #Paginator
    paginator = Paginator(inventarios, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    #Buscando ENA y Envios
    if inventarios.filter(Q(Categoria_Operacion__icontains = 'envio') | Q(Categoria_Operacion__icontains = 'envío')).count() > 0:
        isEnvio = True

    if inventarios.filter(Q(Categoria_Operacion__icontains = 'ENA') | Q(Categoria_Operacion__icontains = 'E.N.A')).count() > 0:
        isEna_menaje = True

    if inventarios.filter(Q(Categoria_Operacion__icontains = 'Menaje')).count() > 0:
        isEna_menaje = True
    
    ctx = {'page_obj': page_obj, 'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'inventario_filter': inventario_filter, 'isEnvio': isEnvio, 'isEna_Menaje': isEna_menaje,'form_hbl_escaneados':form_hbl_escaneados}
    return render(request, 'inventario/inventario_list.html', ctx)
        

#--------Comprobante de entrega de operadores--------------------------------------
@login_required(login_url='login')
def comprobante_entrega_operadores(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Textos de pantalla
    header_text     = 'Comprobantes de operadores pendientes de cobro'
    breadcrumb_text = 'Comprobantes pendientes de cobro'

    #Definiendo menu activo
    active_menu = 'comprobante_pago_operador'
    action = 'Pendiente de cobro'
    if request.method == 'POST':
        date_time_obj = datetime.strptime(request.POST.get('fecha_entrega'), '%Y-%m-%d').date()
        try:
            with transaction.atomic():
                if len(request.POST.getlist('comprobante_id')) == 0:
                    messages.error(request, 'Debe seleccionar al menos un comprobante.')
                    return redirect(request.path)

                if not request.POST.get('fecha_entrega'):
                    messages.error(request, 'Debe definir la fecha de cobro.')
                    return redirect(request.path)

                if not request.POST.get('recibo_ingreso'):
                    messages.error(request, 'Debe introducir el recibo de ingreso.')
                    return redirect(request.path)

                for current_comprobante_id in request.POST.getlist('comprobante_id'):
                    current_comprobante = Factura_Operador.objects.get(pk = current_comprobante_id)
                    current_comprobante.Fecha_Cobro = request.POST.get('fecha_entrega')
                    current_comprobante.Estado = 'Cobrada'
                    current_comprobante.Recibo_Ingreso = request.POST.get('recibo_ingreso')
                    current_comprobante.save()

                    for current_factura_destinatario in current_comprobante.Facturas_Destinatarios.all():
                        #Declarando factura de destinatario como entregada
                        current_factura_destinatario.Estado = 'Cobrada'
                        current_factura_destinatario.Fecha_cobro = request.POST.get('fecha_entrega')
                        current_factura_destinatario.save()
                        # Registro de trazas
                        save_edition(request.user, 'factura', current_factura_destinatario.id, str(model_to_dict(current_factura_destinatario)))

                        #Declarando inventario como entregado
                        for current_inventario in current_factura_destinatario.Inventario.all():
                            current_inventario.Estado = 'Entregado'
                            current_inventario.Tipo_Entrega = 'Puerta a puerta'
                            current_inventario.Fecha_Entrega = request.POST.get('fecha_entrega')
                            current_inventario.Nombre_Entrega = current_inventario.Destinatario.Nombre
                            current_inventario.CI_Entrega = current_inventario.Destinatario.CI
                            current_inventario.Pasaporte_DNI_Entrega = current_inventario.Destinatario.Pasaporte_DNI
                            current_inventario.Direccion_Entrega = current_inventario.Destinatario.Direccion
                            current_inventario.Provincia_Entrega = current_inventario.Destinatario.Provincia
                            current_inventario.Municipio_Entrega = current_inventario.Destinatario.Municipio
                            current_inventario.Telefono_Entrega = current_inventario.Destinatario.Telefono
                            current_inventario.save()
                            # Registro de trazas
                            save_edition(request.user, 'inventario', current_inventario.id, str(model_to_dict(current_inventario)))

                            #Salvando Tracking
                            traking = Traking()
                            traking.Inventario      = current_inventario
                            traking.Estado          = 'Entregado'
                            traking.Observaciones   = 'Inventario entregado al destinatario'
                            traking.Fecha           = now()
                            traking.save()
                            # Registro de trazas
                            save_addition(request.user, 'traking', traking.id, str(model_to_dict(traking)))

                    # Registro de trazas
                    save_edition(request.user, 'factura_operador', current_comprobante.id, str(model_to_dict(current_comprobante)))        

                messages.success(request, 'Comprobantes cobrados satisfactoriamente.')
                return redirect(request.path)
        
        except Exception as inst:
            # print(inst)
            messages.error(request, 'Ha ocurrido un error en el proceso')
            messages.error(request, inst)
            return redirect(request.path)

    comprobantes_operadores = Factura_Operador.objects.filter(Estado = 'Pendiente de cobro').order_by('Fecha_Creacion')

    #Aplicacion de filtros
    comprobante_filter      = Factura_Operador_Filter(request.GET, queryset=comprobantes_operadores)
    comprobantes_operadores = comprobante_filter.qs

    #Paginator
    paginator = Paginator(comprobantes_operadores, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj, 'active_menu': active_menu, 'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'action': action, 'comprobante_filter': comprobante_filter }
    return render(request, 'entrega/lista_comprobantes_entrega.html', ctx)


@login_required(login_url='login')
def comprobante_entrega_operadores_cobrados(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Textos de pantalla
    header_text     = 'Comprobantes de operadores cobrados'
    breadcrumb_text = 'Comprobantes cobrados'

    #Definiendo menu activo
    active_menu = 'comprobante_pago_operador'
    action = 'Cobrada'

    comprobantes_operadores = Factura_Operador.objects.filter(Estado = 'Cobrada').order_by('Fecha_Creacion')

    #Aplicacion de filtros
    comprobante_filter      = Factura_Operador_Filter(request.GET, queryset=comprobantes_operadores)
    comprobantes_operadores = comprobante_filter.qs

    #Paginator
    paginator = Paginator(comprobantes_operadores, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj, 'active_menu': active_menu, 'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'action': action, 'comprobante_filter': comprobante_filter }
    return render(request, 'entrega/lista_comprobantes_entrega.html', ctx)


#----Gestion de Facturas---------------------------------------------------
@login_required(login_url='login')
def facturas_list(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Definiendo menu activo
    active_menu = 'comprobante_pago_destinatario'

    #Formulario de factura
    form_cobro_factura = Factura_Cobrada_Form()

    #Fomulario para seleccionar rango de fecha de facturas a exportar
    form_rango_fechas=Reporte_Contable_Aduana_Form()

    # actualizar_valor()
    # delete_comprobante()
    # desestimar_comprobante()
    # update_destinatario()
    # update_comprobante_operador()
    # update_comprobante()
    # desnacionalizar_cargas()
    #Captura de formularios
    if request.method == 'POST':
        
        #Declarar como cobradas
        if request.POST.get('operacion_tabla') == '1':
            if not request.POST.get('recibo_ingreso'):
                    messages.error(request, 'Debe introducir el recibo de ingreso.')
                    return redirect(request.path)
            form_cobro_factura = Factura_Cobrada_Form(request.POST)
            if form_cobro_factura.is_valid():
                #Facturas no cobradas
                facturas_cobradas = []
                facturas_sin_cobrar = []
                list_facturas = request.POST.getlist('inventario_id')
                for factura_id in list_facturas:
                    current_factura = Factura.objects.get(pk = factura_id)
                    if current_factura.Estado == 'Creada':
                        current_factura.Estado = 'Cobrada'
                        current_factura.Fecha_cobro = form_cobro_factura.cleaned_data['Fecha_Cobro']
                        current_factura.Recibo_Ingreso = request.POST.get('recibo_ingreso')
                        current_factura.save()
                        
                        for current_inventario in current_factura.Inventario.all():
                            #Completando informacion de entrega
                            current_inventario.Tipo_Entrega = 'Presencial'
                            current_inventario.Estado = 'Entregado'
                            current_inventario.Fecha_Entrega = form_cobro_factura.cleaned_data['Fecha_Cobro']
                            current_inventario.Nombre_Entrega = current_inventario.Destinatario.Nombre
                            current_inventario.CI_Entrega = current_inventario.Destinatario.CI
                            current_inventario.Pasaporte_DNI_Entrega = current_inventario.Destinatario.Pasaporte_DNI
                            current_inventario.Direccion_Entrega = current_inventario.Destinatario.Direccion
                            current_inventario.Provincia_Entrega = current_inventario.Destinatario.Provincia
                            current_inventario.Municipio_Entrega = current_inventario.Destinatario.Municipio
                            current_inventario.Telefono_Entrega = current_inventario.Destinatario.Telefono
                            current_inventario.save()
                            # Registro de trazas
                            save_edition(request.user, 'inventario', current_inventario.id, str(model_to_dict(current_inventario)))

                            #Salvando Tracking
                            traking = Traking()
                            traking.Inventario      = current_inventario
                            traking.Estado          = 'Entregado'
                            traking.Observaciones   = 'Inventario entregado al destinatario'
                            traking.Fecha           = now()
                            traking.save()
                            # Registro de trazas
                            save_addition(request.user, 'traking', traking.id, str(model_to_dict(traking)))
                            
                        facturas_cobradas.append(current_factura.id)
                        # Registro de trazas
                        save_edition(request.user, 'factura', current_factura.id, str(model_to_dict(current_factura)))
    
                    else:
                        facturas_sin_cobrar.append(current_factura.id) 

                if len(facturas_cobradas) > 0:
                    messages.success(request, 'Las facturas ' + str(facturas_cobradas).replace('[', '').replace(']', '') + ' fueron cobradas satisfactoriamente')
                if len(facturas_sin_cobrar) > 0:
                    messages.warning(request, 'Las siguientes facturas no fueron cobradas: ' + str(facturas_sin_cobrar).replace('[', '').replace(']', '') + '. Por favor, revise el estado de estas cargas.')
                
                return redirect(request.path)  
            else:
                messages.error(request, 'Información incorrecta. Por favor complete los datos requeridos.')
                return redirect(request.path)

        #Desestimar facturas
        if request.POST.get('operacion_tabla') == '2':
            list_facturas = request.POST.getlist('inventario_id')
            for factura_id in list_facturas:
                current_factura = Factura.objects.get(pk = factura_id)
                if current_factura.Estado == 'Creada':
                    current_factura.Estado = 'Desestimada'
                    current_factura.save()
                    # Registro de trazas
                    save_edition(request.user, 'factura', current_factura.id, str(model_to_dict(current_factura)))
            messages.success(request, 'Facturas desestimadas satisfactoriamente')
            return redirect(request.path)  

        #Exportar facturas
        if request.POST.get('operacion_tabla') == '3':
            #Capturando datos del formulario
            fecha_desde = request.POST.get('Fecha_Desde')
            fecha_hasta = request.POST.get('Fecha_Hasta')
            # list_inventario = request.POST.getlist('inventario_id')
            if (not fecha_desde) or (not fecha_hasta):
                messages.error(request, 'Debe seleccionar un rango de tiempo')
                return redirect(request.path)
            facturas = Factura.objects.filter(Fecha__gte=fecha_desde,Fecha__lte=fecha_hasta)
            wb = openpyxl.Workbook()
            # hoja = wb.active
            wb.remove(wb.active)

            # Asigna formato de ejemplo2
            formato_fecha = "%d-%m-%y"
            title_worksheet = 'Facturas del período' + fecha_desde + '-' + fecha_hasta
            worksheet = wb.create_sheet(title=title_worksheet, index=1)

            # Crea la fila del encabezado con los títulos
            columns = ['No. Factura', 'Importe']
            row_num = 1
            # Asigna el titulo de cada celda
            for col_num, column_title in enumerate(columns, 1):
                cell = worksheet.cell(row=row_num, column=col_num)
                cell.value = column_title

            # Itera sobre las facturas
            for _, factura in enumerate(facturas, 1):
                row_num += 1

                # Define los datos de la fila
                row = [
                    factura.id,
                    factura.Importe_Total_Factura,
                ]

                # Asigna los datos a cada celda de la fila
                for col_num, cell_value in enumerate(row, 1):
                    cell = worksheet.cell(row=row_num, column=col_num)
                    cell.value = cell_value

            wb.save('D:\\'+'Facturas '+fecha_desde+' - '+fecha_hasta+'.xlsx')


    #Lista de manifiestos
    Facturas = Factura.objects.filter(~Q(Estado = 'Desestimada'), ~Q(Estado = 'Cobrada')).order_by('-id')

    #Aplicacion de filtros
    facturas_filter = FacturaFilter(request.GET, queryset=Facturas)
    Facturas = facturas_filter.qs

    #Paginator
    paginator = Paginator(Facturas, 100) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj, 'facturas_filter': facturas_filter,'active_menu': active_menu,'form_cobro_factura':form_cobro_factura,'form_rango_fechas':form_rango_fechas}
    return render(request, 'factura/factura_list.html', ctx)

def facturas_desestimadas_list(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Definiendo menu activo
    active_menu = 'comprobante_pago_destinatario'

    #Formulario de factura
    form_cobro_factura = Factura_Cobrada_Form()

    #Lista de manifiestos
    Facturas = Factura.objects.filter(Q(Estado = 'Desestimada')).order_by('-id')

    #Aplicacion de filtros
    facturas_filter = FacturaFilter(request.GET, queryset=Facturas)
    Facturas = facturas_filter.qs

    #Paginator
    paginator = Paginator(Facturas, 100) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj, 'facturas_filter': facturas_filter, 'form_cobro_factura': form_cobro_factura, 'active_menu': active_menu}
    return render(request, 'factura/factura_list.html', ctx)

def facturas_cobradas_list(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Definiendo menu activo
    active_menu = 'comprobante_pago_destinatario'

    #Formulario de factura
    form_cobro_factura = Factura_Cobrada_Form()

    #Lista de manifiestos
    Facturas = Factura.objects.filter(Q(Estado = 'Cobrada')).order_by('-id')

    #Aplicacion de filtros
    facturas_filter = FacturaFilter(request.GET, queryset=Facturas)
    Facturas = facturas_filter.qs

    #Paginator
    paginator = Paginator(Facturas, 100) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj, 'facturas_filter': facturas_filter, 'form_cobro_factura': form_cobro_factura, 'active_menu': active_menu}
    return render(request, 'factura/factura_list.html', ctx)

def factura_detalle_pdf(request, id_factura):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Capturando factura
    current_factura_object = get_object_or_404(Factura, pk = id_factura)
    #Lista de facturas a pasar a la vista
    lista_facturas = []
    #Diccionario de factura
    current_factura = {}

    #Factura de envios multiples 
    if current_factura_object.isEnvio and current_factura_object.isMultiple:
        #Valores totales
        current_factura['Copias_Facturas'] = range(1)
        current_factura['Importe_Transcargo_Total'] = current_factura_object.Importe_Transcargo_Total
        current_factura['Importe_Seguro_Carga_Total'] = current_factura_object.Importe_Seguro_Carga_Total
        current_factura['Importe_Sobredimension_Total'] = current_factura_object.Importe_Sobredimension_Total
        current_factura['Importe_Recargo_Total'] = current_factura_object.Importe_Recargo_Total
        current_factura['Importe_Transportacion_Total'] = current_factura_object.Importe_Transportacion_Total
        current_factura['Importe_Derecho_Aduanal_Total'] = current_factura_object.Importe_Derecho_Aduanal_Total
        current_factura['Importe_Servicio_Aduanal_Total'] = current_factura_object.Importe_Servicio_Aduanal_Total
        current_factura['Destinatario'] = current_factura_object.Destinatario
        current_factura['facturador'] = current_factura_object.User_Facturador.get_full_name()
        current_factura['Cantidad_Bultos_Total'] = current_factura_object.Cantidad_Bultos_Total
        current_factura['Inventarios'] = Factura_Inventario.objects.filter(Factura = current_factura_object)
        #Valor total de la factura
        current_factura['Precio_Total_Factura'] = current_factura_object.Importe_Total_Factura
        #Identificador de la factura
        current_factura['id_factura'] = current_factura_object.id
        #Agregando factura a lista general de facturas
        lista_facturas.append(current_factura)

        #QR datos de transaccion
        qr_generado = '{"id_transaccion": ' + str(current_factura_object.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}' 

        #Generando reporte PDF
        template_src = 'pdf/facturacion_multiple_envios_pdf.html'
        template = get_template(template_src)
        context = {'lista_facturas': lista_facturas, 'fecha_factura': current_factura_object.Fecha, 'request': request,'qr':qr_generado}
        html  = template.render(context)
        result = BytesIO()
        pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
        if not pdf.err:
            return HttpResponse(result.getvalue(), content_type='application/pdf')
        return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))

    if not current_factura_object.isEnvio and current_factura_object.isMultiple:
        #Valores totales
        current_factura['Copias_Facturas'] = range(1)
        current_factura['Importe_Transcargo_Total'] = current_factura_object.Importe_Transcargo_Total
        current_factura['Importe_Seguro_Carga_Total'] = current_factura_object.Importe_Seguro_Carga_Total
        current_factura['Importe_Servicio_Corresponsalia_Total'] = current_factura_object.Importe_Servicio_Corresponsalia_Total
        current_factura['Importe_Recargo_Total'] = current_factura_object.Importe_Recargo_Total
        current_factura['Importe_Transportacion_Total'] = current_factura_object.Importe_Transportacion_Total
        current_factura['Importe_Derecho_Aduanal_Total'] = current_factura_object.Importe_Derecho_Aduanal_Total
        current_factura['Importe_Servicio_Aduanal_Total'] = current_factura_object.Importe_Servicio_Aduanal_Total
        current_factura['Destinatario'] = current_factura_object.Destinatario
        current_factura['Cantidad_Bultos_Total'] = current_factura_object.Cantidad_Bultos_Total
        current_factura['facturador'] = current_factura_object.User_Facturador.get_full_name()
        current_factura['Inventarios'] = Factura_Inventario.objects.filter(Factura = current_factura_object)
        #Valor total de la factura
        current_factura['Precio_Total_Factura'] = current_factura_object.Importe_Total_Factura
        #Identificador de la factura
        current_factura['id_factura'] = current_factura_object.id
        #Agregando factura a lista general de facturas
        lista_facturas.append(current_factura)

        #QR datos de transaccion
        qr_generado = '{"id_transaccion": ' + str(current_factura_object.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}' 

        #Generando reporte PDF
        template_src = 'pdf/facturacion_multiple_ena_menaje_pdf.html'
        template = get_template(template_src)
        context = {'lista_facturas': lista_facturas, 'fecha_factura': current_factura_object.Fecha, 'request': request,'qr':qr_generado}
        html  = template.render(context)
        result = BytesIO()
        pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
        if not pdf.err:
            return HttpResponse(result.getvalue(), content_type='application/pdf')
        return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))

    if not current_factura_object.isMultiple:
        current_inventario_dict = {}
        current_inventario_dict['Inventario'] = Factura_Inventario.objects.filter(Factura = current_factura_object.id).first().Inventario
        #Cantidad de veces que se mostrara la factura 
        current_inventario_dict['Copias_Facturas'] = range(1)
        
        #Valores
        current_inventario_dict['Importe_Seguro_Carga'] = current_factura_object.Importe_Seguro_Carga_Total
        current_inventario_dict['Importe_Transportacion'] = current_factura_object.Importe_Transportacion_Total
        current_inventario_dict['Importe_Transcargo'] = current_factura_object.Importe_Transcargo_Total 
        current_inventario_dict['Precio_Total_Factura'] = current_factura_object.Importe_Total_Factura
        current_inventario_dict['facturador'] = current_factura_object.User_Facturador.get_full_name()
        current_inventario_dict['Cantidad_Bultos'] = current_factura_object.Cantidad_Bultos_Total
        current_inventario_dict['id_factura'] = current_factura_object.id 
        if current_factura_object.isEnvio:
            current_inventario_dict['Importe_Sobredimension'] = current_factura_object.Importe_Sobredimension_Total
        else:
            current_inventario_dict['Importe_Servicio_Corresponsalia'] = current_factura_object.Importe_Servicio_Corresponsalia_Total

        # #QR datos de transaccion
        qr_generado = '{"id_transaccion": ' + str(current_factura_object.id) + ', "importe": ' + str(current_inventario_dict['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}' 

        #Generando reporte PDF
        template_src = 'pdf/factura_de_inventario.html'
        template = get_template(template_src)
        context = {'current_inventario_dict': current_inventario_dict, 'fecha_factura': current_factura_object.Fecha, 'request': request, 'isEnvio': current_factura_object.isEnvio}
        html  = template.render(context)
        result = BytesIO()
        pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
        if not pdf.err:
            return HttpResponse(result.getvalue(), content_type='application/pdf')
        return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))

def factura_operador_detalle_pdf(request, id_factura):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404
    #Capturando factura
    current_factura = get_object_or_404(Factura_Operador, pk = id_factura)
    #Obteniendo el traslado
    entrega = get_object_or_404(Entrega,Factura_Operador = current_factura.id)
    #Obteniendo el transportista
    transportista = get_object_or_404(Transportista,pk = entrega.Transportista.id)
    #Generando reporte PDF
    template_src = 'pdf/facturacion_operador.html'
    template = get_template(template_src)
    context = {'current_factura': current_factura,'transportista':transportista,'entrega':entrega, 'request': request}
    html  = template.render(context)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
    if not pdf.err:
        return HttpResponse(result.getvalue(), content_type='application/pdf')
    return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))

    
#----Tracking---------------------------------------------------
@login_required(login_url='login')
def tracking_view(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Traking del HBL
    current_traking = None
    current_inventario = None
    traking_form = Tracking_Form()
    if request.method == 'POST':
        if (not request.POST.get('HBL')) and (not request.POST.get('CI')) and (not request.POST.get('Nombre')):
            messages.error(request, 'Debe ingresar alguno de los datos anteriores.')
        else:
            try:

                #Obteniendo inventario
                current_inventario = ''
                inventarios = []
                # Por HBL
                if request.POST.get('HBL'):
                    current_inventario = Inventario.objects.filter(HBL = request.POST.get('HBL'))
                    for inv in current_inventario:
                        inventarios.append(inv.id)                   
                #Por CI
                if request.POST.get('CI'):
                    current_inventario = Inventario.objects.filter(Destinatario__CI = request.POST.get('CI'))
                    for inv in current_inventario:
                        inventarios.append(inv.id)
                #Por Nombre
                if request.POST.get('Nombre'):
                    current_inventario = Inventario.objects.filter(Destinatario__Nombre = request.POST.get('Nombre'))
                    for inv in current_inventario:
                        inventarios.append(inv.id)

                #Obteniendo traking de inventario
                current_traking = Traking.objects.filter(Inventario__in = inventarios).order_by('Fecha')
                print(current_traking)
            except Exception as inst:
                print(inst)
                messages.error(request, 'El dato ingresado no se encuentra registrado en el sistema.')
                return redirect(request.path)
        
    ctx = {'current_traking': current_traking, 'current_inventario': current_inventario,'traking_form':traking_form}
    return render(request, 'tracking/tracking.html', ctx)


#OPERACIONES DE CORRECCION--------------------------------------------
def correccion(request):
    #Facturas multiples
    #contenido = "[{'Copias_Facturas': range(0, 1), 'Importe_Transcargo_Total': 1243.91, 'Importe_Seguro_Carga_Total': 12.0, 'Importe_Sobredimension_Total': 0.0, 'Importe_Recargo_Total': 0.0, 'Importe_Transportacion_Total': 390.0, 'Importe_Derecho_Aduanal_Total': 0.0, 'Importe_Servicio_Aduanal_Total': 650.0, 'Destinatario': <Destinatario: Darlyn Veronica Ponce Cabado>, 'Inventarios': [{'Inventario': <Inventario: MXT2050012802001>, 'Importe_Seguro_Carga': 12.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 283.91}, {'Inventario': <Inventario: MXT2050012803001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012804001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012805001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012806001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012807001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012808001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012809001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012810001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012811001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012812001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012813001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050012814001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}], 'Precio_Total_Factura': 2295.91}]"
    contenido = "{'Copias_Facturas': range(0, 1), 'Importe_Transcargo_Total': 720.0, 'Importe_Seguro_Carga_Total': 0.0, 'Importe_Sobredimension_Total': 0.0, 'Importe_Recargo_Total': 234324.345, 'Importe_Transportacion_Total': 270.0, 'Importe_Derecho_Aduanal_Total': 0.0, 'Importe_Servicio_Aduanal_Total': 450.0, 'Destinatario': <Destinatario: Walfrido Ortega Riveron>, 'Inventarios': [{'Inventario': <Inventario: MXT2050008281001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050008283001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050008284001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050008285001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050008286001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050008287001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050008288001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050008290001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}, {'Inventario': <Inventario: MXT2050008291001>, 'Importe_Seguro_Carga': 0.0, 'Importe_Sobredimension': 0.0, 'Importe_Transportacion': 30.0, 'Importe_Transcargo': 80.0}], 'Precio_Total_Factura': 235764.345}"
    #contenido = "[{'Copias_Facturas': range(0, 1), 'Importe_Transcargo_Total': 765.0, 'Importe_Seguro_Carga_Total': 96.0, 'Importe_Servicio_Corresponsalia_Total': 57.0, 'Importe_Transportacion_Total': 30.0, 'Importe_Recargo_Total': 0.0, 'Importe_Derecho_Aduanal_Total': 0.0, 'Importe_Servicio_Aduanal_Total': 0.0, 'Destinatario': <Destinatario: Walfrido Ortega Riveron>, 'Inventarios': [{'Inventario': <Inventario: MXT2050008282001>, 'Importe_Transcargo': 765.0, 'Importe_Seguro_Carga': 96.0, 'Importe_Servicio_Corresponsalia': 57.0, 'Importe_Transportacion': 30.0}], 'Precio_Total_Factura': 948.0}]"

    contenido_uno = contenido.replace("'Copias_Facturas': range(0, 1), ", '').replace('[', '').replace(']', '').split(', ')
    contenido_para_json = contenido_uno[0] + ', ' + contenido_uno[1] + ', ' + contenido_uno[2] + ', ' + contenido_uno[3] + ', ' + contenido_uno[4] + ', ' + contenido_uno[5] + ', ' + contenido_uno[6] + '}'
    contenido_json = json.loads(contenido_para_json.replace("'", '"'))
    #print(contenido_json)

    #Facturas No multiples
    contenido_no_multiple = "{'Inventario': <Inventario: MXT2050008282001>, 'Copias_Facturas': range(0, 1), 'Importe_Transcargo': 765.0, 'Importe_Seguro_Carga': 96.0, 'Importe_Servicio_Corresponsalia': 57.0, 'Importe_Transportacion': 30.0, 'Precio_Total_Factura': 998.0}"
    contenido_no_multiple_uno = contenido_no_multiple.split(', ')
    print(contenido_no_multiple_uno[3])
    print(contenido_no_multiple_uno[4])
    print(contenido_no_multiple_uno[5])
    print(contenido_no_multiple_uno[6])
    print(contenido_no_multiple_uno[7])
    contenido_para_json = '{' + contenido_no_multiple_uno[3] + ', ' + contenido_no_multiple_uno[4] + ', ' + contenido_no_multiple_uno[5] + ', ' + contenido_no_multiple_uno[6] + ', ' + contenido_no_multiple_uno[7]
    contenido_json = json.loads(contenido_para_json.replace("'", '"'))

    print(contenido_json)
    
    HBL_current = contenido_no_multiple_uno[0].replace("{'Inventario': <Inventario: ", '').replace('>', '')
    current_inventario = Inventario.objects.filter(HBL = HBL_current).first()
    print(current_inventario.Importe_Derecho_aduanal)
    

    #print(contenido_no_multiple_uno)



    
    
    """
    USUARIO = 'aerov'
    PASS = 'eh7443fx'
    MANIFIESTO = '0358/2021'
    HBL = 'MAY21110540'
    CODIGO_ADUANA = '0200'

    URL= 'https://sua.aduana.cu/GINASUA/serviciosExternos.php'
    headers = {
        'Content-Type': 'application/xml',
        'Accept': 'application/xml',
    }
    data = '<?xml version=\"1.0\" encoding=\"utf-8\"?><soap:Envelope xmlns:soap=\"http://schemas.xmlsoap.org/soap/envelope/\"><soap:Body><GABLDespachado><usuario>'+ USUARIO +'</usuario><clave>'+ PASS +'</clave><manifiesto>'+ MANIFIESTO +'</manifiesto><blga>'+ HBL +'</blga><codigoaduana>'+ CODIGO_ADUANA +'</codigoaduana></GABLDespachado></soap:Body></soap:Envelope>'
    
    resp = requests.get( URL, headers = headers, data = data, verify=False )
    print('PRUEBAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA')
    resp_strip = strip_tags(resp.content)
    dict = resp_strip.replace('\\', '').replace("b'n", ""). replace("n'", "")
    dicto = json.loads(dict)
    print(dicto)


    
    destinatarios = Destinatario.objects.all()

    for current in destinatarios:
        if str(current.CI).endswith('.0'):
            current.CI = str(current.CI).replace('.0', '')
        
        if str(current.Telefono).endswith('.0'):
            current.Telefono = str(current.Telefono).replace('.0', '')
            
    current.save()

    
    inventarios = Inventario.objects.all()
    lista_inventarios = []
    lista_inventarios_eliminados = []
    
    for current_inventario in inventarios:
        data={}
        data['HBL']=current_inventario.HBL
        data['CI']=current_inventario.Destinatario.CI

        for item in lista_inventarios:
            if item['HBL'] == current_inventario.HBL and item['CI'] == current_inventario.Destinatario.CI:
                lista_inventarios_eliminados.append(data)
                current_inventario.delete()
                break
        lista_inventarios.append(data)
    

    print('------------ INVENTARIOS TOTALES --------------- ')
    print(lista_inventarios)


    print('------------ INVENTARIOS ELIMINADOS --------------- ')
    print(lista_inventarios_eliminados)
    """

#ELIMINAR------------------------------------------------------------------------------------------------------------------
"""
@login_required(login_url='login')
def valorizar_desde_aduana(request):
    #Lista de inventarios nacionalizados
    inventarios_nacionalizados = []

    if request.method == 'POST':
        inventarios_nacionalizados = []
        if True:
            inventarios = Inventario.objects.all().filter(Q(Importe_Derecho_aduanal = None), Q(Importe_Servicio_aduanal = None), Q(Nacionalizado = True))[:500]
            for current_inventario in inventarios:
                #Trabajo con manifiesto para el servicio de la aduana
                #ESTO SE AGREGARA A LA SALVA DEL MANIFIESTO EN LA DB
                man = str(current_inventario.Manifiesto)
                if len(man.split('/')[0]) < 4:
                    man = '0' + str(current_inventario.Manifiesto)
                
                if len(man.split('/')) == 1:
                    man = man + '/' + str(now().year)
                #Fin

                #dicto = {'success': True, 'despachos': [{'BOLETIN_DERECHO': '171021047035915000007', 'NO_BLGA': 'MAY21110540', 'MANIFIESTOS': '0358/2021', 'VALOR_DERECHOS': '0', 'VALOR_SERVICIO': '50'}]}
                try:
                    with transaction.atomic():
                        #Consultar informacion de la aduana
                        USUARIO = 'aerov'
                        PASS = 'eh7443fx'
                        MANIFIESTO = man
                        HBL = current_inventario.HBL
                        CODIGO_ADUANA = '0200'

                        URL= 'https://sua.aduana.cu/GINASUA/serviciosExternos.php'
                        headers = {
                            'Content-Type': 'application/xml',
                            'Accept': 'application/xml',
                        }
                        data = '<?xml version=\"1.0\" encoding=\"utf-8\"?><soap:Envelope xmlns:soap=\"http://schemas.xmlsoap.org/soap/envelope/\"><soap:Body><GABLDespachado><usuario>'+ USUARIO +'</usuario><clave>'+ PASS +'</clave><manifiesto>'+ MANIFIESTO +'</manifiesto><blga>'+ HBL +'</blga><codigoaduana>'+ CODIGO_ADUANA +'</codigoaduana></GABLDespachado></soap:Body></soap:Envelope>'
                        
                        resp = requests.get( URL, headers = headers, data = data, verify=False )
                        resp_strip = strip_tags(resp.content)
                        dict = resp_strip.replace('\\', '').replace("b'n", ""). replace("n'", "")
                        dicto = json.loads(dict)

                        if dicto['success'] == True:
                            current_inventario.Importe_Derecho_aduanal = float(dicto['despachos'][0]['VALOR_DERECHOS'])
                            current_inventario.Importe_Servicio_aduanal = float(dicto['despachos'][0]['VALOR_SERVICIO'])
                            current_inventario.Nacionalizado = True
                            current_inventario.Categoria_Operacion = 'ENVIO'
                            current_inventario.save()

                            # Registro de trazas
                            save_edition(request.user, 'inventario', current_inventario.id, str(model_to_dict(current_inventario)))
                            
                            #Mostrando inventarios nacionalizados
                            inventarios_nacionalizados.append(current_inventario) 
                        else:
                            current_inventario.Importe_Derecho_aduanal = 0
                            current_inventario.Importe_Servicio_aduanal = 0
                            if current_inventario.Categoria_Operacion == None:
                                current_inventario.Categoria_Operacion = 'E.N.A'
                            current_inventario.save()

                            # Registro de trazas
                            save_edition(request.user, 'inventario', current_inventario.id, str(model_to_dict(current_inventario)))

                    #Fin de la consulta
                except:
                    pass
                    
    ctx = {'inventarios_nacionalizados': inventarios_nacionalizados, 'cantidad_nacionalizados': len(inventarios_nacionalizados)}
    return render(request, 'operacion_mercancia/valorizar_nacionalizados.html', ctx)
"""
@login_required(login_url='login')
def verify_inventario(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404
    #Informacion para el template
    header_text     = 'Rectificación de Manifiesto'
    breadcrumb_text = 'Rectificación de Manifiesto'
    #Definiendo menu activo
    active_menu = 'rectificacion_inventario'

    #Traking del HBL
    current_traking = None
    current_inventario = None

    #Formulario de tabla
    form = Verify_Inventory_Form()
    hbl_no_manifestados = []
    if request.method == 'POST':
        if not request.POST.get('HBL'):
            messages.error(request, 'Debe indicar al menos un HBL.')
        else:
            # try:
            #Declarar como existentes
            form = Verify_Inventory_Form(request.POST)
            if form.is_valid():
                hbl_regex = re.compile(r'[A-Z0-9-]*')
                #HBL escaneados
                hbl = request.POST.get('HBL')
                no_contenedor = request.POST.get('No_Contenedor')
                seleccion = re.findall(hbl_regex,hbl)
                for hbl in seleccion:
                    if hbl:
                        inventario = Inventario.objects.filter(HBL=hbl)
                        if inventario:
                            for inv in inventario:
                                inv.exist = True
                                inv.Estado = 'Inventario'
                                # inv.save()
                                if inv.Categoria_Operacion == 'E.N.A' or inv.Categoria_Operacion == 'ENA':
                                    cantidad_repeticiones = {i:seleccion.count(i) for i in seleccion}
                                    valor=0
                                    for cantidad in cantidad_repeticiones:
                                        valor = cantidad_repeticiones[cantidad]
                                    if inv.Cantidad_Bultos < valor:
                                        inv.Incidencia = Incidencia.objects.get(Tipo__icontains='Sobrante')
                                    if inv.Cantidad_Bultos > valor:
                                        inv.Incidencia = Incidencia.objects.get(Tipo__icontains='Faltante')
                                    # print('cantidad_repeticiones',cantidad_repeticiones)
                                inv.save()    
                        else:
                            hbl_current = HBL_No_Manifestados.objects.filter(HBL=hbl)
                            if not hbl_current:
                                no_manifestados = HBL_No_Manifestados()
                                no_manifestados.HBL = hbl
                                no_manifestados.Fecha_Rectificacion = datetime.now
                                no_manifestados.No_Contenedor = no_contenedor
                                no_manifestados.save()
                            hbl_no_manifestados.append(hbl)
            messages.success(request, 'Manifiesto rectificado satisfactoriamente')
            # return redirect('inventario_rectificar')
    hbl_list = HBL_No_Manifestados.objects.filter(HBL__in=hbl_no_manifestados)  
    ctx = {'form':form,'hbl_no_manifestados':hbl_list}
    return render(request, 'inventario/inventario_verify_inventory_new.html', ctx)

@login_required(login_url='login')
def inventario_no_existente_list(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Formulario de tabla
    # form_trasladar_almacen = Operacion_Trasladar_De_Almacen_Form()
    # form_nacionalizar_carga   = Operacion_Nacionalizar_Inventario_Form()
    form_verificar_existencia = Verify_Inventory_Form()
    #Ejecutando operaciones de las tablas
    operaciones_de_tablas(request)   

    #Informacion para el template
    header_text     = 'Inventarios no manifestados'
    breadcrumb_text = 'Inventarios no manifestados'
    #Definiendo menu activo
    active_menu = 'mercancia_inventario'

    inventarios = HBL_No_Manifestados.objects.all().order_by('HBL')

    #Aplicacion de filtros
    no_manifestados_filter = HBL_No_Manifestados_Filter(request.GET, queryset=inventarios)
    inventarios = no_manifestados_filter.qs

    #Paginator
    paginator = Paginator(inventarios, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj, 'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'no_manifestados_filter': no_manifestados_filter, 'form_verificar_existencia': form_verificar_existencia}
    return render(request, 'inventario/inventario_reporte_no_manifestados.html', ctx)

@login_required(login_url='login')
def inventario_incidencias(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Formulario de tabla
    form_trasladar_almacen = Operacion_Trasladar_De_Almacen_Form()
    form_nacionalizar_carga   = Operacion_Nacionalizar_Inventario_Form()

    #Ejecutando operaciones de las tablas
    operaciones_de_tablas(request)   
    #Informacion para el template
    header_text     = 'Inventarios con incidencias'
    breadcrumb_text = 'Inventarios con incidencias'
    #Definiendo menu activo
    active_menu = 'mercancia_inventario_incidencias'

    inventarios = Inventario.objects.all().filter(Q(Estado = 'Inventario'), Q(Incidencia__isnull = False)).order_by('HBL')

    #Aplicacion de filtros
    inventario_filter = InventarioFilter(request.GET, queryset=inventarios)
    inventarios = inventario_filter.qs

    #Paginator
    paginator = Paginator(inventarios, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj, 'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'form_trasladar_almacen': form_trasladar_almacen, 'inventario_filter': inventario_filter, 'form_nacionalizar_carga': form_nacionalizar_carga}
    return render(request, 'inventario/inventario_list.html', ctx)

@login_required(login_url='login')
def cargas_traslado_mayor_cinco_dias(request):
    
    inventarios = Inventario.objects.filter(Estado='Traslado')
    fecha_actual = datetime.now().date()
    list_id=[]
    for inv in inventarios:
        fecha_traslado = getattr(inv,'Fecha_Traslado')
        if fecha_traslado:
            diferencia = fecha_actual - fecha_traslado
            if diferencia.days > 4:
                list_id.append(inv.id)
    inventarios=inventarios.filter(id__in=list_id)

    header_text     = 'Traslados mayores de 5 días '
    breadcrumb_text = 'Inventario'

    #Definiendo menu activo
    active_menu = 'reporte_inventario_cargas_traslado_mayor_cinco_dias'

    #Aplicacion de filtros
    inventario_filter = InventarioFilter(request.GET, queryset=inventarios)
    inventarios = inventario_filter.qs

    #Paginator
    paginator = Paginator(inventarios, 100) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj,'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'inventario_filter': inventario_filter,'inventario':inventarios}

    return render(request, 'reportes/reporte_traslados_tiempo_prolongado.html', ctx,)

@login_required(login_url='login')
def inventario_trasbordo(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Formulario de tabla
    form_trasladar_almacen = Operacion_Trasladar_De_Almacen_Form()
    form_nacionalizar_carga   = Operacion_Nacionalizar_Inventario_Form()

    #Ejecutando operaciones de las tablas
    operaciones_de_tablas(request)   
    #Informacion para el template
    header_text     = 'Inventarios trasbordados'
    breadcrumb_text = 'Inventarios trasbordados'
    #Definiendo menu activo
    active_menu = 'mercancia_trasbordo'

    inventarios = Inventario.objects.all().filter(Q(Estado = 'Inventario'), Q(trasbordo = True)).order_by('HBL')

    #Aplicacion de filtros
    inventario_filter = InventarioFilter(request.GET, queryset=inventarios)
    inventarios = inventario_filter.qs

    #Paginator
    paginator = Paginator(inventarios, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj, 'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'form_trasladar_almacen': form_trasladar_almacen, 'inventario_filter': inventario_filter, 'form_nacionalizar_carga': form_nacionalizar_carga}
    return render(request, 'inventario/inventario_list.html', ctx)

@login_required(login_url='login')
def cargas_canal_rojo(request):
    inventarios = Inventario.objects.filter(canal_rojo=True)
    

    header_text     = 'Inventarios en canal rojo'
    breadcrumb_text = 'Inventarios en canal rojo'

    #Definiendo menu activo
    active_menu = 'canal_rojo'

    #Aplicacion de filtros
    inventario_filter = InventarioFilter(request.GET, queryset=inventarios)
    inventarios = inventario_filter.qs

    #Paginator
    paginator = Paginator(inventarios, 100) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj,'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'inventario_filter': inventario_filter,'inventario':inventarios}

    return render(request, 'inventario/inventario_list.html', ctx,)

@login_required(login_url='login')
def reporte_parte_diario(request):

    #Definiendo menu activo
    active_menu = 'parte_diario'
    header_text = 'Parte diario'
    breadcrumb_text = 'Parte diario'
    #Info de listado
    data = []
    data_habana = []
    valores_totales = {}
    #Filtro de fechas
    inventario_filter = Reporte_Contable_Aduana_Form()
     #Captura de fechas
    if request.method == 'POST':
        form = Reporte_Contable_Aduana_Form(request.POST)
        if form.is_valid():
            fecha_desde = datetime.strptime(str(form.cleaned_data.get('Fecha_Desde')), '%Y-%m-%d')
            fecha_hasta = datetime.strptime(str(form.cleaned_data.get('Fecha_Hasta')), '%Y-%m-%d')
            provincias = Provincia.objects.all()
            valores_totales['total_entregado_provincia'] = 0
            valores_totales['total_cantidad_clientes_provincia'] = 0
            valores_totales['total_miscelaneas_provincia'] = 0
            valores_totales['total_entregado_habana_ena'] = 0
            valores_totales['total_cantidad_clientes_ena'] = 0
            valores_totales['total_entregado_habana'] = 0
            valores_totales['total_cantidad_clientes_habana'] = 0
            valores_totales['total_miscelaneas_habana'] = 0
            valores_totales['total_entregado_ena_provincia'] = 0
            valores_totales['total_cantidad_clientes_ena_provincia'] = 0
            valores_totales['total_cantidad_bultos'] = 0
            valores_totales['total_cantidad_clientes'] = 0
            valores_totales['total_cantidad_ena'] = 0
            valores_totales['total_cantidad_ena_clientes'] = 0
            valores_totales['total_bultos'] = 0
            valores_totales['total_clientes'] = 0
            for provincia in provincias:
                dicto = {}
                dicto['Provincia_Entrega__Nombre']=provincia.Nombre
                #Tipo Envio
                ena_list=['ENA','E.N.A','ena','e.n.a','Ena','Menaje','MENAJE']
                envio_list=['Envío','envío','ENVIO','Menaje','MENAJE']

                dicto['Cantidad_Bultos_Entregados'] = Inventario.objects.filter(Provincia_Entrega=provincia.id,Estado='Entregado',Fecha_Entrega__gte=fecha_desde,Fecha_Entrega__lte=fecha_hasta).exclude(Categoria_Operacion__in=ena_list).aggregate(Sum('Cantidad_Bultos'))
                dicto['Cantidad_Cantidad_Clientes_Bultos_Entregados'] = Inventario.objects.filter(Provincia_Entrega=provincia.id,Estado='Entregado',Fecha_Entrega__gte=fecha_desde,Fecha_Entrega__lte=fecha_hasta).values('Destinatario').distinct().exclude(Categoria_Operacion__in=ena_list).count()
                dicto['Cantidad_Cantidad_Miscelaneas_Entregados'] = Inventario.objects.filter(Provincia_Entrega=provincia.id,Estado='Entregado',Fecha_Entrega__gte=fecha_desde,Fecha_Entrega__lte=fecha_hasta,Contenido__icontains='MISCELANEAS').exclude(Categoria_Operacion__in=ena_list).count()
                dicto['Cantidad_Bultos_Entregados_ENA'] = Inventario.objects.filter(Provincia_Entrega=provincia.id,Estado='Entregado',Fecha_Entrega__gte=fecha_desde,Fecha_Entrega__lte=fecha_hasta).exclude(Categoria_Operacion__in=envio_list).aggregate(Sum('Cantidad_Bultos'))
                dicto['Cantidad_Cantidad_Clientes_Bultos_Entregados_ENA'] = Inventario.objects.filter(Provincia_Entrega=provincia.id,Estado='Entregado',Fecha_Entrega__gte=fecha_desde,Fecha_Entrega__lte=fecha_hasta).values('Destinatario').distinct().exclude(Categoria_Operacion__in=envio_list).count()

                data.append(dicto)
                #Valores totales
                if dicto['Cantidad_Bultos_Entregados']['Cantidad_Bultos__sum']:
                    valores_totales['total_entregado_provincia'] += dicto['Cantidad_Bultos_Entregados']['Cantidad_Bultos__sum']
                if dicto['Cantidad_Cantidad_Clientes_Bultos_Entregados']:
                    valores_totales['total_cantidad_clientes_provincia'] += dicto['Cantidad_Cantidad_Clientes_Bultos_Entregados']
                if dicto['Cantidad_Cantidad_Miscelaneas_Entregados']:
                    valores_totales['total_miscelaneas_provincia'] += dicto['Cantidad_Cantidad_Miscelaneas_Entregados']
                if dicto['Cantidad_Bultos_Entregados_ENA']['Cantidad_Bultos__sum']:
                    valores_totales['total_entregado_ena_provincia'] += dicto['Cantidad_Bultos_Entregados_ENA']['Cantidad_Bultos__sum']
                if dicto['Cantidad_Cantidad_Clientes_Bultos_Entregados_ENA']:
                    valores_totales['total_cantidad_clientes_ena_provincia'] += dicto['Cantidad_Cantidad_Clientes_Bultos_Entregados_ENA']

            #Entregas en la Habana por municipio
            municipios = Municipio.objects.filter(Provincia__Nombre='La Habana')
            for municipio in municipios:
                dicto_habana = {}
                # Tipo ENA
                envio_list=['Envío','envío','ENVIO','Menaje','MENAJE']
                ena_list=['ENA','E.N.A','ena','e.n.a','Ena','Menaje','MENAJE']

                dicto_habana['Municipio']=municipio.Nombre
                dicto_habana['Cantidad_Bultos_Entregados_ENA'] = Inventario.objects.filter(Municipio_Entrega=municipio.id,Estado='Entregado',Fecha_Entrega__gte=fecha_desde,Fecha_Entrega__lte=fecha_hasta).exclude(Categoria_Operacion__in=envio_list).aggregate(Sum('Cantidad_Bultos'))
                dicto_habana['Cantidad_Cantidad_Clientes_Bultos_Entregados_ENA'] = Inventario.objects.filter(Municipio_Entrega=municipio.id,Estado='Entregado',Fecha_Entrega__gte=fecha_desde,Fecha_Entrega__lte=fecha_hasta).values('Destinatario').distinct().exclude(Categoria_Operacion__in=envio_list).count()
                dicto_habana['Cantidad_Bultos_Entregados'] = Inventario.objects.filter(Municipio_Entrega=municipio.id,Estado='Entregado',Fecha_Entrega__gte=fecha_desde,Fecha_Entrega__lte=fecha_hasta).exclude(Categoria_Operacion__in=ena_list).aggregate(Sum('Cantidad_Bultos'))
                dicto_habana['Cantidad_Cantidad_Clientes_Bultos_Entregados'] = Inventario.objects.filter(Municipio_Entrega=municipio.id,Estado='Entregado',Fecha_Entrega__gte=fecha_desde,Fecha_Entrega__lte=fecha_hasta).values('Destinatario').distinct().exclude(Categoria_Operacion__in=ena_list).count()
                dicto_habana['Cantidad_Cantidad_Miscelaneas_Entregados'] = Inventario.objects.filter(Municipio_Entrega=municipio.id,Estado='Entregado',Fecha_Entrega__gte=fecha_desde,Fecha_Entrega__lte=fecha_hasta,Contenido__icontains='MISCELANEAS').exclude(Categoria_Operacion__in=ena_list).count()
                data_habana.append(dicto_habana)

                if dicto_habana['Cantidad_Bultos_Entregados_ENA']['Cantidad_Bultos__sum']:
                    valores_totales['total_entregado_habana_ena'] += dicto_habana['Cantidad_Bultos_Entregados_ENA']['Cantidad_Bultos__sum']
                if dicto_habana['Cantidad_Cantidad_Clientes_Bultos_Entregados_ENA']:
                    valores_totales['total_cantidad_clientes_ena'] += dicto_habana['Cantidad_Cantidad_Clientes_Bultos_Entregados_ENA']
                if dicto_habana['Cantidad_Bultos_Entregados']['Cantidad_Bultos__sum']:
                    valores_totales['total_entregado_habana'] += dicto_habana['Cantidad_Bultos_Entregados']['Cantidad_Bultos__sum']
                if dicto_habana['Cantidad_Cantidad_Clientes_Bultos_Entregados']:
                    valores_totales['total_cantidad_clientes_habana'] += dicto_habana['Cantidad_Cantidad_Clientes_Bultos_Entregados']
                if dicto_habana['Cantidad_Cantidad_Miscelaneas_Entregados']:
                    valores_totales['total_miscelaneas_habana'] += dicto_habana['Cantidad_Cantidad_Miscelaneas_Entregados']
            valores_totales['total_cantidad_bultos'] = valores_totales['total_entregado_habana'] + valores_totales['total_entregado_provincia']
            valores_totales['total_cantidad_clientes'] = valores_totales['total_cantidad_clientes_habana'] + valores_totales['total_cantidad_clientes_provincia']
            valores_totales['total_cantidad_ena'] = valores_totales['total_entregado_habana_ena'] + valores_totales['total_entregado_ena_provincia']
            valores_totales['total_cantidad_ena_clientes'] = valores_totales['total_cantidad_clientes_ena'] + valores_totales['total_cantidad_clientes_ena_provincia']
            valores_totales['total_bultos'] = valores_totales['total_entregado_habana_ena'] + valores_totales['total_entregado_habana'] + valores_totales['total_entregado_provincia'] + valores_totales['total_entregado_ena_provincia']      
            valores_totales['total_clientes'] = valores_totales['total_cantidad_clientes_provincia'] + valores_totales['total_cantidad_clientes_ena_provincia'] + valores_totales['total_cantidad_clientes_ena'] + valores_totales['total_cantidad_clientes_habana']         
            
    ctx = {'active_menu': active_menu, 'inventario_filter': inventario_filter,'inventario_provincia':data,'valores_totales':valores_totales,'inventario_habana':data_habana}
    return render(request, 'reportes/reporte_parte_diario.html', ctx)

@login_required(login_url='login')
def reporte_parte_operativo(request):

    #Definiendo menu activo
    active_menu = 'parte_operativo'
    header_text = 'Parte operativo'
    breadcrumb_text = 'Parte operativo'
    #Info de listado
    data = []
    data_devoluciones=[]
    data_nacionalizaciones=[]
    data_entregas=[]
    data_prox_distribucion=[]
    data_fuerza_trabajo=[]
    fuerza_trabajo={}

    valores_totales = {}
    #Filtro de fechas
    inventario_filter = Reporte_Diario_Form()
     #Captura de fechas
    if request.method == 'POST':
        form = Reporte_Diario_Form(request.POST)
        if form.is_valid():
            fecha_desde = datetime.strptime(str(form.cleaned_data.get('Fecha_Desde')), '%Y-%m-%d')
            fecha_hasta = datetime.strptime(str(form.cleaned_data.get('Fecha_Hasta')), '%Y-%m-%d')
            almacen = Almacen.objects.get(pk = request.POST.get('Almacen')) 
            cantidad_montacargas = request.POST.get('Montacargas')
            cantidad_posiciones_aduana = request.POST.get('Posiciones_Aduana')
            cantidad_facturadores = request.POST.get('Facturadores') 
            fuerza_trabajo['Brigada']=almacen
            fuerza_trabajo['Montacargas']=cantidad_montacargas
            fuerza_trabajo['Posiciones_Aduana']=cantidad_posiciones_aduana
            fuerza_trabajo['Facturadores']=cantidad_facturadores
            data_fuerza_trabajo.append(fuerza_trabajo)

            #Entrada de mercancías
            entrada = Inventario.objects.filter(Fecha_Entrada__gte=fecha_desde,Fecha_Entrada__lte=fecha_hasta,Almacen=almacen)
            
            #Obteniendo el listado de contenedores
            list_entrada_contenedores = []
            contenedores = {}
            for inventario in entrada:
                contenedores['Contenedor']=inventario.No_Contenedor
                contenedores['Manifiesto']=inventario.Manifiesto
                if not contenedores in list_entrada_contenedores:
                    list_entrada_contenedores.append(contenedores)
            for entrada in list_entrada_contenedores:
                dicto_entrada = {}
                dicto_entrada['Contenedor']=entrada['Contenedor']
                dicto_entrada['Manifiesto']=entrada['Manifiesto']
                dicto_entrada['Total_Bultos']=Inventario.objects.filter(No_Contenedor=entrada['Contenedor'],Manifiesto=entrada['Manifiesto']).aggregate(Sum('Cantidad_Bultos'))
                dicto_entrada['Total_Bultos']=dicto_entrada['Total_Bultos']['Cantidad_Bultos__sum']
                dicto_entrada['Total_HBL']=Inventario.objects.filter(No_Contenedor=entrada['Contenedor'],Manifiesto=entrada['Manifiesto']).values('HBL').distinct().count()
                data.append(dicto_entrada)

            #Mercancías devueltas
            
            devoluciones = Inventario_Reincorporado.objects.filter(Fecha__gte=fecha_desde,Fecha__lte=fecha_hasta,Inventario__Almacen=almacen).values('')
            
            for current_devolucion in devoluciones:
                dicto_devolucion = {}
                entrega = Entrega.objects.get(Factura_Operador=current_devolucion.Factura_Operador)
                dicto_devolucion['Vehiculo']=entrega.Transportista.Chapa
                dicto_devolucion['No_Factura_Operador']=current_devolucion.Factura_Operador.id
                dicto_devolucion['HBL']=current_devolucion.Inventario.HBL
                dicto_devolucion['Cantidad_Bultos']=current_devolucion.Inventario.Cantidad_Bultos
                data_devoluciones.append(dicto_devolucion)

            #Mercancías nacionalizadas por aduana
            ena_list=['ENA','E.N.A','ena','e.n.a','Ena','Menaje','MENAJE']
            envio_list=['Envío','envío','ENVIO','Menaje','MENAJE']
            dicto_nacionalizacion = {}
            dicto_nacionalizacion['Cantidad_HBL']= Inventario.objects.filter(Fecha_Nacionalizacion__gte=fecha_desde,Fecha_Nacionalizacion__lte=fecha_hasta,Almacen=almacen).values('HBL').distinct().count()
            dicto_nacionalizacion['Cantidad_Clientes']= Inventario.objects.filter(Fecha_Nacionalizacion__gte=fecha_desde,Fecha_Nacionalizacion__lte=fecha_hasta,Almacen=almacen).values('Destinatario').distinct().count()
            dicto_nacionalizacion['Cantidad_Bultos']= Inventario.objects.filter(Fecha_Nacionalizacion__gte=fecha_desde,Fecha_Nacionalizacion__lte=fecha_hasta,Almacen=almacen).aggregate(Sum('Cantidad_Bultos'))
            dicto_nacionalizacion['Cantidad_Bultos']=dicto_nacionalizacion['Cantidad_Bultos']['Cantidad_Bultos__sum']
            dicto_nacionalizacion['Cantidad_Envios']=Inventario.objects.filter(Fecha_Nacionalizacion__gte=fecha_desde,Fecha_Nacionalizacion__lte=fecha_hasta,Almacen=almacen).exclude(Categoria_Operacion__in=ena_list).aggregate(Sum('Cantidad_Bultos'))
            dicto_nacionalizacion['Cantidad_Envios']=dicto_nacionalizacion['Cantidad_Envios']['Cantidad_Bultos__sum']
            dicto_nacionalizacion['Cantidad_ENA']=Inventario.objects.filter(Fecha_Nacionalizacion__gte=fecha_desde,Fecha_Nacionalizacion__lte=fecha_hasta,Almacen=almacen).exclude(Categoria_Operacion__in=envio_list).aggregate(Sum('Cantidad_Bultos'))
            dicto_nacionalizacion['Cantidad_ENA']=dicto_nacionalizacion['Cantidad_ENA']['Cantidad_Bultos__sum']
            data_nacionalizaciones.append(dicto_nacionalizacion)

            #Mercancias entregadas
            traslados_concluidos= Entrega.objects.filter(Estado='Concluido')
            for traslado in traslados_concluidos:
                destinos=[]
                dicto_traslado={}
                dicto_traslado['Cantidad_Bultos']=0
                dicto_traslado['Cantidad_HBL']=0
                factura_operador=Factura_Operador.objects.get(id=traslado.Factura_Operador.id)
                dicto_traslado['Operador']=factura_operador.Operador.Nombre
                dicto_traslado['Transportista']=traslado.Transportista
                # print('factura_operador.Facturas_Destinatarios',factura_operador.id)
                facturas_id = Factura_Operador.objects.filter(id=traslado.Factura_Operador.id).values('Facturas_Destinatarios__id')
                # print('id facturas',facturas_id)
                facturas=Factura.objects.filter(id__in=facturas_id)
                
                #Recorro facturas en el traslado
                for factura_destinatario in facturas:
                    #Obtengo cantidad de HBL
                    dicto_traslado['Cantidad_HBL'] += Factura.objects.filter(id=factura_destinatario.id).values('Inventario__id').count()
                    
                    #Obtengo cantidad de bultos
                    inventarios_id = Factura.objects.filter(id=factura_destinatario.id).values('Inventario__id')
                    inventarios = Inventario.objects.filter(id__in=inventarios_id,Almacen=almacen)
                    for inventario in inventarios:
                        dicto_traslado['Cantidad_Bultos'] += inventario.Cantidad_Bultos
                        #Obtengo destinos de entrega
                        destinos.append(inventario.Destinatario.Provincia.Nombre)
                destinos=set(destinos)        
                dicto_traslado['Destinos'] = destinos
                data_entregas.append(dicto_traslado)

            #Mercancias Listas para distribucion
            destinos_prox_distribucion=[]
            dicto_pendientes_distribucion = {}
            dicto_pendientes_distribucion['Cantidad_HBL']= Inventario.objects.filter(Fecha_Nacionalizacion__gte=fecha_desde,Fecha_Nacionalizacion__lte=fecha_hasta,Estado='Inventario',Almacen=almacen).values('HBL').distinct().count()
            dicto_pendientes_distribucion['Cantidad_Bultos']= Inventario.objects.filter(Fecha_Nacionalizacion__gte=fecha_desde,Fecha_Nacionalizacion__lte=fecha_hasta,Estado='Inventario',Almacen=almacen).aggregate(Sum('Cantidad_Bultos'))
            dicto_pendientes_distribucion['Cantidad_Bultos']=dicto_pendientes_distribucion['Cantidad_Bultos']['Cantidad_Bultos__sum']
            dicto_pendientes_distribucion['Cantidad_M3']= Inventario.objects.filter(Fecha_Nacionalizacion__gte=fecha_desde,Fecha_Nacionalizacion__lte=fecha_hasta,Estado='Inventario',Almacen=almacen).aggregate(Sum('Volumen'))
            dicto_pendientes_distribucion['Cantidad_M3']=dicto_pendientes_distribucion['Cantidad_M3']['Volumen__sum']
            
            destinos_prox_distribucion=Inventario.objects.filter(Fecha_Nacionalizacion__gte=fecha_desde,Fecha_Nacionalizacion__lte=fecha_hasta,Estado='Inventario',Almacen=almacen)
            destinos=[]
            for destino in destinos_prox_distribucion:
                destinos.append(destino.Destinatario.Provincia.Nombre)
            destinos=set(destinos)
            dicto_pendientes_distribucion['Destinos'] = destinos
            data_prox_distribucion.append(dicto_pendientes_distribucion)

    ctx = {'active_menu': active_menu, 'inventario_filter': inventario_filter,'valores_totales':valores_totales,'entradas':data,'devoluciones':data_devoluciones,'nacionalizaciones':data_nacionalizaciones,'entregas':data_entregas,'prox_distribucion':data_prox_distribucion,'fuerza_trabajo':fuerza_trabajo}
    return render(request, 'reportes/reporte_operativo.html', ctx)

@login_required(login_url='login')
def reporte_desempeno(request):
    #Definiendo menu activo
    active_menu = 'reporte_desempeno'
    header_text = 'Reporte de desempeño'
    breadcrumb_text = 'Reporte de desempeño'
    #Info de listado
    data = []
    
    #Valores totales del reporte
    valores_totales={}
    valores_totales['cantidad_bultos_menor_1_5_kg'] = 0
    valores_totales['pago_cantidad_bultos_menor_1_5_kg'] = 0
    valores_totales['cantidad_bultos_hasta_30_kg'] = 0
    valores_totales['pago_cantidad_bultos_hasta_30_kg'] = 0
    valores_totales['cantidad_bultos_hasta_100_kg'] = 0
    valores_totales['pago_cantidad_bultos_hasta_100_kg'] = 0
    valores_totales['cantidad_bultos_mayor_100_kg'] = 0
    valores_totales['pago_cantidad_bultos_mayor_100_kg'] = 0
    valores_totales['pago_total'] = 0
    #Filtro de fechas
    form_reporte_diario = Reporte_Diario_Form()
     #Captura de fechas
    if request.method == 'POST':
        if request.POST.get('Fecha_Desde') and request.POST.get('Fecha_Hasta') and request.POST.get('Almacen'):

            form = Reporte_Diario_Form(request.POST)
            if form.is_valid():
                #Obteniendo datos de formulario
                fecha_desde = datetime.strptime(str(form.cleaned_data.get('Fecha_Desde')), '%Y-%m-%d')
                fecha_hasta = form.cleaned_data.get('Fecha_Hasta')
                almacen = Almacen.objects.get(pk = request.POST.get('Almacen'))

                for current_date in range(fecha_desde.timetuple().tm_yday, fecha_hasta.timetuple().tm_yday + 1):
                    #Diccionario
                    bultos_despachados = {}
                    # Initializing start date
                    strt_date = date(int(fecha_desde.year), 1, 1)
                    # converting to date
                    res_date = strt_date + timedelta(days=int(current_date) - 1)
                    fecha = res_date
                    
                    #Valores de cada fila
                    bultos_despachados['fecha']=fecha
                    bultos_despachados['almacen']=almacen
                    bultos_despachados['cantidad_bultos_menor_1_5_kg']=0
                    bultos_despachados['cantidad_bultos_hasta_30_kg']=0
                    bultos_despachados['cantidad_bultos_hasta_100_kg']=0
                    bultos_despachados['cantidad_bultos_mayor_100_kg']=0
                    bultos_despachados['pago_cantidad_bultos_menor_1_5_kg']=0
                    bultos_despachados['pago_cantidad_bultos_hasta_30_kg']=0
                    bultos_despachados['pago_cantidad_bultos_hasta_100_kg']=0
                    bultos_despachados['pago_cantidad_bultos_mayor_100_kg']=0
                    
                    
                    cantidad_bultos_menor_1_5_kg = Inventario.objects.filter(Q(Fecha_Traslado__year=fecha.year),Q(Fecha_Traslado__month=fecha.month), Q(Fecha_Traslado__day = fecha.day),Almacen=almacen,Estado='Traslado',Peso__lte='1.5').aggregate(Sum('Cantidad_Bultos'))
                    cantidad_bultos_hasta_30_kg = Inventario.objects.filter(Q(Fecha_Traslado__year=fecha.year),Q(Fecha_Traslado__month=fecha.month), Q(Fecha_Traslado__day = fecha.day),Almacen=almacen,Estado='Traslado',Peso__gt='1.5',Peso__lte='30').aggregate(Sum('Cantidad_Bultos'))
                    cantidad_bultos_hasta_100_kg = Inventario.objects.filter(Q(Fecha_Traslado__year=fecha.year),Q(Fecha_Traslado__month=fecha.month), Q(Fecha_Traslado__day = fecha.day),Almacen=almacen,Estado='Traslado',Peso__gt='30',Peso__lte='100').aggregate(Sum('Cantidad_Bultos'))
                    cantidad_bultos_mayor_100_kg = Inventario.objects.filter(Q(Fecha_Traslado__year=fecha.year),Q(Fecha_Traslado__month=fecha.month), Q(Fecha_Traslado__day = fecha.day),Almacen=almacen,Estado='Traslado',Peso__gt='100').aggregate(Sum('Cantidad_Bultos'))
                                        
                    if cantidad_bultos_menor_1_5_kg['Cantidad_Bultos__sum']:
                        bultos_despachados['cantidad_bultos_menor_1_5_kg']=cantidad_bultos_menor_1_5_kg['Cantidad_Bultos__sum']
                        bultos_despachados['pago_cantidad_bultos_menor_1_5_kg']=cantidad_bultos_menor_1_5_kg['Cantidad_Bultos__sum'] * 3
                    if cantidad_bultos_hasta_30_kg['Cantidad_Bultos__sum']:
                        bultos_despachados['cantidad_bultos_hasta_30_kg']= cantidad_bultos_hasta_30_kg['Cantidad_Bultos__sum']
                        bultos_despachados['pago_cantidad_bultos_hasta_30_kg']= cantidad_bultos_hasta_30_kg['Cantidad_Bultos__sum'] * 5
                    if cantidad_bultos_hasta_100_kg['Cantidad_Bultos__sum']:            
                        bultos_despachados['cantidad_bultos_hasta_100_kg']=cantidad_bultos_hasta_100_kg['Cantidad_Bultos__sum']
                        bultos_despachados['pago_cantidad_bultos_hasta_100_kg']=cantidad_bultos_hasta_100_kg['Cantidad_Bultos__sum'] * 10
                    if cantidad_bultos_mayor_100_kg['Cantidad_Bultos__sum']:            
                        bultos_despachados['cantidad_bultos_mayor_100_kg']=cantidad_bultos_mayor_100_kg['Cantidad_Bultos__sum']
                        bultos_despachados['pago_cantidad_bultos_mayor_100_kg']=cantidad_bultos_mayor_100_kg['Cantidad_Bultos__sum'] * 20
                   
                    data.append(bultos_despachados)
                    valores_totales['cantidad_bultos_menor_1_5_kg']+= bultos_despachados['cantidad_bultos_menor_1_5_kg']
                    valores_totales['pago_cantidad_bultos_menor_1_5_kg']+= bultos_despachados['pago_cantidad_bultos_menor_1_5_kg']
                    valores_totales['cantidad_bultos_hasta_30_kg']+= bultos_despachados['cantidad_bultos_hasta_30_kg']
                    valores_totales['pago_cantidad_bultos_hasta_30_kg']+= bultos_despachados['pago_cantidad_bultos_hasta_30_kg']
                    valores_totales['cantidad_bultos_hasta_100_kg']+= bultos_despachados['cantidad_bultos_hasta_100_kg']
                    valores_totales['pago_cantidad_bultos_hasta_100_kg']+= bultos_despachados['pago_cantidad_bultos_hasta_100_kg']
                    valores_totales['cantidad_bultos_mayor_100_kg']+= bultos_despachados['cantidad_bultos_mayor_100_kg']
                    valores_totales['pago_cantidad_bultos_mayor_100_kg']+= bultos_despachados['pago_cantidad_bultos_mayor_100_kg']
            valores_totales['bultos_total']=valores_totales['cantidad_bultos_menor_1_5_kg'] + valores_totales['cantidad_bultos_hasta_30_kg'] + valores_totales['cantidad_bultos_hasta_100_kg'] + valores_totales['cantidad_bultos_mayor_100_kg']
            valores_totales['pago_total']=valores_totales['pago_cantidad_bultos_menor_1_5_kg'] + valores_totales['pago_cantidad_bultos_hasta_30_kg'] + valores_totales['pago_cantidad_bultos_hasta_100_kg'] + valores_totales['pago_cantidad_bultos_mayor_100_kg']
        else:
            messages.error(request, 'Debe ingresar los datos requeridos.')
            
    ctx = {'active_menu': active_menu,'bultos_despachados':data,'form':form_reporte_diario,'valores_totales':valores_totales}
    return render(request, 'reportes/reporte_trabajo_diario.html', ctx)       

@login_required(login_url='login')
def reporte_cargas_transportistas(request):
    #Definiendo menu activo
    active_menu = 'reporte_transportistas'
    header_text = 'Reporte de cargas por transportistas'
    breadcrumb_text = 'Reporte de cargas por transportistas'   

    #Filtro de fechas
    form_reporte_diario = Reporte_Transportistas_Form()
    transportistas = []
    fecha_desde = None
    fecha_hasta = None
    
    if request.method == 'POST':
        if request.POST.get('Fecha_Desde') and request.POST.get('Fecha_Hasta'):
            try:
                #Obteniendo datos de formulario
                fecha_desde = datetime.strptime(str(request.POST.get('Fecha_Desde')), '%Y-%m-%d')
                fecha_hasta = datetime.strptime(str(request.POST.get('Fecha_Hasta')), '%Y-%m-%d')
                empresa = None
                current_transportista = None
                
                if request.POST.get('Empresa'):
                    empresa = Empresa.objects.get(pk = request.POST.get('Empresa'))

                if request.POST.get('Transportista'):
                    current_transportista = Transportista.objects.get(pk = request.POST.get('Transportista'))

                with connection.cursor() as cursor:
                    if not empresa and not current_transportista:
                        cursor.execute(""" SELECT 
                                inventario_transportista."Nombre",
                                inventario_transportista."Chapa",
                                inventario_transportista."Empresa",
                                SUM (inventario_factura."Cantidad_Bultos_Total"),
                                inventario_provincia."Nombre"
                            FROM
                                inventario_entrega
                                INNER JOIN inventario_transportista ON (inventario_entrega."Transportista_id" = inventario_transportista.id)
                                INNER JOIN inventario_factura_operador ON (inventario_entrega."Factura_Operador_id" = inventario_factura_operador.id)
                                INNER JOIN "inventario_factura_operador_Facturas_Destinatarios" ON (inventario_factura_operador.id = "inventario_factura_operador_Facturas_Destinatarios".factura_operador_id)
                                INNER JOIN inventario_factura ON ("inventario_factura_operador_Facturas_Destinatarios".factura_id = inventario_factura.id)
                                INNER JOIN inventario_destinatario ON (inventario_factura."Destinatario_id" = inventario_destinatario.id)
                                INNER JOIN inventario_provincia ON (inventario_destinatario."Provincia_id" = inventario_provincia.id)
                            WHERE inventario_entrega."Estado" != 'Cancelado' AND inventario_entrega."Fecha_Entrega" >= '%s' AND inventario_entrega."Fecha_Entrega" <= '%s'
                            GROUP BY inventario_transportista."Nombre",inventario_transportista."Empresa",inventario_transportista."Chapa", inventario_provincia."Nombre"
                                """%(fecha_desde, fecha_hasta))

                    if empresa and not current_transportista: 
                        cursor.execute(""" SELECT 
                                inventario_transportista."Nombre",
                                inventario_transportista."Chapa",
                                inventario_transportista."Empresa",
                                SUM (inventario_factura."Cantidad_Bultos_Total"),
                                inventario_provincia."Nombre"
                            FROM
                                inventario_entrega
                                INNER JOIN inventario_transportista ON (inventario_entrega."Transportista_id" = inventario_transportista.id)
                                INNER JOIN inventario_factura_operador ON (inventario_entrega."Factura_Operador_id" = inventario_factura_operador.id)
                                INNER JOIN "inventario_factura_operador_Facturas_Destinatarios" ON (inventario_factura_operador.id = "inventario_factura_operador_Facturas_Destinatarios".factura_operador_id)
                                INNER JOIN inventario_factura ON ("inventario_factura_operador_Facturas_Destinatarios".factura_id = inventario_factura.id)
                                INNER JOIN inventario_destinatario ON (inventario_factura."Destinatario_id" = inventario_destinatario.id)
                                INNER JOIN inventario_provincia ON (inventario_destinatario."Provincia_id" = inventario_provincia.id)
                            WHERE inventario_entrega."Estado" != 'Cancelado' AND inventario_entrega."Fecha_Entrega" >= '%s' AND inventario_entrega."Fecha_Entrega" <= '%s'  AND inventario_transportista."Empresa"= '%s'
                            GROUP BY inventario_transportista."Nombre",inventario_transportista."Empresa",inventario_transportista."Chapa", inventario_provincia."Nombre"
                                """%(fecha_desde, fecha_hasta, empresa.Nombre))
                    
                    if not empresa and current_transportista: 
                        cursor.execute(""" SELECT 
                                inventario_transportista."Nombre",
                                inventario_transportista."Chapa",
                                inventario_transportista."Empresa",
                                SUM (inventario_factura."Cantidad_Bultos_Total"),
                                inventario_provincia."Nombre"
                            FROM
                                inventario_entrega
                                INNER JOIN inventario_transportista ON (inventario_entrega."Transportista_id" = inventario_transportista.id)
                                INNER JOIN inventario_factura_operador ON (inventario_entrega."Factura_Operador_id" = inventario_factura_operador.id)
                                INNER JOIN "inventario_factura_operador_Facturas_Destinatarios" ON (inventario_factura_operador.id = "inventario_factura_operador_Facturas_Destinatarios".factura_operador_id)
                                INNER JOIN inventario_factura ON ("inventario_factura_operador_Facturas_Destinatarios".factura_id = inventario_factura.id)
                                INNER JOIN inventario_destinatario ON (inventario_factura."Destinatario_id" = inventario_destinatario.id)
                                INNER JOIN inventario_provincia ON (inventario_destinatario."Provincia_id" = inventario_provincia.id)
                            WHERE inventario_entrega."Estado" != 'Cancelado' AND inventario_entrega."Fecha_Entrega" >= '%s' AND inventario_entrega."Fecha_Entrega" <= '%s'  AND inventario_transportista."id"= %s
                            GROUP BY inventario_transportista."Nombre",inventario_transportista."Empresa",inventario_transportista."Chapa", inventario_provincia."Nombre"
                                """%(fecha_desde, fecha_hasta, current_transportista.id))
                    
                    if empresa and current_transportista: 
                        cursor.execute(""" SELECT 
                                inventario_transportista."Nombre",
                                inventario_transportista."Chapa",
                                inventario_transportista."Empresa",
                                SUM (inventario_factura."Cantidad_Bultos_Total"),
                                inventario_provincia."Nombre"
                            FROM
                                inventario_entrega
                                INNER JOIN inventario_transportista ON (inventario_entrega."Transportista_id" = inventario_transportista.id)
                                INNER JOIN inventario_factura_operador ON (inventario_entrega."Factura_Operador_id" = inventario_factura_operador.id)
                                INNER JOIN "inventario_factura_operador_Facturas_Destinatarios" ON (inventario_factura_operador.id = "inventario_factura_operador_Facturas_Destinatarios".factura_operador_id)
                                INNER JOIN inventario_factura ON ("inventario_factura_operador_Facturas_Destinatarios".factura_id = inventario_factura.id)
                                INNER JOIN inventario_destinatario ON (inventario_factura."Destinatario_id" = inventario_destinatario.id)
                                INNER JOIN inventario_provincia ON (inventario_destinatario."Provincia_id" = inventario_provincia.id)
                            WHERE inventario_entrega."Estado" != 'Cancelado' AND inventario_entrega."Fecha_Entrega" >= '%s' AND inventario_entrega."Fecha_Entrega" <= '%s' AND inventario_transportista."id"= %s AND inventario_transportista."Empresa"= '%s'
                            GROUP BY inventario_transportista."Nombre",inventario_transportista."Empresa",inventario_transportista."Chapa", inventario_provincia."Nombre"
                                """%(fecha_desde, fecha_hasta, current_transportista.id, empresa.Nombre))
                    
                    row = cursor.fetchall()

                    for current in row:
                        current_row = {}
                        current_row['transportista']=current[0]
                        current_row['chapa']=current[1]
                        current_row['empresa']=current[2]
                        current_row['destinos']= []

                        transportistas.append(current_row)

                    for current_transportista in transportistas:
                        for current in row:
                            if current_transportista['transportista'] == current[0] and current_transportista['chapa'] == current[1] and current_transportista['empresa'] == current[2]:
                                provincia = {}
                                provincia['provincia']=current[4]
                                provincia['cantidad_bultos']=current[3]
                        
                                current_transportista['destinos'].append(provincia)
            except:
                messages.error(request, 'Ocurrió un error en la búsqueda de los datos')
        else:
            messages.error(request, 'Debe ingresar los datos requeridos.')

    ctx = {'active_menu': active_menu,'form':form_reporte_diario,'bultos_despachados':transportistas, 'fecha_desde': fecha_desde, 'fecha_hasta': fecha_hasta}
    return render(request, 'reportes/reporte_transportistas.html', ctx)


def nacionalizar_cargas():
    list_inventario = Inventario.objects.filter(Nacionalizado=False)
    # print('list_inventario',list_inventario)
    for current_inventario in list_inventario:
        #Obteniendo inventario
        current_inventario = Inventario.objects.get(id = current_inventario.id)

        #Actualizando inventario
        current_inventario.Nacionalizado = True
        current_inventario.Fecha_Nacionalizacion = now()
        
        try:
            #Capturando valores de la aduana
            man = str(current_inventario.Manifiesto)
            if len(man.split('/')[0]) < 4:
                man = str(current_inventario.Manifiesto).zfill(4)
            
            if len(man.split('/')) == 1:
                man = man + '/' + str(current_inventario.Fecha_Entrada_Puerto.year)

            #dicto = {'success': True, 'despachos': [{'BOLETIN_DERECHO': '171021047035915000007', 'NO_BLGA': 'MAY21110540', 'MANIFIESTOS': '0358/2021', 'VALOR_DERECHOS': '0', 'VALOR_SERVICIO': '50'}]}
            USUARIO = 'aerov'
            PASS = 'eh7443fx'
            MANIFIESTO = man
            HBL = current_inventario.HBL
            CODIGO_ADUANA = '0200'

            URL= 'https://sua.aduana.cu/GINASUA/serviciosExternos.php'
            headers = {
                'Content-Type': 'application/xml',
                'Accept': 'application/xml',
            }
            data = '<?xml version=\"1.0\" encoding=\"utf-8\"?><soap:Envelope xmlns:soap=\"http://schemas.xmlsoap.org/soap/envelope/\"><soap:Body><GABLDespachado><usuario>'+ USUARIO +'</usuario><clave>'+ PASS +'</clave><manifiesto>'+ MANIFIESTO +'</manifiesto><blga>'+ HBL +'</blga><codigoaduana>'+ CODIGO_ADUANA +'</codigoaduana></GABLDespachado></soap:Body></soap:Envelope>'
                    
            resp = requests.get( URL, headers = headers, data = data, verify=False )
            resp_strip = strip_tags(resp.content)
            dict = resp_strip.replace('\\', '').replace("b'n", ""). replace("n'", "")
            dicto = json.loads(dict)

            print('-------------- CONSULTA ADUANA ------------------')
            print(dicto['success'])
            if dicto['success'] == True:
                current_inventario.Importe_Derecho_aduanal = float(dicto['despachos'][0]['VALOR_DERECHOS'])
                current_inventario.Importe_Servicio_aduanal = float(dicto['despachos'][0]['VALOR_SERVICIO'])
                current_inventario.Precio = 0
                current_inventario.Categoria_Operacion = 'ENVIO'
                current_inventario.Fecha_Nacionalizacion = datetime.now()
                current_inventario.save()

        except:
            pass

        #Salvando Tracking
        traking = Traking()
        traking.Inventario      = current_inventario
        traking.Estado          = 'Despachado por aduana'
        traking.Observaciones   = 'En desagrupe'
        traking.Fecha           = now()
        traking.save()
        # Registro de trazas
        # save_addition('traking', traking.id, str(model_to_dict(traking)))
        # save_addition(request.user, 'traking', traking.id, str(model_to_dict(traking)))
        print('----------- INVENTARIO SALVADO -------------------')
        print('HBL: ' + str(current_inventario.HBL) + ' Importe_Derecho_aduanal: ' + str(current_inventario.Importe_Derecho_aduanal) + ' Importe_Servicio_aduanal: ' + str(current_inventario.Importe_Servicio_aduanal))
        
        # Registro de trazas
        # save_edition(request.user, 'inventario', current_inventario.id, str(model_to_dict(current_inventario)))


# Tarea a ejecutarse cada determinado tiempo.
# def timer():
#     while True:
#         # print("¡Hola, mundo!")
#         # desnacionalizar_cargas()
#         nacionalizar_cargas()
#         print('paso')
#         time.sleep(10)   # 10 segundos.
# # Iniciar la ejecución en segundo plano.
# t = threading.Thread(target=timer)
# t.start()

@login_required(login_url='login')
def levantamiento_inventario(request):
    #Validando roles
    if not request.user.is_superuser:
        raise Http404

    #Definiendo menu activo
    active_menu = 'levantamiento_inventario'
    form = Importar_Inventario_Form()
    cargas_en_inventario =[]
    if request.method == 'POST':
        form = Importar_Inventario_Form(request.POST, request.FILES)
        if form.is_valid():
            almacen = request.POST.get('Almacen')
            fecha_desde = request.POST.get('Fecha_Desde')
            fecha_hasta = request.POST.get('Fecha_Hasta')
            #Fichero de inventario
            file = request.FILES['File']    
            # Comprobando la extension del archivo
            if not file:
                messages.error(request, 'Debe seleccionar un fichero')
                ctx = {'active_menu': active_menu, 'form': form}
                return render(request, 'reportes/reporte_levantamiento_inventario.html', ctx)         
            #Valores generales
            No_fila = 0
            try:
                with transaction.atomic():
                    dataset = Dataset()

                    # Comprobando la extension del archivo
                    if not file.name.endswith('.xls'):
                        messages.error(request, 'La extensión del archivo no es correcta, debe ser .xls')
                        ctx = {'active_menu': active_menu, 'form': form}
                        return render(request, 'reportes/reporte_levantamiento_inventario.html', ctx)
                    
                    #Carga de archivo excel
                    imported_data = dataset.load(file.read(), format='xls')
                    #Relacion de columnas
                    Col_HBL = 0
                    Col_Cant_Bultos = 1
                    Col_Destinatario_Nombre = 2
                    hbl_no_existentes=[]
                    inventario_almacen=[]
                    for data in imported_data:
                        #Incrementando contador de la fila
                        No_fila = No_fila + 1
                        if No_fila > 1:                                                        
                            # -------------------
                            paquete={}
                            if data[Col_HBL]:
                                inventario_almacen.append(data[Col_HBL])
                            # --------------------
                    manifiestos = Manifiesto.objects.filter(Fecha_Importacion__gt=fecha_desde,Fecha_Importacion__lte=fecha_hasta)
                    manifiestos_id = []
                    for manifiesto in manifiestos:
                        print('manifiesto',manifiesto)
                        manifiestos_id.append(manifiesto.Manifiesto)
                    cargas_en_inventario= Inventario.objects.filter(Estado='Inventario',Almacen__id=almacen,Manifiesto__in=manifiestos_id).exclude(HBL__in=inventario_almacen)

                    # Esto es por si quieren agregar la cantidad de ocurrencias del HBL y la factura asociada
                    # for carga in cargas:
                    #     faltante = {}
                    #     faltante['Factura'] = ''
                    #     faltante['Inventario'] = carga
                    #     faltante['Repeticiones'] = Inventario.objects.filter(HBL=carga.HBL).count()
                    #     if faltante['Repeticiones']>1:
                    #         facturas = Factura.objects.all()
                    #         for factura in facturas:
                    #             cargas_en_factura = factura.Inventario.all()
                    #             for carga_en_factura in cargas_en_factura:
                    #                 if carga_en_factura.HBL == carga.HBL:
                    #                     faltante['Factura'] = factura.id 
                    #     cargas_en_inventario.append(faltante)

            except Exception as inst:
                messages.error(request, 'Ha ocurrido un error importando el manifiesto. Por favor revise la línea ' + str(int(No_fila) + 2))
                messages.error(request, inst)
    # #Aplicacion de filtros
    # inventario_filter = InventarioFilter(request.GET, queryset=cargas_en_inventario)
    # cargas_en_inventario = inventario_filter.qs


    # #Paginator
    # paginator = Paginator(cargas_en_inventario, 400) # Show 100 contacts per page.
    # page_number = request.GET.get('page')
    # page_obj = paginator.get_page(page_number)

    ctx = {'active_menu': active_menu, 'form': form,'inventarios_no_existentes':cargas_en_inventario}
    return render(request, 'reportes/reporte_levantamiento_inventario.html', ctx)


@login_required(login_url='login')
def inventario_fisico(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Formulario de tabla
    form_hbl_escaneados = HBL_Escaneados_Form()

    #Ejecutando operaciones de las tablas
    # operaciones_de_tablas(request)   
    #Informacion para el template
    header_text     = 'Generar Inventario Físico'
    breadcrumb_text = 'Generar Inventario Físico'
    #Definiendo menu activo
    active_menu = 'inventario_fisico'

    inventarios = Inventario.objects.all()
    if request.POST.get('HBL'):
        hbl_regex = re.compile(r'[A-Z0-9-_/\*]*')
        #HBL escaneados
        list_comprobantes = request.POST.get('HBL') 
        print('list_comprobantes',list_comprobantes)  
        seleccion = re.findall(hbl_regex,list_comprobantes)
        seleccion = set(seleccion)

        inventarios = Inventario.objects.all().filter(HBL__in=seleccion).order_by('HBL')
        # print('inventarios',inventarios)
    #Aplicacion de filtros
    inventario_filter = InventarioFilter(request.GET, queryset=inventarios)

    inventarios = inventario_filter.qs
    # print('filtrado',inventarios)
    #Paginator
    paginator = Paginator(inventarios, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj, 'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'inventario_filter': inventario_filter, 'form_hbl_escaneados':form_hbl_escaneados}
    return render(request, 'reportes/inventario_fisico.html', ctx)

# @login_required(login_url='login')
# def exportar_comprobantes_destinatario(request):
#     #Definiendo menu activo
#     active_menu = 'exportar_comprobantes_destinatario'
#     header_text = 'Expo'
#     breadcrumb_text = 'Reporte de cargas por transportistas'  


# def desnacionalizar_cargas():
#     inventarios = Inventario.objects.filter(Fecha_Nacionalizacion=datetime.today(),Estado='Inventario',Nacionalizado=True)
#     inventarios_desnacionalizar =[]
#     for inv in inventarios:
#         facturas_inventario = Factura_Inventario.objects.filter(Inventario__id=inv.id)
#         # print('facturas_inventario',facturas_inventario)
#         if not facturas_inventario:
#             inventarios_desnacionalizar.append(inv.id)
#     # print('inventarios_desnacionalizar',inventarios_desnacionalizar)
#     inventarios_des = Inventario.objects.filter(id__in=inventarios_desnacionalizar)
#     for invent in inventarios_des:
#         invent.Nacionalizado = False
#         invent.save()




# def cantidad_no_nacionalizados():
#     cant_inventario = Inventario.objects.filter(Nacionalizado=False).count()
#     return cant_inventario




# ----------------------------------------Auxiliares--------------------------------------------------
#Actualizar Importe de factura con escaneo doble de comprobantes
# def update_comprobante_operador():
#     factura = Factura_Operador.objects.get(id=2194)
#     factura.Importe = 5740
#     factura.save()
#     return True

# def actualizar_valor():
    
#     facturas_id = Factura_Operador.objects.filter(id=896).values('Facturas_Destinatarios__id')
#     for fac in facturas_id:
#         print('fac',fac)
#         if fac['Facturas_Destinatarios__id'] == 37962:
#             fac.pop('Facturas_Destinatarios__id',37962)
#         fac.save()
    
#     return True

# def update_comprobante_operador():
#     # with connection.cursor() as cursor:
#         # cursor.execute(""" delete from "inventario_factura_operador_Facturas_Destinatarios"
#         #                 where "inventario_factura_operador_Facturas_Destinatarios".factura_operador_id = 2194 AND "inventario_factura_operador_Facturas_Destinatarios".factura_id = 47620 OR "inventario_factura_operador_Facturas_Destinatarios".factura_id = 47630 OR "inventario_factura_operador_Facturas_Destinatarios".factura_id = 47503 OR "inventario_factura_operador_Facturas_Destinatarios".factura_id = 46764 OR "inventario_factura_operador_Facturas_Destinatarios".factura_id = 46690 OR "inventario_factura_operador_Facturas_Destinatarios".factura_id = 47505 OR "inventario_factura_operador_Facturas_Destinatarios".factura_id = 47017 OR "inventario_factura_operador_Facturas_Destinatarios".factura_id = 46983""")
#     factura = Factura_Operador.objects.get(id='896')
#     print('factura factura',factura)
#     factura.Importe = 5740
#     factura.save()
#     return True

# def update_comprobante():
#     tras = Factura.objects.get(id='50006')
#     tras.Importe_Transportacion_Total=0
#     tras.Importe_Recargo_Total=0
#     tras.Importe_Total_Factura = tras.Importe_Transcargo_Total + tras.Importe_Seguro_Carga_Total + tras.Importe_Recargo_Total + tras.Importe_Transportacion_Total + tras.Importe_Derecho_Aduanal_Total + tras.Importe_Servicio_Aduanal_Total
#     tras.save()

#     fact_inv = Factura_Inventario.objects.get(Factura=tras.id)
#     fact_inv.Importe_Transportacion=0
#     fact_inv.save()
#     return True





# def update_destinatario():
#     destinatario=''
#     tras = Destinatario.objects.filter(CI='66010529391',Nombre='MAIRA MARTINEZ GONZALEZ')[:1]
#     for t in tras:
#         destinatario=t
#     # tras = Destinatario.objects.get(CI='66010529391',Nombre='MAIRA MARTINEZ GONZALEZ')
#     hbl_lis=['AFS-4003075','AFS-4003076','AFS-4003077','AFS-4003078','AFS-4003079','AFS-4003080','AFS-4003081','AFS-4003082']
#     inventarios=Inventario.objects.filter(HBL__in=hbl_lis)
#     for inv in inventarios:
#         inv.Destinatario=destinatario
#         inv.save()
#         print('inventario',inv)
#     # for t in tras:
#     #     print('ttttt',t)
#     #     if t.Nombre == 'ESTHER INGUANTE FERNANDEZ':
#     #         t.CI='42090405012'
#     #         t.save()
#     #         print('usuario',tras,tras.CI)
#     return True

