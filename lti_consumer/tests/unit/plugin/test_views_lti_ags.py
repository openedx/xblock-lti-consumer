"""
Tests for LTI Advantage Assignments and Grades Service views.
"""
import json
from mock import patch, PropertyMock

from Cryptodome.PublicKey import RSA
import ddt
from django.urls import reverse
from jwkest.jwk import RSAKey
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

    def _set_lti_token(self, scopes=None):
        """
        Generates and sets a LTI Auth token in the request client.
        """
        if not scopes:
            scopes = ''

        consumer = self.lti_config.get_lti_consumer()
        token = consumer.key_handler.encode_and_sign({
            "iss": "https://example.com",
            "scopes": scopes,
        })
        # pylint: disable=no-member
        self.client.credentials(
            HTTP_AUTHORIZATION="Bearer {}".format(token)
        )

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
        self.client.credentials(HTTP_AUTHORIZATION=authorization)  # pylint: disable=no-member
        response = self.client.get(self.lineitem_endpoint)

        self.assertEqual(response.status_code, 403)

    def test_lti_ags_token_missing_scopes(self):
        """
        Test the LTI AGS list view when there's a valid token without valid scopes.
        """
        self._set_lti_token()
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
        self._set_lti_token(scopes)
        # Test with no LineItems
        response = self.client.get(self.lineitem_endpoint)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_lti_ags_list(self):
        """
        Test the LTI AGS list.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly')

        # Create LineItem
        line_item = LtiAgsLineItem.objects.create(
            lti_configuration=self.lti_config,
            resource_id="test",
            resource_link_id=self.xblock.location,
            label="test label",
            score_maximum=100
        )

        # Retrieve & check
        response = self.client.get(self.lineitem_endpoint)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['content-type'], 'application/vnd.ims.lis.v2.lineitemcontainer+json')
        self.assertEqual(
            response.data,
            [
                {
                    'id': 'http://testserver/lti_consumer/v1/lti/{}/lti-ags/{}'.format(
                        self.lti_config.id,
                        line_item.id
                    ),
                    'resourceId': 'test',
                    'scoreMaximum': 100,
                    'label': 'test label',
                    'tag': '',
                    'resourceLinkId': self.xblock.location,
                    'startDateTime': None,
                    'endDateTime': None,
                }
            ]
        )

    def test_lti_ags_retrieve(self):
        """
        Test the LTI AGS retrieve endpoint.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly')

        # Create LineItem
        line_item = LtiAgsLineItem.objects.create(
            lti_configuration=self.lti_config,
            resource_id="test",
            resource_link_id=self.xblock.location,
            label="test label",
            score_maximum=100
        )

        # Retrieve & check
        lineitem_detail_url = reverse(
            'lti_consumer:lti-ags-view-detail',
            kwargs={
                "lti_config_id": self.lti_config.id,
                "pk": line_item.id
            }
        )
        response = self.client.get(lineitem_detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {
                'id': 'http://testserver/lti_consumer/v1/lti/{}/lti-ags/{}'.format(
                    self.lti_config.id,
                    line_item.id
                ),
                'resourceId': 'test',
                'scoreMaximum': 100,
                'label': 'test label',
                'tag': '',
                'resourceLinkId': self.xblock.location,
                'startDateTime': None,
                'endDateTime': None,
            }
        )

    def test_create_lineitem(self):
        """
        Test the LTI AGS LineItem Creation.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-ags/scope/lineitem')

        # Create LineItem
        response = self.client.post(
            self.lineitem_endpoint,
            data=json.dumps({
                'resourceId': 'test',
                'scoreMaximum': 100,
                'label': 'test',
                'tag': 'score',
                'resourceLinkId': self.xblock.location,
            }),
            content_type="application/vnd.ims.lis.v2.lineitem+json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data,
            {
                'id': 'http://testserver/lti_consumer/v1/lti/1/lti-ags/1',
                'resourceId': 'test',
                'scoreMaximum': 100,
                'label': 'test',
                'tag': 'score',
                'resourceLinkId': self.xblock.location,
                'startDateTime': None,
                'endDateTime': None,
            }
        )
        self.assertEqual(LtiAgsLineItem.objects.all().count(), 1)
        line_item = LtiAgsLineItem.objects.get()
        self.assertEqual(line_item.resource_id, 'test')
        self.assertEqual(line_item.score_maximum, 100)
        self.assertEqual(line_item.label, 'test')
        self.assertEqual(line_item.tag, 'score')
        self.assertEqual(str(line_item.resource_link_id), self.xblock.location)

    def test_create_lineitem_invalid_resource_link_id(self):
        """
        Test the LTI AGS Lineitem creation when passing invalid resource link id.
        """
        self._set_lti_token('https://purl.imsglobal.org/spec/lti-ags/scope/lineitem')

        # Create LineItem
        response = self.client.post(
            self.lineitem_endpoint,
            data=json.dumps({
                'resourceId': 'test',
                'scoreMaximum': 100,
                'label': 'test',
                'tag': 'score',
                'resourceLinkId': 'invalid-resource-link',
            }),
            content_type="application/vnd.ims.lis.v2.lineitem+json",
        )

        self.assertEqual(response.status_code, 400)
