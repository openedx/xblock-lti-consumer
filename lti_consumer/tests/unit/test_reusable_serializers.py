"""Tests for reusable configuration request validation and safe response fields."""
from unittest.mock import patch

from django.test import TestCase

from lti_consumer.plugin.reusable_serializers import (
    ReusableCreateInputSerializer,
    ReusableCreateResponseSerializer,
    ReusableDetailSerializer,
    ReusableListSerializer,
    ReusableUpdateInputSerializer,
)
from lti_consumer.reusable import create_reusable_configuration


class ReusableCreateInputSerializerTests(TestCase):
    """Strict, version-aware create payload validation."""

    def lti11_payload(self, **overrides):
        """Return a valid minimal LTI 1.1 payload."""
        payload = {
            'name': '  Example Tool  ',
            'version': 'lti_1p1',
            'scope': {'course_keys': ['course-v1:Org+Course+Run']},
            'lti_1p1': {'launch_url': 'https://tool.example/launch'},
        }
        payload.update(overrides)
        return payload

    def lti13_payload(self, **overrides):
        """Return a valid minimal LTI 1.3 payload."""
        payload = {
            'name': 'Example Tool',
            'version': 'lti_1p3',
            'scope': {'course_keys': ['course-v1:Org+Course+Run']},
            'lti_1p3': {
                'launch_url': 'https://tool.example/launch',
                'oidc_url': 'https://tool.example/oidc',
                'tool_key_mode': 'keyset_url',
                'tool_keyset_url': 'https://tool.example/jwks',
            },
        }
        payload.update(overrides)
        return payload

    def test_valid_payload_is_normalized_and_defaults_sections(self):
        serializer = ReusableCreateInputSerializer(data=self.lti11_payload())
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['name'], 'Example Tool')
        self.assertEqual(serializer.validated_data['services']['ags_mode'], 'declarative')
        self.assertEqual(serializer.validated_data['defaults'], {})

    def test_unknown_fields_rejected_at_each_level(self):
        cases = (
            self.lti11_payload(extra='no'),
            self.lti11_payload(scope={'course_keys': ['course-v1:Org+Course+Run'], 'owner': 'someone'}),
            self.lti11_payload(lti_1p1={'launch_url': 'https://tool.example/launch', 'private_key': 'secret'}),
            self.lti11_payload(services={'deep_linking_enabled': False, 'platform_key': 'secret'}),
            self.lti11_payload(defaults={'not_a_setting': True}),
        )
        for payload in cases:
            with self.subTest(payload=payload):
                self.assertFalse(ReusableCreateInputSerializer(data=payload).is_valid())

    def test_version_connection_section_must_match(self):
        payload = self.lti11_payload(lti_1p3={'launch_url': 'https://tool.example/launch'})
        self.assertFalse(ReusableCreateInputSerializer(data=payload).is_valid())
        payload = self.lti11_payload(version='lti_1p3')
        self.assertFalse(ReusableCreateInputSerializer(data=payload).is_valid())

    def test_only_http_urls_are_accepted_and_deep_linking_requires_its_url(self):
        payload = self.lti11_payload(lti_1p1={'launch_url': 'javascript:alert(1)'})
        self.assertFalse(ReusableCreateInputSerializer(data=payload).is_valid())
        payload = self.lti13_payload(services={'deep_linking_enabled': True})
        self.assertFalse(ReusableCreateInputSerializer(data=payload).is_valid())
        payload['services']['deep_linking_launch_url'] = 'https://tool.example/deep-link'
        self.assertTrue(ReusableCreateInputSerializer(data=payload).is_valid())
        payload['services']['deep_linking_launch_url'] = ''
        self.assertFalse(ReusableCreateInputSerializer(data=payload).is_valid())
        self.assertTrue(ReusableCreateInputSerializer(data=self.lti11_payload(
            services={'deep_linking_launch_url': ''}
        )).is_valid())

    def test_lti13_requires_exactly_one_non_private_tool_key_source(self):
        payload = self.lti13_payload(lti_1p3={
            'launch_url': 'https://tool.example/launch',
            'oidc_url': 'https://tool.example/oidc',
            'tool_key_mode': 'public_key',
            'tool_public_key': '-----BEGIN PRIVATE KEY-----\nnope',
        })
        self.assertFalse(ReusableCreateInputSerializer(data=payload).is_valid())
        payload['lti_1p3']['tool_public_key'] = '-----BEGIN PUBLIC KEY-----\nkey'
        self.assertTrue(ReusableCreateInputSerializer(data=payload).is_valid())

    def test_course_keys_are_parsed_and_library_keys_are_preserved(self):
        serializer = ReusableCreateInputSerializer(data=self.lti11_payload())
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['scope']['course_keys'], ['course-v1:Org+Course+Run'])

        library_key = 'library-v1:Org+Library'
        payload = self.lti11_payload(scope={'course_keys': [library_key]})
        serializer = ReusableCreateInputSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['scope']['course_keys'], [library_key])

        payload = self.lti11_payload(scope={'course_keys': ['not-a-course-key']})
        self.assertFalse(ReusableCreateInputSerializer(data=payload).is_valid())

    @patch('lti_consumer.plugin.reusable_serializers.compat.get_active_organizations')
    def test_organization_grants_match_one_active_registered_short_name(self, get_organizations):
        get_organizations.return_value = [{'short_name': 'Org-A', 'name': 'Organization A'}]
        payload = self.lti11_payload(scope={'organization_keys': [' ORG-A ', 'org-a']})
        serializer = ReusableCreateInputSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['scope']['organization_keys'], ['org-a'])
        get_organizations.assert_called_once_with()

        get_organizations.reset_mock()
        get_organizations.return_value = [{'short_name': 'Other-Org'}]
        self.assertFalse(ReusableCreateInputSerializer(data=self.lti11_payload(
            scope={'organization_keys': ['unknown-org']}
        )).is_valid())
        get_organizations.assert_called_once_with()

    @patch('lti_consumer.plugin.reusable_serializers.compat.get_active_organizations')
    def test_ambiguous_case_normalized_organization_names_fail_closed(self, get_organizations):
        get_organizations.return_value = [{'short_name': 'Org-A'}, {'short_name': 'org-a'}]
        serializer = ReusableCreateInputSerializer(data=self.lti11_payload(
            scope={'organization_keys': ['ORG-A']}
        ))
        self.assertFalse(serializer.is_valid())
        self.assertIn('organization_keys', serializer.errors['scope'])
        get_organizations.assert_called_once_with()

    def test_scope_and_shared_defaults_are_validated(self):
        self.assertFalse(ReusableCreateInputSerializer(data=self.lti11_payload(
            scope={'course_keys': [], 'organization_keys': [], 'site_wide': False}
        )).is_valid())
        self.assertFalse(ReusableCreateInputSerializer(data=self.lti11_payload(
            defaults={'custom_parameters': ['missing-equals']}
        )).is_valid())
        self.assertFalse(ReusableCreateInputSerializer(data=self.lti11_payload(
            defaults={'custom_parameters': ['=missing-key']}
        )).is_valid())
        self.assertFalse(ReusableCreateInputSerializer(data=self.lti11_payload(
            defaults={'grade_weight': float('nan')}
        )).is_valid())
        self.assertFalse(ReusableCreateInputSerializer(data=self.lti11_payload(
            defaults={'modal_width': 101}
        )).is_valid())


