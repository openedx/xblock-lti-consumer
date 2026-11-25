"""
Storage contracts for the reusable-configuration table and its placement binding.

These are DB-level journeys: the promises are enforced by the schema itself, not by
services or views, so they are exercised against the real database.
"""

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from lti_consumer.models import LtiConfiguration, ReusableLtiConfiguration

COURSE_KEY = 'course-v1:Org+Course+Run'

#: The privacy/hide columns a copy takes as defaults and only local authoring changes.
PRIVACY_DEFAULTS = {
    'pii_share_username': False,
    'pii_share_full_name': False,
    'pii_share_email': False,
    'data_sharing_notice': '',
    'require_user_confirmation': True,
    'hide_external_tool': False,
}


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

    def test_legacy_name_and_client_id_values_stay_permissive(self):
        """Duplicate, blank and NULL legacy names and client ids persist."""
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

    def test_placement_binding_is_optional_targets_the_pk_and_protects_deletion(self):
        """Unbound by default, bound to the PK, and undeletable while in use."""
        placement = LtiConfiguration.objects.create()
        placement.refresh_from_db()
        self.assertIsNone(placement.reusable_configuration_id)

        configuration = self.make_configuration(name='Bound')
        LtiConfiguration.objects.filter(pk=placement.pk).update(reusable_configuration=configuration)
        placement.refresh_from_db()
        self.assertEqual(placement.reusable_configuration_id, configuration.pk)

        with self.assertRaises(ProtectedError):
            configuration.delete()
        placement.refresh_from_db()
        self.assertEqual(placement.reusable_configuration_id, configuration.pk)

    def test_privacy_columns_default_safely_and_reject_null(self):
        """A row defaults to the six safe values, and the database refuses NULL in each."""
        configuration = self.make_configuration()
        stored = ReusableLtiConfiguration.objects.get(pk=configuration.pk)
        self.assertEqual({field: getattr(stored, field) for field in PRIVACY_DEFAULTS}, PRIVACY_DEFAULTS)

        for field_name in PRIVACY_DEFAULTS:
            with self.subTest(field=field_name), self.assertRaises(IntegrityError), transaction.atomic():
                ReusableLtiConfiguration.objects.filter(pk=configuration.pk).update(**{field_name: None})
