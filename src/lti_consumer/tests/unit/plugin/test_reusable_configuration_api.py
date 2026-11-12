"""HTTP journeys for the CMS reusable configuration API.

Each journey drives the real APIClient, URLconf, serializers, mutation module,
Creation Context policy, ORM and database. Only edx-platform owned boundaries
are patched: Global Staff, course admin, Studio course access and the
organization registry. Semantic matrices stay in the service and serializer
suites; these journeys keep the HTTP status, disclosure, ordering, pagination,
CSRF, method and rollback contract.
"""
import uuid
from unittest.mock import patch
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import NoReverseMatch, Resolver404, resolve, reverse
from rest_framework.test import APIClient

from lti_consumer.apps import LTIConsumerApp
from lti_consumer.models import ReusableLtiConfiguration
from lti_consumer.reusable import create_reusable_configuration

COURSE_KEY = 'course-v1:Org+Course+Run'
OTHER_COURSE_KEY = 'course-v1:Other+Course+Run'
CMS_URLCONF = 'lti_consumer.tests.unit.plugin.urls_cms'
LMS_URLCONF = 'lti_consumer.tests.unit.plugin.urls_lms'
LIST_PATH = '/api/lti_consumer/v1/configurations'
CSRF_COOKIE_SECRET = 'a' * 32
STORED_CLIENT_KEY = 'stored-client-key-not-for-the-wire'
STORED_CLIENT_SECRET = 'stored-client-secret-not-for-the-wire'
COPIED_RAW_CONTEXT_KEY = 'legacy-passport-context-key'
COPIED_CLIENT_ID = 'copied-client-id'
COPIED_DEPLOYMENT_ID = 'copied-deployment-id'
LTI11_LAUNCH_URL = 'https://tool.example/launch'
LTI13_LAUNCH_URL = 'https://tool.example/launch'
LTI13_OIDC_URL = 'https://tool.example/oidc'
TOOL_KEYSET_URL = 'https://tool.example/jwks'
TOOL_PUBLIC_KEY = '-----BEGIN PUBLIC KEY----- tool key material'
REGISTRATION_FIELDS = frozenset({'login_url', 'jwks_url', 'access_token_url'})

COMPAT_HELPERS = (
    'get_active_organizations',
    'user_is_global_staff',
    'user_is_course_admin',
    'get_studio_accessible_course_keys',
)

LIST_FIELDS = frozenset({
    'config_id', 'name', 'version', 'context', 'created_at', 'updated_at', 'can_manage',
    'deep_linking_enabled', 'ags_mode', 'nrps_enabled',
})
PRIVACY_FIELDS = frozenset({
    'share_username', 'share_full_name', 'share_email', 'data_sharing_notice', 'require_user_confirmation',
})
DEFAULT_FIELDS = frozenset({
    'display_name', 'enable_grading', 'grade_weight', 'accept_grades_after_due_date', 'open_tool_in',
    'inline_height', 'modal_height', 'modal_width', 'launch_button_text', 'send_extra_parameters',
    'custom_parameters', 'hide_external_tool',
})
DETAIL_FIELDS = LIST_FIELDS | DEFAULT_FIELDS | frozenset({
    'privacy', 'description', 'launch_url', 'oidc_url', 'redirect_uris', 'tool_key_mode',
    'tool_key_configured', 'client_id', 'deployment_id', 'registration_urls', 'deep_linking_launch_url',
})
AUTHORED_DEFAULTS = {
    'display_name': 'Authored default',
    'enable_grading': True,
    'grade_weight': 2.5,
    'accept_grades_after_due_date': False,
    'open_tool_in': 'new_window',
    'inline_height': 900,
    'modal_height': 70,
    'modal_width': 60,
    'launch_button_text': 'Launch it',
    'send_extra_parameters': True,
    'custom_parameters': ['alpha=1', 'beta=2'],
    'hide_external_tool': True,
}
AUTHORED_PRIVACY = {
    'share_username': True,
    'share_full_name': True,
    'share_email': True,
    'data_sharing_notice': 'Hand-written sharing notice',
    'require_user_confirmation': False,
}
AUTHORED_SERVICES = {
    'deep_linking_enabled': False,
    'ags_mode': 'programmatic',
    'nrps_enabled': True,
}


def lti11_payload(context=None, **overrides):
    """Return a minimal LTI 1.1 create payload; overrides replace top-level members."""
    payload = {
        'name': 'Journey tool',
        'version': 'lti_1p1',
        'context': context if context is not None else {'type': 'course', 'key': COURSE_KEY},
        'lti_1p1': {'launch_url': LTI11_LAUNCH_URL},
    }
    payload.update(overrides)
    return payload


def lti13_payload(context=None, **overrides):
    """Return a minimal LTI 1.3 create payload; overrides replace top-level members."""
    payload = {
        'name': 'Journey tool',
        'version': 'lti_1p3',
        'context': context if context is not None else {'type': 'site'},
        'lti_1p3': {
            'launch_url': LTI13_LAUNCH_URL,
            'oidc_url': LTI13_OIDC_URL,
            'tool_key_mode': 'keyset_url',
            'tool_keyset_url': TOOL_KEYSET_URL,
        },
    }
    payload.update(overrides)
    return payload


def converted_row(**overrides):
    """Create a converted row: copied raw context key, no context type and no version."""
    values = {
        'name': 'Copied passport',
        'version': None,
        'context_type': None,
        'context_key': COPIED_RAW_CONTEXT_KEY,
        'lti_1p3_client_id': COPIED_CLIENT_ID,
        'lti_1p3_deployment_id': COPIED_DEPLOYMENT_ID,
        'lti_1p3_oidc_url': LTI13_OIDC_URL,
        'lti_1p3_redirect_uris': ['https://tool.example/redirect'],
        'lti_1p3_tool_keyset_url': TOOL_KEYSET_URL,
    }
    values.update(overrides)
    return ReusableLtiConfiguration.objects.create(**values)


