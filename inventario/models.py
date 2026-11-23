from django.db import models
from django.utils.timezone import now
from django.contrib.auth.models import User
import os,re
from django.utils.translation import gettext_lazy as _

# Create your models here.
def get_valid_filename(filename):
    filename = str(filename).strip().replace(' ', '_')
    filename = str(filename).strip().replace('á', 'a')
    filename = str(filename).strip().replace('é', 'e')
    filename = str(filename).strip().replace('í', 'i')
    filename = str(filename).strip().replace('ó', 'o')
    filename = str(filename).strip().replace('ú', 'u')
    filename = str(filename).strip().replace('ñ', 'n')
    filename = str(filename).strip().replace('Á', 'A')
    filename = str(filename).strip().replace('É', 'E')
    filename = str(filename).strip().replace('Í', 'I')
    filename = str(filename).strip().replace('Ó', 'O')
    filename = str(filename).strip().replace('Ú', 'U')
    filename = str(filename).strip().replace('Ñ', 'N')
    return re.sub(r'(?u)[^-\w.]', '', filename)

def get_upload_path_image(instance, filename):
    Agencia = get_valid_filename(instance.Agencia)
    new_path = os.path.join('logotipo_agencia', str(Agencia))
    name = get_valid_filename(filename)
    return os.path.join(new_path, name)

class Operador(models.Model):
    Nombre    = models.CharField('Nombre', max_length=255, blank=False, null=False)
    Activo    = models.BooleanField('Activo')

    class Meta:
        ordering = ["Nombre"]

    def __str__(self):
        return self.Nombre

class Provincia(models.Model):
    Nombre      = models.CharField('Nombre', max_length=255, blank=False, null=False)
    search_text = models.CharField('Campo de búsqueda', max_length=255, blank=True, null=True)

    class Meta:
        ordering = ["Nombre"]
    def __str__(self):
        return self.Nombre

class Municipio(models.Model):
    Provincia   = models.ForeignKey('Provincia', on_delete=models.PROTECT, null=False, blank=False)
    Nombre      = models.CharField('Nombre', max_length=255, blank=False, null=False)
    Importe_por_entrega = models.FloatField('Importe por entrega', blank=False, null=False )
    Importe_por_trasbordo = models.FloatField('Importe por trasbordo', blank=True, null=True )
    search_text = models.CharField('Campo de búsqueda', max_length=255, blank=True, null=True)

    class Meta:
        ordering = ["Nombre"]
        
    def __str__(self):
        return self.Nombre

class Destinatario(models.Model):
    Nombre          = models.CharField('Nombre y apellidos', max_length=255, blank=False, null=False)
    CI              = models.CharField('Carnet de identidad', max_length=255, blank=True, null=True)
    Pasaporte_DNI   = models.CharField('No. pasaporte / DNI', max_length=255, blank=True, null=True)
    Direccion       = models.CharField('Dirección', max_length=255, blank=False, null=False)
    Provincia       = models.ForeignKey('Provincia', on_delete=models.PROTECT, null=True, blank=True)
    Municipio       = models.ForeignKey('Municipio', on_delete=models.PROTECT, null=True, blank=True)
    Telefono        = models.CharField('Teléfono', max_length=255, blank=False, null=False)
    Email           = models.CharField('Email', max_length=255, blank=True, null=True)

    class Meta:
        ordering = ["Nombre"]
        
    def __str__(self):
        return self.Nombre

class Remitente(models.Model):
    Nombre_Remitente    = models.CharField('Nombre y apellidos', max_length=255, blank=False, null=False)
    Pasaporte_DNI       = models.CharField('No. pasaporte / DNI', max_length=255, blank=True, null=True)

    class Meta:
        ordering = ["Nombre_Remitente"]
        
    def __str__(self):
        return self.Nombre_Remitente

class Almacen(models.Model):
    Nombre    = models.CharField('Nombre', max_length=255, blank=False, null=False)

    class Meta:
        ordering = ["Nombre"]
        verbose_name = "almacén"
        verbose_name_plural = "almacenes"

    def __str__(self):
        return self.Nombre

class Incidencia(models.Model):
    Tipo    = models.CharField('Tipo de incidencia', max_length=255, blank=False, null=False)

    class Meta:
        ordering = ["Tipo"]
        

    def __str__(self):
        return self.Tipo


