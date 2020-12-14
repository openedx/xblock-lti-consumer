"""
Tests for LTI Advantage Assignments and Grades Service views.
"""
from mock import patch, PropertyMock, Mock

from Cryptodome.PublicKey import RSA
from jwkest.jwk import RSAKey
from rest_framework.test import APITransactionTestCase


from lti_consumer.lti_xblock import LtiConsumerXBlock
from lti_consumer.models import LtiConfiguration, LtiDlContentItem
from lti_consumer.tests.unit.test_utils import make_xblock


class LtiDeepLinkingTestCase(APITransactionTestCase):
    """
    Test `LtiAgsLineItemViewset` endpoint.
    """
    def setUp(self):
        super().setUp()

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


class LtiDeepLinkingResponseEndpointTestCase(LtiDeepLinkingTestCase):
    """
    Test `deep_linking_response_endpoint` for LTI Deep Linking compliance.
    """

    def setUp(self):
        super().setUp()

        # Patch method that calls platform core to ask for user permissions
        studio_access_patcher = patch('lti_consumer.plugin.views.user_has_staff_access')
        self.addCleanup(studio_access_patcher.stop)
        self._mock_has_studio_write_acess = studio_access_patcher.start()
        self._mock_has_studio_write_acess.return_value = True

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

    def test_lti_deep_linking_unauthorized_user(self):
        """
        Test that the endpoint errors out when users don't have course write access.
        """
        self._mock_has_studio_write_acess.return_value = False
        response = self.client.post(
            self.url,
            {
                'JWT': self._build_deep_linking_response()
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_lti_content_type_clears_old_entries(self):
        """
        Check that on each new DL request, the old configurations are erased.
        """
        LtiDlContentItem.objects.create(
            lti_configuration=self.lti_config,
            content_type=LtiDlContentItem.LINK,
            attributes={}
        )

        # Make LTI request without any content type and check if the one
        # above was cleared after the request succeeded.
        response = self.client.post(
            self.url,
            {
                'JWT': self._build_deep_linking_response()
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(LtiDlContentItem.objects.count(), 0)

    def test_lti_resource_link_content_type(self):
        """
        Tests that the ltiResourceLink is accepted if valid.
        """
        response_token = self._build_deep_linking_response(
            content_items=[
                {
                    "type": "ltiResourceLink",
                    "url": "https://example.com/lti"
                }
            ]
        )

        # Make request to endpoint
        response = self.client.post(
            self.url,
            {
                'JWT': response_token
            },
        )
        self.assertEqual(response.status_code, 200)

        # Check if content item was created
        content_items = LtiDlContentItem.objects.all()
        self.assertEqual(content_items.count(), 1)
        self.assertEqual(content_items[0].content_type, "ltiResourceLink")
        self.assertEqual(content_items[0].attributes["url"], "https://example.com/lti")


class LtiDeepLinkingContentEndpointTestCase(LtiDeepLinkingTestCase):
    """
    Test ``deep_linking_content_endpoint`` view.
    """

    def setUp(self):
        super().setUp()
        self.url = '/lti_consumer/v1/lti/{}/lti-dl/content'.format(self.lti_config.id)

    @patch('lti_consumer.plugin.views.has_block_access', return_value=False)
    def test_forbidden_access(self, has_block_access_patcher):  # pylint: disable=unused-argument
        """
        Test if 403 is returned when a user doesn't have access.
        """
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 403)

    def test_invalid_lti_config(self):
        """
        Test if throws 404 when lti configuration not found.
        """
        resp = self.client.get('/lti_consumer/v1/lti/200/lti-dl/content')
        self.assertEqual(resp.status_code, 404)

    @patch('lti_consumer.plugin.views.has_block_access', return_value=True)
    def test_no_dl_contents(self, has_block_access_patcher):  # pylint: disable=unused-argument
        """
        Test if throws 404 when there is no LTI-DL Contents.
        """
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 404)

    @patch('lti_consumer.plugin.views.has_block_access', return_value=True)
    def test_dl_contents(self, has_block_access_patcher):  # pylint: disable=unused-argument
        """
        Test if successfully returns an HTML response.
        """
        LtiDlContentItem.objects.create(
            lti_configuration=self.lti_config,
            content_type=LtiDlContentItem.IMAGE,
            attributes={}
        )

        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        expected_title = '{} | Deep Linking Contents'.format(self.lti_config.block.display_name)
        self.assertContains(resp, expected_title)
