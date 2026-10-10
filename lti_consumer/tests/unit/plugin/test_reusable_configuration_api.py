"""API tests for CMS reusable-configuration creation."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from lti_consumer.models import ReusableLtiConfiguration


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
