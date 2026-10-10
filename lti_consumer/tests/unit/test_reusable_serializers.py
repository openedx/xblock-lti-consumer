"""Tests for reusable configuration request validation and safe response fields."""
from django.test import TestCase

from lti_consumer.plugin.reusable_serializers import (
    ReusableCreateInputSerializer,
    ReusableCreateResponseSerializer,
    ReusableDetailSerializer,
    ReusableListSerializer,
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
            'scope': {'organization_keys': ['Org']},
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

    def test_course_keys_are_parsed_and_libraries_rejected(self):
        serializer = ReusableCreateInputSerializer(data=self.lti11_payload())
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['scope']['course_keys'], ['course-v1:Org+Course+Run'])

        for course_key in ('not-a-course-key', 'library-v1:Org+Library'):
            with self.subTest(course_key=course_key):
                payload = self.lti11_payload(scope={'course_keys': [course_key]})
                self.assertFalse(ReusableCreateInputSerializer(data=payload).is_valid())

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
