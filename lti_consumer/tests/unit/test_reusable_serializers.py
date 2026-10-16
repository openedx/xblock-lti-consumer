"""Unit tests for reusable configuration request validation.

Create happy paths, response allowlists, and end-to-end PATCH behavior are
covered by the API journeys; these tests keep the dense validation rules and
the merged-state logic that would be expensive to reach exhaustively through
one request per case.
"""
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from lti_consumer.plugin.reusable_serializers import (
    ReusableContextInputSerializer,
    ReusableCreateInputSerializer,
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


def lti11_payload(**overrides):
    """Return a valid minimal LTI 1.1 create payload."""
    payload = {
        'name': '  Example Tool  ',
        'version': 'lti_1p1',
        'context': course_context(),
        'lti_1p1': {'launch_url': 'https://tool.example/launch'},
    }
    payload.update(overrides)
    return payload


def lti13_payload(**overrides):
    """Return a valid LTI 1.3 create payload, with optional connection-field overrides."""
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
    """Create-only context normalization and organization registry policy."""

    def test_normalizes_course_keys_before_the_length_check(self):
        serializer = ReusableContextInputSerializer(data=course_context(f' {COURSE_KEY}+branch@draft '))
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data, course_context())

        raw_key = f'{COURSE_KEY}+branch@' + 'a' * 300
        self.assertGreater(len(raw_key), 255)
        serializer = ReusableContextInputSerializer(data=course_context(raw_key))
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data, course_context())

        ccx_key = 'ccx-v1:Org+Course+Run+ccx@1'
        serializer = ReusableContextInputSerializer(data=course_context(ccx_key))
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data, course_context(ccx_key))

    @patch(REGISTRY_PATCH)
    def test_organizations_resolve_against_the_registry_but_course_and_site_do_not(self, get_organizations):
        get_organizations.return_value = [{'short_name': 'Org-A'}]
        serializer = ReusableContextInputSerializer(data=organization_context(' ORG-A '))
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data, organization_context('org-a'))

        cases = (
            ('unknown-org', [{'short_name': 'Other-Org'}]),
            ('org-a', [{'short_name': 'Org-A'}, {'short_name': 'org-a'}]),
        )
        for key, registry in cases:
            with self.subTest(key=key):
                get_organizations.return_value = registry
                self.assertFalse(ReusableContextInputSerializer(data=organization_context(key)).is_valid())

        get_organizations.side_effect = AssertionError('course and site must not consult the registry')
        self.assertTrue(ReusableContextInputSerializer(data=course_context()).is_valid())
        self.assertTrue(ReusableContextInputSerializer(data=site_context()).is_valid())

    def test_rejects_invalid_context_shapes(self):
        oversized_course_key = 'course-v1:' + 'o' * 250 + '+C+R'
        invalid = (
            {'type': 'course'},
            {'type': 'course', 'key': ''},
            {'type': 'course', 'key': '   '},
            {'type': 'course', 'key': None},
            {'type': 'course', 'key': 123},
            {'type': ['course'], 'key': COURSE_KEY},
            {'type': 'course', 'key': 'course-v1:version@519665f6223ebd6980884f2b'},
            {'type': 'course', 'key': oversized_course_key},
            {'type': 'organization', 'key': 'o' * 256},
            {'type': 'unknown', 'key': COURSE_KEY},
            {'type': 'site', 'key': ''},
            {'type': 'site', 'key': COURSE_KEY},
            {'type': 'course', 'key': COURSE_KEY, 'extra': True},
            {'course_keys': [COURSE_KEY]},
            {'site_wide': True},
            'course-v1:Org+Course+Run',
            [{'type': 'course', 'key': COURSE_KEY}],
            [],
        )
        for data in invalid:
            with self.subTest(data=data):
                self.assertFalse(ReusableContextInputSerializer(data=data).is_valid())


