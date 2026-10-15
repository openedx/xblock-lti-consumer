"""API tests for CMS reusable-configuration creation, listing, and context immutability."""
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from opaque_keys.edx.keys import CourseKey
from rest_framework.test import APIClient

from lti_consumer.models import ReusableLtiConfiguration
from lti_consumer.reusable import create_reusable_configuration

COURSE_KEY = 'course-v1:Org+Course+Run'
OTHER_KEY = 'course-v1:Hidden+Other+Run'
CCX_KEY = 'ccx-v1:Org+Course+Run+ccx@1'
REGISTRY_PATCH = 'lti_consumer.plugin.compat.get_active_organizations'
COURSE_ADMIN_PATCH = 'lti_consumer.plugin.reusable_permissions.compat.user_is_course_admin'
COURSE_ACCESS_PATCH = 'lti_consumer.plugin.reusable_views.compat.get_studio_accessible_course_keys'

CONFIG_STATE_FIELDS = (
    'name', 'normalized_name', 'description', 'version', 'context_type', 'context_key',
    'lti_1p1_launch_url', 'lti_1p1_client_key', 'lti_1p1_client_secret',
    'lti_1p3_launch_url', 'lti_1p3_oidc_url', 'lti_1p3_redirect_uris',
    'lti_1p3_client_id', 'lti_1p3_deployment_id', 'lti_1p3_tool_key_mode', 'lti_1p3_passport_id',
    'lti_advantage_deep_linking_enabled', 'lti_advantage_deep_linking_launch_url',
    'lti_advantage_ags_mode', 'lti_advantage_enable_nrps',
    'display_name', 'enable_grading', 'grade_weight', 'accept_grades_after_due_date',
    'open_tool_in', 'inline_height', 'modal_height', 'modal_width',
    'launch_button_text', 'send_extra_parameters', 'custom_parameters', 'updated_at',
)
PASSPORT_STATE_FIELDS = (
    'passport_id', 'lti_1p3_client_id', 'lti_1p3_internal_private_key',
    'lti_1p3_internal_private_key_id', 'lti_1p3_internal_public_jwk',
    'lti_1p3_tool_public_key', 'lti_1p3_tool_keyset_url',
)


def build_context(context_type, key=''):
    """Return the create-only context shape; site contexts omit the key."""
    if context_type == 'site':
        return {'type': 'site'}
    return {'type': context_type, 'key': key}


def configuration_state(configuration):
    """Return the stored configuration state used for no-write assertions."""
    return {field: getattr(configuration, field) for field in CONFIG_STATE_FIELDS}


def passport_state(passport):
    """Return the stored passport state used for no-write assertions."""
    return {field: getattr(passport, field) for field in PASSPORT_STATE_FIELDS}


def create_configuration(name, configuration_context, version='lti_1p1', **overrides):
    """Persist a configuration through the service, resolving organization contexts."""
    data = {'name': name, 'version': version, 'context': configuration_context}
    if version == 'lti_1p1':
        data['lti_1p1'] = {
            'launch_url': 'https://tool.example/launch',
            'client_key': 'not-for-list',
            'client_secret': 'secret-not-for-list',
        }
        data['defaults'] = {'custom_parameters': ['secret=value']}
    else:
        data['lti_1p3'] = {
            'launch_url': 'https://tool.example/launch',
            'oidc_url': 'https://tool.example/oidc',
            'tool_key_mode': 'keyset_url',
            'tool_keyset_url': 'https://tool.example/jwks',
        }
    data.update(overrides)
    registered = (
        [{'short_name': configuration_context['key']}]
        if configuration_context['type'] == 'organization' else []
    )
    with patch(REGISTRY_PATCH, return_value=registered):
        return create_reusable_configuration(data).configuration


class ReusableApiTestCase(TestCase):
    """Shared client, course keys, and platform-patch fixtures."""

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username='viewer')
        self.superuser = user_model.objects.create_superuser(username='admin', email='admin@example.com')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.list_url = reverse('reusable_lti:reusable_configuration_create')
        self.course_key = CourseKey.from_string(COURSE_KEY)
        self.other_key = CourseKey.from_string(OTHER_KEY)
        self.course_access_patcher = patch(COURSE_ACCESS_PATCH, return_value=[self.course_key])
        self.course_access = self.course_access_patcher.start()
        self.addCleanup(self.course_access_patcher.stop)
        course_admin_patcher = patch(COURSE_ADMIN_PATCH, return_value=False)
        self.course_admin = course_admin_patcher.start()
        self.addCleanup(course_admin_patcher.stop)

    def detail_url(self, configuration):
        return reverse(
            'reusable_lti:reusable_configuration_detail',
            kwargs={'config_id': configuration.config_id},
        )

    def create(self, name, context_type='course', context_key=None, version='lti_1p1', **overrides):
        """Create a configuration directly through the service."""
        if context_key is None:
            context_key = str(self.course_key)
        return create_configuration(
            name, build_context(context_type, context_key), version=version, **overrides,
        )


