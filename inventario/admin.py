from django.contrib import admin
from django.contrib.admin.models import LogEntry
from .models import *
import csv
from django.http import HttpResponse
from import_export import resources
from import_export.admin import ImportExportModelAdmin


admin.site.site_header = 'Cubanacan Express'
admin.site.site_title = 'Administración'
admin.site.index_title = 'Panel de administración'

@admin.register(Operador)
class OperadorAdmin(admin.ModelAdmin):
    # to filter the resultes by users, content types and action flags
    list_filter = [
    ]

    # when searching the user will be able to search in both object_repr and change_message
    search_fields = [
        'object_repr',
        'change_message'
    ]

    list_display = [
        'Nombre',
    ]


@admin.register(Provincia)
class ProvinciaAdmin(admin.ModelAdmin):
    # to filter the resultes by users, content types and action flags
    list_filter = [
    ]

    # when searching the user will be able to search in both object_repr and change_message
    search_fields = [
        'object_repr',
        'change_message'
    ]

    list_display = [
        'Nombre',
    ]


@admin.register(Municipio)
class MunicipioAdmin(admin.ModelAdmin):
    # to filter the resultes by users, content types and action flags
    list_filter = [
        'Provincia'
    ]

    # when searching the user will be able to search in both object_repr and change_message
    search_fields = [
        'object_repr',
        'change_message'
    ]

    list_display = [
        'Nombre',
        'Provincia',
        'Importe_por_entrega',
        'Importe_por_trasbordo',
    ]


class ExportCsvMixin:
    def export_as_csv(self, request, queryset):

        meta = self.model._meta
        field_names = [field.name for field in meta.fields]

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename={}.csv'.format(meta)
        writer = csv.writer(response)

        writer.writerow(field_names)
        for obj in queryset:
            row = writer.writerow([getattr(obj, field) for field in field_names])

        return response

    export_as_csv.short_description = "Exportar datos seleccionados"


class ChapaInline(admin.TabularInline):
    model = Chapa

@admin.register(Transportista)
class TransportistaAdmin(admin.ModelAdmin, ExportCsvMixin):
    # to filter the resultes by users, content types and action flags
    list_filter = [
        'Tipo',
        'Empresa',
        'Activo',
    ]

    # when searching the user will be able to search in both object_repr and change_message
    search_fields = [
        'object_repr',
        'change_message'
    ]

    list_display = [
        'Nombre',
        'CI',
        # 'Chapa',
        'Tipo',
        'Empresa',
        'Activo',
    ]
    actions = ["export_as_csv"]
    inlines = [
        ChapaInline,
    ]
    fieldsets = (
        (None, {
            'classes': ('row',),
            'fields': ('Nombre','CI')
        }),
        (None, {
            'classes': ('row',),
            'fields': ('Tipo','Empresa','Activo')
        }),
    )


@admin.register(Almacen)
class AlmacenAdmin(admin.ModelAdmin):
    # to filter the resultes by users, content types and action flags
    list_filter = [
    ]

    # when searching the user will be able to search in both object_repr and change_message
    search_fields = [
        'object_repr',
        'change_message'
    ]

    list_display = [
        'Nombre',
    ]

@admin.register(Incidencia)
class IncidenciaAdmin(admin.ModelAdmin):
    # to filter the resultes by users, content types and action flags
    list_filter = [
    ]

    # when searching the user will be able to search in both object_repr and change_message
    search_fields = [
        'object_repr',
        'change_message'
    ]

    list_display = [
        'Tipo',
    ]


@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin,ExportCsvMixin):
    # to have a date-based drilldown navigation in the admin page
    date_hierarchy = 'action_time'

    # to filter the resultes by users, content types and action flags
    list_filter = [
        'user',
        'content_type',
        'action_flag'
    ]

    # when searching the user will be able to search in both object_repr and change_message
    search_fields = [
        'object_repr',
        'change_message'
    ]

    list_display = [
        'action_time',
        'user',
        'content_type',
        'action_flag',
    ]

    actions = ["export_as_csv"]

    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    # to filter the resultes by users, content types and action flags
    list_filter = [
    ]

    # when searching the user will be able to search in both object_repr and change_message
    search_fields = [
        'object_repr',
        'change_message'
    ]

    list_display = [
        'Nombre',
    ]


# @admin.register(Agencia)
# class AgenciaAdmin(admin.ModelAdmin):
#  # to filter the resultes by users, content types and action flags
#     list_filter = [
#     ]

#     # when searching the user will be able to search in both object_repr and change_message
#     search_fields = [
#         'object_repr',
#         'change_message'
#     ]

#     list_display = [
#         'Agencia',
#     ]


class Lugar_OperanInline(admin.TabularInline):
    model = Lugar_Operan

@admin.register(Agencia)
class AgenciaAdmin(admin.ModelAdmin, ExportCsvMixin):
 # to filter the resultes by users, content types and action flags
    list_filter = [
    ]

    # when searching the user will be able to search in both object_repr and change_message
    search_fields = [
        'object_repr',
        'change_message'
    ]

    list_display = [
        'Agencia',
    ]    
    inlines = [
        Lugar_OperanInline,
    ]
    fieldsets = (
        (None, {
            'classes': ('row',),
            'fields': ('Agencia','Pais')
        }),
        (None, {
            'classes': ('row',),
            'fields': ('Correo','Logo','Habilitada')
        }),
    )


@admin.register(Paises)
class PaisesAdmin(admin.ModelAdmin):
    list_filter = [
    ]
    list_display = [
        'pais',
    ]   




# class UserResource(resources.ModelResource):
#     class Meta:
#         model = User
#         fields = ('first_name', 'last_name', 'email')

# class UserAdmin(ExportCsvMixin):
#     resource_class = UserResource
#     pass

# admin.site.unregister(User)
# admin.site.register(User, UserAdmin)



# Register your models here.
#admin.site.register(Manifiesto)
#admin.site.register(Factura)
#admin.site.register(Entrega)
#admin.site.register(Inventario)