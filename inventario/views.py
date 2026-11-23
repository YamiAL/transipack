from io import BytesIO
import os
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
import barcode
from barcode.writer import ImageWriter 
import dbf
import serial
from xml.dom import minidom
import xml.etree.ElementTree as gfg
from io import BytesIO
#import winsound
import calendar
# ------------------Para generar PDF-------------------#
from reportlab.graphics.barcode import code39, code128, code93,eanbc, qr, usps
# from reportlab.graphics.barcode import eanbc, qr, usps
from reportlab.graphics.shapes import Drawing 
from reportlab.lib.pagesizes import letter,inch
from reportlab.lib.units import mm, cm
from reportlab.pdfgen import canvas
from reportlab.graphics import renderPDF
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Table,TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab_qrcode import QRCodeImage
from reportlab.lib.enums import TA_JUSTIFY,TA_LEFT,TA_CENTER,TA_RIGHT
from reportlab.pdfbase.pdfmetrics import stringWidth, getFont
from reportlab.lib import colors
_baseFontName  ='Helvetica'
_baseFontNameB ='Helvetica-Bold'
_baseFontNameI ='Helvetica-Oblique'
_baseFontNameBI='Helvetica-BoldOblique'
from django.db.models import Prefetch

@login_required(login_url='login')
def inicio(request):
    #correccion(request)
    no_contenedor_manifiestos_habilitados = Manifiesto.objects.filter(Habilitado=True).values('No_Contenedor')
    no_guia_manifiestos_habilitados = Manifiesto.objects.filter(Habilitado=True).values('AWB')

    #Lista de inventarios
    inventario = Inventario.objects.all()

    #Datos relevantes
    cantidad_inventarios_no_nacionalizados = inventario.filter(Q(Estado = 'Inventario')).count()
    cantidad_inventarios = inventario.filter(Estado = 'Inventario').count()
    inventario_no_nacionalizado_fuera_tiempo = inventario.filter(~Q(Estado = 'Entregado'), Q(Fecha_Entrada_Puerto__lt = datetime.now() - timedelta(days=30))).count()
    incidencias_del_dia = inventario.filter(Q(Estado = 'Inventario'), ~Q(Incidencia = None)).count()
    # nacionalizar_cargas(request)
    ctx = {'cantidad_inventarios': cantidad_inventarios, 'inventario_no_nacionalizado_fuera_tiempo': inventario_no_nacionalizado_fuera_tiempo, 'incidencias_del_dia': incidencias_del_dia, 'cantidad_inventarios_no_nacionalizados': cantidad_inventarios_no_nacionalizados}
    return render(request, 'inicio.html', ctx)

