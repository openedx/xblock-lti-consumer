"""Direct tests for the reusable Creation Context policy.

One journey per user-visible outcome: normalization, create/assignment authority,
manage authority, ineligible refusal, visibility, and standalone import. Every
denied actor/context combination is preserved -- they are merged into shared
matrices rather than reduced. Only the platform seam is faked; the policy and the
queryset are real, and the visibility journeys run against the real database.
"""

import json
import os
import subprocess
import sys
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from django.db import connection
from django.db.models import QuerySet
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils.translation import gettext_lazy
from opaque_keys.edx.keys import CourseKey

import lti_consumer
from lti_consumer.exceptions import ReusableConfigurationError
from lti_consumer.models import ReusableLtiConfiguration
from lti_consumer.reusable_context import CreationContext, CreationContextPolicy

COURSE_KEY = 'course-v1:Org+Course+Run'
OTHER_KEY = 'course-v1:Other+Course+Run'
CCX_KEY = 'ccx-v1:Org+Course+Run+ccx@1'
REGISTRY_PATCH = 'lti_consumer.plugin.compat.get_active_organizations'
COURSE_ACCESS_PATCH = 'lti_consumer.plugin.compat.get_studio_accessible_course_keys'
COURSE_ADMIN_PATCH = 'lti_consumer.plugin.compat.user_is_course_admin'
GLOBAL_STAFF_PATCH = 'lti_consumer.plugin.compat.user_is_global_staff'

#: Every platform fact the policy may read; an ineligible actor must reach none of them.
PLATFORM_PATCHES = (GLOBAL_STAFF_PATCH, REGISTRY_PATCH, COURSE_ADMIN_PATCH, COURSE_ACCESS_PATCH)
INELIGIBLE_MESSAGE = 'must not be read for an ineligible actor'

SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(lti_consumer.__file__)))

PLATFORM_IMPORT_RECORDER = '''
import sys

ATTEMPTS = []


class _RecordingPlatformImports:
    """Refuse the platform applications, recording every attempt to import one."""

    blocked = ('cms', 'lms')

    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] in self.blocked:
            ATTEMPTS.append(name)
            raise ImportError(f'{name} is not available on a standalone install')
        return None


sys.meta_path.insert(0, _RecordingPlatformImports())
'''

LAZY_IMPORT_SCRIPT = PLATFORM_IMPORT_RECORDER + '''
from django.conf import settings

settings.configure(
    INSTALLED_APPS=['django.contrib.contenttypes', 'django.contrib.auth', 'lti_consumer'],
    DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
    USE_TZ=True,
)

import django

django.setup()

# Only the import of the modules under test counts: the app registry may load its own seams.
del ATTEMPTS[:]

import lti_consumer.reusable
import lti_consumer.reusable_context

import json

print(json.dumps({
    'attempts': ATTEMPTS,
    'paths': [lti_consumer.reusable.__file__, lti_consumer.reusable_context.__file__],
}))
'''

RECORDER_SELF_CHECK_SCRIPT = PLATFORM_IMPORT_RECORDER + '''
import json

try:
    import cms.djangoapps.contentstore
except ImportError:
    pass

print(json.dumps(ATTEMPTS))
'''


def actor(is_superuser=False, is_staff=False, is_authenticated=True, is_active=True):
    """Return a minimal actor with the flags the policy reads."""
    return SimpleNamespace(
        is_authenticated=is_authenticated,
        is_active=is_active,
        is_superuser=is_superuser,
        is_staff=is_staff,
    )


def global_staff_actors():
    """Return a non-superuser Global Staff actor and a superuser, for subTest coverage."""
    return (('global staff', actor(is_staff=True)), ('superuser', actor(is_superuser=True)))


def denied_actors():
    """Return actors that are not both authenticated and active, including staff look-alikes."""
    return (
        ('inactive', actor(is_active=False)),
        ('inactive global staff', actor(is_staff=True, is_active=False)),
        ('inactive superuser', actor(is_superuser=True, is_active=False)),
        ('anonymous but active', actor(is_authenticated=False, is_active=True)),
        ('anonymous', actor(is_authenticated=False, is_active=False)),
        ('flags absent', SimpleNamespace()),
    )


