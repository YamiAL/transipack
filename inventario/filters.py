from typing import Hashable
from django.db.models import fields
from django.forms import *
import django_filters
from django_filters import filters
from .models import *

class InventarioFilter(django_filters.FilterSet):
    Manifiesto              = django_filters.CharFilter(label="Manifiesto", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    No_Contenedor           = django_filters.CharFilter(label="Número de contenedor", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    HBL                     = django_filters.CharFilter(label="HBL", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    AWB                     = django_filters.CharFilter(label="Número de guía aérea", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    Almacen                 = django_filters.ModelChoiceFilter(label="Almacén", queryset=Almacen.objects.all(), widget=Select(attrs={'class': 'form-control'}))
    Destinatario_Nombre     = django_filters.CharFilter(label="Nombre y apellidos del destinatario", field_name="Destinatario__Nombre", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    Destinatario_CI         = django_filters.CharFilter(label="Carnet de identidad", field_name="Destinatario__CI", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    Destinatario_Provincia  = django_filters.ModelChoiceFilter(label="Provincia", field_name="Destinatario__Provincia", queryset=Provincia.objects.all(), widget=Select(attrs={'class': 'form-control'}))
    Destinatario_Municipio  = django_filters.ModelChoiceFilter(label="Municipio", field_name="Destinatario__Municipio", queryset=Municipio.objects.all(), widget=Select(attrs={'class': 'form-control'}))
    Ubicacion_Fila          = django_filters.CharFilter(label="Área", widget=TextInput(attrs={'class': 'form-control'}))
    Ubicacion_Columna       = django_filters.CharFilter(label="Columna", widget=TextInput(attrs={'class': 'form-control'}))
    Agencia    = django_filters.ModelChoiceFilter(label="Corresponsal", field_name="Agencia", queryset=Agencia.objects.all(), widget=Select(attrs={'class': 'form-control'}))
        
    class Meta:
        model = Inventario
        fields = ['Manifiesto', 'HBL', 'Destinatario', 'AWB']


class Mercancia_Traslado_Filter(django_filters.FilterSet):
    Transportista           = django_filters.ModelChoiceFilter(label="Transportista", queryset=Transportista.objects.all(), field_name="Transportista", widget=Select(attrs={'class': 'form-control'}))
    HBL                     = django_filters.CharFilter(label="HBL", field_name="Inventario__HBL", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    Nombre_Destinatario     = django_filters.CharFilter(label="Nombre y apellidos del destinatario", field_name="Inventario__Destinatario__Nombre", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    CI_Destinatario         = django_filters.CharFilter(label="Carnet de identidad", field_name="Inventario__Destinatario__CI", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    Provincia_Destinatario  = django_filters.ModelChoiceFilter(label="Provincia", queryset=Provincia.objects.all(), field_name="Inventario__Destinatario__Provincia", widget=Select(attrs={'class': 'form-control'}))
    Municipio_Destinatario  = django_filters.ModelChoiceFilter(label="Municipio", queryset=Municipio.objects.all(), field_name="Inventario__Destinatario__Municipio", widget=Select(attrs={'class': 'form-control'}))

    class Meta:
        model = Entrega
        fields = ['Transportista', 'HBL']


class Inventario_Reporte_Filter(django_filters.FilterSet):
    No_Contenedor    = django_filters.CharFilter(label="Número de contenedor", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    AWB    = django_filters.CharFilter(label="Número de guía aérea", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    HBL              = django_filters.CharFilter(label="HBL", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    Manifiesto       = django_filters.CharFilter(label="Manifiesto", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    Cantidad_Bultos  = django_filters.CharFilter(label="Cantidad de bultos", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    Peso             = django_filters.CharFilter(label="Peso", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    Volumen          = django_filters.CharFilter(label="Volumen", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    Contenido        = django_filters.CharFilter(label="Contenido", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    Precio           = django_filters.CharFilter(label="Precio", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    Estado           = django_filters.ChoiceFilter(label="Estado", choices=Inventario.ESTADO, widget=Select(attrs={'class': 'form-control'}))
    Incidencia       = django_filters.ModelChoiceFilter(label="Tipo de incidencia", queryset=Incidencia.objects.all(), widget=Select(attrs={'class': 'form-control'}))
    Observ_Incidencia  = django_filters.CharFilter(label="Observaciones sobre la incidencia", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    Fecha_Entrada_Puerto_desde = django_filters.DateFilter(label="Fecha de entrada al puerto (desde)", field_name="Fecha_Entrada_Puerto", lookup_expr='gte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Fecha_Entrada_Puerto_hasta = django_filters.DateFilter(label="Fecha de entrada al puerto (hasta)", field_name="Fecha_Entrada_Puerto", lookup_expr='lte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Fecha_Nacionalizacion_desde = django_filters.DateFilter(label="Fecha de nacionalización (desde)", field_name="Fecha_Nacionalizacion", lookup_expr='gte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Fecha_Nacionalizacion_hasta = django_filters.DateFilter(label="Fecha de nacionalización (hasta)", field_name="Fecha_Nacionalizacion", lookup_expr='lte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Fecha_Entrada_desde = django_filters.DateFilter(label="Fecha de desagrupe (desde)", field_name="Fecha_Entrada", lookup_expr='gte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Fecha_Entrada_hasta = django_filters.DateFilter(label="Fecha de desagrupe (hasta)", field_name="Fecha_Entrada", lookup_expr='lte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Fecha_Pre_Cita_desde = django_filters.DateFilter(label="Fecha de pre-cita (desde)", field_name="Fecha_Entrada", lookup_expr='gte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Fecha_Pre_Cita_hasta = django_filters.DateFilter(label="Fecha de pre-cita (hasta)", field_name="Fecha_Entrada", lookup_expr='lte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Fecha_Devolución_desde = django_filters.DateFilter(label="Fecha de devolución (desde)", field_name="Fecha_Entrada", lookup_expr='gte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Fecha_Devolución_hasta = django_filters.DateFilter(label="Fecha de devolución (hasta)", field_name="Fecha_Entrada", lookup_expr='lte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))

    Almacen       = django_filters.ModelChoiceFilter(queryset=Almacen.objects.all(), widget=Select(attrs={'class': 'form-control'}))
    Ubicacion_Fila = django_filters.CharFilter(label="Área", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    Ubicacion_Columna = django_filters.CharFilter(label="Columna", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    Fecha_Traslado_desde = django_filters.DateFilter(label="Fecha de traslado (desde)", field_name="Fecha_Traslado", lookup_expr='gte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Fecha_Traslado_hasta = django_filters.DateFilter(label="Fecha de traslado (hasta)", field_name="Fecha_Traslado", lookup_expr='lte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Fecha_Entrega_desde = django_filters.DateFilter(label="Fecha de entrega (desde)", field_name="Fecha_Entrega", lookup_expr='gte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Fecha_Entrega_hasta = django_filters.DateFilter(label="Fecha de entrega (hasta)", field_name="Fecha_Entrega", lookup_expr='lte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Destinatario_Nombre = django_filters.CharFilter(label="Nombre y apellidos del destinatario", field_name="Destinatario__Nombre", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    Destinatario_CI = django_filters.CharFilter(label="Carnet de identidad", field_name="Destinatario__CI", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    Destinatario_Telefono = django_filters.CharFilter(label="Teléfono del destinatario", field_name="Destinatario__Telefono", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    Destinatario_Provincia  = django_filters.ModelChoiceFilter(label="Provincia", field_name="Destinatario__Provincia", queryset=Provincia.objects.all(), widget=Select(attrs={'class': 'form-control'}))
    Destinatario_Municipio  = django_filters.ModelChoiceFilter(label="Municipio", field_name="Destinatario__Municipio", queryset=Municipio.objects.all(), widget=Select(attrs={'class': 'form-control'}))
    Pasaporte_DNI = django_filters.CharFilter(label="Pasaporte del remitente", field_name="Remitente__Pasaporte_DNI", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    Agencia       = django_filters.ModelChoiceFilter(label="Corresponsal",queryset=Agencia.objects.all(), widget=Select(attrs={'class': 'form-control'}))
    
    class Meta:
        model = Inventario
        fields = ['No_Contenedor', 'HBL']


class Traslados_Programados_Filter(django_filters.FilterSet):
    Fecha_Entrega_inicio = django_filters.DateFilter(label="Fecha (desde)", field_name="Fecha_Entrega", lookup_expr='gte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Fecha_Entrega_fin = django_filters.DateFilter(label="Fecha (hasta)", field_name="Fecha_Entrega", lookup_expr='lte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Hora_Salida = django_filters.TimeFilter(label="Hora de salida", lookup_expr='gte', widget=DateInput(attrs={'type': 'time', 'class': 'form-control'}))
    Hora_Llegada = django_filters.TimeFilter(label="Hora de regreso", lookup_expr='lte', widget=DateInput(attrs={'type': 'time', 'class': 'form-control'}))
    Transportista = django_filters.ModelChoiceFilter(queryset=Transportista.objects.all(), widget=Select(attrs={'class': 'form-control'}))
    Estado        = django_filters.ChoiceFilter(choices=Entrega.ESTADO, widget=Select(attrs={'class': 'form-control'}))
    Destinatario_CI = django_filters.CharFilter(label="Carnet de identidad", field_name="Factura_Operador__Facturas_Destinatarios__Inventario__Destinatario__CI", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    HBL = django_filters.CharFilter(label="HBL", field_name="Factura_Operador__Facturas_Destinatarios__Inventario__HBL", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    
    class Meta:
        model = Entrega
        fields = ['Fecha_Entrega', 'Hora_Salida', 'Hora_Llegada', 'Transportista', 'Estado', 'Destinatario_CI', 'HBL']


class Citas_Filter(django_filters.FilterSet):
    Fecha_inicio     = django_filters.DateFilter(label="Fecha (desde)", field_name="Fecha", lookup_expr='gte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Fecha_hasta      = django_filters.DateFilter(label="Fecha (hasta)", field_name="Fecha", lookup_expr='lte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Hora_desde       = django_filters.TimeFilter(label="Hora (desde)", field_name="Hora", lookup_expr='gte', widget=DateInput(attrs={'type': 'time', 'class': 'form-control'}))
    Hora_hasta       = django_filters.TimeFilter(label="Hora (hasta)", field_name="Hora", lookup_expr='lte', widget=DateInput(attrs={'type': 'time', 'class': 'form-control'}))
    Nombre_Filtro    = django_filters.CharFilter(label="Nombre y apellidos del destinatario", field_name="Inventario__Destinatario__Nombre", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    Direccion_Filtro = django_filters.CharFilter(label="Dirección", field_name="Inventario__Destinatario__Direccion", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    
    class Meta:
        model = Cita
        fields = ['Fecha', 'Hora',]

class Entrega_Add_Filter(django_filters.FilterSet):
    #CI_Destinatario         = django_filters.CharFilter(label="Carnet de identidad", field_name="Inventario__Destinatario__CI", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    #Provincia_Destinatario  = django_filters.ModelChoiceFilter(label="Provincia", queryset=Provincia.objects.all(), field_name="Inventario__Destinatario__Provincia", widget=Select(attrs={'class': 'form-control'}))
    Municipio_Destinatario  = django_filters.ModelChoiceFilter(label="Municipio", queryset=Municipio.objects.all(), field_name="Destinatario__Municipio", widget=Select(attrs={'class': 'form-control'}))
    Inventario_Almacen      = django_filters.ModelChoiceFilter(label="Almacén", queryset=Almacen.objects.all(), field_name="Almacen", widget=Select(attrs={'class': 'form-control'}))
    Categoria_Operacion     = django_filters.ChoiceFilter(label="Tipo", choices=Inventario.TIPO_OPERACION, field_name="Categoria_Operacion", lookup_expr='icontains', widget=Select(attrs={'class': 'form-control'}))


    class Meta:
        model = Inventario
        fields = ['Municipio_Destinatario', 'Inventario_Almacen', 'Categoria_Operacion']

class Manifiesto_Filter(django_filters.FilterSet):
    No_Contenedor       = django_filters.CharFilter(label="Contenedor", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    AWB                 = django_filters.CharFilter(label="Guía Aérea", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    Manifiesto          = django_filters.CharFilter(label="No de manifiesto", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    #Fecha_Importacion   = django_filters.DateFilter(label="Fecha de importación", widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Fecha_Importacion_desde = django_filters.DateFilter(label="Fecha de importación (desde)", field_name="Fecha_Importacion", lookup_expr='gte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Fecha_Importacion_hasta = django_filters.DateFilter(label="Fecha de importación (hasta)", field_name="Fecha_Importacion", lookup_expr='lte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Agencia  = django_filters.ModelChoiceFilter(label="Corresponsal", field_name="Agencia", queryset=Agencia.objects.all(), widget=Select(attrs={'class': 'form-control'}))
    
    class Meta:
        model = Manifiesto
        fields = ['No_Contenedor', 'Manifiesto','Fecha_Importacion','AWB']

class FacturaFilter(django_filters.FilterSet):
    id              = django_filters.NumberFilter(label="No de comprobante", widget=TextInput(attrs={'class': 'form-control'}))
    Fecha_desde     = django_filters.DateFilter(label="Fecha de creación (desde)", field_name="Fecha", lookup_expr='gte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Fecha_hasta     = django_filters.DateFilter(label="Fecha de creación (hasta)", field_name="Fecha", lookup_expr='lte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Estado          = django_filters.ChoiceFilter(label="Estado", choices=Factura.ESTADO, widget=Select(attrs={'class': 'form-control'}))
    HBL             = django_filters.CharFilter(label="HBL", lookup_expr='icontains', field_name="Inventario__HBL", widget=TextInput(attrs={'class': 'form-control'}))
    Nombre_Destinatario = django_filters.CharFilter(label="Nombre del destinatario", lookup_expr='icontains', field_name="Inventario__Destinatario__Nombre", distinct=True, widget=TextInput(attrs={'class': 'form-control'}))
    CI_Destinatario     = django_filters.CharFilter(label="CI del destinatario", lookup_expr='icontains', field_name="Inventario__Destinatario__CI",  distinct=True, widget=TextInput(attrs={'class': 'form-control'}))
    Fecha_cobro_desde     = django_filters.DateFilter(label="Fecha de cobro (desde)", field_name="Fecha_cobro", lookup_expr='gte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Fecha_cobro_hasta     = django_filters.DateFilter(label="Fecha de cobro (hasta)", field_name="Fecha_cobro", lookup_expr='lte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Destinatario_Provincia  = django_filters.ModelChoiceFilter(label="Provincia", field_name="Provincia", queryset=Provincia.objects.all(), widget=Select(attrs={'class': 'form-control'}))
    Agencia  = django_filters.ModelChoiceFilter(label="Corresponsal", field_name="Agencia", queryset=Agencia.objects.all(), widget=Select(attrs={'class': 'form-control'}))

    class Meta:
        model = Factura
        fields = ['id', 'Fecha', 'Estado']


class Factura_Operador_Filter(django_filters.FilterSet):
    No_Comprobante              = django_filters.CharFilter(label="No. de comprobante", field_name="id", lookup_expr='exact', widget=TextInput(attrs={'class': 'form-control'}))
    Fecha_inicio_creacion       = django_filters.DateFilter(label="Fecha facturación (desde)", field_name="Fecha_Creacion", lookup_expr='gte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Fecha_hasta_creacion        = django_filters.DateFilter(label="Fecha facturación (hasta)", field_name="Fecha_Creacion", lookup_expr='lte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Fecha_inicio_cobro          = django_filters.DateFilter(label="Fecha de cobro (desde)", field_name="Fecha_Cobro", lookup_expr='gte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Fecha_hasta_cobro           = django_filters.DateFilter(label="Fecha de cobro (hasta)", field_name="Fecha_Cobro", lookup_expr='lte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Operador                    = django_filters.ModelChoiceFilter(label="Operador", queryset=Operador.objects.all(), field_name="Operador", widget=Select(attrs={'class': 'form-control'}))

    class Meta:
        model = Factura_Operador
        fields = ['id', 'Fecha_Creacion', 'Fecha_Cobro']

class HBL_No_Manifestados_Filter(django_filters.FilterSet):
    HBL                          = django_filters.CharFilter(label="HBL", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    Fecha_inicio_Rectificacion   = django_filters.DateFilter(label="Fecha verificación (desde)", field_name="Fecha_Rectificacion", lookup_expr='gte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    Fecha_hasta_Rectificacion    = django_filters.DateFilter(label="Fecha verificación (hasta)", field_name="Fecha_Rectificacion", lookup_expr='lte', widget=DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    class Meta:
        model = HBL_No_Manifestados
        fields = ['id', 'HBL', 'Fecha_Rectificacion']

class Tracking_Filter(django_filters.FilterSet):
    HBL = django_filters.CharFilter(label="HBL", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    Nombre = django_filters.CharFilter(label="Nombre del destinatario", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))
    CI = django_filters.CharFilter(label="Carnet de identidad", lookup_expr='icontains', widget=TextInput(attrs={'class': 'form-control'}))

class Agencia_Filter(django_filters.FilterSet):
    Agencia = django_filters.ModelChoiceFilter(label="Seleccione agencia",queryset=Agencia.objects.all(), widget=Select(attrs={'class': 'form-control'}))
    
    class Meta:
        model = Entrega
        fields = ['Agencia']

class Usuario_Filter(django_filters.FilterSet):
    username = django_filters.ModelChoiceFilter(label="Seleccione el usuario",queryset=User.objects.all(), widget=Select(attrs={'class': 'form-control'}))
    
    class Meta:
        model = User
        fields = ['username','first_name']
