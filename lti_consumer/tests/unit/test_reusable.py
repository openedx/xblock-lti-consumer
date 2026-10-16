"""Focused unit tests for reusable configuration creation invariants.

Happy-path credential, UUID, and storage behavior is covered by the API
journeys; these tests protect direct service callers, the create transaction,
and the registry/collision policy.
"""

from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from lti_consumer.models import Lti1p3Passport, ReusableLtiConfiguration
from lti_consumer.reusable import create_reusable_configuration, validate_reusable_context

COURSE_KEY = 'course-v1:Org+Course+Run'
REGISTRY_PATCH = 'lti_consumer.plugin.compat.get_active_organizations'


class ReusableContextValidationTests(SimpleTestCase):
    """Direct service context normalization and organization registry policy."""

    def test_normalizes_contexts_and_rejects_invalid_or_ambiguous_keys(self):
        with patch(REGISTRY_PATCH, return_value=[{'short_name': 'MyOrg'}]):
            self.assertEqual(
                validate_reusable_context({'type': 'course', 'key': f'  {COURSE_KEY}+branch@draft  '}),
                {'type': 'course', 'key': COURSE_KEY},
            )
            self.assertEqual(
                validate_reusable_context({'type': 'course', 'key': 'ccx-v1:Org+Course+Run+ccx@1'}),
                {'type': 'course', 'key': 'ccx-v1:Org+Course+Run+ccx@1'},
            )
            self.assertEqual(
                validate_reusable_context({'type': 'organization', 'key': '  MYORG  '}),
                {'type': 'organization', 'key': 'myorg'},
            )
            self.assertEqual(validate_reusable_context({'type': 'site'}), {'type': 'site'})

        invalid = (
            None,
            {},
            {'type': 'course'},
            {'type': 'course', 'key': ''},
            {'type': 'course', 'key': 'library-v1:Org+Lib'},
            {'type': 'course', 'key': 'not-a-course-key'},
            {'type': 'organization'},
            {'type': 'organization', 'key': 'o' * 256},
            {'type': 'site', 'key': 'anything'},
            {'type': 'library', 'key': 'lib'},
            [{'type': 'site'}],
        )
        with patch(REGISTRY_PATCH, return_value=[{'short_name': 'Org'}, {'short_name': 'ORG'}]):
            for context in (*invalid, {'type': 'organization', 'key': 'org'}):
                with self.subTest(context=context), self.assertRaises(ValidationError):
                    validate_reusable_context(context)


class ReusableCreationTests(TestCase):
    """Service invariants that protect direct callers and the create transaction."""

    def lti11_input(self, **overrides):
        """Return a valid LTI 1.1 creation payload."""
        data = {
            'name': '  One One  ',
            'version': 'lti_1p1',
            'context': {'type': 'course', 'key': COURSE_KEY},
            'lti_1p1': {'launch_url': 'https://tool.example/launch'},
        }
        data.update(overrides)
        return data

    def lti13_input(self, **overrides):
        """Return a valid LTI 1.3 creation payload."""
        data = {
            'name': 'One Three',
            'version': 'lti_1p3',
            'context': {'type': 'site'},
            'lti_1p3': {
                'launch_url': 'https://tool.example/launch',
                'oidc_url': 'https://tool.example/oidc',
                'tool_key_mode': 'keyset_url',
                'tool_keyset_url': 'https://tool.example/jwks',
            },
        }
        data.update(overrides)
        return data

    def test_rejects_invalid_input_before_writing(self):
        invalid = (
            self.lti11_input(context={'type': 'course'}),
            self.lti11_input(version='lti_1p3'),
            self.lti11_input(lti_1p3={}),
            self.lti11_input(lti_1p1={'launch_url': ''}),
            self.lti13_input(lti_1p3={
                'launch_url': 'https://tool.example/launch',
                'oidc_url': 'https://tool.example/oidc',
                'tool_key_mode': 'unknown',
                'tool_public_key': 'key',
            }),
        )
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ValidationError):
                create_reusable_configuration(data)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 0)
        self.assertEqual(Lti1p3Passport.objects.count(), 0)

    def test_failure_after_configuration_write_rolls_back_passport_and_configuration(self):
        original_create = ReusableLtiConfiguration.objects.create

        def create_then_fail(*args, **kwargs):
            original_create(*args, **kwargs)
            raise RuntimeError('injected failure')

        with patch.object(ReusableLtiConfiguration.objects, 'create', side_effect=create_then_fail):
            with self.assertRaisesRegex(RuntimeError, 'injected failure'):
                create_reusable_configuration(self.lti13_input())
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 0)
        self.assertEqual(Lti1p3Passport.objects.count(), 0)

    def test_legacy_passport_client_collision_is_non_disclosing(self):
        Lti1p3Passport.objects.create(lti_1p3_client_id='legacy-client')
        data = self.lti13_input()
        data['lti_1p3']['client_id'] = 'legacy-client'
        with self.assertRaisesMessage(ValidationError, 'conflicts with an existing identity'):
            create_reusable_configuration(data)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 0)

    def test_duplicate_normalized_name_translates_integrity_error(self):
        create_reusable_configuration(self.lti11_input(name='Straße'))
        duplicate = self.lti11_input(name='STRASSE')
        with self.assertRaisesMessage(ValidationError, 'conflicts with an existing record'):
            create_reusable_configuration(duplicate)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 1)
