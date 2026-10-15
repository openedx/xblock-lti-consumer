"""Focused tests for atomic reusable configuration creation and single-context handling."""

import uuid
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from lti_consumer.models import Lti1p3Passport, ReusableLtiConfiguration
from lti_consumer.reusable import create_reusable_configuration, validate_reusable_context

COURSE_KEY = 'course-v1:Org+Course+Run'


class ReusableContextValidationTests(TestCase):
    """Direct service validation and normalization of the single creation context."""

    def test_validate_reusable_context_normalizes_course_key_and_site(self):
        self.assertEqual(
            validate_reusable_context({'type': 'course', 'key': f'  {COURSE_KEY}+branch@draft  '}),
            {'type': 'course', 'key': COURSE_KEY},
        )
        self.assertEqual(
            validate_reusable_context({'type': 'course', 'key': 'ccx-v1:Org+Course+Run+ccx@1'}),
            {'type': 'course', 'key': 'ccx-v1:Org+Course+Run+ccx@1'},
        )
        self.assertEqual(validate_reusable_context({'type': 'site'}), {'type': 'site'})

    def test_validate_reusable_context_rejects_invalid_shapes(self):
        for context in (
            None,
            {},
            {'type': 'course'},
            {'type': 'course', 'key': ''},
            {'type': 'organization'},
            {'type': 'site', 'key': ''},
            {'type': 'site', 'key': 'anything'},
            {'type': 'library', 'key': 'lib'},
            {'type': 'course', 'key': 'library-v1:Org+Lib'},
            {'type': 'course', 'key': 'not-a-course-key'},
            [{'type': 'site'}],
        ):
            with self.subTest(context=context), self.assertRaises(ValidationError):
                validate_reusable_context(context)

    @patch(
        'lti_consumer.plugin.compat.get_active_organizations',
        return_value=[{'short_name': 'MyOrg'}],
    )
    def test_validate_reusable_context_lowercases_and_resolves_organization(self, _get_active):
        self.assertEqual(
            validate_reusable_context({'type': 'organization', 'key': '  MYORG  '}),
            {'type': 'organization', 'key': 'myorg'},
        )
        with self.assertRaises(ValidationError):
            validate_reusable_context({'type': 'organization', 'key': 'unregistered'})

    @patch(
        'lti_consumer.plugin.compat.get_active_organizations',
        return_value=[{'short_name': 'Org'}, {'short_name': 'ORG'}],
    )
    def test_validate_reusable_context_rejects_ambiguous_registration(self, _get_active):
        with self.assertRaises(ValidationError):
            validate_reusable_context({'type': 'organization', 'key': 'org'})


