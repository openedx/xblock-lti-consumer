# Generated migration for copying config_id into modulestore from database (Django 5.2)
"""
This migration will copy config_id from LtiConsumer database to LtiConsumerXBlock.

This will help us link xblocks with LtiConsumer database rows without relying on the location or usage_key of xblocks.
"""
from django.db import migrations


def copy_config_id(apps, schema_editor):
    """Copy config_id from LtiConsumer to LtiConsumerXBlock."""
    from lti_consumer.plugin.compat import load_enough_xblock, save_xblock

    LtiConfiguration = apps.get_model("lti_consumer", "LtiConfiguration")
    LtiXBlockConfig = apps.get_model("lti_consumer", "LtiXBlockConfig")

    for configuration in LtiConfiguration.objects.all():
        LtiXBlockConfig.objects.update_or_create(
            location=configuration.location,
            defaults={
                "lti_configuration": configuration,
            }
        )
        try:
            blockstore = load_enough_xblock(configuration.location)
            blockstore.config_id = str(configuration.config_id)
            blockstore.save()
            save_xblock(blockstore)
        except Exception as e:
            print(f"Failed to copy config_id for configuration {configuration}: {e}")


def backwards(apps, schema_editor):
    """Reverse the migration only for MariaDB databases."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('lti_consumer', '0020_ltixblockconfig'),
    ]

    operations = [
        migrations.RunPython(
            code=copy_config_id,
            reverse_code=backwards,
        ),
    ]
