"""Wire parsing and rendering tests for the reusable configuration adapters.

Semantic rules live in lti_consumer.reusable and its direct tests; these tests
pin the adapter contract: primitive conversion, generic unknown-member refusal,
and safe response allowlists.
"""
from django.test import SimpleTestCase, TestCase

from lti_consumer.models import Lti1p3Passport, ReusableLtiConfiguration
from lti_consumer.plugin.reusable_serializers import (
    ReusableCreateInputSerializer,
    ReusableCreateResponseSerializer,
    ReusableDetailSerializer,
    ReusableListSerializer,
    ReusableUpdateInputSerializer,
)

COURSE_KEY = 'course-v1:Org+Course+Run'
LIST_RESPONSE_FIELDS = {
    'config_id', 'name', 'version', 'context', 'created_at', 'updated_at', 'can_manage',
    'deep_linking_enabled', 'ags_mode', 'nrps_enabled',
}
DETAIL_RESPONSE_FIELDS = LIST_RESPONSE_FIELDS | {
    'description', 'launch_url', 'oidc_url', 'redirect_uris', 'tool_key_mode', 'tool_key_configured',
    'client_id', 'deployment_id', 'registration_urls', 'display_name', 'enable_grading', 'grade_weight',
    'accept_grades_after_due_date', 'open_tool_in', 'inline_height', 'modal_height', 'modal_width',
    'launch_button_text', 'send_extra_parameters', 'custom_parameters', 'deep_linking_launch_url',
}


def lti11_payload(**overrides):
    """Return a wire-valid minimal LTI 1.1 create payload."""
    payload = {
        'name': 'Example Tool',
        'version': 'lti_1p1',
        'context': {'type': 'course', 'key': COURSE_KEY},
        'lti_1p1': {'launch_url': 'https://tool.example/launch'},
    }
    payload.update(overrides)
    return payload


def lti13_payload(**overrides):
    """Return a wire-valid LTI 1.3 create payload, with optional connection overrides."""
    connection = overrides.pop('lti_1p3', {})
    payload = {
        'name': 'Example Tool',
        'version': 'lti_1p3',
        'context': {'type': 'site'},
        'lti_1p3': {
            'launch_url': 'https://tool.example/launch',
            'oidc_url': 'https://tool.example/oidc',
            'tool_key_mode': 'keyset_url',
            'tool_keyset_url': 'https://tool.example/jwks',
        },
    }
    payload['lti_1p3'].update(connection)
    payload.update(overrides)
    return payload


