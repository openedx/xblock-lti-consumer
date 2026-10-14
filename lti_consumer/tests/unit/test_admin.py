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

from lti_consumer.admin import (
    Lti1p3PassportAdmin,
    ReusableLtiConfigurationAdmin,
    ReusableLtiConfigurationCourseInline,
    ReusableLtiConfigurationOrganizationInline,
)
from lti_consumer.models import (
    Lti1p3Passport,
    ReusableLtiConfiguration,
    ReusableLtiConfigurationCourse,
    ReusableLtiConfigurationOrganization,
)
from lti_consumer.reusable import create_reusable_configuration


urlpatterns = [path('admin/', admin.site.urls)]


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
    'site_wide',
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


class ReusableLtiConfigurationAdminTests(TestCase):
    """Read-only reusable configuration admin: visibility, scope, and write protection."""

    course_key = 'course-v1:VisibleOrg+VisibleCourse+Run'
    organization = 'visible-org-grant'

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='reusable-admin-test', email='reusable-admin-test@example.com', password=None,
        )
        self.client.force_login(self.user)
        self.request = RequestFactory().get('/admin/')
        self.request.user = self.user
        self.model_admin = admin.site.get_model_admin(ReusableLtiConfiguration)
        self.changelist_url = reverse('admin:lti_consumer_reusablelticonfiguration_changelist')

        self.lti11_config = create_reusable_configuration({
            'name': 'Legacy launch tool',
            'description': 'LTI 1.1 metadata',
            'version': ReusableLtiConfiguration.LTI_1P1,
            'scope': {'course_keys': [self.course_key]},
            'lti_1p1': {'launch_url': 'https://one-one.example/launch'},
        }).configuration
        self.lti13_config = create_reusable_configuration({
            'name': 'Advantage tool',
            'version': ReusableLtiConfiguration.LTI_1P3,
            'scope': {'organization_keys': [self.organization], 'site_wide': True},
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

    def test_registered_parent_admin_and_no_grant_admin_registration(self):
        self.assertTrue(admin.site.is_registered(ReusableLtiConfiguration))
        self.assertIsInstance(self.model_admin, ReusableLtiConfigurationAdmin)
        self.assertFalse(admin.site.is_registered(ReusableLtiConfigurationCourse))
        self.assertFalse(admin.site.is_registered(ReusableLtiConfigurationOrganization))

    def test_list_display_search_and_filters(self):
        self.assertEqual(
            list(self.model_admin.get_list_display(self.request)),
            ['name', 'version', 'config_id', 'site_wide', 'updated_at'],
        )
        self.assertEqual(set(self.model_admin.get_search_fields(self.request)), {'name', 'config_id'})
        filters = self.model_admin.get_list_filter(self.request)
        self.assertIn('version', filters)
        self.assertIn('site_wide', filters)

    def test_superuser_can_view_but_mutations_and_actions_are_denied(self):
        self.assertTrue(self.model_admin.has_module_permission(self.request))
        self.assertTrue(self.model_admin.has_view_permission(self.request))
        self.assertTrue(self.model_admin.has_view_permission(self.request, self.lti11_config))
        self.assertFalse(self.model_admin.has_add_permission(self.request))
        for obj in (None, self.lti11_config, self.lti13_config):
            with self.subTest(obj=obj):
                self.assertFalse(self.model_admin.has_change_permission(self.request, obj))
                self.assertFalse(self.model_admin.has_delete_permission(self.request, obj))
        self.assertEqual(self.model_admin.get_actions(self.request), {})

    def test_staff_with_every_model_permission_is_denied(self):
        staff_user = get_user_model().objects.create_user(
            username='reusable-staff-test', password='password', is_staff=True,
        )
        staff_user.user_permissions.set(Permission.objects.all())
        staff_user = get_user_model().objects.get(pk=staff_user.pk)
        self.assertTrue(staff_user.has_perm('lti_consumer.view_reusablelticonfiguration'))
        self.assertTrue(staff_user.has_perm('lti_consumer.change_reusablelticonfiguration'))

        self.request.user = staff_user
        self.assertFalse(self.model_admin.has_module_permission(self.request))
        self.assertFalse(self.model_admin.has_view_permission(self.request))
        self.assertFalse(self.model_admin.has_view_permission(self.request, self.lti11_config))

        self.client.force_login(staff_user)
        self.assertEqual(self.client.get(self.changelist_url).status_code, 403)
        self.assertEqual(self.client.get(self.change_url(self.lti11_config)).status_code, 403)

    def test_changelist_lists_both_versions_and_searches_by_name_and_uuid(self):
        response = self.client.get(self.changelist_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.lti11_config.name)
        self.assertContains(response, self.lti13_config.name)
        self.assertContains(response, str(self.lti11_config.config_id))
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

    def test_changelist_filters_by_version_and_site_wide(self):
        response = self.client.get(self.changelist_url, {'version': ReusableLtiConfiguration.LTI_1P3})
        self.assertContains(response, self.lti13_config.name)
        self.assertNotContains(response, self.lti11_config.name)

        response = self.client.get(self.changelist_url, {'site_wide__exact': '1'})
        self.assertContains(response, self.lti13_config.name)
        self.assertNotContains(response, self.lti11_config.name)

        response = self.client.get(self.changelist_url, {'site_wide__exact': '0'})
        self.assertContains(response, self.lti11_config.name)
        self.assertNotContains(response, self.lti13_config.name)

    def test_fieldsets_cover_both_versions_are_readonly_and_exclude_secrets(self):
        editable_fields = {
            field.name for field in ReusableLtiConfiguration._meta.get_fields()
            if field.concrete and field.editable
        }
        for configuration in (self.lti11_config, self.lti13_config):
            with self.subTest(configuration=configuration.name):
                field_names = self.fieldset_fields(configuration)
                self.assertLessEqual(DETAIL_FIELDS, set(field_names))
                self.assertFalse(UNSAFE_FIELDS & set(field_names))
                readonly_fields = set(self.model_admin.get_readonly_fields(self.request, configuration))
                self.assertLessEqual(set(field_names) & editable_fields, readonly_fields)

    def test_detail_pages_render_scope_without_credentials_or_key_material(self):
        response = self.client.get(self.change_url(self.lti11_config))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.lti11_config.lti_1p1_launch_url)
        self.assertContains(response, self.course_key)
        self.assertNotContains(response, self.lti11_config.lti_1p1_client_key)
        self.assertNotContains(response, self.lti11_config.lti_1p1_client_secret)

        response = self.client.get(self.change_url(self.lti13_config))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.lti13_config.lti_1p3_oidc_url)
        self.assertContains(response, self.organization)
        self.assertNotContains(response, self.lti13_config.lti_1p3_passport.lti_1p3_internal_private_key)
        self.assertNotContains(response, str(self.lti13_config.lti_1p3_passport.passport_id))

    def test_scope_inlines_show_single_scoped_field_and_deny_writes(self):
        expected = (
            (ReusableLtiConfigurationCourseInline, ReusableLtiConfigurationCourse, 'course_key'),
            (ReusableLtiConfigurationOrganizationInline, ReusableLtiConfigurationOrganization, 'organization'),
        )
        for inline_class, model, scoped_field in expected:
            with self.subTest(inline=inline_class.__name__):
                self.assertIn(inline_class, self.model_admin.inlines)
                inline = inline_class(ReusableLtiConfiguration, self.model_admin.admin_site)
                self.assertEqual(inline.model, model)
                self.assertEqual(inline.extra, 0)
                self.assertEqual(list(inline.get_fields(self.request, self.lti11_config)), [scoped_field])
                self.assertTrue(inline.has_view_permission(self.request, self.lti11_config))
                self.assertFalse(inline.has_add_permission(self.request, self.lti11_config))
                self.assertFalse(inline.has_change_permission(self.request, self.lti11_config))
                self.assertFalse(inline.has_delete_permission(self.request, self.lti11_config))

    def test_mutating_requests_cannot_change_parent_grants_or_passport(self):
        configuration = self.lti11_config
        course_grant = ReusableLtiConfigurationCourse.objects.get(configuration=configuration)
        passport = self.lti13_config.lti_1p3_passport
        private_key_before = passport.lti_1p3_internal_private_key

        add_url = reverse('admin:lti_consumer_reusablelticonfiguration_add')
        change_url = self.change_url(configuration)
        delete_url = reverse('admin:lti_consumer_reusablelticonfiguration_delete', args=[configuration.pk])

        self.assertEqual(self.client.get(add_url).status_code, 403)
        self.assertEqual(
            self.client.post(add_url, {'name': 'Created in admin', 'version': 'lti_1p1'}).status_code,
            403,
        )
        self.assertEqual(self.client.post(change_url, {'name': 'Renamed in admin'}).status_code, 403)
        self.assertEqual(
            self.client.post(change_url, {
                'name': 'Renamed in admin',
                'course_grants-TOTAL_FORMS': '1',
                'course_grants-INITIAL_FORMS': '1',
                'course_grants-MIN_NUM_FORMS': '0',
                'course_grants-MAX_NUM_FORMS': '1000',
                'course_grants-0-id': str(course_grant.pk),
                'course_grants-0-course_key': 'course-v1:Evil+Course+Run',
            }).status_code,
            403,
        )
        self.assertEqual(self.client.post(delete_url, {'post': 'yes'}).status_code, 403)
        response = self.client.post(self.changelist_url, {
            'action': 'delete_selected',
            'index': '0',
            '_selected_action': [str(configuration.pk)],
        })
        self.assertIn(response.status_code, (200, 400, 403))

        passport_url = reverse('admin:lti_consumer_lti1p3passport_change', args=[passport.pk])
        passport_response = self.client.post(passport_url, {'name': 'Renamed passport'})
        self.assertIn(passport_response.status_code, (302, 403, 404))

        configuration.refresh_from_db()
        passport.refresh_from_db()
        self.assertEqual(configuration.name, 'Legacy launch tool')
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 2)
        self.assertEqual(
            [str(key) for key in ReusableLtiConfigurationCourse.objects.filter(
                configuration=configuration).values_list('course_key', flat=True)],
            [self.course_key],
        )
        self.assertEqual(
            list(ReusableLtiConfigurationOrganization.objects.filter(
                configuration=self.lti13_config).values_list('organization', flat=True)),
            [self.organization],
        )
        self.assertEqual(passport.name, self.lti13_config.name)
        self.assertEqual(passport.lti_1p3_client_id, self.lti13_config.lti_1p3_client_id)
        self.assertEqual(passport.lti_1p3_internal_private_key, private_key_before)