INELIGIBLE_CONTEXTS = (
    None,
    [],
    {},
    {'type': 'library', 'key': 'lib'},
    {'type': 'site', 'key': 'anything'},
    {'type': 'site'},
    {'type': 'organization', 'key': 'org'},
    {'type': 'organization', 'key': '   '},
    {'type': 'course', 'key': 'not-a-course'},
    {'type': 'course', 'key': COURSE_KEY},
    {'type': 'course', 'key': CCX_KEY},
    {'type': 'course'},
)

INELIGIBLE_CONFIGURATIONS = (
    ('course', COURSE_KEY),
    ('course', CCX_KEY),
    ('course', OTHER_KEY),
    ('course', ''),
    ('organization', 'org'),
    ('site', ''),
    (None, None),
    (None, COURSE_KEY),
    ('library', 'lib'),
)


class GlobalStaffPatchMixin:
    """Patch the platform role seam; the canonical helper is covered by compat tests."""

    def setUp(self):
        super().setUp()
        patcher = patch(
            GLOBAL_STAFF_PATCH,
            side_effect=lambda user: bool(user and (user.is_superuser or user.is_staff)),
        )
        patcher.start()
        self.addCleanup(patcher.stop)


class NoPlatformFactsMixin:
    """Fail loudly if any platform fact is read while the block runs."""

    @contextmanager
    def no_platform_facts(self):
        """Patch every platform seam and assert none of them is reached."""
        with ExitStack() as stack:
            seams = {target: stack.enter_context(patch(target)) for target in PLATFORM_PATCHES}
            for target, seam in seams.items():
                seam.side_effect = AssertionError(f'{target} {INELIGIBLE_MESSAGE}')
            yield
            for target, seam in seams.items():
                self.assertFalse(seam.called, f'{target} {INELIGIBLE_MESSAGE}')


def organization(short_name):
    return {'short_name': short_name}


class ReusableConfigurationErrorTests(SimpleTestCase):
    """The shared error seam other modules construct and adapters translate."""

    def test_category_field_and_messages_are_normalized(self):
        error = ReusableConfigurationError('conflict', 'Already exists', field='name')
        self.assertEqual(error.category, 'conflict')
        self.assertEqual(error.field, 'name')
        self.assertEqual(error.messages, ['Already exists'])
        self.assertIsInstance(error.messages, list)
        self.assertIsInstance(error.messages[0], str)

        sequence = ReusableConfigurationError('invalid', ('one', 'two'))
        self.assertEqual(sequence.messages, ['one', 'two'])
        self.assertIsNone(sequence.field)

        lazy = ReusableConfigurationError('invalid', gettext_lazy('Translated'))
        self.assertEqual(lazy.messages, ['Translated'])
        self.assertIsInstance(lazy.messages[0], str)


