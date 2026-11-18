"""Tests for the reusable-configuration Studio catalog compatibility layer.

Each adapter is exercised as a thin seam over a package that is absent here, so the
externally owned modules are injected into sys.modules and nothing in this package is
faked. The adapter also imports on its own in a fresh interpreter with every platform
package refused, so no Django app registry can preload it for the check.
"""
import json
import os
import subprocess
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from ccx_keys.locator import CCXLocator
from django.http import HttpRequest
from django.test import SimpleTestCase
from opaque_keys.edx.locator import CourseLocator, LibraryLocator

import lti_consumer
from lti_consumer.plugin import compat

CMS_MODULE = 'cms.djangoapps.contentstore.views.course'
ROLES_MODULE = 'common.djangoapps.student.roles'

SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(lti_consumer.__file__)))

#: The platform package roots the adapter must never import, a swallowed ImportError included.
PLATFORM_ROOTS = ('cms', 'lms', 'openedx', 'common')

PLATFORM_IMPORT_RECORDER = '''
import sys

ATTEMPTS = []


class _RecordingPlatformImports:
    """Refuse the platform packages, recording every attempt, a swallowed one included."""

    blocked = {blocked}

    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] in self.blocked:
            ATTEMPTS.append(name)
            raise ImportError(f'{name} is not available on a standalone install')
        return None


sys.meta_path.insert(0, _RecordingPlatformImports())
'''.replace('{blocked}', repr(PLATFORM_ROOTS))

LAZY_COMPAT_SCRIPT = PLATFORM_IMPORT_RECORDER + '''
import json

import lti_consumer.plugin.compat as compat

print(json.dumps({
    'attempts': ATTEMPTS,
    'path': compat.__file__,
    'modules': [
        compat.get_studio_accessible_course_keys.__module__,
        compat.user_is_global_staff.__module__,
    ],
}))
'''

RECORDER_SELF_CHECK_SCRIPT = PLATFORM_IMPORT_RECORDER + '''
import json

# A swallowed ImportError still leaves its attempt behind, so this proves the recorder sees it.
for root in _RecordingPlatformImports.blocked:
    try:
        __import__(f'{root}.djangoapps.probe')
    except ImportError:
        pass

print(json.dumps(ATTEMPTS))
'''


class StudioAccessibleCourseKeysAdapterTests(SimpleTestCase):
    """The CMS catalog is authoritative and is consulted without a per-course AuthZ call.

    Accepted risk, documented on PR #715: the platform catalog's AccessListFallback
    branch can list every course, and this adapter re-applies no per-course read check.
    """

    def catalog(self, candidates=None, **kwargs):
        """Return a fake CMS module whose catalog call is recorded."""
        catalog = Mock(return_value=(candidates or [], []), **kwargs)
        cms = ModuleType(CMS_MODULE)
        cms.get_courses_accessible_to_user = catalog
        return cms, catalog

    def test_catalog_is_authoritative_for_distinct_normal_course_keys(self):
        cms, no_access = self.catalog()
        with patch.dict('sys.modules', {CMS_MODULE: cms}):
            self.assertEqual(compat.get_studio_accessible_course_keys(SimpleNamespace(is_authenticated=False)), [])
            # Authenticated but with an empty catalog: nothing is granted either.
            self.assertEqual(
                compat.get_studio_accessible_course_keys(SimpleNamespace(is_authenticated=True)),
                [],
            )
        no_access.assert_called_once()

        first = CourseLocator('Org', 'Course', 'Run')
        second = CourseLocator('Org', 'Other', 'Run')
        user = SimpleNamespace(is_authenticated=True, username='author')
        cms, candidates = self.catalog([
            SimpleNamespace(id=first),
            SimpleNamespace(id=first),
            SimpleNamespace(id=second),
            SimpleNamespace(id=LibraryLocator(org='Org', library='Library')),
            SimpleNamespace(id=CCXLocator.from_string('ccx-v1:Org+Course+Run+ccx@1')),
            SimpleNamespace(id='not-a-course-key'),
        ])
        with patch.dict('sys.modules', {CMS_MODULE: cms}):
            # Deduplicated, sorted and limited to normal course keys: the catalog decides.
            self.assertEqual(compat.get_studio_accessible_course_keys(user), [first, second])

        candidates.assert_called_once()
        request = candidates.call_args.args[0]
        self.assertIsInstance(request, HttpRequest)
        self.assertIs(request.user, user)
        # Caller-controlled GET filters are never forwarded to the catalog method.
        self.assertEqual(request.GET, {})

    def test_platform_failures_surface(self):
        cms, _candidates = self.catalog(side_effect=RuntimeError('CMS unavailable'))
        with patch.dict('sys.modules', {CMS_MODULE: cms}):
            # Never swallowed into a denial or an allow.
            with self.assertRaisesRegex(RuntimeError, 'CMS unavailable'):
                compat.get_studio_accessible_course_keys(SimpleNamespace(is_authenticated=True))


