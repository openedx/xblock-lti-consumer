"""Tests for the reusable-configuration Studio catalog compatibility layer."""
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, call, patch

from ccx_keys.locator import CCXLocator
from django.http import HttpRequest
from django.test import SimpleTestCase
from opaque_keys.edx.locator import CourseLocator, LibraryLocator

from lti_consumer.plugin import compat


class StudioAccessibleCourseKeysTests(SimpleTestCase):
    """The CMS listing is only a candidate source; read policy is authoritative."""

    def setUp(self):
        self.user = SimpleNamespace(is_authenticated=True, username='author')
        self.first = CourseLocator('Org', 'Course', 'Run')
        self.second = CourseLocator('Org', 'Other', 'Run')

    @patch('lti_consumer.plugin.compat._has_studio_course_read_access')
    @patch('lti_consumer.plugin.compat._get_studio_course_candidates')
    def test_neutral_request_and_individual_read_policy_filter(self, candidates, can_read):
        candidates.return_value = [
            SimpleNamespace(id=self.first),
            SimpleNamespace(id=self.first),  # deduplicated
            SimpleNamespace(id=self.second),
            SimpleNamespace(id=LibraryLocator(org='Org', library='Library')),
            SimpleNamespace(id=CCXLocator.from_string('ccx-v1:Org+Course+Run+ccx@1')),
            SimpleNamespace(id='not-a-course-key'),
        ]
        can_read.side_effect = lambda user, key: key == self.first

        result = compat.get_studio_accessible_course_keys(self.user)

        self.assertEqual(result, [self.first])
        request = candidates.call_args.args[0]
        self.assertIsInstance(request, HttpRequest)
        self.assertEqual(request.GET, {})
        self.assertIs(request.user, self.user)
        self.assertCountEqual(can_read.call_args_list, [
            call(self.user, self.first),
            call(self.user, self.second),
        ])

    def test_candidate_wrapper_passes_request_and_returns_tuple_first_item(self):
        cms_course_views = ModuleType('cms.djangoapps.contentstore.views.course')
        cms_api = Mock(return_value=(['candidate'], ['actions']))
        cms_course_views.get_courses_accessible_to_user = cms_api
        modules = {
            'cms': ModuleType('cms'),
            'cms.djangoapps': ModuleType('cms.djangoapps'),
            'cms.djangoapps.contentstore': ModuleType('cms.djangoapps.contentstore'),
            'cms.djangoapps.contentstore.views': ModuleType('cms.djangoapps.contentstore.views'),
            'cms.djangoapps.contentstore.views.course': cms_course_views,
        }
        request = HttpRequest()

        with patch.dict('sys.modules', modules):
            # pylint: disable=protected-access
            self.assertEqual(compat._get_studio_course_candidates(request), ['candidate'])
        cms_api.assert_called_once_with(request)

    @patch('lti_consumer.plugin.compat._has_studio_course_read_access')
    @patch('lti_consumer.plugin.compat._get_studio_course_candidates')
    def test_permission_backend_errors_propagate(self, candidates, can_read):
        candidates.return_value = [SimpleNamespace(id=self.first)]
        can_read.side_effect = RuntimeError('permission backend unavailable')

        with self.assertRaisesRegex(RuntimeError, 'permission backend unavailable'):
            compat.get_studio_accessible_course_keys(self.user)

    @patch('lti_consumer.plugin.compat._get_studio_course_candidates')
    def test_unauthenticated_user_returns_empty_and_candidate_errors_propagate(self, candidates):
        self.assertEqual(
            compat.get_studio_accessible_course_keys(SimpleNamespace(is_authenticated=False)), []
        )
        candidates.side_effect = RuntimeError('CMS unavailable')
        with self.assertRaisesRegex(RuntimeError, 'CMS unavailable'):
            compat.get_studio_accessible_course_keys(self.user)

    def test_read_check_uses_platform_authz_with_legacy_read_fallback(self):
        # Platform dependencies are intentionally absent from unit-test runtime;
        # provide the lazy-import modules and assert the supported API contract.
        permission = Mock(return_value=True)
        authz_constants = ModuleType('openedx.core.djangoapps.authz.constants')
        authz_constants.LegacyAuthoringPermission = SimpleNamespace(READ='read')
        authz_decorators = ModuleType('openedx.core.djangoapps.authz.decorators')
        authz_decorators.user_has_course_permission = permission
        permissions = ModuleType('openedx_authz.constants.permissions')
        permissions.COURSES_VIEW_COURSE = SimpleNamespace(identifier='courses.view_course')
        modules = {
            'openedx': ModuleType('openedx'),
            'openedx.core': ModuleType('openedx.core'),
            'openedx.core.djangoapps': ModuleType('openedx.core.djangoapps'),
            'openedx.core.djangoapps.authz': ModuleType('openedx.core.djangoapps.authz'),
            'openedx.core.djangoapps.authz.constants': authz_constants,
            'openedx.core.djangoapps.authz.decorators': authz_decorators,
            'openedx_authz': ModuleType('openedx_authz'),
            'openedx_authz.constants': ModuleType('openedx_authz.constants'),
            'openedx_authz.constants.permissions': permissions,
        }
        with patch.dict('sys.modules', modules):
            # pylint: disable=protected-access
            self.assertTrue(compat._has_studio_course_read_access(self.user, self.first))
        permission.assert_called_once_with(self.user, 'courses.view_course', self.first, 'read')