class CreationContextShapeTests(GlobalStaffPatchMixin, SimpleTestCase):
    """Context shape and normalization, before any authority decision."""

    REGISTRY = [organization('MyOrg')]

    def authorize(self, raw_context, user=None, registry=None):
        with patch(REGISTRY_PATCH, return_value=self.REGISTRY if registry is None else registry):
            return CreationContextPolicy(user or actor(is_staff=True)).authorize_creation(raw_context)

    def test_invalid_shapes_are_addressed_to_context_members(self):
        invalid = (
            (None, 'context'),
            ({}, 'context.type'),
            ({'type': 'library', 'key': 'lib'}, 'context.type'),
            ({'type': 'site', 'key': 'anything'}, 'context.key'),
            ({'type': 'site', 'extra': 'member'}, 'context'),
            ({'type': 'site', 'scope': {'course_keys': [COURSE_KEY]}}, 'context'),
            ({'type': 'course'}, 'context.key'),
            ({'type': 'course', 'key': '   '}, 'context.key'),
            ({'type': 'course', 'key': 'not-a-course'}, 'context.key'),
            ({'type': 'course', 'key': 'course-v1:Version@1234'}, 'context.key'),
            ({'type': 'course', 'key': 'library-v1:Org+Library'}, 'context.key'),
            ({'type': 'organization'}, 'context.key'),
            ({'type': 'organization', 'key': 'o' * 256}, 'context.key'),
            ({'type': 'course', 'key': f'course-v1:{"O" * 250}+Course+Run'}, 'context.key'),
            ([{'type': 'site'}], 'context'),
        )
        for raw_context, field in invalid:
            with self.subTest(raw_context=raw_context):
                with self.assertRaises(ReusableConfigurationError) as caught:
                    self.authorize(raw_context)
                self.assertEqual(caught.exception.category, 'invalid')
                self.assertEqual(caught.exception.field, field)

        # Shape is settled before authority: an ordinary actor is refused for shape alone.
        policy = CreationContextPolicy(actor())
        with patch(REGISTRY_PATCH) as registry, patch(COURSE_ADMIN_PATCH) as course_admin:
            with self.assertRaises(ReusableConfigurationError) as caught:
                policy.authorize_creation({'type': 'organization', 'key': '   '})
        self.assertEqual(caught.exception.category, 'invalid')
        registry.assert_not_called()
        course_admin.assert_not_called()

    def test_valid_contexts_are_canonicalized(self):
        self.assertEqual(
            self.authorize({'type': 'course', 'key': f'  {COURSE_KEY}+branch@draft  '}),
            CreationContext(type='course', key=COURSE_KEY),
        )
        self.assertEqual(
            self.authorize({'type': 'course', 'key': CCX_KEY}),
            CreationContext(type='course', key=CCX_KEY),
        )
        self.assertEqual(
            self.authorize({'type': 'organization', 'key': '  MYORG  '}),
            CreationContext(type='organization', key='myorg'),
        )
        site = self.authorize({'type': 'site'})
        self.assertEqual(site, CreationContext(type='site'))
        self.assertEqual(site.key, '')


class CreationContextAuthorityTests(GlobalStaffPatchMixin, SimpleTestCase):
    """Authority decides before the organization registry is read."""

    def test_non_staff_contexts_are_forbidden_before_any_platform_read(self):
        for label, raw_context in (
            ('organization', {'type': 'organization', 'key': 'Org'}),
            ('site', {'type': 'site'}),
        ):
            with self.subTest(context=label):
                with patch(REGISTRY_PATCH) as registry:
                    with self.assertRaises(ReusableConfigurationError) as caught:
                        CreationContextPolicy(actor()).authorize_creation(raw_context)
                self.assertEqual(caught.exception.category, 'forbidden')
                registry.assert_not_called()

        policy = CreationContextPolicy(actor(is_authenticated=False))
        with patch(COURSE_ADMIN_PATCH) as course_admin, patch(REGISTRY_PATCH) as registry:
            for raw_context in (
                {'type': 'course', 'key': COURSE_KEY},
                {'type': 'organization', 'key': 'org'},
                {'type': 'site'},
            ):
                with self.subTest(anonymous_context=raw_context.get('type')):
                    with self.assertRaises(ReusableConfigurationError) as caught:
                        policy.authorize_creation(raw_context)
                    self.assertEqual(caught.exception.category, 'forbidden')
        course_admin.assert_not_called()
        registry.assert_not_called()

    def test_course_create_requires_course_admin_unless_global_staff(self):
        user = actor()
        with patch(COURSE_ADMIN_PATCH, return_value=False) as course_admin, patch(REGISTRY_PATCH) as registry:
            with self.assertRaises(ReusableConfigurationError) as caught:
                CreationContextPolicy(user).authorize_creation({'type': 'course', 'key': COURSE_KEY})
        self.assertEqual(caught.exception.category, 'forbidden')
        # The role is asked about the canonical key, never the raw member.
        course_admin.assert_called_once_with(user, CourseKey.from_string(COURSE_KEY))
        registry.assert_not_called()

        with patch(COURSE_ADMIN_PATCH) as course_admin:
            with self.assertRaises(ReusableConfigurationError) as caught:
                CreationContextPolicy(actor()).authorize_creation({'type': 'course', 'key': CCX_KEY})
        self.assertEqual(caught.exception.category, 'forbidden')
        course_admin.assert_not_called()

        for label, staff_user in global_staff_actors():
            with self.subTest(actor=label):
                with patch(COURSE_ADMIN_PATCH) as course_admin:
                    policy = CreationContextPolicy(staff_user)
                    self.assertEqual(
                        policy.authorize_creation({'type': 'course', 'key': COURSE_KEY}),
                        CreationContext(type='course', key=COURSE_KEY),
                    )
                    self.assertEqual(
                        policy.authorize_creation({'type': 'course', 'key': CCX_KEY}),
                        CreationContext(type='course', key=CCX_KEY),
                    )
                course_admin.assert_not_called()

    def test_organization_create_requires_global_staff_and_a_unique_active_entry(self):
        for label, user in global_staff_actors():
            with self.subTest(actor=label):
                with patch(REGISTRY_PATCH, return_value=[organization('Org')]):
                    policy = CreationContextPolicy(user)
                    self.assertEqual(
                        policy.authorize_creation({'type': 'organization', 'key': '  ORG  '}),
                        CreationContext(type='organization', key='org'),
                    )
                    self.assertEqual(policy.authorize_creation({'type': 'site'}), CreationContext(type='site'))

        for registry in ([organization('Other')], [organization('Org'), organization('ORG')]):
            with self.subTest(registry=registry):
                with patch(REGISTRY_PATCH, return_value=registry):
                    with self.assertRaises(ReusableConfigurationError) as caught:
                        CreationContextPolicy(actor(is_staff=True)).authorize_creation(
                            {'type': 'organization', 'key': 'org'}
                        )
                self.assertEqual(caught.exception.category, 'invalid')
                self.assertEqual(caught.exception.field, 'context.key')


