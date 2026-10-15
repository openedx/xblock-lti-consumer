"""Focused tests for version-specific reusable configuration storage."""

from unittest.mock import patch

from django.db import IntegrityError, connections, transaction
from django.test import TestCase

from lti_consumer.models import Lti1p3Passport, ReusableLtiConfiguration


class ReusableConfigurationStorageTests(TestCase):
    def make_configuration(self, **kwargs):
        values = {
            'name': 'Storage test',
            'version': ReusableLtiConfiguration.LTI_1P1,
        }
        values.update(kwargs)
        return ReusableLtiConfiguration.objects.create(**values)

    def test_version_specific_fields_allow_absent_values(self):
        configuration = self.make_configuration()
        for field_name in (
            'lti_1p1_launch_url', 'lti_1p1_client_key', 'lti_1p1_client_secret',
            'lti_1p3_launch_url', 'lti_1p3_oidc_url', 'lti_1p3_client_id',
            'lti_1p3_deployment_id', 'lti_1p3_tool_key_mode', 'lti_1p3_passport',
        ):
            self.assertIsNone(getattr(configuration, f'{field_name}_id', None) if field_name.endswith('passport')
                              else getattr(configuration, field_name))

        self.assertEqual(configuration.lti_1p3_redirect_uris, [])

    def test_normalized_name_distinguishes_accents_but_not_case_or_surrounding_space(self):
        self.make_configuration(name='Café Tool')
        self.make_configuration(name='Cafe Tool')
        self.assertEqual(
            set(ReusableLtiConfiguration.objects.values_list('normalized_name', flat=True)),
            {'café tool', 'cafe tool'},
        )
        for duplicate in ('CAFÉ TOOL', '  Cafe Tool  ', '  café tool  '):
            with self.subTest(duplicate=duplicate), self.assertRaises(IntegrityError), transaction.atomic():
                self.make_configuration(name=duplicate)

    def test_mysql_normalized_name_uses_accent_sensitive_collation(self):
        connection = connections['default']
        if connection.vendor != 'mysql' or getattr(connection, 'mysql_is_mariadb', False):
            self.skipTest('MySQL 8-only collation check.')
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COLLATION_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'lti_consumer_reusablelticonfiguration' "
                "AND COLUMN_NAME = 'normalized_name'"
            )
            self.assertEqual(cursor.fetchone(), ('utf8mb4_0900_as_ci',))

    def test_db_parameters_collation_is_mysql_only(self):
        field = ReusableLtiConfiguration._meta.get_field('normalized_name')
        connection = connections['default']
        for vendor, is_mariadb, expected in (
            ('mysql', False, 'utf8mb4_0900_as_ci'),
            ('mysql', True, None),
            ('sqlite', False, None),
        ):
            with self.subTest(vendor=vendor, mariadb=is_mariadb), \
                    patch.object(connection, 'vendor', vendor), \
                    patch.object(connection, 'mysql_is_mariadb', is_mariadb, create=True):
                self.assertEqual(field.db_parameters(connection)['collation'], expected)

    def test_lti13_client_id_is_unique_but_nullable(self):
        self.make_configuration(name='No identity 1', lti_1p3_client_id=None)
        self.make_configuration(name='No identity 2', lti_1p3_client_id=None)
        self.make_configuration(name='Client identity 1', lti_1p3_client_id='Client-A')
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_configuration(name='Client identity duplicate', lti_1p3_client_id='Client-A')

    def test_passport_is_one_to_one_and_protected(self):
        passport = Lti1p3Passport.objects.create(lti_1p3_client_id='passport-client')
        configuration = self.make_configuration(
            name='Bound configuration',
            lti_1p3_passport=passport,
        )
        self.assertEqual(configuration.lti_1p3_passport, passport)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_configuration(name='Second binding', lti_1p3_passport=passport)
        with self.assertRaises(IntegrityError), transaction.atomic():
            passport.delete()

    def test_service_and_placement_defaults_match_existing_xblock(self):
        configuration = self.make_configuration()
        self.assertFalse(configuration.lti_advantage_deep_linking_enabled)
        self.assertEqual(configuration.lti_advantage_deep_linking_launch_url, '')
        self.assertEqual(configuration.lti_advantage_ags_mode, 'declarative')
        self.assertFalse(configuration.lti_advantage_enable_nrps)
        self.assertEqual(configuration.display_name, 'LTI Consumer')
        self.assertFalse(configuration.enable_grading)
        self.assertEqual(configuration.grade_weight, 1.0)
        self.assertTrue(configuration.accept_grades_after_due_date)
        self.assertEqual(configuration.open_tool_in, 'iframe')
        self.assertEqual(configuration.inline_height, 800)
        self.assertEqual(configuration.modal_height, 80)
        self.assertEqual(configuration.modal_width, 80)
        self.assertEqual(configuration.launch_button_text, '')
        self.assertFalse(configuration.send_extra_parameters)
        self.assertEqual(configuration.custom_parameters, [])
