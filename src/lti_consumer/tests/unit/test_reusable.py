"""Direct tests for the reusable configuration mutation module.

Journeys drive the real service, the real Creation Context policy and the ORM;
only platform adapters are patched. Focused units keep the wire allowlists,
merged-state validation, atomicity and the row-lock request.
"""

import secrets
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.test import TestCase, TransactionTestCase

from lti_consumer.exceptions import ReusableConfigurationError
from lti_consumer.models import Lti1p3Passport, LtiConfiguration, ReusableLtiConfiguration
from lti_consumer.reusable import (
    _conflict,
    create_reusable_configuration,
    update_reusable_configuration,
)
from lti_consumer.reusable_context import CreationContextPolicy

COURSE_KEY = 'course-v1:Org+Course+Run'
OTHER_COURSE_KEY = 'course-v1:Other+Course+Run'
PUBLIC_KEY = '-----BEGIN PUBLIC KEY----- key material'
PRIVATE_KEY = '-----BEGIN PRIVATE KEY----- secret material'
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


def actor(is_staff=False, is_active=True, is_authenticated=True, is_superuser=False):
    """Return the minimal account object the real Creation Context policy reads."""
    return SimpleNamespace(
        is_authenticated=is_authenticated,
        is_active=is_active,
        is_superuser=is_superuser,
        is_staff=is_staff,
    )


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


class PlatformAdapterMixin:
    """Patch only platform adapters; the real policy, service and ORM run.

    Global Staff and the organization registry are stubbed as platform facts. The
    real policy still performs eligibility, shaping, normalization and authority.
    """

    def setUp(self):
        super().setUp()
        self.helpers = {}
        for name in COMPAT_HELPERS:
            patcher = patch(f'lti_consumer.plugin.compat.{name}', autospec=True)
            self.helpers[name] = patcher.start()
            self.addCleanup(patcher.stop)
        self.helpers['user_is_global_staff'].return_value = True
        self.helpers['get_active_organizations'].return_value = [
            {'short_name': 'SomeOrg'},
            {'short_name': 'CANONICAL-ORG'},
        ]
        self.actor = actor(is_staff=True)


class ReusableMutationTestCase(PlatformAdapterMixin, TestCase):
    """Service interface with the real Creation Context policy."""

    def update(self, configuration, changes):
        """Update one configuration through the module interface."""
        return update_reusable_configuration(self.actor, configuration.passport_id, changes)


class ReusableUpdateTestCase(ReusableMutationTestCase):
    """Shared LTI 1.1 and 1.3 rows for update journeys."""

    def setUp(self):
        super().setUp()
        self.lti11 = create_reusable_configuration(self.actor, lti11_data()).configuration
        self.lti13 = create_reusable_configuration(self.actor, lti13_data()).configuration