class Paises(models.Model):
    pais = models.CharField('País', max_length=255, blank=False, null=False)
    sigla = models.CharField('Sigla', max_length=255, blank=True, null=True)

    class Meta:
        ordering = ["pais"]
        

    def __str__(self):
        return self.pais

class Agencia(models.Model):
    Agencia    = models.CharField('Agencia', max_length=255, blank=False, null=False)
    Correo    = models.CharField('Correo Electrónico', max_length=255, blank=False, null=False)
    Pais    = models.ForeignKey('Paises', on_delete=models.PROTECT, null=True, blank=True)
    Logo = models.ImageField(upload_to=get_upload_path_image,null=True,blank=True,max_length=500)
    Habilitada = models.BooleanField('Habilitada',default=True)
    class Meta:
        ordering = ["Agencia"]
        

    def __str__(self):
        return self.Agencia

class Lugar_Operan(models.Model):
    Lugar    = models.CharField('Lugar donde operan', max_length=255, blank=False, null=False)
    Agencia = models.ForeignKey('Agencia', on_delete=models.PROTECT, null=True, blank=True)
    class Meta:
        ordering = ["Lugar"]
        

    def __str__(self):
        return self.Lugar

class Inventario(models.Model):
    ESTADO = [
        ('Desagrupe', 'en desagrupe'),
        ('Inventario', 'en inventario'),
        ('Entregado', 'entregada'),
        ('Traslado', 'en traslado'),
        ('No localizable', 'no localizable'),
        ('Salida de inventario', 'eliminada del inventario'),
    ]

    TIPO_ENTREGA = [
        ('Presencial', 'Presencial'),
        ('Puerta a puerta', 'Puerta a puerta'),
        ('Trasbordo', 'Trasbordo'),
    ]

    TIPO_OPERACION = [
        ('Envio', 'Envío'),
        ('ENA', 'ENA'),
        ('Menaje', 'Menaje'),
    ]
    
    #Informacion general
    No_Contenedor           = models.CharField('Número de contenedor', max_length=255, blank=True, null=True)
    AWB                     = models.CharField('Número de guía aérea', max_length=255, blank=True, null=True)
    Agencia                 = models.ForeignKey('Agencia', on_delete=models.PROTECT, null=True, blank=True)
    Pais_Origen             = models.ForeignKey('Paises', on_delete=models.PROTECT, null=True, blank=True)
    HBL                     = models.CharField('HBL', max_length=255, blank=True, null=True)
    Manifiesto              = models.CharField('Manifiesto', max_length=255, blank=False, null=False)
    Cantidad_Bultos         = models.PositiveIntegerField('Cantidad de bultos', blank=False, null=False)
    Peso                    = models.FloatField('Peso (Kg)', blank=False, null=False)
    Volumen                 = models.FloatField('Volumen (m3)', blank=False, null=False)
    Contenido               = models.TextField('Contenido del paquete', blank=True, null=True)
    Precio                  = models.FloatField('Cargos extra', blank=True, null=True)
    Importe_Derecho_aduanal = models.FloatField('Importe por derecho aduanal', blank=True, null=True)
    Importe_Servicio_aduanal = models.FloatField('Importe por servicio aduanal', blank=True, null=True)
    Destinatario            = models.ForeignKey('Destinatario', on_delete=models.PROTECT, null=True, blank=True)
    Remitente               = models.ForeignKey('Remitente', on_delete=models.PROTECT, null=True, blank=True)
    Estado                  = models.CharField(choices=ESTADO, max_length=255, blank=True, null=True)
    Incidencia              = models.ForeignKey('Incidencia', on_delete=models.PROTECT, null=True, blank=True)
    Observ_Incidencia       = models.TextField('Observaciones sobre la incidencia', blank=True, null=True)
    Fecha_Entrada_Puerto    = models.DateField('Fecha de entrada al puerto', blank=True, null=True) 
    Categoria_Operacion     = models.CharField('Categoría de la operación', max_length=255, blank=True, null=True)
    #Carga nacionalizada
    Nacionalizado           = models.BooleanField('Se encuentra nacionalizada', default=False, null=True, blank=True)
    Fecha_Nacionalizacion   = models.DateField('Fecha de nacionalización', blank=True, null=True) 
    #Informacion de Estado = No nacionalizado
    Fecha_Entrada           = models.DateField('Fecha de desagrupe', blank=True, null=True) 
    #Informacion de Estado = Inventario
    Almacen                 = models.ForeignKey('Almacen', on_delete=models.PROTECT, null=True, blank=True, verbose_name='Almacén')
    Ubicacion_Fila          = models.CharField('Área', max_length=4, blank=True, null=True) 
    Ubicacion_Columna       = models.IntegerField('Columna', blank=True, null=True) 
    #Informacion de Estado = Traslado
    Fecha_Traslado          = models.DateField('Fecha de traslado', blank=True, null=True)  
    #Informacion de Estado = Pre-cita
    Fecha_Pre_Cita          = models.DateField('Fecha de pre-cita', blank=True, null=True) 
    #Informacion de Estado = Entregado
    Fecha_Entrega           = models.DateField('Fecha de entrega', blank=True, null=True) 
    Nombre_Entrega          = models.CharField('Nombre y apellidos', max_length=255, blank=True, null=True)
    CI_Entrega              = models.CharField('Carnet de identidad', max_length=255, blank=True, null=True)
    Pasaporte_DNI_Entrega   = models.CharField('No. pasaporte / DNI', max_length=255, blank=True, null=True)
    Direccion_Entrega       = models.CharField('Dirección', max_length=255, blank=True, null=True)
    Provincia_Entrega       = models.ForeignKey('Provincia', on_delete=models.PROTECT, null=True, blank=True)
    Municipio_Entrega       = models.ForeignKey('Municipio', on_delete=models.PROTECT, null=True, blank=True)
    Telefono_Entrega        = models.CharField('Teléfono', max_length=255, blank=True, null=True)
    Tipo_Entrega            = models.CharField(choices=ESTADO, max_length=255, blank=True, null=True)
    #Informacion de Estado = Devolución
    Fecha_Devolución        = models.DateField('Fecha de salida de inventario', blank=True, null=True) 
    Observ_Devolucion       = models.TextField('Observaciones sobre la salida de inventario', blank=True, null=True)
    #Informacion de Estado = No localizable
    Fecha_No_Localizable    = models.DateField('Fecha de declarado no localizable', blank=True, null=True) 
    Observ_No_Localizable   = models.TextField('Observaciones', blank=True, null=True)
    #Confirma si el inventario se encuentra en algun comprobante de entrega a destinatario
    isFacturado             = models.BooleanField('Esta facturado', default=False)
    #Carga pre-paga
    isPrepago             = models.BooleanField('Carga prepaga', default=True)
    #Confirmar existencia
    exist             = models.BooleanField('Existe', default=False)
    rectificacion_aduana = models.CharField('Rectificación de aduana', max_length=255, blank=True, null=True)
    trasbordo = models.BooleanField('Trasbordo', default=False)
    canal_rojo = models.BooleanField('Canal rojo', default=False)
    #-------Informacion segun tipo de carga (aérea o marítima)   
    isAereo             = models.BooleanField('Carga aerea', default=False)
    isMaritimo             = models.BooleanField('Carga maritima', default=False)
    Importe_Kg_Adicional = models.FloatField('Importe Kg adicional', blank=True, null=True)
    peso_real = models.FloatField('Peso real', blank=True, null=True)
    Aeropuerto_Origen        = models.CharField('Aeropuerto de Origen', max_length=255, blank=True, null=True)
    codigo_barra = models.CharField('Código de barras', max_length=255, blank=True, null=True)
    User_Cobrador           = models.CharField('Cobrador',max_length=255, null=True, blank=True)

    class Meta:
        ordering = ["HBL"]
        permissions = (
            ("can_nacionalizar", "Puede nacionalizar"),
        )
    def __str__(self):
        return self.HBL

