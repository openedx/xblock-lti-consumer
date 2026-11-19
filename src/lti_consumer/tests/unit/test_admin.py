"""
Behavioural tests for the reusable-configuration Django admin.

Journeys drive the real admin site, URLconf, ModelAdmin and ORM. Only the external
edx-platform GlobalStaff role module is injected, since it is not installed here.
"""
import sys
from types import ModuleType
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from lti_consumer.models import Lti1p3Passport, LtiConfiguration, ReusableLtiConfiguration

COURSE_KEY = 'course-v1:Org+Course+Run'
ROLES_MODULE = 'common.djangoapps.student.roles'
PRIVATE_KEY = 'fake-signing-key-sentinel-never-render'


def global_staff_roles(has_user):
    """Inject the absent external role module; edx-platform owns the real one."""
    roles = ModuleType(ROLES_MODULE)
    roles.GlobalStaff = Mock(return_value=Mock(has_user=Mock(side_effect=has_user)))
    return roles


class ReusableAdminJourneyTests(TestCase):
    """Admin journeys through the real admin site, URLconf, ModelAdmin and ORM."""

    def setUp(self):
        patcher = patch.dict(sys.modules, {ROLES_MODULE: global_staff_roles(lambda user: user.is_staff)})
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
        self.assertNotIn(b'Visible configuration', response.content)

    def test_access_requires_the_platform_global_staff_role(self):
        configuration = self.make_configuration(name='Visible configuration')
        global_staff = self.make_user('global-staff', is_staff=True)
        permitted_staff = self.make_user('permitted-staff', is_staff=True)
        permitted_staff.user_permissions.add(
            Permission.objects.get(codename='view_reusablelticonfiguration'),
        )
        superuser = self.make_superuser()

        for actor in (global_staff, superuser):
            self.client.force_login(actor)
            with self.subTest(actor=actor.username):
                self.assertContains(self.client.get(reverse('admin:index')), self.changelist_url)
                self.assertContains(self.client.get(self.changelist_url), 'Visible configuration')
                self.assertEqual(self.client.get(self.change_url(configuration)).status_code, 200)

        self.client.force_login(self.make_user('course-staff'))
        self.assert_denied(self.client.get(self.changelist_url))
        self.assert_denied(self.client.get(self.change_url(configuration)))

        # Model permission does not bypass the platform role.
        self.client.force_login(permitted_staff)
        with patch.dict(sys.modules, {ROLES_MODULE: global_staff_roles(lambda user: False)}):
            self.assert_denied(self.client.get(self.changelist_url))
            self.assert_denied(self.client.get(self.change_url(configuration)))
            self.assertNotContains(self.client.get(reverse('admin:index')), self.changelist_url)

    def test_detail_shows_stored_values_without_private_key_or_generation(self):
        configuration = self.make_configuration(
            name='Rendered configuration',
            context_type=None,
            context_key='raw-copied-context-key',
            lti_1p1_client_key='stored-client-key',
            lti_1p3_tool_public_key='stored-tool-public-key',
            lti_1p3_tool_keyset_url='https://tool.example/jwks',
            lti_1p3_internal_private_key=PRIVATE_KEY,
            lti_1p3_internal_private_key_id='stored-key-id',
            lti_1p3_internal_public_jwk='{"keys": ["stored-public-jwk"]}',
        )
        self.client.force_login(self.make_user('global-staff', is_staff=True))

        response = self.client.get(self.change_url(configuration))
        self.assertEqual(response.status_code, 200)
        if PRIVATE_KEY.encode() in response.content:
            self.fail('signing private key value rendered')
        for value in (
            'raw-copied-context-key',
            'stored-client-key',
            'stored-tool-public-key',
            'https://tool.example/jwks',
            'stored-key-id',
            'stored-public-jwk',
        ):
            self.assertContains(response, value)

        incomplete = self.make_configuration(
            name='Incomplete configuration', version=None, context_type=None, context_key=None,
        )
        updated_at = incomplete.updated_at
        self.assertEqual(self.client.get(self.changelist_url).status_code, 200)
        self.assertEqual(self.client.get(self.change_url(incomplete)).status_code, 200)
        incomplete.refresh_from_db()
        for field in ('lti_1p3_internal_private_key', 'lti_1p3_internal_private_key_id',
                      'lti_1p3_internal_public_jwk'):
            if getattr(incomplete, field):
                self.fail('reading generated reusable signing key material')
        self.assertEqual(incomplete.updated_at, updated_at)

    def test_no_role_can_add_change_or_delete_through_the_admin(self):
        configuration = self.make_configuration(name='Immutable configuration')
        placement = self.make_placement(
            configuration, 'block-v1:Org+Course+Run+type@lti_consumer+block@immutable', 'Immutable passport',
        )
        staff = self.make_user('global-staff', is_staff=True)
        superuser = self.make_superuser()
        add_url = reverse('admin:lti_consumer_reusablelticonfiguration_add')
        change_url = self.change_url(configuration)
        delete_url = reverse('admin:lti_consumer_reusablelticonfiguration_delete', args=[configuration.pk])
        row_before = ReusableLtiConfiguration.objects.values().get(pk=configuration.pk)
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
        if ReusableLtiConfiguration.objects.values().get(pk=configuration.pk) != row_before:
            self.fail('reusable configuration changed')
        self.assertEqual(
            LtiConfiguration.objects.get(pk=placement.pk).reusable_configuration_id, configuration.pk,
        )

    def test_legacy_passport_and_reusable_changelists_show_the_shared_uuid(self):
        passport = Lti1p3Passport.objects.create(name='Retained passport')
        self.make_configuration(name='Matched reusable copy', passport_id=passport.passport_id)
        self.client.force_login(self.make_superuser())
        shared_uuid = str(passport.passport_id)

        for url, name in (
            (reverse('admin:lti_consumer_lti1p3passport_changelist'), 'Retained passport'),
            (self.changelist_url, 'Matched reusable copy'),
        ):
            response = self.client.get(url)
            self.assertContains(response, name)
            self.assertContains(response, shared_uuid)
