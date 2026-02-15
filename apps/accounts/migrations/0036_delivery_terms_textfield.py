# delivery_terms: JSONField (list) -> TextField (string), oldingi holatiga qaytarish

from django.db import migrations, models


def convert_delivery_terms_to_string(apps, schema_editor):
    """JSONField list -> TextField string"""
    SupplierQuestionnaire = apps.get_model('accounts', 'SupplierQuestionnaire')
    for obj in SupplierQuestionnaire.objects.all():
        val = getattr(obj, 'delivery_terms', None)
        if isinstance(val, list):
            str_val = ', '.join(str(x).strip() for x in val if x) if val else ''
        else:
            str_val = str(val).strip() if val else ''
        SupplierQuestionnaire.objects.filter(pk=obj.pk).update(delivery_terms_new=str_val or None)


def reverse_convert(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0035_area_of_object_jsonfield'),
    ]

    operations = [
        migrations.AddField(
            model_name='supplierquestionnaire',
            name='delivery_terms_new',
            field=models.TextField(blank=True, null=True, verbose_name='Сроки поставки и формат работы'),
        ),
        migrations.RunPython(convert_delivery_terms_to_string, reverse_convert),
        migrations.RemoveField(model_name='supplierquestionnaire', name='delivery_terms'),
        migrations.RenameField(
            model_name='supplierquestionnaire',
            old_name='delivery_terms_new',
            new_name='delivery_terms',
        ),
    ]