class PlatformBoundaryMixin:
    """Patch only the platform adapters; the real policy, service and ORM run.

    Global Staff, course admin, Studio course access and the organization
    registry are stubbed as platform facts. The real policy still performs
    eligibility, shaping, normalization, visibility and manage authority.
    """

    def setUp(self):
        super().setUp()
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(username='global-staff', is_staff=True)
        self.manager = user_model.objects.create_user(username='course-manager')
        self.viewer = user_model.objects.create_user(username='viewer')
        self.inactive = user_model.objects.create_user(username='inactive', is_active=False)
        self.course_managers = {self.manager.username}
        self.accessible_keys = {
            self.manager.username: [COURSE_KEY],
            self.viewer.username: [COURSE_KEY],
        }
        self.platform = {}
        for name in COMPAT_HELPERS:
            patcher = patch(f'lti_consumer.plugin.compat.{name}', autospec=True)
            self.platform[name] = patcher.start()
            self.addCleanup(patcher.stop)
        self.platform['user_is_global_staff'].side_effect = (
            lambda user: bool(getattr(user, 'is_staff', False))
        )
        self.platform['user_is_course_admin'].side_effect = self._is_course_admin
        self.platform['get_studio_accessible_course_keys'].side_effect = self._accessible_course_keys
        self.platform['get_active_organizations'].return_value = [{'short_name': 'SomeOrg'}]
        self.client = APIClient()

    def _is_course_admin(self, user, course_key):
        """Return whether this actor is a course manager of the journey course."""
        return getattr(user, 'username', None) in self.course_managers and str(course_key) == COURSE_KEY

    def _accessible_course_keys(self, user):
        """Return the Studio-accessible course keys stubbed for this actor."""
        return self.accessible_keys.get(getattr(user, 'username', None), [])

    def login(self, user=None):
        """Authenticate the shared client with a real session."""
        self.client.force_login(user or self.staff)

    def detail_path(self, configuration):
        """Return the wire detail path of one configuration."""
        return f'{LIST_PATH}/{configuration.passport_id}'

    def create_configuration(self, name='Fixture tool', context=None, version='lti_1p1', **overrides):
        """Persist a configuration through the real service for read and update journeys."""
        if version == 'lti_1p1':
            data = {
                'name': name,
                'version': version,
                'context': context if context is not None else {'type': 'course', 'key': COURSE_KEY},
                'lti_1p1': {
                    'launch_url': LTI11_LAUNCH_URL,
                    'client_key': STORED_CLIENT_KEY,
                    'client_secret': STORED_CLIENT_SECRET,
                },
            }
        else:
            data = {
                'name': name,
                'version': version,
                'context': context if context is not None else {'type': 'site'},
                'lti_1p3': {
                    'launch_url': LTI13_LAUNCH_URL,
                    'oidc_url': LTI13_OIDC_URL,
                    'tool_key_mode': 'keyset_url',
                    'tool_keyset_url': TOOL_KEYSET_URL,
                },
            }
        for key, value in overrides.items():
            if isinstance(value, dict) and isinstance(data.get(key), dict):
                data[key].update(value)
            else:
                data[key] = value
        return create_reusable_configuration(self.staff, data).configuration

    def bulk_course_configurations(self, count, name_format='Tool {index:03d}'):
        """Insert many course configurations directly; list journeys need no service write."""
        return ReusableLtiConfiguration.objects.bulk_create([
            ReusableLtiConfiguration(
                name=name_format.format(index=index),
                version='lti_1p1',
                context_type='course',
                context_key=COURSE_KEY,
                lti_1p1_launch_url=LTI11_LAUNCH_URL,
            )
            for index in range(count)
        ])

    def assert_cache_no_store(self, response):
        """Assert the management response must never be cached."""
        self.assertEqual(response['Cache-Control'], 'no-store', response.content)

    def assert_field_error(self, response, field):
        """Assert a 400 whose body addresses one dotted wire member."""
        self.assertEqual(response.status_code, 400, response.content)
        node = response.json()
        for part in field.split('.'):
            self.assertIsInstance(node, dict, response.content)
            self.assertIn(part, node, response.content)
            node = node[part]
        self.assertTrue(node, f'no message addressed to {field}: {response.content!r}')

    def assert_detail_shape(self, body, expected=None):
        """Assert the allowlisted detail members and privacy rendering."""
        self.assertEqual(set(body), DETAIL_FIELDS if expected is None else expected)
        self.assertEqual(set(body['privacy']), PRIVACY_FIELDS)

    def assert_secrets_absent(self, response, *values):
        """Assert no stored secret appears in the wire response."""
        content = response.content.decode()
        for value in values:
            self.assertNotIn(value, content)


@override_settings(ROOT_URLCONF=CMS_URLCONF)
class ReusableApiTestCase(PlatformBoundaryMixin, TestCase):
    """CMS-mounted API journeys sharing the patched platform boundaries."""


