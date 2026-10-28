"""Direct tests for the reusable configuration mutation module.

Semantic validation, authorization ordering, the transaction and the update
row lock are exercised through the two module interfaces; the Creation Context
policy has its own suite.
"""

import uuid
from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase

from lti_consumer.exceptions import ReusableConfigurationError
from lti_consumer.models import ReusableLtiConfiguration
from lti_consumer.reusable import create_reusable_configuration, update_reusable_configuration
from lti_consumer.reusable_context import CreationContext

COURSE_KEY = 'course-v1:Org+Course+Run'
PUBLIC_KEY = '-----BEGIN PUBLIC KEY----- key material'
PRIVATE_KEY = '-----BEGIN PRIVATE KEY----- secret material'
POLICY_PATCH = 'lti_consumer.reusable.CreationContextPolicy'


def lti11_data(**overrides):
    """Return a valid LTI 1.1 create payload."""
    data = {
        'name': '  One One  ',
        'version': 'lti_1p1',
        'context': {'type': 'course', 'key': COURSE_KEY},
        'lti_1p1': {'launch_url': 'https://tool.example/launch'},
    }
    data.update(overrides)
    return data


def lti13_data(**overrides):
    """Return a valid LTI 1.3 create payload; the connection kwarg merges into it."""
    connection = overrides.pop('connection', {})
    data = {
        'name': 'One Three',
        'version': 'lti_1p3',
        'context': {'type': 'site'},
        'lti_1p3': {
            'launch_url': 'https://tool.example/launch',
            'oidc_url': 'https://tool.example/oidc',
            'tool_key_mode': 'keyset_url',
            'tool_keyset_url': 'https://tool.example/jwks',
        },
    }
    data['lti_1p3'].update(connection)
    if data['lti_1p3']['tool_key_mode'] == 'public_key' and 'tool_keyset_url' not in connection:
        data['lti_1p3'].pop('tool_keyset_url', None)
    data.update(overrides)
    return data


class _RecordingQueryset:
    """Wrap a queryset to record that select_for_update was requested."""

    def __init__(self, queryset):
        self.queryset = queryset
        self.select_for_update_called = False

    def select_for_update(self):
        """Record the lock request and return the wrapped queryset."""
        self.select_for_update_called = True
        return self.queryset


class ReusableMutationTestCase(TestCase):
    """Mutation tests with a stubbed Creation Context policy."""

    def setUp(self):
        policy_patcher = patch(POLICY_PATCH)
        self.policy_class = policy_patcher.start()
        self.addCleanup(policy_patcher.stop)
        self.policy = self.policy_class.return_value
        self.policy.authorize_creation.side_effect = self.canonical_context
        self.policy.authorize_assignment.side_effect = self.canonical_context
        self.policy.visible_configurations.return_value = ReusableLtiConfiguration.objects.all()
        self.policy.can_manage.return_value = True
        self.actor = object()

    @staticmethod
    def canonical_context(raw_context):
        """Return the context the stub policy authorizes."""
        return CreationContext(type=raw_context['type'], key=raw_context.get('key', ''))


