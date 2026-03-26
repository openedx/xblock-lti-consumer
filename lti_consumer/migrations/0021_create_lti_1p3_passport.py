# Generated migration for copying config_id into modulestore from database (Django 6.2)
"""
This migration will copy config_id from LtiConsumer database to LtiConsumerXBlock.

This will help us link xblocks with LtiConsumer database rows without relying on the location or usage_key of xblocks.
"""
from django.db import migrations


def create_lti_1p3_passport(apps, _):  # pragma: nocover
    """Copy config_id from LtiConsumer to LtiConsumerXBlock."""
    from lti_consumer.plugin.compat import load_enough_xblock, save_xblock  # pylint: disable=import-outside-toplevel
    from lti_consumer.utils import model_to_dict  # pylint: disable=import-outside-toplevel

    LtiConfiguration = apps.get_model("lti_consumer", "LtiConfiguration")
    Lti1p3Passport = apps.get_model("lti_consumer", "Lti1p3Passport")

    for configuration in LtiConfiguration.objects.all():
        try:
            block = load_enough_xblock(configuration.location)
            block.lti_1p3_passport_id = str(configuration.config_id)
            block.save()
            save_xblock(block)
        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"Failed to copy passport_id for configuration {configuration}: {e}")
        values = model_to_dict(
            configuration,
            include=[
                'lti_1p3_internal_private_key',
                'lti_1p3_internal_private_key_id',
                'lti_1p3_internal_public_jwk',
                'lti_1p3_client_id',
                'lti_1p3_tool_public_key',
                'lti_1p3_tool_keyset_url',
            ],
        )
        if block.config_type == "new":
            # Data is stored xblock
            values.update({
                'lti_1p3_tool_public_key': block.lti_1p3_tool_public_key,
                'lti_1p3_tool_keyset_url': block.lti_1p3_tool_keyset_url,
            })
        passport, _ = Lti1p3Passport.objects.update_or_create(
            # Use config_id as passport_id to preserve existing urls that use it.
            passport_id=configuration.config_id,
            defaults=values,
        )
        configuration.lti_1p3_passport = passport
        configuration.save()


def backwards(*_):
    """Reverse the migration only for MariaDB databases."""


class Migration(migrations.Migration):

    dependencies = [
        ('lti_consumer', '0020_lti1p3passport_lticonfiguration_lti_1p3_passport'),
    ]

    operations = [
        migrations.RunPython(
            code=create_lti_1p3_passport,
            reverse_code=backwards,
        ),
    ]
