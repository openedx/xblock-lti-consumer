"""
Unit tests for LTI models.
"""
import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import call, patch

import ddt
from ccx_keys.locator import CCXBlockUsageLocator
from Cryptodome.PublicKey import RSA
from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.test import TestCase
from edx_django_utils.cache import RequestCache
from opaque_keys.edx.locator import CourseLocator

from lti_consumer.exceptions import ReusableConfigurationUnavailable
from lti_consumer.lti_xblock import LtiConsumerXBlock
from lti_consumer.models import (
    CourseAllowPIISharingInLTIFlag,
    Lti1p3Passport,
    LtiAgsLineItem,
    LtiAgsScore,
    LtiConfiguration,
    LtiDlContentItem,
    ReusableLtiConfiguration,
)
from lti_consumer.tests.test_utils import TestBaseWithPatch, make_reusable_configuration, make_xblock

LAUNCH_URL = 'http://tool.example/launch'
DEEP_LINK_URL = 'http://tool.example/deep-link/launch'


@ddt.ddt
class TestLtiConfigurationModel(TestBaseWithPatch):
    """
    Unit tests for LtiConfiguration model methods.
    """
    def setUp(self):
        super().setUp()

        # Generate RSA and save exports
        rsa_key = RSA.generate(2048)
        self.public_key = rsa_key.publickey().export_key()

        self.xblock_attributes = {
            'lti_version': 'lti_1p3',
            'lti_1p3_launch_url': LAUNCH_URL,
            'lti_1p3_oidc_url': 'http://tool.example/oidc',
            # We need to set the values below because they are not automatically
            # generated until the user selects `lti_version == 'lti_1p3'` on the
            # Studio configuration view.
            'lti_1p3_tool_public_key': self.public_key,
            'lti_advantage_ags_mode': 'programmatic',
            'lti_advantage_deep_linking_enabled': True,
        }
        self.xblock = make_xblock('lti_consumer', LtiConsumerXBlock, self.xblock_attributes)
        self.xblock_1 = make_xblock('lti_consumer', LtiConsumerXBlock, self.xblock_attributes)
        self.xblock_2 = make_xblock('lti_consumer', LtiConsumerXBlock, self.xblock_attributes)
        self.xblock_3 = make_xblock('lti_consumer', LtiConsumerXBlock, self.xblock_attributes)

        patcher = patch(
            'lti_consumer.plugin.compat.load_enough_xblock',
        )
        self.addCleanup(patcher.stop)
        self._load_block_patch = patcher.start()
        self._load_block_patch.return_value = self.xblock

        # Runtime identity, keys and binding live on the reusable configurations only.
        self.reusable_configuration = make_reusable_configuration(
            lti_1p3_tool_public_key=self.public_key.decode(),
        )
        self.reusable_configuration_db = make_reusable_configuration(
            name='Database reusable configuration',
            lti_1p3_client_id='database-client-id',
            lti_1p3_tool_public_key=self.public_key.decode(),
        )

        # Creates an LTI configuration objects for testing
        self.lti_1p1_config = LtiConfiguration.objects.create(
            location=self.xblock.scope_ids.usage_id,
            version=LtiConfiguration.LTI_1P1
        )

        self.lti_1p3_config = LtiConfiguration.objects.create(
            location=self.xblock_1.scope_ids.usage_id,
            version=LtiConfiguration.LTI_1P3,
            reusable_configuration=self.reusable_configuration,
        )

        self.lti_1p3_config_db = LtiConfiguration.objects.create(
            location=self.xblock_2.scope_ids.usage_id,
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_ON_DB,
            lti_advantage_ags_mode='programmatic',
            lti_advantage_deep_linking_enabled=True,
            reusable_configuration=self.reusable_configuration_db,
        )

        self.lti_1p3_config_external = LtiConfiguration.objects.create(
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_EXTERNAL,
            location=self.xblock_3.scope_ids.usage_id,
        )

        self.lti_1p1_external = LtiConfiguration.objects.create(
            version=LtiConfiguration.LTI_1P1,
            config_store=LtiConfiguration.CONFIG_EXTERNAL,
            external_id="test-external-id"
        )

    def _get_1p3_config(self, **kwargs):
        """
        Helper function to create a LtiConfiguration object with specific attributes
        """
        defaults = kwargs
        defaults["version"] = LtiConfiguration.LTI_1P3
        defaults.setdefault("reusable_configuration", self.reusable_configuration)
        config, _ = LtiConfiguration.objects.update_or_create(
            location=self.xblock_1.scope_ids.usage_id,
            defaults=defaults,
        )
        return config

    @patch("lti_consumer.models.LtiConfiguration._get_lti_1p3_consumer")
    @patch("lti_consumer.models.LtiConfiguration._get_lti_1p1_consumer")
    def test_get_lti_consumer(self, lti_1p1_mock, lti_1p3_mock):
        """
        Check if the correct LTI consumer is returned.
        """
        self.lti_1p1_config.get_lti_consumer()
        lti_1p1_mock.assert_called()

        self.lti_1p3_config.get_lti_consumer()
        lti_1p3_mock.assert_called()

    def test_get_lti_1p3_consumer_invalid_config_store(self):
        """
        Check that NotImplementedError is raised when config_store is not a valid value.
        """
        self.lti_1p3_config.config_store = 'edX'

        with self.assertRaises(NotImplementedError):
            self.lti_1p3_config.get_lti_consumer()

    @patch("lti_consumer.models.LtiConsumer1p1")
    @patch("lti_consumer.models.get_external_config_from_filter")
    def test_get_lti_consumer_calls_filters_to_get_external_config(self, mock_filter, mock_consumer):
        """
        Check when get_lti_consumer is called on an object with config type set to external
        the configuration is fetched using the filters
        """
        mock_filter.return_value = {
            "lti_1p1_client_key": "client_key",
            "lti_1p1_client_secret": "secret",
            "lti_1p1_launch_url": "https://example.com"
        }
        mock_consumer.return_value = "consumer"

        self.assertEqual(self.lti_1p1_external.get_lti_consumer(), "consumer")
        mock_consumer.assert_called_once_with("https://example.com", "client_key", "secret")

    @patch("lti_consumer.models.LtiConfiguration._get_lti_1p3_consumer")
    @patch("lti_consumer.models.LtiConfiguration._get_lti_1p1_consumer")
    @patch("lti_consumer.models.get_external_config_from_filter")
    def test_get_lti_consumer_external_config_version_takes_priority(
        self, mock_filter, mock_1p1, mock_1p3
    ):
        """
        When config_store is external, the version from external config
        should take priority over the stored version field.
        """
        # External config returns LTI 1.3, even though local version is LTI 1.1
        mock_filter.return_value = {
            "version": LtiConfiguration.LTI_1P3,
            "lti_1p3_client_id": "test-client",
        }
        mock_1p3.return_value = "lti_1p3_consumer"
        mock_1p1.return_value = "lti_1p1_consumer"

        result = self.lti_1p1_external.get_lti_consumer()

        self.assertEqual(result, "lti_1p3_consumer")
        mock_1p3.assert_called_once()
        mock_1p1.assert_not_called()

    @patch("lti_consumer.models.get_external_config_from_filter")
    def test_get_effective_version_falls_back_on_external_without_version(
        self, mock_filter
    ):
        """
        External config without a "version" key falls back to the
        stored version field.
        """
        mock_filter.return_value = {"lti_1p3_client_id": "test"}
        config = LtiConfiguration.objects.create(
            version=LtiConfiguration.LTI_1P1,
            config_store=LtiConfiguration.CONFIG_EXTERNAL,
            external_id="test:x",
            location='block-v1:course+test+2020+type@problem+block@effver-fallback',
        )
        self.assertEqual(config.get_effective_version(), LtiConfiguration.LTI_1P1)

    def test_get_effective_version_non_external(self):
        """
        Non-external config_store returns the stored version directly.
        """
        config = LtiConfiguration.objects.create(
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_ON_XBLOCK,
            location='block-v1:course+test+2020+type@problem+block@effver-non-ext',
        )
        self.assertEqual(config.get_effective_version(), LtiConfiguration.LTI_1P3)

    def test_repr(self):
        """
        Test String representation of model.
        """
        dummy_location = 'block-v1:course+test+2020+type@problem+block@test'
        lti_config = LtiConfiguration.objects.create(
            location=dummy_location,
            version=LtiConfiguration.LTI_1P3
        )

        self.assertEqual(
            str(lti_config),
            f"[CONFIG_ON_XBLOCK] lti_1p3 - {dummy_location}"
        )

    @ddt.data(
        LtiConfiguration.CONFIG_ON_XBLOCK,
        LtiConfiguration.CONFIG_ON_DB,
        LtiConfiguration.CONFIG_EXTERNAL,
    )
    @patch('lti_consumer.models.get_external_config_from_filter')
    @patch('lti_consumer.models.external_multiple_launch_urls_enabled')
    def test_lti_consumer_ags_enabled(self, config_store, external_multiple_launch_urls_enabled_mock, filter_mock):
        """
        Check if LTI AGS is properly included when block is graded.
        """
        filter_mock.return_value = {'lti_advantage_ags_mode': 'programmatic'}
        external_multiple_launch_urls_enabled_mock.return_value = False
        config = self._get_1p3_config(
            config_store=config_store,
            lti_advantage_ags_mode='programmatic'
        )

        # Get LTI 1.3 consumer
        consumer = config.get_lti_consumer()

        # Check that LTI claim was included in extra claims
        self.assertEqual(
            consumer.extra_claims,
            {
                'https://purl.imsglobal.org/spec/lti-ags/claim/endpoint':
                {
                    'scope': [
                        'https://purl.imsglobal.org/spec/lti-ags/scope/lineitem',
                        'https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly',
                        'https://purl.imsglobal.org/spec/lti-ags/scope/score',
                    ],
                    'lineitems': f'https://example.com/api/lti_consumer/v1/lti/{config.id}/lti-ags',
                }
            }
        )

    @ddt.data(
        {'config_store': LtiConfiguration.CONFIG_ON_XBLOCK, 'expected_value': 'XBlock'},
        {'config_store': LtiConfiguration.CONFIG_ON_DB, 'expected_value': 'disabled'},
        {'config_store': LtiConfiguration.CONFIG_EXTERNAL, 'expected_value': 'external'},
    )
    @ddt.unpack
    @patch('lti_consumer.models.get_external_config_from_filter')
    def test_get_lti_advantage_ags_mode(self, filter_mock, config_store, expected_value):
        """
        Check if LTI AGS is properly returned.
        """
        filter_mock.return_value = {'lti_advantage_ags_mode': 'external'}
        config = self._get_1p3_config(config_store=config_store, lti_advantage_ags_mode='disabled')

        self.xblock.lti_advantage_ags_mode = 'XBlock'

        self.assertEqual(config.get_lti_advantage_ags_mode(), expected_value)

    @ddt.data(
        LtiConfiguration.CONFIG_ON_XBLOCK,
        LtiConfiguration.CONFIG_ON_DB,
        LtiConfiguration.CONFIG_EXTERNAL,
    )
    @patch('lti_consumer.models.get_external_config_from_filter')
    @patch('lti_consumer.models.external_multiple_launch_urls_enabled')
    def test_lti_consumer_ags_declarative(self, config_store, external_multiple_launch_urls_enabled, filter_mock):
        """
        Check that a LineItem is created if AGS is set to the declarative mode.
        """
        external_multiple_launch_urls_enabled.return_value = False
        filter_mock.return_value = {'lti_advantage_ags_mode': 'declarative'}
        self.xblock.lti_advantage_ags_mode = 'declarative'

        # Include `start` and `due` dates
        self.xblock.start = datetime.now(timezone.utc)
        self.xblock.due = datetime.now(timezone.utc) + timedelta(days=2)

        # Get LTI 1.3 consumer
        config = self._get_1p3_config(config_store=config_store, lti_advantage_ags_mode='declarative')

        consumer = config.get_lti_consumer()

        # Check if lineitem was created
        self.assertEqual(LtiAgsLineItem.objects.count(), 1)
        lineitem = LtiAgsLineItem.objects.get()
        self.assertEqual(lineitem.start_date_time, self.xblock.start)
        self.assertEqual(lineitem.end_date_time, self.xblock.due)

        # Check that there's no LineItem write permission in the token
        ags_claim = consumer.extra_claims['https://purl.imsglobal.org/spec/lti-ags/claim/endpoint']
        self.assertNotIn(
            'https://purl.imsglobal.org/spec/lti-ags/scope/lineitem',
            ags_claim.get('scope')
        )
        self.assertIn(
            'https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly',
            ags_claim.get('scope')
        )

    @ddt.data(
        LtiConfiguration.CONFIG_ON_XBLOCK,
        LtiConfiguration.CONFIG_ON_DB,
        LtiConfiguration.CONFIG_EXTERNAL,
    )
    @patch('lti_consumer.models.get_external_config_from_filter')
    @patch('lti_consumer.models.external_multiple_launch_urls_enabled')
    def test_lti_consumer_deep_linking_enabled(self, config_store, external_multiple_launch_urls_enabled, filter_mock):
        """
        Check if LTI DL is properly instanced when configured.
        """
        filter_mock.return_value = {'lti_advantage_deep_linking_enabled': True}
        external_multiple_launch_urls_enabled.return_value = False
        config = self._get_1p3_config(
            config_store=config_store,
            lti_advantage_deep_linking_enabled=True
        )

        # Get LTI 1.3 consumer
        consumer = config.get_lti_consumer()

        # Check that LTI DL class is instanced.
        self.assertTrue(consumer.dl)

    @ddt.data(
        {'config_store': LtiConfiguration.CONFIG_ON_XBLOCK, 'expected_value': False},
        {'config_store': LtiConfiguration.CONFIG_ON_DB, 'expected_value': True},
        {'config_store': LtiConfiguration.CONFIG_EXTERNAL, 'expected_value': True},
    )
    @ddt.unpack
    @patch('lti_consumer.models.get_external_config_from_filter')
    def test_get_lti_advantage_deep_linking_enabled(self, filter_mock, config_store, expected_value):
        """
        Check if LTI Deep Linking enabled is properly returned.
        """
        filter_mock.return_value = {'lti_advantage_deep_linking_enabled': True}
        config = self._get_1p3_config(config_store=config_store, lti_advantage_deep_linking_enabled=True)

        self.xblock.lti_advantage_deep_linking_enabled = False

        self.assertEqual(config.get_lti_advantage_deep_linking_enabled(), expected_value)

    @ddt.data(
        {'config_store': LtiConfiguration.CONFIG_ON_XBLOCK, 'expected_value': 'XBlock'},
        {'config_store': LtiConfiguration.CONFIG_ON_DB, 'expected_value': 'database'},
        {'config_store': LtiConfiguration.CONFIG_EXTERNAL, 'expected_value': 'external'},
    )
    @ddt.unpack
    @patch('lti_consumer.models.get_external_config_from_filter')
    def test_get_lti_advantage_deep_linking_launch_url(self, filter_mock, config_store, expected_value):
        """
        Check if LTI Deep Linking launch URL is properly returned.
        """
        filter_mock.return_value = {'lti_advantage_deep_linking_launch_url': 'external'}
        config = self._get_1p3_config(config_store=config_store, lti_advantage_deep_linking_launch_url='database')

        self.xblock.lti_advantage_deep_linking_launch_url = 'XBlock'

        self.assertEqual(config.get_lti_advantage_deep_linking_launch_url(), expected_value)

    @ddt.data(
        {'config_store': LtiConfiguration.CONFIG_ON_XBLOCK, 'expected_value': False},
        {'config_store': LtiConfiguration.CONFIG_ON_DB, 'expected_value': True},
        {'config_store': LtiConfiguration.CONFIG_EXTERNAL, 'expected_value': True},
    )
    @ddt.unpack
    @patch('lti_consumer.models.get_external_config_from_filter')
    def test_get_lti_advantage_nrps_enabled(self, filter_mock, config_store, expected_value):
        """
        Check if LTI Deep Linking launch URL is properly returned.
        """
        filter_mock.return_value = {'lti_advantage_enable_nrps': True}
        config = self._get_1p3_config(config_store=config_store, lti_advantage_enable_nrps=True)

        self.xblock.lti_advantage_enable_nrps = False

        self.assertEqual(config.get_lti_advantage_nrps_enabled(), expected_value)

    def test_existing_blank_signing_material_is_never_repaired(self):
        """
        An existing row with blank signing material is denied instead of being written.
        """
        reusable_configuration = make_reusable_configuration(generate_keys=False)
        placement = LtiConfiguration.objects.create(
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_ON_XBLOCK,
            location='block-v1:course+test+2020+type@problem+block@blank-keys',
            reusable_configuration=reusable_configuration,
        )

        with patch.object(ReusableLtiConfiguration, 'save') as save_mock:
            with self.assertRaises(ReusableConfigurationUnavailable):
                placement.get_runtime_identity()
            save_mock.assert_not_called()

        reusable_configuration.refresh_from_db()
        self.assertFalse(reusable_configuration.lti_1p3_internal_private_key)
        self.assertFalse(reusable_configuration.lti_1p3_internal_public_jwk)

    @ddt.data(
        ('lti_1p3_client_id', None),
        ('lti_1p3_internal_private_key', ''),
        ('lti_1p3_internal_private_key_id', ''),
        ('lti_1p3_internal_public_jwk', ''),
        ('lti_1p3_internal_public_jwk', 'not-json'),
        ('lti_1p3_internal_public_jwk', '[]'),
        ('lti_1p3_internal_public_jwk', '{"keys": []}'),
        ('lti_1p3_tool_public_key', ''),
    )
    @ddt.unpack
    def test_incomplete_runtime_identity_is_denied_without_writes(self, field, value):
        """
        A stored component that is missing or malformed denies identity without a write.
        """
        ReusableLtiConfiguration.objects.filter(pk=self.reusable_configuration.pk).update(**{field: value})
        placement = LtiConfiguration.objects.get(pk=self.lti_1p3_config.pk)

        with patch.object(ReusableLtiConfiguration, 'save') as save_mock:
            with self.assertRaises(ReusableConfigurationUnavailable):
                placement.get_runtime_identity()
            save_mock.assert_not_called()

    def test_public_jwk_must_match_the_signing_key(self):
        """
        A keyset that does not carry the stored signing key denies instead of publishing it.
        """
        other = make_reusable_configuration()
        ReusableLtiConfiguration.objects.filter(pk=self.reusable_configuration.pk).update(
            lti_1p3_internal_public_jwk=other.lti_1p3_internal_public_jwk,
        )
        placement = LtiConfiguration.objects.get(pk=self.lti_1p3_config.pk)

        with self.assertRaises(ReusableConfigurationUnavailable):
            placement.get_runtime_identity()

    def test_unparsable_signing_key_is_denied(self):
        """
        A stored private key that cannot be parsed is denied rather than regenerated.
        """
        ReusableLtiConfiguration.objects.filter(pk=self.reusable_configuration.pk).update(
            lti_1p3_internal_private_key='not-a-private-key',
        )
        placement = LtiConfiguration.objects.get(pk=self.lti_1p3_config.pk)

        with self.assertRaises(ReusableConfigurationUnavailable):
            placement.get_runtime_identity()

    def test_encrypted_signing_key_is_denied_without_writes(self):
        """
        A password-encrypted PEM is unusable without a password and is denied without writes.
        """
        encrypted_key = RSA.generate(2048).export_key('PEM', passphrase='secret').decode()
        ReusableLtiConfiguration.objects.filter(pk=self.reusable_configuration.pk).update(
            lti_1p3_internal_private_key=encrypted_key,
        )
        placement = LtiConfiguration.objects.get(pk=self.lti_1p3_config.pk)

        with patch.object(ReusableLtiConfiguration, 'save') as save_mock:
            with self.assertRaises(ReusableConfigurationUnavailable):
                placement.get_runtime_identity()
            save_mock.assert_not_called()

    def test_public_only_signing_key_is_denied_without_writes(self):
        """
        A valid public-only PEM in the signing-key field is denied, not treated as a private key.
        """
        ReusableLtiConfiguration.objects.filter(pk=self.reusable_configuration.pk).update(
            lti_1p3_internal_private_key=self.public_key.decode(),
        )
        placement = LtiConfiguration.objects.get(pk=self.lti_1p3_config.pk)

        with patch.object(ReusableLtiConfiguration, 'save') as save_mock:
            with self.assertRaises(ReusableConfigurationUnavailable):
                placement.get_runtime_identity()
            save_mock.assert_not_called()

    def test_clean(self):
        self.lti_1p3_config.config_store = self.lti_1p3_config.CONFIG_ON_XBLOCK
        self.lti_1p3_config.location = None

        with self.assertRaises(ValidationError):
            self.lti_1p3_config.clean()

        self.lti_1p3_config.config_store = self.lti_1p3_config.CONFIG_EXTERNAL
        self.lti_1p3_config.external_id = None

        with self.assertRaises(ValidationError):
            self.lti_1p3_config.clean()

        self.lti_1p3_config.external_id = 'invalid-external-id'

        with self.assertRaises(ValidationError):
            self.lti_1p3_config.clean()

        self.lti_1p3_config.config_store = self.lti_1p3_config.CONFIG_ON_DB

        # The reusable registration refuses a public-key mode without a key.
        self.lti_1p3_config_db.reusable_configuration.lti_1p3_tool_key_mode = 'public_key'
        self.lti_1p3_config_db.reusable_configuration.lti_1p3_tool_public_key = ''

        with self.assertRaises(ValidationError):
            self.lti_1p3_config_db.reusable_configuration.full_clean()

        self.lti_1p3_config.lti_1p3_proctoring_enabled = True
        self.lti_1p3_config.external_id = 'test_id'

        for config_store in [self.lti_1p3_config.CONFIG_ON_XBLOCK, self.lti_1p3_config.CONFIG_EXTERNAL]:
            self.lti_1p3_config.config_store = config_store
            with self.assertRaises(ValidationError):
                self.lti_1p3_config.clean()

    def test_clean_requires_a_reusable_configuration_for_database_1p3(self):
        """
        A model-stored LTI 1.3 placement must be bound to a reusable configuration.
        """
        placement = LtiConfiguration(
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_ON_DB,
            location='block-v1:course+test+2020+type@problem+block@unbound-clean',
        )

        with self.assertRaisesMessage(ValidationError, 'requires a reusable configuration'):
            placement.clean()

    @ddt.data(
        (LAUNCH_URL, DEEP_LINK_URL, [], [LAUNCH_URL, DEEP_LINK_URL]),
        (LAUNCH_URL, DEEP_LINK_URL, ["http://other.url"], ["http://other.url"]),
    )
    @ddt.unpack
    def test_get_redirect_uris_for_xblock_model_returns_expected(
            self, launch_url, deep_link_url, redirect_uris, expected):
        """
        Returns expected redirect uris for xblock model
        """
        self.xblock.lti_1p3_launch_url = launch_url
        self.xblock.lti_advantage_deep_linking_launch_url = deep_link_url
        self.xblock.lti_1p3_redirect_uris = redirect_uris

        assert self.lti_1p3_config.get_lti_1p3_redirect_uris() == expected

    @ddt.data(
        (LAUNCH_URL, DEEP_LINK_URL, [], [LAUNCH_URL, DEEP_LINK_URL]),
        (LAUNCH_URL, DEEP_LINK_URL, ["http://other.url"], ["http://other.url"]),
    )
    @ddt.unpack
    def test_get_redirect_uris_for_db_model_returns_expected(
            self, launch_url, deep_link_url, redirect_uris, expected):
        """
        Returns expected redirect uris for db model
        """
        self.lti_1p3_config_db.lti_1p3_launch_url = launch_url
        self.lti_1p3_config_db.lti_advantage_deep_linking_launch_url = deep_link_url
        self.lti_1p3_config_db.lti_1p3_redirect_uris = redirect_uris
        self.lti_1p3_config_db.save()

        assert self.lti_1p3_config_db.get_lti_1p3_redirect_uris() == expected

    @patch('lti_consumer.models.choose_lti_1p3_redirect_uris', return_value=None)
    @patch('lti_consumer.models.get_external_config_from_filter')
    def test_get_redirect_uris_with_external_config(
        self,
        get_external_config_from_filter_mock,
        choose_lti_1p3_redirect_uris,
    ):
        """
        Test get_redirect_uris with external configuration.
        """
        external_config = {
            'lti_1p3_redirect_uris': ['external-redirect-uris'],
            'lti_1p3_launch_url': LAUNCH_URL,
            'lti_advantage_deep_linking_launch_url': DEEP_LINK_URL,
        }
        get_external_config_from_filter_mock.return_value = external_config

        self.assertEqual(self.lti_1p3_config_external.get_lti_1p3_redirect_uris(), None)
        get_external_config_from_filter_mock.assert_called_once_with({}, self.lti_1p3_config_external.external_id)
        choose_lti_1p3_redirect_uris.assert_called_once_with(
            external_config['lti_1p3_redirect_uris'],
            external_config['lti_1p3_launch_url'],
            external_config['lti_advantage_deep_linking_launch_url'],
        )

    def test_placement_creation_does_not_create_or_bind_a_registration(self):
        """
        Saving a placement never creates, attaches or edits a catalog registration.
        """
        xblock = make_xblock('lti_consumer', LtiConsumerXBlock, self.xblock_attributes)
        xblock.lti_1p3_passport_id = ''
        self._load_block_patch.return_value = xblock
        before = ReusableLtiConfiguration.objects.count()

        with patch.object(xblock, 'save') as block_save_mock, \
                patch('lti_consumer.plugin.compat.save_xblock') as save_xblock_mock:
            config = LtiConfiguration.objects.create(
                location=xblock.scope_ids.usage_id,
                version=LtiConfiguration.LTI_1P3,
            )

        self.assertIsNone(config.reusable_configuration)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), before)
        self.assertFalse(Lti1p3Passport.objects.exists())
        block_save_mock.assert_not_called()
        save_xblock_mock.assert_not_called()
        self.assertEqual(xblock.lti_1p3_passport_id, '')

    def test_orphan_block_uuid_is_not_attached_implicitly(self):
        """
        A persisted block UUID never attaches its catalog row on save or identity read.
        """
        configuration = make_reusable_configuration(name='Copied row')
        xblock = make_xblock('lti_consumer', LtiConsumerXBlock, self.xblock_attributes)
        xblock.lti_1p3_passport_id = str(configuration.passport_id)
        self._load_block_patch.return_value = xblock
        before = ReusableLtiConfiguration.objects.count()

        placement = LtiConfiguration.objects.create(
            location=xblock.scope_ids.usage_id,
            version=LtiConfiguration.LTI_1P3,
        )

        with self.assertRaises(ReusableConfigurationUnavailable):
            placement.get_runtime_identity()

        placement.refresh_from_db()
        self.assertIsNone(placement.reusable_configuration_id)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), before)
        configuration.refresh_from_db()
        self.assertEqual(configuration.name, 'Copied row')

    def test_runtime_identity_and_keys_come_from_the_reusable_configuration(self):
        """
        A retained passport is never an identity fallback, even when a placement points at one.
        """
        passport = Lti1p3Passport.objects.create(
            lti_1p3_client_id='legacy-client-id',
            lti_1p3_tool_public_key='legacy-tool-key',
            lti_1p3_internal_private_key='legacy-private-key',
            lti_1p3_internal_private_key_id='legacy-key-id',
            lti_1p3_internal_public_jwk='{"keys": []}',
        )
        placement = LtiConfiguration.objects.create(
            location='block-v1:course+test+2020+type@problem+block@identity',
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_ON_DB,
            lti_1p3_passport=passport,
            reusable_configuration=self.reusable_configuration_db,
        )

        configuration = placement.reusable_configuration
        self.assertIsNotNone(configuration)
        self.assertEqual(placement.passport_id, configuration.passport_id)
        self.assertEqual(placement.lti_1p3_client_id, configuration.lti_1p3_client_id)
        self.assertEqual(placement.lti_1p3_tool_public_key, configuration.lti_1p3_tool_public_key)
        self.assertEqual(placement.lti_1p3_tool_keyset_url, configuration.lti_1p3_tool_keyset_url)
        self.assertEqual(placement.lti_1p3_private_key_id, configuration.lti_1p3_internal_private_key_id)
        self.assertEqual(
            placement.lti_1p3_public_jwk,
            json.loads(configuration.lti_1p3_internal_public_jwk),
        )
        self.assertEqual(placement.lti_1p3_client_id, 'database-client-id')
        self.assertNotEqual(placement.lti_1p3_client_id, 'legacy-client-id')

    def test_unbound_placement_denies_identity_without_writing(self):
        """
        An unbound placement denies identity and never creates or attaches a registration.
        """
        placement = LtiConfiguration.objects.create(
            location='block-v1:course+test+2020+type@problem+block@unbound-identity',
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_ON_DB,
        )
        before = ReusableLtiConfiguration.objects.count()

        for accessor in ('passport_id', 'lti_1p3_client_id', 'lti_1p3_public_jwk'):
            with self.assertRaises(ReusableConfigurationUnavailable):
                getattr(placement, accessor)

        with self.assertRaises(ReusableConfigurationUnavailable):
            placement.get_runtime_identity()
        with self.assertRaises(ReusableConfigurationUnavailable):
            placement.get_lti_consumer()

        placement.refresh_from_db()
        self.assertIsNone(placement.reusable_configuration_id)
        self.assertEqual(ReusableLtiConfiguration.objects.count(), before)
        self.assertFalse(Lti1p3Passport.objects.exists())

    def test_stored_null_version_is_never_repaired(self):
        """
        A converted row keeps its unassigned version; resolution never borrows one.
        """
        configuration = make_reusable_configuration(version=None)
        placement = LtiConfiguration.objects.create(
            location='block-v1:course+test+2020+type@problem+block@null-version',
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_ON_DB,
            reusable_configuration=configuration,
        )

        self.assertIs(placement.reusable_configuration, configuration)
        with self.assertRaises(ReusableConfigurationUnavailable):
            placement.get_runtime_identity()
        configuration.refresh_from_db()
        self.assertIsNone(configuration.version)
        with self.assertRaises(ReusableConfigurationUnavailable):
            placement.get_lti_consumer()

    def test_deployment_id_uses_the_stored_value_or_the_historical_one(self):
        """
        A copied registration keeps the historical "1" until a deployment ID is stored.
        """
        placement = LtiConfiguration.objects.create(
            location='block-v1:course+test+2020+type@problem+block@deployment',
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_ON_DB,
            reusable_configuration=self.reusable_configuration_db,
        )

        self.reusable_configuration_db.lti_1p3_deployment_id = ''
        self.reusable_configuration_db.save()
        placement = LtiConfiguration.objects.get(pk=placement.pk)
        self.assertEqual(placement.get_runtime_identity().deployment_id, "1")

        self.reusable_configuration_db.lti_1p3_deployment_id = 'deployment-7'
        self.reusable_configuration_db.save()
        placement = LtiConfiguration.objects.get(pk=placement.pk)
        self.assertEqual(placement.get_runtime_identity().deployment_id, 'deployment-7')

    def test_effective_version_reads_the_reusable_configuration(self):
        """
        A matching bound configuration's stored version is the effective version.
        """
        self.reusable_configuration_db.version = LtiConfiguration.LTI_1P1
        self.reusable_configuration_db.save()
        LtiConfiguration.objects.filter(pk=self.lti_1p3_config_db.pk).update(version=LtiConfiguration.LTI_1P1)

        placement = LtiConfiguration.objects.get(pk=self.lti_1p3_config_db.pk)
        self.assertEqual(placement.get_effective_version(), LtiConfiguration.LTI_1P1)

    @ddt.data(
        (LtiConfiguration.LTI_1P1, LtiConfiguration.LTI_1P3),
        (LtiConfiguration.LTI_1P3, LtiConfiguration.LTI_1P1),
    )
    @ddt.unpack
    def test_version_mismatch_refuses_a_consumer_without_changing_versions(
        self, placement_version, configuration_version,
    ):
        """
        A placement and its bound registration must agree on the protocol, in either direction.
        """
        configuration = make_reusable_configuration(version=configuration_version)
        placement = LtiConfiguration.objects.create(
            location=f'block-v1:course+test+2020+type@problem+block@mismatch-{placement_version}',
            version=placement_version,
            config_store=LtiConfiguration.CONFIG_ON_DB,
            reusable_configuration=configuration,
        )

        self.assertEqual(placement.get_effective_version(), configuration_version)

        with patch.object(LtiConfiguration, 'save') as save_mock, \
                patch.object(ReusableLtiConfiguration, 'save') as catalog_save_mock:
            with self.assertRaises(ReusableConfigurationUnavailable):
                placement.get_lti_consumer()
            save_mock.assert_not_called()
            catalog_save_mock.assert_not_called()

        placement.refresh_from_db()
        configuration.refresh_from_db()
        self.assertEqual(placement.version, placement_version)
        self.assertEqual(configuration.version, configuration_version)

    def test_unassigned_version_refuses_a_consumer(self):
        """
        A NULL stored version denies runtime instead of falling back to the placement version.
        """
        configuration = make_reusable_configuration(version=None)
        placement = LtiConfiguration.objects.create(
            location='block-v1:course+test+2020+type@problem+block@unassigned-version',
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_ON_DB,
            reusable_configuration=configuration,
        )

        self.assertIsNone(placement.get_effective_version())
        with self.assertRaises(ReusableConfigurationUnavailable):
            placement.get_lti_consumer()

    def test_inactive_configuration_still_builds_a_consumer(self):
        """
        Inactive gates launches and new tokens, not keyset reads or service authentication.
        """
        self.reusable_configuration_db.is_active = False
        self.reusable_configuration_db.save()

        consumer = LtiConfiguration.objects.get(pk=self.lti_1p3_config_db.pk).get_lti_consumer()

        self.assertEqual(consumer.client_id, 'database-client-id')

    def test_consumer_uses_reusable_identity_and_stored_deployment_id(self):
        """
        The constructed consumer carries the reusable identity, keys and deployment ID.
        """
        configuration = make_reusable_configuration(
            lti_1p3_client_id='reusable-client-id',
            lti_1p3_deployment_id='deployment-7',
            lti_1p3_tool_public_key=self.public_key.decode(),
        )
        placement = LtiConfiguration.objects.create(
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_ON_DB,
            location='block-v1:course+test+2020+type@problem+block@consumer-identity',
            lti_1p3_launch_url=LAUNCH_URL,
            lti_1p3_oidc_url='http://tool.example/oidc',
            reusable_configuration=configuration,
        )

        consumer = placement.get_lti_consumer()

        self.assertEqual(consumer.client_id, 'reusable-client-id')
        self.assertEqual(consumer.deployment_id, 'deployment-7')
        self.assertIsNotNone(consumer.key_handler.key)

    @patch.object(LtiConfiguration, 'sync_configurations')
    def test_save(self, sync_configurations_mock):
        """Test save method."""
        self.assertEqual(self.lti_1p3_config.save(), None)
        sync_configurations_mock.assert_called_once_with()

    @patch('lti_consumer.models.isinstance', return_value=True)
    @patch.object(LtiConfiguration.objects, 'filter')
    @patch('lti_consumer.models.model_to_dict')
    @patch('lti_consumer.models.setattr')
    def test_sync_configurations_with_ccx_location(
        self,
        setattr_mock,
        model_to_dict_mock,
        filter_mock,
        isinstance_mock,
    ):
        """
        Test sync_configurations method with CCX location.
        """
        model_to_dict_mock.return_value = {'test': 'test'}
        self.lti_1p3_config.location = 'ccx-block-v1:course+test+2020+ccx@1+type@problem+block@test'

        self.assertEqual(self.lti_1p3_config.sync_configurations(), None)
        isinstance_mock.assert_called_once_with(self.lti_1p3_config.location, CCXBlockUsageLocator)
        filter_mock.assert_has_calls([
            call(location=self.lti_1p3_config.location.to_block_locator()),
            call().first(),
        ])
        model_to_dict_mock.assert_called_once_with(
            filter_mock.return_value.first(),
            ['id', 'config_id', 'location', 'external_config'],
        )
        setattr_mock.assert_called_once_with(self.lti_1p3_config, 'test', 'test')

    @patch('lti_consumer.models.isinstance', return_value=False)
    @patch.object(LtiConfiguration.objects, 'filter')
    @patch('lti_consumer.models.model_to_dict')
    def test_sync_configurations_with_location(
        self,
        model_to_dict_mock,
        filter_mock,
        isinstance_mock,
    ):
        """
        Test sync_configurations method with location.
        """
        self.assertEqual(self.lti_1p3_config.sync_configurations(), None)
        isinstance_mock.assert_called_once_with(self.lti_1p3_config.location, CCXBlockUsageLocator)
        filter_mock.assert_has_calls([
            call(location__endswith=str(self.lti_1p3_config.location).split('@')[-1]),
            call().filter(location__startswith=CCXBlockUsageLocator.CANONICAL_NAMESPACE),
            call().filter().exclude(id=self.lti_1p3_config.pk),
            call().filter().exclude().update(**model_to_dict_mock),
        ])
        model_to_dict_mock.assert_called_once_with(
            self.lti_1p3_config,
            ['id', 'config_id', 'location', 'external_config'],
        )

    @patch('lti_consumer.models.isinstance', return_value=False)
    @patch.object(LtiConfiguration.objects, 'filter', side_effect=IndexError())
    @patch('lti_consumer.models.log.exception')
    def test_sync_configurations_with_invalid_location(
        self,
        log_exception_mock,
        filter_mock,
        isinstance_mock,
    ):
        """
        Test sync_configurations method with invalid location.
        """
        self.assertEqual(self.lti_1p3_config.sync_configurations(), None)
        isinstance_mock.assert_called_once_with(self.lti_1p3_config.location, CCXBlockUsageLocator)
        filter_mock.assert_called_once_with(location__endswith=str(self.lti_1p3_config.location).split('@')[-1])
        log_exception_mock.assert_called_once_with(
            f'Failed to query children CCX LTI configurations: '
            f'Failed to parse main LTI configuration location: {self.lti_1p3_config.location}'
        )

    @patch('lti_consumer.models.get_external_config_from_filter')
    @patch('lti_consumer.models.external_multiple_launch_urls_enabled')
    def test_external_lti_consumer_1p3_returns_launch_url_from_block(
        self,
        external_multiple_launch_urls_enabled,
        filter_mock
    ):
        """
        Verify that the external LTI consumer uses the block's launch URL when multiple launch URLs are enabled.

        When the `external_multiple_launch_urls_enabled` flag is True, the consumer's
        `launch_url` should be set to the `lti_1p3_launch_ur`l` from the loaded block rather than
        the default URL provided by the external configuration.
        """
        external_multiple_launch_urls_enabled.return_value = True
        filter_mock.return_value = {
            'lti_1p3_launch_url': 'http://launch-url-from-config.example/launch',
        }
        consumer = self.lti_1p3_config_external.get_lti_consumer()
        self.assertEqual(consumer.launch_url, self.xblock.lti_1p3_launch_url)


