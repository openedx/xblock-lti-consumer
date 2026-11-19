"""Focused adapter rules not covered by the reusable configuration HTTP journeys.

Unknown members are refused at every level and PATCH versions are allowlisted.
"""
from django.test import SimpleTestCase

from lti_consumer.plugin.reusable_serializers import (
    ReusableCreateInputSerializer,
    ReusableUpdateInputSerializer,
)

COURSE_KEY = 'course-v1:Org+Course+Run'


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
    """Return a wire-valid minimal LTI 1.3 create payload with optional connection overrides."""
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


class StrictWireAllowlistTests(SimpleTestCase):
    """Unknown members are refused at every level and PATCH versions are allowlisted."""

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

    def test_refuses_an_unsupported_version_member(self):
        serializer = ReusableUpdateInputSerializer(data={'version': 'lti_2p0'})
        self.assertFalse(serializer.is_valid())
        self.assertIn('version', serializer.errors)
