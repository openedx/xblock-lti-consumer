"""
Behavioural tests for the reusable-configuration Django admin.

Journeys drive the real admin site, URLconf, ModelAdmin, formsets and ORM.
Only the edx-platform Global Staff seam is patched, since it is not installed.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from lti_consumer.models import Lti1p3Passport, LtiConfiguration, ReusableLtiConfiguration

COURSE_KEY = 'course-v1:Org+Course+Run'
GLOBAL_STAFF_PATCH = 'lti_consumer.plugin.compat.user_is_global_staff'
PRIVATE_KEY = '-----BEGIN RSA PRIVATE KEY----- never-render-this-value'


class ReusableAdminJourneyTests(TestCase):
    """Admin journeys through the real admin site, formsets and ORM."""

    def setUp(self):
        patcher = patch(GLOBAL_STAFF_PATCH, return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.user_model = get_user_model()
        self.changelist_url = reverse('admin:lti_consumer_reusablelticonfiguration_changelist')

    def make_user(self, username, **kwargs):
        return self.user_model.objects.create_user(username, password='password', **kwargs)

    def make_superuser(self):
        return self.user_model.objects.create_superuser(
            username='superuser', email='superuser@example.com', password=None,
        )

    def make_configuration(self, **kwargs):
        values = {'name': 'Advantage tool', 'version': ReusableLtiConfiguration.LTI_1P3,
                  'context_type': 'course', 'context_key': COURSE_KEY}
        values.update(kwargs)
        return ReusableLtiConfiguration.objects.create(**values)

    def make_placement(self, configuration, location, passport_name):
        return LtiConfiguration.objects.create(
            location=location,
            reusable_configuration=configuration,
            # A bound passport keeps the post_save signal off the modulestore.
            lti_1p3_passport=Lti1p3Passport.objects.create(name=passport_name),
        )

    def change_url(self, configuration):
        return reverse('admin:lti_consumer_reusablelticonfiguration_change', args=[configuration.pk])

    def assert_denied(self, response):
        self.assertNotEqual(response.status_code, 200)
        self.assertNotContains(response, 'Visible configuration', status_code=response.status_code)

    def test_access_is_global_staff_only_and_model_permissions_do_not_bypass(self):
        configuration = self.make_configuration(name='Visible configuration')
        placement = self.make_placement(
            configuration, 'block-v1:Org+Course+Run+type@lti_consumer+block@bound', 'Bound passport',
        )
        global_staff = self.make_user('global-staff', is_staff=True)
        self.assertFalse(global_staff.has_perm('lti_consumer.view_reusablelticonfiguration'))
        permitted_staff = self.make_user('permitted-staff', is_staff=True)
        permitted_staff.user_permissions.set(Permission.objects.all())
        self.assertTrue(permitted_staff.has_perm('lti_consumer.view_reusablelticonfiguration'))
        superuser = self.make_superuser()

        for actor in (global_staff, permitted_staff, superuser):
            self.client.force_login(actor)
            with self.subTest(actor=actor.username):
                response = self.client.get(reverse('admin:index'))
                self.assertContains(response, self.changelist_url)
                response = self.client.get(self.changelist_url)
                self.assertContains(response, 'Visible configuration')
                self.assertContains(response, self.change_url(configuration))
                response = self.client.get(self.change_url(configuration))
                self.assertContains(response, placement.location)

        self.client.force_login(self.make_user('ordinary'))
        self.assert_denied(self.client.get(self.changelist_url))
        self.assert_denied(self.client.get(self.change_url(configuration)))

        self.client.force_login(permitted_staff)
        with patch(GLOBAL_STAFF_PATCH, return_value=False):
            self.assert_denied(self.client.get(self.changelist_url))
            self.assert_denied(self.client.get(self.change_url(configuration)))
            response = self.client.get(reverse('admin:index'))
            self.assertNotContains(response, self.changelist_url)

    def test_detail_renders_stored_values_except_private_key_and_reads_never_write(self):
        configuration = self.make_configuration(
            name='Rendered configuration',
            is_active=False,
            context_type=None,
            context_key='raw-copied-context-key',
            lti_1p1_client_key='stored-client-key',
            lti_1p1_client_secret='stored-client-secret',
            lti_1p3_tool_public_key='stored-tool-public-key',
            lti_1p3_tool_keyset_url='https://tool.example/jwks',
            lti_1p3_internal_private_key=PRIVATE_KEY,
            lti_1p3_internal_private_key_id='stored-key-id',
            lti_1p3_internal_public_jwk='{"keys": ["stored-public-jwk"]}',
        )
        placement = self.make_placement(
            configuration, 'block-v1:Org+Course+Run+type@lti_consumer+block@read', 'Read passport',
        )
        self.client.force_login(self.make_user('global-staff', is_staff=True))

        response = self.client.get(self.change_url(configuration))
        self.assertEqual(response.status_code, 200)
        with self.subTest('stored values render and detail is view-only'):
            for value in (
                'raw-copied-context-key',
                'stored-client-key',
                'stored-client-secret',
                'stored-tool-public-key',
                'https://tool.example/jwks',
                'stored-key-id',
                'stored-public-jwk',
                placement.location,
            ):
                self.assertContains(response, value)
            self.assertNotContains(response, 'never-render-this-value')
            self.assertContains(response, 'View Reusable LTI configuration')
            self.assertNotContains(response, 'name="name"')
            self.assertNotContains(response, 'name="context_key"')
            self.assertNotContains(response, 'name="lti_1p3_internal_private_key"')

        with self.subTest('changelist has no bulk actions'):
            response = self.client.get(self.changelist_url)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.context.get('actions'))
            self.assertNotContains(response, 'action-toggle')

        with self.subTest('blank keys are not generated or saved on read'):
            incomplete = self.make_configuration(
                name='Incomplete configuration', version=None, context_type=None, context_key=None,
            )
            updated_at = incomplete.updated_at
            self.assertEqual(incomplete.lti_1p3_internal_private_key, '')
            self.assertEqual(self.client.get(self.changelist_url).status_code, 200)
            self.assertEqual(self.client.get(self.change_url(incomplete)).status_code, 200)
            incomplete.refresh_from_db()
            self.assertEqual(incomplete.lti_1p3_internal_private_key, '')
            self.assertEqual(incomplete.lti_1p3_internal_private_key_id, '')
            self.assertEqual(incomplete.lti_1p3_internal_public_jwk, '')
            self.assertEqual(incomplete.updated_at, updated_at)

    def test_no_role_can_add_change_or_delete_through_the_admin(self):
        configuration = self.make_configuration(
            name='Immutable configuration',
            lti_1p1_client_key='immutable-client-key',
            lti_1p1_client_secret='immutable-client-secret',
        )
        self.make_placement(
            configuration, 'block-v1:Org+Course+Run+type@lti_consumer+block@immutable', 'Immutable passport',
        )
        staff = self.make_user('global-staff', is_staff=True)
        superuser = self.make_superuser()
        add_url = reverse('admin:lti_consumer_reusablelticonfiguration_add')
        change_url = self.change_url(configuration)
        delete_url = reverse('admin:lti_consumer_reusablelticonfiguration_delete', args=[configuration.pk])
        inline_prefix = LtiConfiguration._meta.get_field('reusable_configuration').remote_field.get_accessor_name()
        row_before = ReusableLtiConfiguration.objects.values().get(pk=configuration.pk)
        placements_before = list(LtiConfiguration.objects.values())
        counts_before = (ReusableLtiConfiguration.objects.count(), LtiConfiguration.objects.count())

        for actor in (staff, superuser):
            self.client.force_login(actor)
            with self.subTest(actor=actor.username):
                self.assertEqual(
                    self.client.post(add_url, {'name': 'Forged add', 'version': 'lti_1p1'}).status_code, 403,
                )
                self.assertEqual(self.client.post(change_url, {'name': 'Forged rename'}).status_code, 403)
                self.assertEqual(self.client.post(change_url, {
                    'name': 'Forged rename', '_saveasnew': '1',
                }).status_code, 403)
                self.assertEqual(self.client.post(change_url, {
                    f'{inline_prefix}-TOTAL_FORMS': '1',
                    f'{inline_prefix}-INITIAL_FORMS': '0',
                    f'{inline_prefix}-MIN_NUM_FORMS': '0',
                    f'{inline_prefix}-MAX_NUM_FORMS': '1000',
                    f'{inline_prefix}-0-location': 'block-v1:Org+Course+Run+type@lti_consumer+block@forged',
                }).status_code, 403)
                self.assertEqual(self.client.post(delete_url, {'post': 'yes'}).status_code, 403)
                # A bulk action may be refused or ignored; it must still write nothing.
                self.client.post(self.changelist_url, {
                    'action': 'delete_selected',
                    'index': '0',
                    '_selected_action': [str(configuration.pk)],
                })

        self.assertEqual(
            (ReusableLtiConfiguration.objects.count(), LtiConfiguration.objects.count()), counts_before,
        )
        self.assertEqual(ReusableLtiConfiguration.objects.values().get(pk=configuration.pk), row_before)
        self.assertEqual(list(LtiConfiguration.objects.values()), placements_before)

    def test_legacy_passport_admin_is_unchanged(self):
        passport = Lti1p3Passport.objects.create(name='Retained passport', lti_1p3_client_id='legacy-client-id')
        # A reusable copy with the same passport_id would vanish under any matched-ID hiding.
        self.make_configuration(name='Matched reusable copy', passport_id=passport.passport_id)
        changelist_url = reverse('admin:lti_consumer_lti1p3passport_changelist')
        change_url = reverse('admin:lti_consumer_lti1p3passport_change', args=[passport.pk])
        superuser = self.make_superuser()
        plain_staff = self.make_user('plain-staff', is_staff=True)

        self.client.force_login(superuser)
        with self.subTest('superuser still views and edits'):
            self.assertContains(self.client.get(changelist_url), 'Retained passport')
            self.assertEqual(self.client.get(change_url).status_code, 200)
            prefix = LtiConfiguration._meta.get_field('lti_1p3_passport').remote_field.get_accessor_name()
            response = self.client.post(change_url, {
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
            passport.refresh_from_db()
            self.assertEqual(passport.name, 'Renamed passport')

        with self.subTest('matched reusable copy stays visible'):
            self.assertContains(self.client.get(self.changelist_url), 'Matched reusable copy')

        self.client.force_login(plain_staff)
        with self.subTest('staff without model permissions denied'):
            self.assertNotEqual(self.client.get(changelist_url).status_code, 200)
