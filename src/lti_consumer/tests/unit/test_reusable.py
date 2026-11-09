"""Direct tests for the reusable configuration mutation module.

Semantic validation, authorization ordering, the transaction, the update row
lock and the create-only generation rules are exercised through the two module
interfaces; the Creation Context policy has its own suite.
"""

import secrets
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase

from lti_consumer.exceptions import ReusableConfigurationError
from lti_consumer.models import Lti1p3Passport, LtiConfiguration, ReusableLtiConfiguration
from lti_consumer.reusable import (
    _validated_privacy,
    create_reusable_configuration,
    update_reusable_configuration,
)
from lti_consumer.reusable_context import CreationContext, CreationContextPolicy

COURSE_KEY = 'course-v1:Org+Course+Run'
OTHER_COURSE_KEY = 'course-v1:Other+Course+Run'
PUBLIC_KEY = '-----BEGIN PUBLIC KEY----- key material'
PRIVATE_KEY = '-----BEGIN PRIVATE KEY----- secret material'
POLICY_PATCH = 'lti_consumer.reusable.CreationContextPolicy'
COMPAT_HELPERS = (
    'get_active_organizations',
    'user_is_global_staff',
    'user_is_course_admin',
    'get_studio_accessible_course_keys',
)
COPIED_RAW_CONTEXT_KEY = 'legacy-passport-context-key'
PRIVACY_WIRE_MEMBERS = {
    'share_username': 'pii_share_username',
    'share_full_name': 'pii_share_full_name',
    'share_email': 'pii_share_email',
    'data_sharing_notice': 'data_sharing_notice',
    'require_user_confirmation': 'require_user_confirmation',
}
PRIVACY_DEFAULTS = {
    'pii_share_username': False,
    'pii_share_full_name': False,
    'pii_share_email': False,
    'data_sharing_notice': '',
    'require_user_confirmation': True,
}
# Every value differs from its default, so a stored one proves an authoring write.
PRIVACY_AUTHORED = {
    'share_username': True,
    'share_full_name': True,
    'share_email': True,
    'data_sharing_notice': 'Hand-written sharing notice',
    'require_user_confirmation': False,
}


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


def complete_lti13_section(**overrides):
    """Return a complete LTI 1.3 connection section."""
    section = {
        'launch_url': 'https://tool.example/launch',
        'oidc_url': 'https://tool.example/oidc',
        'tool_key_mode': 'public_key',
        'tool_public_key': PUBLIC_KEY,
    }
    section.update(overrides)
    return section


def converted_row(**overrides):
    """Create a converted row: copied raw context key, no context type and no version."""
    values = {
        'name': 'Copied passport',
        'version': None,
        'context_type': None,
        'context_key': COPIED_RAW_CONTEXT_KEY,
    }
    values.update(overrides)
    return ReusableLtiConfiguration.objects.create(**values)


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
        """A 1.1 registration bypasses the model's random Client ID default."""
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

    def test_create_omitting_privacy_uses_the_safe_defaults(self):
        configuration = create_reusable_configuration(self.actor, lti11_data()).configuration
        stored = ReusableLtiConfiguration.objects.get(pk=configuration.pk)
        self.assertEqual(
            {field: getattr(stored, field) for field in PRIVACY_DEFAULTS},
            PRIVACY_DEFAULTS,
        )
        self.assertFalse(stored.hide_external_tool)

    def test_create_stores_explicit_privacy_and_hide_external_tool(self):
        result = create_reusable_configuration(self.actor, lti11_data(
            privacy=dict(PRIVACY_AUTHORED),
            defaults={'hide_external_tool': True},
        ))
        stored = ReusableLtiConfiguration.objects.get(pk=result.configuration.pk)
        self.assertEqual(
            {field: getattr(stored, field) for field in PRIVACY_WIRE_MEMBERS.values()},
            {PRIVACY_WIRE_MEMBERS[member]: value for member, value in PRIVACY_AUTHORED.items()},
        )
        self.assertTrue(stored.hide_external_tool)

    def test_create_rejects_privacy_smuggled_through_defaults_or_services(self):
        cases = (
            (lti11_data(defaults={'share_username': True}), 'defaults.share_username'),
            (lti11_data(defaults={'data_sharing_notice': 'notice'}), 'defaults.data_sharing_notice'),
            (lti11_data(services={'share_email': True}), 'services.share_email'),
        )
        for data, field in cases:
            with self.subTest(field=field):
                with self.assertRaises(ReusableConfigurationError) as raised:
                    create_reusable_configuration(self.actor, data)
                self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', field))
        self.assertFalse(ReusableLtiConfiguration.objects.exists())

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
            (lti11_data(defaults={'hide_external_tool': 1}), 'defaults.hide_external_tool'),
            (lti11_data(defaults={'hide_external_tool': None}), 'defaults.hide_external_tool'),
            (lti11_data(privacy={'share_username': 1}), 'privacy.share_username'),
            (lti11_data(privacy={'share_full_name': None}), 'privacy.share_full_name'),
            (lti11_data(privacy={'share_email': 'yes'}), 'privacy.share_email'),
            (lti11_data(privacy={'require_user_confirmation': 1}), 'privacy.require_user_confirmation'),
            (lti11_data(privacy={'data_sharing_notice': 5}), 'privacy.data_sharing_notice'),
            (lti11_data(privacy={'hide_external_tool': True}), 'privacy.hide_external_tool'),
            (lti11_data(privacy='not-a-mapping'), 'privacy'),
        )
        for data, field in cases:
            with self.subTest(field=field):
                with self.assertRaises(ReusableConfigurationError) as raised:
                    create_reusable_configuration(self.actor, data)
                self.assertEqual(raised.exception.category, 'invalid')
                self.assertEqual(raised.exception.field, field)
        self.assertFalse(ReusableLtiConfiguration.objects.exists())

    def test_create_allows_duplicate_names_and_client_ids(self):
        """Only passport_id is unique: the catalog keeps no name or client-id constraint."""
        create_reusable_configuration(self.actor, lti11_data(name='Straße'))
        create_reusable_configuration(self.actor, lti11_data(name='STRASSE'))
        shared_identity = {'client_id': 'shared-client', 'deployment_id': 'shared-deployment'}
        create_reusable_configuration(self.actor, lti13_data(connection=dict(shared_identity)))
        create_reusable_configuration(self.actor, lti13_data(connection=dict(shared_identity)))
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 4)
        self.assertEqual(
            ReusableLtiConfiguration.objects.filter(lti_1p3_client_id='shared-client').count(), 2,
        )

    def test_create_rolls_back_when_key_generation_fails_after_the_row_is_saved(self):
        """The 1.3 generator runs on the created row; its failure must leave no row behind."""
        real_save = ReusableLtiConfiguration.save

        def save_then_fail(configuration):
            real_save(configuration)
            raise RuntimeError('injected failure')

        with patch.object(ReusableLtiConfiguration, 'generate_lti_1p3_keys_if_missing', save_then_fail):
            with self.assertRaisesRegex(RuntimeError, 'injected failure'):
                create_reusable_configuration(self.actor, lti13_data())
        self.assertFalse(ReusableLtiConfiguration.objects.exists())

    def test_create_conflicts_when_key_generation_raises_integrity_error_after_the_row_is_saved(self):
        real_save = ReusableLtiConfiguration.save

        def save_then_fail(configuration):
            real_save(configuration)
            raise IntegrityError('duplicate')

        with patch.object(ReusableLtiConfiguration, 'generate_lti_1p3_keys_if_missing', save_then_fail):
            with self.assertRaises(ReusableConfigurationError) as raised:
                create_reusable_configuration(self.actor, lti13_data())
        self.assertEqual(raised.exception.category, 'conflict')
        self.assertFalse(ReusableLtiConfiguration.objects.exists())

    def test_create_rolls_back_configuration_after_write_failure(self):
        original_create = ReusableLtiConfiguration.objects.create

        def create_then_fail(*args, **kwargs):
            original_create(*args, **kwargs)
            raise RuntimeError('injected failure')

        with patch.object(ReusableLtiConfiguration.objects, 'create', side_effect=create_then_fail):
            with self.assertRaisesRegex(RuntimeError, 'injected failure'):
                create_reusable_configuration(self.actor, lti13_data())
        self.assertFalse(ReusableLtiConfiguration.objects.exists())


