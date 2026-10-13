"""Focused tests for atomic reusable configuration creation."""

from unittest.mock import patch
import uuid

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from lti_consumer.models import (
    Lti1p3Passport,
    ReusableLtiConfiguration,
    ReusableLtiConfigurationCourse,
    ReusableLtiConfigurationOrganization,
)
from lti_consumer.reusable import create_reusable_configuration


class ReusableCreationTests(TestCase):
    """Creation service invariants and transaction behavior."""

    def lti11_input(self, **overrides):
        """Return a valid LTI 1.1 creation payload."""
        data = {
            'name': '  One One  ',
            'version': 'lti_1p1',
            'scope': {'course_keys': ['course-v1:Org+Course+Run']},
            'lti_1p1': {'launch_url': 'https://tool.example/launch'},
        }
        data.update(overrides)
        return data

    def lti13_input(self, **overrides):
        """Return a valid LTI 1.3 creation payload."""
        data = {
            'name': 'One Three',
            'version': 'lti_1p3',
            'scope': {'organization_keys': ['Org']},
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
        self.assertTrue(config.lti_1p1_client_key)
        self.assertTrue(config.lti_1p1_client_secret)
        self.assertNotEqual(config.lti_1p1_client_key, config.lti_1p1_client_secret)
        self.assertEqual(result.one_time_credentials, {
            'client_key': config.lti_1p1_client_key,
            'client_secret': config.lti_1p1_client_secret,
        })
        self.assertIsNone(config.lti_1p3_client_id)
        self.assertEqual(ReusableLtiConfigurationCourse.objects.filter(configuration=config).count(), 1)

        config.name = '  Straße  '
        config.save(update_fields={'name'})
        config.refresh_from_db()
        self.assertEqual(config.normalized_name, 'strasse')

        config.name = '  RENAMED  '
        config.save(update_fields={'name'})
        config.refresh_from_db()
        self.assertEqual(config.normalized_name, 'renamed')

    def test_repeated_course_grants_are_deduplicated(self):
        data = self.lti11_input(scope={
            'course_keys': ['course-v1:Org+Course+Run', 'course-v1:Org+Course+Run'],
        })
        config = create_reusable_configuration(data).configuration
        self.assertEqual(
            [str(key) for key in config.course_grants.values_list('course_key', flat=True)],
            ['course-v1:Org+Course+Run'],
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReusableLtiConfigurationCourse.objects.create(
                configuration=config, course_key='course-v1:Org+Course+Run',
            )

    def test_organization_grants_are_lowercased_before_deduplication(self):
        data = self.lti13_input(scope={
            'organization_keys': ['Org', 'org', 'ORG'],
        })
        config = create_reusable_configuration(data).configuration
        self.assertEqual(
            list(config.organization_grants.values_list('organization', flat=True)),
            ['org'],
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReusableLtiConfigurationOrganization.objects.create(
                configuration=config, organization='org',
            )

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
        self.assertEqual(ReusableLtiConfigurationOrganization.objects.get(configuration=config).organization, 'org')

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

    def test_legacy_passport_client_collision_is_non_disclosing(self):
        Lti1p3Passport.objects.create(lti_1p3_client_id='legacy-client')
        data = self.lti13_input()
        data['lti_1p3']['client_id'] = 'legacy-client'
        with self.assertRaisesMessage(ValidationError, 'conflicts with an existing identity'):
            create_reusable_configuration(data)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 0)

    def test_failure_after_passport_and_configuration_writes_rolls_everything_back(self):
        def fail_after_course_grant(*args, **kwargs):
            raise RuntimeError('injected failure')

        manager = ReusableLtiConfigurationOrganization.objects
        with patch.object(manager, 'bulk_create', side_effect=fail_after_course_grant):
            data = self.lti13_input(scope={
                'course_keys': ['course-v1:Org+Course+Run'], 'organization_keys': ['Org'],
            })
            with self.assertRaisesRegex(RuntimeError, 'injected failure'):
                create_reusable_configuration(data)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 0)
        self.assertEqual(Lti1p3Passport.objects.count(), 0)
        self.assertEqual(ReusableLtiConfigurationCourse.objects.count(), 0)
        self.assertEqual(ReusableLtiConfigurationOrganization.objects.count(), 0)

    def test_version_connection_scope_and_key_material_invariants(self):
        invalid = [
            self.lti11_input(version='lti_1p3'),
            self.lti11_input(lti_1p3={}),
            self.lti11_input(lti_1p1={'launch_url': ''}),
            self.lti11_input(scope={'site_wide': False}),
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
