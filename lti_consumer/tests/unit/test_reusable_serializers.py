"""Tests for reusable configuration request validation and safe response fields."""
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from lti_consumer.plugin.reusable_serializers import (
    ReusableCreateInputSerializer,
    ReusableCreateResponseSerializer,
    ReusableDetailSerializer,
    ReusableListSerializer,
    ReusableUpdateInputSerializer,
)
from lti_consumer.reusable import create_reusable_configuration


def lti13_payload(**overrides):
    """Return a valid LTI 1.3 payload, with optional connection-field overrides."""
    connection = overrides.pop('lti_1p3', {})
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
    payload['lti_1p3'].update(connection)
    if payload['lti_1p3']['tool_key_mode'] == 'public_key':
        payload['lti_1p3'].pop('tool_keyset_url', None)
    payload.update(overrides)
    return payload


class ReusableCreateInputSerializerTests(SimpleTestCase):
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

    def test_valid_payload_is_normalized_and_defaults_sections(self):
        serializer = ReusableCreateInputSerializer(data=self.lti11_payload())
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['name'], 'Example Tool')
        self.assertEqual(serializer.validated_data['services']['ags_mode'], 'declarative')
        self.assertEqual(serializer.validated_data['defaults'], {})

    def test_field_validation_rejects_blank_names_and_redirect_uris(self):
        for name in ('', '   ', 'x' * 256):
            with self.subTest(name=name):
                serializer = ReusableCreateInputSerializer(data=self.lti11_payload(name=name))
                self.assertFalse(serializer.is_valid())
                self.assertIn('name', serializer.errors)

        payload = lti13_payload(lti_1p3={'redirect_uris': ['']})
        serializer = ReusableCreateInputSerializer(data=payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn('redirect_uris', serializer.errors['lti_1p3'])

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
        payload = lti13_payload(services={'deep_linking_enabled': True})
        self.assertFalse(ReusableCreateInputSerializer(data=payload).is_valid())
        payload['services']['deep_linking_launch_url'] = 'https://tool.example/deep-link'
        self.assertTrue(ReusableCreateInputSerializer(data=payload).is_valid())
        payload['services']['deep_linking_launch_url'] = ''
        self.assertFalse(ReusableCreateInputSerializer(data=payload).is_valid())
        self.assertTrue(ReusableCreateInputSerializer(data=self.lti11_payload(
            services={'deep_linking_launch_url': ''}
        )).is_valid())

    def test_lti13_requires_exactly_one_non_private_tool_key_source(self):
        payload = lti13_payload(lti_1p3={
            'launch_url': 'https://tool.example/launch',
            'oidc_url': 'https://tool.example/oidc',
            'tool_key_mode': 'public_key',
            'tool_public_key': '-----BEGIN PRIVATE KEY-----\nnope',
        })
        self.assertFalse(ReusableCreateInputSerializer(data=payload).is_valid())
        payload['lti_1p3']['tool_public_key'] = '-----BEGIN PUBLIC KEY-----\nkey'
        self.assertTrue(ReusableCreateInputSerializer(data=payload).is_valid())

    def test_keyset_url_limit_is_500_characters(self):
        prefix = 'https://tool.example/'
        accepted_url = prefix + 'k' * (300 - len(prefix))
        rejected_url = prefix + 'k' * (501 - len(prefix))
        payload = lti13_payload()
        payload['lti_1p3']['tool_keyset_url'] = accepted_url

        serializer = ReusableCreateInputSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['lti_1p3']['tool_keyset_url'], accepted_url)

        payload['lti_1p3']['tool_keyset_url'] = rejected_url
        self.assertFalse(ReusableCreateInputSerializer(data=payload).is_valid())

    def test_course_keys_match_stored_identity_and_respect_storage_limit(self):
        serializer = ReusableCreateInputSerializer(data=self.lti11_payload())
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['scope']['course_keys'], ['course-v1:Org+Course+Run'])

        base_key = 'course-v1:Org+Course+Run'
        branch_key = f'{base_key}+branch@draft'
        payload = self.lti11_payload(scope={'course_keys': [branch_key, base_key]})
        serializer = ReusableCreateInputSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['scope']['course_keys'], [base_key])

        version_only_key = 'course-v1:version@519665f6223ebd6980884f2b'
        self.assertFalse(ReusableCreateInputSerializer(data=self.lti11_payload(
            scope={'course_keys': [version_only_key]}
        )).is_valid())

        library_key = 'library-v1:Org+Library'
        serializer = ReusableCreateInputSerializer(data=self.lti11_payload(
            scope={'course_keys': [library_key]}
        ))
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['scope']['course_keys'], [library_key])

        prefix, suffix = 'course-v1:', '+C+R'
        org_length = 255 - len(prefix) - len(suffix)
        max_length_key = f"{prefix}{'o' * org_length}{suffix}"
        too_long_key = f"{prefix}{'o' * (org_length + 1)}{suffix}"
        self.assertEqual(len(max_length_key), 255)
        self.assertTrue(ReusableCreateInputSerializer(data=self.lti11_payload(
            scope={'course_keys': [max_length_key]}
        )).is_valid())
        self.assertFalse(ReusableCreateInputSerializer(data=self.lti11_payload(
            scope={'course_keys': [too_long_key]}
        )).is_valid())
        self.assertFalse(ReusableCreateInputSerializer(data=self.lti11_payload(
            scope={'course_keys': ['not-a-course-key']}
        )).is_valid())

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
        serializer = ReusableCreateInputSerializer(data=self.lti11_payload(
            scope={'organization_keys': ['unknown-org']}
        ))
        self.assertFalse(serializer.is_valid())
        self.assertEqual(
            serializer.errors['scope']['organization_keys'][0],
            'Organization must match one unambiguous active registered organization.',
        )
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
        self.assertTrue(ReusableCreateInputSerializer(data=self.lti11_payload(
            defaults={'inline_height': 2147483647}
        )).is_valid())
        self.assertFalse(ReusableCreateInputSerializer(data=self.lti11_payload(
            defaults={'inline_height': 2147483648}
        )).is_valid())


