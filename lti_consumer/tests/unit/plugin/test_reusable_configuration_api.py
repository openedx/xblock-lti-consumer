"""User-journey integration tests for the reusable configuration API.

Each test drives the real APIClient, serializers, mutation module, ORM and
database. Only edx-platform-owned boundaries are mocked: Studio course access,
course admin checks, the Global Staff role, and the organization registry.
Semantic matrices live in the module suites; these journeys keep the HTTP
status, disclosure, pagination, filter, CSRF and rollback contract.
"""
import json
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection
from django.test import TestCase
from django.urls import reverse
from opaque_keys.edx.keys import CourseKey
from rest_framework.test import APIClient

from lti_consumer.models import ReusableLtiConfiguration
from lti_consumer.reusable import create_reusable_configuration

COURSE_KEY = 'course-v1:Org+Course+Run'
OTHER_KEY = 'course-v1:Hidden+Other+Run'
CCX_KEY = 'ccx-v1:Org+Course+Run+ccx@1'
REGISTRY_PATCH = 'lti_consumer.plugin.compat.get_active_organizations'
COURSE_ADMIN_PATCH = 'lti_consumer.plugin.compat.user_is_course_admin'
GLOBAL_STAFF_PATCH = 'lti_consumer.plugin.compat.user_is_global_staff'
COURSE_ACCESS_PATCH = 'lti_consumer.plugin.compat.get_studio_accessible_course_keys'
CANDIDATES_PATCH = 'lti_consumer.plugin.compat._get_studio_course_candidates'
READ_ACCESS_PATCH = 'lti_consumer.plugin.compat._has_studio_course_read_access'
VIEW_BASE_PATCH = 'lti_consumer.plugin.reusable_serializers.get_lti_view_base'
API_BASE_PATCH = 'lti_consumer.plugin.reusable_serializers.get_lti_api_base'

# One row is both the catalog entry and the LTI 1.3 passport, so one snapshot covers it.
CONFIG_STATE_FIELDS = (
    'name', 'description', 'version', 'context_type', 'context_key',
    'lti_1p1_launch_url', 'lti_1p1_client_key', 'lti_1p1_client_secret',
    'lti_1p3_launch_url', 'lti_1p3_oidc_url', 'lti_1p3_redirect_uris',
    'lti_1p3_client_id', 'lti_1p3_deployment_id', 'lti_1p3_tool_key_mode',
    'lti_advantage_deep_linking_enabled', 'lti_advantage_deep_linking_launch_url',
    'lti_advantage_ags_mode', 'lti_advantage_enable_nrps',
    'display_name', 'enable_grading', 'grade_weight', 'accept_grades_after_due_date',
    'open_tool_in', 'inline_height', 'modal_height', 'modal_width',
    'launch_button_text', 'send_extra_parameters', 'custom_parameters', 'updated_at',
    # Passport identity, credentials and platform signing material.
    'passport_id', 'lti_1p3_internal_private_key', 'lti_1p3_internal_private_key_id',
    'lti_1p3_internal_public_jwk', 'lti_1p3_tool_public_key', 'lti_1p3_tool_keyset_url',
)
FORBIDDEN_RESPONSE_FIELDS = (
    'lti_1p1_client_key', 'lti_1p1_client_secret',
    'lti_1p3_internal_private_key', 'lti_1p3_internal_public_jwk',
    'lti_1p3_tool_public_key', 'one_time_credentials',
)


def build_context(context_type, key=''):
    """Return the create-only context shape; site contexts omit the key."""
    if context_type == 'site':
        return {'type': 'site'}
    return {'type': context_type, 'key': key}


def lti11_create_payload(context=None, **overrides):
    """Return a minimal LTI 1.1 create payload for the API."""
    payload = {
        'name': 'API-created tool',
        'version': 'lti_1p1',
        'context': build_context('course', COURSE_KEY) if context is None else context,
        'lti_1p1': {'launch_url': 'https://tool.example/launch'},
    }
    payload.update(overrides)
    return payload


def lti13_create_payload(context=None, **overrides):
    """Return a minimal LTI 1.3 create payload for the API."""
    payload = {
        'name': 'API-created tool',
        'version': 'lti_1p3',
        'context': build_context('course', COURSE_KEY) if context is None else context,
        'lti_1p3': {
            'launch_url': 'https://tool.example/launch',
            'oidc_url': 'https://tool.example/oidc',
            'tool_key_mode': 'keyset_url',
            'tool_keyset_url': 'https://tool.example/jwks',
        },
    }
    payload.update(overrides)
    return payload


def configuration_state(configuration):
    """Return every stored field used for no-write assertions."""
    return {field: getattr(configuration, field) for field in CONFIG_STATE_FIELDS}


def create_configuration(actor, name, configuration_context, version='lti_1p1', **overrides):
    """Persist a configuration through the module, resolving organization contexts."""
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
        return create_reusable_configuration(actor, data).configuration


