"""
Behavioural tests for the reusable-configuration Django admin.

Journeys drive the real admin site, URLconf, ModelAdmin and ORM. Only the
edx-platform Global Staff seam is patched, since edx-platform is not installed.
"""
from unittest.mock import patch

from django.contrib import admin
from django.contrib.admin.utils import flatten_fieldsets
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from lti_consumer.models import Lti1p3Passport, LtiConfiguration, ReusableLtiConfiguration

COURSE_KEY = 'course-v1:Org+Course+Run'
GLOBAL_STAFF_PATCH = 'lti_consumer.plugin.compat.user_is_global_staff'
PRIVATE_KEY = '-----BEGIN RSA PRIVATE KEY----- never-render-this-value'

DETAIL_FIELDS = {
    'name', 'passport_id', 'version', 'description', 'is_active', 'created_at', 'updated_at',
    'context_type', 'context_key',
    'lti_1p1_launch_url', 'lti_1p1_client_key', 'lti_1p1_client_secret',
    'lti_1p3_launch_url', 'lti_1p3_oidc_url', 'lti_1p3_redirect_uris', 'lti_1p3_client_id',
    'lti_1p3_deployment_id', 'lti_1p3_tool_key_mode', 'lti_1p3_tool_public_key',
    'lti_1p3_tool_keyset_url', 'lti_1p3_internal_private_key_id', 'lti_1p3_internal_public_jwk',
    'lti_advantage_deep_linking_enabled', 'lti_advantage_deep_linking_launch_url',
    'lti_advantage_ags_mode', 'lti_advantage_enable_nrps',
    'display_name', 'enable_grading', 'grade_weight', 'accept_grades_after_due_date',
    'open_tool_in', 'inline_height', 'modal_height', 'modal_width', 'launch_button_text',
    'send_extra_parameters', 'custom_parameters',
    'pii_share_username', 'pii_share_full_name', 'pii_share_email', 'data_sharing_notice',
    'require_user_confirmation', 'hide_external_tool',
}


class AdminTestBase(TestCase):
    """Patch only the platform role seam and provide the admin URLs."""

    def setUp(self):
        super().setUp()
        patcher = patch(
            GLOBAL_STAFF_PATCH,
            side_effect=lambda user: bool(getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False)),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.user_model = get_user_model()
        self.changelist_url = reverse('admin:lti_consumer_reusablelticonfiguration_changelist')

    def make_user(self, username, **kwargs):
        """Create a user with a usable password."""
        values = {'username': username, 'password': 'password'}
        values.update(kwargs)
        return self.user_model.objects.create_user(**values)

    def make_configuration(self, **kwargs):
        """Create a reusable configuration row directly, bypassing the service."""
        values = {
            'name': 'Advantage tool',
            'version': ReusableLtiConfiguration.LTI_1P3,
            'context_type': 'course',
            'context_key': COURSE_KEY,
        }
        values.update(kwargs)
        return ReusableLtiConfiguration.objects.create(**values)

    def change_url(self, configuration):
        """Return the admin change URL for one configuration."""
        return reverse('admin:lti_consumer_reusablelticonfiguration_change', args=[configuration.pk])

    def detail_fields(self, configuration):
        """Return the flattened detail fieldsets of the new admin."""
        model_admin = admin.site.get_model_admin(ReusableLtiConfiguration)
        return flatten_fieldsets(model_admin.get_fieldsets(None, configuration))


