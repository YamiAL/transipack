from django import template

register = template.Library()

@register.filter
def delete_underscore(value):
    return value.replace("_", " ").replace("/", " ")