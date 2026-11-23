#from django import forms
from cProfile import label
from transcargo.settings import MEDIA_ROOT
from django.conf import settings
from django.db import models
from django.forms import *
from django.forms.models import ModelForm
from .models import *
from datetime import date, datetime
from django.db.models import Q
from django import forms
from .fields import UserModelChoiceField
import re
from django.forms import ModelChoiceField

class Inventario_Form(ModelForm):
    class Meta:
        model = Inventario
        fields = '__all__'
        exclude= ['Estado',]

        widgets = {
                'Cantidad_Bultos': TextInput(attrs={'class': 'form-control'}),
                'Volumen': TextInput(attrs={'class': 'form-control'}),
                'Precio': TextInput(attrs={'class': 'form-control'}),
                'Peso': TextInput(attrs={'class': 'form-control'}),
                'Ubicacion_Fila': TextInput(attrs={'class': 'form-control'}),
                'Ubicacion_Columna': TextInput(attrs={'class': 'form-control'}),
                'Fecha_Entrada_Puerto':TextInput(attrs={'class': 'form-control', 'type': 'date'}),
                'Fecha_Entrada':TextInput(attrs={'class': 'form-control', 'type': 'date'}),
            }

    def clean_Precio(self):
        if self.cleaned_data.get('Precio') and self.cleaned_data.get('Precio') <= 0:
            raise ValidationError("El precio debe ser mayor que 0")
        return self.cleaned_data.get('Precio')

    def clean_Ubicacion_Columna(self):
        if self.cleaned_data.get('Ubicacion_Columna') and self.cleaned_data.get('Ubicacion_Columna') <= 0:
            raise ValidationError("La columna debe ser mayor que 0")
        return self.cleaned_data.get('Ubicacion_Columna') 

class Destinatario_Form(ModelForm):
    class Meta:
        model = Destinatario
        fields = '__all__'

        widgets = {
                'CI': TextInput(attrs={'class': 'form-control', 'maxlength': '11', 'minlength': '11'}),
                'Telefono': TextInput(attrs={'class': 'form-control'}),
            }

    def clean_Pasaporte_DNI(self):
        if self.cleaned_data.get('Pasaporte_DNI'):
            try:
                result = re.match(r'^[0-9A-Za-z-]+$', self.cleaned_data.get('Pasaporte_DNI'))
                if result.group():
                    pass
            except:
                raise ValidationError("Pasaporte incorrecto")

            if not len(self.cleaned_data.get('Pasaporte_DNI')) <= 10:
                raise ValidationError("Pasaporte incorrecto")

        return self.cleaned_data.get('Pasaporte_DNI') 

    def clean_Nombre(self):
        try:
            result = re.match(r'^[a-zA-Z ]+$', self.cleaned_data.get('Nombre'))
            if result.group():
                pass
        except:
            raise ValidationError("Nombre incorrecto")

        return self.cleaned_data.get('Nombre') 

    def clean_CI(self):
        try:
            result = re.match(r'^[0-9]+$', self.cleaned_data.get('CI'))
            if result.group():
                pass
        except:
            raise ValidationError("CI incorrecto")

        if not len(self.cleaned_data.get('CI')) == 11:
            raise ValidationError("CI incorrecto")

        return self.cleaned_data.get('CI') 

    def clean_Telefono(self):
        try:
            result = re.match(r'^[0-9]+$', self.cleaned_data.get('Telefono'))
            if result.group():
                pass
        except:
            raise ValidationError("Teléfono incorrecto")

        if not len(self.cleaned_data.get('Telefono')) == 8:
            raise ValidationError("Teléfono incorrecto")

        return self.cleaned_data.get('Telefono')

    def clean_Direccion(self):
        try:
            result = re.match(r'^[0-9A-Za-z/.,:%áéíóúÁÉÍÓÚÑñ"#()\- ]+$', self.cleaned_data.get('Direccion'))
            if result.group():
                pass
        except:
            raise ValidationError("Dirección incorrecta")

        if not len(self.cleaned_data.get('Direccion')) >= 5:
            raise ValidationError("Dirección incorrecta")

        return self.cleaned_data.get('Direccion') 


