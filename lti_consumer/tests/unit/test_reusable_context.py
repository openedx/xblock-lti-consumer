"""Direct tests for the reusable Creation Context policy."""

from types import SimpleNamespace
from unittest.mock import patch

from django.db.models import QuerySet
from django.test import SimpleTestCase, TestCase
from django.utils.translation import gettext_lazy
from opaque_keys.edx.keys import CourseKey

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


def actor(is_superuser=False, is_staff=False, is_authenticated=True):
    """Return a minimal actor with the platform flags the policy reads."""
    return SimpleNamespace(is_authenticated=is_authenticated, is_superuser=is_superuser, is_staff=is_staff)


def global_staff_actors():
    """Return a non-superuser Global Staff actor and a superuser, for subTest coverage."""
    return (('global staff', actor(is_staff=True)), ('superuser', actor(is_superuser=True)))


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


class CreationContextPolicyVisibilityTests(GlobalStaffPatchMixin, TestCase):
    """Query-backed visibility: exact course, matching organization, site and denial."""

    def make_configuration(self, name, context_type='course', context_key=COURSE_KEY):
        return ReusableLtiConfiguration.objects.create(
            name=name,
            version=ReusableLtiConfiguration.LTI_1P1,
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

    def test_query_does_not_expose_a_course_key_that_bypasses_the_actor(self):
        self.make_configuration('Selected')
        self.make_configuration('Other', context_key=OTHER_KEY)
        policy = self.policy_with_courses([CourseKey.from_string(COURSE_KEY)])
        self.assertEqual(self.visible_names(policy), {'Selected'})

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
