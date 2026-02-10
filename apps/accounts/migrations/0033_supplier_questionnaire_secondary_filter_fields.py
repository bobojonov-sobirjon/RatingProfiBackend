# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0032_designer_questionnaire_string_choices'),
    ]

    operations = [
        migrations.AddField(
            model_name='supplierquestionnaire',
            name='rough_materials',
            field=models.JSONField(blank=True, default=list, null=True, verbose_name='Черновые материалы'),
        ),
        migrations.AddField(
            model_name='supplierquestionnaire',
            name='finishing_materials',
            field=models.JSONField(blank=True, default=list, null=True, verbose_name='Чистовые материалы'),
        ),
        migrations.AddField(
            model_name='supplierquestionnaire',
            name='upholstered_furniture',
            field=models.JSONField(blank=True, default=list, null=True, verbose_name='Мягкая мебель'),
        ),
        migrations.AddField(
            model_name='supplierquestionnaire',
            name='cabinet_furniture',
            field=models.JSONField(blank=True, default=list, null=True, verbose_name='Корпусная мебель'),
        ),
        migrations.AddField(
            model_name='supplierquestionnaire',
            name='technique',
            field=models.JSONField(blank=True, default=list, null=True, verbose_name='Техника'),
        ),
        migrations.AddField(
            model_name='supplierquestionnaire',
            name='decor',
            field=models.JSONField(blank=True, default=list, null=True, verbose_name='Декор'),
        ),
    ]