class ReusableCreateTransactionTests(TransactionTestCase):
    """Create-only generation runs once, inside the create transaction.

    TransactionTestCase keeps the test itself outside a transaction, so the
    in_atomic_block probes below observe the module's own atomic block.
    """

    def setUp(self):
        policy_patcher = patch(POLICY_PATCH)
        self.policy_class = policy_patcher.start()
        self.addCleanup(policy_patcher.stop)
        self.policy = self.policy_class.return_value
        self.policy.authorize_creation.side_effect = lambda raw: CreationContext(
            type=raw['type'], key=raw.get('key', ''),
        )
        self.actor = object()

    def test_lti_1p1_create_generates_both_credentials_once_inside_the_transaction(self):
        real_token_urlsafe = secrets.token_urlsafe
        observed = []

        def recording_token_urlsafe(size):
            observed.append(transaction.get_connection().in_atomic_block)
            return real_token_urlsafe(size)

        with patch('lti_consumer.reusable.secrets.token_urlsafe', side_effect=recording_token_urlsafe):
            result = create_reusable_configuration(self.actor, lti11_data())

        self.assertEqual(observed, [True, True])
        self.assertEqual(
            result.one_time_credentials,
            {
                'client_key': result.configuration.lti_1p1_client_key,
                'client_secret': result.configuration.lti_1p1_client_secret,
            },
        )

    def test_lti_1p3_create_generates_identity_and_keys_once_inside_the_transaction(self):
        real_uuid4 = uuid.uuid4
        identity_observations = []

        def recording_uuid4():
            identity_observations.append(transaction.get_connection().in_atomic_block)
            return real_uuid4()

        real_generate = ReusableLtiConfiguration.generate_lti_1p3_keys_if_missing
        key_observations = []

        def recording_generate(configuration):
            key_observations.append(transaction.get_connection().in_atomic_block)
            return real_generate(configuration)

        # Patch the module reference, not uuid.uuid4 itself: the model's kid default shares it.
        with patch('lti_consumer.reusable.uuid') as reusable_uuid:
            reusable_uuid.uuid4.side_effect = recording_uuid4
            with patch.object(ReusableLtiConfiguration, 'generate_lti_1p3_keys_if_missing', recording_generate):
                configuration = create_reusable_configuration(self.actor, lti13_data()).configuration

        self.assertEqual(len(identity_observations), 2)
        self.assertEqual(set(identity_observations), {True})
        self.assertEqual(key_observations, [True])
        uuid.UUID(configuration.lti_1p3_client_id)
        uuid.UUID(configuration.lti_1p3_deployment_id)
        self.assertTrue(configuration.lti_1p3_internal_private_key)

    def test_explicit_lti_1p3_identity_generates_no_identity_uuids(self):
        """Explicit client_id/deployment_id are kept, so no identity UUID is drawn for them."""
        with patch('lti_consumer.reusable.uuid') as reusable_uuid:
            with patch.object(ReusableLtiConfiguration, 'generate_lti_1p3_keys_if_missing') as generator:
                configuration = create_reusable_configuration(self.actor, lti13_data(connection={
                    'client_id': 'client-123',
                    'deployment_id': 'deployment-456',
                })).configuration

        reusable_uuid.uuid4.assert_not_called()
        generator.assert_called_once()
        self.assertEqual(
            (configuration.lti_1p3_client_id, configuration.lti_1p3_deployment_id),
            ('client-123', 'deployment-456'),
        )

    def test_explicit_lti_1p1_credentials_are_not_generated(self):
        with patch('lti_consumer.reusable.secrets.token_urlsafe') as token_urlsafe:
            create_reusable_configuration(self.actor, lti11_data(lti_1p1={
                'launch_url': 'https://tool.example/launch',
                'client_key': 'given-key',
                'client_secret': 'given-secret',
            }))
        token_urlsafe.assert_not_called()

    def test_create_conflict_is_reported_only_after_the_transaction_exits(self):
        observed = []

        def recording_conflict(message):
            observed.append(transaction.get_connection().in_atomic_block)
            raise ReusableConfigurationError('conflict', message)

        with patch.object(ReusableLtiConfiguration.objects, 'create', side_effect=IntegrityError('duplicate')):
            with patch('lti_consumer.reusable._conflict', side_effect=recording_conflict):
                with self.assertRaises(ReusableConfigurationError) as raised:
                    create_reusable_configuration(self.actor, lti13_data())

        self.assertEqual(raised.exception.category, 'conflict')
        self.assertEqual(observed, [False])
        self.assertFalse(ReusableLtiConfiguration.objects.exists())