class ReusableUpdateInputSerializerTests(TestCase):
    """PATCH validation uses the complete resulting connection and service settings."""

    def setUp(self):
        payload = lti13_payload(name='Patch validation')
        payload['lti_1p3']['redirect_uris'] = ['https://tool.example/redirect']
        self.configuration = create_reusable_configuration(payload).configuration

    def validate_patch(self, data):
        serializer = ReusableUpdateInputSerializer(
            data=data, partial=True, context={'configuration': self.configuration},
        )
        return serializer.is_valid(), serializer

    def test_empty_redirects_are_preserved_without_fallback(self):
        valid, serializer = self.validate_patch({
            'lti_1p3': {
                'redirect_uris': [], 'launch_url': 'https://tool.example/new-launch',
            },
            'services': {'deep_linking_launch_url': 'https://tool.example/deep'},
        })
        self.assertTrue(valid, serializer.errors)
        self.assertEqual(serializer.validated_data['lti_1p3']['redirect_uris'], [])

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

    def test_scope_addition_rejects_version_only_course_keys(self):
        version_only_key = 'course-v1:version@519665f6223ebd6980884f2b'
        valid, serializer = self.validate_patch({'scope': {'course_keys': [version_only_key]}})
        self.assertFalse(valid)
        self.assertIn('scope', serializer.errors)

    @patch('lti_consumer.plugin.reusable_serializers.compat.get_active_organizations')
    def test_invalid_new_organization_grant_keeps_patch_specific_error(self, get_organizations):
        get_organizations.return_value = [{'short_name': 'registered'}]
        valid, serializer = self.validate_patch({'scope': {'organization_keys': ['unknown']}})
        self.assertFalse(valid)
        self.assertEqual(
            serializer.errors['scope']['organization_keys'][0],
            'New grants must match one unambiguous active registered organization.',
        )

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

        prefix = 'https://tool.example/'
        accepted_url = prefix + 'k' * (300 - len(prefix))
        rejected_url = prefix + 'k' * (501 - len(prefix))
        valid, serializer = self.validate_patch({'lti_1p3': {
            'tool_key_mode': 'keyset_url', 'tool_keyset_url': accepted_url,
        }})
        self.assertTrue(valid, serializer.errors)
        self.assertEqual(serializer.validated_data['lti_1p3']['tool_keyset_url'], accepted_url)
        self.assertFalse(self.validate_patch({'lti_1p3': {
            'tool_key_mode': 'keyset_url', 'tool_keyset_url': rejected_url,
        }})[0])

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

    def test_lti13_validated_payload_stores_library_scope_and_passport_identity(self):
        library_key = 'library-v1:Org+Library'
        payload = lti13_payload(name='Integrated 1.3', scope={'course_keys': [library_key]})
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

    def test_lti13_registration_urls_use_existing_reusable_api_keys(self):
        configuration = create_reusable_configuration(
            lti13_payload(name='Registration metadata'),
        ).configuration

        with patch(
            'lti_consumer.plugin.reusable_serializers.get_lti_view_base',
            return_value='https://lms.example',
        ), patch(
            'lti_consumer.plugin.reusable_serializers.get_lti_api_base',
            return_value='https://api.example',
        ):
            data = ReusableDetailSerializer(configuration, context={'can_manage': True}).data

        self.assertEqual(data['registration_urls'], {
            'login_url': 'https://lms.example/api/lti_consumer/v1/launch/',
            'jwks_url': 'https://api.example/api/lti_consumer/v1/public_keysets',
            'access_token_url': 'https://api.example/api/lti_consumer/v1/token',
        })

    def test_lti13_detail_never_serializes_tool_or_platform_key_material(self):
        payload = lti13_payload(
            name='Safe 1.3 Tool',
            scope={'site_wide': True},
            lti_1p3={
                'tool_key_mode': 'public_key',
                'tool_public_key': '-----BEGIN PUBLIC KEY-----\\nPUBLIC MATERIAL',
            },
        )
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