class Empresa(models.Model):
    Nombre        = models.CharField('Nombre de la Empresa', max_length=500, blank=False, null=False)
    Telefono      = models.CharField('Teléfono', max_length=255, blank=True, null=True)
    class Meta:
        ordering = ["Nombre"]
    
    def __str__(self):
        return self.Nombre
        
class Transportista(models.Model):
    TIPO = [
        ('Privado', 'Privado'),
        ('Estatal', 'Estatal'),
    ]

    Nombre  = models.CharField('Nombre y apellidos', max_length=255, blank=False, null=False)
    CI      = models.CharField('Carnet de identidad', max_length=255, blank=True, null=True)
    # Chapa   = models.CharField('Chapa del vehíulo', max_length=255, blank=False, null=False)
    Tipo    = models.CharField(choices=TIPO, max_length=255, blank=True, null=True)
    Empresa = models.ForeignKey('Empresa', on_delete=models.PROTECT, null=True, blank=True)
    Activo  = models.BooleanField('Activo')

    class Meta:
        ordering = ["Nombre"]

    def __str__(self):
        return self.Nombre
        # return self.Chapa + ', ' + self.Nombre

class Chapa(models.Model):
    Chapa         = models.CharField('Chapa del vehículo', max_length=255, blank=False, null=False)
    transportista = models.ForeignKey('Transportista', on_delete=models.PROTECT, null=True, blank=True)