class ReusableConfigurationCreateApiTests(ReusableApiTestCase):
    """Create accepts exactly one normalized context and returns secrets once."""

    def setUp(self):
        super().setUp()
        self.url = self.list_url
        self.payload = {
            'name': 'API-created tool',
            'version': 'lti_1p1',
            'context': build_context('course', COURSE_KEY),
            'lti_1p1': {'launch_url': 'https://tool.example/launch'},
        }

    @patch(COURSE_ADMIN_PATCH, return_value=True)
    def test_course_manager_can_create_and_receive_one_time_secret(self, is_admin):
        response = self.client.post(self.url, {
            **self.payload, 'context': build_context('course', f'{COURSE_KEY}+branch@draft'),
        }, format='json')

        self.assertEqual(response.status_code, 201, response.data)
        configuration = ReusableLtiConfiguration.objects.get()
        self.assertEqual((configuration.context_type, configuration.context_key), ('course', COURSE_KEY))
        self.assertEqual(response.data['context'], build_context('course', COURSE_KEY))
        self.assertNotIn('scope', response.data)
        self.assertEqual(configuration.lti_advantage_ags_mode, 'declarative')
        self.assertEqual(
            response.data['one_time_credentials']['client_secret'], configuration.lti_1p1_client_secret,
        )
        self.assertEqual(response['Cache-Control'], 'no-store')
        is_admin.assert_called()

    def test_create_rejects_invalid_context_shapes_without_writes(self):
        # A superuser reaches shape validation for organization/site contexts too;
        # ordinary callers are denied those types before validation by the agreed 403 precheck.
        self.client.force_authenticate(self.superuser)
        legacy_only = {key: value for key, value in self.payload.items() if key != 'context'}
        legacy_only['scope'] = {'course_keys': [COURSE_KEY]}
        payloads = (
            {**self.payload, 'context': None},
            {**self.payload, 'context': []},
            {**self.payload, 'context': [build_context('course', COURSE_KEY)]},
            {**self.payload, 'context': 'course-v1:Org+Course+Run'},
            {**self.payload, 'context': {'type': 'course'}},
            {**self.payload, 'context': {'type': 'course', 'key': ''}},
            {**self.payload, 'context': {'type': 'course', 'key': '   '}},
            {**self.payload, 'context': {'type': 'course', 'key': None}},
            {**self.payload, 'context': {'type': 'course', 'key': [COURSE_KEY]}},
            {**self.payload, 'context': {'type': 'unknown', 'key': COURSE_KEY}},
            {**self.payload, 'context': {'type': 'site', 'key': COURSE_KEY}},
            {**self.payload, 'context': {'type': 'site', 'key': ''}},
            {**self.payload, 'context': {'type': 'site', 'key': None}},
            {**self.payload, 'context': {'type': 'course', 'key': COURSE_KEY, 'extra': True}},
            {**self.payload, 'context': {'course_keys': [COURSE_KEY]}},
            {**self.payload, 'context': {'site_wide': True}},
            {**self.payload, 'context': build_context('course', COURSE_KEY), 'scope': {'course_keys': [COURSE_KEY]}},
            legacy_only,
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                response = self.client.post(self.url, payload, format='json')
                self.assertEqual(response.status_code, 400, response.data)
                self.assertEqual(ReusableLtiConfiguration.objects.count(), 0)

    @patch(COURSE_ADMIN_PATCH, return_value=True)
    def test_create_normalizes_nullable_disabled_deep_link_url(self, _is_admin):
        payload = {
            **self.payload,
            'services': {'deep_linking_enabled': False, 'deep_linking_launch_url': None},
        }
        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertTrue(response.data['one_time_credentials']['client_secret'])
        configuration = ReusableLtiConfiguration.objects.get()
        self.assertEqual(configuration.lti_advantage_deep_linking_launch_url, '')

    @patch(REGISTRY_PATCH)
    def test_superuser_can_create_organization_context(self, get_organizations):
        get_organizations.return_value = [{'short_name': 'Org'}]
        self.client.force_authenticate(self.superuser)
        payload = {**self.payload, 'context': build_context('organization', ' ORG ')}

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, 201, response.data)
        configuration = ReusableLtiConfiguration.objects.get()
        self.assertEqual((configuration.context_type, configuration.context_key), ('organization', 'org'))
        self.assertEqual(response.data['context'], build_context('organization', 'org'))
        self.assertTrue(get_organizations.called)

    def test_superuser_can_create_site_context_without_a_key(self):
        self.client.force_authenticate(self.superuser)
        payload = {**self.payload, 'context': build_context('site')}

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['context'], {'type': 'site'})
        self.assertNotIn('key', response.data['context'])
        configuration = ReusableLtiConfiguration.objects.get()
        self.assertEqual((configuration.context_type, configuration.context_key), ('site', ''))

    @patch(REGISTRY_PATCH)
    def test_non_superuser_organization_and_site_contexts_are_denied_before_registry_lookup(
        self, get_organizations,
    ):
        payloads = (
            {**self.payload, 'context': build_context('organization', 'org')},
            {**self.payload, 'context': build_context('site')},
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                response = self.client.post(self.url, payload, format='json')
                self.assertEqual(response.status_code, 403, response.data)
                self.assertEqual(ReusableLtiConfiguration.objects.count(), 0)
        get_organizations.assert_not_called()

    @patch(COURSE_ADMIN_PATCH, return_value=True)
    def test_course_admin_cannot_create_ccx_context(self, is_admin):
        payload = {**self.payload, 'context': build_context('course', CCX_KEY)}

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 0)
        is_admin.assert_not_called()

    @patch(COURSE_ADMIN_PATCH, return_value=True)
    def test_lti13_create_returns_registration_identity_without_credentials(self, _is_admin):
        keyset_url = 'https://tool.example/' + 'k' * 280
        payload = {
            'name': 'API-created LTI 1.3 tool',
            'version': 'lti_1p3',
            'context': build_context('course', COURSE_KEY),
            'lti_1p3': {
                'launch_url': 'https://tool.example/launch',
                'oidc_url': 'https://tool.example/oidc',
                'tool_key_mode': 'keyset_url',
                'tool_keyset_url': keyset_url,
            },
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data['client_id'])
        self.assertTrue(response.data['deployment_id'])
        self.assertEqual(response.data['context'], build_context('course', COURSE_KEY))
        self.assertNotIn('one_time_credentials', response.data)
        self.assertNotIn('lti_1p3_private_key', response.data)
        configuration = ReusableLtiConfiguration.objects.get()
        self.assertEqual(configuration.lti_1p3_passport.lti_1p3_tool_keyset_url, keyset_url)
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_superuser_can_create_list_retrieve_and_update(self):
        self.client.force_authenticate(self.superuser)
        created = self.client.post(self.url, self.payload, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        configuration = ReusableLtiConfiguration.objects.get(config_id=created.data['config_id'])

        listed = self.client.get(self.list_url)
        self.assertEqual(listed.data['count'], 1)
        self.assertEqual(listed.data['results'][0]['context'], build_context('course', COURSE_KEY))

        detail = self.client.get(self.detail_url(configuration))
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.data['can_manage'])

        updated = self.client.patch(self.detail_url(configuration), {'description': 'Updated'}, format='json')
        self.assertEqual(updated.status_code, 200, updated.data)
        configuration.refresh_from_db()
        self.assertEqual(configuration.description, 'Updated')

    def test_unauthenticated_and_unauthorized_requests_do_not_create(self):
        anonymous = APIClient().post(self.url, self.payload, format='json')
        self.assertEqual(anonymous.status_code, 403)

        with patch('lti_consumer.plugin.reusable_views.can_manage_reusable_context', return_value=False):
            response = self.client.post(self.url, self.payload, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 0)


