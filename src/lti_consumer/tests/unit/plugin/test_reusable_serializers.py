"""Adapter contract tests for the reusable configuration wire serializers.

These pin what the HTTP adapters own and only that: primitive wire conversion,
generic unknown-member refusal, and safe response allowlists. Semantic rules
(validity, authority, merged stored state) live in `lti_consumer.reusable` and
`lti_consumer.reusable_context` and are not asserted here.
"""
from django.test import SimpleTestCase, TestCase, override_settings

from lti_consumer.models import ReusableLtiConfiguration
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
DEFAULT_RESPONSE_FIELDS = {
    'display_name', 'enable_grading', 'grade_weight', 'accept_grades_after_due_date',
    'open_tool_in', 'inline_height', 'modal_height', 'modal_width', 'launch_button_text',
    'send_extra_parameters', 'custom_parameters', 'hide_external_tool',
}
PRIVACY_RESPONSE_FIELDS = {
    'share_username', 'share_full_name', 'share_email', 'data_sharing_notice',
    'require_user_confirmation',
}
DETAIL_RESPONSE_FIELDS = LIST_RESPONSE_FIELDS | DEFAULT_RESPONSE_FIELDS | {
    'description', 'launch_url', 'oidc_url', 'redirect_uris', 'tool_key_mode',
    'tool_key_configured', 'client_id', 'deployment_id', 'registration_urls',
    'deep_linking_launch_url', 'privacy',
}
SECRET_MATERIAL = (
    'lti_1p1_client_key', 'lti_1p1_client_secret', 'lti_1p1-key', 'lti_1p1-secret',
    'lti_1p3_internal_private_key', 'PRIVATE KEY MATERIAL',
    'lti_1p3_internal_public_jwk', 'PUBLIC JWK MATERIAL',
    'lti_1p3_tool_public_key', 'TOOL PUBLIC KEY MATERIAL',
)


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
    """Return a wire-valid LTI 1.3 create payload with optional connection overrides."""
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
    """Create input parsing converts primitives and refuses unknown members only."""

    def test_converts_wire_primitives_without_injecting_defaults(self):
        serializer = ReusableCreateInputSerializer(data=lti13_payload(
            description=None,
            lti_1p3={'redirect_uris': ['https://tool.example/callback']},
            services={'deep_linking_enabled': 'true', 'deep_linking_launch_url': None},
            defaults={'inline_height': '900', 'grade_weight': '2.5', 'enable_grading': 'true'},
            privacy={'share_username': 'true', 'require_user_confirmation': 'false'},
        ))
        self.assertTrue(serializer.is_valid(), serializer.errors)
        validated = serializer.validated_data
        self.assertIsNone(validated['description'])
        self.assertEqual(validated['context'], {'type': 'site'})
        self.assertEqual(validated['lti_1p3']['redirect_uris'], ['https://tool.example/callback'])
        self.assertEqual(validated['services'], {
            'deep_linking_enabled': True,
            'deep_linking_launch_url': None,
        })
        # Only the supplied members appear: no defaults are injected at the wire layer.
        self.assertEqual(validated['defaults'], {
            'inline_height': 900,
            'grade_weight': 2.5,
            'enable_grading': True,
        })
        self.assertEqual(validated['privacy'], {
            'share_username': True,
            'require_user_confirmation': False,
        })

    def test_keeps_false_zero_empty_collections_blank_strings_and_empty_sections(self):
        serializer = ReusableCreateInputSerializer(data=lti11_payload(
            description='',
            services={},
            defaults={
                'enable_grading': False,
                'grade_weight': 0,
                'custom_parameters': [],
                'launch_button_text': '',
                'hide_external_tool': False,
            },
            privacy={'share_email': False, 'data_sharing_notice': ''},
        ))
        self.assertTrue(serializer.is_valid(), serializer.errors)
        validated = serializer.validated_data
        self.assertEqual(validated['description'], '')
        self.assertEqual(validated['services'], {})
        self.assertEqual(validated['defaults'], {
            'enable_grading': False,
            'grade_weight': 0.0,
            'custom_parameters': [],
            'launch_button_text': '',
            'hide_external_tool': False,
        })
        self.assertEqual(validated['privacy'], {'share_email': False, 'data_sharing_notice': ''})

    def test_omitted_optional_sections_stay_absent(self):
        serializer = ReusableCreateInputSerializer(data=lti11_payload())
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(set(serializer.validated_data), {'name', 'version', 'context', 'lti_1p1'})

    def test_refuses_unknown_members_at_every_level(self):
        cases = (
            lti11_payload(scope={'course_keys': [COURSE_KEY]}),
            lti11_payload(context={'type': 'course', 'key': COURSE_KEY, 'owner': 'someone'}),
            lti11_payload(lti_1p1={'launch_url': 'https://tool.example/launch', 'private_key': 'p'}),
            lti11_payload(services={'platform_key': 'p'}),
            lti11_payload(defaults={'not_a_setting': True}),
            lti11_payload(privacy={'pii_share_username': True}),
            lti11_payload(privacy={'not_a_setting': True}),
            lti13_payload(lti_1p3={'unsupported_member': 'x'}),
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
            lti13_payload(privacy={'share_username': 7}),
        )
        for payload in invalid:
            with self.subTest(payload=payload):
                self.assertFalse(ReusableCreateInputSerializer(data=payload).is_valid())

    def test_leaves_semantic_rules_to_the_service(self):
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
    """PATCH parsing never reads stored state and never enforces domain rules."""

    def test_parses_primitives_without_stored_state(self):
        serializer = ReusableUpdateInputSerializer(data={
            'name': 'Renamed',
            'description': None,
            'lti_1p3': {'redirect_uris': ['https://tool.example/cb'], 'tool_key_mode': 'keyset_url'},
            'services': {'nrps_enabled': 'false'},
            'defaults': {'grade_weight': '3', 'modal_width': '50'},
            'privacy': {'data_sharing_notice': 'Read this'},
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        validated = serializer.validated_data
        self.assertIsNone(validated['description'])
        self.assertEqual(validated['lti_1p3'], {
            'redirect_uris': ['https://tool.example/cb'],
            'tool_key_mode': 'keyset_url',
        })
        self.assertEqual(validated['services'], {'nrps_enabled': False})
        self.assertEqual(validated['defaults'], {'grade_weight': 3.0, 'modal_width': 50})
        self.assertEqual(validated['privacy'], {'data_sharing_notice': 'Read this'})

    def test_accepts_an_empty_patch_and_empty_sections(self):
        empty = ReusableUpdateInputSerializer(data={})
        self.assertTrue(empty.is_valid(), empty.errors)
        self.assertEqual(empty.validated_data, {})

        empty_sections = ReusableUpdateInputSerializer(data={'lti_1p1': {}, 'services': {}, 'defaults': {}})
        self.assertTrue(empty_sections.is_valid(), empty_sections.errors)
        self.assertEqual(
            empty_sections.validated_data,
            {'lti_1p1': {}, 'services': {}, 'defaults': {}},
        )

    def test_keeps_false_zero_empty_collections_and_blank_strings(self):
        serializer = ReusableUpdateInputSerializer(data={'defaults': {
            'enable_grading': False,
            'inline_height': 0,
            'custom_parameters': [],
            'launch_button_text': '',
            'hide_external_tool': False,
        }})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['defaults'], {
            'enable_grading': False,
            'inline_height': 0,
            'custom_parameters': [],
            'launch_button_text': '',
            'hide_external_tool': False,
        })

    def test_accepts_the_one_time_context_and_version_members(self):
        serializer = ReusableUpdateInputSerializer(data={'context': {'type': 'site'}, 'version': 'lti_1p3'})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data, {'context': {'type': 'site'}, 'version': 'lti_1p3'})

    def test_refuses_an_unsupported_version_member(self):
        serializer = ReusableUpdateInputSerializer(data={'version': 'lti_2p0'})
        self.assertFalse(serializer.is_valid())
        self.assertIn('version', serializer.errors)

    def test_refuses_unknown_and_immutable_members(self):
        cases = (
            {'scope': {'course_keys': [COURSE_KEY]}},
            {'config_id': '00000000-0000-0000-0000-000000000000'},
            {'client_id': 'replacement'},
            {'lti_1p1': {'client_key': 'rotated'}},
            {'lti_1p1': {'client_secret': 'rotated'}},
            {'lti_1p3': {'client_id': 'replacement'}},
            {'lti_1p3': {'deployment_id': 'replacement'}},
            {'privacy': {'pii_share_email': True}},
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
            {'privacy': {'require_user_confirmation': 7}},
        )
        for payload in invalid:
            with self.subTest(payload=payload):
                self.assertFalse(ReusableUpdateInputSerializer(data=payload).is_valid())


