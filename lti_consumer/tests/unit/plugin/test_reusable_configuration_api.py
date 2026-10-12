"""API tests for CMS reusable-configuration listing and creation."""
import json
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

    def test_detail_uses_list_visibility_and_safe_scope_projection(self):
        visible = self.create('Visible', course_keys=[str(self.course_key)])
        hidden = self.create('Hidden', course_keys=[str(self.other_key)])
        visible_url = reverse(
            'reusable_lti:reusable_configuration_detail', kwargs={'config_id': visible.config_id},
        )
        hidden_url = reverse(
            'reusable_lti:reusable_configuration_detail', kwargs={'config_id': hidden.config_id},
        )

        response = self.client.get(visible_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'Visible')
        self.assertFalse(response.data['can_manage'])
        self.assertEqual(response.data['scope'], {
            'site_wide': False,
            'summary': {'site_wide': False, 'course_count': 1, 'organization_count': 0},
        })
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertNotIn('client_secret', response.data)
        self.assertNotIn('secret-not-for-list', response.content.decode())
        self.assertNotIn(str(self.course_key), response.content.decode())
        self.assertEqual(self.client.get(hidden_url).status_code, 404)

    def test_detail_returns_explicit_grants_only_to_managers(self):
        configuration = self.create('Managed', course_keys=[str(self.course_key)])
        self.course_admin.return_value = True
        detail_url = reverse(
            'reusable_lti:reusable_configuration_detail', kwargs={'config_id': configuration.config_id},
        )

        response = self.client.get(detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['can_manage'])
        self.assertEqual(response.data['scope']['course_keys'], [str(self.course_key)])
        self.assertEqual(response.data['launch_url'], 'https://tool.example/launch')
        self.assertNotIn('secret-not-for-list', response.content.decode())
        self.assertNotIn('not-for-list', response.content.decode())

    def test_patch_updates_editable_metadata_without_rotating_credentials(self):
        configuration = self.create('Before', course_keys=[str(self.course_key)])
        client_secret = configuration.lti_1p1_client_secret
        self.course_admin.return_value = True
        detail_url = reverse(
            'reusable_lti:reusable_configuration_detail', kwargs={'config_id': configuration.config_id},
        )

        response = self.client.patch(detail_url, {
            'name': 'After',
            'description': 'Updated description',
            'launch_url': 'https://tool.example/new-launch',
            'services': {'nrps_enabled': True},
            'defaults': {'display_name': 'Updated display'},
        }, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        configuration.refresh_from_db()
        self.assertEqual(configuration.name, 'After')
        self.assertEqual(configuration.description, 'Updated description')
        self.assertEqual(configuration.lti_1p1_launch_url, 'https://tool.example/new-launch')
        self.assertEqual(configuration.display_name, 'Updated display')
        self.assertEqual(configuration.custom_parameters, ['secret=value'])
        self.assertEqual(configuration.lti_advantage_ags_mode, 'declarative')
        self.assertTrue(configuration.lti_advantage_enable_nrps)
        self.assertEqual(configuration.lti_1p1_client_secret, client_secret)
        self.assertNotIn(client_secret, response.content.decode())
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_lti13_patch_persists_effective_empty_redirect_fallback_and_preserves_omitted_settings(self):
        configuration = create_reusable_configuration({
            'name': 'Redirect fallback',
            'version': 'lti_1p3',
            'scope': {'course_keys': [str(self.course_key)]},
            'lti_1p3': {
                'launch_url': 'https://tool.example/launch',
                'oidc_url': 'https://tool.example/oidc',
                'redirect_uris': ['https://tool.example/old-redirect'],
                'tool_key_mode': 'keyset_url',
                'tool_keyset_url': 'https://tool.example/jwks',
            },
            'services': {'deep_linking_launch_url': 'https://tool.example/deep'},
            'defaults': {'custom_parameters': ['keep=this']},
        }).configuration
        self.course_admin.return_value = True
        detail_url = reverse(
            'reusable_lti:reusable_configuration_detail', kwargs={'config_id': configuration.config_id},
        )

        omitted = self.client.patch(detail_url, {
            'launch_url': 'https://tool.example/new-launch',
            'services': {'nrps_enabled': True},
            'defaults': {'display_name': 'Updated'},
        }, format='json')
        self.assertEqual(omitted.status_code, 200, omitted.data)
        configuration.refresh_from_db()
        self.assertEqual(configuration.lti_1p3_redirect_uris, ['https://tool.example/old-redirect'])
        self.assertEqual(configuration.lti_advantage_deep_linking_launch_url, 'https://tool.example/deep')
        self.assertEqual(configuration.custom_parameters, ['keep=this'])
        self.assertEqual(configuration.display_name, 'Updated')

        fallback = self.client.patch(detail_url, {'redirect_uris': []}, format='json')
        self.assertEqual(fallback.status_code, 200, fallback.data)
        configuration.refresh_from_db()
        self.assertEqual(configuration.lti_1p3_redirect_uris, [
            'https://tool.example/new-launch', 'https://tool.example/deep',
        ])

    def test_invalid_combined_patch_makes_no_writes(self):
        configuration = self.create('No partial writes', course_keys=[str(self.course_key)])
        invalid_stored_url = 'javascript:stored-invalid'
        ReusableLtiConfiguration.objects.filter(pk=configuration.pk).update(
            lti_advantage_deep_linking_launch_url=invalid_stored_url,
        )
        configuration.refresh_from_db()
        updated_at = configuration.updated_at
        self.course_admin.return_value = True
        detail_url = reverse(
            'reusable_lti:reusable_configuration_detail', kwargs={'config_id': configuration.config_id},
        )

        response = self.client.patch(detail_url, {
            'name': 'Must not persist',
            'launch_url': 'https://tool.example/new-launch',
            'services': {'nrps_enabled': True},
            'defaults': {'display_name': 'Must not persist'},
            'scope': {'course_keys': [str(self.other_key)]},
        }, format='json')

        self.assertEqual(response.status_code, 400)
        configuration.refresh_from_db()
        self.assertEqual(configuration.name, 'No partial writes')
        self.assertEqual(configuration.lti_1p1_launch_url, 'https://tool.example/launch')
        self.assertEqual(configuration.lti_advantage_deep_linking_launch_url, invalid_stored_url)
        self.assertFalse(configuration.lti_advantage_enable_nrps)
        self.assertEqual(configuration.display_name, 'LTI Consumer')
        self.assertEqual(configuration.updated_at, updated_at)
        self.assertEqual(set(configuration.course_grants.values_list('course_key', flat=True)), {self.course_key})

    def test_patch_adds_scope_grants_idempotently_and_never_removes(self):
        configuration = self.create('Expandable', course_keys=[str(self.course_key)])
        self.course_admin.return_value = True
        detail_url = reverse(
            'reusable_lti:reusable_configuration_detail', kwargs={'config_id': configuration.config_id},
        )
        patch_data = {'scope': {'course_keys': [str(self.other_key)]}}

        first = self.client.patch(detail_url, patch_data, format='json')
        second = self.client.patch(detail_url, patch_data, format='json')

        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(
            set(configuration.course_grants.values_list('course_key', flat=True)),
            {self.course_key, self.other_key},
        )
        self.assertEqual(configuration.course_grants.count(), 2)
        self.assertEqual(self.client.patch(detail_url, {'scope': {'course_keys': []}}, format='json').status_code, 200)

    def test_patch_authorizes_proposed_scope_and_rejects_identity_fields(self):
        configuration = self.create('Protected', course_keys=[str(self.course_key)])
        self.course_admin.side_effect = lambda user, key: key == self.course_key
        detail_url = reverse(
            'reusable_lti:reusable_configuration_detail', kwargs={'config_id': configuration.config_id},
        )

        denied = self.client.patch(detail_url, {
            'scope': {'course_keys': [str(self.other_key)]},
        }, format='json')
        invalid = self.client.patch(detail_url, {'client_secret': 'replacement'}, format='json')

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(configuration.course_grants.count(), 1)
        configuration.refresh_from_db()
        self.assertEqual(configuration.name, 'Protected')

    @patch('lti_consumer.plugin.reusable_serializers.compat.get_active_organizations')
    def test_non_superuser_cannot_add_org_scope_before_registry_lookup(self, get_organizations):
        configuration = self.create('Course only', course_keys=[str(self.course_key)])
        self.course_admin.return_value = True
        detail_url = reverse(
            'reusable_lti:reusable_configuration_detail', kwargs={'config_id': configuration.config_id},
        )

        response = self.client.patch(detail_url, {
            'scope': {'organization_keys': ['org']},
        }, format='json')

        self.assertEqual(response.status_code, 403)
        get_organizations.assert_not_called()
        self.assertEqual(configuration.organization_grants.count(), 0)

    @patch('lti_consumer.plugin.reusable_serializers.compat.get_active_organizations')
    def test_patch_retains_inactive_org_grants_and_validates_new_orgs(self, get_organizations):
        self.user.is_superuser = True
        self.user.save()
        configuration = self.create('Organizations', organization_keys=['inactive-org'])
        get_organizations.return_value = [{'short_name': 'New-Org'}]
        detail_url = reverse(
            'reusable_lti:reusable_configuration_detail', kwargs={'config_id': configuration.config_id},
        )

        response = self.client.patch(detail_url, {
            'scope': {'organization_keys': ['inactive-org', 'NEW-ORG']},
        }, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['scope']['organization_keys'], ['inactive-org', 'new-org'])
        get_organizations.assert_called_once_with()

    def test_patch_requires_valid_deep_link_url_and_cannot_reduce_site_scope(self):
        configuration = self.create('Deep link', course_keys=[str(self.course_key)])
        self.course_admin.return_value = True
        detail_url = reverse(
            'reusable_lti:reusable_configuration_detail', kwargs={'config_id': configuration.config_id},
        )
        invalid = self.client.patch(detail_url, {
            'services': {'deep_linking_enabled': True},
        }, format='json')
        self.assertEqual(invalid.status_code, 400)
        self.assertFalse(configuration.lti_advantage_deep_linking_enabled)

        self.user.is_superuser = True
        self.user.save()
        configuration.site_wide = True
        configuration.save(update_fields=['site_wide'])
        reduced = self.client.patch(detail_url, {'scope': {'site_wide': False}}, format='json')
        self.assertEqual(reduced.status_code, 400)
        configuration.refresh_from_db()
        self.assertTrue(configuration.site_wide)

    def test_patch_rejects_malformed_bodies_without_writes(self):
        configuration = self.create('Unchanged', course_keys=[str(self.course_key)])
        updated_at = configuration.updated_at
        self.course_admin.return_value = True
        detail_url = reverse(
            'reusable_lti:reusable_configuration_detail', kwargs={'config_id': configuration.config_id},
        )
        payloads = (
            None, False, 1, 'invalid', [], [{'name': 'Changed'}],
            {'name': 'Changed', 'scope': []},
            {'name': 'Changed', 'services': []},
            {'name': 'Changed', 'defaults': []},
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
                self.assertEqual(configuration.course_grants.count(), 1)
                self.assertEqual(ReusableLtiConfiguration.objects.count(), 1)

    def test_patch_rejects_validated_false_site_scope_values(self):
        self.user.is_superuser = True
        self.user.save()
        configuration = self.create('Site scoped', course_keys=[str(self.course_key)], site_wide=True)
        updated_at = configuration.updated_at
        detail_url = reverse(
            'reusable_lti:reusable_configuration_detail', kwargs={'config_id': configuration.config_id},
        )

        for value in (False, 0, 'false', 'False', '0', 'off'):
            with self.subTest(value=value):
                response = self.client.patch(detail_url, {
                    'description': 'Must not persist',
                    'scope': {'site_wide': value},
                }, format='json')
                self.assertEqual(response.status_code, 400)
                self.assertIn('Scope reductions', str(response.data['scope']))
                configuration.refresh_from_db()
                self.assertTrue(configuration.site_wide)
                self.assertEqual(configuration.description, '')
                self.assertEqual(configuration.updated_at, updated_at)

        retained = self.client.patch(detail_url, {
            'description': 'Metadata update', 'scope': {},
        }, format='json')
        self.assertEqual(retained.status_code, 200, retained.data)
        configuration.refresh_from_db()
        self.assertTrue(configuration.site_wide)
        self.assertEqual(configuration.description, 'Metadata update')
        self.assertEqual(configuration.course_grants.count(), 1)

    def test_patch_hides_invisible_ids_and_requires_current_scope_management(self):
        configuration = self.create('Read only', course_keys=[str(self.course_key), str(self.other_key)])
        hidden = self.create('Hidden', course_keys=[str(self.other_key)])
        self.course_admin.side_effect = lambda user, key: key == self.course_key

        for record, expected_status in ((configuration, 403), (hidden, 404)):
            detail_url = reverse(
                'reusable_lti:reusable_configuration_detail', kwargs={'config_id': record.config_id},
            )
            for payload in ({'name': 'Changed', 'scope': {'course_keys': [str(self.course_key)]}}, []):
                with self.subTest(config_id=record.config_id, payload=payload):
                    response = self.client.patch(
                        detail_url, data=json.dumps(payload), content_type='application/json',
                    )
                    self.assertEqual(response.status_code, expected_status)

        configuration.refresh_from_db()
        hidden.refresh_from_db()
        self.assertEqual(configuration.name, 'Read only')
        self.assertEqual(configuration.course_grants.count(), 2)
        self.assertEqual(hidden.name, 'Hidden')
        self.assertEqual(hidden.course_grants.count(), 1)

    def test_session_authenticated_patch_requires_csrf(self):
        configuration = self.create('Session update', course_keys=[str(self.course_key)])
        self.course_admin.return_value = True
        detail_url = reverse(
            'reusable_lti:reusable_configuration_detail', kwargs={'config_id': configuration.config_id},
        )
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
        configuration = self.create('Original', course_keys=[str(self.course_key)])
        hidden = self.create('Hidden conflict', course_keys=[str(self.other_key)])
        updated_at = configuration.updated_at
        self.course_admin.return_value = True
        detail_url = reverse(
            'reusable_lti:reusable_configuration_detail', kwargs={'config_id': configuration.config_id},
        )

        response = self.client.patch(detail_url, {
            'name': ' hidden CONFLICT ',
            'description': 'Must not persist',
            'scope': {'course_keys': [str(self.other_key)]},
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertNotIn(str(hidden.config_id), response.content.decode())
        self.assertNotIn(hidden.name, response.content.decode())
        configuration.refresh_from_db()
        self.assertEqual(configuration.name, 'Original')
        self.assertEqual(configuration.normalized_name, 'original')
        self.assertEqual(configuration.description, '')
        self.assertEqual(configuration.updated_at, updated_at)
        self.assertEqual(list(configuration.course_grants.values_list('course_key', flat=True)), [self.course_key])
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 2)

    def test_lti13_patch_preserves_identity_and_keys_and_rejects_immutable_writes(self):
        configuration = create_reusable_configuration({
            'name': 'LTI 1.3 before update',
            'version': 'lti_1p3',
            'scope': {'course_keys': [str(self.course_key)]},
            'lti_1p3': {
                'launch_url': 'https://tool.example/launch',
                'oidc_url': 'https://tool.example/oidc',
                'tool_key_mode': 'keyset_url',
                'tool_keyset_url': 'https://tool.example/jwks',
            },
        }).configuration
        passport = configuration.lti_1p3_passport
        identity = {field: getattr(configuration, field) for field in (
            'config_id', 'version', 'lti_1p3_client_id', 'lti_1p3_deployment_id', 'lti_1p3_passport_id',
        )}
        passport_state = {field: getattr(passport, field) for field in (
            'passport_id', 'lti_1p3_client_id', 'lti_1p3_internal_private_key',
            'lti_1p3_internal_private_key_id', 'lti_1p3_internal_public_jwk',
            'lti_1p3_tool_public_key', 'lti_1p3_tool_keyset_url',
        )}
        self.course_admin.return_value = True
        detail_url = reverse(
            'reusable_lti:reusable_configuration_detail', kwargs={'config_id': configuration.config_id},
        )

        with patch('lti_consumer.models.Lti1p3Passport.generate_lti_1p3_keys_if_missing') as generate_keys:
            response = self.client.patch(detail_url, {
                'name': 'Updated LTI 1.3',
                'launch_url': 'https://tool.example/new-launch',
                'oidc_url': 'https://tool.example/new-oidc',
                'redirect_uris': ['https://tool.example/redirect'],
                'services': {'nrps_enabled': True},
                'defaults': {'display_name': 'Updated display'},
            }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        generate_keys.assert_not_called()
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertNotIn('one_time_credentials', response.data)
        self.assertEqual(
            response.content.count(json.dumps(passport_state['lti_1p3_internal_private_key']).encode()), 0,
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
        configuration.refresh_from_db()
        passport.refresh_from_db()
        self.assertEqual(configuration.name, 'Updated LTI 1.3')
        self.assertEqual(configuration.updated_at, updated_at)
        for field, value in identity.items():
            self.assertEqual(getattr(configuration, field), value)
        self.assertEqual([
            field for field, value in passport_state.items() if getattr(passport, field) != value
        ], [])
        self.assertEqual(configuration.lti_1p3_client_id, passport.lti_1p3_client_id)

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

    def test_course_filter_narrows_visibility_and_does_not_widen_user_access(self):
        second_course = CourseKey.from_string('course-v1:Second+Course+Run')
        self.course_access.return_value = [self.course_key, second_course]
        self.create('Selected', course_keys=[str(self.course_key)])
        self.create('Other course', course_keys=[str(second_course)])
        self.create('Organization', organization_keys=['org'])
        self.create('Site', site_wide=True)

        response = self.client.get(self.url, {'course_key': str(self.course_key)})
        inaccessible = self.client.get(self.url, {'course_key': str(self.other_key)})

        self.assertEqual([row['name'] for row in response.data['results']], ['Organization', 'Selected', 'Site'])
        self.assertEqual(inaccessible.data['count'], 0)
        self.assertEqual(inaccessible.data['results'], [])

    def test_scope_filter_matches_grant_type_without_widening_visibility(self):
        self.create('Course', course_keys=[str(self.course_key)])
        self.create('Organization', organization_keys=['org'])
        self.create('Site', site_wide=True)
        self.create('Mixed', course_keys=[str(self.course_key)], organization_keys=['org'])

        organization = self.client.get(self.url, {'scope': 'organization'})
        site_wide = self.client.get(self.url, {'scope': 'site_wide'})
        invalid = self.client.get(self.url, {'scope': 'unknown'})

        self.assertEqual([row['name'] for row in organization.data['results']], ['Mixed', 'Organization'])
        self.assertEqual([row['name'] for row in site_wide.data['results']], ['Site'])
        self.assertEqual(invalid.status_code, 400)

    def test_superuser_course_filter_does_not_enumerate_courses(self):
        self.user.is_superuser = True
        self.user.save()
        self.create('Selected', course_keys=[str(self.course_key)])
        self.create('Other', course_keys=[str(self.other_key)])

        response = self.client.get(self.url, {'course_key': str(self.other_key)})

        self.assertEqual([row['name'] for row in response.data['results']], ['Other'])
        self.course_access.assert_not_called()

    def test_invalid_course_filter_is_rejected(self):
        response = self.client.get(self.url, {'course_key': 'not-a-course'})
        self.assertEqual(response.status_code, 400)
        self.course_access.assert_not_called()

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
