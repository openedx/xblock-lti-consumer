"""
Storage contracts for the reusable-configuration table and its placement binding.

These are DB-level journeys: the promises are enforced by the schema itself, not by
services or views, so they are exercised against the real database.
"""

from django.core.exceptions import FieldDoesNotExist
from django.db import IntegrityError, connection, models, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from lti_consumer.models import Lti1p3Passport, LtiConfiguration, ReusableLtiConfiguration

COURSE_KEY = 'course-v1:Org+Course+Run'


class ReusableConfigurationStorageTests(TestCase):
    """Schema, identity and binding contracts of the new reusable-configuration table."""

    def make_configuration(self, **kwargs):
        """Create a configuration row directly, bypassing any service validation."""
        values = {
            'name': 'Storage test',
            'version': ReusableLtiConfiguration.LTI_1P3,
            'context_type': 'course',
            'context_key': COURSE_KEY,
        }
        values.update(kwargs)
        return ReusableLtiConfiguration.objects.create(**values)

    def test_it_is_a_table_separate_from_the_retained_passport(self):
        self.assertNotEqual(
            ReusableLtiConfiguration._meta.db_table,
            Lti1p3Passport._meta.db_table,
        )
        passport = Lti1p3Passport.objects.create(name='Retained', lti_1p3_tool_public_key='key')
        self.make_configuration(name='New table')
        self.assertTrue(Lti1p3Passport.objects.filter(pk=passport.pk).exists())

    def test_passport_id_is_the_only_store_enforced_identity(self):
        configuration = self.make_configuration()
        self.assertEqual(
            ReusableLtiConfiguration.objects.get(passport_id=configuration.passport_id).pk,
            configuration.pk,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_configuration(name='Duplicate identity', passport_id=configuration.passport_id)

        unique_fields = {
            field.name for field in ReusableLtiConfiguration._meta.local_fields
            if field.unique and not field.primary_key
        }
        self.assertEqual(unique_fields, {'passport_id'})
        self.assertEqual(ReusableLtiConfiguration._meta.unique_together, ())
        with self.assertRaises(FieldDoesNotExist):
            ReusableLtiConfiguration._meta.get_field('config_id')

    def test_duplicate_names_and_client_ids_stay_allowed(self):
        """Legacy rows keep duplicate, blank and NULL names and client ids."""
        for name in ('Café Tool', 'Café Tool', '', None):
            self.make_configuration(name=name)

        self.make_configuration(name='No client', lti_1p3_client_id=None)
        self.make_configuration(name='Client 1', lti_1p3_client_id='Client-A')
        self.make_configuration(name='Client duplicate', lti_1p3_client_id='Client-A')

        self.assertEqual(ReusableLtiConfiguration.objects.filter(name='Café Tool').count(), 2)
        self.assertEqual(ReusableLtiConfiguration.objects.filter(lti_1p3_client_id='Client-A').count(), 2)
        self.assertEqual(
            ReusableLtiConfiguration.objects.filter(lti_1p3_client_id__isnull=True).count(),
            1,
        )

    def test_context_shape_constraints_accept_legacy_nulls_and_reject_invalid_shapes(self):
        unassigned = self.make_configuration(name='Unassigned', context_type=None, context_key=None)
        self.assertIsNone(unassigned.context_type)
        self.assertIsNone(unassigned.context_key)
        self.make_configuration(name='Site', context_type='site', context_key='')

        invalid = (
            {'context_type': 'library', 'context_key': 'lib'},
            {'context_type': 'course', 'context_key': ''},
            {'context_type': 'course', 'context_key': None},
            {'context_type': 'organization', 'context_key': ''},
            {'context_type': 'site', 'context_key': 'nonblank'},
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(IntegrityError), transaction.atomic():
                self.make_configuration(name=f"Invalid {values['context_type']}", **values)

    def test_names_use_backend_native_collation(self):
        """No collation override is declared; comparison follows the table's native collation."""
        for field_name in ('name', 'context_key'):
            field = ReusableLtiConfiguration._meta.get_field(field_name)
            with self.subTest(field=field_name):
                self.assertIsNone(field.db_parameters(connection).get('collation'))

        table = ReusableLtiConfiguration._meta.db_table
        if connection.vendor == 'mysql':
            # MySQL/MariaDB: the columns must take the table's own default collation, not one
            # inherited from the connection or forced by the model.
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT TABLE_COLLATION FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
                    [table],
                )
                table_collation = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT COLUMN_NAME, COLLATION_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s "
                    "AND COLUMN_NAME IN ('name', 'context_key')",
                    [table],
                )
                column_collations = dict(cursor.fetchall())
            self.assertEqual(
                column_collations,
                {'name': table_collation, 'context_key': table_collation},
            )

        self.make_configuration(name='Cafe Tool')
        self.make_configuration(name='Café Tool')
        # Grouping uses the column's own collation, so it settles what equality must return.
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(DISTINCT name) FROM {connection.ops.quote_name(table)}")
            distinct_names = cursor.fetchone()[0]
        expected_matches = 2 if distinct_names == 1 else 1
        self.assertEqual(ReusableLtiConfiguration.objects.filter(name='Cafe Tool').count(), expected_matches)

    def test_placement_binding_targets_the_automatic_primary_key_with_protect(self):
        field = LtiConfiguration._meta.get_field('reusable_configuration')
        self.assertIs(field.remote_field.model, ReusableLtiConfiguration)
        self.assertIs(field.remote_field.on_delete, models.PROTECT)
        self.assertTrue(field.null)
        self.assertTrue(field.blank)
        self.assertEqual(field.remote_field.field_name, 'id')
        self.assertEqual(field.target_field.name, 'id')
        self.assertEqual(field.attname, 'reusable_configuration_id')

        configuration = self.make_configuration(name='Bound')
        placement = LtiConfiguration.objects.create(reusable_configuration=configuration)
        placement.refresh_from_db()
        self.assertEqual(placement.reusable_configuration_id, configuration.pk)
        self.assertNotEqual(placement.reusable_configuration_id, configuration.passport_id)
        self.assertEqual(list(configuration.lticonfiguration_set.all()), [placement])

        with self.assertRaises(ProtectedError):
            configuration.delete()
        self.assertTrue(LtiConfiguration.objects.filter(pk=placement.pk).exists())

    def test_placements_stay_unbound_until_one_is_linked(self):
        placement = LtiConfiguration.objects.create()
        placement.refresh_from_db()
        self.assertIsNone(placement.reusable_configuration_id)

        configuration = self.make_configuration(name='Later link')
        LtiConfiguration.objects.filter(pk=placement.pk).update(reusable_configuration=configuration)
        placement.refresh_from_db()
        self.assertEqual(placement.reusable_configuration_id, configuration.pk)

    def test_reads_never_generate_signing_keys(self):
        configuration = self.make_configuration(name='No keys')
        list(ReusableLtiConfiguration.objects.filter(pk=configuration.pk))
        configuration.refresh_from_db()
        self.assertEqual(configuration.lti_1p3_internal_private_key, '')
        self.assertEqual(configuration.lti_1p3_internal_public_jwk, '')
        self.assertEqual(configuration.lti_1p3_internal_private_key_id, '')
