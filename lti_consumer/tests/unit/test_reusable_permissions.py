"""Tests for reusable configuration context management rules."""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from opaque_keys.edx.keys import CourseKey

from lti_consumer.plugin.reusable_permissions import can_manage_reusable_context

COURSE_KEY = 'course-v1:Org+Course+Run'
COURSE_ADMIN_PATCH = 'lti_consumer.plugin.reusable_permissions.compat.user_is_course_admin'


class ReusableContextPermissionTests(SimpleTestCase):
    """Management authority follows the configuration's single creation context."""

    def user(self, *, authenticated=True):
        return SimpleNamespace(is_authenticated=authenticated, is_superuser=False)

    def superuser(self, *, authenticated=True):
        return SimpleNamespace(is_authenticated=authenticated, is_superuser=True)

    @patch(COURSE_ADMIN_PATCH)
    def test_management_authority_follows_course_admin_and_superuser_rules(self, is_admin):
        user = self.user()
        is_admin.return_value = True
        self.assertTrue(can_manage_reusable_context(user, 'course', COURSE_KEY))
        is_admin.assert_called_once_with(user, CourseKey.from_string(COURSE_KEY))

        is_admin.reset_mock()
        is_admin.return_value = False
        self.assertFalse(can_manage_reusable_context(user, 'course', COURSE_KEY))
        is_admin.assert_called_once_with(user, CourseKey.from_string(COURSE_KEY))

        is_admin.reset_mock()
        for context_type in ('organization', 'site'):
            with self.subTest(context_type=context_type):
                self.assertFalse(can_manage_reusable_context(user, context_type, 'org'))
                self.assertTrue(can_manage_reusable_context(self.superuser(), context_type, 'org'))
        self.assertTrue(can_manage_reusable_context(self.superuser(), 'course', COURSE_KEY))
        is_admin.assert_not_called()

    @patch(COURSE_ADMIN_PATCH)
    def test_unauthenticated_unknown_and_invalid_contexts_fail_closed(self, is_admin):
        invalid_contexts = (
            (None, COURSE_KEY),
            ('', COURSE_KEY),
            ('classes', COURSE_KEY),
            ('course', ''),
            ('course', None),
            ('course', 'not-a-course-key'),
            ('course', 'course-v1:version@519665f6223ebd6980884f2b'),
            ('course', 'library-v1:Org+Library'),
            ('course', 'block-v1:Org+Type+Block+block@1'),
        )
        for user in (self.user(), self.superuser(), self.superuser(authenticated=False)):
            for context_type, key in invalid_contexts:
                with self.subTest(
                    superuser=user.is_superuser,
                    authenticated=user.is_authenticated,
                    context_type=context_type,
                    key=key,
                ):
                    self.assertFalse(can_manage_reusable_context(user, context_type, key))
        is_admin.assert_not_called()

    @patch(COURSE_ADMIN_PATCH)
    def test_ccx_course_context_is_superuser_only(self, is_admin):
        # Studio's course catalog excludes CCX keys, so course admins cannot manage them.
        ccx_key = 'ccx-v1:Org+Course+Run+ccx@1'
        self.assertTrue(can_manage_reusable_context(self.superuser(), 'course', ccx_key))
        is_admin.return_value = True
        self.assertFalse(can_manage_reusable_context(self.user(), 'course', ccx_key))
        is_admin.assert_not_called()

    @patch(COURSE_ADMIN_PATCH)
    def test_course_admin_decision_is_cached_within_a_request(self, is_admin):
        user = self.user()
        cache = {}
        is_admin.return_value = True
        self.assertTrue(can_manage_reusable_context(user, 'course', COURSE_KEY, course_admin_cache=cache))
        self.assertTrue(can_manage_reusable_context(
            user, 'course', f'{COURSE_KEY}+branch@draft', course_admin_cache=cache,
        ))
        is_admin.assert_called_once_with(user, CourseKey.from_string(COURSE_KEY))
        self.assertEqual(cache, {CourseKey.from_string(COURSE_KEY): True})

        is_admin.side_effect = AssertionError('cached result must be reused')
        self.assertTrue(can_manage_reusable_context(
            user, 'course', COURSE_KEY,
            course_admin_cache={CourseKey.from_string(COURSE_KEY): True},
        ))
        is_admin.assert_called_once_with(user, CourseKey.from_string(COURSE_KEY))