class TestLtiAgsLineItemModel(TestBaseWithPatch):
    """
    Unit tests for LtiAgsLineItem model methods.
    """
    def setUp(self):
        super().setUp()

        self.dummy_location = 'block-v1:course+test+2020+type@problem+block@test'
        self.lti_ags_model = LtiAgsLineItem.objects.create(
            resource_id="test-id",
            label="this-is-a-test",
            resource_link_id=self.dummy_location,
            score_maximum=100,
        )

    def test_repr(self):
        """
        Test String representation of model.
        """
        self.assertEqual(
            str(self.lti_ags_model),
            "block-v1:course+test+2020+type@problem+block@test - this-is-a-test"
        )


class TestLtiAgsScoreModel(TestBaseWithPatch):
    """
    Unit tests for LtiAgsScore model methods.
    """

    def setUp(self):
        super().setUp()

        # patch things related to LtiAgsScore post_save signal receiver
        compat_mock = patch("lti_consumer.signals.signals.compat")
        self.addCleanup(compat_mock.stop)
        self._compat_mock = compat_mock.start()
        self._compat_mock.load_block_as_user.return_value = make_xblock(
            'lti_consumer', LtiConsumerXBlock, {
                'due': datetime.now(timezone.utc),
                'graceperiod': timedelta(days=2),
            }
        )

        self.dummy_location = 'block-v1:course+test+2020+type@problem+block@test'

        self.lti_config = LtiConfiguration.objects.create(
            config_id='6c440bf4-face-beef-face-e8bcfb1e53bd',
            location=self.dummy_location,
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_ON_XBLOCK,
        )

        self.line_item = LtiAgsLineItem.objects.create(
            lti_configuration=self.lti_config,
            resource_id="test-id",
            label="this-is-a-test",
            resource_link_id=self.dummy_location,
            score_maximum=100,
        )
        self.score = LtiAgsScore.objects.create(
            line_item=self.line_item,
            timestamp='2020-10-04T18:54:46.736+00:00',
            score_given=10,
            score_maximum=100,
            comment='Better luck next time',
            grading_progress=LtiAgsScore.FULLY_GRADED,
            activity_progress=LtiAgsScore.COMPLETED,
            user_id='test-user'
        )

    def test_no_score_max_fails_when_setting_score(self):
        """
        Test if the model raises an exception when trying to set a `scoreGiven` without `scoreMaximum`.
        """
        with self.assertRaises(ValidationError):
            self.score.score_given = 10
            self.score.score_maximum = None
            self.score.save()

    def test_no_score_max_fails_when_setting_zero_score(self):
        """
        Test that a `scoreGiven` of 0 without `scoreMaximum` is rejected too, not just a
        truthy `scoreGiven`.
        """
        with self.assertRaises(ValidationError):
            self.score.score_given = 0
            self.score.score_maximum = None
            self.score.save()

    def test_score_max_fails_when_zero_with_score_given_set(self):
        """
        Test that `scoreMaximum=0` with a set `scoreGiven` is rejected, not just
        `scoreMaximum=None`. Zero is not a usable denominator.
        """
        with self.assertRaises(ValidationError):
            self.score.score_given = 10
            self.score.score_maximum = 0
            self.score.save()

    def test_repr(self):
        """
        Test String representation of model.
        """
        self.assertEqual(
            str(self.score),
            f"LineItem {self.line_item.id}: score 10.0 out of 100.0 - FullyGraded"
        )


