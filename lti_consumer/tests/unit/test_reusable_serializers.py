"""Tests for reusable configuration request validation and safe response fields."""
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from lti_consumer.plugin.reusable_serializers import (
    ReusableContextInputSerializer,
    ReusableCreateInputSerializer,
    ReusableCreateResponseSerializer,
    ReusableDetailSerializer,
    ReusableListSerializer,
    ReusableUpdateInputSerializer,
)
from lti_consumer.reusable import create_reusable_configuration

COURSE_KEY = 'course-v1:Org+Course+Run'
REGISTRY_PATCH = 'lti_consumer.plugin.compat.get_active_organizations'


def course_context(key=COURSE_KEY):
    """Return a create-only course context."""
    return {'type': 'course', 'key': key}


def organization_context(key):
    """Return a create-only organization context."""
    return {'type': 'organization', 'key': key}


def site_context():
    """Return a create-only site context; the key is omitted."""
    return {'type': 'site'}


def lti13_payload(**overrides):
    """Return a valid LTI 1.3 payload, with optional connection-field overrides."""
    connection = overrides.pop('lti_1p3', {})
    payload = {
        'name': 'Example Tool',
        'version': 'lti_1p3',
        'context': course_context(),
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


class ReusableContextInputSerializerTests(SimpleTestCase):
    """The create-only context accepts exactly one normalized context."""

    def test_course_context_is_canonicalized(self):
        serializer = ReusableContextInputSerializer(data=course_context(f' {COURSE_KEY}+branch@draft '))
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data, course_context())

    def test_raw_course_key_over_255_is_normalized_before_the_length_check(self):
        raw_key = f'{COURSE_KEY}+branch@' + 'a' * 300
        self.assertGreater(len(raw_key), 255)

        serializer = ReusableContextInputSerializer(data=course_context(raw_key))

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data, course_context())

    @patch(REGISTRY_PATCH)
    def test_oversized_organization_context_key_is_rejected(self, get_organizations):
        get_organizations.return_value = [{'short_name': 'o' * 256}]
        serializer = ReusableContextInputSerializer(data=organization_context('O' * 256))
        self.assertFalse(serializer.is_valid())

    @patch(REGISTRY_PATCH)
    def test_unknown_or_ambiguous_organizations_fail_closed(self, get_organizations):
        get_organizations.return_value = [{'short_name': 'Other-Org'}]
        self.assertFalse(ReusableContextInputSerializer(data=organization_context('unknown-org')).is_valid())

        get_organizations.return_value = [{'short_name': 'Org-A'}, {'short_name': 'org-a'}]
        self.assertFalse(ReusableContextInputSerializer(data=organization_context('ORG-A')).is_valid())

    @patch(REGISTRY_PATCH)
    def test_course_and_site_contexts_do_not_consult_the_registry(self, get_organizations):
        self.assertTrue(ReusableContextInputSerializer(data=course_context()).is_valid())
        self.assertTrue(ReusableContextInputSerializer(data=site_context()).is_valid())
        get_organizations.assert_not_called()

    def test_invalid_contexts_are_rejected(self):
        oversized_course_key = 'course-v1:' + 'o' * 250 + '+C+R'
        cases = (
            {'type': 'course'},
            {'type': 'course', 'key': ''},
            {'type': 'course', 'key': '   '},
            {'type': 'course', 'key': None},
            {'type': 'course', 'key': 123},
            {'type': ['course'], 'key': COURSE_KEY},
            {'type': 'course', 'key': 'course-v1:version@519665f6223ebd6980884f2b'},
            {'type': 'course', 'key': oversized_course_key},
            {'type': 'unknown', 'key': COURSE_KEY},
            {'type': 'site', 'key': ''},
            {'type': 'site', 'key': None},
            {'type': 'site', 'key': COURSE_KEY},
            {'type': 'course', 'key': COURSE_KEY, 'extra': True},
            {'course_keys': [COURSE_KEY]},
            {'site_wide': True},
            'course-v1:Org+Course+Run',
            [{'type': 'course', 'key': COURSE_KEY}],
            [],
        )
        for data in cases:
            with self.subTest(data=data):
                self.assertFalse(ReusableContextInputSerializer(data=data).is_valid())