class CreateJourneyTests(ReusableApiTestCase):
    """Create journeys: one-time credentials, rendered metadata and refusals."""

    def test_lti_1p1_create_discloses_credentials_once(self):
        self.login(self.manager)
        response = self.client.post(LIST_PATH, lti11_payload(
            name='  Created tool  ',
            privacy=AUTHORED_PRIVACY,
            defaults=AUTHORED_DEFAULTS,
            services=AUTHORED_SERVICES,
        ), format='json')

        self.assertEqual(response.status_code, 201, response.content)
        self.assert_cache_no_store(response)
        body = response.json()
        self.assert_detail_shape(body, DETAIL_FIELDS | {'one_time_credentials'})
        credentials = body['one_time_credentials']
        self.assertEqual(set(credentials), {'client_key', 'client_secret'})
        self.assertTrue(credentials['client_key'] and credentials['client_secret'])
        self.assertEqual(body['name'], 'Created tool')
        self.assertEqual(body['context'], {'type': 'course', 'key': COURSE_KEY})
        self.assertEqual(body['launch_url'], LTI11_LAUNCH_URL)
        self.assertEqual(body['registration_urls'], {})
        self.assertTrue(body['can_manage'])
        self.assertEqual(body['privacy'], AUTHORED_PRIVACY)
        for key, value in {**AUTHORED_DEFAULTS, **AUTHORED_SERVICES}.items():
            self.assertEqual(body[key], value, key)

        configuration = ReusableLtiConfiguration.objects.get(passport_id=body['config_id'])
        for field, value in (
            ('display_name', AUTHORED_DEFAULTS['display_name']),
            ('custom_parameters', AUTHORED_DEFAULTS['custom_parameters']),
            ('hide_external_tool', True),
            ('pii_share_email', True),
            ('data_sharing_notice', AUTHORED_PRIVACY['data_sharing_notice']),
            ('lti_advantage_ags_mode', 'programmatic'),
            ('lti_advantage_enable_nrps', True),
        ):
            self.assertEqual(getattr(configuration, field), value, field)
        self.assertEqual(configuration.lti_1p1_client_key, credentials['client_key'])
        self.assertEqual(configuration.lti_1p1_client_secret, credentials['client_secret'])
        # The generated secret appears exactly once, inside one_time_credentials.
        self.assertEqual(response.content.decode().count(credentials['client_secret']), 1)
        self.assertEqual(response.content.decode().count('one_time_credentials'), 1)

        detail = self.client.get(self.detail_path(configuration))
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertNotIn('one_time_credentials', detail.json())
        self.assert_secrets_absent(detail, credentials['client_key'], credentials['client_secret'])

        updated = self.client.patch(self.detail_path(configuration), {'name': 'Renamed'}, format='json')
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertNotIn('one_time_credentials', updated.json())
        self.assert_secrets_absent(updated, credentials['client_key'], credentials['client_secret'])

    def test_lti_1p3_create_renders_registration_and_keeps_platform_key_secret(self):
        self.login(self.staff)
        response = self.client.post(LIST_PATH, lti13_payload(name='Tool 1.3'), format='json')

        self.assertEqual(response.status_code, 201, response.content)
        self.assert_cache_no_store(response)
        body = response.json()
        self.assert_detail_shape(body)
        self.assertNotIn('one_time_credentials', body)
        self.assertEqual(body['version'], 'lti_1p3')
        self.assertEqual(body['tool_key_mode'], 'keyset_url')
        self.assertTrue(body['tool_key_configured'])
        self.assertTrue(body['client_id'])
        self.assertTrue(body['deployment_id'])
        self.assertEqual(body['redirect_uris'], [])
        self.assertEqual(body['oidc_url'], LTI13_OIDC_URL)
        self.assertEqual(set(body['registration_urls']), REGISTRATION_FIELDS)
        self.assertIn(body['config_id'], body['registration_urls']['jwks_url'])
        self.assertIn(body['config_id'], body['registration_urls']['access_token_url'])
        self.assertEqual(
            urlparse(body['registration_urls']['login_url']).path,
            '/api/lti_consumer/v1/launch/',
        )

        configuration = ReusableLtiConfiguration.objects.get(passport_id=body['config_id'])
        self.assertTrue(configuration.lti_1p3_internal_private_key)
        self.assert_secrets_absent(
            response,
            configuration.lti_1p3_internal_private_key,
            configuration.lti_1p3_internal_public_jwk,
            TOOL_KEYSET_URL,
        )

    def test_create_refusals_write_nothing_and_stay_non_disclosing(self):
        self.login(self.viewer)
        forbidden = self.client.post(LIST_PATH, lti11_payload(name='Denied tool'), format='json')
        self.assertEqual(forbidden.status_code, 403, forbidden.content)
        self.assertEqual(forbidden.content, b'')
        self.assert_cache_no_store(forbidden)

        self.login(self.staff)
        read_only = self.client.post(LIST_PATH, lti11_payload(is_active=True), format='json')
        self.assert_field_error(read_only, 'is_active')
        self.assert_cache_no_store(read_only)

        nested_unknown = self.client.post(
            LIST_PATH,
            lti11_payload(**{'lti_1p1': {'launch_url': LTI11_LAUNCH_URL, 'id_token': 'smuggled'}}),
            format='json',
        )
        self.assert_field_error(nested_unknown, 'lti_1p1.id_token')
        self.assert_cache_no_store(nested_unknown)

        incomplete = self.client.post(
            LIST_PATH,
            lti13_payload(**{'lti_1p3': {'launch_url': LTI13_LAUNCH_URL, 'oidc_url': LTI13_OIDC_URL}}),
            format='json',
        )
        self.assert_field_error(incomplete, 'lti_1p3.tool_key_mode')
        self.assert_cache_no_store(incomplete)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 0)