class ReusableCreateInputSerializerTests(SimpleTestCase):
    """Dense create payload validation; create happy paths belong to the API journeys."""

    def test_rejects_unknown_fields_and_version_section_mismatch(self):
        missing_context = lti11_payload()
        missing_context.pop('context')
        cases = (
            lti11_payload(extra='no'),
            lti11_payload(context={'type': 'course', 'key': COURSE_KEY, 'owner': 'someone'}),
            lti11_payload(lti_1p1={'launch_url': 'https://tool.example/launch', 'private_key': 'secret'}),
            lti11_payload(services={'deep_linking_enabled': False, 'platform_key': 'secret'}),
            lti11_payload(defaults={'not_a_setting': True}),
            lti11_payload(scope={'course_keys': [COURSE_KEY]}),
            missing_context,
            lti11_payload(lti_1p3={'launch_url': 'https://tool.example/launch'}),
            lti11_payload(version='lti_1p3'),
        )
        for payload in cases:
            with self.subTest(payload=payload):
                self.assertFalse(ReusableCreateInputSerializer(data=payload).is_valid())

    def test_validates_urls_key_material_and_default_ranges(self):
        for name in ('', '   ', 'x' * 256):
            with self.subTest(name_length=len(name)):
                self.assertFalse(ReusableCreateInputSerializer(data=lti11_payload(name=name)).is_valid())

        self.assertFalse(ReusableCreateInputSerializer(data=lti11_payload(
            lti_1p1={'launch_url': 'javascript:alert(1)'},
        )).is_valid())
        self.assertFalse(ReusableCreateInputSerializer(data=lti13_payload(
            lti_1p3={'redirect_uris': ['']},
        )).is_valid())

        deep_link = lti13_payload(services={'deep_linking_enabled': True})
        self.assertFalse(ReusableCreateInputSerializer(data=deep_link).is_valid())
        deep_link['services']['deep_linking_launch_url'] = 'https://tool.example/deep-link'
        self.assertTrue(ReusableCreateInputSerializer(data=deep_link).is_valid())
        deep_link['services']['deep_linking_launch_url'] = ''
        self.assertFalse(ReusableCreateInputSerializer(data=deep_link).is_valid())
        self.assertTrue(ReusableCreateInputSerializer(data=lti11_payload(
            services={'deep_linking_launch_url': ''},
        )).is_valid())

        private_key = lti13_payload(lti_1p3={
            'tool_key_mode': 'public_key',
            'tool_public_key': '-----BEGIN PRIVATE KEY----- nope',
        })
        self.assertFalse(ReusableCreateInputSerializer(data=private_key).is_valid())
        public_key = lti13_payload(lti_1p3={
            'tool_key_mode': 'public_key',
            'tool_public_key': '-----BEGIN PUBLIC KEY----- key',
        })
        self.assertTrue(ReusableCreateInputSerializer(data=public_key).is_valid())

        prefix = 'https://tool.example/'
        rejected_keyset = lti13_payload(lti_1p3={
            'tool_keyset_url': prefix + 'k' * (501 - len(prefix)),
        })
        self.assertFalse(ReusableCreateInputSerializer(data=rejected_keyset).is_valid())

        invalid_defaults = (
            {'custom_parameters': ['missing-equals']},
            {'custom_parameters': ['=missing-key']},
            {'grade_weight': float('nan')},
            {'modal_width': 101},
            {'inline_height': 2147483648},
        )
        for defaults in invalid_defaults:
            with self.subTest(defaults=defaults):
                self.assertFalse(ReusableCreateInputSerializer(data=lti11_payload(defaults=defaults)).is_valid())
        self.assertTrue(ReusableCreateInputSerializer(data=lti11_payload(
            defaults={'inline_height': 2147483647},
        )).is_valid())


