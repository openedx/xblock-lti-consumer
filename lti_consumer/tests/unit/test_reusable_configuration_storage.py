"""Focused tests for version-specific reusable configuration storage."""

from django.db import IntegrityError, connection, transaction
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

    def test_lti13_client_id_is_unique_but_nullable(self):
        self.make_configuration(name='No identity 1', lti_1p3_client_id=None)
        self.make_configuration(name='No identity 2', lti_1p3_client_id=None)
        self.make_configuration(name='Client identity 1', lti_1p3_client_id='Client-A')
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_configuration(name='Client identity duplicate', lti_1p3_client_id='Client-A')
        self.make_configuration(name='Case distinct client', lti_1p3_client_id='client-a')

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

    def test_storage_columns_exist_in_database(self):
        with connection.cursor() as cursor:
            columns = {column.name for column in connection.introspection.get_table_description(
                cursor, ReusableLtiConfiguration._meta.db_table
            )}
        expected = {
            'lti_1p1_launch_url', 'lti_1p1_client_key', 'lti_1p1_client_secret',
            'lti_1p3_launch_url', 'lti_1p3_oidc_url', 'lti_1p3_redirect_uris',
            'lti_1p3_client_id', 'lti_1p3_deployment_id', 'lti_1p3_tool_key_mode',
            'lti_1p3_passport_id',
            'lti_advantage_deep_linking_enabled', 'lti_advantage_deep_linking_launch_url',
            'lti_advantage_ags_mode', 'lti_advantage_enable_nrps', 'display_name',
            'enable_grading', 'grade_weight', 'accept_grades_after_due_date', 'open_tool_in',
            'inline_height', 'modal_height', 'modal_width', 'launch_button_text',
            'send_extra_parameters', 'custom_parameters',
        }
        self.assertTrue(expected.issubset(columns))