class TestLtiDlContentItemModel(TestBaseWithPatch):
    """
    Unit tests for LtiDlContentItem model methods.
    """
    def setUp(self):
        super().setUp()

        self.xblock_attributes = {'lti_version': 'lti_1p3'}
        self.xblock = make_xblock('lti_consumer', LtiConsumerXBlock, self.xblock_attributes)

        self.lti_1p3_config = LtiConfiguration.objects.create(
            location=self.xblock.scope_ids.usage_id,
            version=LtiConfiguration.LTI_1P3
        )

    def test_repr(self):
        """
        Test String representation of model.
        """

        content_item = LtiDlContentItem.objects.create(
            lti_configuration=self.lti_1p3_config,
            content_type=LtiDlContentItem.IMAGE,
            attributes={}
        )
        self.assertEqual(
            str(content_item),
            "[CONFIG_ON_XBLOCK] lti_1p3 - "
            f"{content_item.lti_configuration.location}: image"
        )


@contextmanager
def lti_consumer_fields_editing_flag(course_id, enabled_for_course=False):
    """
    Yields CourseEditLTIFieldsEnabledFlag record for unit tests

    Arguments:
        course_id (CourseLocator): course locator to control this feature for.
        enabled_for_course (bool): whether feature is enabled for 'course_id'
    """
    RequestCache.clear_all_namespaces()
    CourseAllowPIISharingInLTIFlag.objects.create(course_id=course_id, enabled=enabled_for_course)
    yield


