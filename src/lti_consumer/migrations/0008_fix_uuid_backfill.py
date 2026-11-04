from django.db import migrations, models
import uuid


def create_config_ids(apps, schema_editor):
    LtiConfiguration = apps.get_model('lti_consumer', 'LtiConfiguration')
    broken = LtiConfiguration.objects.filter(config_id__isnull=True)
    for config in broken:
        config.config_id = uuid.uuid4()
        config.save()


class Migration(migrations.Migration):

    dependencies = [
        ('lti_consumer', '0007_ltidlcontentitem'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lticonfiguration',
            name='config_id',
            field=models.UUIDField(default=uuid.uuid4, editable=True, unique=True),
        ),
        migrations.RunPython(create_config_ids),
        migrations.AlterField(
            model_name='lticonfiguration',
            name='config_id',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
