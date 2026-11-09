"""Direct tests for the reusable Creation Context policy."""

import json
import os
import subprocess
import sys
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from django.db.models import QuerySet
from django.test import SimpleTestCase, TestCase
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

    def test_normalizes_messages_to_a_list_of_strings(self):
        error = ReusableConfigurationError('conflict', 'Already exists', field='name')
        self.assertEqual(error.category, 'conflict')
        self.assertEqual(error.field, 'name')
        self.assertEqual(error.messages, ['Already exists'])
        self.assertIsInstance(error.messages, list)
        self.assertIsInstance(error.messages[0], str)

    def test_accepts_a_sequence_of_messages_and_defaults_the_field(self):
        error = ReusableConfigurationError('invalid', ('one', 'two'))
        self.assertEqual(error.messages, ['one', 'two'])
        self.assertIsNone(error.field)

    def test_coerces_a_lazy_single_message(self):
        error = ReusableConfigurationError('invalid', gettext_lazy('Translated'))
        self.assertEqual(error.messages, ['Translated'])
        self.assertIsInstance(error.messages[0], str)


class CreationContextNormalizationTests(GlobalStaffPatchMixin, SimpleTestCase):
    """Creation context shape and normalization before any authority check."""

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

    def test_course_context_is_canonicalized(self):
        self.assertEqual(
            self.authorize({'type': 'course', 'key': f'  {COURSE_KEY}+branch@draft  '}),
            CreationContext(type='course', key=COURSE_KEY),
        )

    def test_ccx_course_context_is_accepted_for_global_staff(self):
        self.assertEqual(
            self.authorize({'type': 'course', 'key': CCX_KEY}),
            CreationContext(type='course', key=CCX_KEY),
        )

    def test_organization_context_is_trimmed_and_lowercased(self):
        self.assertEqual(
            self.authorize({'type': 'organization', 'key': '  MYORG  '}),
            CreationContext(type='organization', key='myorg'),
        )

    def test_site_context_has_a_blank_key(self):
        context = self.authorize({'type': 'site'})
        self.assertEqual(context, CreationContext(type='site'))
        self.assertEqual(context.key, '')

    def test_invalid_input_is_refused_before_authority(self):
        policy = CreationContextPolicy(actor())
        with patch(REGISTRY_PATCH) as registry, patch(COURSE_ADMIN_PATCH) as course_admin:
            with self.assertRaises(ReusableConfigurationError) as caught:
                policy.authorize_creation({'type': 'organization', 'key': '   '})
        self.assertEqual(caught.exception.category, 'invalid')
        registry.assert_not_called()
        course_admin.assert_not_called()