class ReusableCreateWireParsingTests(SimpleTestCase):
    """Create input parsing: primitives in, unknown members out, nothing semantic."""

    def test_converts_wire_primitives(self):
        serializer = ReusableCreateInputSerializer(data=lti13_payload(
            description=None,
            lti_1p3={'redirect_uris': ['https://tool.example/callback']},
            services={'deep_linking_enabled': 'true', 'deep_linking_launch_url': None},
            defaults={
                'inline_height': '900',
                'grade_weight': '2.5',
                'enable_grading': 'true',
                'modal_width': 50,
                'custom_parameters': ['a=b'],
            },
        ))
        self.assertTrue(serializer.is_valid(), serializer.errors)
        validated = serializer.validated_data
        self.assertEqual(validated['name'], 'Example Tool')
        self.assertIsNone(validated['description'])
        self.assertEqual(validated['context'], {'type': 'site'})
        self.assertEqual(validated['lti_1p3']['redirect_uris'], ['https://tool.example/callback'])
        self.assertEqual(validated['services'], {
            'deep_linking_enabled': True,
            'deep_linking_launch_url': None,
        })
        self.assertEqual(validated['defaults'], {
            'inline_height': 900,
            'grade_weight': 2.5,
            'enable_grading': True,
            'modal_width': 50,
            'custom_parameters': ['a=b'],
        })

    def test_refuses_unknown_members_at_every_level(self):
        cases = (
            lti11_payload(scope={'course_keys': [COURSE_KEY]}),
            lti11_payload(context={'type': 'course', 'key': COURSE_KEY, 'owner': 'someone'}),
            lti11_payload(lti_1p1={'launch_url': 'https://tool.example/launch', 'private_key': 'p'}),
            lti11_payload(services={'platform_key': 'p'}),
            lti11_payload(defaults={'not_a_setting': True}),
        )
        for payload in cases:
            with self.subTest(payload=payload):
                serializer = ReusableCreateInputSerializer(data=payload)
                self.assertFalse(serializer.is_valid())
                self.assertIn('Unknown field.', str(serializer.errors))

    def test_requires_typed_wire_shape(self):
        invalid = (
            [],
            'not-an-object',
            lti11_payload(name=None),
            lti11_payload(context='course-v1:Org+Course+Run'),
            lti11_payload(context={}),
            lti11_payload(lti_1p1='https://tool.example/launch'),
            lti13_payload(lti_1p3={'redirect_uris': 'https://tool.example/callback'}),
            lti13_payload(defaults={'custom_parameters': 'a=b'}),
            lti13_payload(services={'nrps_enabled': 'sometimes'}),
            lti13_payload(defaults={'grade_weight': 'heavy'}),
        )
        for payload in invalid:
            with self.subTest(payload=payload):
                self.assertFalse(ReusableCreateInputSerializer(data=payload).is_valid())

    def test_leaves_semantic_rules_to_the_module(self):
        serializer = ReusableCreateInputSerializer(data=lti11_payload(
            name='',
            version='lti_9p9',
            context={'type': 'course'},
            lti_1p1={'launch_url': 'javascript:alert(1)', 'client_key': ''},
            services={'deep_linking_enabled': True, 'ags_mode': 'bogus'},
            defaults={'custom_parameters': ['missing-equals'], 'modal_width': 101, 'inline_height': -1},
        ))
        self.assertTrue(serializer.is_valid(), serializer.errors)