class ListJourneyTests(ReusableApiTestCase):
    """List journeys: allowlisted rows, scope, pagination and filters."""

    def test_list_rows_are_allowlisted_and_limited_to_visible_contexts(self):
        course_row = self.create_configuration(name='Course tool')
        hidden_row = self.create_configuration(
            name='Hidden tool', context={'type': 'course', 'key': OTHER_COURSE_KEY},
        )
        organization_row = self.create_configuration(
            name='Org tool', context={'type': 'organization', 'key': 'SomeOrg'},
        )
        site_row = self.create_configuration(name='Site tool', context={'type': 'site'})
        lti13_row = self.create_configuration(name='Tool 1.3', version='lti_1p3')
        self.login(self.viewer)

        response = self.client.get(LIST_PATH)

        self.assertEqual(response.status_code, 200, response.content)
        self.assert_cache_no_store(response)
        body = response.json()
        self.assertEqual(set(body), {'count', 'next', 'previous', 'results'})
        self.assertEqual(body['count'], 3)
        self.assertEqual([row['name'] for row in body['results']], ['Course tool', 'Site tool', 'Tool 1.3'])
        self.assertEqual(
            {row['config_id'] for row in body['results']},
            {str(course_row.passport_id), str(site_row.passport_id), str(lti13_row.passport_id)},
        )
        for row in body['results']:
            self.assertEqual(set(row), LIST_FIELDS)
            self.assertFalse(row['can_manage'])
        contexts = {row['name']: row['context'] for row in body['results']}
        self.assertEqual(contexts['Course tool'], {'type': 'course', 'key': COURSE_KEY})
        self.assertEqual(contexts['Site tool'], {'type': 'site'})
        self.assert_secrets_absent(response, STORED_CLIENT_KEY, STORED_CLIENT_SECRET)
        self.assertNotIn(str(hidden_row.passport_id), response.content.decode())
        self.assertNotIn(str(organization_row.passport_id), response.content.decode())

    def test_list_pagination_bounds_page_size_cap_and_page_errors(self):
        self.bulk_course_configurations(105)
        self.login(self.staff)

        first = self.client.get(LIST_PATH)
        self.assertEqual(first.status_code, 200, first.content)
        self.assert_cache_no_store(first)
        body = first.json()
        self.assertEqual(body['count'], 105)
        self.assertEqual(len(body['results']), 20)
        self.assertIsNotNone(body['next'])
        self.assertIsNone(body['previous'])
        self.assertEqual(body['results'][0]['name'], 'Tool 000')

        second = self.client.get(LIST_PATH, {'page': 2}).json()
        self.assertEqual(len(second['results']), 20)
        self.assertIsNotNone(second['previous'])
        self.assertEqual(second['results'][0]['name'], 'Tool 020')

        last = self.client.get(LIST_PATH, {'page': 6}).json()
        self.assertEqual(len(last['results']), 5)
        self.assertIsNone(last['next'])

        small = self.client.get(LIST_PATH, {'page_size': 5})
        self.assertEqual(len(small.json()['results']), 5)

        capped = self.client.get(LIST_PATH, {'page_size': 100})
        self.assert_cache_no_store(capped)
        self.assertEqual(len(capped.json()['results']), 100)
        self.assertIsNotNone(capped.json()['next'])

        over_max = self.client.get(LIST_PATH, {'page_size': 500})
        self.assert_cache_no_store(over_max)
        self.assertEqual(len(over_max.json()['results']), 100)

        invalid_page = self.client.get(LIST_PATH, {'page': 'not-a-number'})
        self.assertEqual(invalid_page.status_code, 404, invalid_page.content)
        self.assert_cache_no_store(invalid_page)

        past_end = self.client.get(LIST_PATH, {'page': 99})
        self.assertEqual(past_end.status_code, 404, past_end.content)
        self.assert_cache_no_store(past_end)

    def test_list_orders_by_name_then_primary_key(self):
        first = ReusableLtiConfiguration.objects.create(
            name='Twin', version='lti_1p1', context_type='course', context_key=COURSE_KEY,
            lti_1p1_launch_url=LTI11_LAUNCH_URL,
        )
        second = ReusableLtiConfiguration.objects.create(
            name='Twin', version='lti_1p1', context_type='course', context_key=COURSE_KEY,
            lti_1p1_launch_url=LTI11_LAUNCH_URL,
        )
        self.bulk_course_configurations(1, name_format='Aaa first')
        self.login(self.staff)

        results = self.client.get(LIST_PATH).json()['results']

        self.assertEqual([row['name'] for row in results], ['Aaa first', 'Twin', 'Twin'])
        self.assertEqual(
            [row['config_id'] for row in results[1:]],
            [str(first.passport_id), str(second.passport_id)],
        )

    def test_list_filters_unknown_queries_and_invalid_keys(self):
        self.create_configuration(name='Alpha tool')
        self.create_configuration(
            name='Beta tool', version='lti_1p3', context={'type': 'course', 'key': COURSE_KEY},
        )
        self.create_configuration(name='Org tool', context={'type': 'organization', 'key': 'SomeOrg'})
        self.create_configuration(name='Site tool', context={'type': 'site'})
        self.login(self.staff)

        everything = self.client.get(LIST_PATH).json()
        self.assertEqual(everything['count'], 4)
        ignored = self.client.get(LIST_PATH, {'nonsense': 'ignored'}).json()
        self.assertEqual(ignored['count'], everything['count'])

        by_course = self.client.get(LIST_PATH, {'course_key': COURSE_KEY})
        self.assertEqual(by_course.status_code, 200, by_course.content)
        self.assert_cache_no_store(by_course)
        self.assertEqual(
            {row['name'] for row in by_course.json()['results']},
            {'Alpha tool', 'Beta tool', 'Site tool'},
        )

        by_type = self.client.get(LIST_PATH, {'context_type': 'organization'})
        self.assertEqual([row['name'] for row in by_type.json()['results']], ['Org tool'])

        by_search = self.client.get(LIST_PATH, {'search': 'alpha'})
        self.assertEqual([row['name'] for row in by_search.json()['results']], ['Alpha tool'])

        by_version = self.client.get(LIST_PATH, {'version': 'lti_1p3'})
        self.assertEqual([row['name'] for row in by_version.json()['results']], ['Beta tool'])

        bad_course_key = self.client.get(LIST_PATH, {'course_key': 'not-a-course-key'})
        self.assert_field_error(bad_course_key, 'course_key')
        self.assert_cache_no_store(bad_course_key)

        bad_context_type = self.client.get(LIST_PATH, {'context_type': 'planet'})
        self.assert_field_error(bad_context_type, 'context_type')
        self.assert_cache_no_store(bad_context_type)

        self.login(self.viewer)
        self.accessible_keys[self.viewer.username] = []
        lost_access = self.client.get(LIST_PATH)
        self.assertEqual(lost_access.status_code, 200, lost_access.content)
        self.assertEqual(lost_access.json()['count'], 0)