class ReusableApiTestCase(TestCase):
    """Shared client, course keys, and edx-platform boundary patches."""

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username='viewer')
        self.superuser = user_model.objects.create_superuser(username='admin', email='admin@example.com')
        global_staff_patcher = patch(
            GLOBAL_STAFF_PATCH,
            side_effect=lambda user: bool(user and (user.is_superuser or user.is_staff)),
        )
        global_staff_patcher.start()
        self.addCleanup(global_staff_patcher.stop)
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
        """Create a configuration directly through the module."""
        if context_key is None:
            context_key = str(self.course_key)
        return create_configuration(
            self.superuser, name, build_context(context_type, context_key), version=version, **overrides,
        )

    def assert_not_disclosed(self, response, value):
        self.assertNotIn(value, response.content.decode())


class ReusableConfigurationApiJourneys(ReusableApiTestCase):
    """End-to-end journeys: create, authorize, list, detail, patch, and conflicts."""

    def test_course_admin_lti11_creation_keeps_secret_creation_only(self):
        self.course_admin.return_value = True
        response = self.client.post(self.list_url, lti11_create_payload(
            build_context('course', f'{COURSE_KEY}+branch@draft'),
            name='  Journey Tool  ',
            services={'nrps_enabled': True, 'deep_linking_launch_url': None},
            defaults={'display_name': 'Journey display', 'custom_parameters': ['secret=value']},
        ), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response['Cache-Control'], 'no-store')

        configuration = ReusableLtiConfiguration.objects.get()
        secret = configuration.lti_1p1_client_secret
        self.assertTrue(secret)
        self.assertNotEqual(configuration.lti_1p1_client_key, configuration.lti_1p1_client_secret)
        self.assertEqual((configuration.context_type, configuration.context_key), ('course', COURSE_KEY))
        self.assertEqual(configuration.name, 'Journey Tool')
        self.assertTrue(configuration.lti_advantage_enable_nrps)
        self.assertEqual(configuration.lti_advantage_deep_linking_launch_url, '')
        self.assertEqual(configuration.display_name, 'Journey display')
        self.assertEqual(configuration.custom_parameters, ['secret=value'])
        self.assertEqual(response.data['one_time_credentials']['client_secret'], secret)
        self.assertEqual(response.data['context'], build_context('course', COURSE_KEY))

        detail_url = self.detail_url(configuration)
        listing = self.client.get(self.list_url)
        detail = self.client.get(detail_url)
        patched = self.client.patch(detail_url, {'name': 'Renamed Tool'}, format='json')
        self.assertEqual(detail['Cache-Control'], 'no-store')
        self.assertEqual(patched.status_code, 200, patched.data)
        self.assertEqual(patched['Cache-Control'], 'no-store')
        self.assertNotIn('one_time_credentials', patched.data)
        self.assertEqual(patched.data['context'], build_context('course', COURSE_KEY))
        for api_response in (listing, detail, patched):
            self.assert_not_disclosed(api_response, secret)

        configuration.refresh_from_db()
        self.assertEqual(configuration.name, 'Renamed Tool')
        self.assertEqual(configuration.lti_1p1_client_secret, secret)

    @patch(API_BASE_PATCH, return_value='https://api.example')
    @patch(VIEW_BASE_PATCH, return_value='https://view.example')
    def test_course_admin_lti13_creation_persists_identity_and_safe_metadata(self, _view_base, _api_base):
        self.course_admin.return_value = True
        response = self.client.post(self.list_url, lti13_create_payload(
            build_context('course', COURSE_KEY),
            lti_1p3={
                'launch_url': 'https://tool.example/launch',
                'oidc_url': 'https://tool.example/oidc',
                'redirect_uris': ['https://tool.example/redirect'],
                'tool_key_mode': 'public_key',
                'tool_public_key': '-----BEGIN PUBLIC KEY----- PUBLIC MATERIAL',
            },
        ), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response['Cache-Control'], 'no-store')

        configuration = ReusableLtiConfiguration.objects.get()
        self.assertEqual(str(uuid.UUID(configuration.lti_1p3_client_id, version=4)), configuration.lti_1p3_client_id)
        self.assertEqual(
            str(uuid.UUID(configuration.lti_1p3_deployment_id, version=4)), configuration.lti_1p3_deployment_id,
        )
        self.assertTrue(configuration.lti_1p3_internal_private_key)
        self.assertEqual(configuration.lti_1p3_tool_public_key, '-----BEGIN PUBLIC KEY----- PUBLIC MATERIAL')
        self.assertEqual(configuration.lti_1p3_redirect_uris, ['https://tool.example/redirect'])

        self.assertEqual(response.data['client_id'], configuration.lti_1p3_client_id)
        self.assertEqual(response.data['deployment_id'], configuration.lti_1p3_deployment_id)
        self.assertTrue(response.data['tool_key_configured'])
        registration_urls = {
            'login_url': 'https://view.example/api/lti_consumer/v1/launch/',
            'jwks_url': 'https://api.example/api/lti_consumer/v1/public_keysets',
            'access_token_url': 'https://api.example/api/lti_consumer/v1/token',
        }
        self.assertEqual(response.data['registration_urls'], registration_urls)
        detail = self.client.get(self.detail_url(configuration))
        self.assertEqual(detail.data['registration_urls'], registration_urls)
        for forbidden in FORBIDDEN_RESPONSE_FIELDS:
            self.assertNotIn(forbidden, response.data)
        self.assert_not_disclosed(response, configuration.lti_1p3_internal_private_key)

    def test_create_authorization_and_validation_leave_no_rows(self):
        self.client.force_authenticate(None)
        anonymous = self.client.post(
            self.list_url, lti11_create_payload(build_context('course', COURSE_KEY)), format='json',
        )
        self.assertEqual(anonymous.status_code, 403)

        self.client.force_authenticate(self.user)
        not_admin = self.client.post(
            self.list_url, lti11_create_payload(build_context('course', COURSE_KEY)), format='json',
        )
        self.assertEqual(not_admin.status_code, 403)

        with patch(REGISTRY_PATCH, side_effect=AssertionError('registry must not be consulted')):
            organization = self.client.post(
                self.list_url, lti11_create_payload(build_context('organization', 'org')), format='json',
            )
            site = self.client.post(
                self.list_url, lti11_create_payload(build_context('site')), format='json',
            )
        self.assertEqual((organization.status_code, site.status_code), (403, 403))

        self.course_admin.reset_mock()
        self.course_admin.return_value = True
        ccx = self.client.post(
            self.list_url, lti11_create_payload(build_context('course', CCX_KEY)), format='json',
        )
        self.assertEqual(ccx.status_code, 403)
        self.course_admin.assert_not_called()

        self.client.force_authenticate(self.superuser)
        missing_context = lti11_create_payload()
        missing_context['context'] = None
        invalid_payloads = (
            missing_context,
            lti11_create_payload(build_context('course', '')),
            lti11_create_payload({'type': 'site', 'key': 'nonblank'}),
            lti11_create_payload(build_context('course', COURSE_KEY), scope={'course_keys': [COURSE_KEY]}),
            lti11_create_payload(build_context('course', COURSE_KEY), lti_1p3={'launch_url': 'https://x.test'}),
            lti13_create_payload(build_context('course', COURSE_KEY), lti_1p3={
                'launch_url': 'https://tool.example/launch',
                'oidc_url': 'https://tool.example/oidc',
                'tool_key_mode': 'public_key',
            }),
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.client.post(self.list_url, payload, format='json')
                self.assertEqual(response.status_code, 400, response.data)
        malformed = self.client.post(
            self.list_url, data=json.dumps([]), content_type='application/json',
        )
        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 0)

    def test_superuser_keeps_organization_and_site_context_creation(self):
        """Superusers keep this access at the patched platform role boundary."""
        self.client.force_authenticate(self.superuser)
        with patch(REGISTRY_PATCH, return_value=[{'short_name': 'Org'}]):
            organization = self.client.post(self.list_url, lti11_create_payload(
                build_context('organization', ' ORG '),
                name='Organization tool',
                lti_1p1={
                    'launch_url': 'https://tool.example/launch',
                    'client_key': 'supplied-key',
                    'client_secret': 'supplied-secret',
                },
            ), format='json')
        self.assertEqual(organization.status_code, 201, organization.data)
        self.assertEqual(organization['Cache-Control'], 'no-store')
        self.assertEqual(organization.data['context'], build_context('organization', 'org'))
        self.assertEqual(
            organization.data['one_time_credentials'],
            {'client_key': 'supplied-key', 'client_secret': 'supplied-secret'},
        )
        stored_organization = ReusableLtiConfiguration.objects.get(name='Organization tool')
        self.assertEqual(
            (stored_organization.context_type, stored_organization.context_key), ('organization', 'org'),
        )
        self.assertEqual(
            (stored_organization.lti_1p1_client_key, stored_organization.lti_1p1_client_secret),
            ('supplied-key', 'supplied-secret'),
        )
        self.assertFalse(stored_organization.lti_advantage_deep_linking_enabled)
        self.assertEqual(stored_organization.lti_advantage_deep_linking_launch_url, '')
        self.assertEqual(stored_organization.lti_advantage_ags_mode, 'declarative')
        self.assertFalse(stored_organization.lti_advantage_enable_nrps)
        self.assertEqual(stored_organization.description, '')
        self.assertEqual(stored_organization.display_name, 'LTI Consumer')
        self.assertFalse(stored_organization.enable_grading)
        self.assertEqual(stored_organization.grade_weight, 1.0)
        self.assertTrue(stored_organization.accept_grades_after_due_date)
        self.assertEqual(stored_organization.open_tool_in, 'iframe')
        self.assertEqual(stored_organization.inline_height, 800)
        self.assertEqual(stored_organization.modal_height, 80)
        self.assertEqual(stored_organization.modal_width, 80)
        self.assertEqual(stored_organization.launch_button_text, '')
        self.assertFalse(stored_organization.send_extra_parameters)
        self.assertEqual(stored_organization.custom_parameters, [])

        site = self.client.post(
            self.list_url, lti11_create_payload(build_context('site'), name='Site tool'), format='json',
        )
        self.assertEqual(site.status_code, 201, site.data)
        self.assertEqual(site['Cache-Control'], 'no-store')
        self.assertEqual(site.data['context'], {'type': 'site'})
        self.assertNotIn('key', site.data['context'])
        self.assertTrue(ReusableLtiConfiguration.objects.filter(context_type='site', context_key='').exists())

    def test_catalog_visibility_projection_and_detail_follow_single_context(self):
        course = self.create('Course tool')
        self.create('Organization tool', context_type='organization', context_key='Org')
        self.create('Site tool', context_type='site')
        self.create('Hidden course', context_type='course', context_key=str(self.other_key))
        self.create('Hidden org', context_type='organization', context_key='other-org')
        self.create('CCX tool', context_type='course', context_key=CCX_KEY)
        secret = course.lti_1p1_client_secret

        with patch(REGISTRY_PATCH, side_effect=AssertionError('read path must not consult the registry')):
            listing = self.client.get(self.list_url)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data['count'], 3)
        visible = {row['name']: row for row in listing.data['results']}
        self.assertEqual(set(visible), {'Course tool', 'Organization tool', 'Site tool'})
        safe_fields = {'config_id', 'name', 'version', 'context', 'created_at', 'updated_at'}
        for row in visible.values():
            self.assertFalse(row['can_manage'])
            self.assertTrue(safe_fields.issubset(row))
            for forbidden in FORBIDDEN_RESPONSE_FIELDS:
                self.assertNotIn(forbidden, row)
        self.assert_not_disclosed(listing, secret)
        self.assertEqual(visible['Course tool']['context'], build_context('course', COURSE_KEY))
        self.assertEqual(visible['Organization tool']['context'], build_context('organization', 'org'))
        self.assertEqual(visible['Site tool']['context'], {'type': 'site'})

        self.assertEqual(self.client.get(self.list_url, {'context_type': 'course'}).data['count'], 1)
        self.assertEqual(self.client.get(self.list_url, {'context_type': 'organization'}).data['count'], 1)
        self.assertEqual(self.client.get(self.list_url, {'context_type': 'site'}).data['count'], 1)
        self.assertEqual(self.client.get(self.list_url, {'search': 'Site tool'}).data['count'], 1)
        self.assertEqual(self.client.get(self.list_url, {'version': 'lti_1p3'}).data['count'], 0)
        paged = self.client.get(self.list_url, {'page_size': 1})
        self.assertEqual(paged.data['count'], 3)
        self.assertEqual([row['name'] for row in paged.data['results']], ['Course tool'])
        self.assertIsNotNone(paged.data['next'])
        second_page = self.client.get(paged.data['next'])
        self.assertEqual([row['name'] for row in second_page.data['results']], ['Organization tool'])
        self.assertIsNotNone(second_page.data['next'])
        final_page = self.client.get(second_page.data['next'])
        self.assertEqual([row['name'] for row in final_page.data['results']], ['Site tool'])
        self.assertIsNone(final_page.data['next'])

        detail = self.client.get(self.detail_url(course))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data['context'], visible['Course tool']['context'])
        self.assertFalse(detail.data['can_manage'])
        self.assert_not_disclosed(detail, secret)

        hidden = ReusableLtiConfiguration.objects.get(name='Hidden course')
        self.assertEqual(self.client.get(self.detail_url(hidden)).status_code, 404)

        self.course_admin.return_value = True
        manager_detail = self.client.get(self.detail_url(course))
        self.assertTrue(manager_detail.data['can_manage'])
        self.assertEqual(manager_detail.data['context'], detail.data['context'])

    def test_course_filters_and_access_loss_do_not_widen_visibility(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.list_url).status_code, 403)
        self.client.force_authenticate(self.user)

        second_course = CourseKey.from_string('course-v1:Second+Course+Run')
        self.course_access.return_value = [self.course_key, second_course]
        self.create('Selected', context_type='course', context_key=str(self.course_key))
        self.create('Second course', context_type='course', context_key=str(second_course))
        self.create('Organization', context_type='organization', context_key='org')
        self.create('Site', context_type='site')
        self.create('Other', context_type='course', context_key=str(self.other_key))

        filtered = self.client.get(self.list_url, {'course_key': f'{self.course_key}+branch@draft'})
        self.assertEqual({row['name'] for row in filtered.data['results']}, {'Selected', 'Organization', 'Site'})
        inaccessible = self.client.get(self.list_url, {'course_key': str(self.other_key)})
        self.assertEqual((inaccessible.data['count'], inaccessible.data['results']), (0, []))
        for bad_key in ('not-a-course', 'course-v1:version@519665f6223ebd6980884f2b'):
            with self.subTest(course_key=bad_key):
                self.assertEqual(self.client.get(self.list_url, {'course_key': bad_key}).status_code, 400)

        self.course_access.return_value = []
        self.assertEqual(self.client.get(self.list_url).data['count'], 0)

        self.client.force_authenticate(self.superuser)
        superuser_filtered = self.client.get(self.list_url, {'course_key': str(self.other_key)})
        self.assertEqual({row['name'] for row in superuser_filtered.data['results']}, {'Other', 'Site'})

    def test_editable_patch_journey_updates_both_versions_and_preserves_identity(self):
        configuration = self.create('Editable 1.1')
        secret = configuration.lti_1p1_client_secret
        self.course_admin.return_value = True
        detail_url = self.detail_url(configuration)

        response = self.client.patch(detail_url, {
            'name': 'Renamed 1.1',
            'description': 'Updated description',
            'lti_1p1': {'launch_url': 'https://tool.example/new-launch'},
            'services': {'nrps_enabled': True, 'deep_linking_launch_url': None},
            'defaults': {'display_name': 'Updated display', 'modal_width': 50},
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response['Cache-Control'], 'no-store')
        configuration.refresh_from_db()
        self.assertEqual((configuration.name, configuration.description), ('Renamed 1.1', 'Updated description'))
        self.assertEqual(configuration.lti_1p1_launch_url, 'https://tool.example/new-launch')
        self.assertTrue(configuration.lti_advantage_enable_nrps)
        self.assertEqual(configuration.lti_advantage_deep_linking_launch_url, '')
        self.assertEqual((configuration.display_name, configuration.modal_width), ('Updated display', 50))
        self.assertEqual(configuration.lti_1p1_client_secret, secret)
        self.assertEqual(response.data['context'], build_context('course', COURSE_KEY))
        self.assert_not_disclosed(response, secret)

        lti13 = self.create('Editable 1.3', version='lti_1p3', lti_1p3={
            'launch_url': 'https://tool.example/launch',
            'oidc_url': 'https://tool.example/oidc',
            'tool_key_mode': 'keyset_url',
            'tool_keyset_url': 'https://tool.example/jwks',
            'client_id': 'supplied-1p3-client',
            'deployment_id': 'supplied-1p3-deployment',
        })
        self.assertEqual(
            (lti13.lti_1p3_client_id, lti13.lti_1p3_deployment_id),
            ('supplied-1p3-client', 'supplied-1p3-deployment'),
        )
        identity = (lti13.lti_1p3_client_id, lti13.lti_1p3_deployment_id, lti13.passport_id)
        detail_url = self.detail_url(lti13)
        response = self.client.patch(detail_url, {
            'lti_1p3': {
                'launch_url': 'https://tool.example/new-launch',
                'oidc_url': 'https://tool.example/new-oidc',
                'redirect_uris': ['https://tool.example/redirect'],
                'tool_key_mode': 'public_key',
                'tool_public_key': '-----BEGIN PUBLIC KEY----- PUBLIC MATERIAL',
            },
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response['Cache-Control'], 'no-store')
        lti13.refresh_from_db()
        self.assertEqual(lti13.lti_1p3_tool_key_mode, 'public_key')
        self.assertEqual(lti13.lti_1p3_tool_public_key, '-----BEGIN PUBLIC KEY----- PUBLIC MATERIAL')
        self.assertEqual(lti13.lti_1p3_tool_keyset_url, '')
        self.assertEqual(lti13.lti_1p3_redirect_uris, ['https://tool.example/redirect'])
        self.assertEqual((lti13.lti_1p3_client_id, lti13.lti_1p3_deployment_id, lti13.passport_id), identity)
        self.assertEqual(
            (lti13.lti_1p3_client_id, lti13.lti_1p3_deployment_id),
            ('supplied-1p3-client', 'supplied-1p3-deployment'),
        )
        self.assert_not_disclosed(response, '-----BEGIN PUBLIC KEY----- PUBLIC MATERIAL')

        swap = self.client.patch(detail_url, {
            'lti_1p3': {'tool_key_mode': 'keyset_url', 'tool_keyset_url': 'https://tool.example/new-jwks'},
        }, format='json')
        self.assertEqual(swap.status_code, 200, swap.data)
        self.assertEqual(swap['Cache-Control'], 'no-store')
        lti13.refresh_from_db()
        self.assertEqual(
            (lti13.lti_1p3_tool_public_key, lti13.lti_1p3_tool_keyset_url),
            ('', 'https://tool.example/new-jwks'),
        )

        self.client.force_authenticate(self.superuser)
        retained = self.create('Retained org', context_type='organization', context_key='inactive-org')
        with patch(REGISTRY_PATCH, side_effect=AssertionError('update must not revalidate the context')):
            retained_response = self.client.patch(
                self.detail_url(retained), {'name': 'Renamed org'}, format='json',
            )
        self.assertEqual(retained_response.status_code, 200, retained_response.data)
        retained.refresh_from_db()
        self.assertEqual((retained.context_type, retained.context_key), ('organization', 'inactive-org'))

    def test_immutable_invalid_and_unauthorized_patch_is_atomic(self):
        configuration = self.create('Immutable', version='lti_1p3')
        self.course_admin.return_value = True
        detail_url = self.detail_url(configuration)
        stored = configuration_state(configuration)

        immutable_payloads = (
            {'name': 'Changed', 'context': build_context('course', str(self.other_key))},
            {'name': 'Changed', 'scope': {'course_keys': [str(self.course_key)]}},
            {'name': 'Changed', 'version': 'lti_1p1'},
            {'name': 'Changed', 'config_id': '00000000-0000-0000-0000-000000000000'},
            {'name': 'Changed', 'client_id': 'replacement-client'},
            {'name': 'Changed', 'lti_1p3': {'client_id': 'replacement-client'}},
            {'name': 'Changed', 'lti_1p3': {'deployment_id': 'replacement-deployment'}},
        )
        for actor in (self.user, self.superuser):
            self.client.force_authenticate(actor)
            for payload in immutable_payloads:
                with self.subTest(actor=actor.username, payload=payload):
                    response = self.client.patch(detail_url, payload, format='json')
                    self.assertEqual(response.status_code, 400, response.data)
                    configuration.refresh_from_db()
                    self.assertEqual(configuration_state(configuration), stored)

        self.client.force_authenticate(self.user)
        malformed = self.client.patch(
            detail_url, data=json.dumps(['not', 'an', 'object']), content_type='application/json',
        )
        self.assertEqual(malformed.status_code, 400)

        lti11 = self.create('Immutable 1.1')
        stored_lti11 = configuration_state(lti11)
        rejected = self.client.patch(self.detail_url(lti11), {'context': build_context('site')}, format='json')
        self.assertEqual(rejected.status_code, 400)
        rotation = self.client.patch(self.detail_url(lti11), {
            'lti_1p1': {'client_secret': 'rotated-secret'},
        }, format='json')
        self.assertEqual(rotation.status_code, 400)
        lti11.refresh_from_db()
        self.assertEqual(configuration_state(lti11), stored_lti11)

        self.course_admin.return_value = False
        self.assertEqual(self.client.patch(detail_url, {'name': 'Changed'}, format='json').status_code, 403)
        hidden = self.create('Hidden', context_type='course', context_key=str(self.other_key))
        self.assertEqual(
            self.client.patch(self.detail_url(hidden), {'name': 'Changed'}, format='json').status_code, 404,
        )
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 3)

    def test_version_initialization_journey_for_converted_rows(self):
        """A converted row with no version is fixable once, by the actor who manages it."""
        orphan = ReusableLtiConfiguration.objects.create(
            name='Converted orphan', version=None, context_type=None, context_key=None,
        )
        self.client.force_authenticate(self.superuser)
        initialized = self.client.patch(self.detail_url(orphan), {'version': 'lti_1p3'}, format='json')
        self.assertEqual(initialized.status_code, 200, initialized.data)
        self.assertEqual(initialized.data['version'], 'lti_1p3')
        orphan.refresh_from_db()
        self.assertEqual(orphan.version, 'lti_1p3')

        # The assignment is one-time: replacing it is an addressed 400 that writes nothing.
        stored = configuration_state(orphan)
        replaced = self.client.patch(
            self.detail_url(orphan), {'version': 'lti_1p1', 'name': 'Renamed'}, format='json',
        )
        self.assertEqual(replaced.status_code, 400, replaced.data)
        self.assertEqual(list(replaced.data), ['version'])
        orphan.refresh_from_db()
        self.assertEqual(configuration_state(orphan), stored)

        # An unsupported value is refused by the wire layer before anything is written.
        provisional = ReusableLtiConfiguration.objects.create(
            name='Converted provisional', version=None, context_type=None, context_key=None,
        )
        invalid = self.client.patch(self.detail_url(provisional), {'version': 'lti_2p0'}, format='json')
        self.assertEqual(invalid.status_code, 400, invalid.data)
        self.assertIn('version', invalid.data)
        provisional.refresh_from_db()
        self.assertIsNone(provisional.version)

        # An assigned row is initialized by the admin of its own course.
        assigned = ReusableLtiConfiguration.objects.create(
            name='Converted course tool',
            version=None,
            context_type='course',
            context_key=str(self.course_key),
        )
        self.course_admin.return_value = True
        self.client.force_authenticate(self.user)
        course_response = self.client.patch(self.detail_url(assigned), {'version': 'lti_1p1'}, format='json')
        self.assertEqual(course_response.status_code, 200, course_response.data)
        assigned.refresh_from_db()
        self.assertEqual(assigned.version, 'lti_1p1')

        # A NULL-context row stays Global-Staff-only, and version never travels with a context.
        hidden = ReusableLtiConfiguration.objects.create(
            name='Converted hidden', version=None, context_type=None, context_key=None,
        )
        self.assertEqual(
            self.client.patch(self.detail_url(hidden), {'version': 'lti_1p3'}, format='json').status_code,
            404,
        )
        self.client.force_authenticate(self.superuser)
        mixed = self.client.patch(
            self.detail_url(hidden),
            {'version': 'lti_1p3', 'context': build_context('site')},
            format='json',
        )
        self.assertEqual(mixed.status_code, 400, mixed.data)
        self.assertEqual(list(mixed.data), ['context'])
        hidden.refresh_from_db()
        self.assertEqual((hidden.version, hidden.context_type), (None, None))

    def test_update_authorization_precedes_semantic_validation(self):
        """Hidden and unmanageable targets answer before any semantic check."""
        hidden = self.create('Hidden validation', context_type='course', context_key=str(self.other_key))
        visible = self.create('Visible validation')
        self.course_admin.return_value = False
        semantically_invalid = {'name': 'x' * 300}
        missing = self.client.patch(self.detail_url(hidden), semantically_invalid, format='json')
        self.assertEqual(missing.status_code, 404)
        self.assertIn('detail', missing.data)
        self.assertEqual(
            self.client.patch(self.detail_url(visible), semantically_invalid, format='json').status_code, 403,
        )

    def test_error_response_styles_are_preserved(self):
        configuration = self.create('First tool')
        self.create('Second tool')
        self.course_admin.return_value = True

        field_error = self.client.patch(self.detail_url(configuration), {
            'lti_1p1': {'launch_url': 'javascript:bad'},
        }, format='json')
        self.assertEqual(field_error.status_code, 400)
        self.assertIn('launch_url', field_error.data['lti_1p1'])

        create_error = self.client.post(self.list_url, lti11_create_payload(
            build_context('course', COURSE_KEY), name='x' * 300,
        ), format='json')
        self.assertEqual(create_error.status_code, 400)
        self.assertIn('name', create_error.data)

    def test_wire_shape_failures_do_not_reveal_targets(self):
        hidden = self.create('Hidden shape', context_type='course', context_key=str(self.other_key))
        self.course_admin.return_value = True
        unknown_url = reverse(
            'reusable_lti:reusable_configuration_detail',
            kwargs={'config_id': uuid.uuid4()},
        )
        payload = {'name': 'Changed', 'unknown_member': True}
        hidden_response = self.client.patch(self.detail_url(hidden), payload, format='json')
        unknown_response = self.client.patch(unknown_url, payload, format='json')
        self.assertEqual((hidden_response.status_code, unknown_response.status_code), (400, 400))
        self.assertEqual(hidden_response.data, unknown_response.data)

    def test_lti13_patch_rolls_back_when_passport_write_fails(self):
        configuration = self.create('Atomic tool-key update', version='lti_1p3')
        self.course_admin.return_value = True
        stored = configuration_state(configuration)

        with patch(
            'lti_consumer.models.ReusableLtiConfiguration.save',
            side_effect=IntegrityError('injected passport failure'),
        ):
            response = self.client.patch(self.detail_url(configuration), {
                'name': 'Must roll back',
                'lti_1p3': {
                    'tool_key_mode': 'public_key',
                    'tool_public_key': '-----BEGIN PUBLIC KEY----- replacement',
                },
            }, format='json')

        self.assertEqual(response.status_code, 400, response.data)
        configuration.refresh_from_db()
        self.assertEqual(configuration_state(configuration), stored)

    def test_duplicate_names_and_rejected_writes_are_non_disclosing(self):
        configuration = self.create('Original')
        hidden = self.create('Hidden name', context_type='course', context_key=str(self.other_key))
        self.course_admin.return_value = True

        # Duplicate names are allowed, and another configuration's identity is never disclosed.
        allowed = self.client.patch(self.detail_url(configuration), {'name': ' hidden name '}, format='json')
        self.assertEqual(allowed.status_code, 200)
        self.assertNotIn(str(hidden.config_id), allowed.content.decode())
        configuration.refresh_from_db()
        self.assertEqual(configuration.name, 'hidden name')

        # A rejected write stays atomic and non-disclosing, even when it names the
        # other configuration: the response must not echo either identity.
        updated_at = configuration.updated_at
        response = self.client.patch(self.detail_url(configuration), {
            'name': hidden.name,
            'description': 'Must not persist',
            'unknown_member': True,
        }, format='json')
        self.assertEqual(response.status_code, 400)
        body = response.content.decode().lower()
        self.assertNotIn(str(hidden.config_id), body)
        self.assertNotIn(hidden.name.lower(), body)
        configuration.refresh_from_db()
        hidden.refresh_from_db()
        self.assertEqual((configuration.name, configuration.description), ('hidden name', ''))
        self.assertEqual(configuration.updated_at, updated_at)
        self.assertEqual(hidden.name, 'Hidden name')

        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        denied = csrf_client.patch(self.detail_url(configuration), {'name': 'Updated'}, format='json')
        self.assertEqual(denied.status_code, 403)
        self.assertIn('CSRF', str(denied.data['detail']))

        token = 'a' * 32
        csrf_client.cookies['csrftoken'] = token
        allowed = csrf_client.patch(
            self.detail_url(configuration), {'name': 'Updated'}, format='json', HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(allowed.status_code, 200, allowed.data)
        configuration.refresh_from_db()
        self.assertEqual(configuration.name, 'Updated')

    def test_list_uses_platform_candidates_and_rechecks_read_access(self):
        self.create('Readable')
        self.create('Unreadable', context_type='course', context_key=str(self.other_key))
        self.course_access_patcher.stop()
        self.addCleanup(self.course_access_patcher.start)
        with patch(CANDIDATES_PATCH) as candidates, patch(
            READ_ACCESS_PATCH, side_effect=lambda user, key: key == self.course_key,
        ):
            candidates.return_value = [SimpleNamespace(id=self.course_key), SimpleNamespace(id=self.other_key)]
            response = self.client.get(
                self.list_url, {'search': 'Readable', 'start_date_on_or_after': '2099-01-01'},
            )
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['name'], 'Readable')
        self.assertEqual(candidates.call_args.args[0].GET, {})

    def test_mysql_collation_matches_case_and_separates_accents(self):
        if connection.vendor != 'mysql' or getattr(connection, 'mysql_is_mariadb', False):
            self.skipTest('MySQL 8-only collation check.')
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COLUMN_NAME, COLLATION_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'lti_consumer_reusablelticonfiguration' "
                "AND COLUMN_NAME = 'context_key'"
            )
            self.assertEqual(dict(cursor.fetchall()), {'context_key': 'utf8mb4_0900_as_ci'})
        self.create('Case variant course', context_type='course', context_key='course-v1:ORG+COURSE+RUN')
        self.create('Accented course', context_type='course', context_key='course-v1:Org+Cóurse+Run')
        self.create('Plain org', context_type='organization', context_key='Org')
        self.create('Accented org', context_type='organization', context_key='Órg')
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 4)

        # Default listing resolves the accessible course through the request-independent
        # context query; ?course_key= would bypass it with a Python precheck.
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(
            [(row['name'], row['context']) for row in response.data['results']],
            [
                ('Case variant course', build_context('course', 'course-v1:ORG+COURSE+RUN')),
                ('Plain org', build_context('organization', 'org')),
            ],
        )


