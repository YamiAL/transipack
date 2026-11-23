from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer
from rest_framework.parsers import JSONParser
from rest_framework import status
from rest_framework.permissions import *
from api.serializers import *
from inventario.models import Inventario,Operador,Destinatario,Traking
from django.shortcuts import get_object_or_404

# Create your views here.
class TrackingApiView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [JSONRenderer]

    def get(self, request, format=None):
        HBL_Request = self.request.query_params.get('HBL')
        #Consulta a Base de datos
        hbl = get_object_or_404(Inventario, HBL=HBL_Request)
        if hbl:
            #Respuesta del servicio
            response = {}
            
            #Completando respuesta
            response['HBL'] = hbl.HBL
            response['Estado'] = hbl.Estado
            response['Fecha_Arribo_Puerto'] = hbl.Fecha_Entrada_Puerto
            response['Fecha_Desagrupe'] = hbl.Fecha_Entrada
            response['Fecha_Nacionalizacion'] = hbl.Fecha_Nacionalizacion
            response['Fecha_Traslado'] = hbl.Fecha_Traslado
            response['Fecha_Pre_Cita'] = hbl.Fecha_Pre_Cita
            response['Fecha_Entrega'] = hbl.Fecha_Entrega
            response['Fecha_Salida_Inventario'] = hbl.Fecha_Devolución
            response['Fecha_No_Localizable'] = hbl.Fecha_No_Localizable

            return Response(response)


class TrackingApiHBLCIView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [JSONRenderer]

    def get(self, request, format=None):
        CI_Request = self.request.query_params.get('CI')
        HBL_Request = self.request.query_params.get('HBL')
        response = {}


        inventarios = ''
        #Consulta a Base de datos
        if HBL_Request:
            hbl = get_object_or_404(Inventario, HBL=HBL_Request)

            #Respuesta del servicio
            #Completando respuesta
            response['HBL'] = hbl.HBL
            response['Estado'] = hbl.Estado
            response['Fecha_Arribo_Puerto'] = hbl.Fecha_Entrada_Puerto
            response['Fecha_Desagrupe'] = hbl.Fecha_Entrada
            response['Fecha_Nacionalizacion'] = hbl.Fecha_Nacionalizacion
            response['Fecha_Traslado'] = hbl.Fecha_Traslado
            response['Fecha_Pre_Cita'] = hbl.Fecha_Pre_Cita
            response['Fecha_Entrega'] = hbl.Fecha_Entrega
            response['Fecha_Salida_Inventario'] = hbl.Fecha_Devolución
            response['Fecha_No_Localizable'] = hbl.Fecha_No_Localizable

        if CI_Request:
            destinatarios = Destinatario.objects.filter(CI=CI_Request).values_list('id')
            inventarios = Inventario.objects.filter(Destinatario__id__in=destinatarios).order_by('HBL').values_list('id')
        if inventarios:
            #Respuesta del servicio
            lista_inventarios=[]
            #Completando respuesta
            ci_hbl_tracking = Traking.objects.filter(Inventario__id__in=inventarios)
            for hbl in ci_hbl_tracking:
                hbl_ci = {}
                hbl_ci['Inventarios'] = hbl.Inventario.HBL
                hbl_ci['Fecha_Arribo_Puerto'] = hbl.Inventario.Fecha_Entrada_Puerto
                hbl_ci['Fecha_Desagrupe'] = hbl.Inventario.Fecha_Entrada
                hbl_ci['Fecha_Nacionalizacion'] = hbl.Inventario.Fecha_Nacionalizacion
                hbl_ci['Fecha_Traslado'] = hbl.Inventario.Fecha_Traslado
                hbl_ci['Fecha_Pre_Cita'] = hbl.Inventario.Fecha_Pre_Cita
                hbl_ci['Fecha_Entrega'] = hbl.Inventario.Fecha_Entrega
                hbl_ci['Fecha_Salida_Inventario'] = hbl.Inventario.Fecha_Devolución
                hbl_ci['Fecha_No_Localizable'] = hbl.Inventario.Fecha_No_Localizable
                if not hbl_ci in lista_inventarios: 
                    lista_inventarios.append(hbl_ci)
            response['lista_inventarios']=lista_inventarios

        return Response(response)
