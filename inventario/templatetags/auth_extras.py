from django import template
from django.contrib.auth.models import Group, Permission

register = template.Library()

@register.filter(name='has_group')
def has_group(user, group_name): 
    group = Group.objects.get(name=group_name) 
    return True if group in user.groups.all() else False

@register.filter(name='permisos')
def permisos(id_user): 
    permissions = Permission.objects.filter(user__id=id_user)
    x = []
    for y in permissions:
        x.append(y.name)
    return x 
   