class ReusableCreateTests(ReusableMutationTestCase):
    """Create journeys, authorization and rejection without writes."""

    def test_lti_1p1_create_journey(self):
        result = create_reusable_configuration(self.actor, lti11_data())
        stored = ReusableLtiConfiguration.objects.get(pk=result.configuration.pk)

        self.assertEqual(stored.name, 'One One')
        self.assertEqual((stored.context_type, stored.context_key), ('course', COURSE_KEY))
        self.assertEqual(stored.lti_1p1_launch_url, 'https://tool.example/launch')
        self.assertEqual(
            result.one_time_credentials,
            {'client_key': stored.lti_1p1_client_key, 'client_secret': stored.lti_1p1_client_secret},
        )
        self.assertTrue(stored.lti_1p1_client_key)
        self.assertTrue(stored.lti_1p1_client_secret)
        self.assertIsNone(stored.lti_1p3_client_id)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), 1)

        explicit = create_reusable_configuration(self.actor, lti11_data(lti_1p1={
            'launch_url': 'https://tool.example/launch',
            'client_key': 'given-key',
            'client_secret': 'given-secret',
        }))
        self.assertEqual(
            explicit.one_time_credentials,
            {'client_key': 'given-key', 'client_secret': 'given-secret'},
        )
        self.assertEqual(
            ReusableLtiConfiguration.objects.get(pk=explicit.configuration.pk).lti_1p1_client_secret,
            'given-secret',
        )

        # The real policy canonicalizes the organization key to its registered short name.
        canonical = create_reusable_configuration(
            self.actor,
            lti11_data(context={'type': 'organization', 'key': 'CANONICAL-ORG'}),
        )
        self.assertEqual(
            (canonical.configuration.context_type, canonical.configuration.context_key),
            ('organization', 'canonical-org'),
        )
        self.helpers['get_active_organizations'].assert_called()

    def test_lti_1p3_create_journey(self):
        result = create_reusable_configuration(self.actor, lti13_data())
        stored = ReusableLtiConfiguration.objects.get(pk=result.configuration.pk)

        self.assertIsNone(result.one_time_credentials)
        self.assertEqual(stored.lti_1p3_tool_key_mode, 'keyset_url')
        self.assertEqual(stored.lti_1p3_tool_keyset_url, 'https://tool.example/jwks')
        self.assertEqual(stored.lti_1p3_tool_public_key, '')
        self.assertTrue(stored.lti_1p3_internal_private_key)
        self.assertTrue(stored.lti_1p3_internal_public_jwk)
        uuid.UUID(stored.lti_1p3_client_id)
        uuid.UUID(stored.lti_1p3_deployment_id)

        explicit = create_reusable_configuration(self.actor, lti13_data(connection={
            'tool_key_mode': 'public_key',
            'tool_public_key': PUBLIC_KEY,
            'redirect_uris': ['https://tool.example/callback'],
            'client_id': 'client-123',
            'deployment_id': 'deployment-456',
        })).configuration
        self.assertEqual(explicit.lti_1p3_client_id, 'client-123')
        self.assertEqual(explicit.lti_1p3_deployment_id, 'deployment-456')
        self.assertEqual(explicit.lti_1p3_redirect_uris, ['https://tool.example/callback'])
        self.assertEqual(explicit.lti_1p3_tool_public_key, PUBLIC_KEY)
        self.assertEqual(explicit.lti_1p3_tool_keyset_url, '')

    def test_create_stores_services_defaults_and_privacy(self):
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

        safe = create_reusable_configuration(self.actor, lti11_data()).configuration
        stored = ReusableLtiConfiguration.objects.get(pk=safe.pk)
        self.assertEqual(
            {field: getattr(stored, field) for field in PRIVACY_DEFAULTS},
            PRIVACY_DEFAULTS,
        )
        self.assertFalse(stored.hide_external_tool)

        authored = create_reusable_configuration(self.actor, lti11_data(
            privacy=dict(PRIVACY_AUTHORED),
            defaults={'hide_external_tool': True},
        )).configuration
        stored = ReusableLtiConfiguration.objects.get(pk=authored.pk)
        self.assertEqual(
            {field: getattr(stored, field) for field in PRIVACY_WIRE_MEMBERS.values()},
            {PRIVACY_WIRE_MEMBERS[member]: value for member, value in PRIVACY_AUTHORED.items()},
        )
        self.assertTrue(stored.hide_external_tool)

    def test_create_rejects_invalid_payloads_without_writes(self):
        with self.assertRaises(ReusableConfigurationError) as raised:
            create_reusable_configuration(self.actor, 'not-a-mapping')
        self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', None))

        smuggling = (
            (lti11_data(defaults={'share_username': True}), 'defaults.share_username'),
            (lti11_data(defaults={'data_sharing_notice': 'notice'}), 'defaults.data_sharing_notice'),
            (lti11_data(services={'share_email': True}), 'services.share_email'),
        )
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
        for data, field in cases + smuggling:
            with self.subTest(field=field):
                with self.assertRaises(ReusableConfigurationError) as raised:
                    create_reusable_configuration(self.actor, data)
                self.assertEqual(raised.exception.category, 'invalid')
                self.assertEqual(raised.exception.field, field)
        self.assertFalse(ReusableLtiConfiguration.objects.exists())

    def test_create_authorizes_before_validating_the_payload(self):
        self.helpers['user_is_global_staff'].return_value = False

        with self.assertRaises(ReusableConfigurationError) as raised:
            create_reusable_configuration(
                actor(), lti11_data(name='', context={'type': 'site'}),
            )

        self.assertEqual(raised.exception.category, 'forbidden')
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


