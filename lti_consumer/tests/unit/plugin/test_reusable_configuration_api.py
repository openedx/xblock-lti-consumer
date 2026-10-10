"""API tests for CMS reusable-configuration listing and creation."""
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from opaque_keys.edx.keys import CourseKey
from rest_framework.test import APIClient

from lti_consumer.models import ReusableLtiConfiguration
from lti_consumer.reusable import create_reusable_configuration


class ReusableConfigurationCreateApiTests(TestCase):
    """Creation is authenticated, scope-authorized, and returns secrets once."""

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username='author', password='password')
        self.superuser = user_model.objects.create_superuser(
            username='admin', email='admin@example.com', password='password'
        )
        self.url = reverse('reusable_lti:reusable_configuration_create')
        self.payload = {
            'name': 'API-created tool',
            'version': 'lti_1p1',
            'scope': {'course_keys': ['course-v1:Org+Course+Run']},
            'lti_1p1': {'launch_url': 'https://tool.example/launch'},
        }

    def test_authenticated_course_manager_can_create_and_receive_one_time_secret(self):
        client = APIClient()
        client.force_authenticate(self.user)
        with patch('lti_consumer.plugin.reusable_views.can_manage_reusable_scope', return_value=True):
            response = client.post(self.url, self.payload, format='json')

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 1)
        self.assertTrue(response.data['one_time_credentials']['client_secret'])
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_lti13_create_returns_registration_identity_without_credentials(self):
        client = APIClient()
        client.force_authenticate(self.user)
        payload = {
            'name': 'API-created LTI 1.3 tool',
            'version': 'lti_1p3',
            'scope': {'course_keys': ['course-v1:Org+Course+Run']},
            'lti_1p3': {
                'launch_url': 'https://tool.example/launch',
                'oidc_url': 'https://tool.example/oidc',
                'tool_key_mode': 'keyset_url',
                'tool_keyset_url': 'https://tool.example/jwks',
            },
        }
        with patch('lti_consumer.plugin.reusable_views.can_manage_reusable_scope', return_value=True):
            response = client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data['client_id'])
        self.assertTrue(response.data['deployment_id'])
        self.assertNotIn('one_time_credentials', response.data)
        self.assertNotIn('lti_1p3_private_key', response.data)
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_unauthenticated_and_unauthorized_requests_do_not_create(self):
        response = APIClient().post(self.url, self.payload, format='json')
        self.assertEqual(response.status_code, 403)

        client = APIClient()
        client.force_authenticate(self.user)
        with patch('lti_consumer.plugin.reusable_views.can_manage_reusable_scope', return_value=False):
            response = client.post(self.url, self.payload, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 0)

    @patch('lti_consumer.plugin.reusable_serializers.compat.get_active_organizations')
    def test_superuser_can_create_with_registered_organization_scope(self, get_organizations):
        get_organizations.return_value = [{'short_name': 'Org'}]
        client = APIClient()
        client.force_authenticate(self.superuser)
        payload = {
            'name': 'Organization tool',
            'version': 'lti_1p1',
            'scope': {'organization_keys': ['ORG']},
            'lti_1p1': {'launch_url': 'https://tool.example/launch'},
        }

        response = client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['scope']['organization_keys'], ['org'])
        get_organizations.assert_called_once_with()

    @patch('lti_consumer.plugin.reusable_serializers.compat.get_active_organizations')
    def test_non_superuser_org_scope_is_denied_before_registry_lookup(self, get_organizations):
        client = APIClient()
        client.force_authenticate(self.user)
        payload = {
            **self.payload,
            'scope': {'organization_keys': ['org']},
        }

        response = client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, 403)
        get_organizations.assert_not_called()
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 0)

    def test_session_authenticated_post_requires_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(self.url, self.payload, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 0)


