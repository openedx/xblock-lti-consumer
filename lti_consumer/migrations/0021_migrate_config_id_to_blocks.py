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

    LtiAgsLineItem = apps.get_model("lti_consumer", "LtiAgsLineItem")
    for line_item in LtiAgsLineItem.objects.all():
        xblock_config = LtiXBlockConfig.objects.filter(
            lti_configuration=line_item.lti_configuration,
            location=line_item.lti_configuration.location,
        ).first()
        if not xblock_config:
            print(f"Invalid configuration linked to AGS line item: {line_item}.")
        line_item.xblock_config = xblock_config
        line_item.save()

    LtiDlContentItem = apps.get_model("lti_consumer", "LtiDlContentItem")
    for content_item in LtiDlContentItem.objects.all():
        xblock_config = LtiXBlockConfig.objects.filter(
            lti_configuration=content_item.lti_configuration,
            location=content_item.lti_configuration.location,
        ).first()
        if not xblock_config:
            print(f"Invalid configuration linked to Dl Conent Item: {content_item}.")
        content_item.xblock_config = xblock_config
        content_item.save()


def backwards(apps, schema_editor):
    """Reverse the migration only for MariaDB databases."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('lti_consumer', '0020_ltixblockconfig_ltiagslineitem_lti_xblock_config_and_more'),
    ]

    operations = [
        migrations.RunPython(
            code=copy_config_id,
            reverse_code=backwards,
        ),
    ]