class DetailAndPatchJourneyTests(ReusableApiTestCase):
    """Detail and PATCH journeys: rendering, merging, immutability and no writes."""

    def test_detail_renders_privacy_and_defaults_without_touching_keys(self):
        configuration = self.create_configuration(
            name='Everything tool',
            version='lti_1p3',
            services={
                'deep_linking_enabled': True,
                'deep_linking_launch_url': 'https://tool.example/deep-link',
                'ags_mode': 'programmatic',
                'nrps_enabled': True,
            },
            defaults=AUTHORED_DEFAULTS,
            privacy=AUTHORED_PRIVACY,
        )
        self.login(self.staff)
        updated_at = ReusableLtiConfiguration.objects.get(pk=configuration.pk).updated_at

        with patch.object(
            ReusableLtiConfiguration, 'generate_lti_1p3_keys_if_missing',
            side_effect=AssertionError('read generated platform keys'),
        ), patch.object(
            ReusableLtiConfiguration, 'save', side_effect=AssertionError('read wrote a row'),
        ):
            response = self.client.get(self.detail_path(configuration))

        self.assertEqual(response.status_code, 200, response.content)
        self.assert_cache_no_store(response)
        body = response.json()
        self.assert_detail_shape(body)
        for field in DEFAULT_FIELDS:
            self.assertEqual(body[field], AUTHORED_DEFAULTS[field], field)
        self.assertEqual(body['privacy'], AUTHORED_PRIVACY)
        self.assertTrue(body['deep_linking_enabled'])
        self.assertEqual(body['deep_linking_launch_url'], 'https://tool.example/deep-link')
        self.assertEqual(body['ags_mode'], 'programmatic')
        self.assertTrue(body['nrps_enabled'])
        self.assertTrue(body['tool_key_configured'])
        self.assertEqual(body['tool_key_mode'], 'keyset_url')
        self.assertEqual(body['redirect_uris'], [])
        self.assertEqual(set(body['registration_urls']), REGISTRATION_FIELDS)
        for forbidden in ('pii_', 'lti_1p3_', 'client_secret', 'private_key'):
            self.assertNotIn(forbidden, response.content.decode())
        self.assert_secrets_absent(response, TOOL_KEYSET_URL, TOOL_PUBLIC_KEY)
        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=configuration.pk).updated_at, updated_at)

    def test_lti_1p1_detail_gates_lti_1p3_metadata(self):
        configuration = self.create_configuration(name='One one')
        ReusableLtiConfiguration.objects.filter(pk=configuration.pk).update(
            lti_1p3_oidc_url=LTI13_OIDC_URL,
            lti_1p3_client_id='stray-client',
            lti_1p3_deployment_id='stray-deployment',
            lti_1p3_redirect_uris=['https://tool.example/cb'],
            lti_1p3_tool_keyset_url=TOOL_KEYSET_URL,
        )
        self.login(self.staff)

        response = self.client.get(self.detail_path(configuration))

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assert_detail_shape(body)
        self.assertEqual(body['launch_url'], LTI11_LAUNCH_URL)
        self.assertIsNone(body['oidc_url'])
        self.assertIsNone(body['client_id'])
        self.assertIsNone(body['deployment_id'])
        self.assertEqual(body['redirect_uris'], [])
        self.assertFalse(body['tool_key_configured'])
        self.assertEqual(body['registration_urls'], {})
        self.assert_secrets_absent(response, STORED_CLIENT_KEY, STORED_CLIENT_SECRET)

    def test_patch_updates_ordinary_settings_and_preserves_identity(self):
        configuration = self.create_configuration(
            name='Before',
            version='lti_1p3',
            services={'ags_mode': 'declarative', 'nrps_enabled': True},
            defaults={'display_name': 'Before default', 'grade_weight': 2.0, 'hide_external_tool': True},
            privacy=AUTHORED_PRIVACY,
        )
        identity = {
            field: getattr(configuration, field)
            for field in (
                'passport_id', 'version', 'context_type', 'context_key',
                'lti_1p3_client_id', 'lti_1p3_deployment_id', 'lti_1p3_tool_keyset_url', 'created_at',
            )
        }
        self.login(self.staff)

        with patch.object(
            ReusableLtiConfiguration, 'generate_lti_1p3_keys_if_missing',
            side_effect=AssertionError('patch generated platform keys'),
        ):
            response = self.client.patch(self.detail_path(configuration), {
                'name': 'After',
                'description': 'Updated description',
                'lti_1p3': {'launch_url': 'https://tool.example/launch-2'},
                'services': {'ags_mode': 'programmatic'},
                'defaults': {'display_name': 'After default', 'inline_height': 1200},
                'privacy': {'share_email': False, 'require_user_confirmation': True},
            }, format='json')

        self.assertEqual(response.status_code, 200, response.content)
        self.assert_cache_no_store(response)
        body = response.json()
        self.assert_detail_shape(body)
        self.assertNotIn('one_time_credentials', body)
        self.assertEqual(body['name'], 'After')
        self.assertEqual(body['description'], 'Updated description')
        self.assertEqual(body['launch_url'], 'https://tool.example/launch-2')
        self.assertEqual(body['ags_mode'], 'programmatic')
        self.assertTrue(body['nrps_enabled'])
        self.assertEqual(body['display_name'], 'After default')
        self.assertEqual(body['inline_height'], 1200)
        self.assertEqual(body['grade_weight'], 2.0)
        self.assertTrue(body['hide_external_tool'])
        self.assertEqual(body['privacy'], {
            'share_username': True,
            'share_full_name': True,
            'share_email': False,
            'data_sharing_notice': 'Hand-written sharing notice',
            'require_user_confirmation': True,
        })

        configuration.refresh_from_db()
        for field, value in identity.items():
            self.assertEqual(getattr(configuration, field), value, field)
        self.assertIsNone(configuration.lti_1p1_client_key)

    def test_patch_updates_lti_1p1_launch_url_and_keeps_credentials(self):
        configuration = self.create_configuration(name='One one')
        self.login(self.staff)

        response = self.client.patch(self.detail_path(configuration), {
            'name': 'One one renamed',
            'lti_1p1': {'launch_url': 'https://tool.example/launch-2'},
        }, format='json')

        self.assertEqual(response.status_code, 200, response.content)
        self.assert_cache_no_store(response)
        body = response.json()
        self.assert_detail_shape(body)
        self.assertEqual(body['name'], 'One one renamed')
        self.assertEqual(body['launch_url'], 'https://tool.example/launch-2')
        configuration.refresh_from_db()
        self.assertEqual(configuration.lti_1p1_client_key, STORED_CLIENT_KEY)
        self.assertEqual(configuration.lti_1p1_client_secret, STORED_CLIENT_SECRET)

    def test_patch_refuses_identity_credentials_and_read_only_members(self):
        lti11 = self.create_configuration(name='One one')
        lti13 = self.create_configuration(name='One three', version='lti_1p3')
        stored = {
            field: getattr(lti13, field)
            for field in ('name', 'version', 'context_type', 'context_key', 'updated_at')
        }
        stored_lti13_identity = (lti13.lti_1p3_client_id, lti13.lti_1p3_deployment_id)
        self.login(self.staff)

        cases = (
            (self.detail_path(lti13), {'context': {'type': 'site'}}, 'context'),
            (self.detail_path(lti13), {'version': 'lti_1p1'}, 'version'),
            (self.detail_path(lti13), {'lti_1p1': {'launch_url': LTI11_LAUNCH_URL}}, 'lti_1p1'),
            (self.detail_path(lti13), {'lti_1p3': {'client_id': 'smuggled'}}, 'lti_1p3.client_id'),
            (self.detail_path(lti13), {'lti_1p3': {'deployment_id': 'smuggled'}}, 'lti_1p3.deployment_id'),
            (self.detail_path(lti13), {'is_active': False}, 'is_active'),
            (self.detail_path(lti13), {'config_id': str(uuid.uuid4())}, 'config_id'),
            (self.detail_path(lti13), {'passport_id': str(uuid.uuid4())}, 'passport_id'),
            (self.detail_path(lti11), {'lti_1p1': {'client_key': 'smuggled'}}, 'lti_1p1.client_key'),
            (self.detail_path(lti11), {'lti_1p1': {'client_secret': 'smuggled'}}, 'lti_1p1.client_secret'),
        )
        for path, payload, field in cases:
            response = self.client.patch(path, payload, format='json')
            self.assert_field_error(response, field)
            self.assert_cache_no_store(response)

        lti13.refresh_from_db()
        lti11.refresh_from_db()
        for field, value in stored.items():
            self.assertEqual(getattr(lti13, field), value, field)
        self.assertEqual((lti13.lti_1p3_client_id, lti13.lti_1p3_deployment_id), stored_lti13_identity)
        self.assertEqual(lti11.lti_1p1_client_key, STORED_CLIENT_KEY)
        self.assertEqual(lti11.lti_1p1_client_secret, STORED_CLIENT_SECRET)

    def test_patch_validates_supplied_sections_against_stored_state(self):
        configuration = self.create_configuration(name='Merged', version='lti_1p3')
        self.login(self.staff)

        empty_section = self.client.patch(
            self.detail_path(configuration), {'lti_1p3': {}}, format='json',
        )
        self.assertEqual(empty_section.status_code, 200, empty_section.content)
        self.assertEqual(empty_section.json()['tool_key_mode'], 'keyset_url')
        self.assertTrue(empty_section.json()['tool_key_configured'])

        cases = (
            ({'lti_1p3': {'tool_key_mode': 'public_key'}}, 'lti_1p3.tool_public_key'),
            ({'defaults': {'custom_parameters': ['missing-equals']}}, 'defaults.custom_parameters'),
            ({'services': {'ags_mode': 'nonsense'}}, 'services.ags_mode'),
            ({'defaults': {'modal_width': 500}}, 'defaults.modal_width'),
        )
        for payload, field in cases:
            response = self.client.patch(self.detail_path(configuration), payload, format='json')
            self.assert_field_error(response, field)
            self.assert_cache_no_store(response)

        configuration.refresh_from_db()
        self.assertEqual(configuration.lti_1p3_tool_key_mode, 'keyset_url')
        self.assertEqual(configuration.modal_width, 80)
        self.assertEqual(configuration.open_tool_in, 'iframe')

    def test_patch_failure_keeps_stored_row(self):
        configuration = self.create_configuration(name='Stable', version='lti_1p3')
        updated_at = configuration.updated_at
        self.login(self.staff)

        response = self.client.patch(
            self.detail_path(configuration),
            {'name': 'Renamed', 'defaults': {'grade_weight': -1}},
            format='json',
        )

        self.assert_field_error(response, 'defaults.grade_weight')
        self.assert_cache_no_store(response)
        configuration.refresh_from_db()
        self.assertEqual(configuration.name, 'Stable')
        self.assertEqual(configuration.updated_at, updated_at)

    def test_converted_row_context_and_version_are_assigned_once(self):
        converted = converted_row()
        self.login(self.staff)

        detail = self.client.get(self.detail_path(converted))
        self.assertEqual(detail.status_code, 200, detail.content)
        body = detail.json()
        self.assert_detail_shape(body)
        self.assertIsNone(body['version'])
        self.assertIsNone(body['context'])
        self.assertIsNone(body['launch_url'])
        self.assertEqual(body['registration_urls'], {})
        self.assertEqual(body['client_id'], COPIED_CLIENT_ID)
        self.assertEqual(body['deployment_id'], COPIED_DEPLOYMENT_ID)
        self.assertEqual(body['oidc_url'], LTI13_OIDC_URL)
        self.assertEqual(body['redirect_uris'], ['https://tool.example/redirect'])
        self.assertTrue(body['tool_key_configured'])
        self.assertNotIn(COPIED_RAW_CONTEXT_KEY, detail.content.decode())

        listed = self.client.get(LIST_PATH)
        self.assertEqual(listed.json()['count'], 1)
        self.assertIsNone(listed.json()['results'][0]['context'])
        self.assertNotIn(COPIED_RAW_CONTEXT_KEY, listed.content.decode())

        assigned = self.client.patch(
            self.detail_path(converted), {'context': {'type': 'course', 'key': COURSE_KEY}}, format='json',
        )
        self.assertEqual(assigned.status_code, 200, assigned.content)
        self.assertEqual(assigned.json()['context'], {'type': 'course', 'key': COURSE_KEY})
        self.assertIsNone(assigned.json()['version'])
        converted.refresh_from_db()
        self.assertEqual(converted.context_type, 'course')
        self.assertEqual(converted.context_key, COURSE_KEY)

        combined = self.client.patch(
            self.detail_path(converted),
            {'context': {'type': 'site'}, 'version': 'lti_1p1'},
            format='json',
        )
        self.assert_field_error(combined, 'context')
        self.assert_cache_no_store(combined)
        converted.refresh_from_db()
        self.assertIsNone(converted.version)
        self.assertEqual(converted.context_type, 'course')

        versioned = self.client.patch(self.detail_path(converted), {'version': 'lti_1p3'}, format='json')
        self.assertEqual(versioned.status_code, 200, versioned.content)
        self.assertEqual(versioned.json()['version'], 'lti_1p3')

        replaced = self.client.patch(self.detail_path(converted), {'version': 'lti_1p1'}, format='json')
        self.assert_field_error(replaced, 'version')

        reassigned = self.client.patch(
            self.detail_path(converted), {'context': {'type': 'site'}}, format='json',
        )
        self.assert_field_error(reassigned, 'context')

    def test_unassigned_row_is_hidden_from_non_staff(self):
        converted = converted_row()
        self.login(self.viewer)

        self.assertEqual(self.client.get(self.detail_path(converted)).status_code, 404)
        self.assertEqual(self.client.get(LIST_PATH).json()['count'], 0)
        refused = self.client.patch(
            self.detail_path(converted), {'context': {'type': 'course', 'key': COURSE_KEY}}, format='json',
        )
        self.assertEqual(refused.status_code, 404, refused.content)
        converted.refresh_from_db()
        self.assertIsNone(converted.context_type)
        self.assertEqual(converted.context_key, COPIED_RAW_CONTEXT_KEY)