class ReusableConfigurationListApiTests(ReusableApiTestCase):
    """Visibility and filters follow the configuration's single context."""

    def test_visible_contexts_and_safe_fields(self):
        self.create('Course', context_type='course', context_key=str(self.course_key))
        self.create('Organization', context_type='organization', context_key='ORG')
        self.create('Site', context_type='site')
        self.create('Hidden', context_type='course', context_key=str(self.other_key))
        self.create('Hidden org', context_type='organization', context_key='other-org')
        self.create('CCX', context_type='course', context_key=CCX_KEY)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 3)
        self.assertEqual([row['name'] for row in response.data['results']], ['Course', 'Organization', 'Site'])
        allowed = {
            'config_id', 'name', 'version', 'context', 'created_at', 'updated_at',
            'can_manage', 'deep_linking_enabled', 'ags_mode', 'nrps_enabled',
        }
        for row in response.data['results']:
            self.assertEqual(set(row), allowed)
            self.assertFalse(row['can_manage'])
        contexts = {row['name']: row['context'] for row in response.data['results']}
        self.assertEqual(contexts, {
            'Course': build_context('course', str(self.course_key)),
            'Organization': build_context('organization', 'org'),
            'Site': {'type': 'site'},
        })
        self.assertNotIn('key', contexts['Site'])
        self.assertNotIn('secret-not-for-list', response.content.decode())
        self.assertNotIn(str(self.other_key), response.content.decode())
        self.course_access.assert_called_once_with(self.user)

    def test_context_type_filter_matches_the_single_context(self):
        self.create('Course', context_type='course', context_key=str(self.course_key))
        self.create('Organization', context_type='organization', context_key='org')
        self.create('Site', context_type='site')
        self.create('Hidden', context_type='course', context_key=str(self.other_key))

        organization = self.client.get(self.list_url, {'context_type': 'organization'})
        site = self.client.get(self.list_url, {'context_type': 'site'})
        course = self.client.get(self.list_url, {'context_type': 'course'})
        invalid = self.client.get(self.list_url, {'context_type': 'scope'})

        self.assertEqual([row['name'] for row in organization.data['results']], ['Organization'])
        self.assertEqual([row['name'] for row in site.data['results']], ['Site'])
        self.assertEqual([row['name'] for row in course.data['results']], ['Course'])
        self.assertEqual(invalid.status_code, 400)

    def test_course_key_filter_matches_context_and_does_not_widen_access(self):
        second_course = CourseKey.from_string('course-v1:Second+Course+Run')
        self.course_access.return_value = [self.course_key, second_course]
        self.create('Selected', context_type='course', context_key=str(self.course_key))
        self.create('Other course', context_type='course', context_key=str(second_course))
        self.create('Organization', context_type='organization', context_key='org')
        self.create('Site', context_type='site')

        response = self.client.get(self.list_url, {'course_key': f'{self.course_key}+branch@draft'})
        inaccessible = self.client.get(self.list_url, {'course_key': str(self.other_key)})

        self.assertEqual([row['name'] for row in response.data['results']], ['Organization', 'Selected', 'Site'])
        self.assertEqual(inaccessible.data['count'], 0)
        self.assertEqual(inaccessible.data['results'], [])

    def test_invalid_course_filter_is_rejected(self):
        for course_key in (
            'not-a-course',
            'course-v1:version@519665f6223ebd6980884f2b',
        ):
            with self.subTest(course_key=course_key):
                response = self.client.get(self.list_url, {'course_key': course_key})
                self.assertEqual(response.status_code, 400)
        self.course_access.assert_not_called()

    def test_superuser_course_filter_does_not_enumerate_courses(self):
        self.user.is_superuser = True
        self.user.save()
        self.create('Selected', context_type='course', context_key=str(self.course_key))
        self.create('Other', context_type='course', context_key=str(self.other_key))

        response = self.client.get(self.list_url, {'course_key': str(self.other_key)})

        self.assertEqual([row['name'] for row in response.data['results']], ['Other'])
        self.course_access.assert_not_called()

    def test_no_studio_access_returns_no_records_even_for_site_context(self):
        self.create('Site', context_type='site')
        self.course_access.return_value = []

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 0)
        self.assertEqual(response.data['results'], [])
        self.course_admin.assert_not_called()

    def test_anonymous_get_is_denied(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.list_url).status_code, 403)
        self.course_access.assert_not_called()

    def test_detail_uses_list_visibility_and_safe_context(self):
        visible = self.create('Visible', context_type='course', context_key=str(self.course_key))
        hidden = self.create('Hidden', context_type='course', context_key=str(self.other_key))

        response = self.client.get(self.detail_url(visible))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'Visible')
        self.assertFalse(response.data['can_manage'])
        self.assertEqual(response.data['context'], build_context('course', str(self.course_key)))
        self.assertNotIn('scope', response.data)
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertNotIn('secret-not-for-list', response.content.decode())
        self.assertEqual(self.client.get(self.detail_url(hidden)).status_code, 404)

    def test_detail_context_is_identical_for_managers_and_viewers(self):
        configuration = self.create('Shared context', context_type='course', context_key=str(self.course_key))
        detail_url = self.detail_url(configuration)

        viewer = self.client.get(detail_url)
        self.course_admin.return_value = True
        manager = self.client.get(detail_url)

        self.assertEqual(viewer.data['context'], manager.data['context'])
        self.assertEqual(manager.data['context'], build_context('course', str(self.course_key)))
        self.assertFalse(viewer.data['can_manage'])
        self.assertTrue(manager.data['can_manage'])
        self.assertNotIn('scope', viewer.data)

    def test_search_and_version_filters_do_not_change_course_enumeration(self):
        self.create('Matching tool', context_type='course', context_key=str(self.course_key))
        self.create('Other tool', context_type='course', context_key=str(self.course_key))
        self.create('Matching hidden', context_type='course', context_key=str(self.other_key))

        response = self.client.get(self.list_url, {
            'search': 'Matching', 'version': 'lti_1p1', 'start_date_on_or_after': '2099-01-01',
        })
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['name'], 'Matching tool')
        self.course_access.assert_called_once_with(self.user)
        response = self.client.get(self.list_url, {'version': 'lti_1p3'})
        self.assertEqual(response.data['results'], [])

    def test_pagination_is_stable(self):
        self.create('Alpha', context_type='course', context_key=str(self.course_key))
        self.create('Beta', context_type='course', context_key=str(self.course_key))

        first = self.client.get(self.list_url, {'page_size': 1})
        self.assertEqual(first.data['count'], 2)
        self.assertEqual(first.data['results'][0]['name'], 'Alpha')
        self.assertIsNotNone(first.data['next'])
        second = self.client.get(first.data['next'])
        self.assertEqual(second.data['results'][0]['name'], 'Beta')
        self.assertIsNone(second.data['next'])

    def test_catalog_queries_are_batched(self):
        for index in range(5):
            self.create(f'Tool {index}', context_type='course', context_key=str(self.course_key))

        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(self.list_url)

        self.assertEqual(response.data['count'], 5)
        self.assertLessEqual(len(captured.captured_queries), 4)
        self.assertEqual(self.course_admin.call_count, 1)

    def test_can_manage_matches_single_context_with_shared_cache(self):
        self.create('Managed', context_type='course', context_key=str(self.course_key))
        self.create('Managed too', context_type='course', context_key=str(self.course_key))
        self.create('Organization', context_type='organization', context_key='org')
        self.create('Site', context_type='site')
        self.course_admin.side_effect = lambda user, key: key == self.course_key

        response = self.client.get(self.list_url)

        manageable = {row['name']: row['can_manage'] for row in response.data['results']}
        self.assertEqual(manageable, {
            'Managed': True, 'Managed too': True, 'Organization': False, 'Site': False,
        })
        self.assertEqual(self.course_admin.call_count, 1)

    def test_retained_organization_context_does_not_consult_active_registry(self):
        self.create('Retained', context_type='organization', context_key='org')
        with patch(REGISTRY_PATCH, side_effect=AssertionError):
            response = self.client.get(self.list_url)
        self.assertEqual(response.data['count'], 1)

    def test_list_uses_neutral_wrapper_and_rechecks_candidate_read_access(self):
        self.create('Readable', context_type='course', context_key=str(self.course_key))
        self.create('Unreadable', context_type='course', context_key=str(self.other_key))
        self.course_access_patcher.stop()
        self.addCleanup(self.course_access_patcher.start)
        with patch(
            'lti_consumer.plugin.compat._get_studio_course_candidates',
        ) as candidates, patch(
            'lti_consumer.plugin.compat._has_studio_course_read_access',
            side_effect=lambda user, key: key == self.course_key,
        ):
            candidates.return_value = [SimpleNamespace(id=self.course_key), SimpleNamespace(id=self.other_key)]
            response = self.client.get(self.list_url, {'search': 'Readable', 'start_date_on_or_after': '2099-01-01'})
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['name'], 'Readable')
        self.assertEqual(candidates.call_args.args[0].GET, {})