class CreationContextManageTests(GlobalStaffPatchMixin, SimpleTestCase):
    """can_manage semantics and registry independence."""

    @staticmethod
    def configuration(context_type='course', context_key=COURSE_KEY):
        return SimpleNamespace(context_type=context_type, context_key=context_key)

    def test_course_manage_requires_course_admin_unless_global_staff(self):
        user = actor()
        with patch(
            COURSE_ADMIN_PATCH, side_effect=lambda user_, key: key == CourseKey.from_string(COURSE_KEY),
        ) as course_admin:
            policy = CreationContextPolicy(user)
            self.assertTrue(policy.can_manage(self.configuration(context_key=COURSE_KEY)))
            self.assertFalse(policy.can_manage(self.configuration(context_key=OTHER_KEY)))
        self.assertTrue(course_admin.called)

        with patch(COURSE_ADMIN_PATCH) as course_admin:
            policy = CreationContextPolicy(actor())
            self.assertFalse(policy.can_manage(self.configuration(context_key='')))
            self.assertFalse(policy.can_manage(self.configuration(context_key='not-a-course')))
            self.assertFalse(policy.can_manage(self.configuration(context_key=CCX_KEY)))
        course_admin.assert_not_called()

        for label, staff_user in global_staff_actors():
            with self.subTest(actor=label):
                with patch(COURSE_ADMIN_PATCH) as course_admin:
                    policy = CreationContextPolicy(staff_user)
                    self.assertTrue(policy.can_manage(self.configuration(context_key=COURSE_KEY)))
                    self.assertTrue(policy.can_manage(self.configuration(context_key=CCX_KEY)))
                course_admin.assert_not_called()

    def test_non_course_manage_is_global_staff_only_and_keeps_the_stored_context(self):
        with patch(REGISTRY_PATCH) as registry, patch(COURSE_ADMIN_PATCH) as course_admin:
            for label, staff_user in global_staff_actors():
                policy = CreationContextPolicy(staff_user)
                with self.subTest(actor=label):
                    self.assertTrue(policy.can_manage(self.configuration('organization', 'org')))
                    self.assertTrue(policy.can_manage(self.configuration('site', '')))
                    # A converted row with no context waits for a Global Staff first assignment.
                    self.assertTrue(policy.can_manage(self.configuration(None, None)))
            user_policy = CreationContextPolicy(actor())
            self.assertFalse(user_policy.can_manage(self.configuration('organization', 'org')))
            self.assertFalse(user_policy.can_manage(self.configuration('site', '')))
            self.assertFalse(user_policy.can_manage(self.configuration('library', 'lib')))
            self.assertFalse(user_policy.can_manage(self.configuration(None, None)))
        registry.assert_not_called()
        # No role lookup exists for organization, site, unknown-type or unassigned rows.
        course_admin.assert_not_called()

        # A persisted organization is taken as stored: no registry, even after inactivation.
        policy = CreationContextPolicy(actor(is_staff=True))
        with patch(REGISTRY_PATCH, side_effect=AssertionError('registry must not be read')):
            self.assertTrue(policy.can_manage(self.configuration('organization', 'long-gone-org')))

    def test_assignment_requires_global_staff_and_normalizes_the_context(self):
        """Only Global Staff may assign, and the assigned context is canonical."""
        with patch(COURSE_ADMIN_PATCH) as course_admin:
            with self.assertRaises(ReusableConfigurationError) as caught:
                CreationContextPolicy(actor()).authorize_assignment({'type': 'course', 'key': COURSE_KEY})
        self.assertEqual(caught.exception.category, 'forbidden')
        course_admin.assert_not_called()

        for label, user in global_staff_actors():
            with self.subTest(actor=label):
                context = CreationContextPolicy(user).authorize_assignment({'type': 'course', 'key': COURSE_KEY})
                self.assertEqual(context, CreationContext(type='course', key=COURSE_KEY))

        with patch(REGISTRY_PATCH, return_value=[organization('Org')]):
            self.assertEqual(
                CreationContextPolicy(actor(is_staff=True)).authorize_assignment(
                    {'type': 'organization', 'key': ' ORG '},
                ),
                CreationContext(type='organization', key='org'),
            )