class ReusableAdminAccessTests(AdminTestBase):
    """The new admin is readable by Global Staff and superusers, and nothing else."""

    def setUp(self):
        super().setUp()
        self.configuration = self.make_configuration(name='Visible configuration')
        self.staff = self.make_user('global-staff', is_staff=True)
        self.staff_with_perms = self.make_user('global-staff-with-perms', is_staff=True)
        self.staff_with_perms.user_permissions.set(Permission.objects.all())
        self.superuser = self.user_model.objects.create_superuser(
            username='superuser', email='superuser@example.com', password=None,
        )
        self.inactive_staff = self.make_user('inactive-staff', is_staff=True, is_active=False)
        self.ordinary = self.make_user('ordinary')

    def test_global_staff_and_superuser_reach_list_detail_and_inline(self):
        placement = LtiConfiguration.objects.create(
            location='block-v1:Org+Course+Run+type@lti_consumer+block@bound',
            reusable_configuration=self.configuration,
            # Bind a passport so the post_save signal does not load the block from the modulestore.
            lti_1p3_passport=Lti1p3Passport.objects.create(name='Bound passport'),
        )
        for actor in (self.staff, self.staff_with_perms, self.superuser):
            self.client.force_login(actor)
            with self.subTest(actor=actor.username):
                # The admin index link pins has_module_permission for every positive actor,
                # including Global Staff with no Django model permissions at all.
                response = self.client.get(reverse('admin:index'))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, self.changelist_url)

                response = self.client.get(self.changelist_url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Visible configuration')
                self.assertContains(response, self.change_url(self.configuration))

                response = self.client.get(self.change_url(self.configuration))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, str(placement.location))

    def test_inactive_staff_ordinary_and_anonymous_are_denied(self):
        for actor in (self.inactive_staff, self.ordinary):
            self.client.force_login(actor)
            with self.subTest(actor=actor.username):
                self._assert_denied(self.client.get(self.changelist_url))
                self._assert_denied(self.client.get(self.change_url(self.configuration)))

        self.client.logout()
        self._assert_denied(self.client.get(self.changelist_url))
        self._assert_denied(self.client.get(self.change_url(self.configuration)))

    def test_platform_role_false_denies_staff_holding_all_model_permissions(self):
        """The role seam is consulted directly: Django model permissions grant no fallback."""
        self.client.force_login(self.staff_with_perms)
        self.assertTrue(self.staff_with_perms.has_perm('lti_consumer.view_reusablelticonfiguration'))
        with patch(GLOBAL_STAFF_PATCH, return_value=False):
            self._assert_denied(self.client.get(self.changelist_url))
            self._assert_denied(self.client.get(self.change_url(self.configuration)))

            response = self.client.get(reverse('admin:index'))
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, self.changelist_url)
            self.assertNotContains(response, 'Visible configuration')

    def _assert_denied(self, response):
        """Assert the response is not the admin page and renders no configuration."""
        self.assertNotEqual(response.status_code, 200)
        self.assertNotContains(response, 'Visible configuration', status_code=response.status_code)


class ReusableAdminRenderingTests(AdminTestBase):
    """Stored values render as stored; only the signing private key value is off the page."""

    def setUp(self):
        super().setUp()
        self.staff = self.make_user('global-staff', is_staff=True)

        self.configuration = self.make_configuration(
            name='Rendered configuration',
            description='Rendered description',
            is_active=False,
            context_type=None,
            context_key='raw-copied-context-key',
            lti_1p1_launch_url='https://one-one.example/launch',
            lti_1p1_client_key='stored-client-key',
            lti_1p1_client_secret='stored-client-secret',
            lti_1p3_launch_url='https://one-three.example/launch',
            lti_1p3_oidc_url='https://one-three.example/oidc',
            lti_1p3_redirect_uris=['https://one-three.example/redirect'],
            lti_1p3_client_id='stored-client-id',
            lti_1p3_deployment_id='stored-deployment-id',
            lti_1p3_tool_key_mode='public_key',
            lti_1p3_tool_public_key='stored-tool-public-key',
            lti_1p3_tool_keyset_url='https://one-three.example/jwks',
            lti_1p3_internal_private_key=PRIVATE_KEY,
            lti_1p3_internal_private_key_id='stored-key-id',
            lti_1p3_internal_public_jwk='{"keys": ["stored-public-jwk"]}',
            lti_advantage_deep_linking_enabled=True,
            lti_advantage_deep_linking_launch_url='https://one-three.example/deep-linking',
            lti_advantage_ags_mode='programmatic',
            lti_advantage_enable_nrps=True,
            display_name='Stored display name',
            enable_grading=True,
            grade_weight=0.5,
            accept_grades_after_due_date=False,
            open_tool_in='modal',
            inline_height=640,
            modal_height=70,
            modal_width=60,
            launch_button_text='Stored button text',
            send_extra_parameters=True,
            custom_parameters=['stored=parameter'],
            pii_share_username=True,
            pii_share_full_name=True,
            pii_share_email=True,
            data_sharing_notice='Stored sharing notice',
            require_user_confirmation=False,
            hide_external_tool=True,
        )
        self.client.force_login(self.staff)

    def test_detail_shows_every_allowlisted_field_and_omits_private_key_value(self):
        self.assertEqual(set(self.detail_fields(self.configuration)), DETAIL_FIELDS)

        response = self.client.get(self.change_url(self.configuration))
        self.assertEqual(response.status_code, 200)
        for value in (
            'Rendered configuration',
            'Rendered description',
            'raw-copied-context-key',
            'https://one-one.example/launch',
            'stored-client-key',
            'stored-client-secret',
            'https://one-three.example/launch',
            'https://one-three.example/oidc',
            'https://one-three.example/redirect',
            'stored-client-id',
            'stored-deployment-id',
            'stored-tool-public-key',
            'https://one-three.example/jwks',
            'stored-key-id',
            'stored-public-jwk',
            'https://one-three.example/deep-linking',
            'Stored display name',
            'Stored button text',
            'stored=parameter',
            'Stored sharing notice',
        ):
            with self.subTest(value=value):
                self.assertContains(response, value)
        self.assertNotContains(response, 'never-render-this-value')

    def test_blank_key_material_is_not_generated_or_saved_on_read(self):
        configuration = self.make_configuration(
            name='Incomplete configuration',
            version=None,
            context_type=None,
            context_key=None,
        )
        self.assertEqual(configuration.lti_1p3_internal_private_key, '')
        self.assertEqual(configuration.lti_1p3_internal_private_key_id, '')
        self.assertEqual(configuration.lti_1p3_internal_public_jwk, '')
        updated_at = configuration.updated_at

        self.assertEqual(self.client.get(self.changelist_url).status_code, 200)
        self.assertEqual(self.client.get(self.change_url(configuration)).status_code, 200)

        configuration.refresh_from_db()
        self.assertEqual(configuration.lti_1p3_internal_private_key, '')
        self.assertEqual(configuration.lti_1p3_internal_private_key_id, '')
        self.assertEqual(configuration.lti_1p3_internal_public_jwk, '')
        self.assertEqual(configuration.updated_at, updated_at)