class ReusableUpdateInputSerializerTests(TestCase):
    """PATCH validation uses the complete resulting connection and service settings."""

    def setUp(self):
        self.configuration = create_reusable_configuration({
            'name': 'Patch validation',
            'version': 'lti_1p3',
            'scope': {'course_keys': ['course-v1:Org+Course+Run']},
            'lti_1p3': {
                'launch_url': 'https://tool.example/launch',
                'oidc_url': 'https://tool.example/oidc',
                'redirect_uris': ['https://tool.example/redirect'],
                'tool_key_mode': 'keyset_url',
                'tool_keyset_url': 'https://tool.example/jwks',
            },
        }).configuration

    def validate_patch(self, data):
        serializer = ReusableUpdateInputSerializer(
            data=data, partial=True, context={'configuration': self.configuration},
        )
        return serializer.is_valid(), serializer

    def test_empty_redirects_use_merged_launch_and_deep_link_urls(self):
        valid, serializer = self.validate_patch({
            'lti_1p3': {
                'redirect_uris': [], 'launch_url': 'https://tool.example/new-launch',
            },
            'services': {'deep_linking_launch_url': 'https://tool.example/deep'},
        })
        self.assertTrue(valid, serializer.errors)
        self.assertEqual(serializer.validated_data['lti_1p3']['redirect_uris'], [
            'https://tool.example/new-launch', 'https://tool.example/deep',
        ])

    def test_nonempty_redirects_are_authoritative_and_omission_is_preserved(self):
        valid, serializer = self.validate_patch({
            'lti_1p3': {'redirect_uris': ['https://only.example/callback']},
        })
        self.assertTrue(valid, serializer.errors)
        self.assertEqual(
            serializer.validated_data['lti_1p3']['redirect_uris'], ['https://only.example/callback'],
        )
        valid, serializer = self.validate_patch({'lti_1p3': {'launch_url': 'https://tool.example/new-launch'}})
        self.assertTrue(valid, serializer.errors)
        self.assertNotIn('redirect_uris', serializer.validated_data['lti_1p3'])
        self.configuration.lti_1p3_redirect_uris = []
        valid, serializer = self.validate_patch({'name': 'metadata only'})
        self.assertTrue(valid, serializer.errors)
        self.assertNotIn('lti_1p3', serializer.validated_data)

    def test_connection_updates_are_versioned_and_reject_immutable_identity(self):
        valid, serializer = self.validate_patch({'lti_1p3': {'launch_url': 'https://tool.example/new'}})
        self.assertTrue(valid, serializer.errors)
        for payload in (
            {'launch_url': 'https://tool.example/new'},
            {'lti_1p1': {'launch_url': 'https://tool.example/new'}},
            {'lti_1p3': {'client_id': 'replacement'}},
            {'lti_1p3': {'deployment_id': 'replacement'}},
        ):
            with self.subTest(payload=payload):
                self.assertFalse(self.validate_patch(payload)[0])

    def test_tool_verification_updates_require_matching_safe_key_material(self):
        public_key = '-----BEGIN PUBLIC KEY-----\\npublic material'
        valid, serializer = self.validate_patch({'lti_1p3': {
            'tool_key_mode': 'public_key', 'tool_public_key': public_key,
        }})
        self.assertTrue(valid, serializer.errors)
        self.assertEqual(serializer.validated_data['lti_1p3']['tool_key_mode'], 'public_key')

        for connection in (
            {'tool_key_mode': 'public_key'},
            {'tool_key_mode': 'public_key', 'tool_public_key': '-----BEGIN PRIVATE KEY-----\\nprivate'},
            {'tool_public_key': public_key},
        ):
            with self.subTest(connection=connection):
                self.assertFalse(self.validate_patch({'lti_1p3': connection})[0])

        valid, serializer = self.validate_patch({'lti_1p3': {
            'tool_key_mode': 'keyset_url', 'tool_keyset_url': 'https://new.example/jwks',
        }})
        self.assertTrue(valid, serializer.errors)
        self.assertEqual(serializer.validated_data['lti_1p3']['tool_keyset_url'], 'https://new.example/jwks')

    def test_invalid_stored_urls_and_redirects_fail_resulting_state_validation(self):
        self.configuration.lti_1p3_launch_url = 'javascript:bad'
        valid, _ = self.validate_patch({'name': 'change'})
        self.assertFalse(valid)
        self.configuration.lti_1p3_launch_url = 'https://tool.example/launch'
        self.configuration.lti_1p3_oidc_url = 'javascript:bad'
        valid, _ = self.validate_patch({'name': 'change'})
        self.assertFalse(valid)
        self.configuration.lti_1p3_oidc_url = 'https://tool.example/oidc'
        self.configuration.lti_1p3_redirect_uris = ['javascript:bad']
        valid, _ = self.validate_patch({'name': 'change'})
        self.assertFalse(valid)

    def test_deep_linking_requires_valid_url_only_when_enabled_and_no_inheritance(self):
        self.configuration.lti_advantage_deep_linking_launch_url = 'javascript:bad'
        valid, _ = self.validate_patch({'name': 'disabled with invalid stored URL'})
        self.assertFalse(valid)

        valid, serializer = self.validate_patch({'services': {
            'deep_linking_enabled': True,
            'deep_linking_launch_url': 'https://tool.example/deep',
        }})
        self.assertTrue(valid, serializer.errors)
        valid, _ = self.validate_patch({'services': {'deep_linking_enabled': True}})
        self.assertFalse(valid)
        valid, _ = self.validate_patch({'services': {
            'deep_linking_enabled': True, 'deep_linking_launch_url': 'javascript:bad',
        }})
        self.assertFalse(valid)

        self.configuration.lti_advantage_deep_linking_launch_url = ''
        valid, serializer = self.validate_patch({'services': {
            'deep_linking_enabled': False, 'deep_linking_launch_url': '',
        }})
        self.assertTrue(valid, serializer.errors)
        valid, serializer = self.validate_patch({'lti_1p3': {'launch_url': 'https://tool.example/changed'}})
        self.assertTrue(valid, serializer.errors)
        self.assertNotIn('services', serializer.validated_data)


