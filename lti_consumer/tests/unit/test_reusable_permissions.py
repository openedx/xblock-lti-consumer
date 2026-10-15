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
    def test_course_context_requires_admin_of_that_single_course(self, is_admin):
        user = self.user()
        is_admin.return_value = True
        self.assertTrue(can_manage_reusable_context(user, 'course', COURSE_KEY))
        is_admin.assert_called_once_with(user, CourseKey.from_string(COURSE_KEY))

        is_admin.reset_mock()
        is_admin.return_value = False
        self.assertFalse(can_manage_reusable_context(user, 'course', COURSE_KEY))
        is_admin.assert_called_once()

    @patch(COURSE_ADMIN_PATCH)
    def test_organization_and_site_contexts_are_superuser_only(self, is_admin):
        for context_type in ('organization', 'site'):
            with self.subTest(context_type=context_type):
                self.assertFalse(can_manage_reusable_context(self.user(), context_type, 'org'))
                self.assertTrue(can_manage_reusable_context(self.superuser(), context_type, 'org'))
        is_admin.assert_not_called()

    @patch(COURSE_ADMIN_PATCH)
    def test_missing_unknown_or_malformed_contexts_are_denied(self, is_admin):
        for user in (self.user(), self.superuser()):
            for context_type, key in (
                (None, COURSE_KEY),
                ('', COURSE_KEY),
                ('classes', COURSE_KEY),
                ('course', ''),
                ('course', None),
                ('course', 'not-a-course-key'),
                ('course', 'course-v1:version@519665f6223ebd6980884f2b'),
            ):
                with self.subTest(superuser=user.is_superuser, context_type=context_type, key=key):
                    self.assertFalse(can_manage_reusable_context(user, context_type, key))
        is_admin.assert_not_called()

    @patch(COURSE_ADMIN_PATCH)
    def test_library_and_non_course_keys_fail_closed(self, is_admin):
        for key in ('library-v1:Org+Library', 'block-v1:Org+Type+Block+block@1'):
            with self.subTest(key=key):
                self.assertFalse(can_manage_reusable_context(self.superuser(), 'course', key))
                self.assertFalse(can_manage_reusable_context(self.user(), 'course', key))
        is_admin.assert_not_called()

    @patch(COURSE_ADMIN_PATCH)
    def test_ccx_course_context_is_superuser_only(self, is_admin):
        ccx_key = 'ccx-v1:Org+Course+Run+ccx@1'
        self.assertTrue(can_manage_reusable_context(self.superuser(), 'course', ccx_key))
        is_admin.return_value = True
        self.assertFalse(can_manage_reusable_context(self.user(), 'course', ccx_key))
        is_admin.assert_not_called()

    @patch(COURSE_ADMIN_PATCH)
    def test_course_admin_cache_is_shared_within_a_request(self, is_admin):
        is_admin.return_value = True
        user = self.user()
        cache = {}
        self.assertTrue(can_manage_reusable_context(user, 'course', COURSE_KEY, course_admin_cache=cache))
        self.assertTrue(can_manage_reusable_context(
            user, 'course', f'{COURSE_KEY}+branch@draft', course_admin_cache=cache,
        ))
        is_admin.assert_called_once_with(user, CourseKey.from_string(COURSE_KEY))
        self.assertEqual(len(cache), 1)

    @patch(COURSE_ADMIN_PATCH)
    def test_prepopulated_course_admin_cache_avoids_rechecks(self, is_admin):
        is_admin.side_effect = AssertionError('cached result must be reused')
        self.assertTrue(can_manage_reusable_context(
            self.user(), 'course', COURSE_KEY,
            course_admin_cache={CourseKey.from_string(COURSE_KEY): True},
        ))
        is_admin.assert_not_called()

    @patch(COURSE_ADMIN_PATCH)
    def test_unauthenticated_user_is_denied(self, is_admin):
        self.assertFalse(can_manage_reusable_context(
            self.superuser(authenticated=False), 'course', COURSE_KEY,
        ))
        self.assertFalse(can_manage_reusable_context(self.superuser(authenticated=False), 'site'))
        is_admin.assert_not_called()