class ReusableAdminMutationTests(AdminTestBase):
    """No role can mutate through the new admin, forged submissions included."""

    def setUp(self):
        super().setUp()
        self.configuration = self.make_configuration(
            name='Immutable configuration',
            lti_1p1_client_key='immutable-client-key',
            lti_1p1_client_secret='immutable-client-secret',
        )
        self.staff = self.make_user('global-staff', is_staff=True)
        self.superuser = self.user_model.objects.create_superuser(
            username='superuser', email='superuser@example.com', password=None,
        )

    def test_forged_writes_are_refused_or_ignored_without_stored_change(self):
        add_url = reverse('admin:lti_consumer_reusablelticonfiguration_add')
        change_url = self.change_url(self.configuration)
        delete_url = reverse('admin:lti_consumer_reusablelticonfiguration_delete', args=[self.configuration.pk])
        inline_prefix = LtiConfiguration._meta.get_field('reusable_configuration').remote_field.get_accessor_name()
        before = ReusableLtiConfiguration.objects.values().get(pk=self.configuration.pk)

        for actor in (self.staff, self.superuser):
            self.client.force_login(actor)
            with self.subTest(actor=actor.username):
                self.assertEqual(
                    self.client.post(add_url, {'name': 'Forged add', 'version': 'lti_1p1'}).status_code, 403,
                )
                # Ordinary forged change and the add-another variant are both refused.
                self.assertEqual(self.client.post(change_url, {'name': 'Forged rename'}).status_code, 403)
                self.assertEqual(
                    self.client.post(change_url, {'name': 'Forged rename', '_saveasnew': '1'}).status_code, 403,
                )
                self.assertEqual(self.client.post(change_url, {
                    f'{inline_prefix}-TOTAL_FORMS': '1',
                    f'{inline_prefix}-INITIAL_FORMS': '0',
                    f'{inline_prefix}-MIN_NUM_FORMS': '0',
                    f'{inline_prefix}-MAX_NUM_FORMS': '1000',
                    f'{inline_prefix}-0-location': 'block-v1:Org+Course+Run+type@lti_consumer+block@forged',
                }).status_code, 403)
                self.assertEqual(self.client.post(delete_url, {'post': 'yes'}).status_code, 403)
                # A bulk action may be ignored rather than refused; it must still write nothing.
                self.client.post(self.changelist_url, {
                    'action': 'delete_selected',
                    'index': '0',
                    '_selected_action': [str(self.configuration.pk)],
                })

        self.assertEqual(ReusableLtiConfiguration.objects.count(), 1)
        self.assertEqual(LtiConfiguration.objects.count(), 0)
        self.assertEqual(ReusableLtiConfiguration.objects.values().get(pk=self.configuration.pk), before)