class ReusableUpdateWireParsingTests(SimpleTestCase):
    """Update input parsing never reads stored state and never enforces rules."""

    def test_parses_primitives_without_stored_state(self):
        serializer = ReusableUpdateInputSerializer(data={
            'name': 'Renamed',
            'description': None,
            'lti_1p3': {
                'redirect_uris': ['https://tool.example/callback'],
                'tool_key_mode': 'keyset_url',
            },
            'services': {'nrps_enabled': 'false'},
            'defaults': {'grade_weight': '3', 'modal_width': '50'},
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        validated = serializer.validated_data
        self.assertEqual(validated['name'], 'Renamed')
        self.assertIsNone(validated['description'])
        self.assertEqual(validated['lti_1p3'], {
            'redirect_uris': ['https://tool.example/callback'],
            'tool_key_mode': 'keyset_url',
        })
        self.assertEqual(validated['services'], {'nrps_enabled': False})
        self.assertEqual(validated['defaults'], {'grade_weight': 3.0, 'modal_width': 50})

    def test_accepts_an_empty_patch(self):
        serializer = ReusableUpdateInputSerializer(data={})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data, {})

    def test_refuses_unknown_and_immutable_members(self):
        cases = (
            {'context': {'type': 'site'}},
            {'scope': {'course_keys': [COURSE_KEY]}},
            {'version': 'lti_1p1'},
            {'config_id': '00000000-0000-0000-0000-000000000000'},
            {'client_id': 'replacement'},
            {'lti_1p1': {'client_secret': 'rotated'}},
            {'lti_1p1': {'client_key': 'rotated'}},
            {'lti_1p3': {'cliend_id': 'typo'}},
            {'defaults': {'unknown_setting': 1}},
        )
        for payload in cases:
            with self.subTest(payload=payload):
                serializer = ReusableUpdateInputSerializer(data=payload)
                self.assertFalse(serializer.is_valid())
                self.assertIn('Unknown field.', str(serializer.errors))

    def test_requires_typed_wire_shape(self):
        invalid = (
            [],
            {'name': None},
            {'lti_1p3': 'https://tool.example/launch'},
            {'lti_1p3': {'redirect_uris': {}}},
            {'services': {'nrps_enabled': 7}},
            {'defaults': {'grade_weight': 'heavy'}},
        )
        for payload in invalid:
            with self.subTest(payload=payload):
                self.assertFalse(ReusableUpdateInputSerializer(data=payload).is_valid())


class RenderingAllowlistTests(TestCase):
    """Response serializers expose only allowlisted metadata, never key material."""

    def setUp(self):
        self.configuration = ReusableLtiConfiguration.objects.create(
            name='Rendered',
            version=ReusableLtiConfiguration.LTI_1P1,
            context_type='course',
            context_key=COURSE_KEY,
            lti_1p1_launch_url='https://tool.example/launch',
            lti_1p1_client_key='not-for-display',
            lti_1p1_client_secret='not-for-display-secret',
        )

    def test_list_rendering_allowlist(self):
        data = ReusableListSerializer(self.configuration, context={'can_manage': True}).data
        self.assertEqual(set(data), LIST_RESPONSE_FIELDS)
        self.assertEqual(data['context'], {'type': 'course', 'key': COURSE_KEY})
        self.assertTrue(data['can_manage'])
        self.assertNotIn('not-for-display', str(data))

    def test_list_rendering_accepts_a_callable_manage_check(self):
        def check(obj):
            return obj.pk == self.configuration.pk

        data = ReusableListSerializer(self.configuration, context={'can_manage': check}).data
        self.assertTrue(data['can_manage'])

    def test_detail_rendering_allowlist_hides_credentials(self):
        data = ReusableDetailSerializer(self.configuration, context={'can_manage': False}).data
        self.assertEqual(set(data), DETAIL_RESPONSE_FIELDS)
        self.assertEqual(data['context'], {'type': 'course', 'key': COURSE_KEY})
        self.assertFalse(data['can_manage'])
        self.assertEqual(data['launch_url'], 'https://tool.example/launch')
        self.assertIsNone(data['client_id'])
        self.assertFalse(data['tool_key_configured'])
        self.assertEqual(data['registration_urls'], {})
        self.assertNotIn('not-for-display', str(data))

    def test_lti13_detail_renders_without_generating_passport_keys(self):
        passport = Lti1p3Passport.objects.create(lti_1p3_client_id='render-client')
        configuration = ReusableLtiConfiguration.objects.create(
            name='Advantage',
            version=ReusableLtiConfiguration.LTI_1P3,
            context_type='site',
            lti_1p3_launch_url='https://tool.example/launch',
            lti_1p3_oidc_url='https://tool.example/oidc',
            lti_1p3_client_id='render-client',
            lti_1p3_deployment_id='render-deployment',
            lti_1p3_tool_key_mode='keyset_url',
            lti_1p3_passport=passport,
        )
        data = ReusableDetailSerializer(configuration, context={'can_manage': True}).data
        self.assertEqual(set(data), DETAIL_RESPONSE_FIELDS)
        self.assertTrue(data['tool_key_configured'])
        self.assertEqual(data['tool_key_mode'], 'keyset_url')
        self.assertEqual(data['context'], {'type': 'site'})
        self.assertEqual(
            set(data['registration_urls']), {'login_url', 'jwks_url', 'access_token_url'},
        )
        passport.refresh_from_db()
        self.assertEqual(passport.lti_1p3_internal_private_key, '')
        self.assertEqual(passport.lti_1p3_internal_public_jwk, '')

    def test_create_response_renders_one_time_credentials_only_when_present(self):
        with_credentials = ReusableCreateResponseSerializer(self.configuration, context={
            'can_manage': True,
            'one_time_credentials': {'client_key': 'k', 'client_secret': 's'},
        }).data
        self.assertEqual(with_credentials['one_time_credentials'], {'client_key': 'k', 'client_secret': 's'})

        without_credentials = ReusableCreateResponseSerializer(
            self.configuration, context={'can_manage': True, 'one_time_credentials': None},
        ).data
        self.assertNotIn('one_time_credentials', without_credentials)