class ReusableCreationTests(TestCase):
    """Creation service invariants and transaction behavior."""

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

    def test_lti11_generates_independent_credentials_and_returns_them_once(self):
        result = create_reusable_configuration(self.lti11_input())
        config = result.configuration
        self.assertEqual(config.name, 'One One')
        self.assertEqual(config.normalized_name, 'one one')
        self.assertEqual((config.context_type, config.context_key), ('course', COURSE_KEY))
        self.assertTrue(config.lti_1p1_client_key)
        self.assertTrue(config.lti_1p1_client_secret)
        self.assertNotEqual(config.lti_1p1_client_key, config.lti_1p1_client_secret)
        self.assertEqual(result.one_time_credentials, {
            'client_key': config.lti_1p1_client_key,
            'client_secret': config.lti_1p1_client_secret,
        })
        self.assertIsNone(config.lti_1p3_client_id)

    def test_create_rejects_missing_or_invalid_context_without_writing(self):
        # One representative invalid context proves the service calls the shared
        # validator before writing; the pure matrix and API tests cover all shapes.
        data = self.lti11_input(context={'type': 'course'})
        with self.assertRaises(ValidationError):
            create_reusable_configuration(data)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 0)
        self.assertEqual(Lti1p3Passport.objects.count(), 0)

    def test_two_configurations_may_share_one_context(self):
        first = create_reusable_configuration(self.lti11_input(name='First')).configuration
        second = create_reusable_configuration(self.lti11_input(name='Second')).configuration
        self.assertEqual((first.context_type, second.context_type), ('course', 'course'))
        self.assertEqual((first.context_key, second.context_key), (COURSE_KEY, COURSE_KEY))
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 2)

    def test_lti11_accepts_overridden_credentials(self):
        data = self.lti11_input()
        data['lti_1p1'].update(client_key='provided-key', client_secret='provided-secret')
        result = create_reusable_configuration(data)
        self.assertEqual(result.one_time_credentials, {
            'client_key': 'provided-key', 'client_secret': 'provided-secret',
        })

    def test_lti13_generates_independent_uuid_identities_eagerly_and_does_not_return_credentials(self):
        result = create_reusable_configuration(self.lti13_input())
        config = result.configuration
        passport = config.lti_1p3_passport
        self.assertEqual((config.context_type, config.context_key), ('site', ''))
        self.assertIsNone(result.one_time_credentials)
        self.assertNotIn('lti_1p3_internal_private_key', config.__dict__)
        self.assertNotIn('lti_1p3_internal_private_key', result.__dict__)
        self.assertNotEqual(config.lti_1p3_client_id, config.lti_1p3_deployment_id)
        self.assertEqual(str(uuid.UUID(config.lti_1p3_client_id, version=4)), config.lti_1p3_client_id)
        self.assertEqual(str(uuid.UUID(config.lti_1p3_deployment_id, version=4)), config.lti_1p3_deployment_id)
        self.assertEqual(passport.lti_1p3_client_id, config.lti_1p3_client_id)
        self.assertTrue(passport.lti_1p3_internal_private_key)
        self.assertTrue(passport.lti_1p3_internal_private_key_id)
        self.assertTrue(passport.lti_1p3_internal_public_jwk)
        # Stored model state is populated; no lazy passport properties are read here.
        self.assertEqual(passport.lti_1p3_tool_keyset_url, 'https://tool.example/jwks')

    def test_lti13_accepts_overridden_independent_identities_and_public_key_mode(self):
        data = self.lti13_input()
        data['lti_1p3'] = {
            'launch_url': 'https://tool.example/launch',
            'oidc_url': 'https://tool.example/oidc',
            'tool_key_mode': 'public_key',
            'tool_public_key': '-----BEGIN PUBLIC KEY-----\nexample',
            'client_id': 'CaseSensitive-ID',
            'deployment_id': 'deployment-override',
        }
        result = create_reusable_configuration(data)
        self.assertEqual(result.configuration.lti_1p3_client_id, 'CaseSensitive-ID')
        self.assertEqual(result.configuration.lti_1p3_deployment_id, 'deployment-override')
        self.assertEqual(result.configuration.lti_1p3_passport.lti_1p3_client_id, 'CaseSensitive-ID')
        self.assertIsNone(result.one_time_credentials)

    def test_accent_equivalent_client_ids_follow_database_collation(self):
        data = self.lti13_input()
        data['lti_1p3']['client_id'] = 'Cafe'
        create_reusable_configuration(data)

        if not ReusableLtiConfiguration.objects.filter(lti_1p3_client_id='Café').exists():
            self.skipTest('Database collation distinguishes accented Client IDs.')

        duplicate = self.lti13_input(name='Different Client ID spelling')
        duplicate['lti_1p3']['client_id'] = 'Café'
        with self.assertRaises(ValidationError):
            create_reusable_configuration(duplicate)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 1)

    def test_legacy_passport_client_collision_is_non_disclosing(self):
        Lti1p3Passport.objects.create(lti_1p3_client_id='legacy-client')
        data = self.lti13_input()
        data['lti_1p3']['client_id'] = 'legacy-client'
        with self.assertRaisesMessage(ValidationError, 'conflicts with an existing identity'):
            create_reusable_configuration(data)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 0)

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

    def test_version_connection_and_key_material_invariants(self):
        invalid = [
            self.lti11_input(version='lti_1p3'),
            self.lti11_input(lti_1p3={}),
            self.lti11_input(lti_1p1={'launch_url': ''}),
            self.lti13_input(lti_1p3={
                'launch_url': 'https://tool.example/launch',
                'oidc_url': 'https://tool.example/oidc',
                'tool_key_mode': 'public_key',
            }),
            self.lti13_input(lti_1p3={
                'launch_url': 'https://tool.example/launch',
                'oidc_url': 'https://tool.example/oidc',
                'tool_key_mode': 'unknown',
                'tool_public_key': 'key',
            }),
        ]
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ValidationError):
                create_reusable_configuration(data)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 0)
        self.assertEqual(Lti1p3Passport.objects.count(), 0)

    def test_duplicate_normalized_name_translates_integrity_error(self):
        create_reusable_configuration(self.lti11_input(name='Straße'))
        duplicate = self.lti11_input(name='STRASSE')
        with self.assertRaisesMessage(ValidationError, 'conflicts with an existing record'):
            create_reusable_configuration(duplicate)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 1)