class Entrega(models.Model):
    ESTADO = [
        ('Programado', 'Programado'),
        ('Ejecucion', 'Ejecución'),
        ('Cancelado', 'Cancelado'),
        ('Concluido', 'Concluido'),
    ]

    Fecha_Entrega     = models.DateField('Fecha del traslado', blank=False, null=False) 
    Hora_Salida       = models.TimeField('Hora de salida', blank=True, null=True) 
    Hora_Llegada      = models.TimeField('Hora de regreso', blank=True, null=True) 
    Transportista     = models.ForeignKey('Transportista', on_delete=models.PROTECT, null=True, blank=True)
    Chapa             = models.CharField('Chapa', max_length=10, null=True, blank=True)
    No_Recorrido      = models.IntegerField('No. de recorrido', blank=True, null=True)
    Estado            = models.CharField(choices=ESTADO, max_length=255, blank=True, null=True)
    Factura_Operador  = models.ForeignKey('Factura_Operador', on_delete=models.PROTECT, null=True, blank=True)

    def __str__(self):
        return str(self.Fecha_Entrega)


class Cita(models.Model):
    Fecha           = models.DateField('Fecha de la cita', blank=False, null=False) 
    Hora            = models.TimeField('Hora de cita', blank=True, null=True) 
    Inventario      = models.ManyToManyField('Inventario', verbose_name="Listado de inventarios a entregar", blank=True)

    def __str__(self):
        return str(self.Fecha)

    def set_inventarios(self, inventarios):
        self.Inventario.clear()
        for current_inventario in inventarios:
            self.Inventario.add(current_inventario)
        self.save()


class Manifiesto(models.Model):
    No_Contenedor           = models.CharField('Número de contenedor', max_length=255, blank=True, null=True)
    AWB                     = models.CharField('Número de guía aérea', max_length=255, blank=True, null=True)
    Manifiesto              = models.CharField('Manifiesto', max_length=255, blank=False, null=False)
    Consignatario           = models.CharField('Consignatario', max_length=255, blank=False, null=False,default='')
    Fecha_Importacion       = models.DateTimeField('Fecha de importación del archivo', default=now, blank=False, null=False) 
    Fecha_Embarque          = models.DateField('Fecha de embarque', blank=False, null=False,default=now) 
    File                    = models.CharField('Archivo', max_length=255, blank=False, null=False)
    isPrepago               = models.BooleanField('Carga prepaga', default=True)
    #-------Informacion tipo de manifiesto (aérea o marítima)   
    isAereo             = models.BooleanField('Carga aerea', default=False)
    isMaritimo             = models.BooleanField('Carga maritima', default=False)
    Agencia  = models.ForeignKey('Agencia', on_delete=models.PROTECT, null=True, blank=True)
    Peso_total              = models.FloatField('Peso total' ,blank=False, null=False,default=0)
    Cantidad_bultos              = models.IntegerField('Cantidad de bultos',blank=False, null=False,default=0)
    Cantidad_envios              = models.IntegerField('Cantidad de envíos',blank=False, null=False,default=0)
    Habilitado             = models.BooleanField('Habilitado', default=False)
    Aeropuerto_Origen        = models.CharField('Aeropuerto de Origen', max_length=255, blank=True, null=True)
    Pais_Origen  = models.ForeignKey('Paises', on_delete=models.PROTECT, null=True, blank=True)
    
    class Meta:
        unique_together = ['No_Contenedor', 'Manifiesto','AWB']
        permissions = (
            ("can_generar_boleta", "Generar boletas"),
        )
    def __str__(self):
        return str('Contenedor: ' + str(self.No_Contenedor) + ', Manifiesto: ' + str(self.Manifiesto))

