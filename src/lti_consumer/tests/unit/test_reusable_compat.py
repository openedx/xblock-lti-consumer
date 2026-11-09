"""Tests for the reusable-configuration Studio catalog compatibility layer."""
import subprocess
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from ccx_keys.locator import CCXLocator
from django.http import HttpRequest
from django.test import SimpleTestCase
from opaque_keys.edx.locator import CourseLocator, LibraryLocator

from lti_consumer.plugin import compat


class StudioAccessibleCourseKeysAdapterTests(SimpleTestCase):
    """The CMS catalog is authoritative and is consulted without a per-course AuthZ call.

    Accepted risk, documented on PR #715: the platform catalog's AccessListFallback
    branch can list every course, and this adapter re-applies no per-course read check.
    """

    def test_catalog_is_authoritative_for_distinct_normal_course_keys(self):
        user = SimpleNamespace(is_authenticated=True, username='author')
        first = CourseLocator('Org', 'Course', 'Run')
        second = CourseLocator('Org', 'Other', 'Run')
        candidates = [
            SimpleNamespace(id=first),
            SimpleNamespace(id=first),
            SimpleNamespace(id=second),
            SimpleNamespace(id=LibraryLocator(org='Org', library='Library')),
            SimpleNamespace(id=CCXLocator.from_string('ccx-v1:Org+Course+Run+ccx@1')),
            SimpleNamespace(id='not-a-course-key'),
        ]

        cms = ModuleType('cms.djangoapps.contentstore.views.course')
        cms_candidates = Mock(return_value=(candidates, []))
        cms.get_courses_accessible_to_user = cms_candidates
        authz = Mock()
        authz_decorators = ModuleType('openedx.core.djangoapps.authz.decorators')
        authz_decorators.user_has_course_permission = authz
        modules = {
            'cms.djangoapps.contentstore.views.course': cms,
            'openedx.core.djangoapps.authz.decorators': authz_decorators,
        }

        with patch.dict('sys.modules', modules):
            self.assertEqual(
                compat.get_studio_accessible_course_keys(SimpleNamespace(is_authenticated=False)),
                [],
            )
            cms_candidates.assert_not_called()

            # Deduplicated, sorted and limited to normal course keys: the catalog decides.
            self.assertEqual(compat.get_studio_accessible_course_keys(user), [first, second])

            cms_candidates.assert_called_once()
            request = cms_candidates.call_args.args[0]
            self.assertIsInstance(request, HttpRequest)
            self.assertIs(request.user, user)
            self.assertEqual(request.GET, {})

            cms_candidates.return_value = ([], [])
            self.assertEqual(compat.get_studio_accessible_course_keys(user), [])

            # Platform failures must surface, never be swallowed into a denial or an allow.
            cms_candidates.side_effect = RuntimeError('CMS unavailable')
            with self.assertRaisesRegex(RuntimeError, 'CMS unavailable'):
                compat.get_studio_accessible_course_keys(user)

            authz.assert_not_called()


class GlobalStaffCompatTests(SimpleTestCase):
    """The Global Staff seam delegates to the canonical platform role class."""

    def test_user_is_global_staff_delegates_to_platform_role(self):
        user = object()
        result = object()
        role = Mock()
        role.has_user.return_value = result
        global_staff = Mock(return_value=role)
        roles = ModuleType('common.djangoapps.student.roles')
        roles.GlobalStaff = global_staff
        modules = {'common.djangoapps.student.roles': roles}
        with patch.dict('sys.modules', modules):
            self.assertIs(compat.user_is_global_staff(user), result)
        global_staff.assert_called_once_with()
        role.has_user.assert_called_once_with(user)

    def test_superuser_without_the_platform_staff_role_keeps_access(self):
        """The previous superuser-only authorization must not be narrowed here."""
        user = SimpleNamespace(is_superuser=True, is_staff=False)
        role = Mock()
        role.has_user.return_value = False
        roles = ModuleType('common.djangoapps.student.roles')
        roles.GlobalStaff = Mock(return_value=role)
        with patch.dict('sys.modules', {'common.djangoapps.student.roles': roles}):
            self.assertTrue(compat.user_is_global_staff(user))


class OtherPlatformAdaptersTests(SimpleTestCase):
    """The remaining reusable-configuration adapters stay thin platform seams."""

    def test_get_active_organizations_delegates_to_the_organizations_api(self):
        organizations = ModuleType('organizations.api')
        organizations.get_organizations = Mock(return_value=['org'])
        with patch.dict('sys.modules', {'organizations.api': organizations}):
            self.assertEqual(compat.get_active_organizations(), ['org'])
        organizations.get_organizations.assert_called_once_with()

    def test_user_is_course_admin_uses_the_course_instructor_role(self):
        user = object()
        course_key = CourseLocator('Org', 'Course', 'Run')
        role = Mock()
        role.has_user.return_value = True
        instructor_role = Mock(return_value=role)
        roles = ModuleType('common.djangoapps.student.roles')
        roles.CourseInstructorRole = instructor_role
        with patch.dict('sys.modules', {'common.djangoapps.student.roles': roles}):
            self.assertTrue(compat.user_is_course_admin(user, course_key))
        instructor_role.assert_called_once_with(course_key)
        role.has_user.assert_called_once_with(user)


class LazyPlatformImportTests(SimpleTestCase):
    """The adapter module imports without any CMS or LMS package installed."""

    def test_compat_imports_with_cms_and_lms_absent(self):
        script = """
import sys

for name in ('cms', 'lms', 'openedx', 'common.djangoapps.student'):
    sys.modules[name] = None

import lti_consumer.plugin.compat as compat

assert compat.get_studio_accessible_course_keys.__module__ == 'lti_consumer.plugin.compat'
assert compat.user_is_global_staff.__module__ == 'lti_consumer.plugin.compat'
loaded = [name for name, module in sys.modules.items() if module is not None]
assert not [name for name in loaded if name.split('.')[0] in ('cms', 'lms', 'openedx')], loaded
"""
        result = subprocess.run(
            [sys.executable, '-c', script],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