class AuthorityAndErrorTests(ReusableApiTestCase):
    """Authority and error journeys: ordering, disclosure and status mapping."""

    def test_hidden_and_missing_targets_are_indistinguishable(self):
        hidden = self.create_configuration(
            name='Hidden tool', context={'type': 'course', 'key': OTHER_COURSE_KEY},
        )
        missing = uuid.uuid4()
        self.login(self.viewer)

        for path in (self.detail_path(hidden), f'{LIST_PATH}/{missing}'):
            missing_detail = self.client.get(path)
            self.assertEqual(missing_detail.status_code, 404, missing_detail.content)
            self.assertIn('detail', missing_detail.json())
            self.assert_cache_no_store(missing_detail)

            missing_patch = self.client.patch(path, {'name': 'Renamed'}, format='json')
            self.assertEqual(missing_patch.status_code, 404, missing_patch.content)
            self.assert_cache_no_store(missing_patch)

            # A malformed body is refused before any lookup, so the target stays hidden.
            malformed = self.client.patch(path, {'unknown_member': 1}, format='json')
            self.assert_field_error(malformed, 'unknown_member')
            self.assert_cache_no_store(malformed)

            # A semantic error is refused after the lookup, which is still a 404.
            semantic = self.client.patch(path, {'name': ''}, format='json')
            self.assertEqual(semantic.status_code, 404, semantic.content)
            self.assert_cache_no_store(semantic)
            for response in (missing_detail, missing_patch, malformed, semantic):
                self.assertNotIn('Hidden tool', response.content.decode())
                self.assert_secrets_absent(response, STORED_CLIENT_KEY, STORED_CLIENT_SECRET)

    def test_visible_nonmanager_reads_but_cannot_manage(self):
        configuration = self.create_configuration(name='Visible tool')
        self.login(self.viewer)

        detail = self.client.get(self.detail_path(configuration))
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertFalse(detail.json()['can_manage'])

        refused = self.client.patch(self.detail_path(configuration), {'name': 'Renamed'}, format='json')
        self.assertEqual(refused.status_code, 403, refused.content)
        self.assertEqual(refused.content, b'')
        self.assert_cache_no_store(refused)

        refused_semantic = self.client.patch(self.detail_path(configuration), {'name': ''}, format='json')
        self.assertEqual(refused_semantic.status_code, 403, refused_semantic.content)
        self.assert_cache_no_store(refused_semantic)

        self.course_managers.add(self.viewer.username)
        allowed = self.client.patch(self.detail_path(configuration), {'name': 'Renamed'}, format='json')
        self.assertEqual(allowed.status_code, 200, allowed.content)
        self.assertTrue(allowed.json()['can_manage'])

        invalid = self.client.patch(self.detail_path(configuration), {'name': ''}, format='json')
        self.assert_field_error(invalid, 'name')
        self.assert_cache_no_store(invalid)

    def test_unauthenticated_and_inactive_accounts_reach_no_view(self):
        configuration = self.create_configuration(name='Private tool')
        self.client.logout()

        unauthenticated = (
            self.client.get(LIST_PATH),
            self.client.post(LIST_PATH, lti11_payload(), format='json'),
            self.client.get(self.detail_path(configuration)),
            self.client.patch(self.detail_path(configuration), {'name': 'Renamed'}, format='json'),
        )
        for response in unauthenticated:
            self.assertEqual(response.status_code, 403, response.content)
            self.assert_cache_no_store(response)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 1)

        for helper in self.platform.values():
            helper.reset_mock()
        self.login(self.inactive)
        inactive_list = self.client.get(LIST_PATH)
        self.assertEqual(inactive_list.status_code, 403, inactive_list.content)
        self.assert_cache_no_store(inactive_list)
        for helper in ('user_is_global_staff', 'user_is_course_admin',
                       'get_studio_accessible_course_keys', 'get_active_organizations'):
            self.assert_not_called(helper)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 1)

    def assert_not_called(self, helper):
        """Assert one patched platform adapter was never consulted."""
        self.platform[helper].assert_not_called()

    def test_session_csrf_is_enforced(self):
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.force_login(self.staff)

        refused = csrf_client.post(LIST_PATH, lti11_payload(name='CSRF tool'), format='json')
        self.assertEqual(refused.status_code, 403, refused.content)
        self.assert_cache_no_store(refused)
        self.assertFalse(ReusableLtiConfiguration.objects.filter(name='CSRF tool').exists())

        csrf_client.cookies[settings.CSRF_COOKIE_NAME] = CSRF_COOKIE_SECRET
        accepted = csrf_client.post(
            LIST_PATH, lti11_payload(name='CSRF tool'), format='json',
            HTTP_X_CSRFTOKEN=CSRF_COOKIE_SECRET,
        )
        self.assertEqual(accepted.status_code, 201, accepted.content)
        self.assert_cache_no_store(accepted)

    def test_method_and_options_handling(self):
        configuration = self.create_configuration(name='Methods tool')
        detail_path = self.detail_path(configuration)
        self.login(self.staff)

        head = self.client.head(LIST_PATH)
        self.assertEqual(head.status_code, 200, head.content)
        self.assert_cache_no_store(head)

        options = self.client.options(detail_path)
        self.assertEqual(options.status_code, 200, options.content)
        self.assert_cache_no_store(options)
        self.assertIn('PATCH', options['Allow'])
        self.assertNotIn('PUT', options['Allow'])

        for path in (LIST_PATH, detail_path):
            put = self.client.put(path, {'name': 'Renamed'}, format='json')
            self.assertEqual(put.status_code, 405, put.content)
            self.assert_cache_no_store(put)
            self.assertNotIn('PUT', put.get('Allow', ''))

            delete = self.client.delete(path)
            self.assertEqual(delete.status_code, 405, delete.content)
            self.assert_cache_no_store(delete)
            self.assertNotIn('DELETE', delete.get('Allow', ''))