class Remitente_Form(ModelForm):
    class Meta:
        model = Remitente
        fields = '__all__'

        widgets = {
                'Pasaporte_DNI': TextInput(attrs={'class': 'form-control'}),
            }
    
    def clean_Nombre_Remitente(self):
        try:
            result = re.match(r'^[a-zA-Z ]+$', self.cleaned_data.get('Nombre_Remitente'))
            if result.group():
                pass
        except:
            raise ValidationError("Nombre incorrecto")

        return self.cleaned_data.get('Nombre_Remitente') 

class Entrega_Form(ModelForm):
    Operador        = forms.ModelChoiceField(label='Operador', queryset=Operador.objects.filter(Activo = True), widget=forms.Select(attrs={'class': 'form-control'}))
    Transportista   = forms.ModelChoiceField(label='Transportista', queryset=Transportista.objects.filter(Activo = True), widget=forms.Select(attrs={'class': 'form-control'}))
    # Chapa           = forms.CharField(label='Chapa', widget=forms.TextInput(attrs={'class': 'form-control'}))
    
    class Meta:
        model = Entrega
        fields = '__all__'

        widgets = {
            'Fecha_Entrega': TextInput(attrs={'class': 'form-control', 'type': 'date'}),
            'Hora_Salida': TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'Hora_Llegada': TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
        }

    def clean_Operador(self):
        if not self.cleaned_data.get('Operador'):
            raise ValidationError("Debe seleccionar un operador")
        return self.cleaned_data.get('Operador') 

class Cita_Form(ModelForm):
    class Meta:
        model = Cita
        fields = '__all__'

        widgets = {
            'Fecha': TextInput(attrs={'class': 'form-control', 'type': 'date'}),
            'Hora': TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'Inventario': CheckboxSelectMultiple(),
        }

class Operacion_Nacionalizar_Inventario_Form(forms.Form):
    Provincia_Destinatario = forms.ModelChoiceField(label='Provincia', queryset=Provincia.objects.all(), widget=forms.Select(attrs={'class': 'form-control'}))
    Municipio_Destinatario = forms.ModelChoiceField(label='Municipio', queryset=Municipio.objects.all(), widget=forms.Select(attrs={'class': 'form-control'}))

    def clean_Provincia_Destinatario(self):
        if not self.cleaned_data.get('Provincia_Destinatario'):
            raise ValidationError("Este campo es obligatorio")
        return self.cleaned_data.get('Provincia_Destinatario') 

    def clean_Municipio_Destinatario(self):
        if not self.cleaned_data.get('Municipio_Destinatario'):
            raise ValidationError("Este campo es obligatorio")
        return self.cleaned_data.get('Municipio_Destinatario') 

class Operacion_Entrar_Inventario_Form(ModelForm):
    class Meta:
        model = Inventario
        fields = 'Almacen', 'Ubicacion_Fila', 'Ubicacion_Columna'

        widgets = {
            'Ubicacion_Fila': TextInput(attrs={'class': 'form-control'}),
            'Ubicacion_Columna': TextInput(attrs={'class': 'form-control'}),
        }

    def clean_Almacen(self):
        if not self.cleaned_data.get('Almacen'):
            raise ValidationError("Debe seleccionar un almacén")
        return self.cleaned_data.get('Almacen') 

    def clean_Ubicacion_Columna(self):
        if self.cleaned_data.get('Ubicacion_Columna') and self.cleaned_data.get('Ubicacion_Columna') <= 0:
            raise ValidationError("La columna debe ser mayor que 0")
        return self.cleaned_data.get('Ubicacion_Columna') 