class CreationContextAuthorityTests(GlobalStaffPatchMixin, SimpleTestCase):
    """Authority decides before the organization registry is read."""

    def test_non_global_staff_organization_is_forbidden_without_registry_read(self):
        with patch(REGISTRY_PATCH) as registry:
            with self.assertRaises(ReusableConfigurationError) as caught:
                CreationContextPolicy(actor()).authorize_creation({'type': 'organization', 'key': 'Org'})
        self.assertEqual(caught.exception.category, 'forbidden')
        registry.assert_not_called()

    def test_non_global_staff_site_context_is_forbidden_without_registry_read(self):
        with patch(REGISTRY_PATCH) as registry:
            with self.assertRaises(ReusableConfigurationError) as caught:
                CreationContextPolicy(actor()).authorize_creation({'type': 'site'})
        self.assertEqual(caught.exception.category, 'forbidden')
        registry.assert_not_called()

    def test_authorized_unknown_or_ambiguous_organization_is_invalid(self):
        for registry in ([organization('Other')], [organization('Org'), organization('ORG')]):
            with self.subTest(registry=registry):
                with patch(REGISTRY_PATCH, return_value=registry):
                    with self.assertRaises(ReusableConfigurationError) as caught:
                        CreationContextPolicy(actor(is_staff=True)).authorize_creation(
                            {'type': 'organization', 'key': 'org'}
                        )
                self.assertEqual(caught.exception.category, 'invalid')
                self.assertEqual(caught.exception.field, 'context.key')

    def test_global_staff_and_superuser_create_organization_and_site_contexts(self):
        for label, user in global_staff_actors():
            with self.subTest(actor=label):
                with patch(REGISTRY_PATCH, return_value=[organization('Org')]):
                    policy = CreationContextPolicy(user)
                    self.assertEqual(
                        policy.authorize_creation({'type': 'organization', 'key': '  ORG  '}),
                        CreationContext(type='organization', key='org'),
                    )
                    self.assertEqual(policy.authorize_creation({'type': 'site'}), CreationContext(type='site'))

    def test_course_context_requires_the_course_admin_role(self):
        user = actor()
        with patch(COURSE_ADMIN_PATCH, return_value=False) as course_admin, patch(REGISTRY_PATCH) as registry:
            with self.assertRaises(ReusableConfigurationError) as caught:
                CreationContextPolicy(user).authorize_creation({'type': 'course', 'key': COURSE_KEY})
        self.assertEqual(caught.exception.category, 'forbidden')
        course_admin.assert_called_once_with(user, CourseKey.from_string(COURSE_KEY))
        registry.assert_not_called()

    def test_ccx_context_is_denied_for_non_global_staff_before_any_role_lookup(self):
        with patch(COURSE_ADMIN_PATCH) as course_admin:
            with self.assertRaises(ReusableConfigurationError) as caught:
                CreationContextPolicy(actor()).authorize_creation({'type': 'course', 'key': CCX_KEY})
        self.assertEqual(caught.exception.category, 'forbidden')
        course_admin.assert_not_called()

    def test_global_staff_and_superuser_course_context_skip_the_role_lookup(self):
        for label, user in global_staff_actors():
            with self.subTest(actor=label):
                with patch(COURSE_ADMIN_PATCH) as course_admin:
                    context = CreationContextPolicy(user).authorize_creation({'type': 'course', 'key': COURSE_KEY})
                self.assertEqual(context, CreationContext(type='course', key=COURSE_KEY))
                course_admin.assert_not_called()

    def test_anonymous_actor_reads_no_platform_facts(self):
        policy = CreationContextPolicy(actor(is_authenticated=False))
        with patch(COURSE_ADMIN_PATCH) as course_admin, patch(REGISTRY_PATCH) as registry:
            for raw_context in (
                {'type': 'course', 'key': COURSE_KEY},
                {'type': 'organization', 'key': 'org'},
                {'type': 'site'},
            ):
                with self.subTest(raw_context=raw_context):
                    with self.assertRaises(ReusableConfigurationError) as caught:
                        policy.authorize_creation(raw_context)
                    self.assertEqual(caught.exception.category, 'forbidden')
        course_admin.assert_not_called()
        registry.assert_not_called()


