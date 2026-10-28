"""Focused tests for reusable configuration storage: one table, one identity."""

import uuid

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.db import IntegrityError, transaction
from django.test import TestCase

from lti_consumer.models import Lti1p3Passport, LtiConfiguration, ReusableLtiConfiguration

COURSE_KEY = 'course-v1:Org+Course+Run'


class ReusableConfigurationStorageTests(TestCase):
    """DB contracts the API journeys cannot exercise: schema, constraints and the binding."""

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

    def test_one_model_owns_the_passport_table(self):
        owning_models = [
            model for model in apps.get_app_config('lti_consumer').get_models()
            if model._meta.db_table == 'lti_consumer_reusablelticonfiguration'
        ]
        self.assertEqual(owning_models, [ReusableLtiConfiguration])
        # The old name survives as a source-level alias only, not as a second model.
        self.assertIs(Lti1p3Passport, ReusableLtiConfiguration)

    def test_passport_id_is_the_only_stored_identity(self):
        configuration = self.make_configuration()
        self.assertEqual(configuration.config_id, configuration.passport_id)
        self.assertEqual(
            ReusableLtiConfiguration.objects.get(passport_id=configuration.passport_id).pk,
            configuration.pk,
        )
        with self.assertRaises(FieldDoesNotExist):
            ReusableLtiConfiguration._meta.get_field('config_id')
        self.assertNotIn('config_id', {field.name for field in ReusableLtiConfiguration._meta.local_fields})

    def test_unassigned_context_is_allowed_and_invalid_shapes_are_rejected(self):
        unassigned = self.make_configuration(name='Unassigned', context_type=None, context_key=None)
        self.assertIsNone(unassigned.context_type)
        self.assertIsNone(unassigned.context_key)

        invalid = (
            {'context_type': 'library', 'context_key': 'lib'},
            {'context_type': 'course', 'context_key': ''},
            {'context_type': 'course', 'context_key': None},
            {'context_type': 'organization', 'context_key': ''},
            {'context_type': 'site', 'context_key': 'nonblank'},
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(IntegrityError), transaction.atomic():
                self.make_configuration(
                    name=f"Invalid {values['context_type']} {values['context_key']}", **values,
                )

    def test_normalized_name_is_not_unique_and_tolerates_missing_names(self):
        self.make_configuration(name='Café Tool')
        self.make_configuration(name='Cafe Tool')
        self.assertEqual(
            set(ReusableLtiConfiguration.objects.values_list('normalized_name', flat=True)),
            {'café tool', 'cafe tool'},
        )
        duplicate = self.make_configuration(name='  CAFÉ TOOL  ')
        self.assertEqual(duplicate.normalized_name, 'café tool')
        unnamed = self.make_configuration(name=None)
        self.assertIsNone(unnamed.normalized_name)
        self.assertEqual(ReusableLtiConfiguration.objects.filter(normalized_name='café tool').count(), 2)

    def test_legacy_client_id_values_stay_nullable_and_non_unique(self):
        self.make_configuration(name='No identity', lti_1p3_client_id=None)
        self.make_configuration(name='Client identity 1', lti_1p3_client_id='Client-A')
        self.make_configuration(name='Client identity duplicate', lti_1p3_client_id='Client-A')
        self.assertEqual(ReusableLtiConfiguration.objects.filter(lti_1p3_client_id='Client-A').count(), 2)
        self.assertEqual(ReusableLtiConfiguration.objects.filter(lti_1p3_client_id__isnull=True).count(), 1)

    def test_existing_placement_fk_is_the_binding(self):
        configuration = self.make_configuration(name='Bound', version=ReusableLtiConfiguration.LTI_1P3)
        placement = LtiConfiguration.objects.create(
            config_id=uuid.uuid4(),
            version='lti_1p3',
            config_store='CONFIG_ON_DB',
            lti_1p3_passport=configuration,
        )
        self.assertEqual(placement.lti_1p3_passport, configuration)
        self.assertEqual(placement.lti_1p3_passport_id, configuration.pk)
        self.assertEqual(list(configuration.lticonfiguration_set.all()), [placement])

    def test_reads_never_generate_signing_keys(self):
        configuration = self.make_configuration(name='No keys', version=ReusableLtiConfiguration.LTI_1P3)
        list(ReusableLtiConfiguration.objects.filter(pk=configuration.pk))
        configuration.refresh_from_db()
        self.assertEqual(configuration.lti_1p3_internal_private_key, '')
        self.assertEqual(configuration.lti_1p3_internal_public_jwk, '')
        self.assertEqual(configuration.lti_1p3_internal_private_key_id, '')