class Factura(models.Model):
    ESTADO = [
        ('Creada', 'Creada'),
        ('Asignada', 'Asignada'),
        ('Desestimada', 'Desestimada'),
        ('Cobrada', 'Cobrada'),
    ]

    Contenido                       = models.TextField('Contenido', blank=False, null=False)
    isMultiple                      = models.BooleanField('Múltiple', blank=False, null=False)
    isEnvio                         = models.BooleanField('Envío', blank=False, null=False)
    Fecha                           = models.DateTimeField('Fecha de creación', blank=True, null=True) 
    Fecha_cobro                     = models.DateTimeField('Fecha de cobro', blank=True, null=True) 
    url                             = models.CharField('url', max_length=255, blank=True, null=True)
    Estado                          = models.CharField(choices=ESTADO, max_length=255, blank=True, null=True)
    Destinatario                    = models.ForeignKey('Destinatario', on_delete=models.PROTECT, null=True, blank=True)
    Importe_Total_Factura           = models.FloatField('Importe total', blank=True, null=True)
    Importe_Transcargo_Total        = models.FloatField('Importe total de transcargo', blank=True, null=True)
    Importe_Seguro_Carga_Total      = models.FloatField('Importe total de seguro de carga', blank=True, null=True) 
    Importe_Recargo_Total           = models.FloatField('Recargo total', blank=True, null=True)    
    Importe_Transportacion_Total    = models.FloatField('Importe total de transportación', blank=True, null=True)         
    Importe_Derecho_Aduanal_Total   = models.FloatField('Importe total de derecho aduanal', blank=True, null=True)      
    Importe_Servicio_Aduanal_Total  = models.FloatField('Importe total de servicio aduanal', blank=True, null=True) 
    Importe_Kg_Adicional_Total      = models.FloatField('Importe total de sobrepeso', blank=True, null=True) 
    Cantidad_Bultos_Total           = models.IntegerField('Cantidad de bultos', blank=True, null=True, default=0)    
    User_Facturador                 = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)
    #Envios
    Importe_Sobredimension_Total = models.FloatField('Importe total de sobredimensión', blank=True, null=True) 
    #Ena/Menaje     
    Importe_Servicio_Corresponsalia_Total = models.FloatField('Importe total de corresponsalía', blank=True, null=True)    
    #Lista de inventarios
    Inventario = models.ManyToManyField('Inventario', verbose_name="Listado de inventarios facturados", blank=True, through='Factura_Inventario')
    Recibo_Ingreso = models.CharField(max_length=255, blank=True, null=True)
    Presencial = models.BooleanField('Presencial', blank=True, null=True)
    Agencia = models.ForeignKey('Agencia', on_delete=models.PROTECT, null=True, blank=True)
    Provincia       = models.ForeignKey('Provincia', on_delete=models.PROTECT, null=True, blank=True)
    User_Cobrador           = models.CharField('Cobrador',max_length=255, null=True, blank=True)

    def __str__(self):
        return 'Factura No. ' + str(self.id)

class Factura_Inventario(models.Model):
    Factura                         = models.ForeignKey('Factura', on_delete=models.PROTECT)
    Inventario                      = models.ForeignKey('Inventario', on_delete=models.CASCADE)
    Importe_Seguro_Carga            = models.FloatField('Importe de seguro de carga', blank=True, null=True) 
    Importe_Transportacion          = models.FloatField('Importe de transportación', blank=True, null=True)  
    Importe_Transcargo              = models.FloatField('Importe de transcargo', blank=True, null=True)
    #Envio
    Importe_Sobredimension          = models.FloatField('Importe de sobredimensión', blank=True, null=True)   
    #Ena
    Importe_Servicio_Corresponsalia = models.FloatField('Importe de corresponsalía', blank=True, null=True) 
    Importe_KG_Adicional = models.FloatField('Importe de kg adicional', blank=True, null=True) 
    