class CreationContextPolicyCacheTests(GlobalStaffPatchMixin, TestCase):
    """Lookups are cached per policy instance, so one request reads each fact once."""

    def test_platform_lookups_are_cached_per_policy_instance(self):
        user = actor()
        with patch(COURSE_ADMIN_PATCH, return_value=True) as course_admin:
            policy = CreationContextPolicy(user)
            course = SimpleNamespace(context_type='course', context_key=COURSE_KEY)
            self.assertTrue(policy.can_manage(course))
            # A branch-qualified copy of the same course is the same cache entry.
            self.assertTrue(policy.can_manage(
                SimpleNamespace(context_type='course', context_key=f'{COURSE_KEY}+branch@draft'),
            ))
            course_admin.assert_called_once_with(user, CourseKey.from_string(COURSE_KEY))
            CreationContextPolicy(user).can_manage(course)
            self.assertEqual(course_admin.call_count, 2)

        with patch(COURSE_ACCESS_PATCH, return_value=[CourseKey.from_string(COURSE_KEY)]) as course_access:
            policy = CreationContextPolicy(actor())
            policy.visible_configurations()
            policy.visible_configurations()
            course_access.assert_called_once()
            CreationContextPolicy(actor()).visible_configurations()
            self.assertEqual(course_access.call_count, 2)


class IneligibleActorTests(NoPlatformFactsMixin, GlobalStaffPatchMixin, SimpleTestCase):
    """An account that is not both authenticated and active reads no platform fact."""

    def test_ineligible_actors_are_forbidden_before_any_shape_or_platform_read(self):
        for label, user in denied_actors():
            for raw_context in INELIGIBLE_CONTEXTS:
                with self.subTest(actor=label, raw_context=raw_context), self.no_platform_facts():
                    with self.assertRaises(ReusableConfigurationError) as caught:
                        CreationContextPolicy(user).authorize_creation(raw_context)
                    self.assertEqual(caught.exception.category, 'forbidden')
                    self.assertIsNone(caught.exception.field)

                with self.subTest(actor=label, raw_context=raw_context, call='assignment'), \
                        self.no_platform_facts():
                    with self.assertRaises(ReusableConfigurationError) as caught:
                        CreationContextPolicy(user).authorize_assignment(raw_context)
                    self.assertEqual(caught.exception.category, 'forbidden')
                    self.assertIsNone(caught.exception.field)

    def test_ineligible_actors_cannot_manage_and_staff_flags_do_not_outrank(self):
        for label, user in denied_actors():
            for context_type, context_key in INELIGIBLE_CONFIGURATIONS:
                with self.subTest(actor=label, context_type=context_type), self.no_platform_facts():
                    configuration = SimpleNamespace(context_type=context_type, context_key=context_key)
                    self.assertFalse(CreationContextPolicy(user).can_manage(configuration))

            with self.subTest(actor=label, call='manage_site'):
                policy = CreationContextPolicy(user)
                with self.no_platform_facts():
                    self.assertFalse(policy.can_manage(SimpleNamespace(context_type='site', context_key='')))
                    self.assertFalse(policy.can_manage(SimpleNamespace(context_type=None, context_key=None)))
                    with self.assertRaises(ReusableConfigurationError) as caught:
                        policy.authorize_assignment({'type': 'site'})
                self.assertEqual(caught.exception.category, 'forbidden')

        # Eligibility fails closed: an absent account flag keeps no authority.
        subject = SimpleNamespace(is_authenticated=True, is_superuser=True, is_staff=True)
        policy = CreationContextPolicy(subject)
        with self.no_platform_facts():
            with self.assertRaises(ReusableConfigurationError) as caught:
                policy.authorize_creation({'type': 'site'})
            self.assertFalse(policy.can_manage(SimpleNamespace(context_type='site', context_key='')))
        self.assertEqual(caught.exception.category, 'forbidden')