class RenderingTests(TestCase):
    """List/detail rendering is allowlisted, null-safe and secret-free."""

    def setUp(self):
        self.lti11 = ReusableLtiConfiguration.objects.create(
            name='Rendered',
            version=ReusableLtiConfiguration.LTI_1P1,
            context_type='course',
            context_key=COURSE_KEY,
            lti_1p1_launch_url='https://tool.example/launch',
            lti_1p1_client_key='lti_1p1-key',
            lti_1p1_client_secret='lti_1p1-secret',
            lti_1p3_internal_private_key='PRIVATE KEY MATERIAL',
            lti_1p3_internal_public_jwk='PUBLIC JWK MATERIAL',
        )

    def assert_no_secret_material(self, data):
        rendered = str(data)
        for marker in SECRET_MATERIAL:
            self.assertNotIn(marker, rendered)

    def test_list_rendering_is_allowlisted_and_secret_free(self):
        data = ReusableListSerializer(self.lti11, context={'can_manage': True}).data
        self.assertEqual(set(data), LIST_RESPONSE_FIELDS)
        self.assertEqual(data['context'], {'type': 'course', 'key': COURSE_KEY})
        self.assertTrue(data['can_manage'])
        self.assert_no_secret_material(data)

    def test_list_rendering_accepts_a_callable_manage_check(self):
        def check(obj):
            return obj.pk == self.lti11.pk

        data = ReusableListSerializer(self.lti11, context={'can_manage': check}).data
        self.assertTrue(data['can_manage'])

    def test_detail_rendering_is_allowlisted_with_nested_privacy_and_flat_defaults(self):
        data = ReusableDetailSerializer(self.lti11, context={'can_manage': False}).data
        self.assertEqual(set(data), DETAIL_RESPONSE_FIELDS)
        self.assertEqual(set(data['privacy']), PRIVACY_RESPONSE_FIELDS)
        for member in DEFAULT_RESPONSE_FIELDS:
            self.assertIn(member, data)
        self.assertFalse(data['can_manage'])
        self.assertEqual(data['launch_url'], 'https://tool.example/launch')
        self.assertIsNone(data['client_id'])
        self.assertFalse(data['tool_key_configured'])
        self.assertEqual(data['registration_urls'], {})
        self.assertNotIn('is_active', data)
        self.assert_no_secret_material(data)

    def test_context_is_null_when_unassigned_regardless_of_version(self):
        unassigned = (
            ReusableLtiConfiguration.objects.create(name='Unassigned', version=None),
            ReusableLtiConfiguration.objects.create(name='Unassigned 1.3', version='lti_1p3'),
        )
        for configuration in unassigned:
            with self.subTest(version=configuration.version):
                listed = ReusableListSerializer(
                    configuration, context={'can_manage': True},
                ).data
                detailed = ReusableDetailSerializer(
                    configuration, context={'can_manage': True},
                ).data
                self.assertIsNone(listed['context'])
                self.assertIsNone(detailed['context'])

    def test_unknown_version_renders_stored_1p3_metadata_without_inference(self):
        configuration = ReusableLtiConfiguration.objects.create(
            name='Copied 1.3',
            version=None,
            lti_1p3_client_id='copied-client',
            lti_1p3_deployment_id='copied-deployment',
            lti_1p3_oidc_url='https://tool.example/oidc',
            lti_1p3_redirect_uris=['https://tool.example/cb'],
            lti_1p3_tool_public_key='TOOL PUBLIC KEY MATERIAL',
        )
        data = ReusableDetailSerializer(configuration, context={'can_manage': True}).data
        self.assertIsNone(data['version'])
        self.assertIsNone(data['launch_url'])
        self.assertEqual(data['registration_urls'], {})
        self.assertEqual(data['client_id'], 'copied-client')
        self.assertEqual(data['deployment_id'], 'copied-deployment')
        self.assertEqual(data['oidc_url'], 'https://tool.example/oidc')
        self.assertEqual(data['redirect_uris'], ['https://tool.example/cb'])
        self.assertTrue(data['tool_key_configured'])
        self.assert_no_secret_material(data)

    def test_unknown_version_tool_key_configured_is_presence_only(self):
        without_key = ReusableLtiConfiguration.objects.create(
            name='No key',
            version=None,
            lti_1p3_tool_public_key='',
            lti_1p3_tool_keyset_url='',
        )
        with_keyset = ReusableLtiConfiguration.objects.create(
            name='Keyset',
            version=None,
            lti_1p3_tool_keyset_url='http://not-a-valid-url',
        )
        self.assertFalse(ReusableDetailSerializer(without_key).data['tool_key_configured'])
        self.assertTrue(ReusableDetailSerializer(with_keyset).data['tool_key_configured'])

    def test_known_lti11_gates_version_specific_metadata(self):
        configuration = ReusableLtiConfiguration.objects.create(
            name='Gated 1.1',
            version='lti_1p1',
            lti_1p1_launch_url='https://tool.example/launch',
            lti_1p3_oidc_url='https://tool.example/oidc',
            lti_1p3_client_id='stray-client',
            lti_1p3_deployment_id='stray-deployment',
            lti_1p3_redirect_uris=['https://tool.example/cb'],
            lti_1p3_tool_keyset_url='https://tool.example/jwks',
        )
        data = ReusableDetailSerializer(configuration).data
        self.assertEqual(data['launch_url'], 'https://tool.example/launch')
        self.assertIsNone(data['oidc_url'])
        self.assertIsNone(data['client_id'])
        self.assertIsNone(data['deployment_id'])
        self.assertEqual(data['redirect_uris'], [])
        self.assertFalse(data['tool_key_configured'])
        self.assertEqual(data['registration_urls'], {})

    def test_known_lti13_renders_stored_metadata_and_uuid_registration_urls(self):
        configuration = ReusableLtiConfiguration.objects.create(
            name='Known 1.3',
            version='lti_1p3',
            context_type='site',
            lti_1p3_launch_url='https://tool.example/launch',
            lti_1p3_oidc_url='https://tool.example/oidc',
            lti_1p3_redirect_uris=['https://tool.example/cb'],
            lti_1p3_client_id='known-client',
            lti_1p3_deployment_id='known-deployment',
            lti_1p3_tool_key_mode='keyset_url',
            lti_1p3_tool_keyset_url='https://tool.example/jwks',
        )
        data = ReusableDetailSerializer(configuration).data
        self.assertEqual(data['client_id'], 'known-client')
        self.assertEqual(data['deployment_id'], 'known-deployment')
        self.assertEqual(data['tool_key_mode'], 'keyset_url')
        self.assertTrue(data['tool_key_configured'])
        self.assertEqual(data['registration_urls'], {
            'login_url': 'https://example.com/api/lti_consumer/v1/launch/',
            'jwks_url': (
                'https://example.com/api/lti_consumer/v1/public_keysets/'
                f'{configuration.passport_id}'
            ),
            'access_token_url': (
                'https://example.com/api/lti_consumer/v1/token/'
                f'{configuration.passport_id}'
            ),
        })

    @override_settings(LTI_BASE='https://view.example', LTI_API_BASE='https://api.example')
    def test_registration_urls_honour_base_precedence(self):
        configuration = ReusableLtiConfiguration.objects.create(
            name='Bases',
            version='lti_1p3',
            lti_1p3_tool_public_key='TOOL PUBLIC KEY MATERIAL',
        )
        urls = ReusableDetailSerializer(configuration).data['registration_urls']
        self.assertEqual(urls['login_url'], 'https://view.example/api/lti_consumer/v1/launch/')
        self.assertEqual(
            urls['jwks_url'],
            f'https://api.example/api/lti_consumer/v1/public_keysets/{configuration.passport_id}',
        )
        self.assertEqual(
            urls['access_token_url'],
            f'https://api.example/api/lti_consumer/v1/token/{configuration.passport_id}',
        )

    def test_reading_never_generates_signing_material(self):
        detail = ReusableDetailSerializer(self.lti11).data
        listed = ReusableListSerializer(self.lti11).data
        self.assertEqual(detail['config_id'], str(self.lti11.passport_id))
        self.assertEqual(listed['config_id'], str(self.lti11.passport_id))
        self.lti11.refresh_from_db()
        self.assertEqual(self.lti11.lti_1p3_internal_private_key, 'PRIVATE KEY MATERIAL')
        self.assertEqual(self.lti11.lti_1p3_internal_public_jwk, 'PUBLIC JWK MATERIAL')

        blank = ReusableLtiConfiguration.objects.create(name='Blank keys', version='lti_1p3')
        blank_detail = ReusableDetailSerializer(blank).data
        self.assertEqual(blank_detail['config_id'], str(blank.passport_id))
        self.assertFalse(blank_detail['tool_key_configured'])
        blank.refresh_from_db()
        self.assertEqual(blank.lti_1p3_internal_private_key, '')
        self.assertEqual(blank.lti_1p3_internal_public_jwk, '')

    def test_create_response_renders_one_time_credentials_only_when_present(self):
        with_credentials = ReusableCreateResponseSerializer(self.lti11, context={
            'can_manage': True,
            'one_time_credentials': {'client_key': 'k', 'client_secret': 's'},
        }).data
        self.assertEqual(with_credentials['one_time_credentials'], {'client_key': 'k', 'client_secret': 's'})

        without_credentials = ReusableCreateResponseSerializer(
            self.lti11, context={'can_manage': True, 'one_time_credentials': None},
        ).data
        self.assertNotIn('one_time_credentials', without_credentials)