class ReusableConfigurationUpdateApiTests(ReusableApiTestCase):
    """PATCH edits settings only and never changes or clears the creation context."""

    def test_patch_updates_editable_metadata_without_rotating_credentials(self):
        configuration = self.create('Before', context_type='course', context_key=str(self.course_key))
        client_secret = configuration.lti_1p1_client_secret
        self.course_admin.return_value = True
        detail_url = self.detail_url(configuration)

        response = self.client.patch(detail_url, {
            'name': 'After',
            'description': 'Updated description',
            'lti_1p1': {'launch_url': 'https://tool.example/new-launch'},
            'services': {'nrps_enabled': True, 'deep_linking_launch_url': None},
            'defaults': {'display_name': 'Updated display'},
        }, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        configuration.refresh_from_db()
        self.assertEqual(configuration.name, 'After')
        self.assertEqual(configuration.description, 'Updated description')
        self.assertEqual(configuration.lti_1p1_launch_url, 'https://tool.example/new-launch')
        self.assertEqual(configuration.lti_advantage_deep_linking_launch_url, '')
        self.assertEqual(configuration.display_name, 'Updated display')
        self.assertEqual(configuration.custom_parameters, ['secret=value'])
        self.assertEqual(configuration.lti_advantage_ags_mode, 'declarative')
        self.assertTrue(configuration.lti_advantage_enable_nrps)
        self.assertEqual((configuration.context_type, configuration.context_key), ('course', str(self.course_key)))
        self.assertEqual(response.data['context'], build_context('course', str(self.course_key)))
        self.assertEqual(configuration.lti_1p1_client_secret, client_secret)
        self.assertNotIn(client_secret, response.content.decode())
        self.assertEqual(response['Cache-Control'], 'no-store')

        invalid = self.client.patch(detail_url, {
            'lti_1p1': {'client_secret': 'replacement-secret'},
        }, format='json')
        self.assertEqual(invalid.status_code, 400)
        configuration.refresh_from_db()
        self.assertEqual(configuration.lti_1p1_client_secret, client_secret)

    def test_rejected_context_or_scope_patch_is_atomic_for_managers_and_superusers(self):
        configuration = self.create(
            'Immutable context', context_type='course', context_key=str(self.course_key), version='lti_1p3',
        )
        passport = configuration.lti_1p3_passport
        detail_url = self.detail_url(configuration)
        self.course_admin.return_value = True
        payloads = (
            {'name': 'Changed', 'context': build_context('course', str(self.course_key))},
            {'name': 'Changed', 'context': build_context('course', str(self.other_key))},
            {'name': 'Changed', 'context': build_context('site')},
            {'name': 'Changed', 'scope': {'course_keys': [str(self.course_key)]}},
            {'context': build_context('course', str(self.course_key)), 'scope': {}},
        )

        for actor in (self.user, self.superuser):
            self.client.force_authenticate(actor)
            for payload in payloads:
                with self.subTest(actor=actor.username, payload=payload):
                    stored = configuration_state(configuration)
                    stored_passport = passport_state(passport)

                    response = self.client.patch(detail_url, payload, format='json')

                    self.assertEqual(response.status_code, 400, response.data)
                    configuration.refresh_from_db()
                    passport.refresh_from_db()
                    self.assertEqual(configuration_state(configuration), stored)
                    self.assertEqual(passport_state(passport), stored_passport)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 1)

    def test_rejected_context_patch_preserves_lti11_credentials(self):
        configuration = self.create('Credentials', context_type='course', context_key=str(self.course_key))
        stored = configuration_state(configuration)
        self.course_admin.return_value = True

        response = self.client.patch(self.detail_url(configuration), {
            'name': 'Changed', 'context': build_context('course', str(self.other_key)),
        }, format='json')

        self.assertEqual(response.status_code, 400, response.data)
        configuration.refresh_from_db()
        self.assertEqual(configuration_state(configuration), stored)

    def test_patch_rejects_malformed_bodies_without_writes(self):
        configuration = self.create('Unchanged', context_type='course', context_key=str(self.course_key))
        updated_at = configuration.updated_at
        self.course_admin.return_value = True
        detail_url = self.detail_url(configuration)
        payloads = (
            [],
            {'name': 'Changed', 'services': []},
        )

        for payload in payloads:
            with self.subTest(payload=payload):
                response = self.client.patch(
                    detail_url, data=json.dumps(payload), content_type='application/json',
                )
                self.assertEqual(response.status_code, 400)
                configuration.refresh_from_db()
                self.assertEqual(configuration.name, 'Unchanged')
                self.assertEqual(configuration.updated_at, updated_at)
                self.assertEqual(ReusableLtiConfiguration.objects.count(), 1)

    def test_patch_hides_invisible_ids_and_requires_context_management(self):
        configuration = self.create('Read only', context_type='course', context_key=str(self.course_key))
        hidden = self.create('Hidden', context_type='course', context_key=str(self.other_key))

        for record, expected_status in ((configuration, 403), (hidden, 404)):
            for payload in ({'name': 'Changed'}, []):
                with self.subTest(config_id=record.config_id, payload=payload):
                    response = self.client.patch(
                        self.detail_url(record), data=json.dumps(payload), content_type='application/json',
                    )
                    self.assertEqual(response.status_code, expected_status)

        configuration.refresh_from_db()
        hidden.refresh_from_db()
        self.assertEqual(configuration.name, 'Read only')
        self.assertEqual(hidden.name, 'Hidden')

    def test_session_authenticated_patch_requires_csrf(self):
        configuration = self.create('Session update', context_type='course', context_key=str(self.course_key))
        self.course_admin.return_value = True
        detail_url = self.detail_url(configuration)
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        payload = {'name': 'Updated with CSRF'}

        denied = client.patch(detail_url, payload, format='json')
        self.assertEqual(denied.status_code, 403)
        self.assertIn('CSRF', str(denied.data['detail']))
        configuration.refresh_from_db()
        self.assertEqual(configuration.name, 'Session update')

        csrf_token = 'a' * 32
        client.cookies['csrftoken'] = csrf_token
        allowed = client.patch(detail_url, payload, format='json', HTTP_X_CSRFTOKEN=csrf_token)
        self.assertEqual(allowed.status_code, 200, allowed.data)
        configuration.refresh_from_db()
        self.assertEqual(configuration.name, 'Updated with CSRF')

    def test_patch_rename_conflict_is_non_disclosing_and_preserves_state(self):
        configuration = self.create('Original', context_type='course', context_key=str(self.course_key))
        hidden = self.create('Hidden conflict', context_type='course', context_key=str(self.other_key))
        updated_at = configuration.updated_at
        self.course_admin.return_value = True

        response = self.client.patch(self.detail_url(configuration), {
            'name': ' hidden CONFLICT ',
            'description': 'Must not persist',
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertNotIn(str(hidden.config_id), response.content.decode())
        self.assertNotIn(hidden.name, response.content.decode())
        configuration.refresh_from_db()
        self.assertEqual(configuration.name, 'Original')
        self.assertEqual(configuration.normalized_name, 'original')
        self.assertEqual(configuration.description, '')
        self.assertEqual(configuration.updated_at, updated_at)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 2)

    def test_patch_preserves_inactive_organization_context(self):
        configuration = self.create(
            'Inactive org', context_type='organization', context_key='inactive-org',
        )
        self.client.force_authenticate(self.superuser)

        with patch(REGISTRY_PATCH, side_effect=AssertionError):
            response = self.client.patch(self.detail_url(configuration), {
                'name': 'Renamed org tool',
            }, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        configuration.refresh_from_db()
        self.assertEqual(configuration.name, 'Renamed org tool')
        self.assertEqual(
            (configuration.context_type, configuration.context_key), ('organization', 'inactive-org'),
        )
        self.assertEqual(response.data['context'], build_context('organization', 'inactive-org'))

    def test_lti13_patch_preserves_identity_and_keys_and_rejects_immutable_writes(self):
        configuration = self.create(
            'LTI 1.3 before update', context_type='course', context_key=str(self.course_key), version='lti_1p3',
        )
        passport = configuration.lti_1p3_passport
        identity = {field: getattr(configuration, field) for field in (
            'config_id', 'version', 'context_type', 'context_key',
            'lti_1p3_client_id', 'lti_1p3_deployment_id', 'lti_1p3_passport_id',
        )}
        stored_passport = passport_state(passport)
        self.course_admin.return_value = True
        detail_url = self.detail_url(configuration)

        with patch('lti_consumer.models.Lti1p3Passport.generate_lti_1p3_keys_if_missing') as generate_keys:
            response = self.client.patch(detail_url, {
                'name': 'Updated LTI 1.3',
                'lti_1p3': {
                    'launch_url': 'https://tool.example/new-launch',
                    'oidc_url': 'https://tool.example/new-oidc',
                    'redirect_uris': ['https://tool.example/redirect'],
                },
                'services': {'nrps_enabled': True},
                'defaults': {'display_name': 'Updated display'},
            }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        generate_keys.assert_not_called()
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertNotIn('one_time_credentials', response.data)
        self.assertEqual(
            response.content.count(json.dumps(stored_passport['lti_1p3_internal_private_key']).encode()), 0,
        )
        configuration.refresh_from_db()
        self.assertEqual(configuration.name, 'Updated LTI 1.3')
        self.assertEqual(configuration.normalized_name, 'updated lti 1.3')
        self.assertEqual(configuration.lti_1p3_launch_url, 'https://tool.example/new-launch')
        self.assertEqual(configuration.lti_1p3_oidc_url, 'https://tool.example/new-oidc')
        self.assertEqual(configuration.lti_1p3_redirect_uris, ['https://tool.example/redirect'])
        self.assertTrue(configuration.lti_advantage_enable_nrps)
        self.assertEqual(configuration.display_name, 'Updated display')
        updated_at = configuration.updated_at

        immutable_writes = {
            'version': 'lti_1p1',
            'config_id': str(configuration.config_id),
            'context_type': 'site',
            'context_key': str(self.other_key),
            'client_id': 'replacement-client',
            'deployment_id': 'replacement-deployment',
            'passport_id': str(passport.passport_id),
            'lti_1p3_internal_private_key': 'not-a-key',
            'registration_urls': {'jwks_url': 'https://tool.example/replacement'},
        }
        for field, value in immutable_writes.items():
            with self.subTest(field=field):
                invalid = self.client.patch(detail_url, {'name': 'Rejected edit', field: value}, format='json')
                self.assertEqual(invalid.status_code, 400)
        for field in ('client_id', 'deployment_id'):
            with self.subTest(nested_identity_field=field):
                invalid = self.client.patch(detail_url, {
                    'name': 'Rejected edit', 'lti_1p3': {field: 'replacement'},
                }, format='json')
                self.assertEqual(invalid.status_code, 400)
        configuration.refresh_from_db()
        passport.refresh_from_db()
        self.assertEqual(configuration.name, 'Updated LTI 1.3')
        self.assertEqual(configuration.updated_at, updated_at)
        for field, value in identity.items():
            self.assertEqual(getattr(configuration, field), value)
        self.assertEqual(passport_state(passport), stored_passport)
        self.assertEqual(configuration.lti_1p3_client_id, passport.lti_1p3_client_id)

    def test_patch_updates_tool_verification_settings_without_exposing_key_material(self):
        configuration = self.create(
            'Editable tool key',
            context_type='course',
            context_key=str(self.course_key),
            version='lti_1p3',
            lti_1p3={
                'launch_url': 'https://tool.example/launch',
                'oidc_url': 'https://tool.example/oidc',
                'tool_key_mode': 'keyset_url',
                'tool_keyset_url': 'https://tool.example/original-jwks',
            },
        )
        passport = configuration.lti_1p3_passport
        identity = {
            'config_id': configuration.config_id,
            'client_id': configuration.lti_1p3_client_id,
            'deployment_id': configuration.lti_1p3_deployment_id,
        }
        stored_passport = passport_state(passport)
        self.course_admin.return_value = True
        detail_url = self.detail_url(configuration)
        public_key = '-----BEGIN PUBLIC KEY----- replacement-tool-key'

        public_response = self.client.patch(detail_url, {'lti_1p3': {
            'tool_key_mode': 'public_key', 'tool_public_key': public_key,
        }}, format='json')
        self.assertEqual(public_response.status_code, 200, public_response.data)
        self.assertEqual(public_response.data['tool_key_mode'], 'public_key')
        self.assertNotIn('replacement-tool-key', public_response.content.decode())
        configuration.refresh_from_db()
        passport.refresh_from_db()
        self.assertEqual(configuration.lti_1p3_tool_key_mode, 'public_key')
        self.assertEqual(passport.lti_1p3_tool_public_key, public_key)
        self.assertEqual(passport.lti_1p3_tool_keyset_url, '')

        keyset_url = 'https://tool.example/updated-jwks'
        keyset_response = self.client.patch(detail_url, {'lti_1p3': {
            'tool_key_mode': 'keyset_url', 'tool_keyset_url': keyset_url,
        }}, format='json')
        self.assertEqual(keyset_response.status_code, 200, keyset_response.data)
        self.assertEqual(keyset_response.data['tool_key_mode'], 'keyset_url')
        self.assertNotIn(keyset_url, keyset_response.content.decode())
        configuration.refresh_from_db()
        passport.refresh_from_db()
        self.assertEqual(configuration.lti_1p3_tool_key_mode, 'keyset_url')
        self.assertEqual(passport.lti_1p3_tool_public_key, '')
        self.assertEqual(passport.lti_1p3_tool_keyset_url, keyset_url)

        invalid = self.client.patch(detail_url, {'lti_1p3': {'tool_key_mode': 'public_key'}}, format='json')
        self.assertEqual(invalid.status_code, 400)
        configuration.refresh_from_db()
        passport.refresh_from_db()
        self.assertEqual(configuration.lti_1p3_tool_key_mode, 'keyset_url')
        self.assertEqual(passport.lti_1p3_tool_keyset_url, keyset_url)
        self.assertEqual(configuration.config_id, identity['config_id'])
        self.assertEqual(configuration.lti_1p3_client_id, identity['client_id'])
        self.assertEqual(configuration.lti_1p3_deployment_id, identity['deployment_id'])
        self.assertEqual(passport_state(passport)['passport_id'], stored_passport['passport_id'])
        self.assertEqual(passport_state(passport)['lti_1p3_internal_private_key'],
                         stored_passport['lti_1p3_internal_private_key'])
        self.assertEqual(passport_state(passport)['lti_1p3_internal_public_jwk'],
                         stored_passport['lti_1p3_internal_public_jwk'])

    def test_lti13_patch_passport_write_failure_rolls_back_configuration_and_passport(self):
        configuration = self.create(
            'Atomic tool-key update',
            context_type='course',
            context_key=str(self.course_key),
            version='lti_1p3',
            lti_1p3={
                'launch_url': 'https://tool.example/launch',
                'oidc_url': 'https://tool.example/oidc',
                'tool_key_mode': 'keyset_url',
                'tool_keyset_url': 'https://tool.example/original-jwks',
            },
        )
        passport = configuration.lti_1p3_passport
        stored_configuration = configuration_state(configuration)
        stored_passport = passport_state(passport)
        self.course_admin.return_value = True

        with patch(
            'lti_consumer.models.Lti1p3Passport.save',
            side_effect=IntegrityError('injected passport failure'),
        ) as passport_save:
            response = self.client.patch(self.detail_url(configuration), {
                'name': 'Must roll back',
                'description': 'Must not persist',
                'defaults': {'display_name': 'Must not persist'},
                'lti_1p3': {
                    'tool_key_mode': 'public_key',
                    'tool_public_key': '-----BEGIN PUBLIC KEY-----\nreplacement',
                },
            }, format='json')

        self.assertEqual(response.status_code, 400, response.data)
        passport_save.assert_called_once_with(
            update_fields=['lti_1p3_tool_public_key', 'lti_1p3_tool_keyset_url'],
        )
        configuration.refresh_from_db()
        passport.refresh_from_db()
        self.assertEqual(configuration_state(configuration), stored_configuration)
        self.assertEqual(passport_state(passport), stored_passport)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 1)