class ReusableCreateTransactionTests(PlatformAdapterMixin, TransactionTestCase):
    """Create-only generation and failure recovery, observed outside an outer transaction."""

    def test_create_rolls_back_when_writing_or_key_generation_fails(self):
        real_save = ReusableLtiConfiguration.save

        def save_then_fail(configuration):
            real_save(configuration)
            raise RuntimeError('injected failure')

        with patch.object(ReusableLtiConfiguration, 'generate_lti_1p3_keys_if_missing', save_then_fail):
            with self.assertRaisesRegex(RuntimeError, 'injected failure'):
                create_reusable_configuration(self.actor, lti13_data())
        self.assertFalse(ReusableLtiConfiguration.objects.exists())

        def save_then_integrity(configuration):
            real_save(configuration)
            raise IntegrityError('duplicate')

        with patch.object(ReusableLtiConfiguration, 'generate_lti_1p3_keys_if_missing', save_then_integrity):
            with self.assertRaises(ReusableConfigurationError) as raised:
                create_reusable_configuration(self.actor, lti13_data())
        self.assertEqual(raised.exception.category, 'conflict')
        self.assertFalse(ReusableLtiConfiguration.objects.exists())

        original_create = ReusableLtiConfiguration.objects.create

        def create_then_fail(*args, **kwargs):
            original_create(*args, **kwargs)
            raise RuntimeError('injected failure')

        with patch.object(ReusableLtiConfiguration.objects, 'create', side_effect=create_then_fail):
            with self.assertRaisesRegex(RuntimeError, 'injected failure'):
                create_reusable_configuration(self.actor, lti13_data())
        self.assertFalse(ReusableLtiConfiguration.objects.exists())

    def test_create_conflict_is_reported_only_after_the_transaction_exits(self):
        observed = []

        def recording_conflict(message):
            observed.append(transaction.get_connection().in_atomic_block)
            _conflict(message)

        with patch.object(ReusableLtiConfiguration.objects, 'create', side_effect=IntegrityError('duplicate')):
            with patch('lti_consumer.reusable._conflict', recording_conflict):
                with self.assertRaises(ReusableConfigurationError) as raised:
                    create_reusable_configuration(self.actor, lti13_data())

        self.assertEqual(raised.exception.category, 'conflict')
        self.assertEqual(observed, [False])
        self.assertFalse(transaction.get_connection().in_atomic_block)
        self.assertFalse(ReusableLtiConfiguration.objects.exists())

    def test_create_generates_credentials_and_keys_once_inside_the_transaction(self):
        real_token_urlsafe = secrets.token_urlsafe
        token_observations = []

        def recording_token_urlsafe(size):
            token_observations.append(transaction.get_connection().in_atomic_block)
            return real_token_urlsafe(size)

        with patch('lti_consumer.reusable.secrets.token_urlsafe', side_effect=recording_token_urlsafe):
            result = create_reusable_configuration(self.actor, lti11_data())

        self.assertEqual(token_observations, [True, True])
        self.assertEqual(
            result.one_time_credentials,
            {
                'client_key': result.configuration.lti_1p1_client_key,
                'client_secret': result.configuration.lti_1p1_client_secret,
            },
        )

        real_uuid4 = uuid.uuid4
        identity_observations = []

        def recording_uuid4():
            identity_observations.append(transaction.get_connection().in_atomic_block)
            return real_uuid4()

        real_generate = ReusableLtiConfiguration.generate_lti_1p3_keys_if_missing
        key_observations = []

        def recording_generate(self):
            key_observations.append(transaction.get_connection().in_atomic_block)
            return real_generate(self)

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

        with patch('lti_consumer.reusable.uuid') as reusable_uuid:
            with patch.object(ReusableLtiConfiguration, 'generate_lti_1p3_keys_if_missing') as generator:
                explicit = create_reusable_configuration(self.actor, lti13_data(connection={
                    'client_id': 'client-123',
                    'deployment_id': 'deployment-456',
                })).configuration

        reusable_uuid.uuid4.assert_not_called()
        generator.assert_called_once()
        self.assertEqual(
            (explicit.lti_1p3_client_id, explicit.lti_1p3_deployment_id),
            ('client-123', 'deployment-456'),
        )

        with patch('lti_consumer.reusable.secrets.token_urlsafe') as token_urlsafe:
            create_reusable_configuration(self.actor, lti11_data(lti_1p1={
                'launch_url': 'https://tool.example/launch',
                'client_key': 'given-key',
                'client_secret': 'given-secret',
            }))
        token_urlsafe.assert_not_called()


