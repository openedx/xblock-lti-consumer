"""
Tests for the LTI Consumer Django admin views.
"""
from unittest.mock import patch

from django.contrib import admin
from django.contrib.admin.utils import flatten_fieldsets
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase
from django.urls import reverse

from lti_consumer.models import LtiConfiguration, ReusableLtiConfiguration
from lti_consumer.reusable import create_reusable_configuration

GLOBAL_STAFF_PATCH = 'lti_consumer.plugin.compat.user_is_global_staff'


class GlobalStaffPatchMixin:
    """Patch the platform role seam for admin requests; compat tests cover the real helper."""

    def setUp(self):
        super().setUp()
        patcher = patch(
            GLOBAL_STAFF_PATCH,
            side_effect=lambda user: bool(user and (user.is_superuser or user.is_staff)),
        )
        patcher.start()
        self.addCleanup(patcher.stop)


UNSAFE_FIELDS = {
    'lti_1p1_client_key',
    'lti_1p1_client_secret',
    'normalized_name',
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


class ReusableLtiConfigurationAdminTests(GlobalStaffPatchMixin, TestCase):
    """Read-only reusable configuration admin: Global Staff/superuser inspection, writes denied."""

    course_key = 'course-v1:VisibleOrg+VisibleCourse+Run'

    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_superuser(
            username='reusable-admin-test', email='reusable-admin-test@example.com', password=None,
        )
        self.staff = get_user_model().objects.create_user(
            username='reusable-staff-test', password='password', is_staff=True,
        )
        self.client.force_login(self.user)
        self.request = RequestFactory().get('/admin/')
        self.request.user = self.user
        self.model_admin = admin.site.get_model_admin(ReusableLtiConfiguration)
        self.changelist_url = reverse('admin:lti_consumer_reusablelticonfiguration_changelist')

        self.lti11_config = create_reusable_configuration(self.user, {
            'name': 'Legacy launch tool',
            'description': 'LTI 1.1 metadata',
            'version': ReusableLtiConfiguration.LTI_1P1,
            'context': {'type': 'course', 'key': self.course_key},
            'lti_1p1': {'launch_url': 'https://one-one.example/launch'},
        }).configuration
        self.lti13_config = create_reusable_configuration(self.user, {
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
        self.lti13_client_id = self.lti13_config.lti_1p3_client_id
        self.lti13_private_key = self.lti13_config.lti_1p3_internal_private_key

    def change_url(self, configuration):
        return reverse('admin:lti_consumer_reusablelticonfiguration_change', args=[configuration.pk])

    def fieldset_fields(self, configuration):
        return flatten_fieldsets(self.model_admin.get_fieldsets(self.request, configuration))

    def test_global_staff_and_superuser_inspect_both_versions_with_search_filters_and_safe_readonly_fieldsets(self):
        for actor in (self.user, self.staff):
            self.client.force_login(actor)
            with self.subTest(actor=actor.username):
                self._assert_inspection()

    def _assert_inspection(self):
        """Assert both versions render read-only safe fields for the logged-in actor."""
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
                    str(self.lti13_config.passport_id),
                ),
                (
                    self.lti13_config.lti_1p3_internal_private_key,
                    self.lti13_config.lti_1p3_tool_keyset_url,
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

    def test_bound_placement_inline_is_read_only_visible_to_global_staff_only(self):
        """The placement inline follows the parent's role gate, not Django model permissions."""
        placement = LtiConfiguration.objects.create(
            location='block-v1:VisibleOrg+VisibleCourse+Run+type@lti_consumer+block@bound',
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_ON_DB,
            lti_1p3_passport=self.lti13_config,
        )
        # self.staff clears only the staff-login gate: no LTI model permissions at all.
        for perm in (
            'lti_consumer.view_reusablelticonfiguration',
            'lti_consumer.view_lticonfiguration',
            'lti_consumer.change_lticonfiguration',
        ):
            self.assertFalse(self.staff.has_perm(perm), perm)

        self.client.force_login(self.staff)
        response = self.client.get(self.change_url(self.lti13_config))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(placement.location))
        # Read-only: the bound placement has no editable control and no delete box.
        inline_prefix = LtiConfiguration._meta.get_field('lti_1p3_passport').remote_field.get_accessor_name()
        self.assertNotContains(response, f'name="{inline_prefix}-0-location"')
        self.assertNotContains(response, f'name="{inline_prefix}-0-DELETE"')
        # The inline shows the binding only; credentials stay hidden.
        self.assertNotContains(response, self.lti13_config.lti_1p3_internal_private_key)
        self.assertNotContains(response, self.lti13_config.lti_1p3_tool_keyset_url)

        # An ordinary actor is still denied the parent page, so the placement is not disclosed.
        with patch(GLOBAL_STAFF_PATCH, return_value=False):
            self.assertEqual(self.client.get(self.change_url(self.lti13_config)).status_code, 403)

    def test_reusable_configurations_deny_every_write_and_keep_identity_intact(self):
        # This user clears every Django gate (staff login, all model permissions), so the
        # false seam below proves the admin asks the role seam, not is_staff or permissions.
        non_global_staff = get_user_model().objects.create_user(
            username='reusable-non-global-staff-test', password='password', is_staff=True,
        )
        non_global_staff.user_permissions.set(Permission.objects.all())
        non_global_staff = get_user_model().objects.get(pk=non_global_staff.pk)
        self.assertTrue(non_global_staff.has_perm('lti_consumer.view_reusablelticonfiguration'))
        self.client.force_login(non_global_staff)
        # Override the suite's role seam: admin login succeeds, the Global Staff role does not.
        with patch(GLOBAL_STAFF_PATCH, return_value=False):
            self.assertEqual(self.client.get(self.changelist_url).status_code, 403)
            self.assertEqual(self.client.get(self.change_url(self.lti11_config)).status_code, 403)

        # Global Staff may write nothing; inspection is covered by the test above.
        staff_user = self.staff
        add_url = reverse('admin:lti_consumer_reusablelticonfiguration_add')
        change_url = self.change_url(self.lti11_config)
        delete_url = reverse('admin:lti_consumer_reusablelticonfiguration_delete', args=[self.lti11_config.pk])
        # Neither Global Staff nor the superuser may add, change or delete.
        for actor in (staff_user, self.user):
            self.client.force_login(actor)
            with self.subTest(actor=actor.username):
                self.assertEqual(self.client.get(add_url).status_code, 403)
                self.assertEqual(self.client.post(add_url, {
                    'name': f'{actor.username} add', 'version': 'lti_1p1',
                }).status_code, 403)
                self.assertEqual(self.client.post(change_url, {
                    'name': f'{actor.username} rename',
                }).status_code, 403)
                self.assertEqual(self.client.post(delete_url, {'post': 'yes'}).status_code, 403)

        # Even the superuser cannot bulk-delete.
        self.client.force_login(self.user)
        self.client.post(self.changelist_url, {
            'action': 'delete_selected',
            'index': '0',
            '_selected_action': [str(self.lti11_config.pk)],
        })
        self.assertTrue(ReusableLtiConfiguration.objects.filter(pk=self.lti11_config.pk).exists())

        # Denied writes leave the merged row's identity and credentials untouched.
        self.lti11_config.refresh_from_db()
        self.lti13_config.refresh_from_db()
        self.assertEqual(self.lti11_config.name, 'Legacy launch tool')
        self.assertEqual(
            (self.lti11_config.context_type, self.lti11_config.context_key),
            ('course', self.course_key),
        )
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 2)
        self.assertEqual(self.lti13_config.name, 'Advantage tool')
        self.assertEqual(self.lti13_config.lti_1p3_client_id, self.lti13_client_id)
        self.assertEqual(self.lti13_config.lti_1p3_internal_private_key, self.lti13_private_key)