class CreationContextPolicyManageTests(GlobalStaffPatchMixin, SimpleTestCase):
    """can_manage semantics, per-instance caching and registry independence."""

    @staticmethod
    def configuration(context_type='course', context_key=COURSE_KEY):
        return SimpleNamespace(context_type=context_type, context_key=context_key)

    def test_course_admin_lookup_is_cached_per_instance(self):
        user = actor()
        with patch(COURSE_ADMIN_PATCH, return_value=True) as course_admin:
            policy = CreationContextPolicy(user)
            self.assertTrue(policy.can_manage(self.configuration()))
            self.assertTrue(policy.can_manage(self.configuration(context_key=f'{COURSE_KEY}+branch@draft')))
            course_admin.assert_called_once_with(user, CourseKey.from_string(COURSE_KEY))
            CreationContextPolicy(user).can_manage(self.configuration())
            self.assertEqual(course_admin.call_count, 2)

    def test_organization_and_site_contexts_are_global_staff_only(self):
        with patch(REGISTRY_PATCH) as registry:
            for label, user in global_staff_actors():
                policy = CreationContextPolicy(user)
                with self.subTest(actor=label):
                    self.assertTrue(policy.can_manage(self.configuration('organization', 'org')))
                    self.assertTrue(policy.can_manage(self.configuration('site', '')))
            user_policy = CreationContextPolicy(actor())
            self.assertFalse(user_policy.can_manage(self.configuration('organization', 'org')))
            self.assertFalse(user_policy.can_manage(self.configuration('site', '')))
        registry.assert_not_called()

    def test_persisted_organization_is_not_revalidated(self):
        policy = CreationContextPolicy(actor(is_staff=True))
        with patch(REGISTRY_PATCH, side_effect=AssertionError('registry must not be read')):
            self.assertTrue(policy.can_manage(self.configuration('organization', 'long-gone-org')))

    def test_global_staff_and_superuser_manage_course_and_ccx_without_a_role_lookup(self):
        for label, user in global_staff_actors():
            with self.subTest(actor=label):
                with patch(COURSE_ADMIN_PATCH) as course_admin:
                    policy = CreationContextPolicy(user)
                    self.assertTrue(policy.can_manage(self.configuration(context_key=COURSE_KEY)))
                    self.assertTrue(policy.can_manage(self.configuration(context_key=CCX_KEY)))
                course_admin.assert_not_called()

    def test_ccx_is_denied_before_any_role_lookup(self):
        with patch(COURSE_ADMIN_PATCH, return_value=True) as course_admin:
            self.assertFalse(CreationContextPolicy(actor()).can_manage(self.configuration(context_key=CCX_KEY)))
        course_admin.assert_not_called()

    def test_unrelated_course_is_denied(self):
        user = actor()
        with patch(
            COURSE_ADMIN_PATCH, side_effect=lambda user_, key: key == CourseKey.from_string(COURSE_KEY),
        ):
            policy = CreationContextPolicy(user)
            self.assertTrue(policy.can_manage(self.configuration(context_key=COURSE_KEY)))
            self.assertFalse(policy.can_manage(self.configuration(context_key=OTHER_KEY)))

    def test_unassigned_configuration_is_global_staff_only(self):
        """A converted row with no context waits for a Global Staff first assignment."""
        unassigned = self.configuration(context_type=None, context_key=None)
        for label, user in global_staff_actors():
            with self.subTest(actor=label):
                self.assertTrue(CreationContextPolicy(user).can_manage(unassigned))
        with patch(COURSE_ADMIN_PATCH) as course_admin:
            self.assertFalse(CreationContextPolicy(actor()).can_manage(unassigned))
        course_admin.assert_not_called()

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

    def test_unknown_context_type_is_denied(self):
        with patch(COURSE_ADMIN_PATCH) as course_admin:
            self.assertFalse(CreationContextPolicy(actor()).can_manage(self.configuration('library', 'lib')))
        course_admin.assert_not_called()

    def test_blank_or_malformed_context_key_is_denied(self):
        with patch(COURSE_ADMIN_PATCH) as course_admin:
            policy = CreationContextPolicy(actor())
            self.assertFalse(policy.can_manage(self.configuration(context_key='')))
            self.assertFalse(policy.can_manage(self.configuration(context_key='not-a-course')))
        course_admin.assert_not_called()

    def test_anonymous_actor_never_reads_platform_facts(self):
        policy = CreationContextPolicy(actor(is_authenticated=False))
        with patch(COURSE_ADMIN_PATCH) as course_admin, patch(REGISTRY_PATCH) as registry:
            self.assertFalse(policy.can_manage(self.configuration()))
            self.assertFalse(policy.can_manage(self.configuration('organization', 'org')))
        course_admin.assert_not_called()
        registry.assert_not_called()