#----Gestion de Inventarios---------------------------------------------------
@login_required(login_url='login')
def inventario_list(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Formulario de tabla
    form_trasladar_almacen = Operacion_Trasladar_De_Almacen_Form()
    form_nacionalizar_carga   = Operacion_Nacionalizar_Inventario_Form()
    form_ubicar_carga_dentro_almacen = Ubicar_Cargas_Dentro_Almacen_Form()

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

    ctx = {'page_obj': page_obj, 'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'form_trasladar_almacen': form_trasladar_almacen, 'inventario_filter': inventario_filter, 'form_nacionalizar_carga': form_nacionalizar_carga,'form_ubicar_carga_dentro_almacen':form_ubicar_carga_dentro_almacen}
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
            traking.Estado          = 'En depósito'
            traking.Observaciones   = 'Sin despachar por aduana'
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
    isMaritimo = getattr(current_inventario,'isMaritimo')
    isAereo = getattr(current_inventario,'isAereo')
    pais = getattr(current_inventario,'Pais_Origen')
    agencia = getattr(current_inventario,'Agencia')
    fecha_entrada_puerto = getattr(current_inventario,'Fecha_Entrada_Puerto')
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
                form_inventario_instance.isAereo=isAereo
                form_inventario_instance.isMaritimo=isMaritimo
                #----------------------------------------------------------------
                edit_pais = Paises.objects.get(id=request.POST.get('Pais_Origen'))
                if edit_pais != pais.id:
                    form_inventario_instance.Pais_Origen=edit_pais
                else:
                    form_inventario_instance.Pais_Origen=pais
                #----------------------------------------------------------------
                
                edit_agencia = Agencia.objects.get(id=request.POST.get('Agencia'))
              
                if edit_agencia.id != agencia.id:
                    form_inventario_instance.Agencia=edit_agencia
                else:
                    form_inventario_instance.Agencia=agencia

                form_inventario_instance.Fecha_Entrada_Puerto=fecha_entrada_puerto

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
    factura_inventario = Factura_Inventario.objects.filter(Inventario__id=id_inventario).last()
    ctx = {'current_registro': current_registro,'factura_inventario':factura_inventario}
    return render(request, 'inventario/inventario_detail.html', ctx)
  
@login_required(login_url='login')
def inventario_delete(request, id_inventario):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404
    # traking = Traking.objects.filter(Inventario__id=id_inventario).delete()
    # inventario = Inventario.objects.filter(id=id_inventario).delete()
    inventario = Inventario.objects.filter(id=id_inventario).first()
    inventario.Estado = 'Salida de inventario'
    inventario.save()
    # inventarios = Inventario.objects.all().filter(Estado = 'Salida de inventario')
    # Registro de trazas
    save_edition(request.user, 'inventario', inventario.id, str(model_to_dict(inventario)))

    mensaje = 'Inventario ' + inventario.HBL + ' eliminado satisfactoriamente'
    messages.success(request, mensaje)
    return redirect('inventario_list')



#----Cargas no nacionalizadas-------------------------------------------------------------
@login_required(login_url='login')
def no_nacionalizada_list(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Formulario de tabla
    form_trasladar_almacen    = Operacion_Trasladar_De_Almacen_Form()
    form_nacionalizar_carga   = Operacion_Nacionalizar_Inventario_Form()
    form_ubicar_carga_dentro_almacen = Ubicar_Cargas_Dentro_Almacen_Form()
    #IF POST: ------  Ejecutando operaciones de las tablas
    operaciones_de_tablas(request)   

    header_text     = 'Inventarios no nacionalizados'
    breadcrumb_text = 'Inventarios no nacionalizados'
    #Definiendo menu activo
    active_menu = 'mercancia_inventario'

    inventarios = Inventario.objects.all().filter(Q(Estado = 'Inventario'),~Q(Estado = 'Desagrupe'), Q(Nacionalizado = False)).order_by('HBL')
    # inventarios = Inventario.objects.all().filter(Q(Estado = 'Inventario'), Q(Nacionalizado = False)).order_by('HBL')
    # inventarios = Inventario.objects.all().filter(Q(Estado = 'Inventario'), Q(Nacionalizado = False), Q(Incidencia__isnull=False) | Q(Estado = 'Inventario'), Q(Nacionalizado = False), Q(Incidencia__isnull=True),Q(rectificacion_aduana__isnull=False)).order_by('HBL')
    # inventarios = Inventario.objects.all().filter(Q(Estado = 'Inventario',exist=True), Q(Nacionalizado = False)).order_by('HBL')

    #Aplicacion de filtros
    inventario_filter = InventarioFilter(request.GET, queryset=inventarios)
    inventarios = inventario_filter.qs

    #Paginator
    paginator = Paginator(inventarios, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj, 'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'form_trasladar_almacen': form_trasladar_almacen, 'form_nacionalizar_carga': form_nacionalizar_carga, 'inventario_filter': inventario_filter,'form_ubicar_carga_dentro_almacen':form_ubicar_carga_dentro_almacen}
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
                current_manifiesto=''
                if request.POST.get('No_Contenedor'):
                    current_manifiesto = Manifiesto.objects.get(Q(No_Contenedor = form.cleaned_data['No_Contenedor']), Q(Manifiesto = form.cleaned_data['Manifiesto']))
                if request.POST.get('AWB'):
                    if not request.POST.get('Aeropuerto_Origen'):
                        messages.error(request, 'Debe ingresar el código IATA del aeropuerto de origen')
                        ctx = {'active_menu': active_menu, 'form': form}
                        return render(request, 'operacion_mercancia/operacion_importar_manifiesto.html', ctx)
                    current_manifiesto = Manifiesto.objects.get(Q(AWB = form.cleaned_data['AWB']), Q(Manifiesto = form.cleaned_data['Manifiesto']))    
                if current_manifiesto:
                    messages.error(request, 'El manifiesto que desea importar ya se encuentra registrado en el sistema')
                    ctx = {'active_menu': active_menu, 'form': form}
                    return render(request, 'operacion_mercancia/operacion_importar_manifiesto.html', ctx)
          

            except:
                pass
            
            #Valores generales
            No_fila = 0
            hbl_existentes = []
            try:
                with transaction.atomic():
                    dataset = Dataset()

                    #Comprobando la extension del archivo
                    if not file.name.endswith('.xls'):
                        messages.error(request, 'La extensión del archivo no es correcta, debe ser .xls')
                        ctx = {'active_menu': active_menu, 'form': form}
                        return render(request, 'operacion_mercancia/operacion_importar_manifiesto.html', ctx)

                    #Carga de archivo excel
                    imported_data = dataset.load(file.read(), format='xls', headers=False)
                    
                    #Relacion de columnas
                    Col_HBL = 0
                    # Col_AWB = 1
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
                    #Datos del contenedor
                    Col_Agencia=''
                    Col_Pais=''
                    Col_Consignatario=''
                    Col_AWB=''
                    Col_Contenedor=''
                    Col_Cantidad_Envios=''
                    Col_Cantidad_Bultos=''
                    Col_Peso_total=''
                    Col_Fecha=''


                    for data in imported_data:
                       

                        if No_fila ==4:
                            Col_Cantidad_Envios = data[1]

                        if No_fila ==5:
                            Col_Cantidad_Bultos = data[1]

                        if No_fila ==6:
                            Col_Peso_total = data[1]

                        if No_fila ==7:
                            Col_Fecha = data[1]
                            
                        if No_fila >= 9:

                            id_HBL = ''
                            if str(data[Col_HBL]).endswith('.0'):
                                id_HBL = str(data[Col_HBL]).replace('.0', '')
                            else:
                                id_HBL = str(data[Col_HBL])
                            existe=''
                            if request.POST.get('No_Contenedor'):
                                existe = Inventario.objects.filter(HBL=id_HBL,No_Contenedor=request.POST.get('No_Contenedor')).first()
                            if request.POST.get('AWB'):
                                existe = Inventario.objects.filter(HBL=id_HBL,AWB=request.POST.get('AWB')).first()
                            if existe:
                                hbl_existentes.append(existe.HBL)
                            else:
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
                                
                                if str(data[Col_HBL]).endswith('.0'):
                                    current_inventario.HBL = str(data[Col_HBL]).replace('.0', '')
                                else:
                                    current_inventario.HBL = str(data[Col_HBL])
                                if request.POST.get('AWB'):  
                                    current_inventario.AWB = request.POST.get('AWB')
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
                                current_inventario.Aeropuerto_Origen = form.cleaned_data['Aeropuerto_Origen']                     
                                # agencia = Agencia.objects.get(id=request.POST.get('Agencia'))
                                current_inventario.Agencia = Agencia.objects.get(id=request.POST.get('Agencia'))
                                current_inventario.Pais_Origen = Paises.objects.get(id=request.POST.get('Pais'))
                                if request.POST.get('isPrepago') == 'on':
                                    current_inventario.isPrepago = True
                                else:
                                    current_inventario.isPrepago = False
                                
                                if request.POST.get('tipo_envio') == 'aereo':
                                    current_inventario.isAereo = True
                                else:
                                    current_inventario.isAereo = False

                                if request.POST.get('tipo_envio') == 'maritimo':
                                    current_inventario.isMaritimo = True
                                else:
                                    current_inventario.isMaritimo = False

                                current_inventario.save()
                                HBL_No_Manifestados.objects.filter(HBL=current_inventario.HBL).delete()

                                #Salvando Tracking
                                traking = Traking()
                                traking.Inventario      = current_inventario
                                traking.Estado = 'En depósito'
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
                    nombre_archivo = ''
                    if request.POST.get('AWB'):
                        nombre_archivo = 'Manifiesto-' + str(form.cleaned_data['Manifiesto']) + '-GuiaAerea-' + str(request.POST.get('AWB')) + '.xls'
                    if request.POST.get('No_Contenedor'):
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
                    

                    if request.POST.get('tipo_envio') == 'aereo':
                        registro_manifiesto.isAereo = True
                    else:
                        registro_manifiesto.isAereo = False

                    if request.POST.get('tipo_envio') == 'maritimo':
                        registro_manifiesto.isMaritimo = True
                    else:
                        registro_manifiesto.isMaritimo = False
                    if request.POST.get('Agencia'):  
                        registro_manifiesto.Agencia = Agencia.objects.get(id=request.POST.get('Agencia'))
                    registro_manifiesto.Pais_Origen = Paises.objects.get(id=request.POST.get('Pais'))
                    registro_manifiesto.Consignatario = 'Cubanacan Express'
                    registro_manifiesto.AWB = request.POST.get('AWB')
                    registro_manifiesto.Aeropuerto_Origen = form.cleaned_data['Aeropuerto_Origen']                     
                    registro_manifiesto.Cantidad_bultos = Col_Cantidad_Bultos
                    registro_manifiesto.Cantidad_envios = Col_Cantidad_Envios
                    registro_manifiesto.Peso_total = Col_Peso_total
                    registro_manifiesto.save()


                   
                    # Registro de trazas
                    save_addition(request.user, 'manifiesto', registro_manifiesto.id, str(model_to_dict(registro_manifiesto)))
                    Total_filas=No_fila-9 - len(hbl_existentes)
                    messages.success(request, 'Se han importado ' + str(Total_filas) + ' registros satisfactoriamente')  
                    messages.warning(request, 'Los siguientes HBL ya se encontraban registrados en el sistema ' + str(hbl_existentes).replace('[', '').replace(']', ''))  
                    return redirect(request.path)  
            except Exception as inst:
                messages.error(request, 'Ha ocurrido un error importando el manifiesto. Por favor revise la línea ' + str(int(No_fila) + 2))
                messages.error(request, inst)
          
    ctx = {'active_menu': active_menu, 'form': form}
    return render(request, 'operacion_mercancia/operacion_importar_manifiesto.html', ctx)

@login_required(login_url='login')
def importar_no_manifestados(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Definiendo menu activo
    active_menu = 'mercancia_inventario'
    form = Operacion_Importar_No_Manifestados_Form()

    if request.method == 'POST':
        form = Operacion_Importar_No_Manifestados_Form(request.POST, request.FILES)
        if form.is_valid():
            #Fichero de manifiesto
            file = request.FILES['File']

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
                    imported_data = dataset.load(file.read(), format='xls', headers=False)
                    
                    #Relacion de columnas
                    Col_HBL = 0
                    # Col_AWB = 1
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
                    #Datos del contenedor
                    Col_Agencia=''
                    Col_Pais=''
                    Col_Consignatario=''
                    Col_AWB=''
                    Col_Contenedor=''
                    Col_Cantidad_Envios=''
                    Col_Cantidad_Bultos=''
                    Col_Peso_total=''
                    Col_Fecha=''

                    Cantidad_importados = 0

                    for data in imported_data:
                        if No_fila >= 9:
                           
                            inventario_existe = Inventario.objects.filter(No_Contenedor = form.cleaned_data['No_Contenedor'], Manifiesto = form.cleaned_data['Manifiesto'],HBL=data[Col_HBL])
                            if len(inventario_existe) > 0:
                                pass
                            else:
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
                                
                                if str(data[Col_HBL]).endswith('.0'):
                                    current_inventario.HBL = str(data[Col_HBL]).replace('.0', '')
                                else:
                                    current_inventario.HBL = str(data[Col_HBL])
                                if request.POST.get('AWB'):  
                                    current_inventario.AWB = request.POST.get('AWB')
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
                                # agencia = Agencia.objects.get(id=request.POST.get('Agencia'))
                                current_inventario.Agencia = Agencia.objects.get(id=request.POST.get('Agencia'))
                                current_inventario.Pais_Origen = Paises.objects.get(id=request.POST.get('Pais'))
                                if request.POST.get('isPrepago') == 'on':
                                    current_inventario.isPrepago = True
                                else:
                                    current_inventario.isPrepago = False
                                
                                if request.POST.get('tipo_envio') == 'aereo':
                                    current_inventario.isAereo = True
                                else:
                                    current_inventario.isAereo = False

                                if request.POST.get('tipo_envio') == 'maritimo':
                                    current_inventario.isMaritimo = True
                                else:
                                    current_inventario.isMaritimo = False

                                current_inventario.save()

                                Cantidad_importados += 1
                                
                                HBL_No_Manifestados.objects.filter(HBL=current_inventario.HBL).delete()

                                #Salvando Tracking
                                traking = Traking()
                                traking.Inventario      = current_inventario
                                traking.Estado = 'En depósito'
                                traking.Observaciones   = 'Sin despachar por aduana'
                                traking.Fecha           = now()
                                traking.save()
                                # Registro de trazas
                                save_addition(request.user, 'traking', traking.id, str(model_to_dict(traking)))

                                # Registro de trazas
                                save_addition(request.user, 'inventario', current_inventario.id, str(model_to_dict(current_inventario)))

                        #Incrementando contador de la fila
                        No_fila = No_fila + 1

                    if Cantidad_importados > 0:
                        messages.success(request, 'Se han importado ' + str(Cantidad_importados) + ' registros satisfactoriamente')  
                        return redirect(request.path) 
                    else:
                        messages.warning(request, 'Los HBL se encontraban registros en el sistema')  
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
    mercancias_traslado_form = Mercancias_Traslado_Form()
    x= Reporte_Transportistas_Form()
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
                    traking.Observaciones   = 'Pendiente de distribución'
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
            messages.error(request, 'Ha ocurrido un error reincorporando los inventarios al almacén.')
            return redirect(request.path) 

    #Definiendo menu activo
    active_menu = 'mercancia_traslado'

    header_text     = 'Lista de mercancías en traslado'
    breadcrumb_text = 'Mercancías en traslado'
    

    inventarios = Inventario.objects.filter(Estado = 'Traslado')

    if request.GET.get('operador'):
        #print('count',str(Factura_Operador.objects.filter(Operador__id=request.GET.get('operador'),Estado='Pendiente de cobro').count()))
        facturas_destinatarios = Factura_Operador.objects.filter(Operador__id=request.GET.get('operador')).prefetch_related('Facturas_Destinatarios').values_list('Facturas_Destinatarios__id', flat=True)
        facturas_inventarios = Factura_Inventario.objects.filter(Factura__id__in=list(facturas_destinatarios)).values_list('Inventario__id', flat=True)
        
        inventarios = inventarios.filter(id__in=facturas_inventarios)
        
    if request.GET.get('transportista'):
        entregas = Entrega.objects.filter(Transportista__id=request.GET.get('transportista')).values_list('Factura_Operador__id')
        facturas_destinatarios = Factura_Operador.objects.filter(id__in=entregas).prefetch_related('Facturas_Destinatarios').values_list('Facturas_Destinatarios__id', flat=True)

        facturas_inventarios = Factura_Inventario.objects.filter(Factura__id__in=list(facturas_destinatarios)).values_list('Inventario__id', flat=True)
        
        inventarios = inventarios.filter(id__in=facturas_inventarios)
    #Aplicacion de filtros
    inventario_filter = InventarioFilter(request.GET, queryset=inventarios)
    inventarios = inventario_filter.qs

    #Paginator
    paginator = Paginator(inventarios, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'x':x,'mercancias_traslado_form':mercancias_traslado_form,'page_obj': page_obj, 'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'form_trasladar_almacen': form_trasladar_almacen, 'inventario_filter': inventario_filter}
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
    factura_filter = FacturaFilter()
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
    
    #Aplicacion de filtros
    facturas_filter = FacturaFilter(request.GET, queryset=facturas)
    facturas = facturas_filter.qs

    if request.method == 'POST':
        form_entrega   = Entrega_Form(request.POST)
        hbl_escaneados = request.POST.get('crear_traslado_escaner_qr')            
        if form_entrega.is_valid():
            chapa = request.POST.get('Chapa')
            transportista = request.POST.get('Transportista')
            if chapa:
                # existe = Transportista.objects.filter(id=transportista,Chapa=chapa)
                existe = Chapa.objects.filter(transportista=transportista,Chapa=chapa)

                if not existe:
                    messages.error(request, 'La chapa introduciada no corresponde al transportista seleccionado ')
                    return redirect(request.path) 
            if not hbl_escaneados:
                if len(request.POST.getlist('factura')) == 0:
                    messages.error(request, 'Debe seleccionar al menos una factura')
                    return redirect(request.path) 
            # try:
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
                entrega=Entrega.objects.get(Factura_Operador__id=factura_operador.id)
                entrega.Chapa=chapa
                entrega.save()

                if not hbl_escaneados:
                    #Agregando listado de comprobantes
                    for current_comprobante_id in request.POST.getlist('factura'):
                        current_comprobante = Factura.objects.get(pk = current_comprobante_id)
                        current_comprobante.Estado = 'Asignada'
                        current_comprobante.save()
                        factura_operador.Facturas_Destinatarios.add(current_comprobante)
                        factura_operador.Importe += current_comprobante.Importe_Total_Factura
                        destinos = current_comprobante.Inventario.all()[:1]
                        for destino in destinos:
                            factura_operador.Provincia =destino.Destinatario.Provincia 
                        factura_operador.save()

                else:
                    id_factura_regex_viejo = re.compile(r'[0-9]*')
                    #Expresión regular para teclado en Inglés y en Español
                    id_transaccion_regex = re.compile(r'((id_transaccion\":[0-9]*))|(transaccion\[Ñ )([0-9]*)')
                  
                    comprobantes_en_monta = []

                    #HBL escaneados
                    list_comprobantes_barra = request.POST.get('HBL')   
                    list_comprobantes_qr = request.POST.get('HBL_old')   
                    
                    seleccion_barra =[]
                    seleccion_qr = ''

                    if request.POST.get('HBL_old'):  
                        seleccion_qr = re.findall(id_factura_regex_viejo,list_comprobantes_qr)
                        seleccion_qr = set(seleccion_qr)
                    if request.POST.get('HBL'):
                        facturas_id = ''
                        largo = False
                        facturas_id = re.findall(id_transaccion_regex,list_comprobantes_barra)
                        if not facturas_id:
                            largo = True
                            facturas_id = re.findall(id_factura_regex_viejo,list_comprobantes_barra)
                        for factura in facturas_id:
                            x = ''
                            if largo == False:
                                x = re.findall(id_factura_regex_viejo,factura[0])
                            if largo == True:
                                x = re.findall(id_factura_regex_viejo,factura)
                            if len(x) > 3:
                                seleccion_barra.append(x[16]) 
                            else:
                                seleccion_barra.append(x[0]) 

                        seleccion_barra = set(seleccion_barra)

                    id_facturas = []
                    id_comprobante = ''
                    for sel in seleccion_barra:
                        id_facturas.append(sel)
                    for sel in seleccion_qr:                        
                        id_facturas.append(sel)                            
                    
                    #Valido que no se repitan los id de factura
                    id_facturas=set(id_facturas)   

                        #Guardo los ID de los comprobantes de destinatario
                    for id_factura in id_facturas:
                        if id_factura:
                            current_comprobante = Factura.objects.get(pk = id_factura)
                            if current_comprobante.Estado == 'Creada':
                                crear_factura_operador=True
                                current_comprobante.Estado = 'Asignada'
                                current_comprobante.save()
                                factura_operador.Facturas_Destinatarios.add(current_comprobante)
                                factura_operador.Importe += current_comprobante.Importe_Total_Factura
                                factura_operador.save()
                            else:
                                comprobantes_en_monta.append(current_comprobante.id)
                    if comprobantes_en_monta:
                        messages.warning(request, 'Las siguientes facturas están asociadas a una monta: ' + str(comprobantes_en_monta).replace('[', '').replace(']', ''))
                        # if len(seleccion) == 1:
                        #     Entrega.objects.filter(Factura_Operador__id=factura_operador.id).delete()
                        #     Factura_Operador.objects.filter(id=factura_operador.id).delete()
                        #     # messages.error(request, 'Ha ocurrido un error programando el traslado')
                        #     return redirect(request.path) 
                # Registro de trazas
                save_addition(request.user, 'entrega', form_entrega_instance.id, str(model_to_dict(form_entrega_instance)))
                save_addition(request.user, 'factura_operador', factura_operador.id, str(model_to_dict(factura_operador)))
                save_addition(request.user, 'factura', current_comprobante.id, str(model_to_dict(current_comprobante)))

                messages.success(request, 'Traslado programado satisfactoriamente')
                return redirect(reverse('entrega_detail', kwargs={"id_entrega": form_entrega_instance.id}))
            # except Exception as inst:
            #     messages.error(request, 'Ha ocurrido un error programando el traslado')
            #     return redirect(request.path) 

    ctx = {'action': action,'factura_filter':factura_filter,'form_entrega': form_entrega,'form_hbl_escaneados':form_hbl_escaneados,'form_empresa':form_empresa, 'active_menu': active_menu, 'facturas': facturas}
    return render(request, 'entrega/entrega_edit.html', ctx)


# @login_required(login_url='login')
# def entrega_monta_facturacion_add(request):
#     #Validando roles
#     if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
#         raise Http404

#     #Definiendo menu activo
#     active_menu = 'mercancia_traslado'

#     action = 'add'
#     form_entrega   = Entrega_Form(initial={'Fecha_Entrega': now().date(), 'Hora_Salida': datetime.now().strftime('%H:%M')})
#     form_empresa = Empresa_Form()
#     form_hbl_escaneados = HBL_Escaneados_Form()
#     factura_filter = FacturaFilter()
#     #list_inventario = Inventario.objects.all().filter(Q(Estado = 'Inventario'), Q(Nacionalizado = True)).order_by('Destinatario__Municipio', 'Destinatario__CI')
#     #Buscando comprobantes de entregas de destinatarios que no estan relacionados en comprobantes de entrega de operadores
#     facturas_disponibles = []
#     with connection.cursor() as cursor:
#         cursor.execute(""" SELECT * FROM "inventario_factura" WHERE id not in 
#                         (
#                         SELECT "inventario_factura_operador_Facturas_Destinatarios"."factura_id" FROM "inventario_factura_operador_Facturas_Destinatarios" 
#                         INNER JOIN "inventario_factura_operador" ON "inventario_factura_operador_Facturas_Destinatarios"."factura_operador_id" = "inventario_factura_operador"."id" 
#                         WHERE not "inventario_factura_operador"."Estado" = 'Desestimada'
#                         ) AND "inventario_factura"."Estado" = 'Creada' """)

#         row = cursor.fetchall()
#         for current in row:
#             facturas_disponibles.append(list(current)[0])
    
#     facturas = Factura.objects.all().filter(Q(id__in = facturas_disponibles)).order_by('id')
    
#     #Aplicacion de filtros
#     facturas_filter = FacturaFilter(request.GET, queryset=facturas)
#     facturas = facturas_filter.qs
#     lista_inventarios_por_persona_sin_aranceles =''
#     lista_inventarios_por_persona_facturados =[]
#     if request.method == 'POST':
#         form_entrega   = Entrega_Form(request.POST)
#         hbl_escaneados = request.POST.get('crear_traslado_escaner_qr')            
#         if form_entrega.is_valid():
#             chapa = request.POST.get('Chapa')
#             transportista = request.POST.get('Transportista')
#             if chapa:
#                 # existe = Transportista.objects.filter(id=transportista,Chapa=chapa)
#                 existe = Chapa.objects.filter(transportista=transportista,Chapa=chapa)

#                 if not existe:
#                     messages.error(request, 'La chapa introduciada no corresponde al transportista seleccionado ')
#                     return redirect(request.path) 
#             if not hbl_escaneados:
#                 if len(request.POST.getlist('factura')) == 0:
#                     messages.error(request, 'Debe seleccionar al menos una factura')
#                     return redirect(request.path) 
#             # try:
#             with transaction.atomic():
#                 form_entrega_instance = form_entrega.save(commit=False)

#                 #Almacenando valores
#                 #Factura de operador
#                 factura_operador = Factura_Operador()
#                 factura_operador.Fecha_Creacion = now()
#                 factura_operador.Estado = 'En espera'
#                 factura_operador.Operador = form_entrega.cleaned_data['Operador']
#                 factura_operador.User_Facturador = request.user
#                 factura_operador.save()
#                 # #Traslado
#                 form_entrega_instance.Estado = 'Programado'
#                 form_entrega_instance.Factura_Operador = factura_operador
#                 form_entrega_instance.save()
#                 entrega=Entrega.objects.get(Factura_Operador__id=factura_operador.id)
#                 entrega.Chapa=chapa
#                 entrega.save()

#                 if not hbl_escaneados:
#                     #Agregando listado de comprobantes
#                     for current_comprobante_id in request.POST.getlist('factura'):
#                         current_comprobante = Factura.objects.get(pk = current_comprobante_id)
#                         current_comprobante.Estado = 'Asignada'
#                         current_comprobante.save()
#                         factura_operador.Facturas_Destinatarios.add(current_comprobante)
#                         factura_operador.Importe += current_comprobante.Importe_Total_Factura
#                         destinos = current_comprobante.Inventario.all()[:1]
#                         for destino in destinos:
#                             factura_operador.Provincia =destino.Destinatario.Provincia 
#                         factura_operador.save()

#                 else:
#                     # -----------------------------------------------
#                     HBL_regex = re.compile(r'([A-Z0-9.\/-]*)')
#                     #Obteniendo listado de HBL
#                     list_hbl_barra = request.POST.get('HBL')
#                     seleccion_barra = re.findall(HBL_regex,list_hbl_barra)
#                     seleccion_barra = set(seleccion_barra)
#                     #Verificando que esten nacionalizados los HBL
#                     hbl_nacionalizados = Inventario.objects.filter(HBL__in=seleccion_barra,Nacionalizado=True)
                    
#                     #Lista de facturas a pasar a la vista
#                     lista_facturas = []
                    
#                     #Obteniendo lista de destinatarios de la solicitud
#                     lista_de_destinatarios = [] #Lista de destinatarios
#                     for current_inventario in hbl_nacionalizados:
#                         lista_de_destinatarios.append(current_inventario.Destinatario.CI)
#                     lista_de_destinatarios = list(dict.fromkeys(lista_de_destinatarios))
#                     lista_inventarios_por_persona_sin_aranceles = hbl_nacionalizados.filter(Q(Importe_Servicio_aduanal__isnull=True)|Q(Importe_Servicio_aduanal__lte=0),Destinatario__CI__in = lista_de_destinatarios).values('HBL')

#                     for current_destinatario in lista_de_destinatarios:
#                         current_factura = {}
#                         current_lista_de_inventarios = []

#                         #Cantidad de veces que se mostrara la factura 
#                         current_factura['Copias_Facturas'] = range(1)

#                         #Valores totales
#                         current_factura['Importe_Transcargo_Total'] = 0.00 
#                         current_factura['Importe_Seguro_Carga_Total'] = 0.00 
#                         current_factura['Importe_Sobredimension_Total'] = 0.00 
#                         current_factura['Importe_Recargo_Total'] = 0
#                         current_factura['Importe_Transportacion_Total'] = 0.00 
#                         current_factura['Importe_Derecho_Aduanal_Total'] = 0.00 
#                         current_factura['Importe_Servicio_Aduanal_Total'] = 0.00 
#                         current_factura['Cantidad_Bultos_Total'] = 0 

#                         lista_inventarios_por_persona = hbl_nacionalizados.filter(Q(Importe_Servicio_aduanal__isnull=False)|Q(Importe_Servicio_aduanal__gt=0),Destinatario__CI = current_destinatario,isFacturado=False)
#                         inventarios_por_persona_facturados = hbl_nacionalizados.filter(Destinatario__CI = current_destinatario,isFacturado=False)
#                         lista_inventarios_por_persona_facturados.append(inventarios_por_persona_facturados)
#                         # +++++++++++++++++++++
#                         corresponsal=Agencia.objects.filter(id=lista_inventarios_por_persona.first().Agencia.id).first()
#                         current_factura['Corresponsal']=corresponsal
#                         destinatario=Destinatario.objects.filter(CI = current_destinatario).first()
#                         provincia=Provincia.objects.filter(id=destinatario.Provincia.id).first()

#                         current_factura['Provincia']=provincia
#                         # ++++++++++++++++++++++
#                         for current_inventario in lista_inventarios_por_persona:
#                             current_inventario_dict = {}
#                             current_inventario_dict['Inventario'] = current_inventario

#                             #Calculando el importe por derechos aduanales
#                             if current_inventario.Importe_Derecho_aduanal:
#                                 current_factura['Importe_Derecho_Aduanal_Total'] += current_inventario.Importe_Derecho_aduanal

#                             #Calculando el importe por servicios aduanales
#                             if current_inventario.Importe_Servicio_aduanal:
#                                 current_factura['Importe_Servicio_Aduanal_Total'] += current_inventario.Importe_Servicio_aduanal
#                             if current_inventario.isPrepago:
#                                 current_factura['Importe_Transcargo_Total'] = 0.00
#                                 current_factura['Importe_Seguro_Carga_Total'] = 0.00
#                                 current_factura['Importe_Sobredimension_Total'] = 0.00
#                                 current_factura['Importe_Recargo_Total'] = 0.00
#                                 current_factura['Importe_Transportacion_Total'] = 0.00
#                                 current_factura['Cantidad_Bultos_Total'] += current_inventario.Cantidad_Bultos
#                                 current_factura['Importe_KG_Adicional_Total'] = 0.00
#                                 #Agregando informacion a la lista
#                                 current_inventario_dict['Importe_Seguro_Carga'] = 0.00
#                                 current_inventario_dict['Importe_Sobredimension'] = 0.00
#                                 current_inventario_dict['Importe_Transportacion'] = 0.00
#                                 current_inventario_dict['Importe_Transcargo'] = 0.00
#                                 current_lista_de_inventarios.append(current_inventario_dict)
#                                 if current_inventario.Peso:
#                                     if current_inventario.Peso < 20.00:
#                                         current_inventario_dict['Importe_KG_Adicional'] = 0.00
#                                     if current_inventario.Peso > 20.00:
#                                         kg_adicional = current_inventario.Peso - 20
#                                         current_inventario_dict['Importe_KG_Adicional'] = kg_adicional * 5
#                                         current_inventario.Importe_Kg_Adicional = kg_adicional * 5
#                                         current_inventario.save()
#                                     current_factura['Importe_KG_Adicional_Total'] += current_inventario_dict['Importe_KG_Adicional']
#                                 else:
#                                     current_inventario_dict['Importe_KG_Adicional'] = 0.00
#                             else:    
#                                 #Calculando precio por seguro de carga
#                                 if current_inventario.Peso:
#                                     if current_inventario.Peso <= 1.50:
#                                         current_inventario_dict['Importe_Seguro_Carga'] = 0.00
#                                     if current_inventario.Peso > 1.50:
#                                         current_inventario_dict['Importe_Seguro_Carga'] = 12.00

#                                     current_factura['Importe_Seguro_Carga_Total'] += current_inventario_dict['Importe_Seguro_Carga']
#                                 else:
#                                     current_inventario_dict['Importe_Seguro_Carga'] = 0.00
                                
#                                 #Calculando precio por sobredimension
#                                 if current_inventario.Peso:
#                                     if current_inventario.Peso < 30.00:
#                                         current_inventario_dict['Importe_Sobredimension'] = 0.00
#                                     if current_inventario.Peso >= 30.00:
#                                         current_inventario_dict['Importe_Sobredimension'] = 70.00

#                                     current_factura['Importe_Sobredimension_Total'] += current_inventario_dict['Importe_Sobredimension']
#                                 else:
#                                     current_inventario_dict['Importe_Sobredimension'] = 0.00
#                                 #Calculando precio por transportacion
#                                 if current_inventario.Peso and request.POST.get('incluir_transportacion') == 'on':        
#                                     if current_inventario.Destinatario.Municipio.Importe_por_entrega:
#                                         current_inventario_dict['Importe_Transportacion'] = float(current_inventario.Destinatario.Municipio.Importe_por_entrega)
#                                         if request.POST.get('trasbordo') == 'on' or current_inventario.trasbordo == True:
#                                             current_inventario.trasbordo = True
#                                             current_inventario.save()
#                                             if current_inventario.Destinatario.Municipio.Importe_por_trasbordo:                                            
#                                                 current_inventario_dict['Importe_Transportacion'] += float(current_inventario.Destinatario.Municipio.Importe_por_trasbordo)
                                    
#                                     else:
#                                         current_inventario_dict['Importe_Transportacion'] = 0.00
#                                     current_factura['Importe_Transportacion_Total'] += float(current_inventario_dict['Importe_Transportacion'])
                                
#                                 else:
#                                     current_inventario_dict['Importe_Transportacion'] = 0.00
#                                 #Calculando el importe de transcargo
#                                 if current_inventario.Peso:
#                                     if current_inventario.Peso <= 1.50:
#                                         if current_inventario.Importe_Derecho_aduanal > 0:
#                                             current_inventario_dict['Importe_Transcargo'] = round((80.00 + (float(current_inventario.Importe_Derecho_aduanal) * 1.10)/100 + (float(current_inventario.Importe_Servicio_aduanal) * 1.10)/100), 2)
#                                         else:
#                                             current_inventario_dict['Importe_Transcargo'] = 80.00

#                                     if current_inventario.Peso > 1.50 and current_inventario.Peso <= 50.00:
#                                         current_inventario_dict['Importe_Transcargo'] = round((199.00 + float(current_inventario.Peso) * 12.00 + (float(current_inventario.Importe_Derecho_aduanal) * 1.10)/100 + (float(current_inventario.Importe_Servicio_aduanal) * 1.10)/100), 2)
#                                     if current_inventario.Peso > 50.00:
#                                         current_inventario_dict['Importe_Transcargo'] = round((800.00 + (float(current_inventario.Importe_Derecho_aduanal) * 1.10)/100 + (float(current_inventario.Importe_Servicio_aduanal) * 1.10)/100), 2)
                                
#                                     current_factura['Importe_Transcargo_Total'] += current_inventario_dict['Importe_Transcargo']
#                                 else:
#                                     current_inventario_dict['Importe_Transcargo'] = 0.00

#                                 if current_inventario.Peso:
#                                     if current_inventario.Peso < 20.00:
#                                         current_inventario_dict['Importe_KG_Adicional'] = 0.00
#                                         current_factura['Importe_KG_Adicional_Total'] += 0.00
                                        
#                                     if current_inventario.Peso > 20.00:
#                                         kg_adicional = current_inventario.Peso - 20
#                                         current_inventario_dict['Importe_KG_Adicional'] = kg_adicional * 5
#                                         current_inventario.Importe_Kg_Adicional = kg_adicional * 5
#                                         current_inventario.save()
#                                         current_factura['Importe_KG_Adicional_Total'] += current_inventario_dict['Importe_KG_Adicional']

#                                     # print('current_inventario_dict Importe_KG_Adicional', current_inventario_dict['Importe_KG_Adicional'])
#                                     # current_factura['Importe_KG_Adicional_Total'] += current_inventario_dict['Importe_KG_Adicional']
#                                     # print('current_factura Importe_KG_Adicional_Total', current_factura['Importe_KG_Adicional_Total'])
                                    
#                                 else:
#                                     current_inventario_dict['Importe_KG_Adicional'] = 0.00
#                                     current_factura['Importe_KG_Adicional_Total'] = 0.00

#                                 #Calculando total de bultos
#                                 current_factura['Cantidad_Bultos_Total'] += current_inventario.Cantidad_Bultos

#                                 #Agregando informacion a la lista
#                                 current_lista_de_inventarios.append(current_inventario_dict)

#                         current_factura['Destinatario'] = Destinatario.objects.filter(CI = current_destinatario).first()
#                         current_factura['Inventarios'] = current_lista_de_inventarios
#                         #Valor total de la factura
#                         current_factura['Precio_Total_Factura'] = current_factura['Importe_Transcargo_Total'] + current_factura['Importe_Seguro_Carga_Total'] + current_factura['Importe_Sobredimension_Total'] + current_factura['Importe_Recargo_Total'] + current_factura['Importe_Transportacion_Total'] + current_factura['Importe_Derecho_Aduanal_Total'] + current_factura['Importe_Servicio_Aduanal_Total']

#                         try:
#                             with transaction.atomic():
#                                 #Almacenando la factura en el sistema
#                                 factura_instance = Factura()
#                                 factura_instance.Contenido = str(current_factura)
#                                 factura_instance.isMultiple = True
#                                 factura_instance.isEnvio = True
#                                 factura_instance.Fecha = now()
#                                 factura_instance.User_Facturador = request.user
#                                 factura_instance.Estado = 'Creada'
#                                 factura_instance.Destinatario = current_factura['Destinatario']
#                                 factura_instance.Importe_Total_Factura = current_factura['Precio_Total_Factura']
#                                 factura_instance.Importe_Transcargo_Total = current_factura['Importe_Transcargo_Total']
#                                 factura_instance.Importe_Seguro_Carga_Total = current_factura['Importe_Seguro_Carga_Total']
#                                 factura_instance.Importe_Recargo_Total = current_factura['Importe_Recargo_Total']
#                                 factura_instance.Importe_Transportacion_Total = current_factura['Importe_Transportacion_Total']
#                                 factura_instance.Importe_Derecho_Aduanal_Total = current_factura['Importe_Derecho_Aduanal_Total']
#                                 factura_instance.Importe_Servicio_Aduanal_Total = current_factura['Importe_Servicio_Aduanal_Total']
#                                 factura_instance.Importe_Sobredimension_Total = current_factura['Importe_Sobredimension_Total']
#                                 factura_instance.Cantidad_Bultos_Total = current_factura['Cantidad_Bultos_Total']
#                                 factura_instance.Agencia=current_factura['Corresponsal']
#                                 factura_instance.Provincia=current_factura['Provincia']
#                                 factura_instance.save()
                                    
#                                 for current_inventario_object in current_factura['Inventarios']:
#                                     factura_inventario_instance = Factura_Inventario()
#                                     factura_inventario_instance.Factura = factura_instance
#                                     factura_inventario_instance.Inventario = current_inventario_object['Inventario']
#                                     factura_inventario_instance.Importe_Seguro_Carga = current_inventario_object['Importe_Seguro_Carga']
#                                     factura_inventario_instance.Importe_Sobredimension = current_inventario_object['Importe_Sobredimension']
#                                     factura_inventario_instance.Importe_Transportacion = current_inventario_object['Importe_Transportacion']
#                                     factura_inventario_instance.Importe_Transcargo = current_inventario_object['Importe_Transcargo']
#                                     factura_inventario_instance.save()

#                                 # Registro de trazas
#                                 save_addition(request.user, 'factura', factura_instance.id, str(model_to_dict(factura_instance)))
#                         except:
#                             raise ValueError('Ha ocurrido un error generando la factura')

#                         qr_generado = '{' + str(factura_instance.id) +'}'
#                         # qr_generado = '{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}'
#                         current_factura['id_factura'] = factura_instance.id
#                         current_factura['facturador'] = factura_instance.User_Facturador.get_full_name()
                        
#                         #Agregando factura a lista general de facturas
#                         lista_facturas.append(current_factura)


#                     for id_factura in lista_facturas:
#                         # if id_factura:
#                         current_comprobante = Factura.objects.get(id = id_factura['id_factura'])
#                         if current_comprobante.Estado == 'Creada':
#                             crear_factura_operador=True
#                             current_comprobante.Estado = 'Asignada'
#                             current_comprobante.save()
#                             factura_operador.Facturas_Destinatarios.add(current_comprobante)
#                             factura_operador.Importe += current_comprobante.Importe_Total_Factura
#                             factura_operador.save()

#                     # -----------------------------------------------
                  
#                 # Registro de trazas
#                 save_addition(request.user, 'entrega', form_entrega_instance.id, str(model_to_dict(form_entrega_instance)))
#                 save_addition(request.user, 'factura_operador', factura_operador.id, str(model_to_dict(factura_operador)))
#                 # save_addition(request.user, 'factura', current_comprobante.id, str(model_to_dict(current_comprobante)))

#                 messages.success(request, 'Traslado programado satisfactoriamente')
#                 if lista_inventarios_por_persona_sin_aranceles:
#                     lista_inventarios = []
#                     hbl = ''
#                     lista = ''
#                     for x in lista_inventarios_por_persona_sin_aranceles:
#                         lista_inventarios.append(x['HBL'])
#                         hbl = 'Los HBL relacionados carecen de aranceles aduanales: '
#                         lista = x['HBL'] + ', '
#                     hbl = hbl + lista
#                     messages.warning(request,hbl)
                
#                 # messages.warning(request, 'Los siguientes HBL fueron facturados previamente' + lista_inventarios_por_persona_facturados)
#                 return redirect(reverse('entrega_detail', kwargs={"id_entrega": form_entrega_instance.id}))
#             # except Exception as inst:
#             #     print(inst)
#             #     messages.error(request, 'Ha ocurrido un error programando el traslado')
#             #     return redirect(request.path) 

#     ctx = {'lista_inventarios_por_persona_sin_aranceles':lista_inventarios_por_persona_sin_aranceles,'action': action,'factura_filter':factura_filter,'form_entrega': form_entrega,'form_hbl_escaneados':form_hbl_escaneados,'form_empresa':form_empresa, 'active_menu': active_menu, 'facturas': facturas}
#     return render(request, 'entrega/entrega_edit.html', ctx)


@login_required(login_url='login')
def entrega_monta_facturacion_add(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Definiendo menu activo
    active_menu = 'mercancia_traslado'

    action = 'add'
    form_entrega   = Entrega_Form(initial={'Fecha_Entrega': now().date(), 'Hora_Salida': datetime.now().strftime('%H:%M')})
    form_empresa = Empresa_Form()
    form_hbl_escaneados = HBL_Escaneados_Form()
    factura_filter = FacturaFilter()
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
    
    #Aplicacion de filtros
    facturas_filter = FacturaFilter(request.GET, queryset=facturas)
    facturas = facturas_filter.qs
    lista_inventarios_por_persona_sin_aranceles =''
    if request.method == 'POST':
        form_entrega   = Entrega_Form(request.POST)
        hbl_escaneados = request.POST.get('crear_traslado_escaner_qr')            
        if form_entrega.is_valid():
            chapa = request.POST.get('Chapa')
            transportista = request.POST.get('Transportista')
            if chapa:
                # existe = Transportista.objects.filter(id=transportista,Chapa=chapa)
                existe = Chapa.objects.filter(transportista=transportista,Chapa=chapa)

                if not existe:
                    messages.error(request, 'La chapa introduciada no corresponde al transportista seleccionado ')
                    return redirect(request.path) 
            if not hbl_escaneados:
                if len(request.POST.getlist('factura')) == 0:
                    messages.error(request, 'Debe seleccionar al menos una factura')
                    return redirect(request.path) 
            # try:
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
                entrega=Entrega.objects.get(Factura_Operador__id=factura_operador.id)
                entrega.Chapa=chapa
                entrega.save()

                if not hbl_escaneados:
                    #Agregando listado de comprobantes
                    for current_comprobante_id in request.POST.getlist('factura'):
                        current_comprobante = Factura.objects.get(pk = current_comprobante_id)
                        current_comprobante.Estado = 'Asignada'
                        current_comprobante.save()
                        factura_operador.Facturas_Destinatarios.add(current_comprobante)
                        factura_operador.Importe += current_comprobante.Importe_Total_Factura
                        destinos = current_comprobante.Inventario.all()[:1]
                        for destino in destinos:
                            factura_operador.Provincia =destino.Destinatario.Provincia 
                        factura_operador.save()

                else:
                    # -----------------------------------------------
                    HBL_regex = re.compile(r'([A-Z0-9.\/-]*)')
                    #Obteniendo listado de HBL
                    list_hbl_barra = request.POST.get('HBL')
                    seleccion_barra = re.findall(HBL_regex,list_hbl_barra)
                    seleccion_barra = set(seleccion_barra)
                    
                    #Verificando que esten nacionalizados los HBL
                    hbl_facturados = Factura_Inventario.objects.filter(Inventario__HBL__in=seleccion_barra).values_list('Inventario__HBL')
                    hbl_nacionalizados = Inventario.objects.filter(~Q(Importe_Servicio_aduanal='0'),Nacionalizado=True,HBL__in=seleccion_barra).exclude(HBL__in=hbl_facturados)
                    if hbl_nacionalizados:
                        #
                    #print('no hay hbl')

                        #Lista de facturas a pasar a la vista
                        lista_facturas = []
                        
                        #Obteniendo lista de destinatarios de la solicitud
                        lista_de_destinatarios = [] #Lista de destinatarios
                        for current_inventario in hbl_nacionalizados:
                            lista_de_destinatarios.append(current_inventario.Destinatario.CI)
                        lista_de_destinatarios = list(dict.fromkeys(lista_de_destinatarios))
                        lista_inventarios_por_persona_sin_aranceles = hbl_nacionalizados.filter(Q(Importe_Servicio_aduanal__isnull=True)|Q(Importe_Servicio_aduanal__lte=0),Destinatario__CI__in = lista_de_destinatarios).values('HBL')

                        for current_destinatario in lista_de_destinatarios:
                            current_factura = {}
                            current_lista_de_inventarios = []

                            #Cantidad de veces que se mostrara la factura 
                            current_factura['Copias_Facturas'] = range(1)

                            #Valores totales
                            current_factura['Importe_Transcargo_Total'] = 0.00 
                            current_factura['Importe_Seguro_Carga_Total'] = 0.00 
                            current_factura['Importe_Sobredimension_Total'] = 0.00 
                            current_factura['Importe_Recargo_Total'] = 0
                            current_factura['Importe_Transportacion_Total'] = 0.00 
                            current_factura['Importe_Derecho_Aduanal_Total'] = 0.00 
                            current_factura['Importe_Servicio_Aduanal_Total'] = 0.00 
                            current_factura['Cantidad_Bultos_Total'] = 0 

                            lista_inventarios_por_persona = hbl_nacionalizados.filter(Q(Importe_Servicio_aduanal__isnull=False)|Q(Importe_Servicio_aduanal__gt=0),Destinatario__CI = current_destinatario)
                            # +++++++++++++++++++++
                            corresponsal=Agencia.objects.filter(id=lista_inventarios_por_persona.first().Agencia.id).first()
                            current_factura['Corresponsal']=corresponsal
                            destinatario=Destinatario.objects.filter(CI = current_destinatario).first()
                            provincia=Provincia.objects.filter(id=destinatario.Provincia.id).first()

                            current_factura['Provincia']=provincia
                            # ++++++++++++++++++++++
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
                                    current_factura['Importe_Transcargo_Total'] = 0.00
                                    current_factura['Importe_Seguro_Carga_Total'] = 0.00
                                    current_factura['Importe_Sobredimension_Total'] = 0.00
                                    current_factura['Importe_Recargo_Total'] = 0.00
                                    current_factura['Importe_Transportacion_Total'] = 0.00
                                    current_factura['Cantidad_Bultos_Total'] += current_inventario.Cantidad_Bultos
                                    current_factura['Importe_KG_Adicional_Total'] = 0.00
                                    #Agregando informacion a la lista
                                    current_inventario_dict['Importe_Seguro_Carga'] = 0.00
                                    current_inventario_dict['Importe_Sobredimension'] = 0.00
                                    current_inventario_dict['Importe_Transportacion'] = 0.00
                                    current_inventario_dict['Importe_Transcargo'] = 0.00
                                    current_inventario_dict['Importe_KG_Adicional'] = 0.00
                                    current_lista_de_inventarios.append(current_inventario_dict)
                                    if current_inventario.Peso:
                                        if current_inventario.Peso < 20.00:
                                            current_inventario.Importe_Kg_Adicional = current_inventario_dict['Importe_KG_Adicional']
                                            current_inventario.save()
                                            current_factura['Importe_KG_Adicional_Total'] += current_inventario_dict['Importe_KG_Adicional']
                                        elif current_inventario.Peso > 20.00:
                                            kg_adicional = current_inventario.Peso - 20
                                            current_inventario_dict['Importe_KG_Adicional'] = kg_adicional * 5
                                            #print('current_inventario_dict[Importe_KG_Adicional]',current_inventario_dict['Importe_KG_Adicional'])
                                            current_inventario.Importe_Kg_Adicional = kg_adicional * 5
                                            current_inventario.save()
                                            #print('current_inventario_dict[Importe_KG_Adicional]',current_inventario_dict['Importe_KG_Adicional'])
                                            current_factura['Importe_KG_Adicional_Total'] += current_inventario_dict['Importe_KG_Adicional']
                                    else:
                                        current_inventario.Importe_Kg_Adicional = current_inventario_dict['Importe_KG_Adicional']
                                        current_inventario.save()
                                        current_factura['Importe_KG_Adicional_Total'] += current_inventario_dict['Importe_KG_Adicional']

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
                                    # factura_instance.Importe_Kg_Adicional_Total = current_factura['Importe_Kg_Adicional_Total']
                                    #factura_instance.url = str(request.path) + '?cargos_extra=' + str(current_factura['Importe_Recargo_Total'])
                                    factura_instance.Agencia=current_factura['Corresponsal']
                                    factura_instance.Provincia=current_factura['Provincia']
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
                            qr_generado = '{' + str(factura_instance.id) +'}'
                            # qr_generado = '{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}'
                            current_factura['id_factura'] = factura_instance.id
                            current_factura['facturador'] = factura_instance.User_Facturador.get_full_name()
                            
                            #Agregando factura a lista general de facturas
                            lista_facturas.append(current_factura)
                        
                        for id_factura in lista_facturas:
                            # if id_factura:
                            current_comprobante = Factura.objects.get(id = id_factura['id_factura'])
                            if current_comprobante.Estado == 'Creada':
                                crear_factura_operador=True
                                current_comprobante.Estado = 'Asignada'
                                current_comprobante.save()
                                factura_operador.Facturas_Destinatarios.add(current_comprobante)
                                factura_operador.Importe += current_comprobante.Importe_Total_Factura
                                factura_operador.save()

                            save_addition(request.user, 'factura', current_comprobante.id, str(model_to_dict(current_comprobante)))

                            
                        # Registro de trazas
                        save_addition(request.user, 'entrega', form_entrega_instance.id, str(model_to_dict(form_entrega_instance)))
                        save_addition(request.user, 'factura_operador', factura_operador.id, str(model_to_dict(factura_operador)))

                        messages.success(request, 'Traslado programado satisfactoriamente')
                        if lista_inventarios_por_persona_sin_aranceles:
                            lista_inventarios = []
                            hbl = ''
                            lista = ''
                            for x in lista_inventarios_por_persona_sin_aranceles:
                                lista_inventarios.append(x['HBL'])
                                hbl = 'Los HBL relacionados carecen de aranceles aduanales: '
                                lista = x['HBL'] + ', '
                            hbl = hbl + lista
                            messages.warning(request,hbl)
                        return redirect(reverse('entrega_detail', kwargs={"id_entrega": form_entrega_instance.id}))
                    if not hbl_nacionalizados:
                        messages.warning(request, 'Traslado no creado. Los HBL ya fueron facturados y agregados a una monta')
                        return redirect(reverse('entrega_list'))

            # except Exception as inst:
            #     print(inst)
            #     messages.error(request, 'Ha ocurrido un error programando el traslado')
            #     return redirect(request.path) 

    ctx = {'lista_inventarios_por_persona_sin_aranceles':lista_inventarios_por_persona_sin_aranceles,'action': action,'factura_filter':factura_filter,'form_entrega': form_entrega,'form_hbl_escaneados':form_hbl_escaneados,'form_empresa':form_empresa, 'active_menu': active_menu, 'facturas': facturas}
    return render(request, 'entrega/entrega_edit.html', ctx)


# --------------Original----------------
# def entrega_monta_facturacion_add(request):
#     #Validando roles
#     if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
#         raise Http404

#     #Definiendo menu activo
#     active_menu = 'mercancia_traslado'

#     action = 'add'
#     form_entrega   = Entrega_Form(initial={'Fecha_Entrega': now().date(), 'Hora_Salida': datetime.now().strftime('%H:%M')})
#     form_empresa = Empresa_Form()
#     form_hbl_escaneados = HBL_Escaneados_Form()
#     factura_filter = FacturaFilter()
#     #list_inventario = Inventario.objects.all().filter(Q(Estado = 'Inventario'), Q(Nacionalizado = True)).order_by('Destinatario__Municipio', 'Destinatario__CI')
#     #Buscando comprobantes de entregas de destinatarios que no estan relacionados en comprobantes de entrega de operadores
#     facturas_disponibles = []
#     with connection.cursor() as cursor:
#         cursor.execute(""" SELECT * FROM "inventario_factura" WHERE id not in 
#                         (
#                         SELECT "inventario_factura_operador_Facturas_Destinatarios"."factura_id" FROM "inventario_factura_operador_Facturas_Destinatarios" 
#                         INNER JOIN "inventario_factura_operador" ON "inventario_factura_operador_Facturas_Destinatarios"."factura_operador_id" = "inventario_factura_operador"."id" 
#                         WHERE not "inventario_factura_operador"."Estado" = 'Desestimada'
#                         ) AND "inventario_factura"."Estado" = 'Creada' """)

#         row = cursor.fetchall()
#         for current in row:
#             facturas_disponibles.append(list(current)[0])
    
#     facturas = Factura.objects.all().filter(Q(id__in = facturas_disponibles)).order_by('id')
    
#     #Aplicacion de filtros
#     facturas_filter = FacturaFilter(request.GET, queryset=facturas)
#     facturas = facturas_filter.qs
#     lista_inventarios_por_persona_sin_aranceles =''
#     if request.method == 'POST':
#         form_entrega   = Entrega_Form(request.POST)
#         hbl_escaneados = request.POST.get('crear_traslado_escaner_qr')            
#         if form_entrega.is_valid():
#             chapa = request.POST.get('Chapa')
#             transportista = request.POST.get('Transportista')
#             if chapa:
#                 # existe = Transportista.objects.filter(id=transportista,Chapa=chapa)
#                 existe = Chapa.objects.filter(transportista=transportista,Chapa=chapa)

#                 if not existe:
#                     messages.error(request, 'La chapa introduciada no corresponde al transportista seleccionado ')
#                     return redirect(request.path) 
#             if not hbl_escaneados:
#                 if len(request.POST.getlist('factura')) == 0:
#                     messages.error(request, 'Debe seleccionar al menos una factura')
#                     return redirect(request.path) 
#             # try:
#             with transaction.atomic():
#                 form_entrega_instance = form_entrega.save(commit=False)

#                 #Almacenando valores
#                 #Factura de operador
#                 factura_operador = Factura_Operador()
#                 factura_operador.Fecha_Creacion = now()
#                 factura_operador.Estado = 'En espera'
#                 factura_operador.Operador = form_entrega.cleaned_data['Operador']
#                 factura_operador.User_Facturador = request.user
#                 factura_operador.save()
#                 # #Traslado
#                 form_entrega_instance.Estado = 'Programado'
#                 form_entrega_instance.Factura_Operador = factura_operador
#                 form_entrega_instance.save()
#                 entrega=Entrega.objects.get(Factura_Operador__id=factura_operador.id)
#                 entrega.Chapa=chapa
#                 entrega.save()

#                 if not hbl_escaneados:
#                     #Agregando listado de comprobantes
#                     for current_comprobante_id in request.POST.getlist('factura'):
#                         current_comprobante = Factura.objects.get(pk = current_comprobante_id)
#                         current_comprobante.Estado = 'Asignada'
#                         current_comprobante.save()
#                         factura_operador.Facturas_Destinatarios.add(current_comprobante)
#                         factura_operador.Importe += current_comprobante.Importe_Total_Factura
#                         destinos = current_comprobante.Inventario.all()[:1]
#                         for destino in destinos:
#                             factura_operador.Provincia =destino.Destinatario.Provincia 
#                         factura_operador.save()

#                 else:
#                     # -----------------------------------------------
#                     HBL_regex = re.compile(r'([A-Z0-9.\/-]*)')
#                     #Obteniendo listado de HBL
#                     list_hbl_barra = request.POST.get('HBL')
#                     seleccion_barra = re.findall(HBL_regex,list_hbl_barra)
#                     seleccion_barra = set(seleccion_barra)
                    
#                     #Verificando que esten nacionalizados los HBL
#                     hbl_nacionalizados = Inventario.objects.filter(HBL__in=seleccion_barra,Nacionalizado=True)
                    
#                     #Lista de facturas a pasar a la vista
#                     lista_facturas = []
                    
#                     #Obteniendo lista de destinatarios de la solicitud
#                     lista_de_destinatarios = [] #Lista de destinatarios
#                     for current_inventario in hbl_nacionalizados:
#                         lista_de_destinatarios.append(current_inventario.Destinatario.CI)
#                     lista_de_destinatarios = list(dict.fromkeys(lista_de_destinatarios))
#                     lista_inventarios_por_persona_sin_aranceles = hbl_nacionalizados.filter(Q(Importe_Servicio_aduanal__isnull=True)|Q(Importe_Servicio_aduanal__lte=0),Destinatario__CI__in = lista_de_destinatarios).values('HBL')

#                     for current_destinatario in lista_de_destinatarios:
#                         current_factura = {}
#                         current_lista_de_inventarios = []

#                         #Cantidad de veces que se mostrara la factura 
#                         current_factura['Copias_Facturas'] = range(1)

#                         #Valores totales
#                         current_factura['Importe_Transcargo_Total'] = 0.00 
#                         current_factura['Importe_Seguro_Carga_Total'] = 0.00 
#                         current_factura['Importe_Sobredimension_Total'] = 0.00 
#                         current_factura['Importe_Recargo_Total'] = 0
#                         current_factura['Importe_Transportacion_Total'] = 0.00 
#                         current_factura['Importe_Derecho_Aduanal_Total'] = 0.00 
#                         current_factura['Importe_Servicio_Aduanal_Total'] = 0.00 
#                         current_factura['Cantidad_Bultos_Total'] = 0 

#                         lista_inventarios_por_persona = hbl_nacionalizados.filter(Q(Importe_Servicio_aduanal__isnull=False)|Q(Importe_Servicio_aduanal__gt=0),Destinatario__CI = current_destinatario)
#                         # +++++++++++++++++++++
#                         corresponsal=Agencia.objects.filter(id=lista_inventarios_por_persona.first().Agencia.id).first()
#                         current_factura['Corresponsal']=corresponsal
#                         destinatario=Destinatario.objects.filter(CI = current_destinatario).first()
#                         provincia=Provincia.objects.filter(id=destinatario.Provincia.id).first()

#                         current_factura['Provincia']=provincia
#                         # ++++++++++++++++++++++
#                         for current_inventario in lista_inventarios_por_persona:
#                             current_inventario_dict = {}
#                             current_inventario_dict['Inventario'] = current_inventario

#                             #Calculando el importe por derechos aduanales
#                             if current_inventario.Importe_Derecho_aduanal:
#                                 current_factura['Importe_Derecho_Aduanal_Total'] += current_inventario.Importe_Derecho_aduanal

#                             #Calculando el importe por servicios aduanales
#                             if current_inventario.Importe_Servicio_aduanal:
#                                 current_factura['Importe_Servicio_Aduanal_Total'] += current_inventario.Importe_Servicio_aduanal
#                             if current_inventario.isPrepago:
#                                 current_factura['Importe_Transcargo_Total'] = 0.00
#                                 current_factura['Importe_Seguro_Carga_Total'] = 0.00
#                                 current_factura['Importe_Sobredimension_Total'] = 0.00
#                                 current_factura['Importe_Recargo_Total'] = 0.00
#                                 current_factura['Importe_Transportacion_Total'] = 0.00
#                                 current_factura['Cantidad_Bultos_Total'] += current_inventario.Cantidad_Bultos
#                                 current_factura['Importe_KG_Adicional_Total'] = 0.00
#                                 #Agregando informacion a la lista
#                                 current_inventario_dict['Importe_Seguro_Carga'] = 0.00
#                                 current_inventario_dict['Importe_Sobredimension'] = 0.00
#                                 current_inventario_dict['Importe_Transportacion'] = 0.00
#                                 current_inventario_dict['Importe_Transcargo'] = 0.00
#                                 current_lista_de_inventarios.append(current_inventario_dict)
#                                 if current_inventario.Peso:
#                                     if current_inventario.Peso < 20.00:
#                                         current_inventario_dict['Importe_KG_Adicional'] = 0.00
#                                     if current_inventario.Peso > 20.00:
#                                         kg_adicional = current_inventario.Peso - 20
#                                         current_inventario_dict['Importe_KG_Adicional'] = kg_adicional * 5
#                                         current_inventario.Importe_Kg_Adicional = kg_adicional * 5
#                                         current_inventario.save()
#                                     current_factura['Importe_KG_Adicional_Total'] += current_inventario_dict['Importe_KG_Adicional']
#                                 else:
#                                     current_inventario_dict['Importe_KG_Adicional'] = 0.00
#                             else:    
#                                 #Calculando precio por seguro de carga
#                                 if current_inventario.Peso:
#                                     if current_inventario.Peso <= 1.50:
#                                         current_inventario_dict['Importe_Seguro_Carga'] = 0.00
#                                     if current_inventario.Peso > 1.50:
#                                         current_inventario_dict['Importe_Seguro_Carga'] = 12.00

#                                     current_factura['Importe_Seguro_Carga_Total'] += current_inventario_dict['Importe_Seguro_Carga']
#                                 else:
#                                     current_inventario_dict['Importe_Seguro_Carga'] = 0.00
                                
#                                 #Calculando precio por sobredimension
#                                 if current_inventario.Peso:
#                                     if current_inventario.Peso < 30.00:
#                                         current_inventario_dict['Importe_Sobredimension'] = 0.00
#                                     if current_inventario.Peso >= 30.00:
#                                         current_inventario_dict['Importe_Sobredimension'] = 70.00

#                                     current_factura['Importe_Sobredimension_Total'] += current_inventario_dict['Importe_Sobredimension']
#                                 else:
#                                     current_inventario_dict['Importe_Sobredimension'] = 0.00
#                                 #Calculando precio por transportacion
#                                 if current_inventario.Peso and request.POST.get('incluir_transportacion') == 'on':        
#                                     if current_inventario.Destinatario.Municipio.Importe_por_entrega:
#                                         current_inventario_dict['Importe_Transportacion'] = float(current_inventario.Destinatario.Municipio.Importe_por_entrega)
#                                         if request.POST.get('trasbordo') == 'on' or current_inventario.trasbordo == True:
#                                             current_inventario.trasbordo = True
#                                             current_inventario.save()
#                                             if current_inventario.Destinatario.Municipio.Importe_por_trasbordo:                                            
#                                                 current_inventario_dict['Importe_Transportacion'] += float(current_inventario.Destinatario.Municipio.Importe_por_trasbordo)
                                    
#                                     else:
#                                         current_inventario_dict['Importe_Transportacion'] = 0.00
#                                     current_factura['Importe_Transportacion_Total'] += float(current_inventario_dict['Importe_Transportacion'])
                                
#                                 else:
#                                     current_inventario_dict['Importe_Transportacion'] = 0.00
#                                 #Calculando el importe de transcargo
#                                 if current_inventario.Peso:
#                                     if current_inventario.Peso <= 1.50:
#                                         if current_inventario.Importe_Derecho_aduanal > 0:
#                                             current_inventario_dict['Importe_Transcargo'] = round((80.00 + (float(current_inventario.Importe_Derecho_aduanal) * 1.10)/100 + (float(current_inventario.Importe_Servicio_aduanal) * 1.10)/100), 2)
#                                         else:
#                                             current_inventario_dict['Importe_Transcargo'] = 80.00

#                                     if current_inventario.Peso > 1.50 and current_inventario.Peso <= 50.00:
#                                         current_inventario_dict['Importe_Transcargo'] = round((199.00 + float(current_inventario.Peso) * 12.00 + (float(current_inventario.Importe_Derecho_aduanal) * 1.10)/100 + (float(current_inventario.Importe_Servicio_aduanal) * 1.10)/100), 2)
#                                     if current_inventario.Peso > 50.00:
#                                         current_inventario_dict['Importe_Transcargo'] = round((800.00 + (float(current_inventario.Importe_Derecho_aduanal) * 1.10)/100 + (float(current_inventario.Importe_Servicio_aduanal) * 1.10)/100), 2)
                                
#                                     current_factura['Importe_Transcargo_Total'] += current_inventario_dict['Importe_Transcargo']
#                                 else:
#                                     current_inventario_dict['Importe_Transcargo'] = 0.00

#                                 if current_inventario.Peso:
#                                     print('no prepago Importe_KG_Adicional_Total')
#                                     if current_inventario.Peso < 20.00:
#                                         current_inventario_dict['Importe_KG_Adicional'] = 0.00
#                                     if current_inventario.Peso > 20.00:
#                                         kg_adicional = current_inventario.Peso - 20
#                                         current_inventario_dict['Importe_KG_Adicional'] = kg_adicional * 5
#                                         current_inventario.Importe_Kg_Adicional = kg_adicional * 5
#                                         current_inventario.save()
#                                     print(current_inventario_dict['Importe_KG_Adicional'])
#                                     current_factura['Importe_KG_Adicional_Total'] += current_inventario_dict['Importe_KG_Adicional']
#                                 else:
#                                     current_inventario_dict['Importe_KG_Adicional'] = 0.00

#                                 #Calculando total de bultos
#                                 current_factura['Cantidad_Bultos_Total'] += current_inventario.Cantidad_Bultos

#                                 #Agregando informacion a la lista
#                                 current_lista_de_inventarios.append(current_inventario_dict)

#                         current_factura['Destinatario'] = Destinatario.objects.filter(CI = current_destinatario).first()
#                         current_factura['Inventarios'] = current_lista_de_inventarios
#                         #Valor total de la factura
#                         current_factura['Precio_Total_Factura'] = current_factura['Importe_Transcargo_Total'] + current_factura['Importe_Seguro_Carga_Total'] + current_factura['Importe_Sobredimension_Total'] + current_factura['Importe_Recargo_Total'] + current_factura['Importe_Transportacion_Total'] + current_factura['Importe_Derecho_Aduanal_Total'] + current_factura['Importe_Servicio_Aduanal_Total']

#                         try:
#                             with transaction.atomic():
#                                 #Almacenando la factura en el sistema
#                                 factura_instance = Factura()
#                                 factura_instance.Contenido = str(current_factura)
#                                 factura_instance.isMultiple = True
#                                 factura_instance.isEnvio = True
#                                 factura_instance.Fecha = now()
#                                 factura_instance.User_Facturador = request.user
#                                 factura_instance.Estado = 'Creada'
#                                 factura_instance.Destinatario = current_factura['Destinatario']
#                                 factura_instance.Importe_Total_Factura = current_factura['Precio_Total_Factura']
#                                 factura_instance.Importe_Transcargo_Total = current_factura['Importe_Transcargo_Total']
#                                 factura_instance.Importe_Seguro_Carga_Total = current_factura['Importe_Seguro_Carga_Total']
#                                 factura_instance.Importe_Recargo_Total = current_factura['Importe_Recargo_Total']
#                                 factura_instance.Importe_Transportacion_Total = current_factura['Importe_Transportacion_Total']
#                                 factura_instance.Importe_Derecho_Aduanal_Total = current_factura['Importe_Derecho_Aduanal_Total']
#                                 factura_instance.Importe_Servicio_Aduanal_Total = current_factura['Importe_Servicio_Aduanal_Total']
#                                 factura_instance.Importe_Sobredimension_Total = current_factura['Importe_Sobredimension_Total']
#                                 factura_instance.Cantidad_Bultos_Total = current_factura['Cantidad_Bultos_Total']
#                                 # factura_instance.Importe_Kg_Adicional_Total = current_factura['Importe_Kg_Adicional_Total']
#                                 #factura_instance.url = str(request.path) + '?cargos_extra=' + str(current_factura['Importe_Recargo_Total'])
#                                 factura_instance.Agencia=current_factura['Corresponsal']
#                                 factura_instance.Provincia=current_factura['Provincia']
#                                 factura_instance.save()
                                    
#                                 for current_inventario_object in current_factura['Inventarios']:
#                                     factura_inventario_instance = Factura_Inventario()
#                                     factura_inventario_instance.Factura = factura_instance
#                                     factura_inventario_instance.Inventario = current_inventario_object['Inventario']
#                                     factura_inventario_instance.Importe_Seguro_Carga = current_inventario_object['Importe_Seguro_Carga']
#                                     factura_inventario_instance.Importe_Sobredimension = current_inventario_object['Importe_Sobredimension']
#                                     factura_inventario_instance.Importe_Transportacion = current_inventario_object['Importe_Transportacion']
#                                     factura_inventario_instance.Importe_Transcargo = current_inventario_object['Importe_Transcargo']
#                                     factura_inventario_instance.save()

#                                 # Registro de trazas
#                                 save_addition(request.user, 'factura', factura_instance.id, str(model_to_dict(factura_instance)))
#                         except:
#                             raise ValueError('Ha ocurrido un error generando la factura')

#                         #Generando codigo QR de la factura
#                         # qr = qrcode.QRCode()
#                         # qr.add_data('{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}')
#                         # qr.make()
#                         # img = qr.make_image()
#                         # img.save(MEDIA_ROOT +'/QR/factura_' + str(factura_instance.id) +'.png')
#                         qr_generado = '{' + str(factura_instance.id) +'}'
#                         # qr_generado = '{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}'
#                         current_factura['id_factura'] = factura_instance.id
#                         current_factura['facturador'] = factura_instance.User_Facturador.get_full_name()
                        
#                         #Agregando factura a lista general de facturas
#                         lista_facturas.append(current_factura)
                    
#                     for id_factura in lista_facturas:
#                         # if id_factura:
#                         current_comprobante = Factura.objects.get(id = id_factura['id_factura'])
#                         if current_comprobante.Estado == 'Creada':
#                             crear_factura_operador=True
#                             current_comprobante.Estado = 'Asignada'
#                             current_comprobante.save()
#                             factura_operador.Facturas_Destinatarios.add(current_comprobante)
#                             factura_operador.Importe += current_comprobante.Importe_Total_Factura
#                             factura_operador.save()
#                             save_addition(request.user, 'factura', current_comprobante.id, str(model_to_dict(current_comprobante)))

                        



                    
#                 # Registro de trazas
#                 save_addition(request.user, 'entrega', form_entrega_instance.id, str(model_to_dict(form_entrega_instance)))
#                 save_addition(request.user, 'factura_operador', factura_operador.id, str(model_to_dict(factura_operador)))

#                 messages.success(request, 'Traslado programado satisfactoriamente')
#                 if lista_inventarios_por_persona_sin_aranceles:
#                     lista_inventarios = []
#                     hbl = ''
#                     lista = ''
#                     for x in lista_inventarios_por_persona_sin_aranceles:
#                         lista_inventarios.append(x['HBL'])
#                         hbl = 'Los HBL relacionados carecen de aranceles aduanales: '
#                         lista = x['HBL'] + ', '
#                     hbl = hbl + lista
#                     messages.warning(request,hbl)
#                 return redirect(reverse('entrega_detail', kwargs={"id_entrega": form_entrega_instance.id}))
#             # except Exception as inst:
#             #     print(inst)
#             #     messages.error(request, 'Ha ocurrido un error programando el traslado')
#             #     return redirect(request.path) 

#     ctx = {'lista_inventarios_por_persona_sin_aranceles':lista_inventarios_por_persona_sin_aranceles,'action': action,'factura_filter':factura_filter,'form_entrega': form_entrega,'form_hbl_escaneados':form_hbl_escaneados,'form_empresa':form_empresa, 'active_menu': active_menu, 'facturas': facturas}
#     return render(request, 'entrega/entrega_edit.html', ctx)

# --------------------------------------------------
# @login_required(login_url='login')
# def entrega_monta_facturacion_add(request):
#     #Validando roles
#     if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
#         raise Http404

#     #Definiendo menu activo
#     active_menu = 'mercancia_traslado'

#     action = 'add'
#     form_entrega   = Entrega_Form(initial={'Fecha_Entrega': now().date(), 'Hora_Salida': datetime.now().strftime('%H:%M')})
#     form_empresa = Empresa_Form()
#     form_hbl_escaneados = HBL_Escaneados_Form()
#     factura_filter = FacturaFilter()
#     #list_inventario = Inventario.objects.all().filter(Q(Estado = 'Inventario'), Q(Nacionalizado = True)).order_by('Destinatario__Municipio', 'Destinatario__CI')
#     #Buscando comprobantes de entregas de destinatarios que no estan relacionados en comprobantes de entrega de operadores
#     facturas_disponibles = []
#     with connection.cursor() as cursor:
#         cursor.execute(""" SELECT * FROM "inventario_factura" WHERE id not in 
#                         (
#                         SELECT "inventario_factura_operador_Facturas_Destinatarios"."factura_id" FROM "inventario_factura_operador_Facturas_Destinatarios" 
#                         INNER JOIN "inventario_factura_operador" ON "inventario_factura_operador_Facturas_Destinatarios"."factura_operador_id" = "inventario_factura_operador"."id" 
#                         WHERE not "inventario_factura_operador"."Estado" = 'Desestimada'
#                         ) AND "inventario_factura"."Estado" = 'Creada' """)

#         row = cursor.fetchall()
#         for current in row:
#             facturas_disponibles.append(list(current)[0])
    
#     facturas = Factura.objects.all().filter(Q(id__in = facturas_disponibles)).order_by('id')
    
#     #Aplicacion de filtros
#     facturas_filter = FacturaFilter(request.GET, queryset=facturas)
#     facturas = facturas_filter.qs
#     lista_inventarios_por_persona_sin_aranceles =''
#     if request.method == 'POST':
#         form_entrega   = Entrega_Form(request.POST)
#         hbl_escaneados = request.POST.get('crear_traslado_escaner_qr')            
#         if form_entrega.is_valid():
#             chapa = request.POST.get('Chapa')
#             transportista = request.POST.get('Transportista')
#             if chapa:
#                 # existe = Transportista.objects.filter(id=transportista,Chapa=chapa)
#                 existe = Chapa.objects.filter(transportista=transportista,Chapa=chapa)

#                 if not existe:
#                     messages.error(request, 'La chapa introduciada no corresponde al transportista seleccionado ')
#                     return redirect(request.path) 
#             if not hbl_escaneados:
#                 if len(request.POST.getlist('factura')) == 0:
#                     messages.error(request, 'Debe seleccionar al menos una factura')
#                     return redirect(request.path) 
#             # try:
#             with transaction.atomic():
#                 form_entrega_instance = form_entrega.save(commit=False)

#                 #Almacenando valores
#                 #Factura de operador
#                 factura_operador = Factura_Operador()
#                 factura_operador.Fecha_Creacion = now()
#                 factura_operador.Estado = 'En espera'
#                 factura_operador.Operador = form_entrega.cleaned_data['Operador']
#                 factura_operador.User_Facturador = request.user
#                 factura_operador.save()
#                 # #Traslado
#                 form_entrega_instance.Estado = 'Programado'
#                 form_entrega_instance.Factura_Operador = factura_operador
#                 form_entrega_instance.save()
#                 entrega=Entrega.objects.get(Factura_Operador__id=factura_operador.id)
#                 entrega.Chapa=chapa
#                 entrega.save()

#                 if not hbl_escaneados:
#                     #Agregando listado de comprobantes
#                     for current_comprobante_id in request.POST.getlist('factura'):
#                         current_comprobante = Factura.objects.get(pk = current_comprobante_id)
#                         current_comprobante.Estado = 'Asignada'
#                         current_comprobante.save()
#                         factura_operador.Facturas_Destinatarios.add(current_comprobante)
#                         factura_operador.Importe += current_comprobante.Importe_Total_Factura
#                         destinos = current_comprobante.Inventario.all()[:1]
#                         for destino in destinos:
#                             factura_operador.Provincia =destino.Destinatario.Provincia 
#                         factura_operador.save()

#                 else:
#                     # -----------------------------------------------
#                     HBL_regex = re.compile(r'([A-Z0-9.\/-]*)')
#                     #Obteniendo listado de HBL
#                     list_hbl_barra = request.POST.get('HBL')
#                     seleccion_barra = re.findall(HBL_regex,list_hbl_barra)
#                     seleccion_barra = set(seleccion_barra)
                    
#                     #Verificando que esten nacionalizados los HBL
#                     hbl_nacionalizados = Inventario.objects.filter(HBL__in=seleccion_barra,Nacionalizado=True)
                    
#                     #Lista de facturas a pasar a la vista
#                     lista_facturas = []
                    
#                     #Obteniendo lista de destinatarios de la solicitud
#                     lista_de_destinatarios = [] #Lista de destinatarios
#                     for current_inventario in hbl_nacionalizados:
#                         lista_de_destinatarios.append(current_inventario.Destinatario.CI)
#                     lista_de_destinatarios = list(dict.fromkeys(lista_de_destinatarios))
#                     lista_inventarios_por_persona_sin_aranceles = hbl_nacionalizados.filter(Q(Importe_Servicio_aduanal__isnull=True)|Q(Importe_Servicio_aduanal__lte=0),Destinatario__CI__in = lista_de_destinatarios).values('HBL')

#                     for current_destinatario in lista_de_destinatarios:
#                         current_factura = {}
#                         current_lista_de_inventarios = []

#                         #Cantidad de veces que se mostrara la factura 
#                         current_factura['Copias_Facturas'] = range(1)

#                         #Valores totales
#                         current_factura['Importe_Transcargo_Total'] = 0.00 
#                         current_factura['Importe_Seguro_Carga_Total'] = 0.00 
#                         current_factura['Importe_Sobredimension_Total'] = 0.00 
#                         current_factura['Importe_Recargo_Total'] = 0
#                         current_factura['Importe_Transportacion_Total'] = 0.00 
#                         current_factura['Importe_Derecho_Aduanal_Total'] = 0.00 
#                         current_factura['Importe_Servicio_Aduanal_Total'] = 0.00 
#                         current_factura['Cantidad_Bultos_Total'] = 0 

#                         lista_inventarios_por_persona = hbl_nacionalizados.filter(Q(Importe_Servicio_aduanal__isnull=False)|Q(Importe_Servicio_aduanal__gt=0),Destinatario__CI = current_destinatario)
#                         # +++++++++++++++++++++
#                         corresponsal=Agencia.objects.filter(id=lista_inventarios_por_persona.first().Agencia.id).first()
#                         current_factura['Corresponsal']=corresponsal
#                         destinatario=Destinatario.objects.filter(CI = current_destinatario).first()
#                         provincia=Provincia.objects.filter(id=destinatario.Provincia.id).first()

#                         current_factura['Provincia']=provincia
#                         # ++++++++++++++++++++++
#                         for current_inventario in lista_inventarios_por_persona:
#                             current_inventario_dict = {}
#                             current_inventario_dict['Inventario'] = current_inventario

#                             #Calculando el importe por derechos aduanales
#                             if current_inventario.Importe_Derecho_aduanal:
#                                 current_factura['Importe_Derecho_Aduanal_Total'] += current_inventario.Importe_Derecho_aduanal

#                             #Calculando el importe por servicios aduanales
#                             if current_inventario.Importe_Servicio_aduanal:
#                                 current_factura['Importe_Servicio_Aduanal_Total'] += current_inventario.Importe_Servicio_aduanal
#                             if current_inventario.isPrepago:
#                                 current_factura['Importe_Transcargo_Total'] = 0.00
#                                 current_factura['Importe_Seguro_Carga_Total'] = 0.00
#                                 current_factura['Importe_Sobredimension_Total'] = 0.00
#                                 current_factura['Importe_Recargo_Total'] = 0.00
#                                 current_factura['Importe_Transportacion_Total'] = 0.00
#                                 current_factura['Cantidad_Bultos_Total'] += current_inventario.Cantidad_Bultos
#                                 current_factura['Importe_KG_Adicional_Total'] = 0.00
#                                 #Agregando informacion a la lista
#                                 current_inventario_dict['Importe_Seguro_Carga'] = 0.00
#                                 current_inventario_dict['Importe_Sobredimension'] = 0.00
#                                 current_inventario_dict['Importe_Transportacion'] = 0.00
#                                 current_inventario_dict['Importe_Transcargo'] = 0.00
#                                 current_lista_de_inventarios.append(current_inventario_dict)
#                                 if current_inventario.Peso:
#                                     if current_inventario.Peso < 20.00:
#                                         current_inventario_dict['Importe_KG_Adicional'] = 0.00
#                                     if current_inventario.Peso > 20.00:
#                                         kg_adicional = current_inventario.Peso - 20
#                                         current_inventario_dict['Importe_KG_Adicional'] = kg_adicional * 5
#                                         current_inventario.Importe_Kg_Adicional = kg_adicional * 5
#                                         current_inventario.save()
#                                     current_factura['Importe_KG_Adicional_Total'] += current_inventario_dict['Importe_KG_Adicional']
#                                 else:
#                                     current_inventario_dict['Importe_KG_Adicional'] = 0.00
#                             else:    
#                                 #Calculando precio por seguro de carga
#                                 if current_inventario.Peso:
#                                     if current_inventario.Peso <= 1.50:
#                                         current_inventario_dict['Importe_Seguro_Carga'] = 0.00
#                                     if current_inventario.Peso > 1.50:
#                                         current_inventario_dict['Importe_Seguro_Carga'] = 12.00

#                                     current_factura['Importe_Seguro_Carga_Total'] += current_inventario_dict['Importe_Seguro_Carga']
#                                 else:
#                                     current_inventario_dict['Importe_Seguro_Carga'] = 0.00
                                
#                                 #Calculando precio por sobredimension
#                                 if current_inventario.Peso:
#                                     if current_inventario.Peso < 30.00:
#                                         current_inventario_dict['Importe_Sobredimension'] = 0.00
#                                     if current_inventario.Peso >= 30.00:
#                                         current_inventario_dict['Importe_Sobredimension'] = 70.00

#                                     current_factura['Importe_Sobredimension_Total'] += current_inventario_dict['Importe_Sobredimension']
#                                 else:
#                                     current_inventario_dict['Importe_Sobredimension'] = 0.00
#                                 #Calculando precio por transportacion
#                                 if current_inventario.Peso and request.POST.get('incluir_transportacion') == 'on':        
#                                     if current_inventario.Destinatario.Municipio.Importe_por_entrega:
#                                         current_inventario_dict['Importe_Transportacion'] = float(current_inventario.Destinatario.Municipio.Importe_por_entrega)
#                                         if request.POST.get('trasbordo') == 'on' or current_inventario.trasbordo == True:
#                                             current_inventario.trasbordo = True
#                                             current_inventario.save()
#                                             if current_inventario.Destinatario.Municipio.Importe_por_trasbordo:                                            
#                                                 current_inventario_dict['Importe_Transportacion'] += float(current_inventario.Destinatario.Municipio.Importe_por_trasbordo)
                                    
#                                     else:
#                                         current_inventario_dict['Importe_Transportacion'] = 0.00
#                                     current_factura['Importe_Transportacion_Total'] += float(current_inventario_dict['Importe_Transportacion'])
                                
#                                 else:
#                                     current_inventario_dict['Importe_Transportacion'] = 0.00
#                                 #Calculando el importe de transcargo
#                                 if current_inventario.Peso:
#                                     if current_inventario.Peso <= 1.50:
#                                         if current_inventario.Importe_Derecho_aduanal > 0:
#                                             current_inventario_dict['Importe_Transcargo'] = round((80.00 + (float(current_inventario.Importe_Derecho_aduanal) * 1.10)/100 + (float(current_inventario.Importe_Servicio_aduanal) * 1.10)/100), 2)
#                                         else:
#                                             current_inventario_dict['Importe_Transcargo'] = 80.00

#                                     if current_inventario.Peso > 1.50 and current_inventario.Peso <= 50.00:
#                                         current_inventario_dict['Importe_Transcargo'] = round((199.00 + float(current_inventario.Peso) * 12.00 + (float(current_inventario.Importe_Derecho_aduanal) * 1.10)/100 + (float(current_inventario.Importe_Servicio_aduanal) * 1.10)/100), 2)
#                                     if current_inventario.Peso > 50.00:
#                                         current_inventario_dict['Importe_Transcargo'] = round((800.00 + (float(current_inventario.Importe_Derecho_aduanal) * 1.10)/100 + (float(current_inventario.Importe_Servicio_aduanal) * 1.10)/100), 2)
                                
#                                     current_factura['Importe_Transcargo_Total'] += current_inventario_dict['Importe_Transcargo']
#                                 else:
#                                     current_inventario_dict['Importe_Transcargo'] = 0.00

#                                 if current_inventario.Peso:
#                                     if current_inventario.Peso < 20.00:
#                                         current_inventario_dict['Importe_KG_Adicional'] = 0.00
#                                     if current_inventario.Peso > 20.00:
#                                         kg_adicional = current_inventario.Peso - 20
#                                         current_inventario_dict['Importe_KG_Adicional'] = kg_adicional * 5
#                                         current_inventario.Importe_Kg_Adicional = kg_adicional * 5
#                                         current_inventario.save()
#                                     current_factura['Importe_KG_Adicional_Total'] += current_inventario_dict['Importe_KG_Adicional']
#                                 else:
#                                     current_inventario_dict['Importe_KG_Adicional'] = 0.00

#                                 #Calculando total de bultos
#                                 current_factura['Cantidad_Bultos_Total'] += current_inventario.Cantidad_Bultos

#                                 #Agregando informacion a la lista
#                                 current_lista_de_inventarios.append(current_inventario_dict)

#                         current_factura['Destinatario'] = Destinatario.objects.filter(CI = current_destinatario).first()
#                         current_factura['Inventarios'] = current_lista_de_inventarios
#                         #Valor total de la factura
#                         current_factura['Precio_Total_Factura'] = current_factura['Importe_Transcargo_Total'] + current_factura['Importe_Seguro_Carga_Total'] + current_factura['Importe_Sobredimension_Total'] + current_factura['Importe_Recargo_Total'] + current_factura['Importe_Transportacion_Total'] + current_factura['Importe_Derecho_Aduanal_Total'] + current_factura['Importe_Servicio_Aduanal_Total']

#                         try:
#                             with transaction.atomic():
#                                 #Almacenando la factura en el sistema
#                                 factura_instance = Factura()
#                                 factura_instance.Contenido = str(current_factura)
#                                 factura_instance.isMultiple = True
#                                 factura_instance.isEnvio = True
#                                 factura_instance.Fecha = now()
#                                 factura_instance.User_Facturador = request.user
#                                 factura_instance.Estado = 'Creada'
#                                 factura_instance.Destinatario = current_factura['Destinatario']
#                                 factura_instance.Importe_Total_Factura = current_factura['Precio_Total_Factura']
#                                 factura_instance.Importe_Transcargo_Total = current_factura['Importe_Transcargo_Total']
#                                 factura_instance.Importe_Seguro_Carga_Total = current_factura['Importe_Seguro_Carga_Total']
#                                 factura_instance.Importe_Recargo_Total = current_factura['Importe_Recargo_Total']
#                                 factura_instance.Importe_Transportacion_Total = current_factura['Importe_Transportacion_Total']
#                                 factura_instance.Importe_Derecho_Aduanal_Total = current_factura['Importe_Derecho_Aduanal_Total']
#                                 factura_instance.Importe_Servicio_Aduanal_Total = current_factura['Importe_Servicio_Aduanal_Total']
#                                 factura_instance.Importe_Sobredimension_Total = current_factura['Importe_Sobredimension_Total']
#                                 factura_instance.Cantidad_Bultos_Total = current_factura['Cantidad_Bultos_Total']
#                                 # factura_instance.Importe_Kg_Adicional_Total = current_factura['Importe_Kg_Adicional_Total']
#                                 #factura_instance.url = str(request.path) + '?cargos_extra=' + str(current_factura['Importe_Recargo_Total'])
#                                 factura_instance.Agencia=current_factura['Corresponsal']
#                                 factura_instance.Provincia=current_factura['Provincia']
#                                 factura_instance.save()
                                    
#                                 for current_inventario_object in current_factura['Inventarios']:
#                                     factura_inventario_instance = Factura_Inventario()
#                                     factura_inventario_instance.Factura = factura_instance
#                                     factura_inventario_instance.Inventario = current_inventario_object['Inventario']
#                                     factura_inventario_instance.Importe_Seguro_Carga = current_inventario_object['Importe_Seguro_Carga']
#                                     factura_inventario_instance.Importe_Sobredimension = current_inventario_object['Importe_Sobredimension']
#                                     factura_inventario_instance.Importe_Transportacion = current_inventario_object['Importe_Transportacion']
#                                     factura_inventario_instance.Importe_Transcargo = current_inventario_object['Importe_Transcargo']
#                                     factura_inventario_instance.save()

#                                 # Registro de trazas
#                                 save_addition(request.user, 'factura', factura_instance.id, str(model_to_dict(factura_instance)))
#                         except:
#                             raise ValueError('Ha ocurrido un error generando la factura')

#                         #Generando codigo QR de la factura
#                         # qr = qrcode.QRCode()
#                         # qr.add_data('{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}')
#                         # qr.make()
#                         # img = qr.make_image()
#                         # img.save(MEDIA_ROOT +'/QR/factura_' + str(factura_instance.id) +'.png')
#                         qr_generado = '{' + str(factura_instance.id) +'}'
#                         # qr_generado = '{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}'
#                         current_factura['id_factura'] = factura_instance.id
#                         current_factura['facturador'] = factura_instance.User_Facturador.get_full_name()
                        
#                         #Agregando factura a lista general de facturas
#                         lista_facturas.append(current_factura)
#                     #Generando reporte PDF
#                     # template_src = 'pdf/Copia_facturacion_multiple_envios_pdf.html'
#                     # template = get_template(template_src)


#                     # Ok
#                     # context = {'lista_facturas': lista_facturas,'fecha_factura': now(),'request': request,'qr':qr_generado}



#                     # html  = template.render(context)
#                     # result = BytesIO()
#                     # pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
#                     # if not pdf.err:
#                     #     return HttpResponse(result.getvalue(), content_type='application/pdf')
#                     # return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))

#                     # Ok
#                     # return render(request, 'pdf/Copia_facturacion_multiple_envios_pdf.html',context)
#                     for id_factura in lista_facturas:
#                         # if id_factura:
#                         current_comprobante = Factura.objects.get(id = id_factura['id_factura'])
#                         if current_comprobante.Estado == 'Creada':
#                             crear_factura_operador=True
#                             current_comprobante.Estado = 'Asignada'
#                             current_comprobante.save()
#                             factura_operador.Facturas_Destinatarios.add(current_comprobante)
#                             factura_operador.Importe += current_comprobante.Importe_Total_Factura
#                             factura_operador.save()

#                         # context = {'lista_facturas': lista_facturas, 'fecha_factura': current_factura_object.Fecha, 'request': request,'qr':qr_generado}
#                         # html  = template.render(context)
#                         # result = BytesIO()
#                         # pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
#                         # if not pdf.err:
#                         #     return HttpResponse(result.getvalue(), content_type='application/pdf')
#                         # return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))
#                         # return render(request, 'pdf/Copia_facturacion_multiple_envios_pdf.html',context)





#                     # -----------------------------------------------
#                     # id_factura_regex_viejo = re.compile(r'[0-9]*')
#                     # #Expresión regular para teclado en Inglés y en Español
#                     # id_transaccion_regex = re.compile(r'(id_transaccion\": )([0-9]*)|(transaccion\[Ñ )([0-9]*)')
                  
#                     # comprobantes_en_monta = []

#                     # #HBL escaneados
#                     # list_comprobantes_barra = request.POST.get('HBL')   
#                     # list_comprobantes_qr = request.POST.get('HBL_old')   

#                     # print('list_comprobantes',list_comprobantes_barra)
#                     # print('list_comprobantes_viejos',list_comprobantes_qr)
#                     # seleccion_barra =''
#                     # seleccion_qr = ''

#                     # if request.POST.get('HBL_old'):  
#                     #     seleccion_qr = re.findall(id_factura_regex_viejo,list_comprobantes_qr)
#                     #     # seleccion_qr = re.findall(id_factura_regex_viejo,list_comprobantes_qr)
#                     #     seleccion_qr = set(seleccion_qr)
#                     # if request.POST.get('HBL'):
#                     #     seleccion_barra = re.findall(id_factura_regex_viejo,list_comprobantes_barra)
#                     #     # seleccion_barra = re.findall(id_transaccion_regex,list_comprobantes_barra)
#                     #     seleccion_barra = set(seleccion_barra)

#                     # id_facturas = []
#                     # id_comprobante = ''
#                     # for sel in seleccion_barra:
#                     #     print('sel',sel)
#                     #     # #Verifica que en la posición 1 halla un valor numérico (este es para teclado en idioma inglés)
#                     #     # if sel[3].isnumeric():
#                     #     #     # print('sel 1',sel[1])
#                     #     #     id_comprobante = sel[3]
#                     #     #     id_facturas.append(id_comprobante)
#                     #     # if sel[1].isnumeric():
#                     #     #     # print('sel 1',sel[1])
#                     #     #     id_comprobante = sel[1]
#                     #     id_facturas.append(sel)
#                     # for sel in seleccion_qr:                        
#                     #     id_facturas.append(sel)                            
                    
#                     # #Valido que no se repitan los id de factura
#                     # id_facturas=set(id_facturas)   

#                     #     #Guardo los ID de los comprobantes de destinatario
#                     # for id_factura in id_facturas:
#                     #     if id_factura:
#                     #         current_comprobante = Factura.objects.get(pk = id_factura)
#                     #         if current_comprobante.Estado == 'Creada':
#                     #             crear_factura_operador=True
#                     #             current_comprobante.Estado = 'Asignada'
#                     #             current_comprobante.save()
#                     #             factura_operador.Facturas_Destinatarios.add(current_comprobante)
#                     #             factura_operador.Importe += current_comprobante.Importe_Total_Factura
#                     #             factura_operador.save()
#                     #         else:
#                     #             comprobantes_en_monta.append(current_comprobante.id)
#                     # if comprobantes_en_monta:
#                     #     messages.warning(request, 'Las siguientes facturas están asociadas a una monta: ' + str(comprobantes_en_monta).replace('[', '').replace(']', ''))
#                     #     if len(seleccion) == 1:
#                     #         Entrega.objects.filter(Factura_Operador__id=factura_operador.id).delete()
#                     #         Factura_Operador.objects.filter(id=factura_operador.id).delete()
#                     #         # messages.error(request, 'Ha ocurrido un error programando el traslado')
#                     #         return redirect(request.path)  
#                 # Registro de trazas
#                 save_addition(request.user, 'entrega', form_entrega_instance.id, str(model_to_dict(form_entrega_instance)))
#                 save_addition(request.user, 'factura_operador', factura_operador.id, str(model_to_dict(factura_operador)))
#                 save_addition(request.user, 'factura', current_comprobante.id, str(model_to_dict(current_comprobante)))

#                 messages.success(request, 'Traslado programado satisfactoriamente')
#                 if lista_inventarios_por_persona_sin_aranceles:
#                     lista_inventarios = []
#                     hbl = ''
#                     lista = ''
#                     for x in lista_inventarios_por_persona_sin_aranceles:
#                         lista_inventarios.append(x['HBL'])
#                         hbl = 'Los HBL relacionados carecen de aranceles aduanales: '
#                         lista = x['HBL'] + ', '
#                     hbl = hbl + lista
#                     messages.warning(request,hbl)
#                 return redirect(reverse('entrega_detail', kwargs={"id_entrega": form_entrega_instance.id}))
#             # except Exception as inst:
#             #     print(inst)
#             #     messages.error(request, 'Ha ocurrido un error programando el traslado')
#             #     return redirect(request.path) 

#     ctx = {'lista_inventarios_por_persona_sin_aranceles':lista_inventarios_por_persona_sin_aranceles,'action': action,'factura_filter':factura_filter,'form_entrega': form_entrega,'form_hbl_escaneados':form_hbl_escaneados,'form_empresa':form_empresa, 'active_menu': active_menu, 'facturas': facturas}
#     return render(request, 'entrega/entrega_edit.html', ctx)


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
                #print(inst)
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
            current_cita.Estado='Programada'
            current_cita.save()
            # Registro de trazas
            save_addition(request.user, 'cita', current_cita.id, str(model_to_dict(current_cita)))

            messages.success(request, 'Cita programada satisfactoriamente')
            return redirect('cita_programadas')

    #Paginator
    paginator = Paginator(list_inventario, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'action': action, 'form_cita': form_cita, 'active_menu': active_menu, 'page_obj': page_obj}
    return render(request, 'cita/cita_edit.html', ctx)

# def cita_add(request):
#     #Validando roles
#     if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
#         raise Http404

#     #Definiendo menu activo
#     active_menu = 'mercancia_citas'

#     action = 'add'
#     form_cita   = Cita_Form()
#     list_inventario = Inventario.objects.all().filter(Q(Estado = 'Inventario'), Q(Nacionalizado = True))

#     if request.method == 'POST':
#         form_cita   = Cita_Form(request.POST)
        
#         if form_cita.is_valid():
#             #Capturando los inventarios seleccionados
#             list_inventario_selected = request.POST.getlist('inventario')
            
#             #Obteniendo lista de destinatarios de la solicitud
#             lista_de_destinatarios = [] #Lista de destinatarios
#             for current_inventario in Inventario.objects.filter(pk__in = list_inventario_selected):
#                 lista_de_destinatarios.append(current_inventario.Destinatario.CI)
#             lista_de_destinatarios = list(dict.fromkeys(lista_de_destinatarios))
#             print('destinatarios',lista_de_destinatarios)
#             if list_inventario_selected:
#                 for destinatario in lista_de_destinatarios:
#                     print('destinatario',destinatario)
#                     #Almacenando valores
#                     inventarios_selected_objects = Inventario.objects.all().filter(pk__in = list_inventario_selected,Destinatario__id=destinatario)
                    
#                     current_cita = Cita()
#                     current_cita.Fecha = request.POST.get('Fecha')
#                     current_cita.Hora = request.POST.get('Hora')
#                     current_cita.Estado='Programada'
#                     #current_cita.Inventario=inventarios_selected_objects
#                     current_cita.save()
#                     current_cita.set_inventarios(inventarios_selected_objects)
#                     current_cita.save()
#                     print('cita',current_cita)

#             # Registro de trazas
#             save_addition(request.user, 'cita', current_cita.id, str(model_to_dict(current_cita)))

#             messages.success(request, 'Cita programada satisfactoriamente')
#             return redirect('cita_programadas')

#     #Paginator
#     paginator = Paginator(list_inventario, 50) # Show 100 contacts per page.
#     page_number = request.GET.get('page')
#     page_obj = paginator.get_page(page_number)

#     ctx = {'action': action, 'form_cita': form_cita, 'active_menu': active_menu, 'page_obj': page_obj}
#     return render(request, 'cita/cita_edit.html', ctx)

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
    paginator = Paginator(list_inventario, 50) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'action': action, 'form_cita': form_cita, 'page_obj': page_obj, 'current_cita': current_cita}
    return render(request, 'cita/cita_edit.html', ctx)

@login_required(login_url='login')
def cita_delete(request, id_cita):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    current_cita = get_object_or_404(Cita, pk = id_cita)
    current_cita.Estado='Cancelada'
    current_cita.save()
    #Cita.objects.filter(pk = id_cita).delete()
    return redirect('cita_programadas')


def generar_comprobantes_envios_entregarlo(request,inventarios):
    #Lista de facturas a pasar a la vista
    lista_facturas = []
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
        current_factura['Importe_Recargo_Total'] = 0.0
        current_factura['Importe_Transportacion_Total'] = 0.00 
        current_factura['Importe_Derecho_Aduanal_Total'] = 0.00 
        current_factura['Importe_Servicio_Aduanal_Total'] = 0.00 
        current_factura['Cantidad_Bultos_Total'] = 0 
        #*********************************************************
        current_factura['Importe_Kg_Adicional_Total'] = 0.00 

        lista_inventarios_por_persona = inventarios.filter(Destinatario__CI = current_destinatario)
        # ---------------------------------------------------
        inventario_x = lista_inventarios_por_persona.first()
        provincia=Provincia.objects.filter(id=inventario_x.Destinatario.Provincia.id)
        corresponsal=Agencia.objects.filter(id=inventario_x.Agencia.id)
        
        # ----------------------------------------------------
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
                
                current_factura['Importe_Transcargo_Total'] = 0.00
                current_factura['Importe_Seguro_Carga_Total'] = 0.00
                current_factura['Importe_Sobredimension_Total'] = 0.00
                current_factura['Importe_Recargo_Total'] = 0.00
                current_factura['Importe_Transportacion_Total'] = 0.00
                current_factura['Cantidad_Bultos_Total'] += current_inventario.Cantidad_Bultos

                if current_inventario.Peso:
                    if current_inventario.Peso <= 20:
                        current_inventario_dict['Importe_Kg_Adicional'] = 0.00
                        current_inventario.Importe_Kg_Adicional = 0.00
                        current_inventario.save()
                    if current_inventario.Peso > 20:
                        #
                        current_inventario_dict['Importe_Kg_Adicional'] = (current_inventario.Peso - 20) * 5

                        current_factura['Importe_Kg_Adicional_Total'] += current_inventario_dict['Importe_Kg_Adicional']
                        current_inventario.Importe_Kg_Adicional = (current_inventario.Peso - 20) * 5
                        current_inventario.save()
                else:
                    current_inventario_dict['Importe_Kg_Adicional'] = 0.00
               
                #Agregando informacion a la lista
                current_inventario_dict['Importe_Seguro_Carga'] = 0.00
                current_inventario_dict['Importe_Sobredimension'] = 0.00
                current_inventario_dict['Importe_Transportacion'] = 0.00
                current_inventario_dict['Importe_Transcargo'] = 0.00
                current_lista_de_inventarios.append(current_inventario_dict)

            else:    
                # #Calculando importe de kg adicional
                if current_inventario.Peso:
                    if current_inventario.Peso <= 20:
                        current_inventario_dict['Importe_Kg_Adicional'] = 0.00
                        current_inventario.Importe_Kg_Adicional= 0
                        current_inventario.save()
                    if current_inventario.Peso > 20:
                        #
                        current_inventario_dict['Importe_Kg_Adicional'] = (current_inventario.Peso - 20) * 5
                        current_factura['Importe_Kg_Adicional_Total'] += current_inventario_dict['Importe_Kg_Adicional']
                        current_inventario.Importe_Kg_Adicional= (current_inventario.Peso - 20) * 5
                        current_inventario.save()
                else:
                    current_inventario_dict['Importe_Kg_Adicional'] = 0.00

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

                #Calculando total de bultos
                current_factura['Cantidad_Bultos_Total'] += current_inventario.Cantidad_Bultos

                #Agregando informacion a la lista
                current_lista_de_inventarios.append(current_inventario_dict)

            current_inventario.isFacturado = True
            current_inventario.Estado ='Entregado'
            current_inventario.save()
            
        current_factura['Destinatario'] = Destinatario.objects.filter(CI = current_destinatario).first()
        current_factura['Inventarios'] = current_lista_de_inventarios
        #Valor total de la factura
        current_factura['Precio_Total_Factura'] = current_factura['Importe_Kg_Adicional_Total'] + current_factura['Importe_Transcargo_Total'] + current_factura['Importe_Seguro_Carga_Total'] + current_factura['Importe_Sobredimension_Total'] + current_factura['Importe_Recargo_Total'] + current_factura['Importe_Transportacion_Total'] + current_factura['Importe_Derecho_Aduanal_Total'] + current_factura['Importe_Servicio_Aduanal_Total']

        try:
            with transaction.atomic():
                #Almacenando la factura en el sistema
                factura_instance = Factura()
                factura_instance.Contenido = str(current_factura)
                factura_instance.isMultiple = True
                factura_instance.isEnvio = True
                factura_instance.Estado = 'Cobrada'
                factura_instance.Fecha = now()
                factura_instance.Fecha_cobro = now()
                factura_instance.User_Facturador = request.user
                factura_instance.User_Cobrador = request.user
                factura_instance.Destinatario = current_factura['Destinatario']
                factura_instance.Importe_Total_Factura = current_factura['Precio_Total_Factura']
                factura_instance.Importe_Transcargo_Total = current_factura['Importe_Transcargo_Total']
                factura_instance.Importe_Seguro_Carga_Total = current_factura['Importe_Seguro_Carga_Total']
                factura_instance.Importe_Recargo_Total = current_factura['Importe_Recargo_Total']
                factura_instance.Importe_Transportacion_Total = current_factura['Importe_Transportacion_Total']
                factura_instance.Importe_Derecho_Aduanal_Total = current_factura['Importe_Derecho_Aduanal_Total']
                factura_instance.Importe_Servicio_Aduanal_Total = current_factura['Importe_Servicio_Aduanal_Total']
                factura_instance.Importe_Sobredimension_Total = current_factura['Importe_Sobredimension_Total']
                factura_instance.Importe_Kg_Adicional_Total = current_factura['Importe_Kg_Adicional_Total']
                factura_instance.Cantidad_Bultos_Total = current_factura['Cantidad_Bultos_Total']
                #factura_instance.url = str(request.path) + '?cargos_extra=' + str(current_factura['Importe_Recargo_Total'])
                if request.POST.get('presencial') == 'on':
                    factura_instance.Presencial=True
                else:
                    factura_instance.Presencial=False
             
                factura_instance.Provincia = provincia.first()
                factura_instance.Agencia = corresponsal.first()
                factura_instance.save()
                for current_inventario_object in current_factura['Inventarios']:
                    factura_inventario_instance = Factura_Inventario()
                    factura_inventario_instance.Factura = factura_instance
                    factura_inventario_instance.Inventario = current_inventario_object['Inventario']
                    factura_inventario_instance.Importe_Seguro_Carga = 0.00
                    factura_inventario_instance.Importe_Sobredimension = 0.00
                    factura_inventario_instance.Importe_Transportacion = 0.00
                    factura_inventario_instance.Importe_Transcargo = 0.00
                    factura_inventario_instance.save()

                # Registro de trazas
                save_addition(request.user, 'factura', factura_instance.id, str(model_to_dict(factura_instance)))
        except:
            raise ValueError('Ha ocurrido un error generando la factura')

        
        num_fac=str(factura_instance.id)
        if len(num_fac.split('/')[0]) < 12:
            num_fac = str(current_inventario.Manifiesto).zfill(12)
            #print('num_fac',num_fac)
       
        #Generando codigo de barra de la factura                                        
        code39 = barcode.get_barcode_class('code39')
        code = code39(str(factura_instance.id), writer=ImageWriter(),add_checksum=False)
        fullname = code.save(MEDIA_ROOT + '/QR/factura_' + str(factura_instance.id))
        
        #Generando codigo QR de la factura
        
        qr_generado = '{' + str(factura_instance.id) +'}'
        #qr_generado = '{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}'
        current_factura['id_factura'] = factura_instance.id
        current_factura['facturador'] = factura_instance.User_Facturador.get_full_name()
        
        #Agregando factura a lista general de facturas
        lista_facturas.append(current_factura)

    #Generando reporte PDF
    # template_src = 'pdf/Copia_facturacion_multiple_envios_pdf.html'
    # template = get_template(template_src)
    context = {'lista_facturas': lista_facturas,'fecha_factura': now(),'request': request,'qr':qr_generado}
    # html  = template.render(context)
    # result = BytesIO()
    # pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
    # if not pdf.err:
    #     return HttpResponse(result.getvalue(), content_type='application/pdf')
    # return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))
    return render(request, 'pdf/Copia_facturacion_multiple_envios_pdf.html',context)
        # context = {'lista_facturas': lista_facturas, 'fecha_factura': factura_instance.Fecha, 'request': request,'qr':qr_generado}
        # # html  = template.render(context)
        # # result = BytesIO()
        # # pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
        # # if not pdf.err:
        # #     return HttpResponse(result.getvalue(), content_type='application/pdf')
        # # return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))
        # return render(request, 'pdf/Copia_facturacion_multiple_envios_pdf.html',context)

def generar_comprobantes_ena_menaje_entregarlo(request,inventarios):
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
        if request.POST.get('cargos_extra_ena') != 0 or request.POST.get('cargos_extra_ena'):
            current_factura['Importe_Recargo_Total'] = float(request.POST.get('cargos_extra_ena'))
        else:
            cargos_extra_ena = 0
            current_factura['Importe_Recargo_Total'] = float(cargos_extra_ena)

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
                current_factura['Importe_Recargo_Total'] = 0.00
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

            current_inventario.isFacturado = True
            current_inventario.Estado = 'Entregado'
            current_inventario.save()
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
                factura_instance.Estado = 'Cobrada'
                factura_instance.Fecha = now()
                factura_instance.Fecha_cobro = now()
                factura_instance.User_Facturador = request.user
                factura_instance.User_Cobrador = request.user
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
        

        code39 = barcode.get_barcode_class('code39')
        code = code39(str(factura_instance.id), writer=ImageWriter(),add_checksum=False)
        barcode_generado = code.save(MEDIA_ROOT + '/QR/factura_' + str(factura_instance.id))

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


@login_required(login_url='login')
def cita_detail(request, id_cita):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    current_cita = get_object_or_404(Cita, pk = id_cita)
    
    if request.POST:
        list_inventario_selected = request.POST.getlist('inventario_id')

        #Lista de inventarios a facturar
        inventarios_envios = Inventario.objects.all().filter((Q(Categoria_Operacion__icontains = 'envio') | Q(Categoria_Operacion__icontains = 'envío')), Q(pk__in = list_inventario_selected))
        inventarios_ena_menaje = Inventario.objects.all().filter(~Q(Categoria_Operacion__icontains = 'envio'), ~Q(Categoria_Operacion__icontains = 'envío'), Q(HBL__in = list_inventario_selected))
        #print('inventarios_envios',inventarios_envios)
        #print('inventarios_ena_menaje',inventarios_ena_menaje)
        if len(inventarios_envios)>0:
            generar_comprobantes_envios_entregarlo(request,inventarios_envios)
        if len(inventarios_ena_menaje)>0:
            generar_comprobantes_ena_menaje_entregarlo(request,inventarios_ena_menaje)

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
    #print(citas)
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
    mostrar_listado = bool(request.GET)

    if mostrar_listado:
        inventarios = Inventario.objects.all()
        inventario_filter = Inventario_Reporte_Filter(request.GET, queryset=inventarios)
        inventarios = inventario_filter.qs
        derecho_aduanal = inventarios.aggregate(Sum('Importe_Derecho_aduanal'))
        servicio_aduanal = inventarios.aggregate(Sum('Importe_Servicio_aduanal'))
        paginator = Paginator(inventarios, 400)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
    else:
        inventario_filter = Inventario_Reporte_Filter(
            request.GET, queryset=Inventario.objects.none()
        )
        derecho_aduanal = {'Importe_Derecho_aduanal__sum': None}
        servicio_aduanal = {'Importe_Servicio_aduanal__sum': None}
        page_obj = None

    ctx = {
        'page_obj': page_obj,
        'active_menu': active_menu,
        'inventario_filter': inventario_filter,
        'derecho_aduanal': derecho_aduanal,
        'servicio_aduanal': servicio_aduanal,
        'mostrar_listado': mostrar_listado,
    }
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
            valores_totales['cantidad_HBL_total'] = 0
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
                dicto['cantidad_HBL'] = 0

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
                        if current_factura.Inventario.all().count():
                            dicto['cantidad_HBL'] += current_factura.Inventario.all().count()
             
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
                valores_totales['cantidad_HBL_total'] += dicto['cantidad_HBL']
                
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
            valores_totales['total_paquetes_nacionalizados'] = 0
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
                dicto['total_paquetes_diario'] = 0
                dicto['total'] = 0

                #Cantidad de facturas a procesar por fila
                # inventarios = Inventario.objects.filter(Q(Fecha_Nacionalizacion__year = fecha.year), Q(Fecha_Nacionalizacion__month = fecha.month), Q(Fecha_Nacionalizacion__day = fecha.day),Nacionalizado=True)
                inventarios = Inventario.objects.filter(Q(Fecha_Nacionalizacion__year = fecha.year), Q(Fecha_Nacionalizacion__month = fecha.month), Q(Fecha_Nacionalizacion__day = fecha.day),Nacionalizado=True).values('Fecha_Nacionalizacion').order_by('Fecha_Nacionalizacion').annotate(derecho_aduanal=Sum('Importe_Derecho_aduanal')).annotate(servicio_aduanal=Sum('Importe_Servicio_aduanal'))
                count_inventarios = Inventario.objects.filter(Q(Fecha_Nacionalizacion__year = fecha.year), Q(Fecha_Nacionalizacion__month = fecha.month), Q(Fecha_Nacionalizacion__day = fecha.day),Nacionalizado=True).count()
                # lista_facturas_destinatarios = []
                # 

                dicto['total_paquetes_diario'] +=count_inventarios
                for inventario in inventarios:
                    #print('inventario',inventario)
                    dicto['derecho_aduanal'] += inventario['derecho_aduanal']
                    dicto['servicio_aduanal'] += inventario['servicio_aduanal']
                    dicto['total'] = dicto['derecho_aduanal'] + dicto['servicio_aduanal']
                #Sumando valores totales
                valores_totales['derecho_aduanal_total'] += dicto['derecho_aduanal']
                valores_totales['servicio_aduanal_total'] += dicto['servicio_aduanal']
                valores_totales['total_paquetes_nacionalizados'] += dicto['total_paquetes_diario']
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
    manifiestos_habilitados = Manifiesto.objects.filter(Habilitado=True).values('Manifiesto')

    inventarios = Inventario.objects.filter(Manifiesto__in=manifiestos_habilitados,Estado = 'Desagrupe').exclude(Incidencia__Tipo__icontains='Faltante').order_by('HBL')

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

def ajax_punteo_inventario_load(request):
    hbl_inventario = request.GET.get('HBL')
    no_contenedor = request.GET.get('No_Contenedor')
    data = {}

    # -------------------------------------------------------------------
    if hbl_inventario:
        hbl_regex = re.compile(r'(((number)(.){4})([A-Za-z0-9-\/*.]{1,})|((^)[A-Z0-9-\S]*))')
        listado = re.findall(hbl_regex,hbl_inventario)
        seleccion = []
        for y in listado:
            if y[2] == 'number':
                seleccion.append(y[4])
            else:
                if y[0] != '{':
                    seleccion.append(y[0])
    # -------------------------------------------------------------------
        #Creando informacion a devolver
        
        if len(seleccion) != 0:
            for inv in seleccion:
                inventario = Inventario.objects.filter(HBL=inv).first()
                # inventario = get_object_or_404(Inventario, HBL=inv)
                if inventario:
                    inventario.exist = True
                    inventario.Estado = 'Inventario'
                    # inv.save()
                    if inventario.Categoria_Operacion == 'E.N.A' or inventario.Categoria_Operacion == 'ENA':
                        cantidad_repeticiones = {i:seleccion.count(i) for i in seleccion}
                        valor=0
                        for cantidad in cantidad_repeticiones:
                            valor = cantidad_repeticiones[cantidad]
                        if inventario.Cantidad_Bultos < valor:
                            inventario.Incidencia = Incidencia.objects.get(Tipo__icontains='Sobrante')
                        if inventario.Cantidad_Bultos > valor:
                            inventario.Incidencia = Incidencia.objects.get(Tipo__icontains='Faltante')
                    inventario.save()    
                else:

                    hbl_current = HBL_No_Manifestados.objects.filter(HBL=inv)
                    if not hbl_current:
                        no_manifestados = HBL_No_Manifestados()
                        no_manifestados.HBL = inv
                        no_manifestados.Fecha_Rectificacion = datetime.now
                        no_manifestados.No_Contenedor = no_contenedor
                        no_manifestados.save()
        hbls = HBL_No_Manifestados.objects.filter(No_Contenedor=no_contenedor)
        #print('no manifestados',hbls)
        data = serializers.serialize('json', hbls)

    return JsonResponse(data, safe= False)

def ajax_hbls_confirmado_punteo_load(request):
    no_contenedor_guia_aerea = request.GET.get('No_Contenedor')
 
    # -------------------------------------------------------------------
    data = {}
    #Obteniendo hbls confirmados
    inventarios=''
    inventarios_contenedor = Inventario.objects.filter(No_Contenedor=no_contenedor_guia_aerea)
    if inventarios_contenedor:
        inventarios = inventarios_contenedor
    else:
        inventarios_guia_aerea = Inventario.objects.filter(AWB=no_contenedor_guia_aerea)
        inventarios=inventarios_guia_aerea
    data = serializers.serialize('json', inventarios)
    return JsonResponse(data, safe= False)

def ajax_punteo_confirmacion_inventario_load(request):
    hbl_inventario = request.GET.get('HBL')
    no_contenedor = request.GET.get('No_Contenedor')
    data = {}

    # -------------------------------------------------------------------
    if hbl_inventario:
        hbl_regex = re.compile(r'(((number)(.){4})([A-Za-z0-9-\/*.]{1,})|((^)[A-Z0-9-\S]*))')
        listado = re.findall(hbl_regex,hbl_inventario)
        seleccion = []
        for y in listado:
            if y[2] == 'number':
                seleccion.append(y[4])
            else:
                if y[0] != '{':
                    seleccion.append(y[0])
    # -------------------------------------------------------------------
        inventarios_contenedor = Inventario.objects.filter(No_Contenedor=no_contenedor)
        inventarios_guia_aerea = Inventario.objects.filter(AWB=no_contenedor) 
        no_manifestados =[]       
        if inventarios_contenedor:
            for hbl in seleccion:
                inventario = inventarios_contenedor.filter(HBL=hbl)
                #Creando informacion a devolver      
                if inventario:
                    data['existe']=True
                else:    
                    data['existe']=False
                    no_manifestados.append(hbl)
                    data['no_manifestados'] = no_manifestados
        if inventarios_guia_aerea:
            for hbl in seleccion:
                inventario = inventarios_guia_aerea.filter(HBL=hbl)
                #Creando informacion a devolver      
                if inventario:
                    data['existe']=True
                else:    
                    data['existe']=False
                    no_manifestados.append(hbl)
                    data['no_manifestados'] = no_manifestados
    return JsonResponse(data, safe= False)

def ajax_hbl_duplicado_load(request):
    hbl_inventario = request.GET.get('HBL')
    no_contenedor = request.GET.get('No_Contenedor')
    data = {}

    # -------------------------------------
    if hbl_inventario:
        hbl_regex = re.compile(r'(((number)(.){4})([A-Za-z0-9-\/*.]{1,})|((^)[A-Z0-9-\S]*))')
        listado = re.findall(hbl_regex,hbl_inventario)
        seleccion = []
        for y in listado:
            if y[2] == 'number':
                seleccion.append(y[4])
            else:
                if y[0] != '{':
                    seleccion.append(y[0])

        inventarios_contenedor = Inventario.objects.filter(No_Contenedor=no_contenedor)
        inventarios_guia_aerea = Inventario.objects.filter(AWB=no_contenedor)
 
        #Creando informacion a devolver      
        if inventarios_contenedor:
            data['existe']=True
            data['hbl'] = list(inventarios_contenedor.filter(HBL__in=seleccion,exist=True))
        if inventarios_guia_aerea:
            data['existe']=True
            data['hbl'] = list(inventarios_guia_aerea.filter(HBL__in=seleccion,exist=True))
        else:    
            data['existe']=False
    return JsonResponse(data, safe= False)

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
    # data['bultos_de_menos'] = inventarios.filter(Q(Peso__lte = 1.5), Q(Fecha_Entrada__year = now().year)).count()
    # data['bultos_de_mas'] = inventarios.filter(Q(Peso__gt = 1.5), Q(Fecha_Entrada__year = now().year)).count()
    data['bultos_de_0_15'] = inventarios.filter(Q(Peso__gt = 0),Q(Peso__lte = 1.5), Q(Fecha_Entrada__year = now().year)).count()
    data['bultos_de_15_3'] = inventarios.filter(Q(Peso__gt = 1.5),Q(Peso__lte = 3), Q(Fecha_Entrada__year = now().year)).count()
    data['bultos_de_3_20'] = inventarios.filter(Q(Peso__gt = 3),Q(Peso__lte = 20), Q(Fecha_Entrada__year = now().year)).count()
    data['bultos_mayor_de_20'] = inventarios.filter(Q(Peso__gt = 20), Q(Fecha_Entrada__year = now().year)).count()

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
        transportistas = Transportista.objects.all().filter(Empresa = empresa).order_by('Nombre')
        #Creando informacion a devolver
        data = serializers.serialize('json', transportistas)
    return JsonResponse(data, safe= False) 

def ajax_existe_chapa_load(request):
    id_chapa = request.GET.get('id_Chapa')
    id_Transportista = request.GET.get('transportista')
    #print('id_Transportista',id_Transportista)
    #print('id_chapa',id_chapa)
    data = {}
    if id_chapa:
        # chapa  = Transportista.objects.filter(Chapa = id_chapa)
        chapa  = Chapa.objects.filter(Chapa = id_chapa,transportista__id=id_Transportista)
        if chapa:
            #Creando informacion a devolver
            data = serializers.serialize('json', chapa)
    return JsonResponse(data, safe= False)    


def rectificar_peso(request):
    header_text = 'Comprobar peso de paquete'
    breadcrumb_text  = 'Comprobar peso de paquete'
    hbl = request.POST.get('hbl')
    data = {}
    peso_diferente = False
    peso_manifestado=''
    peso_real_paquete=''
    paquete_rectificado =''
    if request.method=='POST':
        if hbl:
            inventario = Inventario.objects.get(HBL=hbl)
            ser = serial.Serial()
            ser.close()

            ser.baudrate = 9600
            ser.port = 'COM10'
            ser.stopbits=1
            ser.bytesize=8
            if not ser.isOpen():
                ser.open()
            bits = ser.readlines(100)
            valor = bits[0].decode('ascii')
            regex = re.compile(r'(\d{1,}[.]\d{3}kg)')
            peso_real = regex.search(valor) 
            regex_peso = re.compile(r'(kg)')
            peso_real = re.sub(regex_peso,' ',str(peso_real[0]))
            if inventario.Peso != float(peso_real):
                inventario.peso_real= float(peso_real)
                inventario.save()
                peso_real_paquete=float(peso_real)
                peso_manifestado=inventario.Peso
                paquete_rectificado = inventario.HBL
                peso_diferente = True   
            ser.close()
            file = 'filename.txt'
            with open(file,"a+") as fp:
                fp.seek(0)
                fp.write(peso_real)
                fp.truncate()
                fp.close()
    ctx = {'peso_diferente': peso_diferente,'header_text':header_text,'breadcrumb_text':breadcrumb_text,'peso_manifestado':peso_manifestado,'peso_real':peso_real_paquete,'hbl':paquete_rectificado }
    return render(request, 'inventario/rectificar_peso.html', ctx)



# ser = serial.Serial('COM')
# ser = serial.Serial('COM5',9600,None,8,1)
# def bascula():
#     ser = serial.Serial()
#     ser.baudrate = 9600
#     ser.port = 'COM10'
#     # ser.parity = 'None'
#     ser.stopbits=1
#     ser.bytesize=8
#     print(ser.name)
#     ser.open()

#     # print(ser.is_open)
#     x = ser.readline(10)
#     print('read',x)
# bascula()
# def timer():
#     while True:
#         bascula()
#         time.sleep(10)   # 10 segundos.
# # Iniciar la ejecución en segundo plano.
# t = threading.Thread(target=timer)
# t.start()
# ser.Handshake = Handshake.None
# ser.
#COM6 - nombre que cogió la báscula al conectarla
#Baurate : (Manual)
#Parity : (Manual)
#Stop Bit : (Manual)
#Data Bit : (Manual)
# print(ser.name)
# if ser.name == 'COM6':
# while True:
#     x = ser.readline()
#     tupla = str(x).split(" ")     
#     '''
#         tupla de 3 campos
#         campo1: instrucciones binarias
#         campo2: peso que marcara el indicador
#         campo3: final de cadena       '''
#     peso = tupla[1]
#     #peso = peso.replace("KG", "")      
#     speso = str(peso[:7]) #siete digitos decimales
#     if speso.isdecimal() is True:
#         pesa = int(speso)
#         if pesa > 0:
#             print('pesa: ' + str(pesa) + 'Kg')
#     time.sleep(0.1)
# ser.close()
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
                    # if len(man.split('/')[0]) < 4:
                    #     man = str(current_inventario.Manifiesto).zfill(4)
                    #     print('manifiesto',man)
                    if len(man.split('/')) == 1:
                        man = man + '/' + str(current_inventario.Fecha_Entrada_Puerto.year)
                    #dicto = {'success': True, 'despachos': [{'BOLETIN_DERECHO': '171021047035915000007', 'NO_BLGA': 'MAY21110540', 'MANIFIESTOS': '0358/2021', 'VALOR_DERECHOS': '0', 'VALOR_SERVICIO': '50'}]}
                    USUARIO = 'aerov'
                    PASS = 'eh7443fx'
                    MANIFIESTO = man
                    HBL = current_inventario.HBL
                    if current_inventario.AWB:
                        HBL = current_inventario.AWB +' ' +current_inventario.HBL
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
                    print('dicto',dicto)
                    if dicto['success'] == True:
                        # print('nacionalizacion')
                        current_inventario.Importe_Derecho_aduanal = float(dicto['despachos'][0]['VALOR_DERECHOS'])
                        current_inventario.Importe_Servicio_aduanal = float(dicto['despachos'][0]['VALOR_SERVICIO'])
                        current_inventario.Precio = 0
                        current_inventario.Categoria_Operacion = 'ENVIO'
                    else:
                        current_inventario.Importe_Derecho_aduanal = 0
                        current_inventario.Importe_Servicio_aduanal = 0
                        current_inventario.Precio = 0
                        if current_inventario.Categoria_Operacion == None:
                            current_inventario.Categoria_Operacion = 'E.N.A'
                    
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
                    
                    # Registro de trazas
                    save_edition(request.user, 'inventario', current_inventario.id, str(model_to_dict(current_inventario)))

                except:
                    current_inventario.Importe_Derecho_aduanal = 0
                    current_inventario.Importe_Servicio_aduanal = 0
                    current_inventario.Precio = 0
                    current_inventario.save()               
                
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
                
                #Salvando Tracking
                traking = Traking()
                traking.Inventario      = current_inventario
                traking.Estado          = 'En tránsito'
                traking.Observaciones   = 'Inventario en tránsito'
                traking.Fecha           = now()
                traking.save()

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

            messages.success(request, 'Cargas declaradas en canal rojo satisfactoriamente.')
            return redirect(request.path)

        #Accion de ubicar cargas dentro de almacen----------------------
        if request.POST.get('operacion_tabla') == 'ubicar_cargas_dentro_almacen':
            #Capturando datos del formulario
            fila = request.POST.get('Fila')
            columna = request.POST.get('Columna')
            cargas = request.POST.get('Carga')
            list_inventario = request.POST.getlist('inventario_id')
            #print('fila',fila)
            #print('columna',columna)
            #print('cargas',cargas)
            #print('list_inventario',list_inventario)
            #Validando que se haya seleccionado el área y la columna
            if fila == 'None' or columna =='None':
                messages.error(request, 'Debe seleccionar el área y la columna para ubicar las cargas')
                return redirect(request.path)  

            #Validando que se hayan seleccionado las cargas en la tabla o se hayan esscaneado
            if not cargas and not list_inventario:
                messages.error(request, 'Debe seleccionar las cargas en el listado o escanear su identificador')
                return redirect(request.path)    
            # #Obteniendo almacen
            # current_almacen = Almacen.objects.get(id = id_almacen)
            
            listado_cargas=[]
            if cargas:
                hbl_regex = re.compile(r'[A-Z0-9-]*')
                cargas_escaneadas = re.findall(hbl_regex,cargas)
                inventarios=Inventario.objects.filter(HBL__in=cargas_escaneadas)
                for inventario in inventarios:
                    listado_cargas.append(inventario.id)
            if list_inventario:
                listado_cargas= list_inventario
            #Recorriendo todos los inventarios seleccionados
            for id_current_inventario in listado_cargas:
                current_inventario = Inventario.objects.get(id = id_current_inventario)
                # current_inventario.Almacen = current_almacen
                current_inventario.Ubicacion_Fila = fila
                current_inventario.Ubicacion_Columna = columna
                current_inventario.Estado = 'Inventario'

                current_inventario.save()

                # Registro de trazas
                save_edition(request.user, 'inventario', current_inventario.id, str(model_to_dict(current_inventario)))

            messages.success(request, 'Cargas ubicadas satisfactoriamente')
            return redirect(request.path)

        #Accion de cancelar generacion de comprobantes de destinatarios(cargas no escaneadas)----------
        if request.POST.get('operacion_tabla') == 'cancelar_generacion_comprobantes':
            #Capturando datos del formulario
            list_inventario = request.POST.getlist('inventario_id')

            #Recorriendo todos los inventarios seleccionados
            for inventario in list_inventario:
                Temporal_HBL_Escaneados.objects.filter(Inventario__id=inventario).delete()
                current_inventario=Inventario.objects.get(id=inventario)

                # Registro de trazas
                save_edition(request.user, 'inventario', current_inventario.id, str(model_to_dict(current_inventario)))
 
            messages.success(request, 'Comprobantes cancelados satisfactoriamente.')
            return redirect(request.path)

                #Accion de cancelar generacion de comprobantes de destinatarios(cargas no escaneadas)----------
        if request.POST.get('operacion_tabla') == 'habilitar_manifiesto':
            #Capturando datos del formulario
            list_manifiesto = request.POST.getlist('manifiesto_id')

            #Recorriendo todos los inventarios seleccionados
            for manifiesto in list_manifiesto:
                current_manifiesto = Manifiesto.objects.get(id = manifiesto)
                current_manifiesto.Habilitado = True
                current_manifiesto.save()


                # Registro de trazas
                save_edition(request.user, 'manifiesto', current_manifiesto.id, str(model_to_dict(current_manifiesto)))
 
            messages.success(request, 'Manifiestos habilitados satisfactoriamente.')
            return redirect(request.path)
        if request.POST.get('operacion_tabla') == 'deshabilitar_manifiesto':
            #Capturando datos del formulario
            list_manifiesto = request.POST.getlist('manifiesto_id')

            #Recorriendo todos los inventarios seleccionados
            for manifiesto in list_manifiesto:
                current_manifiesto = Manifiesto.objects.get(id = manifiesto)
                current_manifiesto.Habilitado = False
                current_manifiesto.save()


                # Registro de trazas
                save_edition(request.user, 'manifiesto', current_manifiesto.id, str(model_to_dict(current_manifiesto)))
 
            messages.success(request, 'Manifiestos deshabilitados satisfactoriamente.')
            return redirect(request.path)


#----Generacion de PDF-------------------------------------------------------
def lista_entregas_pdf(request, id_entrega):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Capturando solicitud
    current_entrega = get_object_or_404(Entrega, pk = id_entrega)
    #Obteniendo el transportista
    transportista = get_object_or_404(Transportista,pk = current_entrega.Transportista.id)
    chapa = Chapa.objects.get(Chapa=current_entrega.Chapa,transportista__id=transportista.id)
    #Calculando cantidad de bultos
    cantidad_bultos = 0
    for comprobante_destinatario in current_entrega.Factura_Operador.Facturas_Destinatarios.all():             
        for current_inventario in comprobante_destinatario.Inventario.all():             
            cantidad_bultos = cantidad_bultos + current_inventario.Cantidad_Bultos

    #Generando reporte PDF
    template_src = 'pdf/lista_entregas_pdf.html'
    template = get_template(template_src)
    context = {'current_entrega': current_entrega, 'cantidad_bultos': cantidad_bultos,'transportista':transportista,'chapa':chapa,'request': request}
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
        current_factura['Importe_Recargo_Total'] = 0.0
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

            code39 = barcode.get_barcode_class('code39')
            code = code39(str(factura_instance.id), writer=ImageWriter(),add_checksum=False)
            fullname = code.save(MEDIA_ROOT + '/QR/factura_' + str(factura_instance.id))
            qr_generado = '{' + str(factura_instance.id)+ '}'
            # qr_generado = '{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}' 
        #Identificador de la factura
        if current_entrega.Estado == 'Ejecucion':
            current_factura['id_factura'] = factura_instance.id
        else:
            current_factura['id_factura'] = None

        #Agregando factura a lista general de facturas
        lista_facturas.append(current_factura)

        #Generando reporte PDF
        # template_src = 'pdf/Copia_facturacion_multiple_envios_pdf.html'
        # template = get_template(template_src)
        context = {'lista_facturas': lista_facturas,'fecha_factura': now(),'request': request,'qr':qr_generado}
        # html  = template.render(context)
        # result = BytesIO()
        # pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
        # if not pdf.err:
        #     return HttpResponse(result.getvalue(), content_type='application/pdf')
        # return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))
        return render(request, 'pdf/Copia_facturacion_multiple_envios_pdf.html',context)
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
        current_factura['Importe_Recargo_Total'] = 0.0
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

            code39 = barcode.get_barcode_class('code39')
            code = code39(str(factura_instance.id), writer=ImageWriter(),add_checksum=False)
            fullname = code.save(MEDIA_ROOT + '/QR/factura_' + str(factura_instance.id))
            qr_generado = '{' + str(factura_instance.id) +'}'
            # qr_generado = '{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}' 
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
    code39 = barcode.get_barcode_class('code39')
    code = code39(str(factura_instance.id), writer=ImageWriter(),add_checksum=False)
    fullname = code.save(MEDIA_ROOT + '/QR/factura_' + str(factura_instance.id))
    # qr_generado = '{' + str(factura_instance.id)+ '}'
    # qr_generado = '{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}' 
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

def factura_detalle_img(request, id_factura):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Capturando factura
    current_factura_object = get_object_or_404(Factura, pk = id_factura)
    #Lista de facturas a pasar a la vista
    lista_facturas = []
    #Diccionario de factura
    current_factura = {}

    provincia = ''
    municipio = ''
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
        provincia = Factura_Inventario.objects.filter(Factura = current_factura_object).values('Inventario__Destinatario__Provincia__Nombre').first()
        municipio = Factura_Inventario.objects.filter(Factura = current_factura_object).values('Inventario__Destinatario__Municipio__Nombre').first()
        #QR datos de transaccion
        qr_generado = '{' + str(current_factura_object.id)+ '}'
        # qr_generado = '{"id_transaccion": ' + str(current_factura_object.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}' 

        #Generando reporte PDF
        # template_src = 'pdf/Copia_facturacion_multiple_envios_pdf.html'
        # template = get_template(template_src)
        # context = {'lista_facturas': lista_facturas, 'fecha_factura': current_factura_object.Fecha, 'request': request,'qr':qr_generado}
        # html  = template.render(context)
        # result = BytesIO()
        # pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
        # if not pdf.err:
        #     return HttpResponse(result.getvalue(), content_type='application/pdf')
        # return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))
        # return render(request, 'pdf/Copia_facturacion_multiple_envios_pdf.html',context)
        # template_src = 'pdf/Copia_facturacion_multiple_envios_pdf.html'
        # template = get_template(template_src)
        context = {'lista_facturas': lista_facturas,'fecha_factura': now(),'request': request,'qr':qr_generado,'municipio':municipio,'provincia':provincia}
        # html  = template.render(context)
        # result = BytesIO()
        # pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
        # if not pdf.err:
        #     return HttpResponse(result.getvalue(), content_type='application/pdf')
        # return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))
        return render(request, 'pdf/Copia_facturacion_multiple_envios_pdf.html',context)
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
        provincia = Factura_Inventario.objects.filter(Factura = current_factura_object).values('Inventario__Destinatario__Provincia__Nombre').first()
        municipio = Factura_Inventario.objects.filter(Factura = current_factura_object).values('Inventario__Destinatario__Municipio__Nombre').first()

        #QR datos de transaccion
        # qr_generado = '{"id_transaccion": ' + str(current_factura_object.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}' 
        qr_generado = '{' + str(current_factura_object.id) +'}' 
        #Generando reporte PDF
        template_src = 'pdf/facturacion_multiple_ena_menaje_pdf.html'
        template = get_template(template_src)
        context = {'lista_facturas': lista_facturas, 'fecha_factura': current_factura_object.Fecha, 'request': request,'qr':qr_generado,'municipio':municipio,'provincia':provincia}
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
        provincia = Factura_Inventario.objects.filter(Factura = current_factura_object).values('Inventario__Destinatario__Provincia__Nombre').first()
        municipio = Factura_Inventario.objects.filter(Factura = current_factura_object).values('Inventario__Destinatario__Municipio__Nombre').first()

        # #QR datos de transaccion
        # qr_generado = '{"id_transaccion": ' + str(current_factura_object.id) + ', "importe": ' + str(current_inventario_dict['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}' 
        qr_generado = '{' + str(current_factura_object.id) +'}'
        #Generando reporte PDF
        template_src = 'pdf/factura_de_inventario.html'
        template = get_template(template_src)
        context = {'current_inventario_dict': current_inventario_dict, 'fecha_factura': current_factura_object.Fecha, 'request': request, 'isEnvio': current_factura_object.isEnvio,'municipio':municipio,'provincia':provincia}
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
                            if current_inventario.AWB:
                                HBL = current_inventario.AWB +' ' +current_inventario.HBL
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
    operaciones_de_tablas(request)

    #Lista de manifiestos
    Manifiestos = Manifiesto.objects.all().order_by('-id')

    #Aplicacion de filtros
    manifiesto_filter = Manifiesto_Filter(request.GET, queryset=Manifiestos)
    Manifiestos = manifiesto_filter.qs
    
    #Paginator
    paginator = Paginator(Manifiestos, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj, 'manifiesto_filter': manifiesto_filter, 'active_menu': 'manifiestos'}
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
            # print(inst)
            messages.error(request, 'Este manifiesto no puede ser eliminado porque ya se han realizado operaciones con sus inventarios.')
            return redirect(reverse('manifiesto_list'))
    else:
        return redirect(reverse('manifiesto_list'))


#--------Comprobante de entrega de destinatario--------------------------------------
# @login_required(login_url='login')
# def comprobante_entrega_envios_pdf(request):
#     #Validando roles
#     if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
#         raise Http404

#     #Flags sobre la informacion de inventarios
#     isEnvio         = False
#     isEna_menaje    = False

#     #Informacion para el template
#     header_text     = 'Generar comprobantes de pago de destinatarios'
#     breadcrumb_text = 'Generar comprobantes de pago de destinatarios'
#     #Definiendo menu activo
#     active_menu = 'comprobante_pago_destinatario'
#     trasbordo_form = Operacion_Trasladar_De_Almacen_Form()
#     form_hbl_escaneados = HBL_Escaneados_Form()

#     if request.method == 'POST':
#         try:
            
#             # list_inventario_selected = ''
#             # if request.POST.get('HBL'):
#             #     #Comprobante desde escaner
#             #     hbl_regex = re.compile(r'([A-Z0-9*]*)')
#             #     #Obtengo los HBL escaneados
#             #     hbl_escaneados_list=request.POST.get('HBL')
#             #     no_contenedor=request.POST.get('No_Contenedor')

#             #     print('hbl_escaneados_list',hbl_escaneados_list)
#             #     list_inventario_selected = re.findall(hbl_regex,hbl_escaneados_list)
                
#             #     #Obtengo los inventarios que coinciden con los HBL escaneados
#             #     inventarios = Inventario.objects.all().filter(HBL__in = list_inventario_selected,No_Contenedor=no_contenedor)

#             #     #Lista de facturas a pasar a la vista
#             #     lista_facturas = []
                
#             #     #Obteniendo lista de destinatarios de la solicitud
#             #     lista_de_destinatarios = [] #Lista de destinatarios
#             #     for current_inventario in inventarios:
#             #         lista_de_destinatarios.append(current_inventario.Destinatario.CI)
#             #     # lista_de_destinatarios = list(dict.fromkeys(lista_de_destinatarios))

#             #     hbl_destinatario_no_escaneados = []
#             #     #Obtengo todos los HBL de cada destinatario
#             #     for destinatario in lista_de_destinatarios:
#             #         hbl_destinatario = Inventario.objects.filter(Destinatario=destinatario,No_Contenedor=no_contenedor).values('HBL')
#             #         for hbl in hbl_destinatario:
#             #             if hbl not in hbl_escaneados_list:
#             #                 inventario = Inventario.objects.get_object_or_404(HBL=hbl)
#             #                 hbl_destinatario_no_escaneados.append(inventario)
#             #     # if hbl_destinatario_no_escaneados:
                           




#             # if not request.POST.get('HBL'):
#             #     list_inventario_selected = request.POST.getlist('inventario_id')
#             list_inventario_selected = request.POST.getlist('inventario_id')        

#             if request.POST.get('operacion_tabla') == 'facturar_envios':
#                 #Lista de inventarios a facturar
#                 inventarios = Inventario.objects.all().filter((Q(Categoria_Operacion__icontains = 'envio') | Q(Categoria_Operacion__icontains = 'envío')), Q(pk__in = list_inventario_selected))

#                 #Lista de facturas a pasar a la vista
#                 lista_facturas = []
                
#                 #Obteniendo lista de destinatarios de la solicitud
#                 lista_de_destinatarios = [] #Lista de destinatarios
#                 for current_inventario in inventarios:
#                     lista_de_destinatarios.append(current_inventario.Destinatario.CI)
#                 lista_de_destinatarios = list(dict.fromkeys(lista_de_destinatarios))

#                 for current_destinatario in lista_de_destinatarios:
#                     current_factura = {}
#                     current_lista_de_inventarios = []

#                     #Cantidad de veces que se mostrara la factura 
#                     current_factura['Copias_Facturas'] = range(1)

#                     #Valores totales
#                     current_factura['Importe_Transcargo_Total'] = 0.00 
#                     current_factura['Importe_Seguro_Carga_Total'] = 0.00 
#                     current_factura['Importe_Sobredimension_Total'] = 0.00 
#                     current_factura['Importe_Recargo_Total'] = float(request.POST.get('cargos_extra'))
#                     current_factura['Importe_Transportacion_Total'] = 0.00 
#                     current_factura['Importe_Derecho_Aduanal_Total'] = 0.00 
#                     current_factura['Importe_Servicio_Aduanal_Total'] = 0.00 
#                     current_factura['Cantidad_Bultos_Total'] = 0 

#                     lista_inventarios_por_persona = inventarios.filter(Destinatario__CI = current_destinatario)
#                     for current_inventario in lista_inventarios_por_persona:
#                         current_inventario_dict = {}
#                         current_inventario_dict['Inventario'] = current_inventario

#                         #Calculando el importe por derechos aduanales
#                         if current_inventario.Importe_Derecho_aduanal:
#                             current_factura['Importe_Derecho_Aduanal_Total'] += current_inventario.Importe_Derecho_aduanal

#                         #Calculando el importe por servicios aduanales
#                         if current_inventario.Importe_Servicio_aduanal:
#                             current_factura['Importe_Servicio_Aduanal_Total'] += current_inventario.Importe_Servicio_aduanal
#                         if current_inventario.isPrepago:
#                             current_factura['Importe_Seguro_Carga_Total'] = 0.00
#                             current_factura['Importe_Sobredimension_Total'] = 0.00
#                             current_factura['Importe_Transportacion_Total'] = 0.00
#                             current_factura['Importe_Transcargo_Total'] = 0.00
#                             current_factura['Cantidad_Bultos_Total'] += current_inventario.Cantidad_Bultos
                            
#                             #Agregando informacion a la lista
#                             current_inventario_dict['Importe_Seguro_Carga'] = 0.00
#                             current_inventario_dict['Importe_Sobredimension'] = 0.00
#                             current_inventario_dict['Importe_Transportacion'] = 0.00
#                             current_inventario_dict['Importe_Transcargo'] = 0.00
#                             current_lista_de_inventarios.append(current_inventario_dict)

#                         else:    
#                             #Calculando precio por seguro de carga
#                             if current_inventario.Peso:
#                                 if current_inventario.Peso <= 1.50:
#                                     current_inventario_dict['Importe_Seguro_Carga'] = 0.00
#                                 if current_inventario.Peso > 1.50:
#                                     current_inventario_dict['Importe_Seguro_Carga'] = 12.00

#                                 current_factura['Importe_Seguro_Carga_Total'] += current_inventario_dict['Importe_Seguro_Carga']
#                             else:
#                                 current_inventario_dict['Importe_Seguro_Carga'] = 0.00
                            
#                             #Calculando precio por sobredimension
#                             if current_inventario.Peso:
#                                 if current_inventario.Peso < 30.00:
#                                     current_inventario_dict['Importe_Sobredimension'] = 0.00
#                                 if current_inventario.Peso >= 30.00:
#                                     current_inventario_dict['Importe_Sobredimension'] = 70.00

#                                 current_factura['Importe_Sobredimension_Total'] += current_inventario_dict['Importe_Sobredimension']
#                             else:
#                                 current_inventario_dict['Importe_Sobredimension'] = 0.00
#                             #Calculando precio por transportacion
#                             if current_inventario.Peso and request.POST.get('incluir_transportacion') == 'on':        
#                                 if current_inventario.Destinatario.Municipio.Importe_por_entrega:
#                                     current_inventario_dict['Importe_Transportacion'] = float(current_inventario.Destinatario.Municipio.Importe_por_entrega)
#                                     if request.POST.get('trasbordo') == 'on' or current_inventario.trasbordo == True:
#                                         current_inventario.trasbordo = True
#                                         current_inventario.save()
#                                         if current_inventario.Destinatario.Municipio.Importe_por_trasbordo:                                            
#                                             current_inventario_dict['Importe_Transportacion'] += float(current_inventario.Destinatario.Municipio.Importe_por_trasbordo)
                                
#                                 else:
#                                     current_inventario_dict['Importe_Transportacion'] = 0.00
#                                 current_factura['Importe_Transportacion_Total'] += float(current_inventario_dict['Importe_Transportacion'])
                            
#                             else:
#                                 current_inventario_dict['Importe_Transportacion'] = 0.00
#                             #Calculando el importe de transcargo
#                             if current_inventario.Peso:
#                                 if current_inventario.Peso <= 1.50:
#                                     if current_inventario.Importe_Derecho_aduanal > 0:
#                                         current_inventario_dict['Importe_Transcargo'] = round((80.00 + (float(current_inventario.Importe_Derecho_aduanal) * 1.10)/100 + (float(current_inventario.Importe_Servicio_aduanal) * 1.10)/100), 2)
#                                     else:
#                                         current_inventario_dict['Importe_Transcargo'] = 80.00

#                                 if current_inventario.Peso > 1.50 and current_inventario.Peso <= 50.00:
#                                     current_inventario_dict['Importe_Transcargo'] = round((199.00 + float(current_inventario.Peso) * 12.00 + (float(current_inventario.Importe_Derecho_aduanal) * 1.10)/100 + (float(current_inventario.Importe_Servicio_aduanal) * 1.10)/100), 2)
#                                 if current_inventario.Peso > 50.00:
#                                     current_inventario_dict['Importe_Transcargo'] = round((800.00 + (float(current_inventario.Importe_Derecho_aduanal) * 1.10)/100 + (float(current_inventario.Importe_Servicio_aduanal) * 1.10)/100), 2)
                            
#                                 current_factura['Importe_Transcargo_Total'] += current_inventario_dict['Importe_Transcargo']
#                             else:
#                                 current_inventario_dict['Importe_Transcargo'] = 0.00

#                             #Calculando total de bultos
#                             current_factura['Cantidad_Bultos_Total'] += current_inventario.Cantidad_Bultos

#                             #Agregando informacion a la lista
#                             current_lista_de_inventarios.append(current_inventario_dict)

#                     current_factura['Destinatario'] = Destinatario.objects.filter(CI = current_destinatario).first()
#                     current_factura['Inventarios'] = current_lista_de_inventarios
#                     #Valor total de la factura
#                     current_factura['Precio_Total_Factura'] = current_factura['Importe_Transcargo_Total'] + current_factura['Importe_Seguro_Carga_Total'] + current_factura['Importe_Sobredimension_Total'] + current_factura['Importe_Recargo_Total'] + current_factura['Importe_Transportacion_Total'] + current_factura['Importe_Derecho_Aduanal_Total'] + current_factura['Importe_Servicio_Aduanal_Total']

#                     try:
#                         with transaction.atomic():
#                             #Almacenando la factura en el sistema
#                             factura_instance = Factura()
#                             factura_instance.Contenido = str(current_factura)
#                             factura_instance.isMultiple = True
#                             factura_instance.isEnvio = True
#                             factura_instance.Fecha = now()
#                             factura_instance.User_Facturador = request.user
#                             factura_instance.Estado = 'Creada'
#                             factura_instance.Destinatario = current_factura['Destinatario']
#                             factura_instance.Importe_Total_Factura = current_factura['Precio_Total_Factura']
#                             factura_instance.Importe_Transcargo_Total = current_factura['Importe_Transcargo_Total']
#                             factura_instance.Importe_Seguro_Carga_Total = current_factura['Importe_Seguro_Carga_Total']
#                             factura_instance.Importe_Recargo_Total = current_factura['Importe_Recargo_Total']
#                             factura_instance.Importe_Transportacion_Total = current_factura['Importe_Transportacion_Total']
#                             factura_instance.Importe_Derecho_Aduanal_Total = current_factura['Importe_Derecho_Aduanal_Total']
#                             factura_instance.Importe_Servicio_Aduanal_Total = current_factura['Importe_Servicio_Aduanal_Total']
#                             factura_instance.Importe_Sobredimension_Total = current_factura['Importe_Sobredimension_Total']
#                             factura_instance.Cantidad_Bultos_Total = current_factura['Cantidad_Bultos_Total']
#                             #factura_instance.url = str(request.path) + '?cargos_extra=' + str(current_factura['Importe_Recargo_Total'])
#                             factura_instance.save()
                                
#                             for current_inventario_object in current_factura['Inventarios']:
#                                 factura_inventario_instance = Factura_Inventario()
#                                 factura_inventario_instance.Factura = factura_instance
#                                 factura_inventario_instance.Inventario = current_inventario_object['Inventario']
#                                 factura_inventario_instance.Importe_Seguro_Carga = current_inventario_object['Importe_Seguro_Carga']
#                                 factura_inventario_instance.Importe_Sobredimension = current_inventario_object['Importe_Sobredimension']
#                                 factura_inventario_instance.Importe_Transportacion = current_inventario_object['Importe_Transportacion']
#                                 factura_inventario_instance.Importe_Transcargo = current_inventario_object['Importe_Transcargo']
#                                 factura_inventario_instance.save()

#                             # Registro de trazas
#                             save_addition(request.user, 'factura', factura_instance.id, str(model_to_dict(factura_instance)))
#                     except:
#                         raise ValueError('Ha ocurrido un error generando la factura')

#                     #Generando codigo QR de la factura
#                     # qr = qrcode.QRCode()
#                     # qr.add_data('{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}')
#                     # qr.make()
#                     # img = qr.make_image()
#                     # img.save(MEDIA_ROOT +'/QR/factura_' + str(factura_instance.id) +'.png')
#                     qr_generado = '{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}'
#                     current_factura['id_factura'] = factura_instance.id
#                     current_factura['facturador'] = factura_instance.User_Facturador.get_full_name()
                    
#                     #Agregando factura a lista general de facturas
#                     lista_facturas.append(current_factura)

#                 #Generando reporte PDF
#                 template_src = 'pdf/facturacion_multiple_envios_pdf.html'
#                 template = get_template(template_src)
#                 context = {'lista_facturas': lista_facturas,'fecha_factura': now(),'request': request,'qr':qr_generado}
#                 html  = template.render(context)
#                 result = BytesIO()
#                 pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
#                 if not pdf.err:
#                     return HttpResponse(result.getvalue(), content_type='application/pdf')
#                 return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))

#             if request.POST.get('operacion_tabla') == 'facturar_ena_menaje':
#                 #Lista de inventarios a facturar
#                 inventarios = Inventario.objects.all().filter(~Q(Categoria_Operacion__icontains = 'envio'), ~Q(Categoria_Operacion__icontains = 'envío'), Q(pk__in = list_inventario_selected))

#                 #Lista de facturas a pasar a la vista
#                 lista_facturas = []
                
#                 #Obteniendo lista de destinatarios de la solicitud
#                 lista_de_destinatarios = [] #Lista de destinatarios
#                 for current_inventario in inventarios:
#                     lista_de_destinatarios.append(current_inventario.Destinatario.CI)
#                 lista_de_destinatarios = list(dict.fromkeys(lista_de_destinatarios))

#                 for current_destinatario in lista_de_destinatarios:
#                     current_factura = {}
#                     current_lista_de_inventarios = []

#                     #Cantidad de veces que se mostrara la factura 
#                     current_factura['Copias_Facturas'] = range(1)

#                     #Valores totales
#                     current_factura['Importe_Transcargo_Total'] = 0.00  #OK
#                     current_factura['Importe_Seguro_Carga_Total'] = 0.00 #OK
#                     current_factura['Importe_Servicio_Corresponsalia_Total'] = 0.00 #OK
#                     current_factura['Importe_Transportacion_Total'] = 0.00 #OK
#                     current_factura['Importe_Recargo_Total'] = float(request.POST.get('cargos_extra_ena'))
#                     current_factura['Importe_Derecho_Aduanal_Total'] = float(request.POST.get('importe_derecho_aduanal'))
#                     current_factura['Importe_Servicio_Aduanal_Total'] = float(request.POST.get('importe_servicio_aduanal'))
#                     current_factura['Cantidad_Bultos_Total'] = 0

#                     lista_inventarios_por_persona = inventarios.filter(Destinatario__CI = current_destinatario)
#                     for current_inventario in lista_inventarios_por_persona:
#                         current_inventario_dict = {}
#                         current_inventario_dict['Inventario'] = current_inventario

#                         if current_inventario.isPrepago:
#                             current_factura['Importe_Transcargo_Total'] = 0.00
#                             current_factura['Importe_Seguro_Carga_Total'] = 0.00
#                             current_factura['Importe_Servicio_Corresponsalia_Total'] = 0.00
#                             current_factura['Importe_Transportacion_Total'] = 0.00
#                             current_factura['Cantidad_Bultos_Total'] += current_inventario.Cantidad_Bultos                            
                            
#                             #Agregando informacion a la lista
#                             current_inventario_dict['Importe_Transcargo'] = 0.00
#                             current_inventario_dict['Importe_Seguro_Carga'] = 0.00
#                             current_inventario_dict['Importe_Servicio_Corresponsalia'] = 0.00
#                             current_inventario_dict['Importe_Sobredimension'] = 0.00
#                             current_inventario_dict['Importe_Transportacion'] = 0.00
#                             current_lista_de_inventarios.append(current_inventario_dict)

#                         else:
#                             #Facturacion de ENA
#                             if current_inventario.Categoria_Operacion == 'ENA' or current_inventario.Categoria_Operacion == 'ena' or current_inventario.Categoria_Operacion == 'Ena' or current_inventario.Categoria_Operacion == 'E.N.A' or current_inventario.Categoria_Operacion == 'e.n.a' or current_inventario.Categoria_Operacion == 'E.n.a': 
#                                 #Calculando el importe de transcargo
#                                 if current_inventario.Volumen:
#                                     if current_inventario.Volumen <= 1:
#                                         current_inventario_dict['Importe_Transcargo'] = 765.00
#                                     if current_inventario.Volumen > 1:
#                                         current_inventario_dict['Importe_Transcargo'] = round(765.00 * float(current_inventario.Volumen), 2)
                                    
#                                     current_factura['Importe_Transcargo_Total'] += current_inventario_dict['Importe_Transcargo']
#                                 else:
#                                     current_inventario_dict['Importe_Transcargo'] = 0.00

#                                 #Calculando precio por seguro de carga
#                                 if current_inventario.Volumen:
#                                     current_inventario_dict['Importe_Seguro_Carga'] = 96.00
#                                     current_factura['Importe_Seguro_Carga_Total'] += current_inventario_dict['Importe_Seguro_Carga']
#                                 else:
#                                     current_inventario_dict['Importe_Seguro_Carga'] = 0.00

#                                 #Calculando precio por servicio de corresponsalia
#                                 if current_inventario.Volumen:
#                                     current_inventario_dict['Importe_Servicio_Corresponsalia'] = 57.00
#                                     current_factura['Importe_Servicio_Corresponsalia_Total'] += current_inventario_dict['Importe_Servicio_Corresponsalia']
#                                 else:
#                                     current_inventario_dict['Importe_Servicio_Corresponsalia'] = 0.00

#                                 #Calculando precio por transportacion
#                                 if current_inventario.Volumen and request.POST.get('incluir_transportacion_ena') == 'on':
#                                     if current_inventario.Destinatario.Municipio.Importe_por_entrega:
#                                         current_inventario_dict['Importe_Transportacion'] = current_inventario.Destinatario.Municipio.Importe_por_entrega
#                                         # print('importe transportacion',current_inventario_dict['Importe_Transportacion'])
#                                         if request.POST.get('trasbordo') == 'on':
#                                             current_inventario.trasbordo = True
#                                             current_inventario.save()
#                                             if current_inventario.Destinatario.Municipio.Importe_por_trasbordo:
#                                                 # print('importe transportacion',current_inventario_dict['Importe_Transportacion'])
                                                
#                                                 current_inventario_dict['Importe_Transportacion'] += float(current_inventario.Destinatario.Municipio.Importe_por_trasbordo)
#                                                 # print('importe transportacion con trasbordo',current_inventario_dict['Importe_Transportacion'])
#                                     else:
#                                         current_inventario_dict['Importe_Transportacion'] = 0.00
#                                     current_factura['Importe_Transportacion_Total'] += current_inventario_dict['Importe_Transportacion']
#                                 else:
#                                     current_inventario_dict['Importe_Transportacion'] = 0.00

#                                 #Calculando total de bultos
#                                 current_factura['Cantidad_Bultos_Total'] += current_inventario.Cantidad_Bultos

#                                 #Agregando informacion a la lista
#                                 current_lista_de_inventarios.append(current_inventario_dict)

#                             #Facturacion de Menaje
#                             if current_inventario.Categoria_Operacion == 'MENAJE' or current_inventario.Categoria_Operacion == 'Menaje' or current_inventario.Categoria_Operacion == 'menaje': 
#                                 #Calculando el importe de transcargo
#                                 if current_inventario.Volumen:
#                                     if current_inventario.Volumen <= 1:
#                                         current_inventario_dict['Importe_Transcargo'] = 765.00
#                                     if current_inventario.Volumen > 1:
#                                         current_inventario_dict['Importe_Transcargo'] = round((765.00 * float(current_inventario.Volumen)), 2)
                                    
#                                     current_factura['Importe_Transcargo_Total'] += current_inventario_dict['Importe_Transcargo']
#                                 else:
#                                     current_inventario_dict['Importe_Transcargo'] = 0.00

#                                 #Calculando precio por seguro de carga
#                                 if current_inventario.Volumen:
#                                     current_inventario_dict['Importe_Seguro_Carga'] = 240.00
#                                     current_factura['Importe_Seguro_Carga_Total'] += current_inventario_dict['Importe_Seguro_Carga']
#                                 else:
#                                     current_inventario_dict['Importe_Seguro_Carga'] = 0.00

#                                 #Calculando precio por servicio de corresponsalia
#                                 if current_inventario.Volumen:
#                                     current_inventario_dict['Importe_Servicio_Corresponsalia'] = 57.00
#                                     current_factura['Importe_Servicio_Corresponsalia_Total'] += current_inventario_dict['Importe_Servicio_Corresponsalia']
#                                 else:
#                                     current_inventario_dict['Importe_Servicio_Corresponsalia'] = 0.00

#                                 #Calculando precio por transportacion
#                                 if current_inventario.Volumen and request.POST.get('incluir_transportacion_ena') == 'on':
#                                     if current_inventario.Destinatario.Municipio.Importe_por_entrega:
#                                         current_inventario_dict['Importe_Transportacion'] = current_inventario.Destinatario.Municipio.Importe_por_entrega
#                                         if request.POST.get('trasbordo') == 'on':
#                                             current_inventario.trasbordo = True
#                                             current_inventario.save()
#                                             if current_inventario.Destinatario.Municipio.Importe_por_trasbordo:
#                                                 # print('importe transportacion',current_inventario_dict['Importe_Transportacion'])
                                                
#                                                 current_inventario_dict['Importe_Transportacion'] += float(current_inventario.Destinatario.Municipio.Importe_por_trasbordo)
#                                                 # print('importe transportacion con trasbordo',current_inventario_dict['Importe_Transportacion'])
#                                     else:
#                                         current_inventario_dict['Importe_Transportacion'] = 0.00
#                                     current_factura['Importe_Transportacion_Total'] += current_inventario_dict['Importe_Transportacion']
#                                 else:
#                                     current_inventario_dict['Importe_Transportacion'] = 0.00

#                                 #Calculando total de bultos
#                                 current_factura['Cantidad_Bultos_Total'] += current_inventario.Cantidad_Bultos

#                                 #Agregando informacion a la lista
#                                 current_lista_de_inventarios.append(current_inventario_dict)

#                     current_factura['Destinatario'] = Destinatario.objects.filter(CI = current_destinatario).first()
#                     current_factura['Inventarios'] = current_lista_de_inventarios
#                     #Valor total de la factura

#                     if current_inventario.Volumen: 
#                         current_factura['Precio_Total_Factura'] = current_factura['Importe_Transcargo_Total'] + current_factura['Importe_Seguro_Carga_Total'] + current_factura['Importe_Servicio_Corresponsalia_Total'] + current_factura['Importe_Transportacion_Total'] + current_factura['Importe_Recargo_Total'] + current_factura['Importe_Derecho_Aduanal_Total'] + current_factura['Importe_Servicio_Aduanal_Total'] + ((current_factura['Importe_Derecho_Aduanal_Total'] * 1.10)/100) + ((current_factura['Importe_Servicio_Aduanal_Total'] * 1.10)/100)
#                     else:
#                         current_factura['Precio_Total_Factura'] = current_factura['Importe_Recargo_Total'] + current_factura['Importe_Derecho_Aduanal_Total'] + current_factura['Importe_Servicio_Aduanal_Total'] 

#                     try:
#                         with transaction.atomic():
#                             #Almacenando la factura en el sistema
#                             factura_instance = Factura()
#                             factura_instance.Contenido = str(current_factura)
#                             factura_instance.isMultiple = True
#                             factura_instance.isEnvio = False
#                             factura_instance.Estado = 'Creada'
#                             factura_instance.Fecha = now()
#                             factura_instance.User_Facturador = request.user
#                             factura_instance.Destinatario = current_factura['Destinatario']
#                             factura_instance.Importe_Total_Factura = current_factura['Precio_Total_Factura']
#                             factura_instance.Importe_Transcargo_Total = current_factura['Importe_Transcargo_Total']
#                             factura_instance.Importe_Seguro_Carga_Total = current_factura['Importe_Seguro_Carga_Total']
#                             factura_instance.Importe_Recargo_Total = current_factura['Importe_Recargo_Total']
#                             factura_instance.Importe_Transportacion_Total = current_factura['Importe_Transportacion_Total']
#                             factura_instance.Importe_Derecho_Aduanal_Total = current_factura['Importe_Derecho_Aduanal_Total']
#                             factura_instance.Importe_Servicio_Aduanal_Total = current_factura['Importe_Servicio_Aduanal_Total']
#                             factura_instance.Importe_Servicio_Corresponsalia_Total = current_factura['Importe_Servicio_Corresponsalia_Total']
#                             factura_instance.Cantidad_Bultos_Total = current_factura['Cantidad_Bultos_Total']
#                             #factura_instance.url = str(request.path) + '?importe_derecho_aduanal=' + str(current_factura['Importe_Derecho_Aduanal_Total']) + '&importe_servicio_aduanal=' + str(current_factura['Importe_Servicio_Aduanal_Total']) + '&cargos_extra=' + str(current_factura['Importe_Recargo_Total'])
#                             factura_instance.save()
                            
#                             for current_inventario_object in current_factura['Inventarios']:
#                                 factura_inventario_instance = Factura_Inventario()
#                                 factura_inventario_instance.Factura = factura_instance
#                                 factura_inventario_instance.Inventario = current_inventario_object['Inventario']
#                                 factura_inventario_instance.Importe_Seguro_Carga = current_inventario_object['Importe_Seguro_Carga']                                
#                                 factura_inventario_instance.Importe_Servicio_Corresponsalia = current_inventario_object['Importe_Servicio_Corresponsalia']                                
#                                 factura_inventario_instance.Importe_Transportacion = current_inventario_object['Importe_Transportacion']                                
#                                 factura_inventario_instance.Importe_Transcargo = current_inventario_object['Importe_Transcargo']
#                                 factura_inventario_instance.save()
                            
#                             # Registro de trazas
#                             save_addition(request.user, 'factura', factura_instance.id, str(model_to_dict(factura_instance)))
#                     except:
#                         raise ValueError('Ha ocurrido un error generando la factura') 

#                     #Generando codigo QR de la factura
#                     # qr = qrcode.QRCode()
#                     # qr.add_data('{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}')
#                     # qr.make()
#                     # img = qr.make_image()
#                     # img.save(MEDIA_ROOT +'/QR/factura_' + str(factura_instance.id) +'.png')
#                     qr_generado = "id_transaccion:" + str(factura_instance.id) 
#                     #Identificador de la factura
#                     current_factura['id_factura'] = factura_instance.id
#                     current_factura['facturador'] = factura_instance.User_Facturador.get_full_name()

#                     #Agregando factura a lista general de facturas
#                     lista_facturas.append(current_factura)

#                 #Generando reporte PDF
#                 template_src = 'pdf/facturacion_multiple_ena_menaje_pdf.html'
#                 template = get_template(template_src)
#                 context = {'lista_facturas': lista_facturas, 'fecha_factura': now(), 'request': request}
#                 html  = template.render(context)
#                 result = BytesIO()
#                 pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
#                 if not pdf.err:
#                     return HttpResponse(result.getvalue(), content_type='application/pdf')
#                 return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))
        
#         except Exception as inst:
#             print(inst)
#             messages.error(request, 'Ha ocurrido un error generando el comprobante de pago')
#             return redirect(request.path) 

#     #Buscando inventarios sin facturar    
#     inventarios_sin_facturar = []
#     with connection.cursor() as cursor:
#         cursor.execute(""" SELECT "inventario_inventario"."id" FROM "inventario_inventario" 
#                             WHERE "inventario_inventario"."id" NOT IN (
#                             SELECT "inventario_factura_inventario"."Inventario_id" FROM "inventario_factura_inventario"
#                             INNER JOIN "inventario_factura" ON "inventario_factura_inventario"."Factura_id" = "inventario_factura"."id"
#                             WHERE not "inventario_factura"."Estado" = 'Desestimada'
#                             )
#                             AND "inventario_inventario"."Nacionalizado" = true """)
#         row = cursor.fetchall()
#         for current in row:
#             inventarios_sin_facturar.append(list(current)[0])
        
#     #Lista de inventarios nacionalizados sin facturar    
#     inventarios = Inventario.objects.all().filter(Q(Estado = 'Inventario'), Q(id__in = inventarios_sin_facturar)).order_by('HBL')

#     #Aplicacion de filtros
#     inventario_filter = InventarioFilter(request.GET, queryset=inventarios)
#     inventarios = inventario_filter.qs

#     #Paginator
#     paginator = Paginator(inventarios, 400) # Show 100 contacts per page.
#     page_number = request.GET.get('page')
#     page_obj = paginator.get_page(page_number)

#     #Buscando ENA y Envios
#     if inventarios.filter(Q(Categoria_Operacion__icontains = 'envio') | Q(Categoria_Operacion__icontains = 'envío')).count() > 0:
#         isEnvio = True

#     if inventarios.filter(Q(Categoria_Operacion__icontains = 'ENA') | Q(Categoria_Operacion__icontains = 'E.N.A')).count() > 0:
#         isEna_menaje = True

#     if inventarios.filter(Q(Categoria_Operacion__icontains = 'Menaje')).count() > 0:
#         isEna_menaje = True
    
#     ctx = {'page_obj': page_obj, 'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'inventario_filter': inventario_filter, 'isEnvio': isEnvio, 'isEna_Menaje': isEna_menaje,'form_hbl_escaneados':form_hbl_escaneados}
#     return render(request, 'inventario/inventario_list.html', ctx)
@login_required(login_url='login')
def hbl_no_escaneado_temporal(request):
    #Informacion para el template
    header_text     = 'Cargas no escaneadas'
    breadcrumb_text = 'Cargas no escaneadas'
    #Definiendo menu activo
    active_menu = 'comprobante_pago_destinatario'

    operaciones_de_tablas(request)
    cargas_temporales = Temporal_HBL_Escaneados.objects.all()
    isNoEscaneado = True
    ctx = {'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'cargas_temporales':cargas_temporales,'isNoEscaneado':isNoEscaneado}
    return render(request, 'inventario/inventario_no_escaneado.html', ctx)

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
    hbl_destinatario_no_escaneados = []
    hbl_escaneados = []

    #Ejecutando operaciones de las tablas
    operaciones_de_tablas(request)
    if request.method == 'POST':
        # try:
            
            list_inventario_selected = ''

            if request.POST.get('HBL'):
                #Informacion para el template
                header_text     = 'Cargas no escaneadas'
                breadcrumb_text = 'Cargas no escaneadas'
                #Definiendo menu activo
                active_menu = 'comprobante_pago_destinatario'

                #Comprobante desde escaner
                hbl_regex = re.compile(r'[A-Z0-9*]*')
                
                #Obtengo informacion del formulario
                hbl_escaneados_list=request.POST.get('HBL')
                no_contenedor=request.POST.get('No_Contenedor')

                list_inventario_selected = re.findall(hbl_regex,hbl_escaneados_list)
                
                #Obtengo los inventarios que coinciden con los HBL escaneados
                # inventarios = Inventario.objects.all().filter(HBL__in = list_inventario_selected,No_Contenedor=no_contenedor)
                inventarios = Inventario.objects
                if list_inventario_selected:
                    inventarios= inventarios.filter(HBL__in = list_inventario_selected)
                if no_contenedor:
                    es_guia= Inventario.objects.filter(AWB=no_contenedor)
                    es_contenedor= Inventario.objects.filter(No_Contenedor=no_contenedor)
                    if es_contenedor:
                        inventarios= inventarios.filter(No_Contenedor = no_contenedor)
                    if es_guia:
                        inventarios= inventarios.filter(AWB = no_contenedor)
         
                #Lista de facturas a pasar a la vista
                lista_facturas = []
                
                #Obteniendo lista de destinatarios de la solicitud
                lista_de_destinatarios = [] #Lista de destinatarios
                for current_inventario in inventarios:
                    lista_de_destinatarios.append(current_inventario.Destinatario.CI)
                
                #Obtengo todos los HBL de cada destinatario
                for destinatario in lista_de_destinatarios:
                    # hbl_destinatario = Inventario.objects.filter(Destinatario__CI=destinatario,No_Contenedor=no_contenedor)
                    hbl_destinatario = Inventario.objects.filter(Destinatario__CI=destinatario,Estado='Inventario')
                    hbl_escaneados = []
                    for hbl in hbl_destinatario:
                        hbl_sin_escanear = hbl.HBL not in list_inventario_selected
                        hbl_escaneado = hbl.HBL in list_inventario_selected
                        if hbl_escaneado:
                            inventario_escaneado=Inventario.objects.get(HBL=hbl.HBL)
                            hbl_escaneados.append(inventario_escaneado)

                        if hbl_sin_escanear == True:
                            inventario = Inventario.objects.get(HBL=hbl.HBL)
                            destinatario = Destinatario.objects.get(id=inventario.Destinatario.id)
                            hbl_destinatario_no_escaneados.append(inventario)
                            
                            #Verifica si está en la tabla temporal
                            guardado_en_temporal = Temporal_HBL_Escaneados.objects.filter(Inventario=inventario)
                            
                            if not guardado_en_temporal:
                                #Guardo inventario en tabla temporal
                                hbl_no_escaneado = Temporal_HBL_Escaneados()
                                hbl_no_escaneado.Inventario=inventario
                                hbl_no_escaneado.Destinatario=destinatario
                                hbl_no_escaneado.isEscaneado=False
                                hbl_no_escaneado.save()
                   
                    if hbl_destinatario_no_escaneados:
                        for carga in hbl_escaneados:
                            # #Verifica si está en la tabla temporal
                            # inventario = Inventario.objects.get(id=carga)
                            # destinatario = Destinatario.objects.get(id=inventario.Destinatario.id)

                            guardado_en_temporal = Temporal_HBL_Escaneados.objects.filter(Inventario=carga)
                            
                            if not guardado_en_temporal:
                                #Guardo inventario en tabla temporal
                                hbl_no_escaneado = Temporal_HBL_Escaneados()
                                hbl_no_escaneado.Inventario=carga
                                hbl_no_escaneado.Destinatario=destinatario
                                hbl_no_escaneado.isEscaneado=True
                                hbl_no_escaneado.save()

                    if not hbl_destinatario_no_escaneados:
                        inventarios_envios = hbl_destinatario.filter((Q(Categoria_Operacion__icontains = 'envio') | Q(Categoria_Operacion__icontains = 'envío')), Q(HBL__in = list_inventario_selected))
                        inventarios_ena_menaje = Inventario.objects.all().filter(~Q(Categoria_Operacion__icontains = 'envio'), ~Q(Categoria_Operacion__icontains = 'envío'), Q(HBL__in = list_inventario_selected))

                        if inventarios_envios: 
                            #Lista de facturas a pasar a la vista
                            lista_facturas = []
                            
                            #Obteniendo lista de destinatarios de la solicitud
                            lista_de_destinatarios = [] #Lista de destinatarios
                            for current_inventario in inventarios_envios:
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
                                current_factura['Importe_Recargo_Total'] = 0
                                current_factura['Importe_Transportacion_Total'] = 0.00 
                                current_factura['Importe_Derecho_Aduanal_Total'] = 0.00 
                                current_factura['Importe_Servicio_Aduanal_Total'] = 0.00 
                                current_factura['Cantidad_Bultos_Total'] = 0 
                                current_factura['Importe_Kg_Adicional_Total'] = 0.00

                                lista_inventarios_por_persona = inventarios.filter(Destinatario__CI = current_destinatario)
                                inventario_persona = lista_inventarios_por_persona.first()
                                corresponsal = inventario_persona.Agencia if inventario_persona else None
                                destinatario_obj = Destinatario.objects.filter(CI=current_destinatario).first()
                                provincia = destinatario_obj.Provincia if destinatario_obj else None
                                current_factura['Corresponsal'] = corresponsal
                                current_factura['Provincia'] = provincia
                                # ++++++++++++++++++++++
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
                                        current_factura['Importe_Transcargo_Total'] = 0.00
                                        current_factura['Importe_Seguro_Carga_Total'] = 0.00
                                        current_factura['Importe_Sobredimension_Total'] = 0.00
                                        current_factura['Importe_Recargo_Total'] = 0.00
                                        current_factura['Importe_Transportacion_Total'] = 0.00
                                        current_factura['Cantidad_Bultos_Total'] += current_inventario.Cantidad_Bultos
                                       
                                        #Agregando informacion a la lista
                                        current_inventario_dict['Importe_Seguro_Carga'] = 0.00
                                        current_inventario_dict['Importe_Sobredimension'] = 0.00
                                        current_inventario_dict['Importe_Transportacion'] = 0.00
                                        current_inventario_dict['Importe_Transcargo'] = 0.00
                                        current_lista_de_inventarios.append(current_inventario_dict)
                                        if current_inventario.Peso:
                                            if current_inventario.Peso < 20.00:
                                                current_inventario_dict['Importe_KG_Adicional'] = 0.00
                                            if current_inventario.Peso > 20.00:
                                                kg_adicional = current_inventario.Peso - 20
                                                current_inventario_dict['Importe_KG_Adicional'] = kg_adicional * 5
                                                current_inventario.Importe_Kg_Adicional = kg_adicional * 5
                                                current_inventario.save()
                                            current_factura['Importe_Kg_Adicional_Total'] += current_inventario_dict['Importe_KG_Adicional']
                                        else:
                                            current_inventario_dict['Importe_KG_Adicional'] = 0.00

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
                                        
                                        if current_inventario.Peso:
                                            if current_inventario.Peso < 20.00:
                                                current_inventario_dict['Importe_KG_Adicional'] = 0.00
                                            if current_inventario.Peso > 20.00:
                                                kg_adicional = current_inventario.Peso - 20
                                                current_inventario_dict['Importe_KG_Adicional'] = kg_adicional * 5

                                            current_factura['Importe_Kg_Adicional_Total'] += current_inventario_dict['Importe_KG_Adicional']
                                        else:
                                            current_inventario_dict['Importe_KG_Adicional'] = 0.00

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
                                    current_inventario.isFacturado = True
                                    current_inventario.save()

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
                                        factura_instance.Importe_Kg_Adicional_Total = current_factura['Importe_Kg_Adicional_Total']
                                        #factura_instance.url = str(request.path) + '?cargos_extra=' + str(current_factura['Importe_Recargo_Total'])
                                        factura_instance.Agencia=current_factura['Corresponsal']
                                        factura_instance.Provincia=current_factura['Provincia']
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
                                qr_generado = '{' + str(factura_instance.id) +'}'
                                # qr_generado = '{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}'
                                current_factura['id_factura'] = factura_instance.id
                                current_factura['facturador'] = factura_instance.User_Facturador.get_full_name()
                                
                                #Agregando factura a lista general de facturas
                                lista_facturas.append(current_factura)
                            #Generando reporte PDF
                            # template_src = 'pdf/Copia_facturacion_multiple_envios_pdf.html'
                            # template = get_template(template_src)
                            context = {'lista_facturas': lista_facturas,'fecha_factura': now(),'request': request,'qr':qr_generado}
                            # html  = template.render(context)
                            # result = BytesIO()
                            # pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
                            # if not pdf.err:
                            #     return HttpResponse(result.getvalue(), content_type='application/pdf')
                            # return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))
                            return render(request, 'pdf/Copia_facturacion_multiple_envios_pdf.html',context)
                            # context = {'lista_facturas': lista_facturas, 'fecha_factura': current_factura_object.Fecha, 'request': request,'qr':qr_generado}
                            # html  = template.render(context)
                            # result = BytesIO()
                            # pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
                            # if not pdf.err:
                            #     return HttpResponse(result.getvalue(), content_type='application/pdf')
                            # return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))
                            # return render(request, 'pdf/Copia_facturacion_multiple_envios_pdf.html',context)

                        if inventarios_ena_menaje:
                            #Lista de facturas a pasar a la vista
                            lista_facturas = []
                            qr_generado=''
                            #Obteniendo lista de destinatarios de la solicitud
                            lista_de_destinatarios = [] #Lista de destinatarios
                            for current_inventario in inventarios_ena_menaje:
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
                                if request.POST.get('cargos_extra_ena') or request.POST.get('cargos_extra_ena') != 0:
                                    current_factura['Importe_Recargo_Total'] = float(request.POST.get('cargos_extra_ena'))
                                else:
                                    cargos_extra_ena = 0
                                    current_factura['Importe_Recargo_Total'] = float(cargos_extra_ena)

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
                                        current_factura['Importe_Recargo_Total'] = 0.00
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

                                    current_inventario.isFacturado = True
                                    current_inventario.save()
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
                                qr_generado = '{' + str(factura_instance.id) +'}'
                                # qr_generado = '{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}'

                                #Identificador de la factura
                                current_factura['id_factura'] = factura_instance.id
                                current_factura['facturador'] = factura_instance.User_Facturador.get_full_name()

                                #Agregando factura a lista general de facturas
                                lista_facturas.append(current_factura)

                            #Generando reporte PDF
                            template_src = 'pdf/facturacion_multiple_ena_menaje_pdf.html'
                            template = get_template(template_src)
                            context = {'lista_facturas': lista_facturas, 'fecha_factura': now(), 'request': request, 'qr':qr_generado}
                            html  = template.render(context)
                            result = BytesIO()
                            pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
                            if not pdf.err:
                                return HttpResponse(result.getvalue(), content_type='application/pdf')
                            return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))
            
            else:   
                list_inventario_selected = request.POST.getlist('inventario_id')

                #Recorriendo todos los inventarios seleccionados
                for inventario in list_inventario_selected:
                    Temporal_HBL_Escaneados.objects.filter(Inventario__id=inventario).delete()
                if request.POST.get('operacion_tabla') == 'facturar_envios':
                    if not list_inventario_selected:
                        messages.error(request, 'Debe seleccionar al menos un envío para generar el comprobante')
                        return redirect(request.path)

                    #Lista de inventarios a facturar
                    inventarios = Inventario.objects.all().filter((Q(Categoria_Operacion__icontains = 'envio') | Q(Categoria_Operacion__icontains = 'envío')), Q(pk__in = list_inventario_selected))
                    if not inventarios.exists():
                        messages.error(request, 'Las cargas seleccionadas no son envíos. No se pudo generar el comprobante.')
                        return redirect(request.path)

                    #Lista de facturas a pasar a la vista
                    lista_facturas = []
                    qr_generado=''
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
                        current_factura['Importe_Recargo_Total'] = 0.0
                        current_factura['Importe_Transportacion_Total'] = 0.00 
                        current_factura['Importe_Derecho_Aduanal_Total'] = 0.00 
                        current_factura['Importe_Servicio_Aduanal_Total'] = 0.00 
                        current_factura['Cantidad_Bultos_Total'] = 0 
                        #*********************************************************
                        current_factura['Importe_Kg_Adicional_Total'] = 0.00 

                        lista_inventarios_por_persona = inventarios.filter(Destinatario__CI = current_destinatario)
                        # ---------------------------------------------------
                        inventario_x = lista_inventarios_por_persona.first()
                        provincia=Provincia.objects.filter(id=inventario_x.Destinatario.Provincia.id)
                        corresponsal=Agencia.objects.filter(id=inventario_x.Agencia.id)
                        #print('provincia',provincia)
                        #print('corresponsal',corresponsal)
                        # ----------------------------------------------------
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
                                
                                current_factura['Importe_Transcargo_Total'] = 0.00
                                current_factura['Importe_Seguro_Carga_Total'] = 0.00
                                current_factura['Importe_Sobredimension_Total'] = 0.00
                                current_factura['Importe_Recargo_Total'] = 0.00
                                current_factura['Importe_Transportacion_Total'] = 0.00
                                current_factura['Cantidad_Bultos_Total'] += current_inventario.Cantidad_Bultos

                                if current_inventario.Peso:
                                    if current_inventario.Peso <= 20:
                                        current_inventario_dict['Importe_Kg_Adicional'] = 0.00
                                        current_inventario.Importe_Kg_Adicional = 0.00
                                        current_inventario.save()
                                    if current_inventario.Peso > 20:
                                        #
                                        current_inventario_dict['Importe_Kg_Adicional'] = (current_inventario.Peso - 20) * 5

                                        current_factura['Importe_Kg_Adicional_Total'] += current_inventario_dict['Importe_Kg_Adicional']
                                        current_inventario.Importe_Kg_Adicional = (current_inventario.Peso - 20) * 5
                                        current_inventario.save()
                                else:
                                    current_inventario_dict['Importe_Kg_Adicional'] = 0.00
                               
                                #Agregando informacion a la lista
                                current_inventario_dict['Importe_Seguro_Carga'] = 0.00
                                current_inventario_dict['Importe_Sobredimension'] = 0.00
                                current_inventario_dict['Importe_Transportacion'] = 0.00
                                current_inventario_dict['Importe_Transcargo'] = 0.00
                                current_lista_de_inventarios.append(current_inventario_dict)

                            else:    
                                # #Calculando importe de kg adicional
                                if current_inventario.Peso:
                                    if current_inventario.Peso <= 20:
                                        current_inventario_dict['Importe_Kg_Adicional'] = 0.00
                                        current_inventario.Importe_Kg_Adicional= 0
                                        current_inventario.save()
                                    if current_inventario.Peso > 20:
                                        #
                                        current_inventario_dict['Importe_Kg_Adicional'] = (current_inventario.Peso - 20) * 5
                                        current_factura['Importe_Kg_Adicional_Total'] += current_inventario_dict['Importe_Kg_Adicional']
                                        current_inventario.Importe_Kg_Adicional= (current_inventario.Peso - 20) * 5
                                        current_inventario.save()
                                else:
                                    current_inventario_dict['Importe_Kg_Adicional'] = 0.00

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

                                #Calculando total de bultos
                                current_factura['Cantidad_Bultos_Total'] += current_inventario.Cantidad_Bultos

                                #Agregando informacion a la lista
                                current_lista_de_inventarios.append(current_inventario_dict)

                            current_inventario.isFacturado = True
                            current_inventario.save()
                            
                        current_factura['Destinatario'] = Destinatario.objects.filter(CI = current_destinatario).first()
                        current_factura['Inventarios'] = current_lista_de_inventarios
                        #Valor total de la factura
                        current_factura['Precio_Total_Factura'] = current_factura['Importe_Kg_Adicional_Total'] + current_factura['Importe_Transcargo_Total'] + current_factura['Importe_Seguro_Carga_Total'] + current_factura['Importe_Sobredimension_Total'] + current_factura['Importe_Recargo_Total'] + current_factura['Importe_Transportacion_Total'] + current_factura['Importe_Derecho_Aduanal_Total'] + current_factura['Importe_Servicio_Aduanal_Total']

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
                                factura_instance.Importe_Kg_Adicional_Total = current_factura['Importe_Kg_Adicional_Total']
                                factura_instance.Cantidad_Bultos_Total = current_factura['Cantidad_Bultos_Total']
                                #factura_instance.url = str(request.path) + '?cargos_extra=' + str(current_factura['Importe_Recargo_Total'])
                                if request.POST.get('presencial') == 'on':
                                    factura_instance.Presencial=True
                                else:
                                    factura_instance.Presencial=False
                             
                                factura_instance.Provincia = provincia.first() if hasattr(provincia, 'first') else provincia
                                factura_instance.Agencia = corresponsal.first() if hasattr(corresponsal, 'first') else corresponsal
                                factura_instance.save()
                                for current_inventario_object in current_factura['Inventarios']:
                                    factura_inventario_instance = Factura_Inventario()
                                    factura_inventario_instance.Factura = factura_instance
                                    factura_inventario_instance.Inventario = current_inventario_object['Inventario']
                                    factura_inventario_instance.Importe_Seguro_Carga = 0.00
                                    factura_inventario_instance.Importe_Sobredimension = 0.00
                                    factura_inventario_instance.Importe_Transportacion = 0.00
                                    factura_inventario_instance.Importe_Transcargo = 0.00
                                    factura_inventario_instance.save()

                                # Registro de trazas
                                save_addition(request.user, 'factura', factura_instance.id, str(model_to_dict(factura_instance)))
                        except Exception as e:
                            logging.exception('Error generando comprobante de envío')
                            raise ValueError('Ha ocurrido un error generando la factura: %s' % e) from e

                        
                        num_fac=str(factura_instance.id)
                        if len(num_fac.split('/')[0]) < 12:
                            num_fac = str(current_inventario.Manifiesto).zfill(12)
                            #print('num_fac',num_fac)
                       
                        #Generando codigo de barra de la factura
                        try:
                            os.makedirs(os.path.join(str(MEDIA_ROOT), 'QR'), exist_ok=True)
                            code39 = barcode.get_barcode_class('code39')
                            code = code39(str(factura_instance.id), writer=ImageWriter(), add_checksum=False)
                            fullname = code.save(os.path.join(str(MEDIA_ROOT), 'QR', 'factura_' + str(factura_instance.id)))
                        except Exception:
                            logging.exception('No se pudo generar el código de barras de la factura %s', factura_instance.id)
                        
                        #Generando codigo QR de la factura
                        
                        qr_generado = '{' + str(factura_instance.id) +'}'
                        #qr_generado = '{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}'
                        current_factura['id_factura'] = factura_instance.id
                        current_factura['facturador'] = factura_instance.User_Facturador.get_full_name()
                        
                        #Agregando factura a lista general de facturas
                        lista_facturas.append(current_factura)

                    #Generando reporte PDF
                    # template_src = 'pdf/Copia_facturacion_multiple_envios_pdf.html'
                    # template = get_template(template_src)
                    context = {'lista_facturas': lista_facturas,'fecha_factura': now(),'request': request,'qr':qr_generado}
                    # html  = template.render(context)
                    # result = BytesIO()
                    # pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
                    # if not pdf.err:
                    #     return HttpResponse(result.getvalue(), content_type='application/pdf')
                    # return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))
                    return render(request, 'pdf/Copia_facturacion_multiple_envios_pdf.html',context)
                        # context = {'lista_facturas': lista_facturas, 'fecha_factura': factura_instance.Fecha, 'request': request,'qr':qr_generado}
                        # # html  = template.render(context)
                        # # result = BytesIO()
                        # # pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
                        # # if not pdf.err:
                        # #     return HttpResponse(result.getvalue(), content_type='application/pdf')
                        # # return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))
                        # return render(request, 'pdf/Copia_facturacion_multiple_envios_pdf.html',context)

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
                                current_factura['Importe_Recargo_Total'] = 0.00
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

                            current_inventario.isFacturado = True
                            current_inventario.save()
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
                        

                        code39 = barcode.get_barcode_class('code39')
                        code = code39(str(factura_instance.id), writer=ImageWriter(),add_checksum=False)
                        barcode_generado = code.save(MEDIA_ROOT + '/QR/factura_' + str(factura_instance.id))

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
        
        # except Exception as inst:
        #     # print(inst)
        #     messages.error(request, 'Ha ocurrido un error generando el comprobante de pago')
        #     return redirect(request.path) 

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
        
    # Lista de inventarios nacionalizados sin facturar.
    # No se exige importe de aduana distinto de 0: los envíos suelen tenerlo en 0
    # y no deben quedar fuera del comprobante. Se incluyen cargas sin incidencia.
    inventarios = Inventario.objects.filter(
        Q(Incidencia__isnull=True) | ~Q(Incidencia__Tipo__icontains='Faltante'),
        Estado='Inventario',
        Nacionalizado=True,
        id__in=inventarios_sin_facturar,
    ).order_by('HBL')

    #Aplicacion de filtros
    inventario_filter = InventarioFilter(request.GET, queryset=inventarios)
    inventarios = inventario_filter.qs

    #Paginator
    paginator = Paginator(inventarios, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Esta pantalla es de comprobantes de envío: la acción debe estar siempre disponible.
    isEnvio = True

    if inventarios.filter(Q(Categoria_Operacion__icontains = 'ENA') | Q(Categoria_Operacion__icontains = 'E.N.A')).count() > 0:
        isEna_menaje = True

    if inventarios.filter(Q(Categoria_Operacion__icontains = 'Menaje')).count() > 0:
        isEna_menaje = True
    
    if len(hbl_destinatario_no_escaneados) !=0:
        # inventarios = Temporal_HBL_Escaneados.objects.filter(id__in=hbl_destinatario_no_escaneados)
        cargas_temporales_no_escaneadas = Temporal_HBL_Escaneados.objects.filter(Inventario__in=hbl_destinatario_no_escaneados)
        cargas_temporales_escaneadas = Temporal_HBL_Escaneados.objects.filter(Inventario__in=hbl_escaneados)
        cargas_temporales=list(chain(cargas_temporales_no_escaneadas,cargas_temporales_escaneadas))
        isNoEscaneado = True

        ctx = {'page_obj': page_obj, 'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'inventario_filter': inventario_filter, 'isEnvio': isEnvio, 'isEna_Menaje': isEna_menaje, 'cargas_temporales':cargas_temporales,'isNoEscaneado':isNoEscaneado}
        return render(request, 'inventario/inventario_no_escaneado.html', ctx)

    else:
        ctx = {'page_obj': page_obj, 'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'inventario_filter': inventario_filter, 'isEnvio': isEnvio, 'isEna_Menaje': isEna_menaje,'form_hbl_escaneados':form_hbl_escaneados}
        return render(request, 'inventario/inventario_list.html', ctx)
        



@login_required(login_url='login')
def cancelar_generacion_automatica_comprobantes_destinatarios(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404
    
    # operaciones_de_tablas(request) 
    
    #Definiendo menu activo
    active_menu = 'comprobante_pago_destinatario'
    header_text = ''
    breadcrumb_text = ''
    #Formulario de factura
    form_cobro_factura = Factura_Cobrada_Form()

    #Fomulario para seleccionar rango de fecha de facturas a exportar
    form_rango_fechas=Reporte_Contable_Aduana_Form()

    #Lista de manifiestos
    Facturas = Factura.objects.filter(~Q(Estado = 'Desestimada'), ~Q(Estado = 'Cobrada')).order_by('-id')

    #Aplicacion de filtros
    facturas_filter = FacturaFilter(request.GET, queryset=Facturas)
    Facturas = facturas_filter.qs

    #Paginator
    paginator = Paginator(Facturas, 100) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    ctx = {'page_obj': page_obj, 'facturas_filter': facturas_filter, 'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu}
    return render(request, 'factura/factura_list.html', ctx)

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
                    current_comprobante.User_Cobrador = request.user.first_name + ' ' + request.user.last_name
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
                            current_inventario.User_Cobrador = request.user.first_name + ' ' + request.user.last_name    
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

# ---------------------------

@login_required(login_url='login')
def comprobante_entrega_pago_parcial(request, id_comprobante):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Definiendo menu activo
    active_menu = 'comprobante_pago_operador'
    action = ''

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

                #Obteniendo el comprobante de entrega de operador
                comprobante_operador = Factura_Operador.objects.get(pk = id_comprobante)

                for current_comprobante_id in request.POST.getlist('comprobante_id'):
                    current_comprobante = Factura.objects.get(pk = current_comprobante_id)
                    current_comprobante.Fecha_Cobro = request.POST.get('fecha_entrega')
                    current_comprobante.Estado = 'Cobrada'
                    current_comprobante.Recibo_Ingreso = request.POST.get('recibo_ingreso')
                    current_comprobante.save()

                    # Registro de trazas
                    save_edition(request.user, 'factura', current_comprobante.id, str(model_to_dict(current_comprobante)))

                    #Actualizando valor cobrado del comprobante del operador
                    comprobante_operador.Importe_Cobrado += current_comprobante.Importe_Total_Factura 
                    comprobante_operador.save()

                    #Declarando inventario como entregado
                    for current_inventario in current_comprobante.Inventario.all():
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

                #Comprobando si todo el comprobante fue cobrado
                if comprobante_operador.Facturas_Destinatarios.filter(~Q(Estado = 'Cobrada')).count() == 0:
                    comprobante_operador.Fecha_Cobro = request.POST.get('fecha_entrega')
                    comprobante_operador.Estado = 'Cobrada'
                    comprobante_operador.Recibo_Ingreso = request.POST.get('recibo_ingreso')
                    comprobante_operador.save()
                    
                # Registro de trazas
                save_edition(request.user, 'factura_operador', comprobante_operador.id, str(model_to_dict(comprobante_operador)))   

                messages.success(request, 'Comprobantes cobrados satisfactoriamente.')
                return redirect(reverse('comprobante_entrega_operadores'))
        
        except Exception as inst:
            # print(inst)
            messages.error(request, 'Ha ocurrido un error en el proceso')
            messages.error(request, inst)
            return redirect(request.path)

    comprobantes_destinatarios = Factura_Operador.objects.get(pk = id_comprobante).Facturas_Destinatarios.filter(~Q(Estado = 'Cobrada')).order_by('Fecha')

    ctx = {'active_menu': active_menu, 'action': action, 'comprobantes_destinatarios': comprobantes_destinatarios }
    return render(request, 'entrega/entrega_pago_parcial.html', ctx)


@login_required(login_url='login')
def comprobante_entrega_detalles_pago(request, id_comprobante):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Definiendo menu activo
    active_menu = 'comprobante_pago_operador'
    action = ''

    comprobantes_destinatarios = Factura_Operador.objects.get(pk = id_comprobante).Facturas_Destinatarios.all().order_by('Fecha')

    ctx = {'active_menu': active_menu, 'action': action, 'comprobantes_destinatarios': comprobantes_destinatarios }
    return render(request, 'entrega/entrega_detalles_pago.html', ctx)

# -----------------------------
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
                usuario=User.objects.get(id=request.user.id)
                for factura_id in list_facturas:
                    current_factura = Factura.objects.get(pk = factura_id)
                    if current_factura.Estado == 'Creada':
                        current_factura.Estado = 'Cobrada'
                        current_factura.Fecha_cobro = form_cobro_factura.cleaned_data['Fecha_Cobro']
                        current_factura.Recibo_Ingreso = request.POST.get('recibo_ingreso')
                        current_factura.User_Cobrador = usuario.first_name + ''+ usuario.last_name
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
                            current_inventario.User_Cobrador = usuario.first_name + ' '+ usuario.last_name
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
                for inv in current_factura.Inventario.all():
                    inv.isFacturado = False
                    inv.save()
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
            columns = ['No. Factura', 'Importe','HBL']
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

            buffer = BytesIO()
            wb.save(buffer)
            filename = 'Facturas ' + fecha_desde + ' - ' + fecha_hasta + '.xlsx'
            response = HttpResponse(
                buffer.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
            response['Content-Disposition'] = 'attachment; filename="%s"' % filename
            return response


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
        current_factura['Importe_Kg_Adicional_Total'] = current_factura_object.Importe_Kg_Adicional_Total
        current_factura['Destinatario'] = current_factura_object.Destinatario
        current_factura['facturador'] = current_factura_object.User_Facturador.get_full_name()
        current_factura['Cantidad_Bultos_Total'] = current_factura_object.Cantidad_Bultos_Total
        current_factura['Inventarios'] = Factura_Inventario.objects.filter(Factura = current_factura_object)
        #Valor total de la factura
        current_factura['Precio_Total_Factura'] = current_factura_object.Importe_Total_Factura
        #Identificador de la factura
        current_factura['id_factura'] = current_factura_object.id
        current_factura['facturador'] = current_factura_object.User_Facturador.get_full_name()

        #Agregando factura a lista general de facturas
        lista_facturas.append(current_factura)

        code39 = barcode.get_barcode_class('code39')
        code = code39(str(current_factura_object.id), writer=ImageWriter(),add_checksum=False)
        fullname = code.save(MEDIA_ROOT + '/QR/factura_' + str(current_factura_object.id))

        #QR datos de transaccion
        #qr_generado = '{"id_transaccion": ' + str(current_factura_object.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}' 
        qr_generado = '{' + str(current_factura_object.id) +'}'
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

        code39 = barcode.get_barcode_class('code39')
        code = code39(str(current_factura_object.id), writer=ImageWriter(),add_checksum=False)
        fullname = code.save(MEDIA_ROOT + '/QR/factura_' + str(current_factura_object.id))

        #QR datos de transaccion
        #qr_generado = '{"id_transaccion": ' + str(current_factura_object.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}' 
        qr_generado = '{' + str(current_factura_object.id) +'}'
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

        code39 = barcode.get_barcode_class('code39')
        code = code39(str(current_factura_object.id), writer=ImageWriter(),add_checksum=False)
        fullname = code.save(MEDIA_ROOT + '/QR/factura_' + str(current_factura_object.id))

        # #QR datos de transaccion
        # qr_generado = '{"id_transaccion": ' + str(current_factura_object.id) + ', "importe": ' + str(current_inventario_dict['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}' 
        qr_generado = '{' + str(current_factura_object.id) +'}'
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
    chapa = Chapa.objects.get(Chapa=entrega.Chapa,transportista__id=transportista.id)
    # chapa = get_object_or_404(Chapa,Chapa = id_Chapa.Chapa)
    importe_pendiente_pago = current_factura.Importe - current_factura.Importe_Cobrado
    #Generando reporte PDF
    template_src = 'pdf/facturacion_operador.html'
    template = get_template(template_src)
    context = {'importe_pendiente_pago':importe_pendiente_pago,'current_factura': current_factura,'transportista':transportista,'entrega':entrega, 'request': request,'chapa':chapa}
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
    tracking_cargas = []
    if request.method == 'POST':
        if not request.POST.get('HBL') and not request.POST.get('CI') and not request.POST.get('Nombre'):
            messages.error(request, 'Debe ingresar alguno de los datos anteriores.')
        else:
            try:

                #Obteniendo inventario
                current_inventario = ''
                inventarios = Inventario.objects
                # Por HBL
                if request.POST.get('HBL'):
                    inventarios = inventarios.filter(HBL = request.POST.get('HBL'))
                
                #Por CI
                if request.POST.get('CI'):
                    inventarios = inventarios.filter(Destinatario__CI = request.POST.get('CI'))

                #Por Nombre
                if request.POST.get('Nombre'):
                    inventarios = inventarios.filter(Destinatario__Nombre = request.POST.get('Nombre'))

                #Obteniendo traking de inventario
                for inventario in inventarios:
                    current_traking = Traking.objects.filter(Inventario = inventario).order_by('Fecha')
                    tracking_inventario = {}
                    tracking_inventario['carga'] = inventario
                    tracking_inventario['tracking_cargas'] = current_traking
                    tracking_cargas.append(tracking_inventario)

                # id_factura = Factura_Inventario.objects.filter(Inventario=inventarios.first()).values('id')
                # if id_factura:
                #     id_facturas_operador = Factura_Operador
                #     operador = Entrega.objects.filter()
                
            except Exception as inst:
                #print(inst)
                messages.error(request, 'El dato ingresado no se encuentra registrado en el sistema.')
                return redirect(request.path)
        
    ctx = {'current_traking': tracking_cargas, 'current_inventario': current_inventario,'traking_form':traking_form}
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
    #print(contenido_no_multiple_uno[3])
    #print(contenido_no_multiple_uno[4])
    #print(contenido_no_multiple_uno[5])
    #print(contenido_no_multiple_uno[6])
    #print(contenido_no_multiple_uno[7])
    contenido_para_json = '{' + contenido_no_multiple_uno[3] + ', ' + contenido_no_multiple_uno[4] + ', ' + contenido_no_multiple_uno[5] + ', ' + contenido_no_multiple_uno[6] + ', ' + contenido_no_multiple_uno[7]
    contenido_json = json.loads(contenido_para_json.replace("'", '"'))

    #print(contenido_json)
    
    HBL_current = contenido_no_multiple_uno[0].replace("{'Inventario': <Inventario: ", '').replace('>', '')
    current_inventario = Inventario.objects.filter(HBL = HBL_current).first()
    #print(current_inventario.Importe_Derecho_aduanal)
    

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

    resp_strip = strip_tags(resp.content)
    dict = resp_strip.replace('\\', '').replace("b'n", ""). replace("n'", "")
    dicto = json.loads(dict)
    


    
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
                hbl_regex=''
                #HBL escaneados
                hbls = request.POST.get('HBL')
               # print('VERIFYYYYYY')
               # print('hbls',hbls)
                if request.POST.get('QR_multiple') == 'off':
                    hbl_regex = re.compile(r'[A-Z0-9-]*')
                if request.POST.get('QR_multiple') == 'on':
                    hbl_regex = re.compile(r'((number)(.){4})([A-Za-z0-9-\/*.]{1,})')
                 #   print('multiple')
                #print('hbl_regex',hbl_regex)

                no_contenedor = request.POST.get('No_Contenedor')
                seleccion = re.findall(hbl_regex,hbls)
                #print('seleccion',seleccion)
                # -----------------------------------------
                hbl_mutiple_regex = re.compile(r'[A-Z0-9-]*')
                

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
    titulo = 'Parte diario'
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
                ena_list=['ENA','E.N.A','ena','e.n.a','Ena']
                envio_list=['Envío','envío','ENVIO']

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
                envio_list=['Envío','envío','ENVIO']
                ena_list=['ENA','E.N.A','ena','e.n.a','Ena']

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
            
    ctx = {'titulo':titulo,'active_menu': active_menu, 'inventario_filter': inventario_filter,'inventario_provincia':data,'valores_totales':valores_totales,'inventario_habana':data_habana}
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
        if not request.POST.get('Almacen'):
            messages.error(request, 'Debe seleccionar el almacén.')
            return redirect(request.path)
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

            inventarios = Inventario.objects.all()

            #Entrada de mercancías
            manifiestos_Guia_Aerea = Manifiesto.objects.filter(Fecha_Importacion__gte=fecha_desde,Fecha_Importacion__lte=fecha_hasta).values_list('AWB', flat=True)
            manifiestos_No_Contenedor = Manifiesto.objects.filter(Fecha_Importacion__gte=fecha_desde,Fecha_Importacion__lte=fecha_hasta).values_list('No_Contenedor', flat=True)
            manifiestos_Manifiesto = Manifiesto.objects.filter(Fecha_Importacion__gte=fecha_desde,Fecha_Importacion__lte=fecha_hasta).values_list('Manifiesto', flat=True)
         
            dicto_entrada = {}
            dicto_entrada['Contenedor'] = list(manifiestos_No_Contenedor) + list(manifiestos_Guia_Aerea)
            dicto_entrada['Manifiesto'] = manifiestos_Manifiesto
            bultos_contenedor=inventarios.filter(No_Contenedor__in=list(manifiestos_No_Contenedor),Manifiesto__in=list(manifiestos_Manifiesto)).aggregate(Sum('Cantidad_Bultos'))
            bultos_awb=inventarios.filter(AWB__in=list(manifiestos_Guia_Aerea),Manifiesto__in=list(manifiestos_Manifiesto)).aggregate(Sum('Cantidad_Bultos'))
            dicto_entrada['Total_Bultos']=bultos_contenedor['Cantidad_Bultos__sum'] + bultos_awb['Cantidad_Bultos__sum']
            dicto_entrada['Total_HBL']=inventarios.filter(No_Contenedor__in=list(manifiestos_No_Contenedor),Manifiesto__in=list(manifiestos_Manifiesto)).values('HBL').distinct().count() + inventarios.filter(AWB__in=list(manifiestos_Guia_Aerea),Manifiesto__in=list(manifiestos_Manifiesto)).values('HBL').distinct().count()
            data.append(dicto_entrada)

           
            #Mercancías devueltas
            devoluciones = Inventario_Reincorporado.objects.filter(Fecha__gte=fecha_desde,Fecha__lte=fecha_hasta,Inventario__Almacen=almacen)
            
            for current_devolucion in devoluciones:
                dicto_devolucion = {}
                entrega = Entrega.objects.get(Factura_Operador=current_devolucion.Factura_Operador)
                dicto_devolucion['Vehiculo']=Chapa.objects.filter(transportista=entrega.Transportista.id,Chapa=entrega.Chapa).first()
                dicto_devolucion['No_Factura_Operador']=current_devolucion.Factura_Operador.id
                dicto_devolucion['HBL']=current_devolucion.Inventario.HBL
                dicto_devolucion['Cantidad_Bultos']=current_devolucion.Inventario.Cantidad_Bultos
                data_devoluciones.append(dicto_devolucion)

            #Mercancías despachadas por aduana
            ena_list=['ENA','E.N.A','ena','e.n.a','Ena','Menaje','MENAJE']
            envio_list=['Envío','envío','ENVIO','Menaje','MENAJE']
            dicto_nacionalizacion = {}
            dicto_nacionalizacion['Cantidad_HBL'] = inventarios.filter(Fecha_Nacionalizacion__gte=fecha_desde,Fecha_Nacionalizacion__lte=fecha_hasta,Almacen=almacen).values('HBL').distinct().count()
            dicto_nacionalizacion['Cantidad_Clientes'] = inventarios.filter(Fecha_Nacionalizacion__gte=fecha_desde,Fecha_Nacionalizacion__lte=fecha_hasta,Almacen=almacen).values('Destinatario').distinct().count()
            dicto_nacionalizacion['Cantidad_Bultos'] = inventarios.filter(Fecha_Nacionalizacion__gte=fecha_desde,Fecha_Nacionalizacion__lte=fecha_hasta,Almacen=almacen).aggregate(Sum('Cantidad_Bultos'))
            dicto_nacionalizacion['Cantidad_Bultos'] = dicto_nacionalizacion['Cantidad_Bultos']['Cantidad_Bultos__sum']
            dicto_nacionalizacion['Cantidad_Envios'] = Inventario.objects.filter(Fecha_Nacionalizacion__gte=fecha_desde,Fecha_Nacionalizacion__lte=fecha_hasta,Almacen=almacen).exclude(Categoria_Operacion__in=ena_list).aggregate(Sum('Cantidad_Bultos'))
            dicto_nacionalizacion['Cantidad_Envios'] = dicto_nacionalizacion['Cantidad_Envios']['Cantidad_Bultos__sum']
            dicto_nacionalizacion['Cantidad_ENA'] = inventarios.filter(Fecha_Nacionalizacion__gte=fecha_desde,Fecha_Nacionalizacion__lte=fecha_hasta,Almacen=almacen).exclude(Categoria_Operacion__in=envio_list).aggregate(Sum('Cantidad_Bultos'))
            dicto_nacionalizacion['Cantidad_ENA'] = dicto_nacionalizacion['Cantidad_ENA']['Cantidad_Bultos__sum']
            data_nacionalizaciones.append(dicto_nacionalizacion)
            g = inventarios.filter(Fecha_Nacionalizacion__gte=fecha_desde,Fecha_Nacionalizacion__lte=fecha_hasta,Almacen=almacen).values('HBL').distinct().count()

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
            dicto_pendientes_distribucion['Cantidad_HBL']= inventarios.filter(Fecha_Nacionalizacion__gte=fecha_desde,Fecha_Nacionalizacion__lte=fecha_hasta,Estado='Inventario',Almacen=almacen).values('HBL').distinct().count()
            dicto_pendientes_distribucion['Cantidad_Bultos']= inventarios.filter(Fecha_Nacionalizacion__gte=fecha_desde,Fecha_Nacionalizacion__lte=fecha_hasta,Estado='Inventario',Almacen=almacen).aggregate(Sum('Cantidad_Bultos'))
            dicto_pendientes_distribucion['Cantidad_Bultos']=dicto_pendientes_distribucion['Cantidad_Bultos']['Cantidad_Bultos__sum']
            dicto_pendientes_distribucion['Cantidad_M3']= inventarios.filter(Fecha_Nacionalizacion__gte=fecha_desde,Fecha_Nacionalizacion__lte=fecha_hasta,Estado='Inventario',Almacen=almacen).aggregate(Sum('Volumen'))
            dicto_pendientes_distribucion['Cantidad_M3']=dicto_pendientes_distribucion['Cantidad_M3']['Volumen__sum']
            
            destinos_prox_distribucion=inventarios.filter(Fecha_Nacionalizacion__gte=fecha_desde,Fecha_Nacionalizacion__lte=fecha_hasta,Estado='Inventario',Almacen=almacen)
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
    data = []
    if request.method == 'POST':
        if not request.POST.get('Fecha_Desde') or not request.POST.get('Fecha_Hasta'):
            messages.error(request, 'Debe seleccionar el rango de fecha')
            return redirect(request.path)
        if request.POST.get('Fecha_Desde') and request.POST.get('Fecha_Hasta'):

            try:
                #Obteniendo datos de formulario
                fecha_desde = datetime.strptime(str(request.POST.get('Fecha_Desde')), '%Y-%m-%d')
                fecha_hasta = datetime.strptime(str(request.POST.get('Fecha_Hasta')), '%Y-%m-%d')
                empresa = None
                current_transportista = None
                
                entregas = Entrega.objects.filter(Fecha_Entrega__gte=fecha_desde,Fecha_Entrega__lte=fecha_hasta).select_related('Factura_Operador')
                                  
                if request.POST.get('Empresa'):
                    empresa = Empresa.objects.get(pk = request.POST.get('Empresa'))

                if request.POST.get('Transportista'):
                    transportista = Transportista.objects.get(pk = request.POST.get('Transportista'))
                    entrega = {}
                    entrega['empresa'] = empresa
                    entregas_transportista = entregas.filter(~Q(Estado='Cancelado'),Q(Transportista__id=request.POST.get('Transportista')))
                    entrega['transportista'] = transportista
                    chapa = []   
                    destinos=[]
                    for provincia in Provincia.objects.all():
                        destino = {}
                        destino['provincia'] = provincia
                        destino['cantidad_bultos'] = 0
                       
                        for entrega_transportista in entregas_transportista:                            
                            for vv in entrega_transportista.Factura_Operador.Facturas_Destinatarios.all():
                                if vv.Destinatario.Provincia.id == provincia.id:
                                    destino['cantidad_bultos'] += vv.Cantidad_Bultos_Total
                            chapa.append(entrega_transportista.Chapa) 
                        destino['cantidad_bultos'] = destino['cantidad_bultos']                 
                        destinos.append(destino)
                    entrega['chapa'] = set(chapa)
                    entrega['destinos'] = destinos
                    data.append(entrega)
  
                if not request.POST.get('Transportista'):
                    datos_entregas = []
                    for transportista in Transportista.objects.all():
                        entrega = {}
                        entrega['empresa'] = transportista.Empresa
                        entregas_transportista = entregas.filter(Transportista__id = transportista.id)
                        entrega['transportista'] = transportista
                        chapa = []
                        destinos=[]
                        for provincia in Provincia.objects.all():
                            destino = {}
                            destino['provincia'] = provincia
                            destino['cantidad_bultos'] = 0
                            for entrega_transportista in entregas_transportista:
                                for vv in entrega_transportista.Factura_Operador.Facturas_Destinatarios.all():
                                    if vv.Destinatario.Provincia.id == provincia.id:
                                        destino['cantidad_bultos'] += vv.Cantidad_Bultos_Total
                                chapa.append(entrega_transportista.Chapa)  
                            destino['cantidad_bultos'] = destino['cantidad_bultos']                 
                            destinos.append(destino)
                        if chapa:
                            entrega['chapa'] = set(chapa)
                        else:
                            entrega['chapa'] = ''
                        entrega['destinos'] = destinos
                        datos_entregas.append(entrega)
                    data = datos_entregas

            except:
                messages.error(request, 'Ocurrió un error en la búsqueda de los datos')
        else:
            messages.error(request, 'Debe ingresar los datos requeridos.')

    ctx = {'active_menu': active_menu,'form':form_reporte_diario,'bultos_despachados':transportistas, 'fecha_desde': fecha_desde, 'fecha_hasta': fecha_hasta,'datos':data}
    return render(request, 'reportes/reporte_transportistas.html', ctx)


def nacionalizar_cargas():
    list_inventario = Inventario.objects.filter(Nacionalizado=False,Estado='Inventario')
    for current_inventario in list_inventario:
        #Obteniendo inventario
        # current_inventario = Inventario.objects.get(id = current_inventario.id)
        current_inventario = Inventario.objects.get(id = current_inventario.id)
        
        try:
            #Capturando valores de la aduana
            man = str(current_inventario.Manifiesto)
           # print('man',man)
           # print('hbl',current_inventario.HBL)
           # print('contenedor',current_inventario.No_Contenedor)
           # print('AWB',current_inventario.AWB)
            if current_inventario.No_Contenedor:
                if len(man.split('/')[0]) < 4:
                    man = str(current_inventario.Manifiesto).zfill(4)
            
            if len(man.split('/')) == 1:
                man = man + '/' + str(current_inventario.Fecha_Entrada_Puerto.year)

            #dicto = {'success': True, 'despachos': [{'BOLETIN_DERECHO': '171021047035915000007', 'NO_BLGA': 'MAY21110540', 'MANIFIESTOS': '0358/2021', 'VALOR_DERECHOS': '0', 'VALOR_SERVICIO': '50'}]}
            USUARIO = 'aerov'
            PASS = 'eh7443fx'
            MANIFIESTO = man
            HBL = current_inventario.HBL
            if current_inventario.AWB:
                HBL = current_inventario.AWB + ' '+ current_inventario.HBL
            # if current_inventario.No_Contenedor:
            #     HBL = current_inventario.HBL
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

           # print('dicto',dicto)
            if dicto['success'] == True:
                #Actualizando inventario
                current_inventario.Nacionalizado = True
                current_inventario.Importe_Derecho_aduanal = float(dicto['despachos'][0]['VALOR_DERECHOS'])
                current_inventario.Importe_Servicio_aduanal = float(dicto['despachos'][0]['VALOR_SERVICIO'])
                current_inventario.Precio = 0
                current_inventario.Categoria_Operacion = 'ENVIO'
                current_inventario.Fecha_Nacionalizacion = datetime.now()
                current_inventario.save()
                #Salvando Tracking
                traking = Traking()
                traking.Inventario      = current_inventario
                traking.Estado          = 'Inventario'
                traking.Observaciones   = 'Despachado por aduana'
                traking.Fecha           = now()
                traking.save()
                # Registro de trazas
                save_addition('traking', traking.id, str(model_to_dict(traking)))
             
           
        except:
            pass



# Tarea a ejecutarse cada determinado tiempo.
def timer():
    while True:
        nacionalizar_cargas()
        time.sleep(10)   # 10 segundos.
 # Iniciar la ejecución en segundo plano.
t = threading.Thread(target=timer, daemon=True)
t.start()


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
            fecha_desde = datetime.strptime(str(request.POST.get('Fecha_Desde')), '%Y-%m-%d')
            fecha_hasta = datetime.strptime(str(request.POST.get('Fecha_Hasta')), '%Y-%m-%d')

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
                    imported_data = dataset.load(file.read(), format='xls', headers=False)
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


                    manifiestos = Manifiesto.objects.filter(Fecha_Importacion__gte=fecha_desde,Fecha_Importacion__lte=fecha_hasta)
                    list_no_contenedor = []
                    for manifiesto in manifiestos:
                        list_no_contenedor.append(manifiesto.No_Contenedor)

                    cargas_en_inventario= Inventario.objects.filter(Estado='Inventario',Almacen__id=almacen,No_Contenedor__in=list_no_contenedor).exclude(HBL__in=inventario_almacen)
                    
            except Exception as inst:
                messages.error(request, 'Ha ocurrido un error importando el manifiesto. Por favor revise la línea ' + str(int(No_fila) + 2))
                messages.error(request, inst)

    ctx = {'active_menu': active_menu, 'form': form,'inventarios_no_existentes':cargas_en_inventario}
    return render(request, 'reportes/reporte_levantamiento_inventario.html', ctx)


@login_required(login_url='login')
def inventario_fisico(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Consultor', 'Operador']).exists()) and not request.user.is_superuser:
        raise Http404

    #Formulario de tabla
    form_hbl_escaneados = HBL_Escaneados_Form()
    inventarios_no_manifestados =[]
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
        seleccion = re.findall(hbl_regex,list_comprobantes)
        seleccion = set(seleccion)

        inventarios = Inventario.objects.all().filter(HBL__in=seleccion).order_by('HBL')
        inventarios_no_manifestados = Inventario.objects.all().filter(HBL__in=seleccion)
    #Aplicacion de filtros
    inventario_filter = InventarioFilter(request.GET, queryset=inventarios)

    inventarios = inventario_filter.qs
    #Paginator
    paginator = Paginator(inventarios, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {'page_obj': page_obj, 'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'inventario_filter': inventario_filter, 'form_hbl_escaneados':form_hbl_escaneados,'inventarios_no_manifestados':inventarios_no_manifestados}
    return render(request, 'reportes/inventario_fisico.html', ctx)




# ---------------------Manual de Ayuda---------------------------------
@login_required(login_url='login')
def pagina_inicio_manual(request):
    header_text     = 'Manual'
    breadcrumb_text = 'Manual'
    #Definiendo menu activo
    active_menu = 'pagina_inicio_manual'

    ctx = {'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu}
    return render(request, 'manual_ayuda/pagina_inicio.html', ctx)    

@login_required(login_url='login')
def modulo_inventario(request):
    header_text     = 'Manual'
    breadcrumb_text = 'Módulo inventario'
    #Definiendo menu activo
    active_menu = 'pagina_inicio_manual'

    ctx = {'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu}
    return render(request, 'manual_ayuda/modulo_inventario.html', ctx)

@login_required(login_url='login')
def modulo_facturacion(request):
    header_text     = 'Manual'
    breadcrumb_text = 'Módulo de facturación'
    #Definiendo menu activo
    active_menu = 'pagina_inicio_manual'

    ctx = {'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu}
    return render(request, 'manual_ayuda/modulo_facturacion.html', ctx)  

@login_required(login_url='login')
def manual_reportes(request):
    header_text     = 'Manual'
    breadcrumb_text = 'Reportes'
    #Definiendo menu activo
    active_menu = 'manual_reportes'

    ctx = {'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu}
    return render(request, 'manual_ayuda/modulo_reportes.html', ctx)  
# -----------------------Fin Manual de Ayuda---------------------------


@login_required(login_url='login')
def exportar_facturas_to_dbf(request):

    #Informacion para el template
    titulo     = 'Exportar facturas'
    header_text     = 'Exportar facturas'
    breadcrumb_text = 'Exportar facturas'
    #Definiendo menu activo
    active_menu = 'exportar_facturas_to_dbf'
    form = Reporte_Contable_Aduana_Form()
    file = False
    if request.method == 'POST':
        data = []
        facturas = ''
        data_presencial = []
        facturas_presenciales = ''
        fecha = date.today()
        if request.POST.get('Fecha_Desde') and request.POST.get('Fecha_Hasta'):
            facturas = Factura_Operador.objects.prefetch_related('Facturas_Destinatarios').filter(Estado = 'Cobrada',Fecha_Creacion__gte=request.POST.get('Fecha_Desde'),Fecha_Creacion__lte=request.POST.get('Fecha_Hasta')).values_list('id','Fecha_Creacion','Fecha_Cobro','Importe','Facturas_Destinatarios__Destinatario__Provincia')
            facturas_presenciales = Factura.objects.filter(Estado = 'Cobrada',Fecha__gte=request.POST.get('Fecha_Desde'),Fecha__lte=request.POST.get('Fecha_Hasta'),Presencial=True).values_list('id','Fecha','Fecha_cobro','Importe_Total_Factura','Destinatario__Provincia__Nombre')
        elif not request.POST.get('Fecha_Desde') and not request.POST.get('Fecha_Hasta'):    
            
            facturas = Factura_Operador.objects.prefetch_related('Facturas_Destinatarios').filter(Estado = 'Cobrada',Fecha_Creacion__year=fecha.year,Fecha_Creacion__month=fecha.month,Fecha_Creacion__day=fecha.day).values_list('id','Fecha_Creacion','Fecha_Cobro','Importe','Facturas_Destinatarios__Destinatario__Provincia')
            facturas_presenciales = Factura.objects.filter(Estado = 'Cobrada',Fecha__year=fecha.year,Fecha__month=fecha.month,Fecha__day=fecha.day,Presencial=True).values_list('id','Fecha','Fecha_cobro','Importe_Total_Factura','Destinatario__Provincia__Nombre')
            
        else:
            messages.error(request, 'Debe ingresar la fecha de inicio y la fecha de fin o ninguna fecha')
            ctx = {'titulo':titulo,'active_menu': active_menu, 'inventario_filter': form}
            return render(request, 'reportes/reporte_parte_diario.html', ctx)

        # Facturas de entrega puerta a puerta
        nombre_fichero=MEDIA_ROOT + '/manifiestos/Facturas_Puerta_Puerta.dbf'
        table = dbf.Table(nombre_fichero, 'comprobant N(4,0); empresa C(4); cuenta C(20); cto_gto C(4); doc C(20); concepto C(2); fec_val D; descrip C(30); importe N(15,0); debito L; cod_fc C(2); fec_con D; libro C(1); tasa N(13,0); moneda C(3); referencia C(20); fecha_venc D; observac M;')
        provincias = Provincia.objects.filter(~Q(Nombre = 'Mayabeque'),~Q(Nombre = 'Artemisa'),~Q(Nombre = 'La Habana'),~Q(Nombre = 'Isla de la Juventud'))
        

        for current_factura in facturas:
            importe_kg_adicional = 0
            importe_aduana = 0
            ingreso = []
            ingreso_aduana = []
            debito = []
            destino = ''
            cuenta_debito = ''
            if current_factura[4]:
                destino = Provincia.objects.get(id=current_factura[4])
            
            if destino:
                facturas_destinatarios = Factura_Operador.objects.get(id=current_factura[0]).Facturas_Destinatarios.all()
                
                for factura in facturas_destinatarios:

                    importe_aduana += factura.Importe_Derecho_Aduanal_Total
                    importe_aduana += factura.Importe_Servicio_Aduanal_Total
                    if factura.Importe_Kg_Adicional_Total:
                        importe_kg_adicional += factura.Importe_Kg_Adicional_Total

                # #Comprobante
                debito.append(current_factura[0])
                #Empresa
                debito.append('304')
                #Cuenta
                debito.append('101100041')
                #Centro de costo
                debito.append('')
                doc = 'FAC-'+str(current_factura[0])
                #Documento
                debito.append(doc)
                #Concepto
                debito.append('')
                #Fecha de validacion (Fecha actual) 
                debito.append(dbf.Date(fecha))
                #Descripción (Deposito de efectivo)
                debito.append('Entrega Puerta a Puerta')
                #Importe
                debito.append(current_factura[3])
                #Debito
                debito.append(1)
                #Cod fc
                debito.append('')
                #Fecha de confeccion de la factura
                debito.append(dbf.Date(current_factura[1]))
                #Libro
                debito.append('G')
                #Tasa
                debito.append(1.00000000)
                #Moneda
                debito.append('CUP')
                #Referencia
                debito.append('')
                #Fecha venc
                debito.append(dbf.Date())
                #Observaciones
                debito.append('')
                data.append(tuple(debito))


                # #Comprobante
                ingreso.append(current_factura[0])
                #Empresa
                ingreso.append('304')
                #Cuenta
                ingreso.append('91010001185')
                #Centro de costo
                ingreso.append('5709')
                #Documento
                ingreso.append('')
                #Concepto
                ingreso.append('')
                #Fecha de validacion (Fecha actual) 
                ingreso.append(dbf.Date(fecha))
                #Descripción (Deposito de efectivo)
                ingreso.append('Entrega Puerta a Puerta')
                #Importe
                ingreso.append(importe_kg_adicional)
                #Debito
                ingreso.append(0)
                #Cod fc
                ingreso.append('')
                #Fecha de confeccion de la factura
                ingreso.append(dbf.Date(current_factura[1]))
                #Libro (Fecha de creacion)
                ingreso.append('G')
                #Tasa
                ingreso.append(1.00000000)
                #Moneda
                ingreso.append('CUP')
                #Referencia
                ingreso.append('')
                #Fecha venc
                ingreso.append(dbf.Date())
                #Observaciones
                ingreso.append('')
                data.append(tuple(ingreso))

                
                # #Comprobante
                ingreso_aduana.append(current_factura[0])
                #Empresa
                ingreso_aduana.append('304')
                #Cuenta
                ingreso_aduana.append('40710020712001')
                #Centro de costo
                ingreso_aduana.append('')
                #Documento
                doc = 'FAC-'+str(current_factura[0])
                ingreso_aduana.append(doc)
                #Concepto
                ingreso_aduana.append('')
                #Fecha de validacion (Fecha actual) 
                ingreso_aduana.append(dbf.Date(fecha))
                #Descripción (Deposito de efectivo)
                ingreso_aduana.append('Entrega Puerta a Puerta')
                #Importe
                ingreso_aduana.append(importe_aduana)
                #Debito
                ingreso_aduana.append(0)
                #Cod fc
                ingreso_aduana.append('')
                #Fecha de confeccion de la factura
                ingreso_aduana.append(dbf.Date(current_factura[1]))
                #Libro (Fecha de creacion)
                ingreso_aduana.append('G')
                #Tasa
                ingreso_aduana.append(1.00000000)
                #Moneda
                ingreso_aduana.append('CUP')
                #Referencia
                ingreso_aduana.append('')
                #Fecha venc
                ingreso_aduana.append(dbf.Date())
                #Observaciones
                ingreso_aduana.append('')
                data.append(tuple(ingreso_aduana))
        data = tuple(data)
        table.open(mode=dbf.READ_WRITE)
        for datum in data:
            table.append(datum)
        table.close()


        #······························· Facturas presencial··································#
        nombre_fichero_presencial=MEDIA_ROOT + '/manifiestos/Facturas_Presencial.dbf'
        table_presencial = dbf.Table(nombre_fichero_presencial, 'comprobant N(4,0); empresa C(4); cuenta C(20); cto_gto C(4); doc C(20); concepto C(2); fec_val D; descrip C(30); importe N(15,0); debito L; cod_fc C(2); fec_con D; libro C(1); tasa N(13,0); moneda C(3); referencia C(20); fecha_venc D; observac M;')
        ingreso_presencial = []
        debito_presencial = []
        importe = 0
        for current_factura in facturas_presenciales:                 
            if current_factura[4] == 'La Habana' or current_factura[4] == 'Artemisa' or current_factura[4] == 'Mayabeque' or current_factura[4] == 'Isla de la Juventud':

                importe += current_factura[3]
                
        # #Comprobante
        debito_presencial.append(1)
        #Empresa
        debito_presencial.append('304')
        #Cuenta
        debito_presencial.append('101100041')
        #Centro de costo
        debito_presencial.append('')
        #Documento
        debito_presencial.append('')
        #Concepto
        debito_presencial.append('')
        #Fecha de validacion (Fecha actual) 
        debito_presencial.append(dbf.Date(fecha))
        #Descripción
        debito_presencial.append('Cobro Presencial')
        #Importe
        debito_presencial.append(importe)
        #Debito
        debito_presencial.append(1)
        #Cod fc
        debito_presencial.append('')
        #Fecha de confeccion de la factura
        debito_presencial.append(dbf.Date(fecha))
        #Libro (Fecha de creacion)
        debito_presencial.append('G')
        #Tasa
        debito_presencial.append('1.00000000')
        #Moneda
        debito_presencial.append('CUP')
        #Referencia
        debito_presencial.append('')
        #Fecha venc
        debito_presencial.append(dbf.Date())
        #Observaciones
        debito_presencial.append('')

        data_presencial.append(tuple(debito_presencial))


        #Comprobante
        ingreso_presencial.append(1)
        #Empresa
        ingreso_presencial.append('304')
        #Cuenta
        ingreso_presencial.append('91010001185')
        #Centro de costo
        ingreso_presencial.append('5709')
        #Documento
        ingreso_presencial.append('')
        #Concepto
        ingreso_presencial.append('')
        #Fecha de validacion (Fecha actual) 
        ingreso_presencial.append(dbf.Date(fecha))
        #Descripción
        ingreso_presencial.append('Cobro Presencial')
        #Importe
        ingreso_presencial.append(importe)
        #Debito
        ingreso_presencial.append(0)
        #Cod fc
        ingreso_presencial.append('')
        #Fecha de confeccion de la factura
        ingreso_presencial.append(dbf.Date(fecha))
        #Libro (Fecha de creacion)
        ingreso_presencial.append('G')
        #Tasa
        ingreso_presencial.append(1.00000000)
        #Moneda
        ingreso_presencial.append('CUP')
        #Referencia
        ingreso_presencial.append('')
        #Fecha venc
        ingreso_presencial.append(dbf.Date())
        #Observaciones
        ingreso_presencial.append('')
        data_presencial.append(tuple(ingreso_presencial))

        data_presencial = tuple(data_presencial)


        # #Comprobante
        ingreso_aduana.append(current_factura[0])
        #Empresa
        ingreso_aduana.append('304')
        #Cuenta
        ingreso_aduana.append('41610030')
        #Centro de costo
        ingreso_aduana.append('')
        #Documento
        doc = 'FAC-'+str(current_factura[0])
        ingreso_aduana.append(doc)
        #Concepto
        ingreso_aduana.append('')
        #Fecha de validacion (Fecha actual) 
        ingreso_aduana.append(dbf.Date(fecha))
        #Descripción (Deposito de efectivo)
        ingreso_aduana.append('Entrega Puerta a Puerta')
        #Importe
        ingreso_aduana.append(importe_aduana)
        #Debito
        ingreso_aduana.append(0)
        #Cod fc
        ingreso_aduana.append('')
        #Fecha de confeccion de la factura
        ingreso_aduana.append(dbf.Date(current_factura[1]))
        #Libro (Fecha de creacion)
        ingreso_aduana.append('G')
        #Tasa
        ingreso_aduana.append(1.00000000)
        #Moneda
        ingreso_aduana.append('CUP')
        #Referencia
        ingreso_aduana.append('')
        #Fecha venc
        ingreso_aduana.append(dbf.Date())
        #Observaciones
        ingreso_aduana.append('')
        data.append(tuple(ingreso_aduana))

        table_presencial.open(mode=dbf.READ_WRITE)
        for datum in data_presencial:
            table_presencial.append(datum)
        table_presencial.close()
        # table_presencial.open(mode=dbf.READ_WRITE)

        file = True
        
        messages.success(request, 'El fichero se generó correctamente')
        ctx = {'titulo':titulo,'active_menu': active_menu, 'inventario_filter': form, 'file':file}
        return render(request, 'reportes/reporte_parte_diario.html', ctx)

    ctx = {'titulo':titulo,'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'inventario_filter':form, 'file':file}
    return render(request, 'reportes/reporte_parte_diario.html', ctx)

    # ------------------------Despacho Electrónico------------------------------------------
@login_required(login_url='login')
def despacho_electronico(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404
    nacionalizad_aduana_form = Nacionalizar_Desde_Aduana_Form()
    #Definiendo titulo de página
    titulo='Despachado electrónico'
    #Definiendo menu activo
    active_menu = 'mercancia_inventario'
    #Lista de inventarios nacionalizados
    inventarios_nacionalizados=[]
    if request.method == 'POST':
        if not request.POST.get('Manifiesto') or not request.POST.get('AWB'):
            messages.error(request, 'Debe ingresar el No. de manifiesto y la Guía Aérea.')
        else:
            #try:

            inventarios = Inventario.objects.filter(Manifiesto = request.POST.get('Manifiesto'),AWB=request.POST.get('AWB'))
            if request.POST.getlist('marcado'):
                inventarios = inventarios.filter(HBL__in=request.POST.getlist('marcado'))
            #Trabajo con manifiesto para el servicio de la aduana
            #ESTO SE AGREGARA A LA SALVA DEL MANIFIESTO EN LA DB
            man = str(request.POST.get('Manifiesto'))
            if len(man.split('/')[0]) < 4:
                man = str(request.POST.get('Manifiesto')).zfill(4)
                
            if len(man.split('/')) == 1:
                man = man + '/' + str(inventarios.last().Fecha_Entrada_Puerto.year)
            #Fin
            if inventarios:
                for current_inventario in inventarios:
                # try:
                   
# ------------------------------Descomentariar----------------------------------------------------
                # with transaction.atomic():
                    #Consultar informacion de la aduana
                    USUARIO = 'aerov'
                    PASS = 'eh7443fx'
                    MANIFIESTO = man
                    HBL = current_inventario.AWB + ' '+ current_inventario.HBL
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
                        if current_inventario.Importe_Derecho_aduanal != float(dicto['despachos'][0]['VALOR_DERECHOS']) or current_inventario.Importe_Servicio_aduanal != float(dicto['despachos'][0]['VALOR_SERVICIO']):
                            current_inventario.Importe_Derecho_aduanal = float(dicto['despachos'][0]['VALOR_DERECHOS'])
                            current_inventario.Importe_Servicio_aduanal = float(dicto['despachos'][0]['VALOR_SERVICIO'])
                            current_inventario.Precio = 0
                            current_inventario.Nacionalizado = True
                            current_inventario.Estado = 'Inventario'
                            current_inventario.Fecha_Nacionalizacion = now()
                            current_inventario.save()

                            # Registro de trazas
                            save_edition(request.user, 'inventario', current_inventario.id, str(model_to_dict(current_inventario)))
                            
                    #         #Mostrando inventarios nacionalizados
                    #         inventarios_nacionalizados.append(current_inventario)
# ----------------------------------Descomentariar------------------------------------------------
                    #Fin de la consulta
                # except:
                #     pass
            # if inventarios_nacionalizados:
            #     #Lista de facturas a pasar a la vista
            #     lista_facturas = []
            #     qr_generado=''
            #     #Obteniendo lista de destinatarios de la solicitud
            #     lista_de_destinatarios = [] #Lista de destinatarios
            #     for current_inventario in inventarios:
            #         lista_de_destinatarios.append(current_inventario.Destinatario.CI)
            #     # lista_de_destinatarios = list(dict.fromkeys(lista_de_destinatarios))
            #     lista_de_destinatarios = set(lista_de_destinatarios)

            #     for current_destinatario in lista_de_destinatarios:
            #         current_factura = {}
            #         current_lista_de_inventarios = []
            #         #Cantidad de veces que se mostrara la factura 
            #         current_factura['Copias_Facturas'] = range(1)

            #         #Valores totales 
            #         current_factura['Importe_Derecho_Aduanal_Total'] = 0.00 
            #         current_factura['Importe_Servicio_Aduanal_Total'] = 0.00 
            #         current_factura['Cantidad_Bultos_Total'] = 0 
                    
            #         # inventarios_nacionalizados
            #         lista_inventarios_por_persona=[]
            #         for inventario in inventarios_nacionalizados:
            #             if inventario.Destinatario.CI == current_destinatario:
            #                 lista_inventarios_por_persona.append(inventario)
            #         # lista_inventarios_por_persona = inventarios.filter(Destinatario__CI = current_destinatario)
            #         for current_inventario in lista_inventarios_por_persona:
            #             current_inventario_dict = {}
            #             current_inventario_dict['Inventario'] = current_inventario

            #             #Calculando el importe por derechos aduanales
            #             if current_inventario.Importe_Derecho_aduanal:
            #                 current_factura['Importe_Derecho_Aduanal_Total'] += current_inventario.Importe_Derecho_aduanal

            #             #Calculando el importe por servicios aduanales
            #             if current_inventario.Importe_Servicio_aduanal:
            #                 current_factura['Importe_Servicio_Aduanal_Total'] += current_inventario.Importe_Servicio_aduanal
            #             if current_inventario.isPrepago:
            #                 current_factura['Cantidad_Bultos_Total'] += current_inventario.Cantidad_Bultos
                           
            #                 #Agregando informacion a la lista
            #                 current_inventario_dict['Importe_KG_Adicional'] = 0.00
            #                 current_lista_de_inventarios.append(current_inventario_dict)

            #             else:    
            #                 #Calculando precio por sobredimension
            #                 if current_inventario.Peso:
            #                     if current_inventario.Peso < 3.00:
            #                         current_inventario_dict['Importe_KG_Adicional'] = 0.00
            #                     if current_inventario.Peso > 20.00:
            #                         kg_adicional = current_inventario.Peso - 20
            #                         current_inventario_dict['Importe_KG_Adicional'] = kg_adicional * 5

            #                     current_factura['Importe_KG_Adicional_Total'] += current_inventario_dict['Importe_KG_Adicional']
            #                 else:
            #                     current_inventario_dict['Importe_KG_Adicional'] = 0.00
                            

            #                 #Calculando total de bultos
            #                 current_factura['Cantidad_Bultos_Total'] += current_inventario.Cantidad_Bultos

            #                 #Agregando informacion a la lista
            #                 current_lista_de_inventarios.append(current_inventario_dict)

            #         current_factura['Destinatario'] = Destinatario.objects.filter(CI = current_destinatario).first()
            #         current_factura['Inventarios'] = current_lista_de_inventarios
            #         #Valor total de la factura
            #         current_factura['Precio_Total_Factura'] = current_factura['Importe_KG_Adicional_Total'] + current_factura['Importe_Derecho_Aduanal_Total'] + current_factura['Importe_Servicio_Aduanal_Total'] 

            #         try:
            #             with transaction.atomic():
            #                 #Almacenando la factura en el sistema
            #                 factura_instance = Factura()
            #                 factura_instance.Contenido = str(current_factura)
            #                 factura_instance.isMultiple = True
            #                 factura_instance.isEnvio = True
            #                 factura_instance.Fecha = now()
            #                 factura_instance.User_Facturador = request.user
            #                 factura_instance.Estado = 'Creada'
            #                 factura_instance.Destinatario = current_factura['Destinatario']
            #                 factura_instance.Importe_Total_Factura = current_factura['Precio_Total_Factura']
            #                 factura_instance.Importe_Transcargo_Total = 0
            #                 factura_instance.Importe_Seguro_Carga_Total = 0
            #                 factura_instance.Importe_Recargo_Total = 0
            #                 factura_instance.Importe_Transportacion_Total = 0
            #                 factura_instance.Importe_Derecho_Aduanal_Total = current_factura['Importe_Derecho_Aduanal_Total']
            #                 factura_instance.Importe_Servicio_Aduanal_Total = current_factura['Importe_Servicio_Aduanal_Total']
            #                 factura_instance.Importe_Sobredimension_Total = 0
            #                 factura_instance.Importe_Kg_Adicional_Total = current_factura['Importe_Kg_Adicional_Total']
            #                 factura_instance.Cantidad_Bultos_Total = current_factura['Cantidad_Bultos_Total']
            #                 #factura_instance.url = str(request.path) + '?cargos_extra=' + str(current_factura['Importe_Recargo_Total'])
            #                 factura_instance.save()
                                
            #                 for current_inventario_object in current_factura['Inventarios']:
            #                     factura_inventario_instance = Factura_Inventario()
            #                     factura_inventario_instance.Factura = factura_instance
            #                     factura_inventario_instance.Inventario = current_inventario_object['Inventario']
            #                     factura_inventario_instance.Importe_Seguro_Carga = 0
            #                     factura_inventario_instance.Importe_Sobredimension = 0
            #                     factura_inventario_instance.Importe_Transportacion = 0
            #                     factura_inventario_instance.Importe_Transcargo = 0
            #                     factura_inventario_instance.save()

            #                 # Registro de trazas
            #                 save_addition(request.user, 'factura', factura_instance.id, str(model_to_dict(factura_instance)))
            #         except:
            #             raise ValueError('Ha ocurrido un error generando la factura')

            #         qr_generado = '{' + str(factura_instance.id)+ '}'
            #         # qr_generado = '{"id_transaccion": ' + str(factura_instance.id) + ', "importe": ' + str(current_factura['Precio_Total_Factura']) + ', "moneda": "CUP", "numero_proveedor": ' + str(settings.NUMERO_PROVEEDOR) +', "version": ""}'
            #         current_factura['id_factura'] = factura_instance.id
            #         current_factura['facturador'] = factura_instance.User_Facturador.get_full_name()
                    
            #         #Agregando factura a lista general de facturas
            #         lista_facturas.append(current_factura)

            # else:
            #     messages.error(request, 'Problemas para obtener los datos requeridos.')
            #     return redirect(request.path)




            # except Exception as inst:
            #     messages.error(request, 'Error al realizarce el despacho electrónico. Por favor verifique los datos ingresados.')
            #     return redirect(request.path)
            
    ctx = {'nacionalizad_aduana_form': nacionalizad_aduana_form, 'inventarios_nacionalizados': inventarios_nacionalizados,'titulo':titulo}
    return render(request, 'operacion_mercancia/despacho_electronico.html', ctx)
# ------------------------Fin Despacho Electrónico--------------------------------------

# ++++++++++++++++++++++++++++++++++++++++++++++++

#---------------------------------Desglose guía aérea-----------------------------------

@login_required(login_url='login')
def generar_desglose(request):
    #Validando roles
    if not (request.user.groups.filter(name__in=['Operador']).exists()) and not request.user.is_superuser:
        raise Http404
    #Definiendo titulo de página
    titulo='Desglose de manifiesto'
    #Definiendo menu activo
    active_menu = 'desglose'
    save_path_file = ''
    guia_aerea = ''
    if request.method == 'POST':
        if not request.POST.get('guia_aerea'):
            messages.error(request, 'Debe introducir la guía aérea.')
        if request.POST.get('guia_aerea'):
            ahora = datetime.now()
            nuevo_desglose = Desglose()

            guia_aerea = request.POST.get('guia_aerea')
            inventarios = Inventario.objects.filter(AWB=guia_aerea)
            if request.POST.getlist('hbl_desglosado'):
                inventarios = inventarios.filter(HBL__in=request.POST.getlist('hbl_desglosado'))

            manifiesto = Manifiesto.objects.filter(AWB=request.POST.get('guia_aerea'))
            save_path_file = MEDIA_ROOT + '/manifiestos/'+guia_aerea+'.xml'            
            
            nuevo_desglose.Desglose=save_path_file
            nuevo_desglose.save()
            
    # ---------------------------------------------------------
            document = gfg.Element('outer')
            node = gfg.SubElement(document, 'inner')
            et = gfg.ElementTree(document)

            f = BytesIO()
            et.write(f, encoding='utf-8', xml_declaration=True)
    # --------------------------------------------------------- 
            root = gfg.Element("mensaje")
    # ---------------------------------------------------------
            id_desglose = gfg.Element("id")
            root.append (id_desglose)
            # id_desglose.text= str(nuevo_desglose.id)
            id_desglose.text= "desglose"

            cabecera = gfg.Element("cabecera")
            root.append(cabecera)

            guias = gfg.Element("guias")
            root.append(guias)
    # ---------------------------------------------------------
            mensajeNumero = gfg.SubElement(cabecera, "mensajeNumero")
            mensajeNumero.text = "HAV_"+str(ahora.year)+str(ahora.month).zfill(2)+str(ahora.day).zfill(2)+"_"+str(ahora.hour).zfill(2)+str(ahora.minute).zfill(2)+str(ahora.second).zfill(2)+'-'+"1D"
            
            transitarioNit = gfg.SubElement(cabecera, "transitarioNit")
            transitarioNit.text = "30000343383"

            guiaMaster = gfg.SubElement(cabecera, "guiaMaster")
            guiaMaster.text = guia_aerea

            aduana = gfg.SubElement(cabecera, "aduana")
            aduana.text = "0100"
    # ----------------------------------------------------------
            for inv in inventarios:
                guia = gfg.SubElement(guias, "guia")
                manifiesto = gfg.SubElement(guia, "manifiesto")
                manifiesto.text = inv.Manifiesto + '/' + datetime.now().strftime('%Y')

                guiaHija = gfg.SubElement(guia, "guiaHija")
                guiaHija.text = guia_aerea + ' ' +inv.HBL

                naturaleza = gfg.SubElement(guia, "naturaleza")
                naturaleza.text = "GEN"

                tipoGuia = gfg.SubElement(guia, "tipoGuia")
                tipoGuia.text = "I"

                origen = gfg.SubElement(guia, "origen")
                origen.text = inv.Aeropuerto_Origen

                destino = gfg.SubElement(guia, "destino")
                destino.text = "HAV"

                mercancia = gfg.SubElement(guia, "mercancia")
                mercancia.text = inv.Contenido

                proveedor = gfg.SubElement(guia, "proveedor")
                proveedor.text = inv.Remitente.Nombre_Remitente

                paisProveedor = gfg.SubElement(guia, "paisProveedor")
                paisProveedor.text = inv.Pais_Origen.sigla

                consignatario = gfg.SubElement(guia, "consignatario")
                consignatario.text = inv.Destinatario.Nombre

                CI = gfg.SubElement(guia, "CI")
                CI.text = inv.Destinatario.CI

                direccion = gfg.SubElement(guia, "direccion")
                direccion.text = inv.Destinatario.Direccion

                bultos = gfg.SubElement(guia, "bultos")
                bultos.text = str(inv.Cantidad_Bultos)

                peso = gfg.SubElement(guia, "peso")
                peso.text = str(inv.Peso)

            tree = gfg.ElementTree(root)
            
            with open (save_path_file, "wb") as files :
                tree.write(files)

    ctx = {'desglose_xml': save_path_file,'titulo':titulo,'guia_aerea':guia_aerea}
    return render(request, 'desglose/desglose.html', ctx)


@login_required(login_url='login')
def generar_boleta(request,id):

    # listado_paquetes = Paquete.objects.filter(manifiesto=id)
    manifiesto = Manifiesto.objects.get(id=id)
    valor = ''
    if manifiesto.AWB:
        valor = manifiesto.AWB
    if manifiesto.No_Contenedor:
        valor = manifiesto.No_Contenedor
    listado_paquetes = Inventario.objects.filter(Q(No_Contenedor=valor)|Q(AWB=valor))
    if listado_paquetes:

        for paquete in listado_paquetes:
            if not paquete.codigo_barra:
                code39 = barcode.get_barcode_class('code39')
                code = code39(str(paquete.HBL), writer=ImageWriter(),add_checksum=False)
                fullname = code.save(MEDIA_ROOT + '/QR/paquete_' + str(paquete.HBL))
                paquete.codigo_barra = '/QR/paquete_' + str(paquete.HBL)
                paquete.save()
        #Generando reporte PDF
        template_src = 'etiquetas_generadas/boleta.html'
        template = get_template(template_src)
        context = {'listado_paquetes': listado_paquetes,'request': request}
        html  = template.render(context)
        result = BytesIO()
        pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
        if not pdf.err:
            return HttpResponse(result.getvalue(), content_type='application/pdf')
        return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))

    else:
        messages.error(request, 'No se pudo generar las etiquetas. Por favor contacte con el desarrollador.')
        return redirect(reverse('listar_manifiestos'))


@login_required(login_url='login')
def generar_etiquetas(request,id):
    manifiesto = Manifiesto.objects.get(id=id)
    valor = ''
    # destinatario = {}
    qr=''
    destinatario = {}
    code128 = barcode.get_barcode_class('code128')
    listado_paquetes = Inventario.objects.filter(Manifiesto=manifiesto.Manifiesto)
    for paq in listado_paquetes:
        # peso_total += paq.peso
        # destinatario['peso_total'] = peso_total
        if not paq.codigo_barra:
            code128 = barcode.get_barcode_class('code128')
            code = code128(str(paq.HBL), writer=ImageWriter())
            fullname = code.save(MEDIA_ROOT + '/QR/paquete_' + str(paq.HBL))
            paq.codigo_barra = '/QR/paquete_' + str(paq.HBL)
            paq.save()
        
        if paq.AWB:
            qr= paq.AWB + ' ' + paq.Destinatario.Nombre + ' ' + paq.Destinatario.CI
            paq.qr = qr
            paq.save()
        if paq.No_Contenedor:
            qr= paq.No_Contenedor + ' ' + paq.Destinatario.Nombre + ' ' + paq.Destinatario.CI
            paq.qr = qr
            paq.save()
    #Generando reporte PDF
    template_src = 'etiquetas_generadas/etiquetas.html'
    template = get_template(template_src)
    context = {'listado_paquetes': listado_paquetes,'request': request}
    html  = template.render(context)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
    if not pdf.err:
        return HttpResponse(result.getvalue(), content_type='application/pdf')
    return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))
 



# ---------------------------Inicio Administrar Inventario-------------------------------------
@login_required(login_url='login')
def administrar_inventario(request):
    #Definiendo menu activo
    active_menu = 'administrar_inventario'
    form = Operacion_Importar_Manifiesto_Form()
    titulo = 'Administrar Inventario'

    if request.method == 'POST':
        if not request.POST.get('filtro_manifiesto'):
            messages.error(request, 'Debe introducir el No. de manifiesto')
            ctx = {'active_menu': active_menu, 'form': form}
            return render(request, 'others/administrar_inventario.html', ctx)
        if not request.POST.get('filtro_contenedor') and not request.POST.get('filtro_guia') and not request.POST.get('filtro_manifiesto'):
            messages.error(request, 'Debe introducir el No. de Contenedor o la Guía Aérea y el No. de manifiesto')
            ctx = {'active_menu': active_menu, 'form': form}
            return render(request, 'others/administrar_inventario.html', ctx)
        else:
            if request.POST.get('filtro_contenedor'):
                # BMOU 605035-6
                inventarios = Inventario.objects.filter(No_Contenedor = request.POST.get('filtro_contenedor'),Manifiesto=request.POST.get('filtro_manifiesto'))
                if request.POST.get('isPrepago') == 'on':
                    for inventario in inventarios:
                        inventario.isPrepago = True
                        inventario.save()
                    manifiesto = Manifiesto.objects.filter(Manifiesto=request.POST.get('filtro_manifiesto'))
                    manifiesto.isPrepago = True
                    manifiesto.save()

                if request.POST.get('AWB'):
                    for inventario in inventarios:
                        inventario.AWB = request.POST.get('AWB')
                        inventario.save()

                        # Registro de trazas
                        save_addition(request.user, 'inventario', inventario.id, str(model_to_dict(inventario)))

                if request.POST.get('No_Contenedor'):
                    for inventario in inventarios:
                        inventario.No_Contenedor = request.POST.get('No_Contenedor')
                        inventario.save()

                        # Registro de trazas
                        save_addition(request.user, 'inventario', inventario.id, str(model_to_dict(inventario)))

                if request.POST.get('Manifiesto'):
                    for inventario in inventarios:
                        inventario.Manifiesto = request.POST.get('Manifiesto')
                        inventario.save()
                        
                        # Registro de trazas
                        save_addition(request.user, 'inventario', inventario.id, str(model_to_dict(inventario)))

                if request.POST.get('Fecha_Entrada_Puerto'):
                    for inventario in inventarios:
                        inventario.Fecha_Entrada_Puerto = request.POST.get('Fecha_Entrada_Puerto')
                        inventario.save()
                        
                        # Registro de trazas
                        save_addition(request.user, 'inventario', inventario.id, str(model_to_dict(inventario)))

                if request.POST.get('Fecha_Entrada'):
                    for inventario in inventarios:
                        inventario.Fecha_Entrada = request.POST.get('Fecha_Entrada')
                        inventario.save()
                        
                        # Registro de trazas
                        save_addition(request.user, 'inventario', inventario.id, str(model_to_dict(inventario)))

                if request.POST.get('Fecha_Entrada_CADC'):
                    for inventario in inventarios:
                        inventario.Fecha_Entrada_CADC = request.POST.get('Fecha_Entrada_CADC')
                        inventario.save()

                        # Registro de trazas
                        save_addition(request.user, 'inventario', inventario.id, str(model_to_dict(inventario)))

                if request.POST.get('Agencia'):
                    for inventario in inventarios:
                        inventario.Agencia = request.POST.get('Agencia')
                        inventario.save()

                        # Registro de trazas
                        save_addition(request.user, 'inventario', inventario.id, str(model_to_dict(inventario)))

                if request.POST.get('Pies_Contenedor'):
                    for inventario in inventarios:
                        inventario.Pies_Contenedor = request.POST.get('Pies_Contenedor')
                        inventario.save()

                        # Registro de trazas
                        save_addition(request.user, 'inventario', inventario.id, str(model_to_dict(inventario)))

            if request.POST.get('filtro_guia'):
                inventarios = Inventario.objects.filter(AWB = request.POST.get('filtro_guia'),Manifiesto=request.POST.get('filtro_manifiesto'))

                if request.POST.get('AWB'):
                    for inventario in inventarios:
                        inventario.Manifiesto = request.POST.get('Manifiesto')
                        inventario.save()

                        # Registro de trazas
                        save_addition(request.user, 'inventario', inventario.id, str(model_to_dict(inventario)))

                if request.POST.get('No_Contenedor'):
                    for inventario in inventarios:
                        inventario.Manifiesto = request.POST.get('Manifiesto')
                        inventario.save()

                        # Registro de trazas
                        save_addition(request.user, 'inventario', inventario.id, str(model_to_dict(inventario)))

                if request.POST.get('Manifiesto'):
                    for inventario in inventarios:
                        inventario.Manifiesto = request.POST.get('Manifiesto')
                        inventario.save()

                        # Registro de trazas
                        save_addition(request.user, 'inventario', inventario.id, str(model_to_dict(inventario)))

                if request.POST.get('Manifiesto'):
                    for inventario in inventarios:
                        inventario.Manifiesto = request.POST.get('Manifiesto')
                        inventario.save()

                        # Registro de trazas
                        save_addition(request.user, 'inventario', inventario.id, str(model_to_dict(inventario)))

                if request.POST.get('Fecha_Entrada_Puerto'):
                    for inventario in inventarios:
                        inventario.Fecha_Entrada_Puerto = request.POST.get('Fecha_Entrada_Puerto')
                        inventario.save()

                        # Registro de trazas
                        save_addition(request.user, 'inventario', inventario.id, str(model_to_dict(inventario)))

                if request.POST.get('Fecha_Entrada'):
                    for inventario in inventarios:
                        inventario.Fecha_Entrada = request.POST.get('Fecha_Entrada')
                        inventario.save()

                        # Registro de trazas
                        save_addition(request.user, 'inventario', inventario.id, str(model_to_dict(inventario)))

                if request.POST.get('Fecha_Entrada_CADC'):
                    for inventario in inventarios:
                        inventario.Fecha_Entrada_CADC = request.POST.get('Fecha_Entrada_CADC')
                        inventario.save()

                        # Registro de trazas
                        save_addition(request.user, 'inventario', inventario.id, str(model_to_dict(inventario)))

                if request.POST.get('Agencia'):
                    for inventario in inventarios:
                        inventario.Agencia = request.POST.get('Agencia')
                        inventario.save()

                        # Registro de trazas
                        save_addition(request.user, 'inventario', inventario.id, str(model_to_dict(inventario)))

                if request.POST.get('Pies_Contenedor'):
                    for inventario in inventarios:
                        inventario.Pies_Contenedor = request.POST.get('Pies_Contenedor')
                        inventario.save()

                        # Registro de trazas
                        save_addition(request.user, 'inventario', inventario.id, str(model_to_dict(inventario)))


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

            #Aplicacion de filtros
            inventario_filter = InventarioFilter(request.GET, queryset=inventarios)
            inventarios = inventario_filter.qs
            total_bultos = inventarios.aggregate(Sum('Cantidad_Bultos'))
            total_kg = inventarios.aggregate(Sum('Peso'))
            total_hbl = inventarios.count()
            cantidad_paginada = 400
            if request.GET.get('export_excel'):
                cantidad_paginada = 100000000000

            #Paginator
            paginator = Paginator(inventarios, cantidad_paginada) # Show 100 contacts per page.
            page_number = request.GET.get('page')
            page_obj = paginator.get_page(page_number)

            ctx = {'total_kg':total_kg,'total_hbl':total_hbl,'total_bultos':total_bultos,'page_obj': page_obj, 'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu, 'form_trasladar_almacen': form_trasladar_almacen, 'inventario_filter': inventario_filter, 'form_nacionalizar_carga': form_nacionalizar_carga}

            return render(request, 'inventario/inventario_list.html', ctx)
    ctx = {'active_menu': active_menu, 'form': form,'titulo':titulo}
    return render(request, 'others/administrar_inventario.html', ctx)

@login_required(login_url='login')
def administrar_manifiesto(request):
    #Definiendo menu activo
    active_menu = 'manifiesto_eliminar'
    form = Operacion_Importar_Manifiesto_Form()
    titulo = 'Administrar Manifiesto'

    if request.method == 'POST':
        if not request.POST.get('filtro_manifiesto'):
            messages.error(request, 'Debe introducir el No. de manifiesto')
            ctx = {'active_menu': active_menu, 'form': form}
            return render(request, 'others/administrar_inventario.html', ctx)

        if not request.POST.get('filtro_contenedor') and not request.POST.get('filtro_guia') and not request.POST.get('filtro_manifiesto'):
            messages.error(request, 'Debe introducir el No. de Contenedor o la Guía Aérea y el No. de manifiesto')
            ctx = {'active_menu': active_menu, 'form': form}
            return render(request, 'others/administrar_inventario.html', ctx)

        else:
            if request.POST.get('filtro_contenedor'):
                inventarios = Inventario.objects.filter(No_Contenedor=request.POST.get('filtro_contenedor'))
                inventarios__id = Inventario.objects.filter(No_Contenedor=request.POST.get('filtro_contenedor')).values_list('id')

                facturas_inventario = Factura_Inventario.objects.filter(Inventario__id__in=inventarios__id).delete()

                facturas_id = Factura_Inventario.objects.filter(Inventario__id__in=inventarios__id).values_list('Factura__id')
                facturas = Factura.objects.filter(id__in=facturas_id)
                
                #Facturas a eliminar
                for factura in facturas:
                    factura.delete()
                    # Registro de trazas
                    save_deletion(request.user, 'factura', factura.id, str(model_to_dict(factura)))   

                #Manifiesto a eliminar
                manifiesto = Manifiesto.objects.get(No_Contenedor = str(request.POST.get('filtro_contenedor')))
                manifiesto.delete()
                # Registro de trazas
                save_deletion(request.user, 'manifiesto', manifiesto.id, str(model_to_dict(manifiesto)))   

                traking = Traking.objects.filter(Inventario__id__in=inventarios__id).delete()

                inventarios_reincorporados = Inventario_Reincorporado.objects.filter(Inventario__id__in=inventarios__id).delete()
                #Inventarios a eliminar  
                for inventario in inventarios:
                    inventario.delete()
                    # Registro de trazas
                    save_deletion(request.user, 'inventario', inventario.id, str(model_to_dict(inventario)))  

                messages.success(request, 'Manifiesto eliminado satisfactoriamente.')

            if request.POST.get('filtro_guia'):
                inventarios = Inventario.objects.filter(AWB=request.POST.get('filtro_guia'))
                inventarios__id = Inventario.objects.filter(AWB=request.POST.get('filtro_guia')).values_list('id')

                facturas_inventario = Factura_Inventario.objects.filter(Inventario__id__in=inventarios__id).delete()

                facturas_id = Factura_Inventario.objects.filter(Inventario__id__in=inventarios__id).values_list('Factura__id')
                facturas = Factura.objects.filter(id__in=facturas_id)
                
                #Facturas a eliminar
                for factura in facturas:
                    factura.delete()
                    # Registro de trazas
                    save_deletion(request.user, 'factura', factura.id, str(model_to_dict(factura)))   

                #Manifiesto a eliminar
                manifiesto = Manifiesto.objects.get(AWB = str(request.POST.get('filtro_guia')))
                manifiesto.delete()
                # Registro de trazas
                save_deletion(request.user, 'manifiesto', manifiesto.id, str(model_to_dict(manifiesto)))   

                traking = Traking.objects.filter(Inventario__id__in=inventarios__id).delete()

                inventarios_reincorporados = Inventario_Reincorporado.objects.filter(Inventario__id__in=inventarios__id).delete()
                #Inventarios a eliminar  
                for inventario in inventarios:
                    inventario.delete()
                    # Registro de trazas
                    save_deletion(request.user, 'inventario', inventario.id, str(model_to_dict(inventario)))   

                messages.success(request, 'Manifiesto eliminado satisfactoriamente.')

    ctx = {'active_menu': active_menu, 'form': form,'titulo':titulo}
    return render(request, 'others/administrar_inventario.html', ctx)
# ---------------------------Fin Administrar Inventario----------------------------------------


def resumen_manifiesto(request,id):
    manifiesto = Manifiesto.objects.get(id=id)
    cant_hbl_inventario=0
    cant_hbl_traslado=0
    cant_hbl_entregado=0
    if manifiesto.AWB:
        cant_hbl_inventario=Inventario.objects.filter(Estado='Inventario',AWB=manifiesto.AWB).count()
        cant_hbl_traslado=Inventario.objects.filter(Estado='Traslado',AWB=manifiesto.AWB).count()
        cant_hbl_entregado=Inventario.objects.filter(Estado='Entregado',AWB=manifiesto.AWB).count()
    if manifiesto.No_Contenedor:
        cant_hbl_inventario=Inventario.objects.filter(Estado='Inventario',No_Contenedor=manifiesto.No_Contenedor).count()
        cant_hbl_traslado=Inventario.objects.filter(Estado='Traslado',No_Contenedor=manifiesto.No_Contenedor).count()
        cant_hbl_entregado=Inventario.objects.filter(Estado='Entregado',No_Contenedor=manifiesto.No_Contenedor).count()
    valores_totales={}
    valores_totales['derecho_aduanal_total'] = 0
    valores_totales['servicio_aduanal_total'] = 0
    valores_totales['cantidad_HBL_total'] = 0
    valores_totales['total_total'] = 0
    data=[]
    #Diccionario
    dicto = {}
    
    #Valores de cada fila
    dicto['derecho_aduanal'] = 0
    dicto['servicio_aduanal'] = 0
    dicto['cantidad_HBL'] = 0
    dicto['total'] = 0

    #Cantidad de facturas a procesar por fila
    lista_facturas_destinatarios = Factura.objects.all()

    for current_factura in lista_facturas_destinatarios:
        inventario = current_factura.Inventario.all().first()
        pertenece = False
        if inventario.No_Contenedor == manifiesto.No_Contenedor:
            pertenece=True
        if inventario.AWB == manifiesto.AWB:
            pertenece=True
        if pertenece:
            if current_factura.Importe_Total_Factura > 0:
                #Inicializando valores
                derecho_aduanal = 0
                servicio_aduanal = 0
                cantidad_hbl_menor = 0
                cantidad_hbl_mayor = 0
                
                if current_factura.Importe_Derecho_Aduanal_Total:    
                    derecho_aduanal = current_factura.Importe_Derecho_Aduanal_Total
                if current_factura.Importe_Servicio_Aduanal_Total:    
                    servicio_aduanal = current_factura.Importe_Servicio_Aduanal_Total
                if current_factura.Inventario:
                    cantidad_hbl_menor = current_factura.Inventario.all().filter(Peso__lte = 1.50).count()
                    cantidad_hbl_mayor = current_factura.Inventario.all().filter(Peso__gt = 1.50).count()
                if current_factura.Inventario.all().count():
                    dicto['cantidad_HBL'] += current_factura.Inventario.all().count()
     
                dicto['derecho_aduanal'] += derecho_aduanal
                dicto['servicio_aduanal'] += servicio_aduanal
                dicto['total'] = dicto['derecho_aduanal'] + dicto['servicio_aduanal']
        #Sumando valores totales
        valores_totales['derecho_aduanal_total'] += dicto['derecho_aduanal']
        valores_totales['servicio_aduanal_total'] += dicto['servicio_aduanal']
        valores_totales['total_total'] += dicto['total']
        valores_totales['cantidad_HBL_total'] += dicto['cantidad_HBL']
        
        data.append(dicto)
        
    #Generando reporte PDF
    template_src = 'pdf/resumen_manifiesto.html'
    template = get_template(template_src)
    context = {'manifiesto': manifiesto,'cant_hbl_inventario':cant_hbl_inventario,'cant_hbl_traslado':cant_hbl_traslado,'cant_hbl_entregado':cant_hbl_entregado,'valores_totales':valores_totales,'request': request}
    html  = template.render(context)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
    if not pdf.err:
        return HttpResponse(result.getvalue(), content_type='application/pdf')
    return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))


def reporte_historico_agencia(request):
    #Informacion para el template
    header_text     = 'Histórico de agencia'
    breadcrumb_text = 'Histórico de agencia'
    #Definiendo menu activo
    active_menu = 'reporte_historico_agencia'

    agencia_form=Agencia_Form()
    
    manifiestos=Manifiesto.objects.all()
    fecha_desde=''
    fecha_hasta=''
    agencia=''
    if request.method == 'POST':

        manifiestos_agencias = []
        manifiestos = Manifiesto.objects.all()
        #meses = [1,2,3,4,5,6,7,8,9,10,11,12]
        
        # Obteniendo rango de fecha
        if request.POST.get('Fecha_Desde') and request.POST.get('Fecha_Hasta'):
            fecha_desde = datetime.strptime(str(request.POST.get('Fecha_Desde')), '%Y-%m-%d')
            fecha_hasta = datetime.strptime(str(request.POST.get('Fecha_Hasta')), '%Y-%m-%d')
            manifiestos = manifiestos.filter(Fecha_Importacion__gte=fecha_desde,Fecha_Importacion__lte=fecha_hasta)
        
        # Obteniendo agencia específica
        if request.POST.get('Agencia'):
            agencia = Agencia.objects.get(id = request.POST.get('Agencia'))
            for numero_mes in [1,2,3,4,5,6,7,8,9,10,11,12]:
                mes = {}
                mes['mes'] = calendar.month_name[numero_mes]
                manifiestos_mes = []
                manifiestos_mes.append(mes)                 
                manifiestos_agencia = manifiestos.filter(Agencia = agencia)               
                data = {}
                data['agencia'] = agencia
                data['manifiestos_mes'] = manifiestos_agencia.filter(Fecha_Importacion__month=str(numero_mes).zfill(2))           
                manifiestos_mes.append(data)     
                manifiestos_agencias.append(manifiestos_mes)

        # Obteniendo todas las agencias
        if not request.POST.get('Agencia'): 
            for numero_mes in [1,2,3,4,5,6,7,8,9,10,11,12]:
                mes = {}
                mes['mes'] = calendar.month_name[numero_mes]
                manifiestos_mes = []
                manifiestos_mes.append(mes) 
                for agencia in Agencia.objects.all():
                    manifiestos_agencia = manifiestos.filter(Agencia = agencia)                    
                    data = {}
                    data['agencia'] = agencia
                    data['manifiestos_mes'] = manifiestos_agencia.filter(Fecha_Importacion__month=str(numero_mes).zfill(2))
                    manifiestos_mes.append(data)                     
                manifiestos_agencias.append(manifiestos_mes)
                
        #Generando reporte PDF
        template_src = 'pdf/registro_agencia.html'
        template = get_template(template_src)
        context = {'request': request,'manifiestos_agencias':manifiestos_agencias}
        html  = template.render(context)
        result = BytesIO()
        pdf = pisa.pisaDocument(BytesIO(html.encode("utf-8")), result)
        if not pdf.err:
            return HttpResponse(result.getvalue(), content_type='application/pdf')
        return HttpResponse('Unable to process the request, We had some errors<pre>%s</pre>' % escape(html))

    ctx = {'manifiestos':manifiestos,'agencia_form':agencia_form,'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu}

    return render(request, 'reportes/reporte_historico_agencia.html', ctx,)

def permisos_usuario_list(request):
    header_text = 'Listado de permisos de usuario'
    breadcrumb_text = 'Listado de permisos de usuario'
    active_menu = 'Listado de permisos de usuario'

    usuarios = User.objects.all()

    #Aplicacion de filtros
    usuario_filter=Usuario_Filter(request.GET, queryset=usuarios)
    usuarios = usuario_filter.qs


    #Paginator
    paginator = Paginator(usuarios, 400) # Show 100 contacts per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    ctx = {'usuario_filter':usuario_filter,'page_obj':usuarios,'header_text': header_text, 'breadcrumb_text': breadcrumb_text, 'active_menu': active_menu}

    return render(request, 'reportes/reporte_permisos_usuario.html', ctx,)