class ReusableAdminListTests(AdminTestBase):
    """Changelist columns, filters, search and the absence of actions."""

    def setUp(self):
        super().setUp()
        self.course_configuration = self.make_configuration(name='Course tool')
        self.site_configuration = self.make_configuration(
            name='Site tool',
            version=ReusableLtiConfiguration.LTI_1P1,
            context_type='site',
            context_key=None,
        )
        self.client.force_login(self.make_user('global-staff', is_staff=True))

    def test_changelist_shows_columns_and_has_no_actions(self):
        response = self.client.get(self.changelist_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Course tool')
        self.assertContains(response, 'Site tool')
        for column in ('name', 'version', 'passport_id', 'context_type', 'updated_at'):
            with self.subTest(column=column):
                self.assertContains(response, f'column-{column}')
        self.assertFalse(response.context.get('actions'))
        self.assertNotContains(response, 'action-toggle')

    def test_filters_and_search_narrow_rows(self):
        response = self.client.get(self.changelist_url, {'version': ReusableLtiConfiguration.LTI_1P1})
        self.assertContains(response, 'Site tool')
        self.assertNotContains(response, 'Course tool')

        response = self.client.get(self.changelist_url, {'context_type': 'course'})
        self.assertContains(response, 'Course tool')
        self.assertNotContains(response, 'Site tool')

        response = self.client.get(self.changelist_url, {'q': 'Course'})
        self.assertContains(response, 'Course tool')
        self.assertNotContains(response, 'Site tool')

        response = self.client.get(self.changelist_url, {'q': str(self.site_configuration.passport_id)})
        self.assertContains(response, 'Site tool')
        self.assertNotContains(response, 'Course tool')


class LegacyPassportAdminTests(AdminTestBase):
    """The retained passport admin keeps its existing model-permission behaviour."""

    def setUp(self):
        super().setUp()
        self.passport = Lti1p3Passport.objects.create(name='Retained passport', lti_1p3_client_id='legacy-client-id')
        # A reusable copy with the same passport_id would vanish under any matched-ID hiding.
        self.make_configuration(name='Matched reusable copy', passport_id=self.passport.passport_id)
        self.changelist_url = reverse('admin:lti_consumer_lti1p3passport_changelist')
        self.change_url = reverse('admin:lti_consumer_lti1p3passport_change', args=[self.passport.pk])
        self.superuser = self.user_model.objects.create_superuser(
            username='superuser', email='superuser@example.com', password=None,
        )
        self.staff = self.make_user('plain-staff', is_staff=True)

    def test_superuser_still_views_and_edits_passports(self):
        self.client.force_login(self.superuser)
        response = self.client.get(self.changelist_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Retained passport')
        self.assertEqual(self.client.get(self.change_url).status_code, 200)
        prefix = LtiConfiguration._meta.get_field('lti_1p3_passport').remote_field.get_accessor_name()
        response = self.client.post(self.change_url, {
            'name': 'Renamed passport',
            'lti_1p3_client_id': 'legacy-client-id',
            # The model's clean() requires one tool key source for an LTI 1.3 passport.
            'lti_1p3_tool_public_key': 'legacy-tool-public-key',
            f'{prefix}-TOTAL_FORMS': '0',
            f'{prefix}-INITIAL_FORMS': '0',
            f'{prefix}-MIN_NUM_FORMS': '0',
            f'{prefix}-MAX_NUM_FORMS': '1000',
        })
        self.assertEqual(response.status_code, 302)
        self.passport.refresh_from_db()
        self.assertEqual(self.passport.name, 'Renamed passport')

    def test_staff_without_model_permissions_gains_no_bypass(self):
        self.client.force_login(self.staff)
        self.assertNotEqual(self.client.get(self.changelist_url).status_code, 200)
