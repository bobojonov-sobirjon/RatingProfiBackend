# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0030_change_magazine_cards_to_jsonfield'),
    ]

    operations = [
        # DesignerQuestionnaire
        migrations.AddField(
            model_name='designerquestionnaire',
            name='categories',
            field=models.JSONField(blank=True, default=list, verbose_name='Категории'),
        ),
        migrations.AddField(
            model_name='designerquestionnaire',
            name='purpose_of_property',
            field=models.JSONField(blank=True, default=list, verbose_name='Назначение недвижимости'),
        ),
        migrations.AddField(
            model_name='designerquestionnaire',
            name='area_of_object',
            field=models.IntegerField(blank=True, null=True, verbose_name='Площадь объекта (м²)'),
        ),
        migrations.AddField(
            model_name='designerquestionnaire',
            name='cost_per_m2',
            field=models.IntegerField(blank=True, null=True, verbose_name='Стоимость за м² (руб)'),
        ),
        migrations.AddField(
            model_name='designerquestionnaire',
            name='experience',
            field=models.IntegerField(
                blank=True,
                null=True,
                choices=[(0, 'Новичок'), (1, 'До 2 лет'), (2, '2-5 лет'), (3, '5-10 лет'), (4, 'Свыше 10 лет')],
                verbose_name='Опыт работы',
            ),
        ),
        # RepairQuestionnaire
        migrations.AddField(
            model_name='repairquestionnaire',
            name='categories',
            field=models.JSONField(blank=True, default=list, verbose_name='Категории'),
        ),
        migrations.AddField(
            model_name='repairquestionnaire',
            name='speed_of_execution',
            field=models.CharField(
                blank=True,
                choices=[
                    ('advance_booking', 'Предварительная запись'),
                    ('quick_start', 'Быстрый старт'),
                    ('not_important', 'Не важно'),
                ],
                max_length=30,
                null=True,
                verbose_name='Скорость исполнения',
            ),
        ),
        # SupplierQuestionnaire
        migrations.AddField(
            model_name='supplierquestionnaire',
            name='categories',
            field=models.JSONField(blank=True, default=list, verbose_name='Категории'),
        ),
        migrations.AddField(
            model_name='supplierquestionnaire',
            name='speed_of_execution',
            field=models.CharField(
                blank=True,
                choices=[
                    ('in_stock', 'В наличии'),
                    ('up_to_2_weeks', 'До 2х недель'),
                    ('up_to_1_month', 'До 1 месяца'),
                    ('up_to_3_months', 'До 3х месяцев'),
                    ('not_important', 'Не важно'),
                ],
                max_length=30,
                null=True,
                verbose_name='Скорость исполнения'),
        ),
    ]