class Operacion_Entregar_Inventario_Form(ModelForm):
    class Meta:
        model = Inventario
        fields = 'Nombre_Entrega', 'CI_Entrega', 'Pasaporte_DNI_Entrega', 'Direccion_Entrega', 'Provincia_Entrega', 'Municipio_Entrega', 'Telefono_Entrega'

        widgets = {
                'CI_Entrega': TextInput(attrs={'class': 'form-control', 'maxlength': '11', 'minlength': '11'}),
                'Telefono_Entrega': TextInput(attrs={'class': 'form-control'}),
            }
    
    def clean_Nombre_Entrega(self):
        if not self.cleaned_data.get('Nombre_Entrega'):
            raise ValidationError("Este campo es obligatorio")
        return self.cleaned_data.get('Nombre_Entrega') 

    def clean_Pasaporte_DNI_Entrega(self):
        if (not self.cleaned_data.get('CI_Entrega')) and (not self.cleaned_data.get('Pasaporte_DNI_Entrega')):
            raise ValidationError("Debe definir el Carnet de identidad o el No. pasaporte / DNI")
        return self.cleaned_data.get('Pasaporte_DNI_Entrega') 

    def clean_Direccion_Entrega(self):
        if not self.cleaned_data.get('Direccion_Entrega'):
            raise ValidationError("Este campo es obligatorio")
        return self.cleaned_data.get('Direccion_Entrega') 

    def clean_Provincia_Entrega(self):
        if not self.cleaned_data.get('Provincia_Entrega'):
            raise ValidationError("Este campo es obligatorio")
        return self.cleaned_data.get('Provincia_Entrega')

    def clean_Municipio_Entrega(self):
        if not self.cleaned_data.get('Municipio_Entrega'):
            raise ValidationError("Este campo es obligatorio")
        return self.cleaned_data.get('Municipio_Entrega')
    
    def clean_Telefono_Entrega(self):
        if not self.cleaned_data.get('Telefono_Entrega'):
            raise ValidationError("Este campo es obligatorio")
        return self.cleaned_data.get('Telefono_Entrega')

class Operacion_Devolucion_Inventario_Form(ModelForm):
    class Meta:
        model = Inventario
        fields = 'Observ_Devolucion',

class Operacion_No_Localizable_Inventario_Form(ModelForm):
    class Meta:
        model = Inventario
        fields = 'Observ_No_Localizable',
    
TIPO_ENVIO_CHOICE=(
    ("","---------"),
    ("aereo","Aéreo"),
    ("maritimo","Marítimo"),
    )        
class Operacion_Importar_Manifiesto_Form(forms.Form):
    No_Contenedor           = forms.CharField(label='Número de contenedor',required=False, max_length=255, widget=forms.TextInput(attrs={'class': 'form-control'}))
    AWB           = forms.CharField(label='Número de guía aérea',required=False, max_length=255, widget=forms.TextInput(attrs={'class': 'form-control'}))
    Aeropuerto_Origen           = forms.CharField(label='Aeropuerto de origen',required=False, max_length=255, widget=forms.TextInput(attrs={'class': 'form-control'}))
    Manifiesto              = forms.IntegerField(label='Número de manifiesto', widget=forms.TextInput(attrs={'class': 'form-control'}))
    Fecha_Entrada_Puerto    = forms.DateField(label='Fecha de entrada al puerto', widget=forms.TextInput(attrs={'class': 'form-control', 'type': 'date'})) 
    Fecha_Entrada           = forms.DateField(label='Fecha de desagrupe', widget=forms.TextInput(attrs={'class': 'form-control', 'type': 'date'})) 
    Almacen                 = forms.ModelChoiceField(label='Almacén de destino', queryset=Almacen.objects.all(), widget=forms.Select(attrs={'class': 'form-control'}))
    File                    = forms.FileField(label='Cargue el archivo a importar (.xls)', widget=forms.FileInput(attrs={'class': 'form-control', 'type': 'file'}))
    isPrepago               = forms.BooleanField(label='Carga Prepago',required=False)
    # isAereo                 = forms.BooleanField(label='Envío Aéreo',required=False)
    # isMaritimo              = forms.BooleanField(label='Envío Marítimo',required=False)
    tipo_envio              = forms.ChoiceField(label='Origen',choices=TIPO_ENVIO_CHOICE, widget=forms.Select(attrs={'class': 'form-control'}))
    Agencia                 = forms.ModelChoiceField(label="Corresponsal", queryset=Agencia.objects.all(), widget=forms.Select(attrs={'class': 'form-control'}))
    Pais                 = forms.ModelChoiceField(label='País', queryset=Paises.objects.all(), widget=forms.Select(attrs={'class': 'form-control'}))

    def clean_No_Contenedor(self):
        
        if self.cleaned_data.get('No_Contenedor'):
            try:
                result = re.match(r'^([A-Z]{4})([ ])([0-9]{6})([-])(([0-9]){1,2})$', self.cleaned_data.get('No_Contenedor'))
                if result.group():
                    pass 
            except:
                raise ValidationError("Número de contenedor incorrecto") 
        
        return self.cleaned_data.get('No_Contenedor')

    def clean_AWB(self):
        
        if self.cleaned_data.get('AWB'):
            try:
                result = re.match(r'^([0-9]{3})([-])(([0-9]){8})$', self.cleaned_data.get('AWB'))
                if result.group():
                    pass 
            except:
                raise ValidationError("Número de guía aérea incorrecta") 
        
        return self.cleaned_data.get('AWB')

    def clean_Aeropuerto_Origen(self):
        
        if self.cleaned_data.get('Aeropuerto_Origen'):
            try:
                result = re.match(r'^([A-Z]{3})$', self.cleaned_data.get('Aeropuerto_Origen'))
                if result.group():
                    pass 
            except:
                raise ValidationError("Código del aeropuerto de origen incorrecto. Debe introducir sólo tres letras mayúscula") 
        
        return self.cleaned_data.get('Aeropuerto_Origen')

    
    def clean_Manifiesto(self):
        if not self.cleaned_data.get('Manifiesto'):
            raise ValidationError("Este campo es obligatorio")
        # if len(str(self.cleaned_data.get('Manifiesto'))) > 4:
        #     raise ValidationError("Este campo solo admite hasta 4 dígitos") 
        # if self.cleaned_data.get('Manifiesto'):
        #     try:
        #         result = re.match(r'[0-9]*', self.cleaned_data.get('Manifiesto'))
        #         if result.group():
        #             pass 
        #     except:
        #         raise ValidationError("Número de manifiesto incorrecto. Ingrese sólo números.")
        return self.cleaned_data.get('Manifiesto')

    def clean_Fecha_Entrada(self):
        if not self.cleaned_data.get('Fecha_Entrada'):
            raise ValidationError("Este campo es obligatorio")
        return self.cleaned_data.get('Fecha_Entrada')

    def clean_Fecha_Entrada_Puerto(self):
        if not self.cleaned_data.get('Fecha_Entrada_Puerto'):
            raise ValidationError("Este campo es obligatorio")
        return self.cleaned_data.get('Fecha_Entrada_Puerto')

    def clean_Almacen(self):
        if not self.cleaned_data.get('Almacen'):
            raise ValidationError("Este campo es obligatorio")
        return self.cleaned_data.get('Almacen')

    def clean_Agencia(self):
        if not self.cleaned_data.get('Agencia'):
            raise ValidationError("Este campo es obligatorio")
        return self.cleaned_data.get('Agencia')