@override_settings(ROOT_URLCONF=CMS_URLCONF)
class CreateRollbackTests(PlatformBoundaryMixin, TransactionTestCase):
    """A failed LTI 1.3 create rolls the inserted row back in a real transaction."""

    def test_lti_1p3_create_conflict_returns_400_without_field_and_rolls_back(self):
        self.login(self.staff)

        with patch.object(
            ReusableLtiConfiguration, 'generate_lti_1p3_keys_if_missing',
            side_effect=IntegrityError('duplicate key value'),
        ):
            response = self.client.post(LIST_PATH, lti13_payload(name='Conflict tool'), format='json')

        self.assertEqual(response.status_code, 400, response.content)
        self.assert_cache_no_store(response)
        body = response.json()
        self.assertIsInstance(body, list)
        self.assertTrue(body)
        self.assertFalse(ReusableLtiConfiguration.objects.filter(name='Conflict tool').exists())
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 0)

    def test_failed_lti_1p3_create_leaves_no_row(self):
        self.login(self.staff)
        self.client.raise_request_exception = False

        with patch.object(
            ReusableLtiConfiguration, 'generate_lti_1p3_keys_if_missing',
            side_effect=RuntimeError('platform key generation failed'),
        ):
            response = self.client.post(LIST_PATH, lti13_payload(name='Rollback tool'), format='json')

        self.assertGreaterEqual(response.status_code, 500, response.content)
        self.assertFalse(ReusableLtiConfiguration.objects.filter(name='Rollback tool').exists())
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 0)


