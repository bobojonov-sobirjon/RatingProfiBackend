# area_of_object: CharField -> JSONField (list), like speed_of_execution

from django.db import migrations, models


def convert_area_of_object(apps, schema_editor):
    """DesignerQuestionnaire: area_of_object CharField -> list"""
    DesignerQuestionnaire = apps.get_model('accounts', 'DesignerQuestionnaire')
    for obj in DesignerQuestionnaire.objects.all():
        v = getattr(obj, 'area_of_object', None)
        new_val = [v] if v and str(v).strip() else []
        DesignerQuestionnaire.objects.filter(pk=obj.pk).update(area_of_object_new=new_val)


def reverse_area(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0034_delivery_terms_speed_of_execution_jsonfield'),
    ]

    operations = [
        migrations.AddField(
            model_name='designerquestionnaire',
            name='area_of_object_new',
            field=models.JSONField(blank=True, default=list, verbose_name='Площадь объекта'),
        ),
        migrations.RunPython(convert_area_of_object, reverse_area),
        migrations.RemoveField(model_name='designerquestionnaire', name='area_of_object'),
        migrations.RenameField(
            model_name='designerquestionnaire',
            old_name='area_of_object_new',
            new_name='area_of_object',
        ),
    ]