class Operacion_Importar_No_Manifestados_Form(forms.Form):
    No_Contenedor           = forms.CharField(label='Número de contenedor',required=False, max_length=255, widget=forms.TextInput(attrs={'class': 'form-control'}))
    AWB                     = forms.CharField(label='Número de guía aérea',required=False, max_length=255, widget=forms.TextInput(attrs={'class': 'form-control'}))
    Rectificacion_Aduana    = forms.CharField(label='Rectificación de aduana',required=False, max_length=255, widget=forms.TextInput(attrs={'class': 'form-control'}))
    Manifiesto              = forms.IntegerField(label='Manifiesto', widget=forms.TextInput(attrs={'class': 'form-control'}))
    Fecha_Entrada_Puerto    = forms.DateField(label='Fecha de entrada al puerto', widget=forms.TextInput(attrs={'class': 'form-control', 'type': 'date'})) 
    Fecha_Entrada           = forms.DateField(label='Fecha de desagrupe', widget=forms.TextInput(attrs={'class': 'form-control', 'type': 'date'})) 
    Almacen                 = forms.ModelChoiceField(label='Almacén de destino', queryset=Almacen.objects.all(), widget=forms.Select(attrs={'class': 'form-control'}))
    File                    = forms.FileField(label='Cargue el archivo a importar (.xls)', widget=forms.FileInput(attrs={'class': 'form-control', 'type': 'file'}))
    isPrepago               = forms.BooleanField(label='Carga Prepago',required=False)
    # isAereo                 = forms.BooleanField(label='Envío Aéreo',required=False)
    # isMaritimo              = forms.BooleanField(label='Envío Marítimo',required=False)
    tipo_envio              = forms.ChoiceField(label='Origen',choices=TIPO_ENVIO_CHOICE, widget=forms.Select(attrs={'class': 'form-control'}))
    Agencia                 = forms.ModelChoiceField(label="Corresponsal", queryset=Agencia.objects.all(), widget=forms.Select(attrs={'class': 'form-control'}))
    Pais                 = forms.ModelChoiceField(label='País', queryset=Paises.objects.all(), widget=forms.Select(attrs={'class': 'form-control'}))

    def clean_No_Contenedor(self):
        
        if self.cleaned_data.get('No_Contenedor'):
            try:
                result = re.match(r'^([A-Z]{4})([ ])([0-9]{6})([-])(([0-9]){1,2})$', self.cleaned_data.get('No_Contenedor'))
                if result.group():
                    pass 
            except:
                raise ValidationError("Número de contenedor incorrecto") 
        
        return self.cleaned_data.get('No_Contenedor')

    def clean_AWB(self):
        
        if self.cleaned_data.get('AWB'):
            try:
                result = re.match(r'^([0-9]{3})([-])(([0-9]){8})$', self.cleaned_data.get('AWB'))
                if result.group():
                    pass 
            except:
                raise ValidationError("Número de guía aérea incorrecta") 
        
        return self.cleaned_data.get('AWB')
    
    def clean_Manifiesto(self):
        if not self.cleaned_data.get('Manifiesto'):
            raise ValidationError("Este campo es obligatorio")
        # if len(str(self.cleaned_data.get('Manifiesto'))) > 4:
        #     raise ValidationError("Este campo solo admite hasta 4 dígitos") 
        return self.cleaned_data.get('Manifiesto')

    def clean_Fecha_Entrada(self):
        if not self.cleaned_data.get('Fecha_Entrada'):
            raise ValidationError("Este campo es obligatorio")
        return self.cleaned_data.get('Fecha_Entrada')

    def clean_Fecha_Entrada_Puerto(self):
        if not self.cleaned_data.get('Fecha_Entrada_Puerto'):
            raise ValidationError("Este campo es obligatorio")
        return self.cleaned_data.get('Fecha_Entrada_Puerto')

    def clean_Almacen(self):
        if not self.cleaned_data.get('Almacen'):
            raise ValidationError("Este campo es obligatorio")
        return self.cleaned_data.get('Almacen')

    def clean_Agencia(self):
        if not self.cleaned_data.get('Agencia'):
            raise ValidationError("Este campo es obligatorio")
        return self.cleaned_data.get('Agencia')


