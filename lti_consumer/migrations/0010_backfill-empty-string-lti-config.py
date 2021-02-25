"""
Backfill empty lti_config records

We need to do this with raw SQL,
otherwise the model fails upon instantiation,
as the empty string is an invalid JSON dictionary.
"""
import uuid

from django.db import connection
from django.db import migrations


sql_forward = """\
UPDATE
    lti_consumer_lticonfiguration
SET
    lti_config = %s
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
    lti_config = ""
;\
"""


def _get_ids_with_empty_lti_config():
    """
    Retrieve the list of primary keys for each entry with a blank lti_config
    """
    with connection.cursor() as cursor:
        cursor.execute(sql_select_empty)
        for row in cursor.fetchall():
            yield row[0]


def _forward(apps, schema_editor):
    """
    Generate an empty JSON dict for rows missing one
    """
    for _id in _get_ids_with_empty_lti_config():
        lti_config = '{}'
        schema_editor.execute(sql_forward, [
            lti_config,
            _id,
        ])


class Migration(migrations.Migration):
    """
    Backfill empty lti_config records
    """

    dependencies = [
        ('lti_consumer', '0009_backfill-empty-string-config-id'),
    ]

    operations = [
        migrations.RunPython(_forward, atomic=False),
    ]
