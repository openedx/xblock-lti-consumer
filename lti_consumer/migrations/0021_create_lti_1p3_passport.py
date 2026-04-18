# Generated migration for copying config_id to the LtiPassport table
"""
This migration will copy config_id from LtiConfiguration database to LtiPassport table.

This will help us link xblocks with LtiConsumer database rows without relying on the location or usage_key of xblocks.
"""
from django.db import migrations

FIELD_NAMES = [
    'lti_1p3_internal_private_key',
    'lti_1p3_internal_private_key_id',
    'lti_1p3_internal_public_jwk',
    'lti_1p3_client_id',
    'lti_1p3_tool_public_key',
    'lti_1p3_tool_keyset_url',
]


def create_lti_1p3_passport(apps, _):
    """
    Create a new LtiPassport entry for each existing LtiConfiguration

    We use the `config_id` of the existing LtiConfiguration as the `passport_id` for the newly
    created LtiPassort entries to maintain backwards compatability and to ensure urls built
    from LtiPassoport passport_ids continue to work for previously created LtiConfiguration
    which correspond to existing instances of the LTI Consumer XBlock.
    """
    from lti_consumer.plugin.compat import load_enough_xblock  # pylint: disable=import-outside-toplevel
    from lti_consumer.utils import model_to_dict  # pylint: disable=import-outside-toplevel

    LtiConfiguration = apps.get_model("lti_consumer", "LtiConfiguration")
    Lti1p3Passport = apps.get_model("lti_consumer", "Lti1p3Passport")

    for configuration in LtiConfiguration.objects.all():
        values = model_to_dict(
            configuration,
            include=FIELD_NAMES,
        )
        if configuration.location:
            try:
                block = load_enough_xblock(configuration.location)
                if block.config_type == "new":
                    # Data is stored on the xblock
                    values.update({
                        'lti_1p3_tool_public_key': block.lti_1p3_tool_public_key,
                        'lti_1p3_tool_keyset_url': block.lti_1p3_tool_keyset_url,
                    })
            except Exception as e:  # pylint: disable=broad-exception-caught
                print(f"Failed to load block for {configuration.location}: {e}")
        passport, _ = Lti1p3Passport.objects.update_or_create(
            # Use config_id as passport_id to preserve existing urls that use it.
            passport_id=configuration.config_id,
            defaults=values,
        )
        configuration.lti_1p3_passport = passport
        configuration.save()


def backwards(apps, _):
    """Copy LTI 1.3 passport data back to configuration fields before unapplying."""
    LtiConfiguration = apps.get_model("lti_consumer", "LtiConfiguration")

    for configuration in LtiConfiguration.objects.select_related("lti_1p3_passport").all():
        passport = configuration.lti_1p3_passport
        if not passport:
            continue

        for field_name in FIELD_NAMES:
            setattr(configuration, field_name, getattr(passport, field_name))

        # Use config_id as passport_id to preserve existing urls that use it.
        configuration.config_id = passport.passport_id

        configuration.save(update_fields=[*FIELD_NAMES, 'config_id'])


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
