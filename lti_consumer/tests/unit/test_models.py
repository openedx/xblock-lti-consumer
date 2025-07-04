"""
Unit tests for LTI models.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, call

import ddt
from Cryptodome.PublicKey import RSA
from django.core.exceptions import ValidationError
from django.test.testcases import TestCase
from edx_django_utils.cache import RequestCache
from ccx_keys.locator import CCXBlockUsageLocator
from opaque_keys.edx.locator import CourseLocator

from lti_consumer.lti_xblock import LtiConsumerXBlock
from lti_consumer.models import (CourseAllowPIISharingInLTIFlag, LtiAgsLineItem, LtiAgsScore, LtiConfiguration,
                                 LtiDlContentItem)
from lti_consumer.tests.test_utils import make_xblock

LAUNCH_URL = 'http://tool.example/launch'
DEEP_LINK_URL = 'http://tool.example/deep-link/launch'


@ddt.ddt
class TestLtiConfigurationModel(TestCase):
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

        patcher = patch(
            'lti_consumer.plugin.compat.load_enough_xblock',
        )
        self.addCleanup(patcher.stop)
        self._load_block_patch = patcher.start()
        self._load_block_patch.return_value = self.xblock

        # Creates an LTI configuration objects for testing
        self.lti_1p1_config = LtiConfiguration.objects.create(
            location=self.xblock.scope_ids.usage_id,
            version=LtiConfiguration.LTI_1P1
        )

        self.lti_1p3_config = LtiConfiguration.objects.create(
            location=self.xblock.scope_ids.usage_id,
            version=LtiConfiguration.LTI_1P3
        )

        self.lti_1p3_config_db = LtiConfiguration.objects.create(
            location=self.xblock.scope_ids.usage_id,
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_ON_DB,
            lti_advantage_ags_mode='programmatic',
            lti_advantage_deep_linking_enabled=True,
        )

        self.lti_1p3_config_external = LtiConfiguration.objects.create(
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_EXTERNAL,
            location=self.xblock.scope_ids.usage_id,
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
        return LtiConfiguration.objects.create(
            location=self.xblock.scope_ids.usage_id,
            version=LtiConfiguration.LTI_1P3,
            **kwargs
        )

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

    def test_generate_private_key(self):
        """
        Checks if a private key is correctly generated.
        """
        lti_config = LtiConfiguration.objects.create(
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_ON_XBLOCK,
            location='block-v1:course+test+2020+type@problem+block@test'
        )

        # Check that model fields are empty
        self.assertFalse(lti_config.lti_1p3_internal_private_key)
        self.assertFalse(lti_config.lti_1p3_internal_private_key_id)
        self.assertFalse(lti_config.lti_1p3_internal_public_jwk)

        # Create and retrieve public keys
        _ = lti_config.lti_1p3_public_jwk

        # Check if keys were created
        self.assertTrue(lti_config.lti_1p3_internal_private_key)
        self.assertTrue(lti_config.lti_1p3_internal_private_key_id)
        self.assertTrue(lti_config.lti_1p3_internal_public_jwk)

    def test_generate_public_key_only(self):
        """
        Checks if a public key is correctly regenerated from a private key
        """
        lti_config = LtiConfiguration.objects.create(
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_ON_XBLOCK,
            location='block-v1:course+test+2020+type@problem+block@test'
        )
        # Create and retrieve public keys
        public_key = lti_config.lti_1p3_public_jwk.copy()
        lti_config.lti_1p3_internal_public_jwk = ""
        lti_config.save()

        # Retrieve public key and check that it was correctly regenerated
        regenerated_public_key = lti_config.lti_1p3_public_jwk
        lti_config.refresh_from_db()
        self.assertEqual(regenerated_public_key, public_key)

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

        self.lti_1p3_config_db.lti_1p3_tool_keyset_url = ''
        self.lti_1p3_config_db.lti_1p3_tool_public_key = ''

        with self.assertRaises(ValidationError):
            self.lti_1p3_config_db.clean()

        self.lti_1p3_config.lti_1p3_proctoring_enabled = True
        self.lti_1p3_config.external_id = 'test_id'

        for config_store in [self.lti_1p3_config.CONFIG_ON_XBLOCK, self.lti_1p3_config.CONFIG_EXTERNAL]:
            self.lti_1p3_config.config_store = config_store
            with self.assertRaises(ValidationError):
                self.lti_1p3_config.clean()

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


class TestLtiAgsLineItemModel(TestCase):
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


class TestLtiAgsScoreModel(TestCase):
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

    def test_repr(self):
        """
        Test String representation of model.
        """
        self.assertEqual(
            str(self.score),
            "LineItem 1: score 10.0 out of 100.0 - FullyGraded"
        )


class TestLtiDlContentItemModel(TestCase):
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
class TestLTIConsumerHideFieldsFlag(TestCase):
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