class ReusableCreateTests(ReusableMutationTestCase):
    """Create semantics, one-time credentials and rejection without writes."""

    def test_lti_1p1_create_stores_row_and_returns_one_time_credentials(self):
        result = create_reusable_configuration(self.actor, lti11_data())
        configuration = result.configuration
        self.assertEqual(configuration.name, 'One One')
        self.assertEqual((configuration.context_type, configuration.context_key), ('course', COURSE_KEY))
        self.assertEqual(configuration.lti_1p1_launch_url, 'https://tool.example/launch')
        self.assertEqual(
            result.one_time_credentials,
            {'client_key': configuration.lti_1p1_client_key, 'client_secret': configuration.lti_1p1_client_secret},
        )
        self.assertTrue(configuration.lti_1p1_client_key)
        self.assertTrue(configuration.lti_1p1_client_secret)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 1)

    def test_lti_1p1_create_accepts_explicit_credentials(self):
        result = create_reusable_configuration(self.actor, lti11_data(lti_1p1={
            'launch_url': 'https://tool.example/launch',
            'client_key': 'given-key',
            'client_secret': 'given-secret',
        }))
        self.assertEqual(result.one_time_credentials, {'client_key': 'given-key', 'client_secret': 'given-secret'})
        self.assertEqual(result.configuration.lti_1p1_client_secret, 'given-secret')

    def test_lti_1p1_create_stores_no_lti_1p3_client_id(self):
        """A 1.1 registration bypasses the merged model's random Client ID default."""
        configuration = create_reusable_configuration(self.actor, lti11_data()).configuration

        self.assertIsNone(configuration.lti_1p3_client_id)
        self.assertIsNone(ReusableLtiConfiguration.objects.get(pk=configuration.pk).lti_1p3_client_id)
        lti13 = create_reusable_configuration(self.actor, lti13_data()).configuration
        self.assertIsNotNone(lti13.lti_1p3_client_id)

    def test_lti_1p3_create_generates_identity_and_platform_material(self):
        result = create_reusable_configuration(self.actor, lti13_data())
        configuration = result.configuration
        self.assertIsNone(result.one_time_credentials)
        self.assertEqual(configuration.lti_1p3_tool_key_mode, 'keyset_url')
        self.assertEqual(configuration.lti_1p3_tool_keyset_url, 'https://tool.example/jwks')
        self.assertEqual(configuration.lti_1p3_tool_public_key, '')
        self.assertTrue(configuration.lti_1p3_internal_private_key)
        self.assertTrue(configuration.lti_1p3_internal_public_jwk)
        uuid.UUID(configuration.lti_1p3_client_id)
        uuid.UUID(configuration.lti_1p3_deployment_id)

    def test_lti_1p3_create_accepts_public_key_identity_and_redirects(self):
        result = create_reusable_configuration(self.actor, lti13_data(connection={
            'tool_key_mode': 'public_key',
            'tool_public_key': PUBLIC_KEY,
            'redirect_uris': ['https://tool.example/callback'],
            'client_id': 'client-123',
            'deployment_id': 'deployment-456',
        }))
        configuration = result.configuration
        self.assertEqual(configuration.lti_1p3_client_id, 'client-123')
        self.assertEqual(configuration.lti_1p3_deployment_id, 'deployment-456')
        self.assertEqual(configuration.lti_1p3_redirect_uris, ['https://tool.example/callback'])
        self.assertEqual(configuration.lti_1p3_tool_public_key, PUBLIC_KEY)
        self.assertEqual(configuration.lti_1p3_tool_keyset_url, '')

    def test_create_stores_validated_services_and_defaults(self):
        result = create_reusable_configuration(self.actor, lti11_data(
            services={
                'deep_linking_enabled': True,
                'deep_linking_launch_url': 'https://tool.example/deep',
                'ags_mode': 'programmatic',
                'nrps_enabled': True,
            },
            defaults={
                'display_name': 'Display',
                'grade_weight': 0.5,
                'custom_parameters': ['a=b', ' c=d '],
                'inline_height': 2147483647,
            },
        ))
        configuration = result.configuration
        self.assertTrue(configuration.lti_advantage_deep_linking_enabled)
        self.assertEqual(configuration.lti_advantage_deep_linking_launch_url, 'https://tool.example/deep')
        self.assertEqual(configuration.lti_advantage_ags_mode, 'programmatic')
        self.assertTrue(configuration.lti_advantage_enable_nrps)
        self.assertEqual(configuration.display_name, 'Display')
        self.assertEqual(configuration.grade_weight, 0.5)
        self.assertEqual(configuration.custom_parameters, ['a=b', 'c=d'])
        self.assertEqual(configuration.inline_height, 2147483647)

    def test_create_stores_the_policy_canonical_context(self):
        self.policy.authorize_creation.side_effect = lambda raw: CreationContext(
            type='organization', key='canonical-org',
        )
        result = create_reusable_configuration(self.actor, lti11_data(
            context={'type': 'organization', 'key': 'CANONICAL-ORG'},
        ))
        self.assertEqual(
            (result.configuration.context_type, result.configuration.context_key),
            ('organization', 'canonical-org'),
        )
        self.policy.authorize_creation.assert_called_once_with({'type': 'organization', 'key': 'CANONICAL-ORG'})

    def test_create_authorizes_the_context_before_reporting_other_errors(self):
        self.policy.authorize_creation.side_effect = ReusableConfigurationError('forbidden', 'not allowed')
        with self.assertRaises(ReusableConfigurationError) as raised:
            create_reusable_configuration(self.actor, lti11_data(name=''))
        self.assertEqual(raised.exception.category, 'forbidden')
        self.policy.authorize_creation.assert_called_once_with({'type': 'course', 'key': COURSE_KEY})
        self.assertFalse(ReusableLtiConfiguration.objects.exists())

    def test_create_rejects_non_mapping_data(self):
        with self.assertRaises(ReusableConfigurationError) as raised:
            create_reusable_configuration(self.actor, 'not-a-mapping')
        self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', None))
        self.assertFalse(ReusableLtiConfiguration.objects.exists())

    def test_create_rejects_invalid_payloads_without_writes(self):
        cases = (
            (lti11_data(name='   '), 'name'),
            (lti11_data(name='x' * 256), 'name'),
            (lti11_data(version='lti_1p4'), 'version'),
            (lti11_data(lti_1p3={}), 'lti_1p1'),
            (lti11_data(description=123), 'description'),
            (lti11_data(extra='x'), 'extra'),
            (lti11_data(scope={'course_keys': [COURSE_KEY]}), 'scope'),
            (lti11_data(lti_1p1={'launch_url': 'javascript:alert(1)'}), 'lti_1p1.launch_url'),
            (lti11_data(lti_1p1={'launch_url': ''}), 'lti_1p1.launch_url'),
            (lti11_data(lti_1p1={'launch_url': f'https://tool.example/{"a" * 255}'}), 'lti_1p1.launch_url'),
            (
                lti11_data(lti_1p1={'launch_url': 'https://tool.example/launch', 'client_key': ''}),
                'lti_1p1.client_key',
            ),
            (
                lti11_data(lti_1p1={'launch_url': 'https://tool.example/launch', 'private_key': 'secret'}),
                'lti_1p1.private_key',
            ),
            (lti13_data(connection={'oidc_url': None}), 'lti_1p3.oidc_url'),
            (lti13_data(connection={'redirect_uris': ['']}), 'lti_1p3.redirect_uris'),
            (lti13_data(connection={'redirect_uris': 'https://tool.example/callback'}), 'lti_1p3.redirect_uris'),
            (lti13_data(connection={'tool_key_mode': 'unknown'}), 'lti_1p3.tool_key_mode'),
            (lti13_data(connection={'tool_key_mode': 'public_key'}), 'lti_1p3.tool_public_key'),
            (
                lti13_data(connection={'tool_key_mode': 'public_key', 'tool_public_key': PRIVATE_KEY}),
                'lti_1p3.tool_public_key',
            ),
            (
                lti13_data(connection={
                    'tool_key_mode': 'public_key',
                    'tool_public_key': PUBLIC_KEY,
                    'tool_keyset_url': 'https://tool.example/keys',
                }),
                'lti_1p3.tool_keyset_url',
            ),
            (
                lti13_data(connection={'tool_key_mode': 'keyset_url', 'tool_public_key': PUBLIC_KEY}),
                'lti_1p3.tool_public_key',
            ),
            (
                lti13_data(connection={'tool_keyset_url': f'https://tool.example/{"k" * 491}'}),
                'lti_1p3.tool_keyset_url',
            ),
            (lti13_data(connection={'client_id': '   '}), 'lti_1p3.client_id'),
            (lti11_data(services={'deep_linking_enabled': True}), 'services.deep_linking_launch_url'),
            (
                lti11_data(services={'deep_linking_launch_url': 'javascript:bad'}),
                'services.deep_linking_launch_url',
            ),
            (
                lti11_data(services={'deep_linking_launch_url': f'https://tool.example/{"d" * 300}'}),
                'services.deep_linking_launch_url',
            ),
            (lti11_data(services={'ags_mode': 'sometimes'}), 'services.ags_mode'),
            (lti11_data(services={'nrps_enabled': 'yes'}), 'services.nrps_enabled'),
            (lti11_data(services={'platform_key': 'secret'}), 'services.platform_key'),
            (lti11_data(services=None), 'services'),
            (lti11_data(defaults={'not_a_setting': True}), 'defaults.not_a_setting'),
            (lti11_data(defaults={'display_name': ' '}), 'defaults.display_name'),
            (lti11_data(defaults={'grade_weight': -1}), 'defaults.grade_weight'),
            (lti11_data(defaults={'grade_weight': float('nan')}), 'defaults.grade_weight'),
            (lti11_data(defaults={'enable_grading': 'yes'}), 'defaults.enable_grading'),
            (lti11_data(defaults={'open_tool_in': 'popup'}), 'defaults.open_tool_in'),
            (lti11_data(defaults={'inline_height': -1}), 'defaults.inline_height'),
            (lti11_data(defaults={'inline_height': 2147483648}), 'defaults.inline_height'),
            (lti11_data(defaults={'modal_height': 101}), 'defaults.modal_height'),
            (lti11_data(defaults={'modal_width': -1}), 'defaults.modal_width'),
            (lti11_data(defaults={'custom_parameters': ['missing-equals']}), 'defaults.custom_parameters'),
            (lti11_data(defaults={'custom_parameters': ['=missing-key']}), 'defaults.custom_parameters'),
        )
        for data, field in cases:
            with self.subTest(field=field):
                with self.assertRaises(ReusableConfigurationError) as raised:
                    create_reusable_configuration(self.actor, data)
                self.assertEqual(raised.exception.category, 'invalid')
                self.assertEqual(raised.exception.field, field)
        self.assertFalse(ReusableLtiConfiguration.objects.exists())

    def test_create_allows_duplicate_names(self):
        create_reusable_configuration(self.actor, lti11_data(name='Straße'))
        create_reusable_configuration(self.actor, lti11_data(name='STRASSE'))
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 2)

    def test_create_rolls_back_configuration_after_write_failure(self):
        original_create = ReusableLtiConfiguration.objects.create

        def create_then_fail(*args, **kwargs):
            original_create(*args, **kwargs)
            raise RuntimeError('injected failure')

        with patch.object(ReusableLtiConfiguration.objects, 'create', side_effect=create_then_fail):
            with self.assertRaisesRegex(RuntimeError, 'injected failure'):
                create_reusable_configuration(self.actor, lti13_data())
        self.assertFalse(ReusableLtiConfiguration.objects.exists())


