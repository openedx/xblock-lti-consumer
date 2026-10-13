from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import path, reverse

from lti_consumer.admin import Lti1p3PassportAdmin
from lti_consumer.models import Lti1p3Passport, ReusableLtiConfiguration


urlpatterns = [path('admin/', admin.site.urls)]


@override_settings(ROOT_URLCONF=__name__)
class Lti1p3PassportAdminTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='admin-test', email='admin-test@example.com', password='password',
        )
        self.request = RequestFactory().get('/admin/')
        self.request.user = self.user
        self.client.force_login(self.user)
        self.model_admin = Lti1p3PassportAdmin(Lti1p3Passport, AdminSite())
        self.legacy_passport = Lti1p3Passport.objects.create(lti_1p3_client_id='legacy-client')
        self.reusable_passport = Lti1p3Passport.objects.create(
            lti_1p3_client_id='reusable-client',
            lti_1p3_internal_private_key='reusable-private-key-must-not-appear',
        )
        ReusableLtiConfiguration.objects.create(
            name='Reusable configuration',
            version=ReusableLtiConfiguration.LTI_1P3,
            lti_1p3_client_id='reusable-client',
            lti_1p3_passport=self.reusable_passport,
        )

    def test_queryset_hides_reusable_owned_passports_only(self):
        passports = self.model_admin.get_queryset(self.request)
        self.assertQuerySetEqual(passports, [self.legacy_passport], transform=lambda passport: passport)

    def test_object_permissions_preserve_legacy_and_deny_reusable_passports(self):
        self.assertTrue(self.model_admin.has_view_permission(self.request, self.legacy_passport))
        self.assertTrue(self.model_admin.has_change_permission(self.request, self.legacy_passport))
        self.assertTrue(self.model_admin.has_delete_permission(self.request, self.legacy_passport))
        self.assertFalse(self.model_admin.has_view_permission(self.request, self.reusable_passport))
        self.assertFalse(self.model_admin.has_change_permission(self.request, self.reusable_passport))
        self.assertFalse(self.model_admin.has_delete_permission(self.request, self.reusable_passport))

    def test_guessed_admin_urls_do_not_expose_reusable_passport(self):
        for action in ('change', 'history', 'delete'):
            url = reverse(
                f'admin:lti_consumer_lti1p3passport_{action}',
                args=(self.reusable_passport.pk,),
            )
            with self.subTest(action=action):
                response = self.client.get(url)
                self.assertIn(response.status_code, (302, 403, 404))
                self.assertNotIn('reusable-private-key-must-not-appear', response.content.decode())
                self.assertTrue(Lti1p3Passport.objects.filter(pk=self.reusable_passport.pk).exists())

        legacy_change_url = reverse(
            'admin:lti_consumer_lti1p3passport_change',
            args=(self.legacy_passport.pk,),
        )
        self.assertEqual(self.client.get(legacy_change_url).status_code, 200)
