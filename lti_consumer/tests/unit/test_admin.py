"""
Tests for the LTI Consumer Django admin views.
"""
from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.admin.utils import flatten_fieldsets
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase, override_settings
from django.urls import path, reverse

from lti_consumer.admin import Lti1p3PassportAdmin
from lti_consumer.models import Lti1p3Passport, ReusableLtiConfiguration
from lti_consumer.reusable import create_reusable_configuration

urlpatterns = [path('admin/', admin.site.urls)]

UNSAFE_FIELDS = {
    'lti_1p1_client_key',
    'lti_1p1_client_secret',
    'normalized_name',
    'lti_1p3_passport',
    'lti_1p3_tool_public_key',
    'lti_1p3_tool_keyset_url',
    'lti_1p3_internal_private_key',
    'lti_1p3_internal_private_key_id',
    'lti_1p3_internal_public_jwk',
}

DETAIL_FIELDS = {
    'name',
    'description',
    'version',
    'context_type',
    'context_key',
    'lti_1p1_launch_url',
    'lti_1p3_launch_url',
    'lti_1p3_oidc_url',
    'lti_advantage_deep_linking_enabled',
    'lti_advantage_deep_linking_launch_url',
    'lti_advantage_ags_mode',
    'lti_advantage_enable_nrps',
    'display_name',
    'enable_grading',
    'grade_weight',
    'accept_grades_after_due_date',
    'open_tool_in',
    'inline_height',
    'modal_height',
    'modal_width',
    'launch_button_text',
    'send_extra_parameters',
    'custom_parameters',
}


@override_settings(ROOT_URLCONF=__name__)
class Lti1p3PassportAdminTests(TestCase):
    """Legacy passport admin visibility and reusable passport isolation."""

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='admin-test', email='admin-test@example.com', password=None,
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
            context_type='course',
            context_key='course-v1:Org+Course+Run',
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


