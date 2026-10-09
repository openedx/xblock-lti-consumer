from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from lti_consumer.admin import Lti1p3PassportAdmin
from lti_consumer.models import Lti1p3Passport, ReusableLtiConfiguration


class Lti1p3PassportAdminTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get('/admin/')
        self.request.user = AnonymousUser()
        self.model_admin = Lti1p3PassportAdmin(Lti1p3Passport, AdminSite())
        self.legacy_passport = Lti1p3Passport.objects.create(lti_1p3_client_id='legacy-client')
        self.reusable_passport = Lti1p3Passport.objects.create(lti_1p3_client_id='reusable-client')
        ReusableLtiConfiguration.objects.create(
            name='Reusable configuration',
            version=ReusableLtiConfiguration.LTI_1P3,
            lti_1p3_client_id='reusable-client',
            lti_1p3_passport=self.reusable_passport,
        )

    def test_queryset_hides_reusable_owned_passports_only(self):
        passports = self.model_admin.get_queryset(self.request)
        self.assertQuerySetEqual(passports, [self.legacy_passport], transform=lambda passport: passport)

    def test_object_permissions_deny_reusable_passport_access(self):
        self.assertFalse(self.model_admin.has_view_permission(self.request, self.reusable_passport))
        self.assertFalse(self.model_admin.has_change_permission(self.request, self.reusable_passport))
        self.assertFalse(self.model_admin.has_delete_permission(self.request, self.reusable_passport))