class IneligibleActorTests(NoPlatformFactsMixin, GlobalStaffPatchMixin, SimpleTestCase):
    """An account that is not both authenticated and active reads no platform fact."""

    def test_create_is_forbidden_before_shape_or_platform_reads(self):
        for label, user in denied_actors():
            for raw_context in INELIGIBLE_CONTEXTS:
                with self.subTest(actor=label, raw_context=raw_context), self.no_platform_facts():
                    with self.assertRaises(ReusableConfigurationError) as caught:
                        CreationContextPolicy(user).authorize_creation(raw_context)
                    self.assertEqual(caught.exception.category, 'forbidden')
                    self.assertIsNone(caught.exception.field)

    def test_assignment_is_forbidden_before_shape_or_platform_reads(self):
        for label, user in denied_actors():
            for raw_context in INELIGIBLE_CONTEXTS:
                with self.subTest(actor=label, raw_context=raw_context), self.no_platform_facts():
                    with self.assertRaises(ReusableConfigurationError) as caught:
                        CreationContextPolicy(user).authorize_assignment(raw_context)
                    self.assertEqual(caught.exception.category, 'forbidden')
                    self.assertIsNone(caught.exception.field)

    def test_manage_is_refused_for_every_context_shape_without_platform_reads(self):
        configurations = (
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
        for label, user in denied_actors():
            for context_type, context_key in configurations:
                with self.subTest(actor=label, context_type=context_type), self.no_platform_facts():
                    configuration = SimpleNamespace(context_type=context_type, context_key=context_key)
                    self.assertFalse(CreationContextPolicy(user).can_manage(configuration))

    def test_staff_and_superuser_flags_do_not_outrank_ineligibility(self):
        """The Global Staff seam is guarded too, so an inactive staffer is still refused."""
        for label, user in denied_actors():
            with self.subTest(actor=label):
                policy = CreationContextPolicy(user)
                with self.no_platform_facts():
                    self.assertFalse(policy.can_manage(SimpleNamespace(context_type='site', context_key='')))
                    self.assertFalse(policy.can_manage(SimpleNamespace(context_type=None, context_key=None)))
                    with self.assertRaises(ReusableConfigurationError) as caught:
                        policy.authorize_assignment({'type': 'site'})
                self.assertEqual(caught.exception.category, 'forbidden')

    def test_a_subject_without_an_is_active_flag_is_ineligible(self):
        """Eligibility fails closed: an absent account flag keeps no authority."""
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

    def test_global_staff_and_superuser_see_everything_and_course_filter_includes_site(self):
        self.make_configuration('Selected')
        self.make_configuration('Other', context_key=OTHER_KEY)
        self.make_configuration('Organization', context_type='organization', context_key='org')
        self.make_configuration('Site', context_type='site', context_key='')
        for label, user in global_staff_actors():
            policy = CreationContextPolicy(user)
            with self.subTest(actor=label):
                self.assertEqual(self.visible_names(policy), {'Selected', 'Other', 'Organization', 'Site'})
                self.assertEqual(self.visible_names(policy, course_key=OTHER_KEY), {'Other', 'Site'})

    def test_actor_sees_exact_course_matching_organization_and_site(self):
        self.make_configuration('Selected')
        self.make_configuration('Other', context_key=OTHER_KEY)
        self.make_configuration('Matching organization', context_type='organization', context_key='org')
        self.make_configuration('Other organization', context_type='organization', context_key='otherorg')
        self.make_configuration('Site', context_type='site', context_key='')
        policy = self.policy_with_courses([CourseKey.from_string(COURSE_KEY)])
        self.assertEqual(self.visible_names(policy), {'Selected', 'Matching organization', 'Site'})

    def test_membership_is_filtered_in_the_database(self):
        self.make_configuration('Selected')
        policy = self.policy_with_courses([CourseKey.from_string(COURSE_KEY)])
        queryset = policy.visible_configurations()
        self.assertIsInstance(queryset, QuerySet)
        self.assertIn('context_type', str(queryset.query))

    def test_ccx_contexts_are_invisible_to_non_global_staff(self):
        self.make_configuration('CCX', context_key=CCX_KEY)
        self.make_configuration('Selected')
        policy = self.policy_with_courses([CourseKey.from_string(COURSE_KEY)])
        self.assertEqual(self.visible_names(policy), {'Selected'})
        for label, user in global_staff_actors():
            with self.subTest(actor=label):
                self.assertEqual(self.visible_names(CreationContextPolicy(user)), {'CCX', 'Selected'})

    def test_no_accessible_courses_hides_site_contexts_too(self):
        self.make_configuration('Site', context_type='site', context_key='')
        self.assertEqual(self.visible_names(self.policy_with_courses([])), set())

    def test_valid_but_inaccessible_course_key_is_empty(self):
        self.make_configuration('Other', context_key=OTHER_KEY)
        policy = self.policy_with_courses([CourseKey.from_string(COURSE_KEY)])
        self.assertEqual(self.visible_names(policy, course_key=OTHER_KEY), set())

    def test_malformed_course_key_is_an_addressed_invalid_error(self):
        policy = CreationContextPolicy(actor(is_staff=True))
        for course_key in ('not-a-course', 'course-v1:Version@1234', 'library-v1:Org+Library'):
            with self.subTest(course_key=course_key):
                with self.assertRaises(ReusableConfigurationError) as caught:
                    policy.visible_configurations(course_key=course_key)
                self.assertEqual(caught.exception.category, 'invalid')
                self.assertEqual(caught.exception.field, 'course_key')
                self.assertIsInstance(caught.exception.messages, list)

    def test_unassigned_rows_never_match_the_copied_raw_key(self):
        """A copied row's stale raw key grants nothing until a Global Staff assignment."""
        self.make_configuration(
            'Copied',
            context_type=None,
            context_key=COURSE_KEY,
            version=None,
        )
        self.make_configuration('Selected')
        policy = self.policy_with_courses([CourseKey.from_string(COURSE_KEY)])
        self.assertEqual(self.visible_names(policy), {'Selected'})
        self.assertEqual(self.visible_names(policy, course_key=COURSE_KEY), {'Selected'})
        for label, user in global_staff_actors():
            with self.subTest(actor=label):
                self.assertEqual(self.visible_names(CreationContextPolicy(user)), {'Copied', 'Selected'})

    def test_anonymous_actor_sees_nothing_and_reads_no_platform_facts(self):
        self.make_configuration('Site', context_type='site', context_key='')
        with patch(COURSE_ACCESS_PATCH) as course_access:
            queryset = CreationContextPolicy(actor(is_authenticated=False)).visible_configurations()
            self.assertIsInstance(queryset, QuerySet)
            self.assertEqual(queryset.count(), 0)
        course_access.assert_not_called()

    def test_accessible_course_lookup_is_cached_per_instance(self):
        self.make_configuration('Selected')
        with patch(COURSE_ACCESS_PATCH, return_value=[CourseKey.from_string(COURSE_KEY)]) as course_access:
            policy = CreationContextPolicy(actor())
            self.visible_names(policy)
            self.visible_names(policy)
            course_access.assert_called_once()
            CreationContextPolicy(actor()).visible_configurations().count()
            self.assertEqual(course_access.call_count, 2)

    def test_expansion_fails_closed_on_a_malformed_platform_key(self):
        self.make_configuration('Site', context_type='site', context_key='')
        self.assertEqual(self.visible_names(self.policy_with_courses(['not-a-course'])), set())

    def test_malformed_platform_key_is_skipped_and_valid_keys_still_apply(self):
        self.make_configuration('Selected')
        self.make_configuration('Other', context_key=OTHER_KEY)
        policy = self.policy_with_courses(['not-a-course', CourseKey.from_string(COURSE_KEY)])
        self.assertEqual(self.visible_names(policy), {'Selected'})


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

    def test_list_is_empty_without_any_platform_read(self):
        self.make_every_context()
        for label, user in denied_actors():
            with self.subTest(actor=label), self.no_platform_facts():
                queryset = CreationContextPolicy(user).visible_configurations()
                self.assertIsInstance(queryset, QuerySet)
                self.assertEqual(queryset.count(), 0)

    def test_course_filter_reads_no_platform_facts_and_grants_nothing(self):
        self.make_every_context()
        filters = (None, COURSE_KEY, OTHER_KEY, CCX_KEY, 'not-a-course', CourseKey.from_string(COURSE_KEY))
        for label, user in denied_actors():
            for course_key in filters:
                with self.subTest(actor=label, course_key=course_key), self.no_platform_facts():
                    queryset = CreationContextPolicy(user).visible_configurations(course_key=course_key)
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

    def test_both_modules_import_without_cms_or_lms(self):
        completed = self.run_script(LAZY_IMPORT_SCRIPT)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report['attempts'], [])
        self.assertEqual(len(report['paths']), 2)
        for path in report['paths']:
            self.assertTrue(path.startswith(SOURCE_ROOT + os.sep), path)

    def test_the_recorder_refuses_a_platform_import(self):
        """Self-check: the lazy-import assertion cannot pass vacuously."""
        completed = self.run_script(RECORDER_SELF_CHECK_SCRIPT)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), ['cms'])
