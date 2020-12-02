"""
Tests for LTI Advantage Assignments and Grades Service views.
"""
from mock import patch, PropertyMock, Mock

from Cryptodome.PublicKey import RSA
import ddt
from jwkest.jwk import RSAKey
from rest_framework.test import APITransactionTestCase


from lti_consumer.lti_xblock import LtiConsumerXBlock
from lti_consumer.models import LtiConfiguration
from lti_consumer.tests.unit.test_utils import make_xblock


class LtiDeepLinkingTestCase(APITransactionTestCase):
    """
    Test `LtiAgsLineItemViewset` endpoint.
    """
    def setUp(self):
        super(LtiDeepLinkingTestCase, self).setUp()

        self.location = 'block-v1:course+test+2020+type@problem+block@test'

        # Create configuration
        self.lti_config = LtiConfiguration.objects.create(
            location=self.location,
            version=LtiConfiguration.LTI_1P3,
        )

        # Create custom LTI Block
        rsa_key = RSA.import_key(self.lti_config.lti_1p3_private_key)
        self.key = RSAKey(
            # Using the same key ID as client id
            # This way we can easily serve multiple public
            # keys on teh same endpoint and keep all
            # LTI 1.3 blocks working
            kid=self.lti_config.lti_1p3_private_key_id,
            key=rsa_key
        )
        self.public_key = rsa_key.publickey().export_key()

        self.xblock_attributes = {
            'lti_version': 'lti_1p3',
            'lti_1p3_launch_url': 'http://tool.example/launch',
            'lti_1p3_oidc_url': 'http://tool.example/oidc',
            # Intentionally using the same key for tool key to
            # allow using signing methods and make testing easier.
            'lti_1p3_tool_public_key': self.public_key,

            # xblock due date related attributes
            'lti_advantage_deep_linking_enabled': True,
            'lti_advantage_deep_linking_launch_url': 'http://tool.example/deep_link_launch',
        }
        self.xblock = make_xblock('lti_consumer', LtiConsumerXBlock, self.xblock_attributes)

        # Set dummy location so that UsageKey lookup is valid
        self.xblock.location = self.location

        # Preload XBlock to avoid calls to modulestore
        self.lti_config.block = self.xblock

        # Patch internal method to avoid calls to modulestore
        patcher = patch(
            'lti_consumer.models.LtiConfiguration.block',
            new_callable=PropertyMock,
            return_value=self.xblock
        )
        self.addCleanup(patcher.stop)
        self._lti_block_patch = patcher.start()

        self._mock_user = Mock()
        compat_mock = patch("lti_consumer.signals.compat")
        self.addCleanup(compat_mock.stop)
        self._compat_mock = compat_mock.start()
        self._compat_mock.get_user_from_external_user_id.return_value = self._mock_user
        self._compat_mock.load_block_as_anonymous_user.return_value = self.xblock


@ddt.ddt
class LtiDeepLinkingResponseEndpointTestCase(LtiDeepLinkingTestCase):
    """
    Test `deep_linking_response_endpoint` for LTI Deep Linking compliance.
    """

    def setUp(self):
        super().setUp()

        # Deep Linking response endpoint
        self.url = '/lti_consumer/v1/lti/{}/lti-dl/response'.format(self.lti_config.id)

    def _build_deep_linking_response(self, content_items=None):
        """
        Builds a mock deep linking response to test the API.
        """
        if not content_items:
            content_items = []
        consumer = self.lti_config.get_lti_consumer()

        # Notice that we're using the same key for both the key and platform
        # to make use of the built-in encoding function in the
        # platform key handler and make the testing easier.
        return consumer.key_handler.encode_and_sign({
            "iss": consumer.client_id,
            "aud": consumer.iss,
            "https://purl.imsglobal.org/spec/lti/claim/deployment_id": consumer.deployment_id,
            "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiDeepLinkingResponse",
            "https://purl.imsglobal.org/spec/lti/claim/version": "1.3.0",
            "https://purl.imsglobal.org/spec/lti-dl/claim/content_items": content_items
        })

    def test_lti_deep_linking_no_configuration(self):
        """
        Test that the endpoint returns a 404 when LTI config is not found.
        """
        # Deep Linking response endpoint pointing to invalid config id
        url = '/lti_consumer/v1/lti/12345/lti-dl/response'

        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_lti_deep_linking_bad_token(self):
        """
        Test that the endpoint returns a 403 when LTI token is invalid.
        """
        response = self.client.post(self.url, {'JWT': 'bad-token'})
        self.assertEqual(response.status_code, 403)

    def test_lti_deep_linking_with_invalid_content_type(self):
        """
        Test that the endpoint returns 403 when content type is not supported.
        """
        response = self.client.post(
            self.url,
            {
                'JWT': self._build_deep_linking_response([{
                    'type': 'invalid_content_type'
                }])
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_lti_deep_linking_valid_request(self):
        """
        Test that the endpoint returns a 200 when LTI DL response is correct.
        """
        response = self.client.post(
            self.url,
            {
                'JWT': self._build_deep_linking_response()
            },
        )
        self.assertEqual(response.status_code, 200)