@ddt.ddt
class TestLTIConsumerHideFieldsFlag(TestBaseWithPatch):
    """
    Tests the behavior of the flags for lti consumer fields' editing feature.
    These are set via Django admin settings.
    """

    def setUp(self):
        super().setUp()
        self.course_id = CourseLocator(org="edx", course="course", run="run")

    @ddt.data(
        (True, True),
        (True, False),
        (False, True),
        (False, False),
    )
    @ddt.unpack
    def test_lti_fields_editing_feature_flags(self, enabled_for_course, is_already_sharing_learner_info):
        """
        Test that feature flag works correctly with course-specific configuration in combination with
        a boolean which indicates whether a course-run already sharing learner username/email - given
        the course-specific configuration record is present.
        """
        with lti_consumer_fields_editing_flag(
            course_id=self.course_id,
            enabled_for_course=enabled_for_course
        ):
            feature_enabled = CourseAllowPIISharingInLTIFlag.lti_access_to_learners_editable(
                self.course_id,
                is_already_sharing_learner_info,
            )
            self.assertEqual(feature_enabled, enabled_for_course)

    @ddt.data(True, False)
    def test_lti_fields_editing_is_backwards_compatible(self, is_already_sharing_learner_info):
        """
        Test that feature flag works correctly with a boolean which indicates whether a course-run already
        sharing learner username/email - given the course-specific configuration record is not set previously.

        This tests the backward compatibility which currently is: if an existing course run is already
        sharing learner information then this feature should be enabled for that course run by default.
        """
        feature_enabled = CourseAllowPIISharingInLTIFlag.lti_access_to_learners_editable(
            self.course_id,
            is_already_sharing_learner_info,
        )
        feature_flag_created = CourseAllowPIISharingInLTIFlag.objects.filter(course_id=self.course_id).exists()
        self.assertEqual(feature_flag_created, is_already_sharing_learner_info)
        self.assertEqual(feature_enabled, is_already_sharing_learner_info)

    def test_enable_disable_course_flag(self):
        """
        Ensures that the flag, once enabled for a course, can also be disabled.
        """
        with lti_consumer_fields_editing_flag(
            course_id=self.course_id,
            enabled_for_course=True
        ):
            self.assertTrue(CourseAllowPIISharingInLTIFlag.lti_access_to_learners_editable(self.course_id, False))

        with lti_consumer_fields_editing_flag(
            course_id=self.course_id,
            enabled_for_course=False
        ):
            self.assertFalse(CourseAllowPIISharingInLTIFlag.lti_access_to_learners_editable(self.course_id, False))