class ReusableLtiConfigurationAdminTests(TestCase):
    """Read-only reusable configuration admin: superuser inspection, every write denied."""

    course_key = 'course-v1:VisibleOrg+VisibleCourse+Run'

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='reusable-admin-test', email='reusable-admin-test@example.com', password=None,
        )
        self.client.force_login(self.user)
        self.request = RequestFactory().get('/admin/')
        self.request.user = self.user
        self.model_admin = admin.site.get_model_admin(ReusableLtiConfiguration)
        self.changelist_url = reverse('admin:lti_consumer_reusablelticonfiguration_changelist')
        self.legacy_passport = Lti1p3Passport.objects.create(lti_1p3_client_id='legacy-client')

        self.lti11_config = create_reusable_configuration({
            'name': 'Legacy launch tool',
            'description': 'LTI 1.1 metadata',
            'version': ReusableLtiConfiguration.LTI_1P1,
            'context': {'type': 'course', 'key': self.course_key},
            'lti_1p1': {'launch_url': 'https://one-one.example/launch'},
        }).configuration
        self.lti13_config = create_reusable_configuration({
            'name': 'Advantage tool',
            'version': ReusableLtiConfiguration.LTI_1P3,
            'context': {'type': 'site'},
            'lti_1p3': {
                'launch_url': 'https://one-three.example/launch',
                'oidc_url': 'https://one-three.example/oidc',
                'tool_key_mode': 'keyset_url',
                'tool_keyset_url': 'https://one-three.example/jwks',
            },
        }).configuration

    def change_url(self, configuration):
        return reverse('admin:lti_consumer_reusablelticonfiguration_change', args=[configuration.pk])

    def fieldset_fields(self, configuration):
        return flatten_fieldsets(self.model_admin.get_fieldsets(self.request, configuration))

    def test_superuser_inspects_both_versions_with_search_filters_and_safe_readonly_fieldsets(self):
        response = self.client.get(self.changelist_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.lti11_config.name)
        self.assertContains(response, self.lti13_config.name)
        self.assertContains(response, str(self.lti11_config.config_id))
        self.assertContains(response, str(self.lti13_config.config_id))
        self.assertNotContains(response, self.lti11_config.lti_1p1_client_key)
        self.assertNotContains(response, self.lti11_config.lti_1p1_client_secret)

        response = self.client.get(self.changelist_url, {'q': 'Advantage'})
        self.assertContains(response, self.lti13_config.name)
        self.assertNotContains(response, self.lti11_config.name)

        for config_id in (str(self.lti11_config.config_id), self.lti11_config.config_id.hex):
            with self.subTest(config_id=config_id):
                response = self.client.get(self.changelist_url, {'q': config_id})
                self.assertContains(response, self.lti11_config.name)
                self.assertNotContains(response, self.lti13_config.name)

        # Pass both plain and __exact params: Django 6.0 ChoicesFieldListFilter uses field__exact.
        response = self.client.get(self.changelist_url, {
            'version': ReusableLtiConfiguration.LTI_1P3,
            'version__exact': ReusableLtiConfiguration.LTI_1P3,
        })
        self.assertContains(response, self.lti13_config.name)
        self.assertNotContains(response, self.lti11_config.name)

        response = self.client.get(self.changelist_url, {
            'context_type': 'course',
            'context_type__exact': 'course',
        })
        self.assertContains(response, self.lti11_config.name)
        self.assertNotContains(response, self.lti13_config.name)

        editable_fields = {
            field.name for field in ReusableLtiConfiguration._meta.get_fields()
            if field.concrete and field.editable
        }
        for configuration, visible_values, hidden_values in (
            (
                self.lti11_config,
                (self.lti11_config.name, self.lti11_config.lti_1p1_launch_url, self.course_key),
                (
                    self.lti11_config.lti_1p1_client_key,
                    self.lti11_config.lti_1p1_client_secret,
                    self.lti11_config.normalized_name,
                ),
            ),
            (
                self.lti13_config,
                (
                    self.lti13_config.name,
                    self.lti13_config.lti_1p3_launch_url,
                    self.lti13_config.lti_1p3_oidc_url,
                ),
                (
                    self.lti13_config.lti_1p3_passport.lti_1p3_internal_private_key,
                    str(self.lti13_config.lti_1p3_passport.passport_id),
                    self.lti13_config.lti_1p3_passport.lti_1p3_tool_keyset_url,
                    self.lti13_config.normalized_name,
                ),
            ),
        ):
            with self.subTest(configuration=configuration.name):
                # Structural allowlist: intended safe fields are present, every exposed
                # editable model field is readonly, and unsafe fields are never exposed,
                # independent of the rendered fixture values.
                field_names = self.fieldset_fields(configuration)
                self.assertLessEqual(DETAIL_FIELDS, set(field_names))
                self.assertFalse(UNSAFE_FIELDS & set(field_names))
                readonly_fields = set(self.model_admin.get_readonly_fields(self.request, configuration))
                self.assertLessEqual(set(field_names) & editable_fields, readonly_fields)
                for context_field in ('context_type', 'context_key'):
                    self.assertIn(context_field, field_names)
                    self.assertIn(context_field, readonly_fields)

                response = self.client.get(self.change_url(configuration))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, str(configuration.config_id))
                self.assertContains(response, 'class="readonly"')
                for value in visible_values:
                    self.assertContains(response, value)
                for value in hidden_values:
                    self.assertNotContains(response, value)
                html = response.content.decode()
                for control in ('name="_save"', 'name="_continue"', 'name="_addanother"',
                                'name="_saveasnew"', 'deletelink'):
                    self.assertNotIn(control, html)

    def test_reusable_configurations_deny_every_write_and_keep_passports_isolated(self):
        # A staff user holding every model permission still gets no access at all.
        staff_user = get_user_model().objects.create_user(
            username='reusable-staff-test', password='password', is_staff=True,
        )
        staff_user.user_permissions.set(Permission.objects.all())
        staff_user = get_user_model().objects.get(pk=staff_user.pk)
        self.assertTrue(staff_user.has_perm('lti_consumer.view_reusablelticonfiguration'))
        self.client.force_login(staff_user)
        self.assertEqual(self.client.get(self.changelist_url).status_code, 403)
        self.assertEqual(self.client.get(self.change_url(self.lti11_config)).status_code, 403)

        # Even the superuser cannot add, change, delete, or bulk-delete configurations.
        self.client.force_login(self.user)
        add_url = reverse('admin:lti_consumer_reusablelticonfiguration_add')
        change_url = self.change_url(self.lti11_config)
        delete_url = reverse('admin:lti_consumer_reusablelticonfiguration_delete', args=[self.lti11_config.pk])

        self.assertEqual(self.client.get(add_url).status_code, 403)
        self.assertEqual(self.client.post(add_url, {
            'name': 'Created in admin', 'version': 'lti_1p1',
        }).status_code, 403)
        self.assertEqual(self.client.post(change_url, {
            'name': 'Renamed in admin', 'context_type': 'organization', 'context_key': 'evil-org',
        }).status_code, 403)
        self.assertEqual(self.client.post(delete_url, {'post': 'yes'}).status_code, 403)
        self.client.post(self.changelist_url, {
            'action': 'delete_selected',
            'index': '0',
            '_selected_action': [str(self.lti11_config.pk)],
        })
        self.assertTrue(ReusableLtiConfiguration.objects.filter(pk=self.lti11_config.pk).exists())

        # The Passport admin lists the legacy passport only and rejects writes to the reusable one.
        reusable_passport = self.lti13_config.lti_1p3_passport
        private_key_before = reusable_passport.lti_1p3_internal_private_key
        passport_list = self.client.get(reverse('admin:lti_consumer_lti1p3passport_changelist'))
        self.assertContains(passport_list, self.legacy_passport.lti_1p3_client_id)
        self.assertNotContains(passport_list, reusable_passport.lti_1p3_client_id)
        self.assertNotContains(passport_list, private_key_before)
        passport_write = self.client.post(
            reverse('admin:lti_consumer_lti1p3passport_change', args=[reusable_passport.pk]),
            {'name': 'Renamed passport'},
        )
        self.assertIn(passport_write.status_code, (302, 403, 404))

        self.lti11_config.refresh_from_db()
        reusable_passport.refresh_from_db()
        self.assertEqual(self.lti11_config.name, 'Legacy launch tool')
        self.assertEqual(
            (self.lti11_config.context_type, self.lti11_config.context_key),
            ('course', self.course_key),
        )
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 2)
        self.assertEqual(reusable_passport.name, self.lti13_config.name)
        self.assertEqual(reusable_passport.lti_1p3_client_id, self.lti13_config.lti_1p3_client_id)
        self.assertEqual(reusable_passport.lti_1p3_internal_private_key, private_key_before)