class ReusableUpdateTests(ReusableUpdateTestCase):
    """Update journeys and retained validation matrices."""

    def test_update_metadata_and_connection_journey(self):
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
        })
        self.assertIsInstance(updated, ReusableLtiConfiguration)
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual((stored.name, stored.description), ('Renamed', 'Notes'))
        self.assertEqual(stored.lti_1p3_launch_url, 'https://tool.example/new-launch')
        self.assertEqual(stored.lti_1p3_oidc_url, 'https://tool.example/new-oidc')
        self.assertEqual(stored.lti_1p3_redirect_uris, ['https://tool.example/callback'])
        self.assertEqual(stored.lti_1p3_tool_key_mode, 'public_key')
        self.assertEqual(stored.lti_1p3_tool_public_key, PUBLIC_KEY)
        self.assertEqual(stored.lti_1p3_tool_keyset_url, '')

        self.update(self.lti13, {'description': None})
        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=self.lti13.pk).description, '')

        self.update(self.lti13, {'lti_1p3': {
            'tool_key_mode': 'keyset_url',
            'tool_keyset_url': 'https://tool.example/new-jwks',
        }})
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual(stored.lti_1p3_tool_public_key, '')
        self.assertEqual(stored.lti_1p3_tool_keyset_url, 'https://tool.example/new-jwks')

        before = (stored.lti_1p3_tool_public_key, stored.lti_1p3_tool_keyset_url)
        self.update(self.lti13, {'lti_1p3': {'launch_url': 'https://tool.example/moved'}})
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual((stored.lti_1p3_tool_public_key, stored.lti_1p3_tool_keyset_url), before)

        updated = self.update(self.lti11, {'lti_1p1': {'launch_url': 'https://tool.example/moved'}})
        self.assertEqual(updated.lti_1p1_launch_url, 'https://tool.example/moved')
        self.assertEqual(updated.lti_1p1_client_key, self.lti11.lti_1p1_client_key)
        self.assertEqual(updated.lti_1p1_client_secret, self.lti11.lti_1p1_client_secret)

    def test_update_authoring_settings_journey(self):
        updated = self.update(self.lti13, {
            'services': {'deep_linking_enabled': True, 'deep_linking_launch_url': 'https://tool.example/deep'},
            'defaults': {
                'display_name': 'Tool',
                'grade_weight': 2.5,
                'custom_parameters': ['a=b'],
                'open_tool_in': 'modal',
            },
        })
        stored = ReusableLtiConfiguration.objects.get(pk=updated.pk)
        self.assertTrue(stored.lti_advantage_deep_linking_enabled)
        self.assertEqual(stored.lti_advantage_deep_linking_launch_url, 'https://tool.example/deep')
        self.assertEqual(stored.display_name, 'Tool')
        self.assertEqual(stored.grade_weight, 2.5)
        self.assertEqual(stored.custom_parameters, ['a=b'])
        self.assertEqual(stored.open_tool_in, 'modal')

        self.update(self.lti13, {'privacy': dict(PRIVACY_AUTHORED)})
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual(
            {field: getattr(stored, field) for field in PRIVACY_WIRE_MEMBERS.values()},
            {PRIVACY_WIRE_MEMBERS[member]: value for member, value in PRIVACY_AUTHORED.items()},
        )

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

        updated = self.update(self.lti13, {'defaults': {'hide_external_tool': True}})
        self.assertTrue(updated.hide_external_tool)
        self.update(self.lti13, {'defaults': {'display_name': 'Tool'}})
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertTrue(stored.hide_external_tool)
        self.assertEqual(stored.display_name, 'Tool')
        self.update(self.lti13, {'defaults': {'hide_external_tool': False}})
        self.assertFalse(ReusableLtiConfiguration.objects.get(pk=self.lti13.pk).hide_external_tool)

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

    def test_update_rejects_unknown_immutable_and_malformed_members(self):
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

        with self.assertRaises(ReusableConfigurationError) as raised:
            update_reusable_configuration(self.actor, self.lti13.passport_id, 'not-a-mapping')
        self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', None))

    def test_update_rejects_invalid_values_without_partial_writes(self):
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
            ({'defaults': {'share_username': True}}, 'defaults.share_username'),
            ({'defaults': {'data_sharing_notice': 'notice'}}, 'defaults.data_sharing_notice'),
            ({'services': {'share_email': True}}, 'services.share_email'),
            ({'privacy': {'hide_external_tool': True}}, 'privacy.hide_external_tool'),
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

    def test_present_services_and_connection_sections_validate_merged_state(self):
        self.lti13.lti_advantage_deep_linking_enabled = True
        self.lti13.lti_advantage_deep_linking_launch_url = 'javascript:bad'
        self.lti13.save()

        updated = self.update(self.lti13, {'name': 'Metadata only'})
        self.assertEqual(updated.name, 'Metadata only')
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual(stored.lti_advantage_deep_linking_launch_url, 'javascript:bad')

        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(self.lti13, {'services': {'ags_mode': 'disabled'}})
        self.assertEqual(
            (raised.exception.category, raised.exception.field),
            ('invalid', 'services.deep_linking_launch_url'),
        )
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual(stored.lti_advantage_ags_mode, 'declarative')
        self.assertEqual(stored.lti_advantage_deep_linking_launch_url, 'javascript:bad')

        self.lti13.lti_1p3_redirect_uris = ['javascript:bad']
        self.lti13.save()
        updated = self.update(self.lti13, {'name': 'Metadata only'})
        self.assertEqual(updated.name, 'Metadata only')
        self.assertEqual(
            ReusableLtiConfiguration.objects.get(pk=self.lti13.pk).lti_1p3_redirect_uris, ['javascript:bad'],
        )

        incomplete = converted_row(
            name='Needs keys', version=ReusableLtiConfiguration.LTI_1P3,
            context_type='course', context_key=COURSE_KEY,
        )
        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(incomplete, {'lti_1p3': {}})
        self.assertEqual(
            (raised.exception.category, raised.exception.field), ('invalid', 'lti_1p3.launch_url'),
        )
        self.assertIsNone(ReusableLtiConfiguration.objects.get(pk=incomplete.pk).lti_1p3_launch_url)

        incomplete_11 = converted_row(
            name='Needs a launch URL', version=ReusableLtiConfiguration.LTI_1P1,
            context_type='course', context_key=COURSE_KEY,
        )
        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(incomplete_11, {'lti_1p1': {}})
        self.assertEqual(
            (raised.exception.category, raised.exception.field), ('invalid', 'lti_1p1.launch_url'),
        )

        self.update(self.lti13, {'lti_1p3': {'redirect_uris': ['https://tool.example/callback']}})
        updated = self.update(self.lti13, {'lti_1p3': {}})
        self.assertEqual(updated.lti_1p3_launch_url, 'https://tool.example/launch')
        self.assertEqual(updated.lti_1p3_oidc_url, 'https://tool.example/oidc')
        self.assertEqual(updated.lti_1p3_tool_key_mode, 'keyset_url')
        self.assertEqual(updated.lti_1p3_tool_keyset_url, 'https://tool.example/jwks')

    def test_present_defaults_and_privacy_sections_validate_merged_state(self):
        self.lti13.grade_weight = -1
        self.lti13.save()

        updated = self.update(self.lti13, {'name': 'Metadata only'})
        self.assertEqual(updated.name, 'Metadata only')
        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=self.lti13.pk).grade_weight, -1)

        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(self.lti13, {'name': 'Renamed', 'description': 'Notes', 'defaults': {}})
        self.assertEqual(
            (raised.exception.category, raised.exception.field), ('invalid', 'defaults.grade_weight'),
        )
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual((stored.name, stored.description, stored.grade_weight), ('Metadata only', '', -1))

        self.update(self.lti13, {'defaults': {'grade_weight': 1.0}})
        updated = self.update(self.lti13, {'defaults': {}})
        self.assertEqual(
            (updated.display_name, updated.grade_weight, updated.open_tool_in, updated.inline_height),
            ('LTI Consumer', 1.0, 'iframe', 800),
        )

        self.lti13.grade_weight = -1
        self.lti13.save()
        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(self.lti13, {'defaults': {'modal_width': 50}})
        self.assertEqual(
            (raised.exception.category, raised.exception.field), ('invalid', 'defaults.grade_weight'),
        )
        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=self.lti13.pk).modal_width, 80)

        self.lti13.grade_weight = -1
        self.lti13.open_tool_in = 'popup'
        self.lti13.save()
        updated = self.update(self.lti13, {'defaults': {'grade_weight': 2.5, 'open_tool_in': 'modal'}})
        self.assertEqual((updated.grade_weight, updated.open_tool_in), (2.5, 'modal'))
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual((stored.grade_weight, stored.open_tool_in), (2.5, 'modal'))

        self.update(self.lti13, {'privacy': dict(PRIVACY_AUTHORED)})
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        before = {field: getattr(stored, field) for field in PRIVACY_WIRE_MEMBERS.values()}
        self.update(self.lti13, {'privacy': {}})
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual(
            {field: getattr(stored, field) for field in PRIVACY_WIRE_MEMBERS.values()}, before,
        )
        self.update(self.lti13, {'name': 'Metadata only'})
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual(stored.name, 'Metadata only')
        self.assertEqual(
            {field: getattr(stored, field) for field in PRIVACY_WIRE_MEMBERS.values()}, before,
        )

    def test_update_targeting_and_authorization_precedence(self):
        self.helpers['user_is_global_staff'].return_value = False
        self.helpers['user_is_course_admin'].return_value = False
        self.helpers['get_studio_accessible_course_keys'].return_value = [COURSE_KEY]
        non_staff = actor()

        with self.assertRaises(ReusableConfigurationError) as raised:
            update_reusable_configuration(non_staff, self.lti13.passport_id, {'name': 'Denied'})
        self.assertEqual((raised.exception.category, raised.exception.field), ('forbidden', None))
        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=self.lti13.pk).name, 'One Three')

        hidden = converted_row(
            name='Hidden', version=ReusableLtiConfiguration.LTI_1P3,
            context_type='course', context_key=COURSE_KEY,
        )
        self.helpers['get_studio_accessible_course_keys'].return_value = [OTHER_COURSE_KEY]
        self.helpers['user_is_course_admin'].reset_mock()
        for config_id in (hidden.passport_id, uuid.uuid4(), 'not-a-uuid'):
            with self.subTest(config_id=config_id):
                with self.assertRaises(ReusableConfigurationError) as raised:
                    update_reusable_configuration(non_staff, config_id, {'name': 'Changed'})
                self.assertEqual(raised.exception.category, 'not_found')
        # An invisible or unknown id must not be probed through the manage check either.
        self.helpers['user_is_course_admin'].assert_not_called()
        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=self.lti13.pk).name, 'One Three')

        self.helpers['get_studio_accessible_course_keys'].return_value = [COURSE_KEY]
        with self.assertRaises(ReusableConfigurationError) as raised:
            update_reusable_configuration(non_staff, self.lti13.passport_id, {'privacy': {'share_email': 1}})
        self.assertEqual((raised.exception.category, raised.exception.field), ('forbidden', None))

        self.helpers['get_studio_accessible_course_keys'].return_value = [OTHER_COURSE_KEY]
        with self.assertRaises(ReusableConfigurationError) as raised:
            update_reusable_configuration(non_staff, hidden.passport_id, {'privacy': {'share_email': 1}})
        self.assertEqual((raised.exception.category, raised.exception.field), ('not_found', None))

    def test_incomplete_configuration_is_remediable(self):
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

        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(incomplete, {'lti_1p3': {
                'launch_url': 'https://tool.example/launch',
                'oidc_url': 'https://tool.example/oidc',
            }})
        self.assertEqual(
            (raised.exception.category, raised.exception.field), ('invalid', 'lti_1p3.tool_key_mode'),
        )
        self.assertIsNone(ReusableLtiConfiguration.objects.get(pk=incomplete.pk).lti_1p3_launch_url)

        updated = self.update(incomplete, {'lti_1p3': complete_lti13_section()})
        self.assertEqual(updated.lti_1p3_tool_key_mode, 'public_key')
        self.assertEqual(updated.lti_1p3_tool_public_key, PUBLIC_KEY)
        self.assertEqual(updated.lti_1p3_tool_keyset_url, '')

    def test_version_can_be_initialized_once(self):
        configuration = converted_row()
        updated = self.update(configuration, {'version': 'lti_1p3'})
        self.assertEqual(updated.version, 'lti_1p3')
        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=configuration.pk).version, 'lti_1p3')

        version_first = converted_row(context_key=None)
        self.update(version_first, {'version': 'lti_1p3'})
        self.update(version_first, {'context': {'type': 'site'}})
        stored = ReusableLtiConfiguration.objects.get(pk=version_first.pk)
        self.assertEqual((stored.version, stored.context_type, stored.context_key), ('lti_1p3', 'site', ''))

        context_first = converted_row()
        self.update(context_first, {'context': {'type': 'course', 'key': COURSE_KEY}})
        self.update(context_first, {'version': 'lti_1p1'})
        stored = ReusableLtiConfiguration.objects.get(pk=context_first.pk)
        self.assertEqual(
            (stored.version, stored.context_type, stored.context_key), ('lti_1p1', 'course', COURSE_KEY),
        )

        inline = converted_row()
        updated = self.update(inline, {
            'version': 'lti_1p1',
            'name': '  Renamed  ',
            'defaults': {'display_name': 'Tool'},
        })
        self.assertEqual((updated.version, updated.name, updated.display_name), ('lti_1p1', 'Renamed', 'Tool'))
        self.assertIsNone(updated.lti_1p1_launch_url)

        with_connection = converted_row()
        updated = self.update(with_connection, {
            'version': 'lti_1p3',
            'lti_1p3': complete_lti13_section(),
        })
        self.assertEqual(updated.version, 'lti_1p3')
        self.assertEqual(updated.lti_1p3_tool_key_mode, 'public_key')
        self.assertEqual(updated.lti_1p3_tool_public_key, PUBLIC_KEY)

        for requested in ('lti_1p1', 'lti_1p3'):
            with self.subTest(requested=requested):
                with self.assertRaises(ReusableConfigurationError) as raised:
                    self.update(self.lti13, {'version': requested})
                self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', 'version'))
        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=self.lti13.pk).version, 'lti_1p3')

        unsupported = converted_row()
        for requested in ('lti_2p0', '', None, 'LTI_1P3'):
            with self.subTest(requested=requested):
                with self.assertRaises(ReusableConfigurationError) as raised:
                    self.update(unsupported, {'version': requested})
                self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', 'version'))
        self.assertIsNone(ReusableLtiConfiguration.objects.get(pk=unsupported.pk).version)

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

    def test_connection_edits_require_and_follow_the_assigned_version(self):
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

        versioned = converted_row()
        self.update(versioned, {'version': 'lti_1p3'})
        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(versioned, {'lti_1p1': {'launch_url': 'https://tool.example/launch'}})
        self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', 'lti_1p1'))

        updated = self.update(versioned, {'lti_1p3': complete_lti13_section()})
        self.assertEqual(updated.version, 'lti_1p3')
        self.assertEqual(updated.lti_1p3_tool_key_mode, 'public_key')
        self.assertEqual(updated.lti_1p3_tool_public_key, PUBLIC_KEY)

        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(self.lti11, {'lti_1p3': {'launch_url': 'https://tool.example/new'}})
        self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', 'lti_1p3'))
        self.assertEqual(
            ReusableLtiConfiguration.objects.get(pk=self.lti11.pk).lti_1p1_launch_url,
            'https://tool.example/launch',
        )

    def test_creation_context_is_assigned_once_and_is_context_only(self):
        unassigned = converted_row(name='Unassigned', context_key=None)
        updated = self.update(unassigned, {'context': {'type': 'site'}})
        self.assertEqual((updated.context_type, updated.context_key), ('site', ''))
        stored = ReusableLtiConfiguration.objects.get(pk=unassigned.pk)
        self.assertEqual((stored.context_type, stored.context_key), ('site', ''))

        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(unassigned, {'context': {'type': 'course', 'key': COURSE_KEY}})
        self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', 'context'))
        stored.refresh_from_db()
        self.assertEqual((stored.context_type, stored.context_key), ('site', ''))

        only = converted_row(name='Unassigned', context_key=None)
        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(only, {'name': 'Renamed', 'context': {'type': 'site'}})
        self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', 'context'))
        stored = ReusableLtiConfiguration.objects.get(pk=only.pk)
        self.assertEqual((stored.name, stored.context_type), ('Unassigned', None))

        mixed = converted_row(context_key=None)
        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(mixed, {'version': 'lti_1p3', 'context': {'type': 'site'}})
        self.assertEqual((raised.exception.category, raised.exception.field), ('invalid', 'context'))
        stored = ReusableLtiConfiguration.objects.get(pk=mixed.pk)
        self.assertEqual((stored.version, stored.context_type, stored.context_key), (None, None, None))

        copied = converted_row()
        updated = self.update(copied, {'context': {'type': 'course', 'key': OTHER_COURSE_KEY}})
        self.assertEqual((updated.context_type, updated.context_key), ('course', OTHER_COURSE_KEY))
        self.assertNotEqual(updated.context_key, COPIED_RAW_CONTEXT_KEY)
        stored = ReusableLtiConfiguration.objects.get(pk=copied.pk)
        self.assertEqual((stored.context_type, stored.context_key), ('course', OTHER_COURSE_KEY))

        site = converted_row()
        updated = self.update(site, {'context': {'type': 'site'}})
        self.assertEqual((updated.context_type, updated.context_key), ('site', ''))
        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=site.pk).context_key, '')

        before_version = converted_row()
        updated = self.update(before_version, {'context': {'type': 'organization', 'key': 'SomeOrg'}})
        self.assertEqual((updated.context_type, updated.context_key), ('organization', 'someorg'))
        self.assertIsNone(updated.version)
        self.assertIsNone(ReusableLtiConfiguration.objects.get(pk=before_version.pk).version)

    def test_update_locks_the_visible_target(self):
        self.helpers['user_is_global_staff'].return_value = False
        self.helpers['user_is_course_admin'].return_value = True
        self.helpers['get_studio_accessible_course_keys'].return_value = [COURSE_KEY]
        hidden = converted_row(
            name='Hidden', version=ReusableLtiConfiguration.LTI_1P1,
            context_type='course', context_key=OTHER_COURSE_KEY,
        )

        calls = []
        real_select_for_update = QuerySet.select_for_update

        def recording_select_for_update(queryset, *args, **kwargs):
            calls.append(queryset)
            return real_select_for_update(queryset, *args, **kwargs)

        with patch.object(QuerySet, 'select_for_update', recording_select_for_update):
            self.update(self.lti11, {'name': 'Renamed'})

        self.assertEqual(len(calls), 1)
        locked = calls[0]
        self.assertEqual(locked.model, ReusableLtiConfiguration)
        self.assertTrue(locked.query.where)
        self.assertEqual(set(locked.values_list('pk', flat=True)), {self.lti11.pk, self.lti13.pk})
        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=self.lti11.pk).name, 'Renamed')

        with self.assertRaises(ReusableConfigurationError) as raised:
            self.update(hidden, {'name': 'Hidden rename'})
        self.assertEqual((raised.exception.category, raised.exception.field), ('not_found', None))


