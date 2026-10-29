"""Tests for the reusable-configuration Studio catalog compatibility layer."""
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, call, patch

from ccx_keys.locator import CCXLocator
from django.http import HttpRequest
from django.test import SimpleTestCase
from opaque_keys.edx.locator import CourseLocator, LibraryLocator

from lti_consumer.plugin import compat


class StudioAccessibleCourseKeysAdapterTests(SimpleTestCase):
    """The public adapter reads CMS candidates through AuthZ once per canonical course."""

    def test_catalog_filters_and_rechecks_external_cms_and_authz(self):
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
        legacy_read = 'read'
        authz_constants = ModuleType('openedx.core.djangoapps.authz.constants')
        authz_constants.LegacyAuthoringPermission = SimpleNamespace(READ=legacy_read)
        authz_decorators = ModuleType('openedx.core.djangoapps.authz.decorators')
        authz = Mock(side_effect=lambda actor, permission, key, fallback: key == first)
        authz_decorators.user_has_course_permission = authz
        permissions = ModuleType('openedx_authz.constants.permissions')
        courses_view_course = SimpleNamespace(identifier='courses.view_course')
        permissions.COURSES_VIEW_COURSE = courses_view_course
        modules = {
            'cms.djangoapps.contentstore.views.course': cms,
            'openedx.core.djangoapps.authz.constants': authz_constants,
            'openedx.core.djangoapps.authz.decorators': authz_decorators,
            'openedx_authz.constants.permissions': permissions,
        }

        with patch.dict('sys.modules', modules):
            self.assertEqual(
                compat.get_studio_accessible_course_keys(SimpleNamespace(is_authenticated=False)),
                [],
            )
            cms_candidates.assert_not_called()
            authz.assert_not_called()
            self.assertEqual(compat.get_studio_accessible_course_keys(user), [first])

            cms_candidates.assert_called_once()
            request = cms_candidates.call_args.args[0]
            self.assertIsInstance(request, HttpRequest)
            self.assertIs(request.user, user)
            self.assertEqual(request.GET, {})
            self.assertCountEqual(authz.call_args_list, [
                call(user, courses_view_course.identifier, first,
                     legacy_read),
                call(user, courses_view_course.identifier, second,
                     legacy_read),
            ])

            # Platform failures must surface, never be swallowed into a denial or an allow.
            authz.side_effect = RuntimeError('permission backend unavailable')
            with self.assertRaisesRegex(RuntimeError, 'permission backend unavailable'):
                compat.get_studio_accessible_course_keys(user)

            authz.side_effect = lambda actor, permission, key, fallback: key == first
            cms_candidates.side_effect = RuntimeError('CMS unavailable')
            with self.assertRaisesRegex(RuntimeError, 'CMS unavailable'):
                compat.get_studio_accessible_course_keys(user)


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