class Operacion_Trasladar_De_Almacen_Form(forms.Form):
    Almacen_Traslado = forms.ModelChoiceField(label='Seleccione el almacén donde desea colocar la carga', queryset=Almacen.objects.all(), widget=forms.Select(attrs={'class': 'form-control'}))
    Observaciones    = forms.CharField(label='Observaciones', widget=forms.Textarea(attrs={'class': 'form-control'}))
    def clean_Almacen_Traslado(self):
        if not self.cleaned_data.get('Almacen_Traslado'):
            raise ValidationError("Este campo es obligatorio")
        return self.cleaned_data.get('Almacen_Traslado')

class Entrega_Ejecutar_Form(ModelForm):
    class Meta:
        model = Entrega
        fields = 'Fecha_Entrega', 'Hora_Salida', 'Transportista'

        widgets = {
            'Fecha_Entrega': TextInput(attrs={'class': 'form-control', 'type': 'date'}),
            'Hora_Salida': TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
        }

    def clean_Fecha_Entrega(self):
        if not self.cleaned_data.get('Fecha_Entrega'):
            raise ValidationError("Este campo es obligatorio")
        return self.cleaned_data.get('Fecha_Entrega')

    def clean_Hora_Salida(self):
        if not self.cleaned_data.get('Hora_Salida'):
            raise ValidationError("Este campo es obligatorio")
        return self.cleaned_data.get('Hora_Salida')

    def clean_Transportista(self):
        if not self.cleaned_data.get('Transportista'):
            raise ValidationError("Este campo es obligatorio")
        return self.cleaned_data.get('Transportista')


class Entrega_Concluir_Form(ModelForm):
    class Meta:
        model = Entrega
        fields = 'Hora_Llegada', 

        widgets = {
            'Hora_Llegada': TextInput(attrs={'class': 'form-control', 'type': 'time'}),
        }

    def clean_Hora_Llegada(self):
        if not self.cleaned_data.get('Hora_Llegada'):
            raise ValidationError("Este campo es obligatorio")
        return self.cleaned_data.get('Hora_Llegada')


