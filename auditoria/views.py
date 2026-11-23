from django.shortcuts import render

# Create your views here.
from django.contrib.contenttypes.models import ContentType
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE, DELETION
from django.utils.encoding import force_str

def save_log(user, type_object, object_id, result, ACTION):
    content_type_object = ContentType.objects.all().filter(model = type_object).first()

    log = LogEntry.objects.create(
        user_id = user.id,
        content_type_id = content_type_object.id,
        object_id = object_id,
        object_repr = force_str(type_object),
        action_flag = ACTION,
        change_message = result
    )

    log.save()

def save_addition(user, type_object, object_id, result):
    save_log(user, type_object, object_id, result, ADDITION)

def save_edition(user, type_object, object_id, result):
    save_log(user, type_object, object_id, result, CHANGE)

def save_deletion(user, type_object, object_id, result):
    save_log(user, type_object, object_id, result, DELETION)