class ReusableSerializerServiceIntegrationTests(TestCase):
    """Ensure validated create payloads match the atomic service contract."""

    def test_lti11_validated_payload_creates_configuration_and_one_time_credentials(self):
        payload = {
            'name': 'Integrated 1.1',
            'version': 'lti_1p1',
            'scope': {'course_keys': ['course-v1:Org+Course+Run']},
            'lti_1p1': {'launch_url': 'https://tool.example/launch'},
        }
        serializer = ReusableCreateInputSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)

        result = create_reusable_configuration(serializer.validated_data)
        configuration = result.configuration
        self.assertEqual(configuration.lti_1p1_launch_url, 'https://tool.example/launch')
        self.assertEqual(configuration.lti_advantage_ags_mode, 'declarative')
        self.assertEqual(str(configuration.course_grants.get().course_key), 'course-v1:Org+Course+Run')
        self.assertEqual(result.one_time_credentials['client_secret'], configuration.lti_1p1_client_secret)

    def test_lti13_validated_payload_stores_library_scope_and_passport_identity(self):
        library_key = 'library-v1:Org+Library'
        payload = {
            'name': 'Integrated 1.3',
            'version': 'lti_1p3',
            'scope': {'course_keys': [library_key]},
            'lti_1p3': {
                'launch_url': 'https://tool.example/launch',
                'oidc_url': 'https://tool.example/oidc',
                'tool_key_mode': 'keyset_url',
                'tool_keyset_url': 'https://tool.example/jwks',
            },
        }
        serializer = ReusableCreateInputSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)

        result = create_reusable_configuration(serializer.validated_data)
        configuration = result.configuration
        self.assertEqual(str(configuration.course_grants.get().course_key), library_key)
        self.assertEqual(configuration.lti_1p3_passport.lti_1p3_client_id, configuration.lti_1p3_client_id)
        self.assertIsNone(result.one_time_credentials)