class Nacionalizar_Desde_Aduana_Form(forms.Form):
    Manifiesto      = forms.CharField(label='Manifiesto', widget=forms.TextInput(attrs={'class': 'form-control'}))
    No_Contenedor   = forms.CharField(label='Número de contenedor',required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    AWB   = forms.CharField(label='Número de guía aérea',required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    # Municipio       = forms.ModelChoiceField(label='Municipio del destinatario', queryset=Municipio.objects.all(), required=False, widget=forms.Select(attrs={'class': 'form-control'}))

class Despacho_Electronico_Form(forms.Form):
    Manifiesto      = forms.CharField(label='Manifiesto', widget=forms.TextInput(attrs={'class': 'form-control'}))
    No_Contenedor   = forms.CharField(label='Número de contenedor',required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    AWB   = forms.CharField(label='Número de guía aérea',required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    # Municipio       = forms.ModelChoiceField(label='Municipio del destinatario', queryset=Municipio.objects.all(), required=False, widget=forms.Select(attrs={'class': 'form-control'}))
    

class EmpresaModelChoiceField(ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.Empresa

class Reporte_Control_Ingresos_Form(forms.Form):
    Fecha_Desde = forms.DateField(label='Fecha desde', widget=forms.TextInput(attrs={'class': 'form-control', 'type': 'date'})) 
    Fecha_Hasta = forms.DateField(label='Fecha hasta', widget=forms.TextInput(attrs={'class': 'form-control', 'type': 'date'})) 
    Operador    = forms.ModelChoiceField(label='Operador', queryset=Operador.objects.filter(Activo = True),required=False, widget=forms.Select(attrs={'class': 'form-control'}))
    Chapa       = forms.ModelChoiceField(label='Transportista', queryset=Transportista.objects.filter(Activo = True), required=False, widget=forms.Select(attrs={'class': 'form-control'}))
    Empresa   = forms.ModelChoiceField(label='Empresa', queryset=Empresa.objects.all(),required=False, widget=forms.Select(attrs={'class': 'form-control'}))  
       
class Reporte_Contable_Aduana_Form(forms.Form):
    Fecha_Desde = forms.DateField(label='Fecha desde', widget=forms.TextInput(attrs={'class': 'form-control', 'type': 'date'})) 
    Fecha_Hasta = forms.DateField(label='Fecha hasta', widget=forms.TextInput(attrs={'class': 'form-control', 'type': 'date'})) 


class Factura_Cobrada_Form(forms.Form):
    Fecha_Cobro = forms.DateField(label='Fecha de cobro', widget=forms.TextInput(attrs={'class': 'form-control', 'type': 'date'})) 

class Verify_Inventory_Form(forms.Form):
    HBL = forms.CharField(label='Listado de HBL', max_length=100000, widget=forms.Textarea(attrs={'rows':'5', 'cols':'100','class': 'form-control'}))
    # HBL = forms.CharField(label='Listado de HBL', widget=forms.TextInput(attrs={'class': 'form-control'}))
    # Fecha_Rectificacion = forms.DateField(label='Fecha de cobro',required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'type': 'date'})) 
    No_Contenedor  = forms.CharField(label='Número de contenedor', max_length=255, widget=forms.TextInput(attrs={'class': 'form-control'}))
    # QR_multiple    = forms.BooleanField(label='QR Múltiple',required=False)

class HBL_Escaneados_Form(forms.Form):
    HBL = forms.CharField(label='Listado de comprobantes ',required=False, widget=forms.Textarea(attrs={'rows':'5', 'cols':'100','class': 'form-control'}))
    HBL_old = forms.CharField(label='Listado de comprobantes',required=False, widget=forms.Textarea(attrs={'rows':'5', 'cols':'100','class': 'form-control'}))
    No_Contenedor = forms.CharField(label='Número de contenedor', max_length=255, widget=forms.TextInput(attrs={'class': 'form-control'}))
    Manifiesto = forms.CharField(label='Manifiesto', max_length=255, widget=forms.TextInput(attrs={'class': 'form-control'}))
    
class Reporte_Diario_Form(forms.Form):
    Fecha_Desde = forms.DateField(label='Fecha desde', widget=forms.TextInput(attrs={'class': 'form-control', 'type': 'date'})) 
    Fecha_Hasta = forms.DateField(label='Fecha hasta', widget=forms.TextInput(attrs={'class': 'form-control', 'type': 'date'})) 
    Facturadores= forms.CharField(label='Facturadores',required=False, max_length=255, widget=forms.TextInput(attrs={'class': 'form-control'}))
    Posiciones_Aduana= forms.CharField(label='Posiciones de aduana',required=False, max_length=255, widget=forms.TextInput(attrs={'class': 'form-control'}))
    Montacargas= forms.CharField(label='Montacargas',required=False, max_length=255, widget=forms.TextInput(attrs={'class': 'form-control'}))
    Almacen = forms.ModelChoiceField(label='Almacén',required=False, queryset=Almacen.objects.all(), widget=forms.Select(attrs={'class': 'form-control'}))

class Tracking_Form(forms.Form):
    HBL = forms.CharField(label='HBL', widget=forms.TextInput(attrs={'class': 'form-control'}))
    CI = forms.CharField(label='Carnet de identidad', widget=forms.TextInput(attrs={'class': 'form-control'}))
    Nombre = forms.CharField(label='Nombre del destinatario', widget=forms.TextInput(attrs={'class': 'form-control'}))

class Empresa_Form(ModelForm):
    Empresa   = forms.ModelChoiceField(label='Empresa', queryset=Empresa.objects.all(), widget=forms.Select(attrs={'class': 'form-control'}))
    class Meta:
        model = Empresa
        fields = '__all__'

class Importar_Inventario_Form(forms.Form):
    Almacen     = forms.ModelChoiceField(label='Almacén', queryset=Almacen.objects.all(), widget=forms.Select(attrs={'class': 'form-control'}))
    File        = forms.FileField(label='Seleccione el archivo a importar (.xls)', widget=forms.FileInput(attrs={'class': 'form-control', 'type': 'file'}))
    Fecha_Desde = forms.DateField(label='Fecha desde', widget=forms.TextInput(attrs={'class': 'form-control', 'type': 'date'})) 
    Fecha_Hasta = forms.DateField(label='Fecha hasta', widget=forms.TextInput(attrs={'class': 'form-control', 'type': 'date'})) 

class Reporte_Transportistas_Form(forms.Form):
    Fecha_Desde = forms.DateField(label='Fecha desde', widget=forms.TextInput(attrs={'class': 'form-control', 'type': 'date'})) 
    Fecha_Hasta = forms.DateField(label='Fecha hasta', widget=forms.TextInput(attrs={'class': 'form-control', 'type': 'date'})) 
    Transportista = forms.ModelChoiceField(label='Transportista', queryset=Transportista.objects.filter(Activo = True), required=False, widget=forms.Select(attrs={'class': 'form-control'}))
    Empresa   = forms.ModelChoiceField(label='Empresa', queryset=Empresa.objects.all(),required=False, widget=forms.Select(attrs={'class': 'form-control'}))  
    
class Ubicar_Cargas_Dentro_Almacen_Form(forms.Form):
    Fila = forms.CharField(label='Área', widget=forms.TextInput(attrs={'class': 'form-control'}))
    Columna = forms.CharField(label='Columna', widget=forms.TextInput(attrs={'class': 'form-control'}))
    Carga = forms.CharField(label='Cargas escaneadas',required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))

class Mercancias_Traslado_Form(forms.Form):
    operador        = forms.ModelChoiceField(label='Operador', queryset=Operador.objects.filter(Activo = True), widget=forms.Select(attrs={'class': 'form-control'}))
    transportista   = forms.ModelChoiceField(label='Transportista', queryset=Transportista.objects.filter(Activo = True), widget=forms.Select(attrs={'class': 'form-control'}))
    
class Agencia_Form(forms.Form):
    Agencia        = forms.ModelChoiceField(label='Seleccione corresponsal', queryset=Agencia.objects.all(), widget=forms.Select(attrs={'class': 'form-control'}))
    Operador        = forms.ModelChoiceField(label='Operador', queryset=Operador.objects.filter(Activo = True), widget=forms.Select(attrs={'class': 'form-control'}))
    Fecha_Desde = forms.DateField(label='Fecha desde', widget=forms.TextInput(attrs={'class': 'form-control', 'type': 'date'})) 
    Fecha_Hasta = forms.DateField(label='Fecha hasta', widget=forms.TextInput(attrs={'class': 'form-control', 'type': 'date'})) 

  
class Prefactura_Contenedor_Form(forms.Form):
    Operador        = forms.ModelChoiceField(label='Operador',required=True, queryset=Operador.objects.filter(Activo = True), widget=forms.Select(attrs={'class': 'form-control'}))
    No_Contenedor = forms.CharField(label='No. de Contenedor',required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    AWB = forms.CharField(label='Guía Aérea',required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    Manifiesto = forms.CharField(label='Manifiesto',required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
