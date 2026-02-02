# Generated manually: area_of_object, cost_per_m2, experience — IntegerField -> CharField (текстовие варианты)

from django.db import migrations, models


EXPERIENCE_INT_TO_STR = {
    0: 'Новичок',
    1: 'До 2 лет',
    2: '2-5 лет',
    3: '5-10 лет',
    4: 'Свыше 10 лет',
}

AREA_CHOICES = [
    ('до 10 м2', 'до 10 м2'),
    ('до 40 м 2', 'до 40 м 2'),
    ('до 80 м 2', 'до 80 м 2'),
    ('дома', 'дома'),
]
COST_CHOICES = [
    ('До 1500 р', 'До 1500 р'),
    ('до 2500р', 'до 2500р'),
    ('до 4000 р', 'до 4000 р'),
    ('свыше 4000 р', 'свыше 4000 р'),
]
EXPERIENCE_CHOICES = [
    ('Новичок', 'Новичок'),
    ('До 2 лет', 'До 2 лет'),
    ('2-5 лет', '2-5 лет'),
    ('5-10 лет', '5-10 лет'),
    ('Свыше 10 лет', 'Свыше 10 лет'),
]


def migrate_to_string_fields(apps, schema_editor):
    DesignerQuestionnaire = apps.get_model('accounts', 'DesignerQuestionnaire')
    for obj in DesignerQuestionnaire.objects.all():
        if obj.experience is not None and obj.experience in EXPERIENCE_INT_TO_STR:
            obj.experience_new = EXPERIENCE_INT_TO_STR[obj.experience]
        else:
            obj.experience_new = None
        obj.save(update_fields=['experience_new'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0031_add_questionnaire_filter_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='designerquestionnaire',
            name='area_of_object_new',
            field=models.CharField(
                blank=True, choices=AREA_CHOICES, max_length=50, null=True, verbose_name='Площадь объекта'
            ),
        ),
        migrations.AddField(
            model_name='designerquestionnaire',
            name='cost_per_m2_new',
            field=models.CharField(
                blank=True, choices=COST_CHOICES, max_length=50, null=True, verbose_name='Стоимость за м²'
            ),
        ),
        migrations.AddField(
            model_name='designerquestionnaire',
            name='experience_new',
            field=models.CharField(
                blank=True, choices=EXPERIENCE_CHOICES, max_length=50, null=True, verbose_name='Опыт работы'
            ),
        ),
        migrations.RunPython(migrate_to_string_fields, noop),
        migrations.RemoveField(model_name='designerquestionnaire', name='area_of_object'),
        migrations.RemoveField(model_name='designerquestionnaire', name='cost_per_m2'),
        migrations.RemoveField(model_name='designerquestionnaire', name='experience'),
        migrations.RenameField(model_name='designerquestionnaire', old_name='area_of_object_new', new_name='area_of_object'),
        migrations.RenameField(model_name='designerquestionnaire', old_name='cost_per_m2_new', new_name='cost_per_m2'),
        migrations.RenameField(model_name='designerquestionnaire', old_name='experience_new', new_name='experience'),
    ]