class TestLti1p3PassportKeysetUrl(TestCase):
    """
    The retained passport keeps its readers and writers, but its keyset URL column widens to 500.

    Validation is Django's ordinary CharField max_length on the field and through the model
    form: no custom validator and no new placement field.
    """

    KEYSET_URL = 'http://tool.example/.well-known/jwks.json'

    def keyset_url(self, length):
        """Return a URL-shaped value of exactly the requested length."""
        return self.KEYSET_URL + 'x' * (length - len(self.KEYSET_URL))

    def test_a_500_character_keyset_url_is_accepted(self):
        field = Lti1p3Passport._meta.get_field('lti_1p3_tool_keyset_url')
        self.assertEqual(field.max_length, 500)

        passport = Lti1p3Passport(lti_1p3_tool_keyset_url=self.keyset_url(500))
        passport.full_clean()
        passport.save()
        passport.refresh_from_db()
        self.assertEqual(len(passport.lti_1p3_tool_keyset_url), 500)

    def test_the_keyset_url_is_validated_through_the_model_form(self):
        class PassportForm(forms.ModelForm):
            class Meta:
                model = Lti1p3Passport
                fields = ['name', 'lti_1p3_tool_public_key', 'lti_1p3_tool_keyset_url']

        accepted = PassportForm(data={
            'name': 'Widened',
            'lti_1p3_tool_public_key': 'tool-key',
            'lti_1p3_tool_keyset_url': self.keyset_url(500),
        })
        self.assertTrue(accepted.is_valid(), accepted.errors)

        rejected = PassportForm(data={
            'name': 'Too long',
            'lti_1p3_tool_public_key': 'tool-key',
            'lti_1p3_tool_keyset_url': self.keyset_url(501),
        })
        self.assertFalse(rejected.is_valid())
        self.assertIn('lti_1p3_tool_keyset_url', rejected.errors)

        with self.assertRaises(ValidationError):
            Lti1p3Passport(lti_1p3_tool_keyset_url=self.keyset_url(501)).full_clean()