class GlobalStaffJourneyTests(ReusableApiTestCase):
    """One non-superuser Global Staff journey; superuser retention stays in the existing tests."""

    def setUp(self):
        super().setUp()
        self.staff = get_user_model().objects.create_user(username='staff', is_staff=True)

    def test_global_staff_assigns_an_unassigned_configuration_once(self):
        """A converted row is hidden from ordinary users and assignable once by Global Staff."""
        unassigned = ReusableLtiConfiguration.objects.create(
            name='Converted orphan',
            version=ReusableLtiConfiguration.LTI_1P3,
        )
        detail = self.detail_url(unassigned)
        course_context = build_context('course', COURSE_KEY)

        self.course_admin.return_value = True
        hidden = self.client.patch(detail, {'context': course_context}, format='json')
        self.assertEqual(hidden.status_code, 404)
        unassigned.refresh_from_db()
        self.assertIsNone(unassigned.context_type)

        self.client.force_authenticate(self.staff)
        listing = self.client.get(self.list_url)
        self.assertEqual(listing.status_code, 200)
        self.assertIn('Converted orphan', {row['name'] for row in listing.data['results']})

        assigned = self.client.patch(detail, {'context': course_context}, format='json')
        self.assertEqual(assigned.status_code, 200, assigned.data)
        self.assertEqual(assigned.data['context'], course_context)
        self.assertTrue(assigned.data['can_manage'])

        second = self.client.patch(detail, {'context': build_context('site')}, format='json')
        self.assertEqual(second.status_code, 400)
        self.assertIn('context', second.data)

        stored = ReusableLtiConfiguration.objects.get(pk=unassigned.pk)
        self.assertEqual((stored.context_type, stored.context_key), ('course', COURSE_KEY))

    def test_global_staff_manages_course_organization_site_and_ccx(self):
        self.client.force_authenticate(self.staff)
        with patch(REGISTRY_PATCH, return_value=[{'short_name': 'Org'}]):
            course = self.client.post(self.list_url, lti11_create_payload(
                build_context('course', COURSE_KEY), name='Staff course',
            ), format='json')
            organization = self.client.post(self.list_url, lti11_create_payload(
                build_context('organization', ' ORG '), name='Staff organization',
            ), format='json')
            site = self.client.post(self.list_url, lti11_create_payload(
                build_context('site'), name='Staff site',
            ), format='json')
            ccx = self.client.post(self.list_url, lti11_create_payload(
                build_context('course', CCX_KEY), name='Staff ccx',
            ), format='json')

        self.course_admin.assert_not_called()
        self.assertEqual(
            (course.status_code, organization.status_code, site.status_code, ccx.status_code),
            (201, 201, 201, 201),
            (course.data, organization.data, site.data, ccx.data),
        )
        self.assertEqual(organization.data['context'], build_context('organization', 'org'))
        self.assertEqual(site.data['context'], {'type': 'site'})
        self.assertEqual(ccx.data['context'], build_context('course', CCX_KEY))
        secret = course.data['one_time_credentials']['client_secret']

        with patch(COURSE_ACCESS_PATCH, side_effect=AssertionError('must not enumerate courses')):
            listing = self.client.get(self.list_url)
            filtered = self.client.get(self.list_url, {'course_key': COURSE_KEY})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data['count'], 4)
        self.assertEqual(
            {row['name'] for row in listing.data['results']},
            {'Staff course', 'Staff organization', 'Staff site', 'Staff ccx'},
        )
        self.assertTrue(all(row['can_manage'] for row in listing.data['results']))
        for row in listing.data['results']:
            for forbidden in FORBIDDEN_RESPONSE_FIELDS:
                self.assertNotIn(forbidden, row)
        self.assert_not_disclosed(listing, secret)
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(
            {row['name'] for row in filtered.data['results']},
            {'Staff course', 'Staff organization', 'Staff site'},
        )

        stored = {
            name: ReusableLtiConfiguration.objects.get(name=name)
            for name in ('Staff course', 'Staff organization', 'Staff site', 'Staff ccx')
        }
        for name, expected_context in (
            ('Staff course', build_context('course', COURSE_KEY)),
            ('Staff organization', build_context('organization', 'org')),
            ('Staff site', {'type': 'site'}),
            ('Staff ccx', build_context('course', CCX_KEY)),
        ):
            with self.subTest(detail=name):
                detail = self.client.get(self.detail_url(stored[name]))
                self.assertEqual(detail.status_code, 200)
                self.assertTrue(detail.data['can_manage'])
                self.assertEqual(detail.data['context'], expected_context)
                self.assert_not_disclosed(detail, secret)

        for name, renamed in (
            ('Staff course', 'Staff course renamed'),
            ('Staff organization', 'Staff organization renamed'),
            ('Staff site', 'Staff site renamed'),
            ('Staff ccx', 'Staff ccx renamed'),
        ):
            with self.subTest(patch=name):
                response = self.client.patch(
                    self.detail_url(stored[name]), {'name': renamed}, format='json',
                )
                self.assertEqual(response.status_code, 200, response.data)
                self.assertTrue(response.data['can_manage'])

        self.client.force_authenticate(self.user)
        self.assertEqual(
            self.client.patch(
                self.detail_url(stored['Staff site']), {'name': 'Ordinary rename'}, format='json',
            ).status_code,
            403,
        )
