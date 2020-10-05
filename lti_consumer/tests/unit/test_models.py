"""
Unit tests for LTI models.
"""
from Cryptodome.PublicKey import RSA
from django.test.testcases import TestCase

from jwkest.jwk import RSAKey
from mock import patch

from lti_consumer.lti_xblock import LtiConsumerXBlock
from lti_consumer.models import LtiAgsLineItem, LtiConfiguration
from lti_consumer.tests.unit.test_utils import make_xblock


class TestLtiCofigurationModel(TestCase):
    """
    Unit tests for LtiConfiguration model methods.
    """
    def setUp(self):
        super(TestLtiCofigurationModel, self).setUp()

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
            'lti_1p3_client_id': self.rsa_key_id,
            'lti_1p3_block_key': rsa_key.export_key('PEM'),
            # Use same key for tool key to make testing easier
            'lti_1p3_tool_public_key': self.public_key,
            'has_score': True,
        }
        self.xblock = make_xblock('lti_consumer', LtiConsumerXBlock, self.xblock_attributes)
        # Set dummy location so that UsageKey lookup is valid
        self.xblock.location = 'block-v1:course+test+2020+type@problem+block@test'

        # Creates an LTI configuration objects for testing
        self.lti_1p1_config = LtiConfiguration.objects.create(
            location=str(self.xblock.location),
            version=LtiConfiguration.LTI_1P1
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
            "[CONFIG_ON_XBLOCK] lti_1p3 - {}".format(dummy_location)
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
                        'https://purl.imsglobal.org/spec/lti-ags/scope/lineitem',
                        'https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly',
                        'https://purl.imsglobal.org/spec/lti-ags/scope/score',
                    ],
                    'lineitems': 'https://example.com/api/lti_consumer/v1/lti/2/lti-ags'
                }
            }
        )


class TestLtiAgsLineItemModel(TestCase):
    """
    Unit tests for LtiAgsLineItem model methods.
    """
    def setUp(self):
        super(TestLtiAgsLineItemModel, self).setUp()

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
