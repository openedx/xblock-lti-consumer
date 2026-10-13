"""Tests for reusable configuration scope management rules."""
from types import SimpleNamespace
from unittest.mock import call, patch

from django.test import SimpleTestCase
from opaque_keys.edx.keys import CourseKey

from lti_consumer.plugin.reusable_permissions import can_manage_reusable_scope


class ReusableScopePermissionTests(SimpleTestCase):
    """Creation permission follows the full proposed scope."""

    def setUp(self):
        self.course_scope = {'course_keys': [
            'course-v1:Org+Course+Run',
            'course-v1:Org+Second+Run',
        ]}

    def user(self, *, authenticated=True, superuser=False):
        return SimpleNamespace(is_authenticated=authenticated, is_superuser=superuser)

    @patch('lti_consumer.plugin.reusable_permissions.compat.user_is_course_admin')
    def test_course_admin_must_admin_every_scoped_course(self, is_admin):
        user = self.user()
        is_admin.return_value = True
        self.assertTrue(can_manage_reusable_scope(user, self.course_scope))
        self.assertEqual(is_admin.call_args_list, [
            call(user, CourseKey.from_string(course_key)) for course_key in (
                'course-v1:Org+Course+Run', 'course-v1:Org+Second+Run',
            )
        ])

        is_admin.reset_mock()
        is_admin.side_effect = [True, False]
        self.assertFalse(can_manage_reusable_scope(user, self.course_scope))

    @patch('lti_consumer.plugin.reusable_permissions.compat.user_is_course_admin')
    def test_branch_scope_uses_the_persisted_course_identity(self, is_admin):
        is_admin.return_value = True
        branch_key = CourseKey.from_string('course-v1:Org+Course+Run+branch@draft')
        base_key = CourseKey.from_string('course-v1:Org+Course+Run')

        self.assertTrue(can_manage_reusable_scope(
            self.user(), {'course_keys': [str(branch_key)]},
        ))
        is_admin.assert_called_once_with(self.user(), base_key)

    @patch('lti_consumer.plugin.reusable_permissions.compat.user_is_course_admin')
    def test_organization_and_site_scopes_are_superuser_only(self, is_admin):
        for scope in (
            {'organization_keys': ['org']},
            {'site_wide': True},
        ):
            with self.subTest(scope=scope):
                self.assertFalse(can_manage_reusable_scope(self.user(), scope))
                self.assertTrue(can_manage_reusable_scope(self.user(superuser=True), scope))
        is_admin.assert_not_called()

    @patch('lti_consumer.plugin.reusable_permissions.compat.user_is_course_admin')
    def test_library_scope_fails_closed_pending_policy(self, is_admin):
        scope = {'course_keys': ['library-v1:Org+Library']}
        self.assertFalse(can_manage_reusable_scope(self.user(superuser=True), scope))
        self.assertFalse(can_manage_reusable_scope(self.user(), scope))
        is_admin.assert_not_called()

    @patch('lti_consumer.plugin.reusable_permissions.compat.user_is_course_admin')
    def test_ccx_scope_is_superuser_only(self, is_admin):
        scope = {'course_keys': ['ccx-v1:Org+Course+Run+ccx@1']}
        self.assertFalse(can_manage_reusable_scope(self.user(), scope))
        self.assertTrue(can_manage_reusable_scope(self.user(superuser=True), scope))
        is_admin.assert_not_called()

    @patch('lti_consumer.plugin.reusable_permissions.compat.user_is_course_admin')
    def test_invalid_or_empty_scope_is_denied(self, is_admin):
        self.assertFalse(can_manage_reusable_scope(self.user(), {'course_keys': ['invalid']}))
        self.assertFalse(can_manage_reusable_scope(self.user(superuser=True), {
            'course_keys': ['course-v1:version@519665f6223ebd6980884f2b'],
        }))
        self.assertFalse(can_manage_reusable_scope(self.user(superuser=True), {'site_wide': False}))
        is_admin.assert_not_called()

    def test_unauthenticated_user_is_denied(self):
        self.assertFalse(can_manage_reusable_scope(self.user(authenticated=False, superuser=True), self.course_scope))
