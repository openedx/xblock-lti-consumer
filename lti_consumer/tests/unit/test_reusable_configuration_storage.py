"""Focused tests for version-specific reusable configuration storage."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from lti_consumer.models import Lti1p3Passport, ReusableLtiConfiguration

COURSE_KEY = 'course-v1:Org+Course+Run'


class ReusableConfigurationStorageTests(TestCase):
    """Column, constraint, and default behavior of the reusable configuration model."""

    def make_configuration(self, **kwargs):
        """Create a configuration row directly, bypassing service validation."""
        values = {
            'name': 'Storage test',
            'version': ReusableLtiConfiguration.LTI_1P1,
            'context_type': 'course',
            'context_key': COURSE_KEY,
        }
        values.update(kwargs)
        return ReusableLtiConfiguration.objects.create(**values)

    def test_context_columns_store_supported_shapes(self):
        course = self.make_configuration(name='Course context')
        organization = self.make_configuration(
            name='Organization context', context_type='organization', context_key='org',
        )
        site = self.make_configuration(name='Site context', context_type='site', context_key='')
        self.assertEqual((course.context_type, course.context_key), ('course', COURSE_KEY))
        self.assertEqual((organization.context_type, organization.context_key), ('organization', 'org'))
        self.assertEqual((site.context_type, site.context_key), ('site', ''))

    def test_context_shape_constraints_reject_invalid_shapes(self):
        invalid = (
            {'context_type': 'library', 'context_key': 'lib'},
            {'context_type': 'course', 'context_key': ''},
            {'context_type': 'organization', 'context_key': ''},
            {'context_type': 'site', 'context_key': 'nonblank'},
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(IntegrityError), transaction.atomic():
                self.make_configuration(
                    name=f"Invalid {values['context_type']} {values['context_key']}", **values,
                )

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
