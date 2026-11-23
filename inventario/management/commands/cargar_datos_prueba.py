from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.timezone import now

from inventario.models import (
    Agencia,
    Almacen,
    Destinatario,
    Incidencia,
    Inventario,
    Manifiesto,
    Municipio,
    Paises,
    Provincia,
    Remitente,
    Traking,
)


class Command(BaseCommand):
    help = 'Carga manifiestos e inventarios de prueba (prefijo TEST-).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Elimina previamente los datos de prueba TEST-.',
        )

    def handle(self, *args, **options):
        if options['reset']:
            self._reset()

        with transaction.atomic():
            created = self._cargar()
        self.stdout.write(self.style.SUCCESS(
            'Datos de prueba cargados: %s manifiestos, %s inventarios.' % created
        ))

    def _reset(self):
        inventarios = Inventario.objects.filter(HBL__startswith='TEST-')
        Traking.objects.filter(Inventario__in=inventarios).delete()
        inventarios.delete()
        Destinatario.objects.filter(Nombre__startswith='TEST ').delete()
        Remitente.objects.filter(Nombre_Remitente__startswith='TEST ').delete()
        Manifiesto.objects.filter(Manifiesto__startswith='TEST-').delete()
        self.stdout.write('Datos de prueba anteriores eliminados.')

    def _cargar(self):
        agencia = Agencia.objects.first()
        pais = Paises.objects.first()
        almacen = Almacen.objects.first()
        incidencia = Incidencia.objects.first()
        habana = Provincia.objects.filter(id=2).first() or Provincia.objects.first()
        playa = Municipio.objects.filter(Provincia=habana, Nombre__icontains='Playa').first()
        if not playa:
            playa = Municipio.objects.filter(Provincia=habana).first() or Municipio.objects.first()

        if not all([agencia, pais, almacen, habana, playa]):
            raise SystemExit('Faltan catálogos (agencia, país, almacén, provincia o municipio).')

        hoy = date.today()
        destinatarios = []
        remitentes = []
        for i, nombre in enumerate([
            'Ana Pérez',
            'Carlos Díaz',
            'María López',
            'Pedro García',
            'Laura Sánchez',
            'José Fernández',
            'Elena Ruiz',
            'Raúl Torres',
        ], start=1):
            destinatarios.append(Destinatario.objects.create(
                Nombre='TEST %s' % nombre,
                CI='8501011234%s' % i,
                Pasaporte_DNI='P%s%s' % (i, 100000 + i),
                Direccion='Calle %s e/ 5 y 7, Playa' % (10 + i),
                Provincia=habana,
                Municipio=playa,
                Telefono='5230000%s' % i,
                Email='test%s@prueba.cu' % i,
            ))
            remitentes.append(Remitente.objects.create(
                Nombre_Remitente='TEST Remitente %s' % i,
                Pasaporte_DNI='R%s' % (200000 + i),
            ))

        maritimo = Manifiesto.objects.create(
            No_Contenedor='TEST-CONT-001',
            AWB='',
            Manifiesto='TEST-MNF-MAR-001',
            Consignatario='Cubanacan Express',
            Fecha_Importacion=now(),
            Fecha_Embarque=hoy - timedelta(days=20),
            File='manifiestos/TEST-MNF-MAR-001.xls',
            isPrepago=True,
            isAereo=False,
            isMaritimo=True,
            Agencia=agencia,
            Pais_Origen=pais,
            Peso_total=1250.5,
            Cantidad_bultos=48,
            Cantidad_envios=6,
            Habilitado=True,
            Aeropuerto_Origen='',
        )
        aereo = Manifiesto.objects.create(
            No_Contenedor='',
            AWB='TEST-AWB-7788',
            Manifiesto='TEST-MNF-AIR-001',
            Consignatario='Cubanacan Express',
            Fecha_Importacion=now(),
            Fecha_Embarque=hoy - timedelta(days=8),
            File='manifiestos/TEST-MNF-AIR-001.xls',
            isPrepago=False,
            isAereo=True,
            isMaritimo=False,
            Agencia=agencia,
            Pais_Origen=pais,
            Peso_total=186.2,
            Cantidad_bultos=12,
            Cantidad_envios=2,
            Habilitado=False,
            Aeropuerto_Origen='MIA',
        )

        casos = [
            {
                'hbl': 'TEST-HBL-001', 'manifiesto': maritimo, 'estado': 'Desagrupe',
                'nacionalizado': False, 'peso': 45.2, 'bultos': 3, 'volumen': 0.8,
                'contenido': 'Ropa y calzado', 'exist': True, 'prepago': True,
            },
            {
                'hbl': 'TEST-HBL-002', 'manifiesto': maritimo, 'estado': 'Inventario',
                'nacionalizado': True, 'peso': 62.0, 'bultos': 4, 'volumen': 1.1,
                'contenido': 'Electrodomésticos', 'exist': True, 'prepago': True,
                'fecha_nac': hoy - timedelta(days=3), 'fila': 'A1', 'columna': 12,
            },
            {
                'hbl': 'TEST-HBL-003', 'manifiesto': maritimo, 'estado': 'Inventario',
                'nacionalizado': False, 'peso': 28.4, 'bultos': 2, 'volumen': 0.4,
                'contenido': 'Medicamentos y aseo', 'exist': True, 'prepago': True,
                'fila': 'B2', 'columna': 5, 'incidencia': incidencia,
            },
            {
                'hbl': 'TEST-HBL-004', 'manifiesto': maritimo, 'estado': 'Traslado',
                'nacionalizado': True, 'peso': 90.0, 'bultos': 6, 'volumen': 1.8,
                'contenido': 'Muebles desarmados', 'exist': True, 'prepago': True,
                'fecha_nac': hoy - timedelta(days=10), 'fecha_traslado': hoy - timedelta(days=1),
            },
            {
                'hbl': 'TEST-HBL-005', 'manifiesto': maritimo, 'estado': 'Entregado',
                'nacionalizado': True, 'peso': 33.7, 'bultos': 2, 'volumen': 0.5,
                'contenido': 'Juguetes', 'exist': True, 'prepago': True,
                'fecha_nac': hoy - timedelta(days=15), 'fecha_entrega': hoy - timedelta(days=2),
            },
            {
                'hbl': 'TEST-HBL-006', 'manifiesto': maritimo, 'estado': 'No localizable',
                'nacionalizado': True, 'peso': 18.0, 'bultos': 1, 'volumen': 0.2,
                'contenido': 'Documentos', 'exist': False, 'prepago': True,
                'fecha_nac': hoy - timedelta(days=25), 'no_localizable': hoy - timedelta(days=4),
            },
            {
                'hbl': 'TEST-HBL-007', 'manifiesto': aereo, 'estado': 'Desagrupe',
                'nacionalizado': False, 'peso': 12.5, 'bultos': 1, 'volumen': 0.15,
                'contenido': 'Repuestos electrónicos', 'exist': False, 'prepago': False,
                'canal_rojo': True,
            },
            {
                'hbl': 'TEST-HBL-008', 'manifiesto': aereo, 'estado': 'Inventario',
                'nacionalizado': True, 'peso': 21.3, 'bultos': 2, 'volumen': 0.3,
                'contenido': 'Alimentos no perecederos', 'exist': True, 'prepago': False,
                'fecha_nac': hoy - timedelta(days=1), 'fila': 'C3', 'columna': 8,
            },
        ]

        for idx, caso in enumerate(casos):
            manifiesto = caso['manifiesto']
            dest = destinatarios[idx]
            rem = remitentes[idx]
            inventario = Inventario.objects.create(
                No_Contenedor=manifiesto.No_Contenedor or None,
                AWB=manifiesto.AWB or None,
                Agencia=agencia,
                Pais_Origen=pais,
                HBL=caso['hbl'],
                Manifiesto=manifiesto.Manifiesto,
                Cantidad_Bultos=caso['bultos'],
                Peso=caso['peso'],
                Volumen=caso['volumen'],
                Contenido=caso['contenido'],
                Precio=0,
                Importe_Derecho_aduanal=25 if caso['nacionalizado'] else 0,
                Importe_Servicio_aduanal=10 if caso['nacionalizado'] else 0,
                Destinatario=dest,
                Remitente=rem,
                Estado=caso['estado'],
                Incidencia=caso.get('incidencia'),
                Observ_Incidencia='Caja golpeada' if caso.get('incidencia') else None,
                Fecha_Entrada_Puerto=hoy - timedelta(days=18 if manifiesto.isMaritimo else 6),
                Categoria_Operacion='Envio',
                Nacionalizado=caso['nacionalizado'],
                Fecha_Nacionalizacion=caso.get('fecha_nac'),
                Fecha_Entrada=hoy - timedelta(days=12 if manifiesto.isMaritimo else 5),
                Almacen=almacen,
                Ubicacion_Fila=caso.get('fila'),
                Ubicacion_Columna=caso.get('columna'),
                Fecha_Traslado=caso.get('fecha_traslado'),
                Fecha_Entrega=caso.get('fecha_entrega'),
                Nombre_Entrega=dest.Nombre if caso['estado'] == 'Entregado' else None,
                CI_Entrega=dest.CI if caso['estado'] == 'Entregado' else None,
                Fecha_No_Localizable=caso.get('no_localizable'),
                Observ_No_Localizable='No responde teléfono' if caso.get('no_localizable') else None,
                isFacturado=caso['estado'] == 'Entregado',
                isPrepago=caso['prepago'],
                exist=caso['exist'],
                canal_rojo=caso.get('canal_rojo', False),
                isAereo=manifiesto.isAereo,
                isMaritimo=manifiesto.isMaritimo,
                Aeropuerto_Origen=manifiesto.Aeropuerto_Origen or None,
            )
            Traking.objects.create(
                Inventario=inventario,
                Estado='En depósito' if caso['estado'] == 'Desagrupe' else caso['estado'],
                Observaciones='Dato de prueba',
                Fecha=now(),
            )

        return Manifiesto.objects.filter(Manifiesto__startswith='TEST-').count(), Inventario.objects.filter(HBL__startswith='TEST-').count()
