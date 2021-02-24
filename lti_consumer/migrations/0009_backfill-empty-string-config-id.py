"""
Backfill empty config_id records

We need to do this with raw SQL,
otherwise the model fails upon instantiation,
as the empty string is an invalid UUID.
"""
import uuid

from django.db import connection
from django.db import migrations


sql_forward = """\
UPDATE
    lti_consumer_lticonfiguration
SET
    config_id = %s
WHERE
    id = %s
;\
"""

sql_select_empty = """\
SELECT
    id
FROM
    lti_consumer_lticonfiguration
WHERE
    config_id = ""
;\
"""


def _get_ids_with_empty_uuid():
    """
    Retrieve the list of primary keys for each entry with a blank config_id
    """
    with connection.cursor() as cursor:
        cursor.execute(sql_select_empty)
        for row in cursor.fetchall():
            yield row[0]


def _create_config_ids(apps, schema_editor):
    """
    Generate a UUID for rows missing one

    Note: The model stores these without hyphens.
    """
    for _id in _get_ids_with_empty_uuid():
        config_id = uuid.uuid4()
        config_id = str(config_id)
        config_id = config_id.replace('-', '')
        schema_editor.execute(sql_forward, [
            config_id,
            _id,
        ])


class Migration(migrations.Migration):
    """
    Backfill empty config_id records
    """

    dependencies = [
        ('lti_consumer', '0008_fix_uuid_backfill'),
    ]

    operations = [
        migrations.RunPython(_create_config_ids, atomic=False),
    ]
