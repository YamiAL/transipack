from django.urls import path
from . import views

urlpatterns = [
    path('hbl/', views.TrackingApiView.as_view()),
    path('obtener-hbl/HBL/CI', views.TrackingApiHBLCIView.as_view()),
]