class ReusableUpdateTransactionTests(PlatformAdapterMixin, TransactionTestCase):
    """Update atomicity and conflict reporting, observed outside an outer transaction."""

    def setUp(self):
        super().setUp()
        self.lti13 = create_reusable_configuration(self.actor, lti13_data()).configuration

    def update(self, changes):
        """Update the fixture row through the module interface."""
        return update_reusable_configuration(self.actor, self.lti13.passport_id, changes)

    def test_update_rolls_back_and_translates_conflicts(self):
        real_save = ReusableLtiConfiguration.save

        def save_then_fail(configuration):
            real_save(configuration)
            raise RuntimeError('injected failure')

        with patch.object(ReusableLtiConfiguration, 'save', save_then_fail):
            with self.assertRaisesRegex(RuntimeError, 'injected failure'):
                self.update({
                    'name': 'Renamed',
                    'lti_1p3': {'tool_key_mode': 'public_key', 'tool_public_key': PUBLIC_KEY},
                })
        stored = ReusableLtiConfiguration.objects.get(pk=self.lti13.pk)
        self.assertEqual(stored.name, 'One Three')
        self.assertEqual(stored.lti_1p3_tool_key_mode, 'keyset_url')
        self.assertEqual(stored.lti_1p3_tool_public_key, '')
        self.assertEqual(stored.lti_1p3_tool_keyset_url, 'https://tool.example/jwks')
        self.assertFalse(transaction.get_connection().in_atomic_block)

        def save_then_integrity(configuration):
            real_save(configuration)
            raise IntegrityError('duplicate')

        with patch.object(ReusableLtiConfiguration, 'save', save_then_integrity):
            with self.assertRaises(ReusableConfigurationError) as raised:
                self.update({'name': 'Taken'})
        self.assertEqual(raised.exception.category, 'conflict')
        self.assertEqual(ReusableLtiConfiguration.objects.get(pk=self.lti13.pk).name, 'One Three')
        self.assertFalse(transaction.get_connection().in_atomic_block)


class ReusableCopiedRowTests(ReusableMutationTestCase):
    """Converted rows keep their raw copied context and blank identity material."""

    def test_converted_row_metadata_update_keeps_raw_context_and_blank_material(self):
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
        self.assertEqual(stored.name, 'Renamed')

        raw = converted_row()
        self.update(raw, {
            'name': 'Renamed',
            'services': {'ags_mode': 'disabled'},
            'defaults': {'display_name': 'Tool'},
        })
        stored = ReusableLtiConfiguration.objects.get(pk=raw.pk)
        self.assertEqual(
            (stored.version, stored.context_type, stored.context_key),
            (None, None, COPIED_RAW_CONTEXT_KEY),
        )
        self.assertEqual((stored.name, stored.lti_advantage_ags_mode, stored.display_name),
                         ('Renamed', 'disabled', 'Tool'))


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