class CreationContextPolicyVisibilityTests(GlobalStaffPatchMixin, TestCase):
    """Query-backed visibility: exact course, matching organization, site and denial."""

    def make_configuration(self, name, context_type='course', context_key=COURSE_KEY, version='lti_1p1'):
        return ReusableLtiConfiguration.objects.create(
            name=name,
            version=version,
            context_type=context_type,
            context_key=context_key,
        )

    def policy_with_courses(self, course_keys):
        patcher = patch(COURSE_ACCESS_PATCH, return_value=course_keys)
        patcher.start()
        self.addCleanup(patcher.stop)
        return CreationContextPolicy(actor())

    @staticmethod
    def visible_names(policy, **kwargs):
        return set(policy.visible_configurations(**kwargs).values_list('name', flat=True))

    def test_global_staff_sees_everything_and_course_filter_narrows_to_course_and_site(self):
        self.make_configuration('Selected')
        self.make_configuration('Other', context_key=OTHER_KEY)
        self.make_configuration('Organization', context_type='organization', context_key='org')
        self.make_configuration('Site', context_type='site', context_key='')
        for label, user in global_staff_actors():
            policy = CreationContextPolicy(user)
            with self.subTest(actor=label):
                self.assertEqual(self.visible_names(policy), {'Selected', 'Other', 'Organization', 'Site'})
                self.assertEqual(self.visible_names(policy, course_key=OTHER_KEY), {'Other', 'Site'})

    def test_actor_visibility_is_exact_course_matching_organization_and_site(self):
        self.make_configuration('Selected')
        self.make_configuration('Other', context_key=OTHER_KEY)
        self.make_configuration('Matching organization', context_type='organization', context_key='org')
        self.make_configuration('Other organization', context_type='organization', context_key='otherorg')
        self.make_configuration('Site', context_type='site', context_key='')
        self.make_configuration('CCX', context_key=CCX_KEY)
        # A copied row's stale raw key grants nothing until a Global Staff assignment.
        self.make_configuration('Copied', context_type=None, context_key=COURSE_KEY, version=None)

        policy = self.policy_with_courses([CourseKey.from_string(COURSE_KEY)])
        self.assertEqual(self.visible_names(policy), {'Selected', 'Matching organization', 'Site'})
        # A valid key the actor cannot reach yields nothing at all.
        self.assertEqual(self.visible_names(policy, course_key=OTHER_KEY), set())
        self.assertEqual(
            self.visible_names(policy, course_key=COURSE_KEY),
            {'Selected', 'Matching organization', 'Site'},
        )

        for label, user in global_staff_actors():
            with self.subTest(actor=label):
                self.assertEqual(
                    self.visible_names(CreationContextPolicy(user)),
                    {'Selected', 'Other', 'Matching organization', 'Other organization', 'Site', 'CCX', 'Copied'},
                )

    def test_no_accessible_courses_hides_site_contexts_too(self):
        self.make_configuration('Site', context_type='site', context_key='')
        self.assertEqual(self.visible_names(self.policy_with_courses([])), set())

    def test_membership_is_filtered_by_the_database(self):
        """The context predicates run in SQL, so a large table is never read whole."""
        self.make_configuration('Selected')
        self.make_configuration('Other', context_key=OTHER_KEY)
        self.make_configuration('Organization', context_type='organization', context_key='org')
        self.make_configuration('Site', context_type='site', context_key='')
        policy = self.policy_with_courses([CourseKey.from_string(COURSE_KEY)])

        with CaptureQueriesContext(connection) as built:
            queryset = policy.visible_configurations()
        self.assertIsInstance(queryset, QuerySet)
        self.assertEqual(len(built.captured_queries), 0, 'building the queryset must not query')

        with CaptureQueriesContext(connection) as captured:
            names = set(queryset.values_list('name', flat=True))
        self.assertEqual(names, {'Selected', 'Organization', 'Site'})
        self.assertEqual(len(captured.captured_queries), 1)
        sql = captured.captured_queries[0]['sql']
        # One predicate per context branch: site, course-in-catalog and organization-of-catalog.
        self.assertEqual(sql.count('context_type'), 3, sql)

    def test_malformed_requested_course_key_is_an_addressed_invalid_error(self):
        policy = CreationContextPolicy(actor(is_staff=True))
        for course_key in ('not-a-course', 'course-v1:Version@1234', 'library-v1:Org+Library'):
            with self.subTest(course_key=course_key):
                with self.assertRaises(ReusableConfigurationError) as caught:
                    policy.visible_configurations(course_key=course_key)
                self.assertEqual(caught.exception.category, 'invalid')
                self.assertEqual(caught.exception.field, 'course_key')
                self.assertIsInstance(caught.exception.messages, list)

    def test_malformed_platform_keys_are_skipped_or_fail_closed(self):
        self.make_configuration('Selected')
        self.make_configuration('Other', context_key=OTHER_KEY)
        # A malformed entry is skipped and the valid keys still apply.
        policy = self.policy_with_courses(['not-a-course', CourseKey.from_string(COURSE_KEY)])
        self.assertEqual(self.visible_names(policy), {'Selected'})
        # An all-malformed catalog fails closed rather than opening up, site rows included.
        self.make_configuration('Site', context_type='site', context_key='')
        self.assertEqual(self.visible_names(self.policy_with_courses(['not-a-course'])), set())