class GlobalStaffCompatTests(SimpleTestCase):
    """The Global Staff seam delegates to the canonical platform role class."""

    def test_delegates_to_the_platform_role_and_keeps_superuser_access(self):
        user = object()
        result = object()
        role = Mock()
        role.has_user.return_value = result
        global_staff = Mock(return_value=role)
        roles = ModuleType(ROLES_MODULE)
        roles.GlobalStaff = global_staff
        with patch.dict('sys.modules', {ROLES_MODULE: roles}):
            self.assertIs(compat.user_is_global_staff(user), result)
        global_staff.assert_called_once_with()
        role.has_user.assert_called_once_with(user)

        # The previous superuser-only authorization must not be narrowed here.
        superuser = SimpleNamespace(is_superuser=True, is_staff=False)
        role = Mock()
        role.has_user.return_value = False
        roles = ModuleType(ROLES_MODULE)
        roles.GlobalStaff = Mock(return_value=role)
        with patch.dict('sys.modules', {ROLES_MODULE: roles}):
            self.assertTrue(compat.user_is_global_staff(superuser))
        role.has_user.assert_not_called()


class OtherPlatformAdaptersTests(SimpleTestCase):
    """The remaining reusable-configuration adapters stay thin platform seams."""

    def test_remaining_seams_delegate_to_canonical_platform_apis(self):
        organizations = ModuleType('organizations.api')
        organizations.get_organizations = Mock(return_value=['org'])
        with patch.dict('sys.modules', {'organizations.api': organizations}):
            self.assertEqual(compat.get_active_organizations(), ['org'])
        organizations.get_organizations.assert_called_once_with()

        user = object()
        course_key = CourseLocator('Org', 'Course', 'Run')
        role = Mock()
        role.has_user.return_value = True
        instructor_role = Mock(return_value=role)
        roles = ModuleType(ROLES_MODULE)
        roles.CourseInstructorRole = instructor_role
        with patch.dict('sys.modules', {ROLES_MODULE: roles}):
            self.assertTrue(compat.user_is_course_admin(user, course_key))
        instructor_role.assert_called_once_with(course_key)
        role.has_user.assert_called_once_with(user)


class LazyPlatformImportTests(SimpleTestCase):
    """The adapter module imports on a standalone install, with no platform package installed."""

    def run_script(self, script):
        """Run one script in a fresh interpreter that prefers this worktree's source."""
        environment = dict(os.environ)
        environment['PYTHONPATH'] = os.pathsep.join(
            [SOURCE_ROOT] + [part for part in os.environ.get('PYTHONPATH', '').split(os.pathsep) if part]
        )
        return subprocess.run(
            [sys.executable, '-c', script],
            capture_output=True,
            text=True,
            env=environment,
            check=False,
            timeout=120,
        )

    def test_compat_imports_without_cms_lms_openedx_or_common(self):
        """Self-check first: the lazy-import assertion cannot pass vacuously."""
        recorder = self.run_script(RECORDER_SELF_CHECK_SCRIPT)
        self.assertEqual(recorder.returncode, 0, recorder.stderr)
        self.assertEqual(json.loads(recorder.stdout), list(PLATFORM_ROOTS))

        completed = self.run_script(LAZY_COMPAT_SCRIPT)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report['attempts'], [])
        # The real module was imported, not a shadow copy from the installed package.
        self.assertTrue(report['path'].startswith(SOURCE_ROOT + os.sep), report['path'])
        self.assertEqual(report['modules'], ['lti_consumer.plugin.compat', 'lti_consumer.plugin.compat'])