class ReusableConfigurationListApiTests(TestCase):
    """Visibility is the union of course/org/site scope, not management authority."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username='viewer')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = reverse('reusable_lti:reusable_configuration_create')
        self.course_key = CourseKey.from_string('course-v1:Org+Course+Run')
        self.other_key = CourseKey.from_string('course-v1:Hidden+Other+Run')
        self.course_access_patcher = patch(
            'lti_consumer.plugin.reusable_views.compat.get_studio_accessible_course_keys',
            return_value=[self.course_key],
        )
        self.course_access = self.course_access_patcher.start()
        self.addCleanup(self.course_access_patcher.stop)
        course_admin_patcher = patch(
            'lti_consumer.plugin.reusable_permissions.compat.user_is_course_admin',
            return_value=False,
        )
        self.course_admin = course_admin_patcher.start()
        self.addCleanup(course_admin_patcher.stop)

    def create(self, name, **scope):
        """Create complete fixtures without invoking the platform registry."""
        return create_reusable_configuration({
            'name': name,
            'version': 'lti_1p1',
            'scope': scope,
            'lti_1p1': {
                'launch_url': 'https://tool.example/launch',
                'client_key': 'not-for-list',
                'client_secret': 'secret-not-for-list',
            },
            'defaults': {'custom_parameters': ['secret=value']},
        }).configuration

    def test_scope_union_returns_only_visible_records_with_safe_fields(self):
        self.create('Course', course_keys=[str(self.course_key)])
        self.create('Organization', organization_keys=['ORG'])
        self.create('Site', site_wide=True)
        self.create('Hidden', course_keys=[str(self.other_key)])
        self.create('Hidden org', organization_keys=['hidden'])
        self.create('Library', course_keys=['library-v1:Org+Library'])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 3)
        self.assertEqual([row['name'] for row in response.data['results']], ['Course', 'Organization', 'Site'])
        allowed = {
            'config_id', 'name', 'version', 'scope_summary', 'created_at', 'updated_at',
            'can_manage', 'deep_linking_enabled', 'ags_mode', 'nrps_enabled',
        }
        for row in response.data['results']:
            self.assertEqual(set(row), allowed)
            self.assertFalse(row['can_manage'])
        self.assertNotIn('secret-not-for-list', response.content.decode())
        self.assertNotIn(str(self.other_key), response.content.decode())
        self.course_access.assert_called_once_with(self.user)

    def test_no_studio_access_returns_no_records_even_for_site_scope(self):
        self.create('Site', site_wide=True)
        self.course_access.return_value = []
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 0)
        self.assertEqual(response.data['results'], [])
        self.course_admin.assert_not_called()

    def test_superuser_sees_all_without_enumerating_courses(self):
        self.user.is_superuser = True
        self.user.save()
        self.create('Hidden', course_keys=[str(self.other_key)])
        self.create('Organization', organization_keys=['absent-from-registry'])
        self.create('Site', site_wide=True)
        response = self.client.get(self.url)
        self.assertEqual(response.data['count'], 3)
        self.assertTrue(all(row['can_manage'] for row in response.data['results']))
        self.course_access.assert_not_called()
        self.course_admin.assert_not_called()

    def test_anonymous_get_is_denied(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.course_access.assert_not_called()

    def test_can_manage_requires_admin_of_every_explicit_course(self):
        self.create('Managed', course_keys=[str(self.course_key)])
        self.create('Shared', course_keys=[str(self.course_key), str(self.other_key)])
        self.create('Organization', organization_keys=['org'])
        self.create('Site', site_wide=True)
        self.course_admin.side_effect = lambda user, key: key == self.course_key
        response = self.client.get(self.url)
        manageable = {row['name']: row['can_manage'] for row in response.data['results']}
        self.assertEqual(manageable, {'Managed': True, 'Shared': False, 'Organization': False, 'Site': False})
        # Shared course checks are cached across configurations in this page.
        self.assertEqual(self.course_admin.call_count, 2)

    def test_retained_org_coverage_does_not_consult_active_registry(self):
        self.create('Retained', organization_keys=['org'])
        with patch('lti_consumer.plugin.compat.get_active_organizations', side_effect=AssertionError):
            response = self.client.get(self.url)
        self.assertEqual(response.data['count'], 1)

    def test_search_and_version_filters_do_not_change_course_enumeration(self):
        self.create('Matching tool', course_keys=[str(self.course_key)])
        self.create('Other tool', course_keys=[str(self.course_key)])
        self.create('Matching hidden', course_keys=[str(self.other_key)])
        response = self.client.get(self.url, {
            'search': 'Matching', 'version': 'lti_1p1', 'start_date_on_or_after': '2099-01-01',
        })
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['name'], 'Matching tool')
        self.course_access.assert_called_once_with(self.user)
        response = self.client.get(self.url, {'version': 'lti_1p3'})
        self.assertEqual(response.data['results'], [])

    def test_pagination_is_stable_without_duplicate_join_rows(self):
        self.create('Alpha', course_keys=[str(self.course_key)], organization_keys=['org'], site_wide=True)
        self.create('Beta', course_keys=[str(self.course_key)])
        first = self.client.get(self.url, {'page_size': 1})
        self.assertEqual(first.data['count'], 2)
        self.assertEqual(first.data['results'][0]['name'], 'Alpha')
        self.assertIsNotNone(first.data['next'])
        second = self.client.get(first.data['next'])
        self.assertEqual(second.data['results'][0]['name'], 'Beta')
        self.assertIsNone(second.data['next'])

    def test_list_uses_neutral_wrapper_and_rechecks_candidate_read_access(self):
        self.create('Readable', course_keys=[str(self.course_key)])
        self.create('Unreadable', course_keys=[str(self.other_key)])
        self.course_access_patcher.stop()
        with patch('lti_consumer.plugin.compat._get_studio_course_candidates') as candidates, patch(
            'lti_consumer.plugin.compat._has_studio_course_read_access',
            side_effect=lambda user, key: key == self.course_key,
        ):
            candidates.return_value = [SimpleNamespace(id=self.course_key), SimpleNamespace(id=self.other_key)]
            response = self.client.get(self.url, {'search': 'Readable', 'start_date_on_or_after': '2099-01-01'})
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['name'], 'Readable')
        self.assertEqual(candidates.call_args.args[0].GET, {})

    def test_catalog_queries_are_batched(self):
        for index in range(5):
            self.create(f'Tool {index}', course_keys=[str(self.course_key)])
        # Count, configurations, and two grant prefetches; no per-record queries.
        with self.assertNumQueries(4):
            response = self.client.get(self.url)
        self.assertEqual(response.data['count'], 5)
        self.assertEqual(self.course_admin.call_count, 1)