class Factura_Operador(models.Model):
    ESTADO = [
        ('En espera', 'En espera'),
        ('Pendiente de cobro', 'Pendiente de cobro'),
        ('Cobrada', 'Cobrada'),
        ('Desestimada', 'Desestimada'),
    ]

    Fecha_Creacion          = models.DateTimeField('Fecha de creación', blank=True, null=True) 
    Fecha_Cobro             = models.DateTimeField('Fecha de cobro', blank=True, null=True) 
    Fecha_Desestimacion     = models.DateTimeField('Fecha de desestimada', blank=True, null=True) 
    Estado                  = models.CharField(choices=ESTADO, max_length=255, blank=True, null=True)
    Operador                = models.ForeignKey(Operador, on_delete=models.PROTECT, null=True, blank=True)
    User_Facturador         = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)
    User_Cobrador           = models.CharField('Cobrador',max_length=255, null=True, blank=True)
    Provincia               = models.ForeignKey(Provincia, on_delete=models.PROTECT, null=True, blank=True)
    Importe                 = models.FloatField('Importe', blank=True, null=True, default=0)  
    Importe_Cobrado         = models.FloatField('Importe cobrado', blank=True, null=True, default=0)  
    #Lista de comprobantes de entrega de destinatarios
    Facturas_Destinatarios  = models.ManyToManyField(Factura, verbose_name="Listado de comprobantes de entrega de destinatarios", blank=True)
    Recibo_Ingreso = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return 'Comprobante No. ' + str(self.id)


class Inventario_Reincorporado(models.Model):
    Factura_Operador            = models.ForeignKey(Factura_Operador, on_delete=models.PROTECT, null=True, blank=True)
    Inventario                  = models.ForeignKey(Inventario, on_delete=models.PROTECT, null=True, blank=True)
    Observaciones               = models.CharField(max_length=255)
    Fecha                       = models.DateTimeField('Fecha de reincorporación', blank=True, null=True, default=now) 
    Importe                     = models.FloatField('Importe total', blank=True, null=True, default=0) 
    Importe_Transcargo          = models.FloatField('Importe de transcargo', blank=True, null=True, default=0) 
    Importe_Seguro_Carga        = models.FloatField('Importe de seguro de carga', blank=True, null=True, default=0) 
    Importe_Transportacion      = models.FloatField('Importe de transportación', blank=True, null=True, default=0) 
    Importe_Derecho_Aduanal     = models.FloatField('Importe de derecho aduanal', blank=True, null=True, default=0) 
    Importe_Servicio_Aduanal    = models.FloatField('Importe de servicio aduanal', blank=True, null=True, default=0) 

    def __str__(self):
        return self.Inventario.HBL


class Traking(models.Model):
    ESTADO = [
        
        ('En depósito', 'En depósito'),
        ('Despachado por aduana', 'Despachado por aduana'),
        ('En almacén', 'En almacén'),
        ('En tránsito', 'En tránsito'),
        ('Entregada', 'Entregada'),

# ------------------------------------------------
        # ('En almacén', 'En almacén'),
        ('Lista para traslado', 'Lista para traslado'),
        ('En traslado', 'En traslado'),
        # ('Entregada', 'Entregada'),
        ('No localizable', 'No localizable'),
        ('Eliminada del inventario', 'Eliminada del inventario'),
    ]

    Inventario        = models.ForeignKey(Inventario, on_delete=models.PROTECT, null=True, blank=True)
    Estado            = models.CharField(choices=ESTADO, max_length=255, blank=True, null=True)
    Observaciones     = models.CharField(max_length=255, blank=True, null=True)
    Fecha             = models.DateTimeField('Fecha de acción', blank=True, null=True, default=now) 

    def __str__(self):
        return self.Inventario.HBL

class HBL_No_Manifestados(models.Model):
    HBL                 = models.CharField(max_length=255, blank=False, null=False)
    No_Contenedor       = models.CharField(max_length=255, blank=True, null=True)
    Fecha_Rectificacion = models.DateField('Fecha de rectificación',auto_now_add=True)

class Temporal_HBL_Escaneados(models.Model):
    Inventario        = models.ForeignKey(Inventario, on_delete=models.PROTECT, null=True, blank=True)
    Destinatario        = models.ForeignKey(Destinatario, on_delete=models.PROTECT, null=True, blank=True)

class Desglose(models.Model):
    Fecha_Desglose = models.DateField('Fecha de desglose',auto_now_add=True)
    Desglose       = models.CharField('Desglose', max_length=255, blank=False, null=False)