class ReusableUpdateInputSerializerTests(TestCase):
    """PATCH validation always validates the complete resulting state."""

    def setUp(self):
        payload = lti13_payload(name='Patch validation')
        payload['lti_1p3']['redirect_uris'] = ['https://tool.example/redirect']
        self.configuration = create_reusable_configuration(payload).configuration

    def validate_patch(self, data):
        serializer = ReusableUpdateInputSerializer(
            data=data, partial=True, context={'configuration': self.configuration},
        )
        return serializer.is_valid(), serializer

    def test_rejects_context_scope_version_and_immutable_identity(self):
        cases = (
            {'context': course_context()},
            {'context': {'type': 'site'}},
            {'scope': {'course_keys': [COURSE_KEY]}},
            {'name': 'Changed', 'context': course_context()},
            {'context': course_context(), 'scope': {}},
            {'launch_url': 'https://tool.example/new'},
            {'lti_1p1': {'launch_url': 'https://tool.example/new'}},
            {'lti_1p3': {'client_id': 'replacement'}},
            {'lti_1p3': {'deployment_id': 'replacement'}},
        )
        for payload in cases:
            with self.subTest(payload=payload):
                valid, serializer = self.validate_patch(payload)
                self.assertFalse(valid)
                if {'context', 'scope'}.intersection(payload):
                    self.assertTrue({'context', 'scope'}.intersection(serializer.errors))

    def test_merges_redirects_and_revalidates_stored_state(self):
        valid, serializer = self.validate_patch({
            'lti_1p3': {'redirect_uris': [], 'launch_url': 'https://tool.example/new-launch'},
            'services': {'deep_linking_launch_url': 'https://tool.example/deep'},
        })
        self.assertTrue(valid, serializer.errors)
        self.assertEqual(serializer.validated_data['lti_1p3']['redirect_uris'], [])

        valid, serializer = self.validate_patch({
            'lti_1p3': {'redirect_uris': ['https://only.example/callback']},
        })
        self.assertTrue(valid, serializer.errors)
        self.assertEqual(
            serializer.validated_data['lti_1p3']['redirect_uris'], ['https://only.example/callback'],
        )

        valid, serializer = self.validate_patch({'lti_1p3': {'launch_url': 'https://tool.example/new'}})
        self.assertTrue(valid, serializer.errors)
        self.assertNotIn('redirect_uris', serializer.validated_data['lti_1p3'])
        self.assertNotIn('lti_1p3', self.validate_patch({'name': 'metadata only'})[1].validated_data)

        for field, value in (
            ('lti_1p3_launch_url', 'javascript:bad'),
            ('lti_1p3_oidc_url', 'javascript:bad'),
            ('lti_1p3_redirect_uris', ['javascript:bad']),
        ):
            with self.subTest(field=field):
                original = getattr(self.configuration, field)
                setattr(self.configuration, field, value)
                self.assertFalse(self.validate_patch({'name': 'change'})[0])
                setattr(self.configuration, field, original)

    def test_merges_tool_key_mode_and_services_state(self):
        public_key = '-----BEGIN PUBLIC KEY----- public material'
        valid, serializer = self.validate_patch({
            'lti_1p3': {'tool_key_mode': 'public_key', 'tool_public_key': public_key},
        })
        self.assertTrue(valid, serializer.errors)
        self.assertEqual(serializer.validated_data['lti_1p3']['tool_key_mode'], 'public_key')

        for connection in (
            {'tool_key_mode': 'public_key'},
            {'tool_key_mode': 'public_key', 'tool_public_key': '-----BEGIN PRIVATE KEY----- private'},
            {'tool_public_key': public_key},
        ):
            with self.subTest(connection=connection):
                self.assertFalse(self.validate_patch({'lti_1p3': connection})[0])

        valid, serializer = self.validate_patch({
            'lti_1p3': {'tool_key_mode': 'keyset_url', 'tool_keyset_url': 'https://new.example/jwks'},
        })
        self.assertTrue(valid, serializer.errors)
        self.assertEqual(serializer.validated_data['lti_1p3']['tool_keyset_url'], 'https://new.example/jwks')

        prefix = 'https://tool.example/'
        accepted_url = prefix + 'k' * (300 - len(prefix))
        rejected_url = prefix + 'k' * (501 - len(prefix))
        self.assertTrue(self.validate_patch({
            'lti_1p3': {'tool_key_mode': 'keyset_url', 'tool_keyset_url': accepted_url},
        })[0])
        self.assertFalse(self.validate_patch({
            'lti_1p3': {'tool_key_mode': 'keyset_url', 'tool_keyset_url': rejected_url},
        })[0])

        self.configuration.lti_advantage_deep_linking_launch_url = ''
        self.assertFalse(self.validate_patch({'services': {'deep_linking_enabled': True}})[0])
        self.configuration.lti_advantage_deep_linking_launch_url = 'javascript:bad'
        self.assertFalse(self.validate_patch({'name': 'disabled with invalid stored URL'})[0])
        self.configuration.lti_advantage_deep_linking_launch_url = 'https://tool.example/deep'
        self.assertTrue(self.validate_patch({'services': {'deep_linking_enabled': True}})[0])
        self.assertFalse(self.validate_patch({'services': {
            'deep_linking_enabled': True, 'deep_linking_launch_url': 'javascript:bad',
        }})[0])
