from django.forms import ModelMultipleChoiceField

class UserModelChoiceField(ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        data = {}
        data['Manifiesto'] = obj.Manifiesto
        data['HBL'] = obj.HBL
        return obj.HBL