class ReusableUpdateTests(ReusableMutationTestCase):
    """Update mapping, merged-state validation, locks and rollback."""

    def setUp(self):
        super().setUp()
        self.lti11 = create_reusable_configuration(self.actor, lti11_data()).configuration
        self.lti13 = create_reusable_configuration(self.actor, lti13_data()).configuration

    def update(self, configuration, changes):
        """Update one configuration through the module interface."""
        return update_reusable_configuration(self.actor, configuration.passport_id, changes)

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

    def test_update_refuses_identity_and_credential_members_whatever_the_value(self):
        """Immutable members are refused by presence, so blanks cannot be smuggled as edits."""
        def snapshot(pk):
            row = ReusableLtiConfiguration.objects.get(pk=pk)
            return (
                row.name, row.lti_1p3_client_id, row.lti_1p3_deployment_id,
                row.lti_1p1_client_key, row.lti_1p1_client_secret,
            )

        before = {pk: snapshot(pk) for pk in (self.lti13.pk, self.lti11.pk)}
        values = ('', None, '   ', 'replacement')
        cases = [
            (self.lti13, {'lti_1p3': {member: value}}, f'lti_1p3.{member}')
            for member in ('client_id', 'deployment_id')
            for value in values
        ] + [
            (self.lti11, {'lti_1p1': {member: value}}, f'lti_1p1.{member}')
            for member in ('client_key', 'client_secret')
            for value in values
        ]
        for configuration, changes, field in cases:
            with self.subTest(changes=changes):
                with self.assertRaises(ReusableConfigurationError) as raised:
                    self.update(configuration, changes)
                self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', field))
        self.assertEqual({pk: snapshot(pk) for pk in before}, before)

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
            ({'defaults': {'hide_external_tool': 1}}, 'defaults.hide_external_tool'),
            ({'defaults': {'hide_external_tool': None}}, 'defaults.hide_external_tool'),
            ({'privacy': {'share_username': 1}}, 'privacy.share_username'),
            ({'privacy': {'share_full_name': None}}, 'privacy.share_full_name'),
            ({'privacy': {'share_email': 'yes'}}, 'privacy.share_email'),
            ({'privacy': {'require_user_confirmation': 1}}, 'privacy.require_user_confirmation'),
            ({'privacy': {'data_sharing_notice': 5}}, 'privacy.data_sharing_notice'),
            ({'privacy': {'share_email': {'nested': True}}}, 'privacy.share_email'),
            ({'privacy': 'not-a-mapping'}, 'privacy'),
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

    def test_update_leaves_invalid_stored_services_untouched_when_omitted(self):
        """An omitted section is untouched, so a metadata edit stays available."""
        self.lti13.lti_advantage_deep_linking_enabled = True
        self.lti13.lti_advantage_deep_linking_launch_url = 'javascript:bad'
        self.lti13.save()

        updated = self.update(self.lti13, {'name': 'Metadata only'})

        self.assertEqual(updated.name, 'Metadata only')
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual(stored.lti_advantage_deep_linking_launch_url, 'javascript:bad')

    def test_present_services_section_validates_the_merged_state_and_rolls_back(self):
        self.lti13.lti_advantage_deep_linking_enabled = True
        self.lti13.lti_advantage_deep_linking_launch_url = 'javascript:bad'
        self.lti13.save()

        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(self.lti13, {'services': {'ags_mode': 'disabled'}})

        self.assertEqual(
            (raised.exception.category, raised.exception.field),
            ('invalid', 'services.deep_linking_launch_url'),
        )
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual(stored.lti_advantage_ags_mode, 'declarative')
        self.assertEqual(stored.lti_advantage_deep_linking_launch_url, 'javascript:bad')

    def test_update_leaves_invalid_stored_defaults_untouched_when_omitted(self):
        """An omitted defaults section is untouched, so a metadata edit stays available."""
        self.lti13.grade_weight = -1
        self.lti13.save()

        updated = self.update(self.lti13, {'name': 'Metadata only'})

        self.assertEqual(updated.name, 'Metadata only')
        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=self.lti13.pk).grade_weight, -1)

    def test_present_empty_defaults_section_validates_the_merged_state_and_rolls_back(self):
        """A present defaults section validates what is stored, not only what it carries."""
        self.lti13.grade_weight = -1
        self.lti13.save()

        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(self.lti13, {'name': 'Renamed', 'description': 'Notes', 'defaults': {}})

        self.assertEqual(
            (raised.exception.category, raised.exception.field), ('invalid', 'defaults.grade_weight'),
        )
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual((stored.name, stored.description, stored.grade_weight), ('One Three', '', -1))

    def test_present_empty_defaults_section_on_a_complete_row_changes_nothing(self):
        updated = self.update(self.lti13, {'defaults': {}})
        self.assertEqual(
            (updated.display_name, updated.grade_weight, updated.open_tool_in, updated.inline_height),
            ('LTI Consumer', 1.0, 'iframe', 800),
        )

    def test_present_empty_privacy_validates_the_merged_state_and_omitted_privacy_is_untouched(self):
        """A present privacy section validates stored state; an omitted one leaves it untouched."""
        self.update(self.lti13, {'privacy': dict(PRIVACY_AUTHORED)})
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        before = {field: getattr(stored, field) for field in PRIVACY_WIRE_MEMBERS.values()}

        with patch('lti_consumer.reusable._validated_privacy', wraps=_validated_privacy) as validated:
            self.update(self.lti13, {'privacy': {}})

        validated.assert_called_once_with(dict(PRIVACY_AUTHORED))
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual(
            {field: getattr(stored, field) for field in PRIVACY_WIRE_MEMBERS.values()}, before,
        )

        with patch('lti_consumer.reusable._validated_privacy', wraps=_validated_privacy) as validated:
            self.update(self.lti13, {'name': 'Metadata only'})

        validated.assert_not_called()
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual(stored.name, 'Metadata only')
        self.assertEqual(
            {field: getattr(stored, field) for field in PRIVACY_WIRE_MEMBERS.values()}, before,
        )

    def test_update_merges_partial_privacy_with_stored_values(self):
        self.update(self.lti13, {'privacy': dict(PRIVACY_AUTHORED)})

        self.update(self.lti13, {'privacy': {'share_email': False}})

        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertFalse(stored.pii_share_email)
        self.assertTrue(stored.pii_share_username)
        self.assertTrue(stored.pii_share_full_name)
        self.assertEqual(stored.data_sharing_notice, 'Hand-written sharing notice')
        self.assertFalse(stored.require_user_confirmation)

        self.update(self.lti13, {'privacy': {'share_full_name': False}})

        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertFalse(stored.pii_share_email)
        self.assertTrue(stored.pii_share_username)
        self.assertFalse(stored.pii_share_full_name)

    def test_update_explicit_false_and_empty_notice_clear_stored_privacy(self):
        self.update(self.lti13, {'privacy': dict(PRIVACY_AUTHORED)})
        cleared = {
            'share_username': False,
            'share_full_name': False,
            'share_email': False,
            'require_user_confirmation': False,
        }
        for notice in (None, '', '   '):
            with self.subTest(notice=notice):
                self.update(self.lti13, {'privacy': dict(cleared, data_sharing_notice=notice)})
                stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
                self.assertEqual(
                    {field: getattr(stored, field) for field in PRIVACY_WIRE_MEMBERS.values()},
                    dict(PRIVACY_DEFAULTS, require_user_confirmation=False),
                )

    def test_update_keeps_the_sharing_notice_separate_from_the_tool_description(self):
        self.update(self.lti13, {
            'description': 'Tool Description',
            'privacy': {'data_sharing_notice': 'Learner-facing notice'},
        })
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual(
            (stored.description, stored.data_sharing_notice),
            ('Tool Description', 'Learner-facing notice'),
        )

        self.update(self.lti13, {'description': 'Renamed Tool Description'})
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual(stored.data_sharing_notice, 'Learner-facing notice')

        self.update(self.lti13, {'privacy': {'data_sharing_notice': 'Changed learner notice'}})
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual(stored.description, 'Renamed Tool Description')
        self.assertEqual(stored.data_sharing_notice, 'Changed learner notice')

    def test_defaults_hide_external_tool_roundtrips_and_merges(self):
        updated = self.update(self.lti13, {'defaults': {'hide_external_tool': True}})
        self.assertTrue(updated.hide_external_tool)

        self.update(self.lti13, {'defaults': {'display_name': 'Tool'}})
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertTrue(stored.hide_external_tool)
        self.assertEqual(stored.display_name, 'Tool')

        self.update(self.lti13, {'defaults': {'hide_external_tool': False}})
        self.assertFalse(ReusableLtiConfiguration.objects.get(pk=self.lti13.pk).hide_external_tool)

    def test_invalid_privacy_rolls_back_sibling_changes_and_keeps_identity(self):
        self.update(self.lti13, {'privacy': dict(PRIVACY_AUTHORED)})
        before_row = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        before = (
            before_row.name, before_row.description, before_row.lti_1p3_launch_url,
            before_row.lti_1p3_client_id, before_row.lti_1p3_deployment_id,
            before_row.lti_1p3_internal_private_key, before_row.context_type, before_row.context_key,
            before_row.display_name, before_row.hide_external_tool,
            *(getattr(before_row, field) for field in PRIVACY_WIRE_MEMBERS.values()),
        )

        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(self.lti13, {
                'name': 'Renamed',
                'description': 'Notes',
                'lti_1p3': {'launch_url': 'https://tool.example/moved'},
                'defaults': {'display_name': 'Changed'},
                'privacy': {'share_email': 1},
            })

        self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', 'privacy.share_email'))
        after_row = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual(
            (
                after_row.name, after_row.description, after_row.lti_1p3_launch_url,
                after_row.lti_1p3_client_id, after_row.lti_1p3_deployment_id,
                after_row.lti_1p3_internal_private_key, after_row.context_type, after_row.context_key,
                after_row.display_name, after_row.hide_external_tool,
                *(getattr(after_row, field) for field in PRIVACY_WIRE_MEMBERS.values()),
            ),
            before,
        )

    def test_privacy_errors_do_not_change_authorization_or_lookup_precedence(self):
        self.policy.can_manage.return_value = False
        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(self.lti13, {'privacy': {'share_email': 1}})
        self.assertEqual((raised.exception.category, raised.exception.field), ('forbidden', None))

        self.policy.can_manage.return_value = True
        self.policy.visible_configurations.return_value = ReusableLtiConfiguration.objects.none()
        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(self.lti13, {'privacy': {'share_email': 1}})
        self.assertEqual((raised.exception.category, raised.exception.field), ('not_found', None))

    def test_privacy_members_are_not_accepted_through_defaults_or_services(self):
        cases = (
            ({'defaults': {'share_username': True}}, 'defaults.share_username'),
            ({'defaults': {'data_sharing_notice': 'notice'}}, 'defaults.data_sharing_notice'),
            ({'services': {'share_email': True}}, 'services.share_email'),
            ({'privacy': {'hide_external_tool': True}}, 'privacy.hide_external_tool'),
        )
        for changes, field in cases:
            with self.subTest(field=field):
                with self.assertRaises(ReusableConfigurationError) as raised:
                    self.update(self.lti13, changes)
                self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', field))

    def test_present_defaults_section_can_remediate_invalid_stored_defaults(self):
        self.lti13.grade_weight = -1
        self.lti13.open_tool_in = 'popup'
        self.lti13.save()

        updated = self.update(self.lti13, {'defaults': {'grade_weight': 2.5, 'open_tool_in': 'modal'}})

        self.assertEqual((updated.grade_weight, updated.open_tool_in), (2.5, 'modal'))
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual((stored.grade_weight, stored.open_tool_in), (2.5, 'modal'))

    def test_provided_defaults_do_not_bypass_another_invalid_stored_default(self):
        """The merged section is validated, so one valid patch cannot hide a stored defect."""
        self.lti13.grade_weight = -1
        self.lti13.save()

        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(self.lti13, {'defaults': {'modal_width': 50}})

        self.assertEqual(
            (raised.exception.category, raised.exception.field), ('invalid', 'defaults.grade_weight'),
        )
        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=self.lti13.pk).modal_width, 80)

    def test_update_validates_omitted_connection_state_only_when_it_is_present(self):
        """Stored connection state is revalidated by presence, not by every update."""
        self.lti13.lti_1p3_redirect_uris = ['javascript:bad']
        self.lti13.save()

        updated = self.update(self.lti13, {'name': 'Metadata only'})

        self.assertEqual(updated.name, 'Metadata only')
        self.assertEqual(
            ReusableLtiConfiguration.objects.get(pk=self.lti13.pk).lti_1p3_redirect_uris, ['javascript:bad'],
        )

    def test_present_empty_lti_1p3_section_validates_the_merged_state(self):
        incomplete = converted_row(
            name='Needs keys', version=ReusableLtiConfiguration.LTI_1P3,
            context_type='course', context_key=COURSE_KEY,
        )
        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(incomplete, {'lti_1p3': {}})
        # The merged state has no launch URL, so the empty section is validated, not skipped.
        self.assertEqual(
            (raised.exception.category, raised.exception.field), ('invalid', 'lti_1p3.launch_url'),
        )
        self.assertIsNone(ReusableLtiConfiguration.objects.get(pk=incomplete.pk).lti_1p3_launch_url)

    def test_present_empty_lti_1p1_section_requires_a_stored_launch_url(self):
        incomplete = converted_row(
            name='Needs a launch URL', version=ReusableLtiConfiguration.LTI_1P1,
            context_type='course', context_key=COURSE_KEY,
        )
        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(incomplete, {'lti_1p1': {}})
        self.assertEqual(
            (raised.exception.category, raised.exception.field), ('invalid', 'lti_1p1.launch_url'),
        )

    def test_present_empty_section_on_a_complete_row_changes_nothing(self):
        updated = self.update(self.lti13, {'lti_1p3': {}})
        self.assertEqual(updated.lti_1p3_launch_url, 'https://tool.example/launch')
        self.assertEqual(updated.lti_1p3_oidc_url, 'https://tool.example/oidc')
        self.assertEqual(updated.lti_1p3_tool_key_mode, 'keyset_url')
        self.assertEqual(updated.lti_1p3_tool_keyset_url, 'https://tool.example/jwks')

    def test_update_remediates_an_incomplete_lti_1p3_configuration_without_a_connection_section(self):
        """A converted row with no connection data at all stays remediable field by field."""
        incomplete = converted_row(
            name='Needs configuration', version=ReusableLtiConfiguration.LTI_1P3,
            context_type='course', context_key=COURSE_KEY,
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

    def test_update_validates_the_supplied_lti_1p3_section_against_stored_state(self):
        """A supplied connection section keeps full merged validation, so key/mode edits stay safe."""
        incomplete = converted_row(
            name='Needs keys', version=ReusableLtiConfiguration.LTI_1P3,
            context_type='course', context_key=COURSE_KEY,
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

    def test_update_initializes_the_version_of_an_unversioned_configuration(self):
        """A converted row with no version gets exactly one through the update interface."""
        configuration = converted_row()

        updated = self.update(configuration, {'version': 'lti_1p3'})

        self.assertEqual(updated.version, 'lti_1p3')
        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=configuration.pk).version, 'lti_1p3')

    def test_update_initializes_version_and_context_in_separate_patches(self):
        """Version and Creation Context each travel alone; either order works."""
        version_first = converted_row(context_key=None)
        self.update(version_first, {'version': 'lti_1p3'})
        self.update(version_first, {'context': {'type': 'site'}})
        stored = ReusableLtiConfiguration.objects.get(pk=version_first.pk)
        self.assertEqual((stored.version, stored.context_type, stored.context_key), ('lti_1p3', 'site', ''))

        context_first = converted_row()
        self.update(context_first, {'context': {'type': 'course', 'key': COURSE_KEY}})
        self.update(context_first, {'version': 'lti_1p1'})
        stored = ReusableLtiConfiguration.objects.get(pk=context_first.pk)
        self.assertEqual((stored.version, stored.context_type, stored.context_key), ('lti_1p1', 'course', COURSE_KEY))

    def test_update_initializes_version_inline_with_ordinary_edits(self):
        configuration = converted_row()

        updated = self.update(configuration, {
            'version': 'lti_1p1',
            'name': '  Renamed  ',
            'defaults': {'display_name': 'Tool'},
        })

        self.assertEqual((updated.version, updated.name, updated.display_name), ('lti_1p1', 'Renamed', 'Tool'))
        self.assertIsNone(updated.lti_1p1_launch_url)

    def test_update_initializes_version_with_a_complete_connection_section(self):
        configuration = converted_row()

        updated = self.update(configuration, {
            'version': 'lti_1p3',
            'lti_1p3': complete_lti13_section(),
        })

        self.assertEqual(updated.version, 'lti_1p3')
        self.assertEqual(updated.lti_1p3_tool_key_mode, 'public_key')
        self.assertEqual(updated.lti_1p3_tool_public_key, PUBLIC_KEY)

    def test_unversioned_row_rejects_a_connection_section_as_invalid_version(self):
        """A NULL version is never read as LTI 1.1: the caller states the version instead."""
        configuration = converted_row()
        cases = (
            {'lti_1p1': {'launch_url': 'https://tool.example/launch'}},
            {'lti_1p1': {}},
            {'lti_1p3': complete_lti13_section()},
            {'lti_1p3': {}},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                with self.assertRaises(ReusableConfigurationError) as raised:
                    self.update(configuration, changes)
                self.assertEqual(
                    (raised.exception.category, raised.exception.field), ('invalid', 'version'),
                )
        stored = ReusableLtiConfiguration.objects.get(pk=configuration.pk)
        self.assertEqual(
            (stored.version, stored.lti_1p1_launch_url, stored.lti_1p3_launch_url, stored.lti_1p3_tool_key_mode),
            (None, None, None, None),
        )

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
        configuration = converted_row()
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
        configuration = converted_row(context_key=None)

        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(configuration, {'version': 'lti_1p3', 'context': {'type': 'site'}})

        self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', 'context'))
        stored = ReusableLtiConfiguration.objects.get(pk=configuration.pk)
        self.assertEqual((stored.version, stored.context_type, stored.context_key), (None, None, None))

    def test_update_after_version_initialization_uses_version_specific_validation(self):
        """Once the version exists, connection remediation follows that version's rules."""
        configuration = converted_row()
        self.update(configuration, {'version': 'lti_1p3'})

        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(configuration, {'lti_1p1': {'launch_url': 'https://tool.example/launch'}})
        self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', 'lti_1p1'))

        updated = self.update(configuration, {'lti_1p3': complete_lti13_section()})
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

    def test_update_never_regenerates_identity_credentials_or_signing_material(self):
        """Identity, credentials and platform RSA material are create-only, blanks included."""
        self.lti13.lti_1p3_client_id = None
        self.lti13.lti_1p3_deployment_id = None
        self.lti13.lti_1p3_internal_private_key = ''
        self.lti13.lti_1p3_internal_private_key_id = ''
        self.lti13.lti_1p3_internal_public_jwk = ''
        self.lti13.save()
        before = (
            self.lti13.version, self.lti13.context_type, self.lti13.context_key,
            self.lti13.lti_1p3_client_id, self.lti13.lti_1p3_deployment_id, self.lti13.passport_id,
        )

        with patch.object(ReusableLtiConfiguration, 'generate_lti_1p3_keys_if_missing') as generator:
            with patch('lti_consumer.reusable.secrets.token_urlsafe') as token_urlsafe:
                self.update(self.lti13, {
                    'name': 'Renamed', 'description': 'Notes', 'privacy': {'share_email': True},
                })
                self.update(self.lti11, {'name': 'Renamed one one'})

        generator.assert_not_called()
        token_urlsafe.assert_not_called()
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual(
            (
                stored.version, stored.context_type, stored.context_key,
                stored.lti_1p3_client_id, stored.lti_1p3_deployment_id, stored.passport_id,
            ),
            before,
        )
        self.assertEqual(
            (
                stored.lti_1p3_internal_private_key,
                stored.lti_1p3_internal_private_key_id,
                stored.lti_1p3_internal_public_jwk,
            ),
            ('', '', ''),
        )
        self.assertEqual(stored.name, 'Renamed')
        self.assertTrue(stored.pii_share_email)
        stored_11 = ReusableLtiConfiguration.objects.get(pk=self.lti11.pk)
        self.assertEqual(
            (stored_11.lti_1p1_client_key, stored_11.lti_1p1_client_secret),
            (self.lti11.lti_1p1_client_key, self.lti11.lti_1p1_client_secret),
        )

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
        # An invisible or unknown id must not be probed through the manage check either.
        self.policy.can_manage.assert_not_called()
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
        unassigned = converted_row(name='Unassigned', context_key=None)

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
        unassigned = converted_row(name='Unassigned', context_key=None)

        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(unassigned, {'name': 'Renamed', 'context': {'type': 'site'}})

        self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', 'context'))
        stored = ReusableLtiConfiguration.objects.get(pk=unassigned.pk)
        self.assertEqual((stored.name, stored.context_type), ('Unassigned', None))

    def test_update_rejects_non_mapping_changes(self):
        with self.assertRaises(ReusableConfigurationError) as raised:
            update_reusable_configuration(self.actor, self.lti13.passport_id, 'not-a-mapping')
        self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', None))

    def test_update_rolls_back_after_configuration_write_failure(self):
        real_save = ReusableLtiConfiguration.save

        def save_then_fail(configuration):
            real_save(configuration)
            raise RuntimeError('injected failure')

        with patch.object(ReusableLtiConfiguration, 'save', save_then_fail):
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
        observed = []

        def recording_conflict(message):
            observed.append(transaction.get_connection().in_atomic_block)
            raise ReusableConfigurationError('conflict', message)

        real_save = ReusableLtiConfiguration.save

        def save_then_fail(configuration):
            real_save(configuration)
            raise IntegrityError('duplicate')

        with patch.object(ReusableLtiConfiguration, 'save', save_then_fail):
            with patch('lti_consumer.reusable._conflict', side_effect=recording_conflict):
                with self.assertRaises(ReusableConfigurationError) as raised:
                    self.update(self.lti13, {'name': 'Taken'})
        self.assertEqual(raised.exception.category, 'conflict')
        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=self.lti13.pk).name, 'One Three')


