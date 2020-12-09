"""
Unit tests for LTI models.
"""
from datetime import timedelta
from unittest.mock import patch

from Cryptodome.PublicKey import RSA
from django.test.testcases import TestCase
from django.utils import timezone
from jwkest.jwk import RSAKey

from lti_consumer.lti_1p1.consumer import LtiConsumer1p1
from lti_consumer.lti_xblock import LtiConsumerXBlock
from lti_consumer.models import (
    LtiAgsLineItem,
    LtiConfiguration,
    LtiAgsScore,
    LtiDlContentItem,
)
from lti_consumer.tests.unit.test_utils import make_xblock


class TestLtiConfigurationModel(TestCase):
    """
    Unit tests for LtiConfiguration model methods.
    """
    def setUp(self):
        super().setUp()

        self.rsa_key_id = "1"
        # Generate RSA and save exports
        rsa_key = RSA.generate(2048)
        self.key = RSAKey(
            key=rsa_key,
            kid=self.rsa_key_id
        )
        self.public_key = rsa_key.publickey().export_key()

        self.xblock_attributes = {
            'lti_version': 'lti_1p3',
            'lti_1p3_launch_url': 'http://tool.example/launch',
            'lti_1p3_oidc_url': 'http://tool.example/oidc',
            # We need to set the values below because they are not automatically
            # generated until the user selects `lti_version == 'lti_1p3'` on the
            # Studio configuration view.
            'lti_1p3_tool_public_key': self.public_key,
            'has_score': True,
            'lti_advantage_deep_linking_enabled': True,
        }
        self.xblock = make_xblock('lti_consumer', LtiConsumerXBlock, self.xblock_attributes)
        # Set dummy location so that UsageKey lookup is valid
        self.xblock.location = 'block-v1:course+test+2020+type@problem+block@test'

        # Creates an LTI configuration objects for testing
        self.lti_1p1_config = LtiConfiguration.objects.create(
            location=str(self.xblock.location),
            version=LtiConfiguration.LTI_1P1
        )
        self.lti_1p1_config_db = LtiConfiguration.objects.create(
            version=LtiConfiguration.LTI_1P1,
            config_store=LtiConfiguration.CONFIG_ON_DB,
            lti_1p1_launch_url='http://tool.example/lti1.1launch',
            lti_1p1_client_key='test_1p1p_key',
            lti_1p1_client_secret='test_1p1p_secret',
        )

        self.lti_1p3_config = LtiConfiguration.objects.create(
            location=str(self.xblock.location),
            version=LtiConfiguration.LTI_1P3
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

    def test_xblock_store_lti1p1(self):
        """
        Check if the correct LTI consumer is returned.
        """
        lti_consumer = self.lti_1p1_config_db.get_lti_consumer()

        self.assertIsInstance(lti_consumer, LtiConsumer1p1)

        lti_1p3_config = LtiConfiguration.objects.create(
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_ON_DB,
        )
        with self.assertRaises(NotImplementedError):
            lti_1p3_config.get_lti_consumer()

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

    def test_lti_consumer_ags_enabled(self):
        """
        Check if LTI AGS is properly included when block is graded.
        """
        self.lti_1p3_config.block = self.xblock

        # Get LTI 1.3 consumer
        consumer = self.lti_1p3_config.get_lti_consumer()

        # Check that LTI claim was included in extra claims
        self.assertEqual(
            consumer.extra_claims,
            {
                'https://purl.imsglobal.org/spec/lti-ags/claim/endpoint':
                {
                    'scope': [
                        'https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly',
                        'https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly',
                        'https://purl.imsglobal.org/spec/lti-ags/scope/score',
                    ],
                    'lineitems': 'https://example.com/api/lti_consumer/v1/lti/3/lti-ags',
                    'lineitem': 'https://example.com/api/lti_consumer/v1/lti/3/lti-ags/1',
                }
            }
        )

    def test_lti_consumer_deep_linking_enabled(self):
        """
        Check if LTI DL is properly instanced when configured.
        """
        self.lti_1p3_config.block = self.xblock

        # Get LTI 1.3 consumer
        consumer = self.lti_1p3_config.get_lti_consumer()

        # Check that LTI DL class is instanced.
        self.assertTrue(consumer.dl)

    @patch("lti_consumer.models.compat")
    def test_block_property(self, compat_mock):
        """
        Check if a block is properly loaded when calling the `block` property.
        """
        compat_mock.load_block_as_anonymous_user.return_value = self.xblock

        block = self.lti_1p3_config.block
        self.assertEqual(block, self.xblock)

    def test_block_property_missing_location(self):
        """
        Check the `block` property raises when failing to retrieve a block.
        """
        self.lti_1p3_config.location = None
        with self.assertRaises(ValueError):
            _ = self.lti_1p3_config.block

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


class TestLtiAgsLineItemModel(TestCase):
    """
    Unit tests for LtiAgsLineItem model methods.
    """
    def setUp(self):
        super().setUp()

        self.dummy_location = 'block-v1:course+test+2020+type@problem+block@test'
        self.lti_ags_model = LtiAgsLineItem.objects.create(
            lti_configuration=None,
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
        compat_mock = patch("lti_consumer.signals.compat")
        self.addCleanup(compat_mock.stop)
        self._compat_mock = compat_mock.start()
        self._compat_mock.load_block_as_anonymous_user.return_value = make_xblock(
            'lti_consumer', LtiConsumerXBlock, {
                'due': timezone.now(),
                'graceperiod': timedelta(days=2),
            }
        )

        self.dummy_location = 'block-v1:course+test+2020+type@problem+block@test'
        self.line_item = LtiAgsLineItem.objects.create(
            lti_configuration=None,
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
        # Set dummy location so that UsageKey lookup is valid
        self.xblock.location = 'block-v1:course+test+2020+type@problem+block@test'

        self.lti_1p3_config = LtiConfiguration.objects.create(
            location=str(self.xblock.location),
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
            "[CONFIG_ON_XBLOCK] lti_1p3 - block-v1:course+test+2020+type@problem+block@test: image"
        )