class ReusableUpdateTests(ReusableMutationTestCase):
    """Update mapping, merged-state validation, locks and rollback."""

    def setUp(self):
        super().setUp()
        self.lti11 = create_reusable_configuration(self.actor, lti11_data()).configuration
        self.lti13 = create_reusable_configuration(self.actor, lti13_data()).configuration

    def update(self, configuration, changes):
        """Update one configuration through the module interface."""
        return update_reusable_configuration(self.actor, configuration.config_id, changes)

    def test_update_applies_metadata_connection_services_and_defaults(self):
        updated = self.update(self.lti13, {
            'name': '  Renamed  ',
            'description': '  Notes  ',
            'lti_1p3': {
                'launch_url': 'https://tool.example/new-launch',
                'oidc_url': 'https://tool.example/new-oidc',
                'redirect_uris': ['https://tool.example/callback'],
                'tool_key_mode': 'public_key',
                'tool_public_key': PUBLIC_KEY,
            },
            'services': {'deep_linking_enabled': True, 'deep_linking_launch_url': 'https://tool.example/deep'},
            'defaults': {
                'display_name': 'Tool',
                'grade_weight': 2.5,
                'custom_parameters': ['a=b'],
                'open_tool_in': 'modal',
            },
        })
        self.assertIsInstance(updated, ReusableLtiConfiguration)
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual((stored.name, stored.description), ('Renamed', 'Notes'))
        self.assertEqual(stored.lti_1p3_launch_url, 'https://tool.example/new-launch')
        self.assertEqual(stored.lti_1p3_oidc_url, 'https://tool.example/new-oidc')
        self.assertEqual(stored.lti_1p3_redirect_uris, ['https://tool.example/callback'])
        self.assertEqual(stored.lti_1p3_tool_key_mode, 'public_key')
        self.assertTrue(stored.lti_advantage_deep_linking_enabled)
        self.assertEqual(stored.lti_advantage_deep_linking_launch_url, 'https://tool.example/deep')
        self.assertEqual(stored.display_name, 'Tool')
        self.assertEqual(stored.grade_weight, 2.5)
        self.assertEqual(stored.custom_parameters, ['a=b'])
        self.assertEqual(stored.open_tool_in, 'modal')
        self.assertEqual(stored.lti_1p3_tool_public_key, PUBLIC_KEY)
        self.assertEqual(stored.lti_1p3_tool_keyset_url, '')

    def test_update_clears_description_with_null(self):
        self.update(self.lti11, {'description': 'Text'})
        self.update(self.lti11, {'description': None})
        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=self.lti11.pk).description, '')

    def test_update_rejects_unknown_or_immutable_members_without_writes(self):
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        before = (
            stored.name, stored.description, stored.lti_1p3_launch_url, stored.lti_1p3_client_id,
            stored.context_type, stored.context_key,
        )
        cases = (
            ({'context': {'type': 'site'}}, 'context'),
            ({'scope': {}}, 'scope'),
            ({'version': 'lti_1p1'}, 'version'),
            ({'client_id': 'replacement'}, 'client_id'),
            ({'launch_url': 'https://tool.example/new'}, 'launch_url'),
            ({'lti_1p1': {'launch_url': 'https://tool.example/new'}}, 'lti_1p1'),
            ({'lti_1p3': {'client_id': 'replacement'}}, 'lti_1p3.client_id'),
            ({'lti_1p3': {'deployment_id': 'replacement'}}, 'lti_1p3.deployment_id'),
            ({'services': {'platform_key': 'secret'}}, 'services.platform_key'),
            ({'services': None}, 'services'),
            ({'lti_1p3': None}, 'lti_1p3'),
            ({'defaults': {'not_a_setting': True}}, 'defaults.not_a_setting'),
            ({'name': 'Changed', 'context': {'type': 'site'}}, 'context'),
        )
        for changes, field in cases:
            with self.subTest(field=field):
                with self.assertRaises(ReusableConfigurationError) as raised:
                    self.update(self.lti13, changes)
                self.assertEqual(raised.exception.category, 'invalid')
                self.assertEqual(raised.exception.field, field)
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual(
            (
                stored.name, stored.description, stored.lti_1p3_launch_url, stored.lti_1p3_client_id,
                stored.context_type, stored.context_key,
            ),
            before,
        )

    def test_update_rejects_invalid_semantic_values_without_writes(self):
        cases = (
            ({'name': '   '}, 'name'),
            ({'description': 5}, 'description'),
            ({'lti_1p3': {'launch_url': 'javascript:bad'}}, 'lti_1p3.launch_url'),
            ({'lti_1p3': {'oidc_url': 'not-a-url'}}, 'lti_1p3.oidc_url'),
            ({'lti_1p3': {'redirect_uris': 'https://tool.example/callback'}}, 'lti_1p3.redirect_uris'),
            ({'lti_1p3': {'redirect_uris': ['javascript:bad']}}, 'lti_1p3.redirect_uris'),
            ({'lti_1p3': {'tool_public_key': PUBLIC_KEY}}, 'lti_1p3.tool_public_key'),
            ({'lti_1p3': {'tool_key_mode': 'public_key'}}, 'lti_1p3.tool_public_key'),
            (
                {'lti_1p3': {'tool_key_mode': 'public_key', 'tool_public_key': PRIVATE_KEY}},
                'lti_1p3.tool_public_key',
            ),
            (
                {'lti_1p3': {
                    'tool_key_mode': 'public_key',
                    'tool_public_key': PUBLIC_KEY,
                    'tool_keyset_url': 'https://tool.example/keys',
                }},
                'lti_1p3.tool_keyset_url',
            ),
            ({'lti_1p3': {'tool_keyset_url': f'https://tool.example/{"k" * 491}'}}, 'lti_1p3.tool_keyset_url'),
            ({'services': {'deep_linking_enabled': True}}, 'services.deep_linking_launch_url'),
            ({'services': {'deep_linking_launch_url': 'javascript:bad'}}, 'services.deep_linking_launch_url'),
            ({'services': {'ags_mode': 'sometimes'}}, 'services.ags_mode'),
            ({'defaults': {'modal_width': 101}}, 'defaults.modal_width'),
            ({'defaults': {'custom_parameters': ['missing-equals']}}, 'defaults.custom_parameters'),
        )
        for changes, field in cases:
            with self.subTest(field=field):
                with self.assertRaises(ReusableConfigurationError) as raised:
                    self.update(self.lti13, changes)
                self.assertEqual(raised.exception.category, 'invalid')
                self.assertEqual(raised.exception.field, field)
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual(stored.name, 'One Three')
        self.assertEqual(stored.lti_1p3_tool_key_mode, 'keyset_url')

    def test_update_revalidates_stored_state(self):
        self.lti13.lti_advantage_deep_linking_launch_url = 'javascript:bad'
        self.lti13.save()
        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(self.lti13, {'name': 'Metadata only'})
        self.assertEqual(raised.exception.field, 'services.deep_linking_launch_url')

        self.lti13.lti_advantage_deep_linking_launch_url = ''
        self.lti13.lti_1p3_redirect_uris = ['javascript:bad']
        self.lti13.save()
        # Connection settings are validated only when the request supplies them.
        updated = self.update(self.lti13, {'name': 'Metadata only'})
        self.assertEqual(updated.name, 'Metadata only')

    def test_update_remediates_an_incomplete_lti_1p3_configuration_without_a_connection_section(self):
        """A converted row with no connection data at all stays remediable field by field."""
        incomplete = ReusableLtiConfiguration.objects.create(
            name='Needs configuration',
            version=ReusableLtiConfiguration.LTI_1P3,
            context_type='course',
            context_key=COURSE_KEY,
        )
        self.assertIsNone(incomplete.lti_1p3_tool_key_mode)

        updated = self.update(incomplete, {
            'name': '  Remediated  ',
            'description': 'Notes',
            'services': {'ags_mode': 'disabled'},
            'defaults': {'display_name': 'Remediated tool'},
        })
        self.assertEqual((updated.name, updated.description), ('Remediated', 'Notes'))
        stored = ReusableLtiConfiguration.objects.get(pk=incomplete.pk)
        self.assertEqual(
            (
                stored.name, stored.description, stored.lti_advantage_ags_mode,
                stored.display_name, stored.lti_1p3_tool_key_mode,
            ),
            ('Remediated', 'Notes', 'disabled', 'Remediated tool', None),
        )

        # An explicitly empty connection section changes nothing and validates nothing.
        self.update(incomplete, {'lti_1p3': {}})
        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=incomplete.pk).name, 'Remediated')

    def test_update_validates_the_supplied_lti_1p3_section_against_stored_state(self):
        """A supplied connection section keeps full merged validation, so key/mode edits stay safe."""
        incomplete = ReusableLtiConfiguration.objects.create(
            name='Needs keys',
            version=ReusableLtiConfiguration.LTI_1P3,
            context_type='course',
            context_key=COURSE_KEY,
        )
        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(incomplete, {'lti_1p3': {
                'launch_url': 'https://tool.example/launch',
                'oidc_url': 'https://tool.example/oidc',
            }})
        # The stored tool-key mode is still NULL, so the merged state is rejected before any write.
        self.assertEqual(
            (raised.exception.category, raised.exception.field), ('invalid', 'lti_1p3.tool_key_mode'),
        )
        self.assertIsNone(ReusableLtiConfiguration.objects.get(pk=incomplete.pk).lti_1p3_launch_url)

        updated = self.update(incomplete, {'lti_1p3': {
            'launch_url': 'https://tool.example/launch',
            'oidc_url': 'https://tool.example/oidc',
            'tool_key_mode': 'public_key',
            'tool_public_key': PUBLIC_KEY,
        }})
        self.assertEqual(updated.lti_1p3_tool_key_mode, 'public_key')
        self.assertEqual(updated.lti_1p3_tool_public_key, PUBLIC_KEY)
        self.assertEqual(updated.lti_1p3_tool_keyset_url, '')

    def make_unversioned(self, context_type='site', context_key=''):
        """Create a converted row that has no version yet."""
        return ReusableLtiConfiguration.objects.create(
            name='Converted without version',
            version=None,
            context_type=context_type,
            context_key=context_key,
        )

    def test_update_initializes_the_version_of_an_unversioned_configuration(self):
        """A converted row with no version gets exactly one through the update interface."""
        configuration = self.make_unversioned()

        updated = self.update(configuration, {'version': 'lti_1p3'})

        self.assertEqual(updated.version, 'lti_1p3')
        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=configuration.pk).version, 'lti_1p3')

    def test_update_initializes_version_and_context_in_separate_patches(self):
        """Version and Creation Context each travel alone; either order works."""
        version_first = self.make_unversioned(context_type=None, context_key=None)
        self.update(version_first, {'version': 'lti_1p3'})
        self.update(version_first, {'context': {'type': 'site'}})
        stored = ReusableLtiConfiguration.objects.get(pk=version_first.pk)
        self.assertEqual((stored.version, stored.context_type, stored.context_key), ('lti_1p3', 'site', ''))

        context_first = self.make_unversioned(context_type=None, context_key=None)
        self.update(context_first, {'context': {'type': 'course', 'key': COURSE_KEY}})
        self.update(context_first, {'version': 'lti_1p1'})
        stored = ReusableLtiConfiguration.objects.get(pk=context_first.pk)
        self.assertEqual((stored.version, stored.context_type, stored.context_key), ('lti_1p1', 'course', COURSE_KEY))

    def test_update_rejects_replacing_an_existing_version(self):
        """Once a version is set it is immutable, even when the same value is resent."""
        for requested in ('lti_1p1', 'lti_1p3'):
            with self.subTest(requested=requested):
                with self.assertRaises(ReusableConfigurationError) as raised:
                    self.update(self.lti13, {'version': requested})
                self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', 'version'))
        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=self.lti13.pk).version, 'lti_1p3')

    def test_update_rejects_an_unsupported_version(self):
        """Only the two supported versions can initialize a converted row."""
        configuration = self.make_unversioned()
        for requested in ('lti_2p0', '', None, 'LTI_1P3'):
            with self.subTest(requested=requested):
                with self.assertRaises(ReusableConfigurationError) as raised:
                    self.update(configuration, {'version': requested})
                self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', 'version'))
        self.assertIsNone(ReusableLtiConfiguration.objects.get(pk=configuration.pk).version)

    def test_update_version_failure_leaves_other_changes_unwritten(self):
        """A rejected version assignment writes none of the members that travelled with it."""
        before = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        name_before, display_before = before.name, before.display_name

        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(self.lti13, {
                'version': 'lti_1p1',
                'name': 'Renamed',
                'defaults': {'display_name': 'Changed'},
            })

        self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', 'version'))
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual((stored.version, stored.name, stored.display_name), ('lti_1p3', name_before, display_before))

    def test_update_rejects_a_version_mixed_with_a_context_assignment(self):
        """The one-time context assignment stays context-only, version included."""
        configuration = self.make_unversioned(context_type=None, context_key=None)

        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(configuration, {'version': 'lti_1p3', 'context': {'type': 'site'}})

        self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', 'context'))
        stored = ReusableLtiConfiguration.objects.get(pk=configuration.pk)
        self.assertEqual((stored.version, stored.context_type), (None, None))

    def test_update_after_version_initialization_uses_version_specific_validation(self):
        """Once the version exists, connection remediation follows that version's rules."""
        configuration = self.make_unversioned()
        self.update(configuration, {'version': 'lti_1p3'})

        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(configuration, {'lti_1p1': {'launch_url': 'https://tool.example/launch'}})
        self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', 'lti_1p1'))

        updated = self.update(configuration, {'lti_1p3': {
            'launch_url': 'https://tool.example/launch',
            'oidc_url': 'https://tool.example/oidc',
            'tool_key_mode': 'public_key',
            'tool_public_key': PUBLIC_KEY,
        }})
        self.assertEqual(updated.version, 'lti_1p3')
        self.assertEqual(updated.lti_1p3_tool_key_mode, 'public_key')
        self.assertEqual(updated.lti_1p3_tool_public_key, PUBLIC_KEY)

    def test_update_rejects_the_other_version_section(self):
        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(self.lti11, {'lti_1p3': {'launch_url': 'https://tool.example/new'}})
        self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', 'lti_1p3'))
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti11.pk)
        self.assertEqual(stored.lti_1p1_launch_url, 'https://tool.example/launch')

    def test_update_applies_lti_1p1_launch_url_and_keeps_credentials(self):
        updated = self.update(self.lti11, {'lti_1p1': {'launch_url': 'https://tool.example/moved'}})
        self.assertEqual(updated.lti_1p1_launch_url, 'https://tool.example/moved')
        self.assertEqual(updated.lti_1p1_client_key, self.lti11.lti_1p1_client_key)
        self.assertEqual(updated.lti_1p1_client_secret, self.lti11.lti_1p1_client_secret)

    def test_update_tool_key_transitions_with_tool_key_mode(self):
        self.update(self.lti13, {'lti_1p3': {'tool_key_mode': 'public_key', 'tool_public_key': PUBLIC_KEY}})
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual(stored.lti_1p3_tool_key_mode, 'public_key')
        self.assertEqual(stored.lti_1p3_tool_public_key, PUBLIC_KEY)
        self.assertEqual(stored.lti_1p3_tool_keyset_url, '')

        self.update(self.lti13, {'lti_1p3': {
            'tool_key_mode': 'keyset_url',
            'tool_keyset_url': 'https://tool.example/new-jwks',
        }})
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual(stored.lti_1p3_tool_public_key, '')
        self.assertEqual(stored.lti_1p3_tool_keyset_url, 'https://tool.example/new-jwks')

    def test_update_keeps_tool_key_material_when_only_connection_urls_change(self):
        before = (self.lti13.lti_1p3_tool_public_key, self.lti13.lti_1p3_tool_keyset_url)
        self.update(self.lti13, {'lti_1p3': {'launch_url': 'https://tool.example/moved'}})
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual((stored.lti_1p3_tool_public_key, stored.lti_1p3_tool_keyset_url), before)

    def test_update_never_changes_identity_or_context(self):
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        before = (
            stored.version, stored.context_type, stored.context_key, stored.lti_1p3_client_id,
            stored.lti_1p3_deployment_id, stored.passport_id,
        )
        self.update(self.lti13, {'name': 'Renamed', 'description': 'Notes'})
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual(
            (
                stored.version, stored.context_type, stored.context_key, stored.lti_1p3_client_id,
                stored.lti_1p3_deployment_id, stored.passport_id,
            ),
            before,
        )
        self.assertEqual(stored.name, 'Renamed')

    def test_update_not_found_for_unknown_hidden_or_malformed_identifier(self):
        self.policy.visible_configurations.return_value = ReusableLtiConfiguration.objects.none()
        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(self.lti13, {'name': 'Hidden'})
        self.assertEqual((raised.exception.category, raised.exception.field), ('not_found', None))

        self.policy.visible_configurations.return_value = ReusableLtiConfiguration.objects.all()
        for config_id in (uuid.uuid4(), 'not-a-uuid'):
            with self.subTest(config_id=config_id):
                with self.assertRaises(ReusableConfigurationError) as raised:
                    update_reusable_configuration(self.actor, config_id, {'name': 'Changed'})
                self.assertEqual(raised.exception.category, 'not_found')
        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=self.lti13.pk).name, 'One Three')

    def test_update_forbidden_for_visible_unmanageable_target(self):
        self.policy.can_manage.return_value = False
        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(self.lti13, {'name': 'Denied'})
        self.assertEqual((raised.exception.category, raised.exception.field), ('forbidden', None))
        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=self.lti13.pk).name, 'One Three')

    def test_update_locks_the_visible_target(self):
        recording = _RecordingQueryset(ReusableLtiConfiguration.objects.all())
        self.policy.visible_configurations.return_value = recording
        self.update(self.lti13, {'name': 'Renamed'})
        self.assertTrue(recording.select_for_update_called)
        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=self.lti13.pk).name, 'Renamed')

    def test_update_assigns_the_creation_context_once(self):
        unassigned = ReusableLtiConfiguration.objects.create(
            name='Unassigned',
            version=ReusableLtiConfiguration.LTI_1P3,
            context_type=None,
            context_key=None,
        )

        updated = self.update(unassigned, {'context': {'type': 'site'}})

        self.assertEqual((updated.context_type, updated.context_key), ('site', ''))
        stored = ReusableLtiConfiguration.objects.get(pk=unassigned.pk)
        self.assertEqual((stored.context_type, stored.context_key), ('site', ''))
        self.policy.authorize_assignment.assert_called_once_with({'type': 'site'})

    def test_update_rejects_a_second_context_assignment(self):
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        before = (stored.context_type, stored.context_key)

        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(self.lti13, {'context': {'type': 'course', 'key': COURSE_KEY}})

        self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', 'context'))
        stored.refresh_from_db()
        self.assertEqual((stored.context_type, stored.context_key), before)

    def test_assignment_is_context_only(self):
        """The assignment path accepts no other members, so it stays one write."""
        unassigned = ReusableLtiConfiguration.objects.create(
            name='Unassigned',
            version=ReusableLtiConfiguration.LTI_1P3,
            context_type=None,
            context_key=None,
        )

        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(unassigned, {'name': 'Renamed', 'context': {'type': 'site'}})

        self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', 'context'))
        stored = ReusableLtiConfiguration.objects.get(pk=unassigned.pk)
        self.assertEqual((stored.name, stored.context_type), ('Unassigned', None))

    def test_update_rejects_non_mapping_changes(self):
        with self.assertRaises(ReusableConfigurationError) as raised:
            update_reusable_configuration(self.actor, self.lti13.config_id, 'not-a-mapping')
        self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', None))

    def test_update_rolls_back_after_configuration_write_failure(self):
        with patch.object(ReusableLtiConfiguration, 'save', side_effect=RuntimeError('injected failure')):
            with self.assertRaisesRegex(RuntimeError, 'injected failure'):
                self.update(self.lti13, {
                    'name': 'Renamed',
                    'lti_1p3': {'tool_key_mode': 'public_key', 'tool_public_key': PUBLIC_KEY},
                })
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual(stored.name, 'One Three')
        self.assertEqual(stored.lti_1p3_tool_key_mode, 'keyset_url')
        self.assertEqual(stored.lti_1p3_tool_public_key, '')
        self.assertEqual(stored.lti_1p3_tool_keyset_url, 'https://tool.example/jwks')

    def test_update_translates_integrity_error_after_rollback(self):
        with patch.object(ReusableLtiConfiguration, 'save', side_effect=IntegrityError('duplicate')):
            with self.assertRaises(ReusableConfigurationError) as raised:
                self.update(self.lti13, {'name': 'Taken'})
        self.assertEqual((raised.exception.category, raised.exception.field), ('conflict', None))
        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=self.lti13.pk).name, 'One Three')