class IneligibleActorVisibilityTests(NoPlatformFactsMixin, GlobalStaffPatchMixin, TestCase):
    """An ineligible actor lists nothing, before any platform or course-key read."""

    def make_configuration(self, name, context_type='course', context_key=COURSE_KEY):
        """Create one row directly, bypassing the mutation module."""
        return ReusableLtiConfiguration.objects.create(
            name=name,
            version=ReusableLtiConfiguration.LTI_1P1,
            context_type=context_type,
            context_key=context_key,
        )

    def make_every_context(self):
        """Create a row in every context shape an ineligible actor might reach."""
        self.make_configuration('Selected')
        self.make_configuration('Other', context_key=OTHER_KEY)
        self.make_configuration('Organization', context_type='organization', context_key='org')
        self.make_configuration('Site', context_type='site', context_key='')
        self.make_configuration('Copied', context_type=None, context_key=COURSE_KEY)

    def test_ineligible_actors_list_nothing_before_any_platform_read(self):
        self.make_every_context()
        filters = (None, COURSE_KEY, OTHER_KEY, CCX_KEY, 'not-a-course', CourseKey.from_string(COURSE_KEY))
        for label, user in denied_actors():
            for course_key in filters:
                with self.subTest(actor=label, course_key=course_key), self.no_platform_facts():
                    queryset = CreationContextPolicy(user).visible_configurations(course_key=course_key)
                    self.assertIsInstance(queryset, QuerySet)
                    self.assertEqual(queryset.count(), 0)


class LazyPlatformImportTests(SimpleTestCase):
    """The policy and the mutation module import on a standalone install."""

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

    def test_recorder_guards_and_modules_import_without_cms_or_lms(self):
        """Self-check first: the lazy-import assertion cannot pass vacuously."""
        recorder = self.run_script(RECORDER_SELF_CHECK_SCRIPT)
        self.assertEqual(recorder.returncode, 0, recorder.stderr)
        self.assertEqual(json.loads(recorder.stdout), ['cms'])

        completed = self.run_script(LAZY_IMPORT_SCRIPT)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report['attempts'], [])
        # The real modules were imported, not a shadow copy from the installed package.
        self.assertEqual(len(report['paths']), 2)
        for path in report['paths']:
            self.assertTrue(path.startswith(SOURCE_ROOT + os.sep), path)
