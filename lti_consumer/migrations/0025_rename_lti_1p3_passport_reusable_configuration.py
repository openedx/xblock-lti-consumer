"""Rename the placement's passport reference to the reusable configuration.

The column is renamed in place: every placement keeps the configuration it was
already bound to, and the foreign key keeps its PROTECT behaviour.
"""
from django.db import migrations


class Migration(migrations.Migration):
    """Rename only the placement foreign key; no row is rewritten."""

    dependencies = [
        ('lti_consumer', '0024_reusable_lti_configuration'),
    ]

    operations = [
        migrations.RenameField(
            model_name='lticonfiguration',
            old_name='lti_1p3_passport',
            new_name='reusable_configuration',
        ),
    ]
