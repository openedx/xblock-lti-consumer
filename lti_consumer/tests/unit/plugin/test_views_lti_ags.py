"""
Tests for LTI Advantage Assignments and Grades Service views.
"""
import ddt
from mock import patch, PropertyMock

from Cryptodome.PublicKey import RSA
from django.urls import reverse
from jwkest.jwk import RSAKey
from rest_framework import status
from rest_framework.test import APITransactionTestCase


from lti_consumer.lti_xblock import LtiConsumerXBlock
from lti_consumer.models import LtiConfiguration, LtiAgsLineItem
from lti_consumer.tests.unit.test_utils import make_xblock


@ddt.ddt
class TestLtiAgsLineItemViewSet(APITransactionTestCase):
    """
    Test `LtiAgsLineItemViewset` method.
    """
    def setUp(self):
        super(TestLtiAgsLineItemViewSet, self).setUp()

        # Create custom LTI Block
        self.rsa_key_id = "1"
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
            # Intentionally using the same key for tool key to
            # allow using signing methods and make testing easier.
            'lti_1p3_tool_public_key': self.public_key,
        }
        self.xblock = make_xblock('lti_consumer', LtiConsumerXBlock, self.xblock_attributes)

        # Set dummy location so that UsageKey lookup is valid
        self.xblock.location = 'block-v1:course+test+2020+type@problem+block@test'

        # Create configuration
        self.lti_config = LtiConfiguration.objects.create(
            location=str(self.xblock.location),
            version=LtiConfiguration.LTI_1P3
        )
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

        # LineItem endpoint
        self.lineitem_endpoint = reverse(
            'lti_consumer:lti-ags-view-list',
            kwargs={
                "lti_config_id": self.lti_config.id
            }
        )

    def _generate_lti_access_token(self, scopes):
        """
        Generates a valid LTI Auth token.
        """
        consumer = self.lti_config.get_lti_consumer()
        return consumer.key_handler.encode_and_sign({
            "iss": "https://example.com",
            "scopes": scopes,
        })

    def test_lti_ags_view_no_token(self):
        """
        Test the LTI AGS list view when there's no token.
        """
        response = self.client.get(self.lineitem_endpoint)
        self.assertEqual(response.status_code, 403)

    @ddt.data("Bearer invalid-token", "test", "Token with more items")
    def test_lti_ags_view_invalid_token(self, authorization):
        """
        Test the LTI AGS list view when there's an invalid token.
        """
        self.client.credentials(HTTP_AUTHORIZATION=authorization)
        response = self.client.get(self.lineitem_endpoint)

        self.assertEqual(response.status_code, 403)

    def test_lti_ags_token_missing_scopes(self):
        """
        Test the LTI AGS list view when there's a valid token without valid scopes.
        """
        self.client.credentials(
            HTTP_AUTHORIZATION="Bearer {}".format(
                # No scopes in token
                self._generate_lti_access_token("")
            )
        )
        response = self.client.get(self.lineitem_endpoint)
        self.assertEqual(response.status_code, 403)

    @ddt.data(
        'https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly',
        'https://purl.imsglobal.org/spec/lti-ags/scope/lineitem'
    )
    def test_lti_ags_list_permissions(self, scopes):
        """
        Test the LTI AGS list view when there's token valid scopes.
        """
        self.client.credentials(
            HTTP_AUTHORIZATION="Bearer {}".format(
                self._generate_lti_access_token(scopes)
            )
        )
        # Test with no LineItems
        response = self.client.get(self.lineitem_endpoint)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_lti_ags_list(self):
        """
        Test the LTI AGS list.
        """
        self.client.credentials(
            HTTP_AUTHORIZATION="Bearer {}".format(
                self._generate_lti_access_token(
                    'https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly'
                )
            )
        )

        # Create LineItem
        line_item = LtiAgsLineItem.objects.create(
            lti_configuration=self.lti_config,
            resource_id="test",
            label="test label",
            score_maximum=100
        )

        # Retrieve & check
        response = self.client.get(self.lineitem_endpoint)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])