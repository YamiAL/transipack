import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class NumberValidator(object):
    def validate(self, password, user=None):
        if not re.findall(r'\d', password):
            raise ValidationError(
                _("Su contraseña debe contener al menos 1 dígito del 1 al 9."),
                code='password_no_number',
            )

    def get_help_text(self):
        return _(
            "Su contraseña debe contener al menos 1 dígito del 1 al 9."
        )


class UppercaseValidator(object):
    def validate(self, password, user=None):
        if not re.findall(r'[A-Z]', password):
            raise ValidationError(
                _("Su contraseña debe contener al menos 1 letra mayúscula."),
                code='password_no_upper',
            )

    def get_help_text(self):
        return _(
            "Su contraseña debe contener al menos 1 letra mayúscula."
        )


class SymbolValidator(object):
    def validate(self, password, user=None):
        if not re.findall(r'[()[\]{}|\\`~!@#$%^&*_\-+=;:\'",<>./?]', password):
            raise ValidationError(
                _("Su contraseña debe contener al menos 1 caracter especial: " +
                  "()[]{}|\\`~!@#$%^&*_-+=;:'\",<>./?"),
                code='password_no_symbol',
            )

    def get_help_text(self):
        return _(
            "Su contraseña debe contener al menos 1 caracter especial: " +
            "()[]{}|\\`~!@#$%^&*_-+=;:'\",<>./?"
        )