class ReusableCreateInputSerializerTests(SimpleTestCase):
    """Strict, version-aware create payload validation."""

    def lti11_payload(self, **overrides):
        """Return a valid minimal LTI 1.1 payload."""
        payload = {
            'name': '  Example Tool  ',
            'version': 'lti_1p1',
            'context': course_context(),
            'lti_1p1': {'launch_url': 'https://tool.example/launch'},
        }
        payload.update(overrides)
        return payload

    def test_valid_payload_is_normalized_and_defaults_sections(self):
        serializer = ReusableCreateInputSerializer(data=self.lti11_payload())
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['name'], 'Example Tool')
        self.assertEqual(serializer.validated_data['context'], course_context())
        self.assertEqual(serializer.validated_data['services']['ags_mode'], 'declarative')
        self.assertEqual(serializer.validated_data['defaults'], {})

    def test_context_replaces_the_legacy_scope_field(self):
        serializer = ReusableCreateInputSerializer(data=self.lti11_payload())
        self.assertIn('context', serializer.fields)
        self.assertNotIn('scope', serializer.fields)

        legacy_only = self.lti11_payload(scope={'course_keys': [COURSE_KEY]})
        legacy_only.pop('context')
        self.assertFalse(ReusableCreateInputSerializer(data=legacy_only).is_valid())

        both = self.lti11_payload(scope={'course_keys': [COURSE_KEY]})
        self.assertFalse(ReusableCreateInputSerializer(data=both).is_valid())

    def test_missing_context_is_rejected(self):
        payload = self.lti11_payload()
        payload.pop('context')
        serializer = ReusableCreateInputSerializer(data=payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn('context', serializer.errors)

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
            self.lti11_payload(context={'type': 'course', 'key': COURSE_KEY, 'owner': 'someone'}),
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
            'tool_public_key': '-----BEGIN PRIVATE KEY----- nope',
        })
        self.assertFalse(ReusableCreateInputSerializer(data=payload).is_valid())
        payload['lti_1p3']['tool_public_key'] = '-----BEGIN PUBLIC KEY----- key'
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

    def test_shared_defaults_are_validated(self):
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

    def test_context_and_scope_are_rejected_on_patch(self):
        payloads = (
            {'context': course_context()},
            {'context': {'type': 'site'}},
            {'scope': {'course_keys': [COURSE_KEY]}},
            {'name': 'Changed', 'context': course_context()},
            {'name': 'Changed', 'scope': {'course_keys': [COURSE_KEY]}},
            {'context': course_context(), 'scope': {}},
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                valid, serializer = self.validate_patch(payload)
                self.assertFalse(valid)
                self.assertTrue({'context', 'scope'}.intersection(serializer.errors))

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

    def test_tool_verification_updates_require_matching_safe_key_material(self):
        public_key = '-----BEGIN PUBLIC KEY----- public material'
        valid, serializer = self.validate_patch({'lti_1p3': {
            'tool_key_mode': 'public_key', 'tool_public_key': public_key,
        }})
        self.assertTrue(valid, serializer.errors)
        self.assertEqual(serializer.validated_data['lti_1p3']['tool_key_mode'], 'public_key')

        for connection in (
            {'tool_key_mode': 'public_key'},
            {'tool_key_mode': 'public_key', 'tool_public_key': '-----BEGIN PRIVATE KEY----- private'},
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
    """Ensure validated create payloads match the atomic single-context service contract."""

    def test_validated_payload_stores_the_normalized_context(self):
        payload = lti13_payload(name='Integrated 1.3', context=course_context(f'{COURSE_KEY}+branch@draft'))
        serializer = ReusableCreateInputSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)

        result = create_reusable_configuration(serializer.validated_data)
        configuration = result.configuration
        self.assertEqual((configuration.context_type, configuration.context_key), ('course', COURSE_KEY))
        self.assertEqual(configuration.lti_1p3_passport.lti_1p3_client_id, configuration.lti_1p3_client_id)
        self.assertIsNone(result.one_time_credentials)

    def test_site_context_stores_a_blank_context_key(self):
        payload = lti13_payload(name='Site 1.3', context=site_context())
        serializer = ReusableCreateInputSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)

        configuration = create_reusable_configuration(serializer.validated_data).configuration
        self.assertEqual((configuration.context_type, configuration.context_key), ('site', ''))

    @patch(REGISTRY_PATCH)
    def test_organization_context_stores_the_lowercased_key(self, get_organizations):
        get_organizations.return_value = [{'short_name': 'Org-A'}]
        payload = lti13_payload(name='Org 1.3', context=organization_context(' ORG-A '))
        serializer = ReusableCreateInputSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)

        configuration = create_reusable_configuration(serializer.validated_data).configuration
        self.assertEqual((configuration.context_type, configuration.context_key), ('organization', 'org-a'))


class ReusableResponseSerializerTests(TestCase):
    """Response serializers expose metadata only through explicit allowlists."""

    def setUp(self):
        self.configuration = create_reusable_configuration({
            'name': 'Safe Tool',
            'version': 'lti_1p1',
            'context': course_context(),
            'lti_1p1': {'launch_url': 'https://tool.example/launch'},
        }).configuration

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
        self.assertNotIn('scope', detail)
        self.assertEqual(detail['context'], course_context())

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
            lti_1p3={
                'tool_key_mode': 'public_key',
                'tool_public_key': '-----BEGIN PUBLIC KEY----- PUBLIC MATERIAL',
            },
        )
        configuration = create_reusable_configuration(payload).configuration
        private_key = configuration.lti_1p3_passport.lti_1p3_internal_private_key
        data = ReusableDetailSerializer(configuration, context={'can_manage': True}).data
        self.assertNotIn(private_key, str(data))
        self.assertNotIn('tool_public_key', data)
        self.assertNotIn('lti_1p3_internal_private_key', data)
        self.assertEqual(data['context'], course_context())
        self.assertEqual(data['client_id'], configuration.lti_1p3_client_id)
        self.assertTrue(data['tool_key_configured'])