class ReusableCopiedRowTests(ReusableMutationTestCase):
    """Converted rows: copied raw context, no version, and blank identity material."""

    def update(self, configuration, changes):
        """Update one configuration through the module interface."""
        return update_reusable_configuration(self.actor, configuration.passport_id, changes)

    def test_metadata_update_keeps_the_version_and_raw_copied_context(self):
        copied = converted_row()

        self.update(copied, {
            'name': 'Renamed',
            'services': {'ags_mode': 'disabled'},
            'defaults': {'display_name': 'Tool'},
        })

        stored = ReusableLtiConfiguration.objects.get(pk=copied.pk)
        self.assertEqual(
            (stored.version, stored.context_type, stored.context_key),
            (None, None, COPIED_RAW_CONTEXT_KEY),
        )
        self.assertEqual((stored.name, stored.lti_advantage_ags_mode, stored.display_name),
                         ('Renamed', 'disabled', 'Tool'))

    def test_copied_blank_identity_and_signing_material_are_not_repaired(self):
        copied = converted_row(
            name='Copied', version=ReusableLtiConfiguration.LTI_1P3,
            context_type='course', context_key=COURSE_KEY, lti_1p3_client_id=None,
        )
        self.assertIsNone(copied.lti_1p3_client_id)
        self.assertEqual(copied.lti_1p3_internal_private_key, '')

        with patch.object(ReusableLtiConfiguration, 'generate_lti_1p3_keys_if_missing') as generator:
            with patch('lti_consumer.reusable.secrets.token_urlsafe') as token_urlsafe:
                self.update(copied, {'name': 'Renamed', 'description': 'Notes'})

        generator.assert_not_called()
        token_urlsafe.assert_not_called()
        stored = ReusableLtiConfiguration.objects.get(pk=copied.pk)
        self.assertEqual(
            (
                stored.lti_1p3_client_id, stored.lti_1p3_deployment_id,
                stored.lti_1p3_internal_private_key, stored.lti_1p3_internal_private_key_id,
                stored.lti_1p3_internal_public_jwk,
            ),
            (None, None, '', '', ''),
        )

    def test_course_assignment_replaces_the_copied_raw_key_with_the_canonical_key(self):
        """The copied raw value is overwritten, never matched, and is not a valid course key."""
        copied = converted_row()

        updated = self.update(copied, {'context': {'type': 'course', 'key': OTHER_COURSE_KEY}})

        self.assertEqual((updated.context_type, updated.context_key), ('course', OTHER_COURSE_KEY))
        self.assertNotEqual(updated.context_key, COPIED_RAW_CONTEXT_KEY)
        stored = ReusableLtiConfiguration.objects.get(pk=copied.pk)
        self.assertEqual((stored.context_type, stored.context_key), ('course', OTHER_COURSE_KEY))

    def test_site_assignment_stores_a_blank_key_rather_than_the_copied_value(self):
        copied = converted_row()

        updated = self.update(copied, {'context': {'type': 'site'}})

        self.assertEqual((updated.context_type, updated.context_key), ('site', ''))
        self.assertEqual(
            ReusableLtiConfiguration.objects.get(pk=copied.pk).context_key, '',
        )

    def test_assignment_works_before_the_version_is_assigned(self):
        copied = converted_row()

        updated = self.update(copied, {'context': {'type': 'organization', 'key': 'SomeOrg'}})

        self.assertEqual((updated.context_type, updated.context_key), ('organization', 'SomeOrg'))
        self.assertIsNone(updated.version)
        self.assertIsNone(ReusableLtiConfiguration.objects.get(pk=copied.pk).version)