class ReusableResponseSerializerTests(TestCase):
    """Response serializers expose metadata only through explicit allowlists."""

    def setUp(self):
        payload = {
            'name': 'Safe Tool',
            'version': 'lti_1p1',
            'scope': {'course_keys': ['course-v1:Org+Course+Run']},
            'lti_1p1': {'launch_url': 'https://tool.example/launch'},
        }
        self.configuration = create_reusable_configuration(payload).configuration

    def test_list_response_has_only_safe_list_fields(self):
        data = ReusableListSerializer(self.configuration).data
        self.assertEqual(set(data), {
            'config_id', 'name', 'version', 'scope_summary', 'created_at', 'updated_at',
            'can_manage', 'deep_linking_enabled', 'ags_mode', 'nrps_enabled',
        })
        self.assertEqual(data['scope_summary'], {
            'site_wide': False, 'course_count': 1, 'organization_count': 0,
        })
        self.assertNotIn(self.configuration.lti_1p1_client_secret, str(data))

    def test_detail_and_create_responses_never_include_stored_credentials(self):
        detail = ReusableDetailSerializer(self.configuration, context={'can_manage': True}).data
        created = ReusableCreateResponseSerializer(
            self.configuration,
            context={'can_manage': True, 'one_time_credentials': {
                'client_key': self.configuration.lti_1p1_client_key,
                'client_secret': self.configuration.lti_1p1_client_secret,
            }},
        ).data
        self.assertNotIn('lti_1p1_client_secret', detail)
        self.assertNotIn(self.configuration.lti_1p1_client_secret, str(detail))
        self.assertEqual(created['one_time_credentials']['client_secret'], self.configuration.lti_1p1_client_secret)
        self.assertNotIn('lti_1p1_client_secret', created)
        self.assertNotIn('lti_1p3_passport', detail)
        self.assertNotIn('lti_1p3_internal_private_key', str(detail))
        self.assertEqual(detail['scope']['course_keys'], ['course-v1:Org+Course+Run'])

    def test_lti13_detail_never_serializes_tool_or_platform_key_material(self):
        payload = {
            'name': 'Safe 1.3 Tool',
            'version': 'lti_1p3',
            'scope': {'site_wide': True},
            'lti_1p3': {
                'launch_url': 'https://tool.example/launch',
                'oidc_url': 'https://tool.example/oidc',
                'tool_key_mode': 'public_key',
                'tool_public_key': '-----BEGIN PUBLIC KEY-----\\nPUBLIC MATERIAL',
            },
        }
        configuration = create_reusable_configuration(payload).configuration
        private_key = configuration.lti_1p3_passport.lti_1p3_internal_private_key
        data = ReusableDetailSerializer(configuration, context={'can_manage': True}).data
        self.assertNotIn(private_key, str(data))
        self.assertNotIn('tool_public_key', data)
        self.assertNotIn('lti_1p3_internal_private_key', data)
        self.assertEqual(data['client_id'], configuration.lti_1p3_client_id)
        self.assertTrue(data['tool_key_configured'])

    def test_non_manager_detail_does_not_disclose_grant_identifiers(self):
        detail = ReusableDetailSerializer(self.configuration, context={'can_manage': False}).data
        self.assertNotIn('course_keys', detail['scope'])
        self.assertNotIn('course-v1:Org+Course+Run', str(detail))