@override_settings(ROOT_URLCONF=CMS_URLCONF)
class CmsMountTests(SimpleTestCase):
    """The CMS mount exposes the management routes under the plugin namespace only."""

    def test_management_routes_use_the_plugin_namespace(self):
        for path in (LIST_PATH, f'{LIST_PATH}/{uuid.uuid4()}'):
            self.assertEqual(resolve(path).namespace, 'lti_consumer')

    def test_lms_routes_are_absent_from_the_cms_mount(self):
        for path in (
            '/api/lti_consumer/v1/launch/',
            f'/api/lti_consumer/v1/public_keysets/{uuid.uuid4()}',
            f'/api/lti_consumer/v1/token/{uuid.uuid4()}',
        ):
            with self.assertRaises(Resolver404):
                resolve(path)

    def test_app_registration_declares_both_mounts(self):
        url_config = LTIConsumerApp.plugin_app['url_config']
        self.assertEqual(url_config['cms.djangoapp'], {
            'namespace': 'lti_consumer',
            'regex': '^api/',
            'relative_path': 'plugin.reusable_urls',
        })
        self.assertEqual(url_config['lms.djangoapp'], {
            'namespace': 'lti_consumer',
            'regex': '^api/',
            'relative_path': 'plugin.urls',
        })


@override_settings(ROOT_URLCONF=LMS_URLCONF)
class LmsMountTests(SimpleTestCase):
    """The LMS mount keeps its endpoints and names after the CMS registration."""

    def test_lms_routes_keep_their_names_and_prefix(self):
        passport_id = uuid.uuid4()
        self.assertEqual(
            reverse('lti_consumer:lti_consumer.public_keyset_endpoint', kwargs={'passport_id': passport_id}),
            f'/api/lti_consumer/v1/public_keysets/{passport_id}',
        )
        self.assertEqual(
            reverse('lti_consumer:lti_consumer.access_token', kwargs={'passport_id': passport_id}),
            f'/api/lti_consumer/v1/token/{passport_id}',
        )
        self.assertEqual(
            reverse('lti_consumer:lti_consumer.launch_gate'),
            '/api/lti_consumer/v1/launch/',
        )

    def test_management_routes_are_absent_from_the_lms_mount(self):
        with self.assertRaises(Resolver404):
            resolve(LIST_PATH)


class RegistrationLinkTests(ReusableApiTestCase):
    """Registration metadata renders under the CMS mount and resolves in the LMS mount."""

    def registration_urls(self, configuration):
        """Return the detail registration metadata for one configuration."""
        self.login(self.staff)
        response = self.client.get(self.detail_path(configuration))
        self.assertEqual(response.status_code, 200, response.content)
        self.assert_cache_no_store(response)
        return response.json()['registration_urls']

    def test_registration_urls_target_the_real_lms_routes(self):
        configuration = self.create_configuration(name='Registered tool', version='lti_1p3')
        urls = self.registration_urls(configuration)

        self.assertEqual(set(urls), REGISTRATION_FIELDS)
        self.assertIn(str(configuration.passport_id), urls['jwks_url'])
        self.assertIn(str(configuration.passport_id), urls['access_token_url'])
        self.assertEqual(urlparse(urls['login_url']).path, '/api/lti_consumer/v1/launch/')
        # The CMS mount has no LMS route names, so the metadata cannot depend on reverse().
        with self.assertRaises(NoReverseMatch):
            reverse('lti_consumer:lti_consumer.access_token', kwargs={'passport_id': configuration.passport_id})
        with override_settings(ROOT_URLCONF=LMS_URLCONF):
            self.assertEqual(resolve(urlparse(urls['login_url']).path).url_name, 'lti_consumer.launch_gate')
            self.assertEqual(
                resolve(urlparse(urls['jwks_url']).path).url_name, 'lti_consumer.public_keyset_endpoint',
            )
            self.assertEqual(resolve(urlparse(urls['access_token_url']).path).url_name, 'lti_consumer.access_token')

    def test_registration_url_base_precedence(self):
        configuration = self.create_configuration(name='Based tool', version='lti_1p3')

        with override_settings(LTI_BASE='https://lti-base.test', LTI_API_BASE='https://api.test'):
            split = self.registration_urls(configuration)
            self.assertTrue(split['login_url'].startswith('https://lti-base.test/'))
            self.assertTrue(split['jwks_url'].startswith('https://api.test/'))
            self.assertTrue(split['access_token_url'].startswith('https://api.test/'))