class TestRetainedPassportBinding(TestCase):
    """The old passport FK stays authoritative and unbinds a placement when its passport goes."""

    def test_deleting_the_retained_passport_unbinds_the_placement(self):
        self.assertIs(
            LtiConfiguration._meta.get_field('lti_1p3_passport').remote_field.on_delete,
            models.SET_NULL,
        )

        passport = Lti1p3Passport.objects.create(name='Retained passport')
        placement = LtiConfiguration.objects.create(lti_1p3_passport=passport)
        placement.refresh_from_db()

        passport.delete()
        placement.refresh_from_db()
        self.assertIsNone(placement.lti_1p3_passport_id)


class ReusableConfigurationModelTests(TestCase):
    """Signing-key generation, display and tool-key validation."""

    def make_configuration(self, **kwargs):
        values = {'name': 'Model test', 'version': ReusableLtiConfiguration.LTI_1P3}
        values.update(kwargs)
        return ReusableLtiConfiguration.objects.create(**values)

    def test_generate_lti_1p3_keys_if_missing_stores_signing_material(self):
        configuration = self.make_configuration()
        self.assertFalse(configuration.lti_1p3_internal_private_key)
        self.assertFalse(configuration.lti_1p3_internal_private_key_id)
        self.assertFalse(configuration.lti_1p3_internal_public_jwk)

        configuration.generate_lti_1p3_keys_if_missing()

        configuration.refresh_from_db()
        self.assertTrue(
            configuration.lti_1p3_internal_private_key.startswith('-----BEGIN RSA PRIVATE KEY-----')
        )
        self.assertEqual(uuid.UUID(configuration.lti_1p3_internal_private_key_id).version, 4)
        key_set = json.loads(configuration.lti_1p3_internal_public_jwk)['keys']
        self.assertEqual(key_set[0]['kty'], 'RSA')
        self.assertEqual(key_set[0]['kid'], configuration.lti_1p3_internal_private_key_id)

    def test_generate_lti_1p3_keys_if_missing_keeps_an_existing_key_pair(self):
        configuration = self.make_configuration()
        configuration.generate_lti_1p3_keys_if_missing()
        configuration.refresh_from_db()
        stored = (
            configuration.lti_1p3_internal_private_key,
            configuration.lti_1p3_internal_private_key_id,
            configuration.lti_1p3_internal_public_jwk,
        )

        configuration.generate_lti_1p3_keys_if_missing()

        configuration.refresh_from_db()
        self.assertEqual(
            (
                configuration.lti_1p3_internal_private_key,
                configuration.lti_1p3_internal_private_key_id,
                configuration.lti_1p3_internal_public_jwk,
            ),
            stored,
        )

    def test_generate_lti_1p3_keys_if_missing_rebuilds_a_missing_jwk_from_the_stored_private_key(self):
        configuration = self.make_configuration()
        configuration.generate_lti_1p3_keys_if_missing()
        configuration.refresh_from_db()
        stored_private_key = configuration.lti_1p3_internal_private_key
        stored_private_key_id = configuration.lti_1p3_internal_private_key_id
        stored_jwk = json.loads(configuration.lti_1p3_internal_public_jwk)
        configuration.lti_1p3_internal_public_jwk = ''
        configuration.save()

        configuration.generate_lti_1p3_keys_if_missing()

        configuration.refresh_from_db()
        self.assertEqual(json.loads(configuration.lti_1p3_internal_public_jwk), stored_jwk)
        self.assertEqual(configuration.lti_1p3_internal_private_key, stored_private_key)
        self.assertEqual(configuration.lti_1p3_internal_private_key_id, stored_private_key_id)

    def test_str_names_the_configuration_and_its_passport(self):
        passport_id = uuid.uuid4()

        configuration = self.make_configuration(passport_id=passport_id)

        self.assertEqual(
            str(configuration),
            f'ReusableLtiConfiguration: Model test - {passport_id}',
        )

    def test_clean_requires_a_public_key_in_public_key_mode(self):
        configuration = self.make_configuration(lti_1p3_tool_key_mode='public_key')

        with self.assertRaisesMessage(ValidationError, 'A public key is required in public-key mode.'):
            configuration.clean()

    def test_clean_requires_a_keyset_url_in_keyset_url_mode(self):
        configuration = self.make_configuration(lti_1p3_tool_key_mode='keyset_url')

        with self.assertRaisesMessage(ValidationError, 'A keyset URL is required in keyset-URL mode.'):
            configuration.clean()

    def test_clean_accepts_absent_and_complete_tool_key_settings(self):
        self.make_configuration().clean()
        self.make_configuration(
            lti_1p3_tool_key_mode='public_key',
            lti_1p3_tool_public_key='-----BEGIN PUBLIC KEY-----',
        ).clean()
        self.make_configuration(
            lti_1p3_tool_key_mode='keyset_url',
            lti_1p3_tool_keyset_url='https://tool.example/jwks',
        ).clean()

    def test_privacy_defaults_and_authored_values_persist_independently_of_the_description(self):
        """A new row takes the safe privacy defaults; authored values stay separate."""
        defaulted = self.make_configuration(name='Defaults')
        defaulted.refresh_from_db()

        self.assertFalse(defaulted.pii_share_username)
        self.assertFalse(defaulted.pii_share_full_name)
        self.assertFalse(defaulted.pii_share_email)
        self.assertEqual(defaulted.data_sharing_notice, '')
        self.assertTrue(defaulted.require_user_confirmation)
        self.assertFalse(defaulted.hide_external_tool)

        configuration = self.make_configuration(
            description='Tool Description',
            pii_share_username=True,
            pii_share_full_name=True,
            pii_share_email=True,
            data_sharing_notice='Learner-facing notice',
            require_user_confirmation=False,
            hide_external_tool=True,
        )

        configuration.refresh_from_db()
        self.assertTrue(configuration.pii_share_username)
        self.assertTrue(configuration.pii_share_full_name)
        self.assertTrue(configuration.pii_share_email)
        self.assertFalse(configuration.require_user_confirmation)
        self.assertTrue(configuration.hide_external_tool)
        self.assertEqual(configuration.data_sharing_notice, 'Learner-facing notice')
        self.assertNotEqual(configuration.data_sharing_notice, configuration.description)

        # The sharing notice and the Tool Description are separate stored values.
        configuration.description = 'Renamed Tool Description'
        configuration.save()
        configuration.data_sharing_notice = 'Updated learner notice'
        configuration.save()
        configuration.refresh_from_db()
        self.assertEqual(configuration.description, 'Renamed Tool Description')
        self.assertEqual(configuration.data_sharing_notice, 'Updated learner notice')

    def test_clean_accepts_key_material_without_a_mode(self):
        for label, key_material in (
            ('public key', {'lti_1p3_tool_public_key': '-----BEGIN PUBLIC KEY-----'}),
            ('keyset URL', {'lti_1p3_tool_keyset_url': 'https://tool.example/jwks'}),
        ):
            with self.subTest(label):
                self.make_configuration(lti_1p3_tool_key_mode=None, **key_material).clean()