class ReusableRetainedTableTests(ReusableMutationTestCase):
    """Every write stays on the reusable catalog table."""

    def test_create_and_update_write_only_the_new_table(self):
        with patch.object(Lti1p3Passport, 'save', side_effect=AssertionError('retained passport write')), \
                patch.object(LtiConfiguration, 'save', side_effect=AssertionError('placement write')):
            lti13 = create_reusable_configuration(self.actor, lti13_data()).configuration
            lti11 = create_reusable_configuration(self.actor, lti11_data()).configuration
            update_reusable_configuration(self.actor, lti13.passport_id, {'name': 'Renamed'})
            update_reusable_configuration(self.actor, lti11.passport_id, {'name': 'Renamed one one'})

        self.assertEqual(ReusableLtiConfiguration.objects.count(), 2)
        self.assertEqual(Lti1p3Passport.objects.count(), 0)
        self.assertEqual(LtiConfiguration.objects.count(), 0)


class ReusableActorEligibilityTests(TestCase):
    """Inactive actors are refused before any platform fact is read.

    These tests drive the real Creation Context policy, which owns the shared
    eligibility guard; compat helpers are patched so any lookup would fail the
    assertion below.
    """

    def setUp(self):
        self.helpers = {}
        for name in COMPAT_HELPERS:
            helper_patcher = patch(f'lti_consumer.plugin.compat.{name}', autospec=True)
            self.helpers[name] = helper_patcher.start()
            self.addCleanup(helper_patcher.stop)
        self.inactive = SimpleNamespace(is_authenticated=True, is_active=False)
        self.active = SimpleNamespace(is_authenticated=True, is_active=True, is_superuser=False)

    def assert_no_platform_reads(self):
        """Assert that no compat helper ran."""
        for name, helper in self.helpers.items():
            with self.subTest(helper=name):
                helper.assert_not_called()

    def test_inactive_actor_is_denied_on_create_before_any_platform_read(self):
        for context in ({'type': 'site'}, {'type': 'course', 'key': COURSE_KEY},
                        {'type': 'organization', 'key': 'SomeOrg'}):
            with self.subTest(context=context['type']):
                with self.assertRaises(ReusableConfigurationError) as raised:
                    create_reusable_configuration(self.inactive, lti11_data(context=context))
                self.assertEqual(raised.exception.category, 'forbidden')
        self.assert_no_platform_reads()
        self.assertFalse(ReusableLtiConfiguration.objects.exists())

    def test_inactive_actor_sees_no_configurations_and_cannot_manage_one(self):
        configuration = ReusableLtiConfiguration.objects.create(
            name='Visible to staff only', version=ReusableLtiConfiguration.LTI_1P3,
            context_type='site', context_key='',
        )

        policy = CreationContextPolicy(self.inactive)

        self.assertEqual(list(policy.visible_configurations()), [])
        self.assertFalse(policy.can_manage(configuration))
        self.assert_no_platform_reads()

    def test_inactive_actor_is_denied_on_update_and_assignment_before_any_platform_read(self):
        assigned = ReusableLtiConfiguration.objects.create(
            name='Assigned', version=ReusableLtiConfiguration.LTI_1P3,
            context_type='course', context_key=COURSE_KEY,
        )
        unassigned = converted_row(name='Unassigned', context_key=None)

        for configuration, changes in (
            (assigned, {'name': 'Denied'}),
            (assigned, {'lti_1p3': complete_lti13_section()}),
            (unassigned, {'context': {'type': 'site'}}),
            (unassigned, {'version': 'lti_1p3'}),
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ReusableConfigurationError) as raised:
                    update_reusable_configuration(self.inactive, configuration.passport_id, changes)
                # An invisible target is indistinguishable from an unknown one.
                self.assertEqual(raised.exception.category, 'not_found')

        self.assert_no_platform_reads()
        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=assigned.pk).name, 'Assigned')
        self.assertIsNone(ReusableLtiConfiguration.objects.get(pk=unassigned.pk).context_type)

    def test_active_global_staff_actor_is_allowed(self):
        self.helpers['user_is_global_staff'].return_value = True

        configuration = create_reusable_configuration(self.active, lti13_data()).configuration

        self.assertEqual(configuration.context_type, 'site')
        self.assertTrue(configuration.lti_1p3_internal_private_key)
        self.helpers['user_is_global_staff'].assert_called()
