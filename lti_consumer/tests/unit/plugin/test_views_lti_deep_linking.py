"""
Tests for LTI Advantage Assignments and Grades Service views.
"""
from unittest.mock import patch, Mock

import re
import ddt
from Cryptodome.PublicKey import RSA
from jwkest.jwk import RSAKey
from rest_framework.test import APITransactionTestCase
from rest_framework.exceptions import ValidationError


from lti_consumer.data import Lti1p3LaunchData
from lti_consumer.utils import cache_lti_1p3_launch_data
from lti_consumer.lti_xblock import LtiConsumerXBlock
from lti_consumer.models import LtiConfiguration, LtiDlContentItem
from lti_consumer.tests.test_utils import make_xblock


class LtiDeepLinkingTestCase(APITransactionTestCase):
    """
    Test `LtiAgsLineItemViewset` endpoint.
    """
    def setUp(self):
        super().setUp()

        # We define the XBlock first in order to create an LtiConfiguration instance, which is used to generate
        # LTI 1.3 keys. Later, we set the necessary XBlock attributes.
        self.xblock = make_xblock('lti_consumer', LtiConsumerXBlock, {})

        # Create configuration
        self.lti_config = LtiConfiguration.objects.create(
            location=self.xblock.scope_ids.usage_id,
            version=LtiConfiguration.LTI_1P3,
        )

        # Create custom LTI Block
        rsa_key = RSA.import_key(self.lti_config.lti_1p3_private_key)
        self.key = RSAKey(
            # Using the same key ID as client id
            # This way we can easily serve multiple public
            # keys on the same endpoint and keep all
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

        for key, value in self.xblock_attributes.items():
            setattr(self.xblock, key, value)

        # Patch internal methods to avoid calls to modulestore
        enough_mock = patch(
            'lti_consumer.plugin.compat.load_enough_xblock',
        )
        self.addCleanup(enough_mock.stop)
        self._load_block_patch = enough_mock.start()
        self._load_block_patch.return_value = self.xblock

        # some deep linking endpoints still load the xblock as its user for access check
        as_user_mock = patch(
            'lti_consumer.plugin.compat.load_block_as_user',
        )
        self.addCleanup(as_user_mock.stop)
        self._load_block_as_user_patch = as_user_mock.start()
        self._load_block_as_user_patch.return_value = self.xblock

        self._mock_user = Mock()
        get_user_mock = patch("lti_consumer.plugin.compat.get_user_from_external_user_id")
        self.addCleanup(get_user_mock.stop)
        self._get_user_patch = get_user_mock.start()
        self._get_user_patch.return_value = self._mock_user


@ddt.ddt
class LtiDeepLinkingResponseEndpointTestCase(LtiDeepLinkingTestCase):
    """
    Test `deep_linking_response_endpoint` for LTI Deep Linking compliance.
    """

    def setUp(self):
        super().setUp()

        # Patch method that calls platform core to ask for user permissions
        compat_mock = patch("lti_consumer.signals.signals.compat")
        self.addCleanup(compat_mock.stop)
        self._compat_mock = compat_mock.start()
        self._compat_mock.user_has_studio_write_access.return_value = True

        has_studio_write_acess_patcher = patch(
            'lti_consumer.plugin.views.compat.user_has_studio_write_access',
            return_value=True
        )
        self.addCleanup(has_studio_write_acess_patcher.stop)
        self._mock_has_studio_write_acess = has_studio_write_acess_patcher.start()

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
        Test that the endpoint returns 400 when content type is not supported.
        """
        response = self.client.post(
            self.url,
            {
                'JWT': self._build_deep_linking_response([{
                    'type': 'invalid_content_type'
                }])
            },
        )
        self.assertEqual(response.status_code, 400)

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

    def _content_type_validation_test_helper(self, content_item, is_valid):
        """
        A helper method to test content type data.

        Performs tests based on wether data is valid or not.
        """
        response_token = self._build_deep_linking_response(
            content_items=[content_item]
        )

        if is_valid:
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
            self.assertEqual(content_items[0].content_type, content_item["type"])
            del content_item["type"]
            self.assertEqual(content_items[0].attributes, content_item)
        else:
            # If the datastructure is not valid, we expect to have a Validation Error.
            with self.assertRaises(ValidationError):
                self.client.post(
                    self.url,
                    {
                        'JWT': response_token
                    },
                )

    @ddt.data(
        ({"type": "link"}, False),
        ({"type": "link", "url": "https://example.com/link"}, True),
        ({"type": "link", "url": "https://example.com/link", "text": "This is a link"}, True),

        # invalid icon
        ({"type": "link", "url": "https://example.com/link", "text": "This is a link", "icon": {}}, False),
        # valid icon
        ({
            "type": "link",
            "url": "https://example.com/link",
            "text": "This is a link",
            "icon": {"url": "https://ex.com/icon", "width": 20, "height": 20}
        }, True),

        # invalid thumbnail
        ({"type": "link", "url": "https://example.com/link", "text": "This is a link", "thumbnail": {}}, False),
        # valid thumbnail
        ({
            "type": "link",
            "url": "https://example.com/link",
            "text": "This is a link",
            "thumbnail": {"url": "https://ex.com/icon", "width": 20, "height": 20}
        }, True),

        # invalid embed
        ({"type": "link", "url": "https://example.com/link", "embed": {}}, False),
        # valid embed
        ({
            "type": "link",
            "url": "https://example.com/link",
            "embed": {"html": "<p>Hello</p>"}
        }, True),

        # window
        ({"type": "link", "url": "https://example.com/link", "window": {}}, True),
        ({"type": "link", "url": "https://example.com/link", "window": {"targetName": "targetWindow"}}, True),
        ({
            "type": "link",
            "url": "https://example.com/link",
            "window": {
                "targetName": "targetWindow",
                "width": 200,
                "height": 200,
                "windowFeatures": "menubar=yes,location=yes,resizable=yes"
            }
        }, True),

        # iframe
        ({"type": "link", "url": "https://example.com/link", "iframe": {}}, False),
        ({"type": "link", "url": "https://example.com/link", "iframe": {"src": "http://ex.com/iframe"}}, False),
        ({
            "type": "link",
            "url": "https://example.com/link",
            "iframe": {"src": "http://ex.com/iframe", "width": 200, "height": 200}
        }, True),
    )
    def test_link_content_type(self, test_data):
        """
        Tests validation for `link` content type.

        Args:
            self
            test_data (tuple): 1st element is the datastructure to test,
                and the second one indicates wether it's valid or not.
        """
        content_item, is_valid = test_data
        self._content_type_validation_test_helper(content_item, is_valid)

    @ddt.data(
        ({"type": "html"}, False),
        ({"type": "html", "html": "<p>Hello</p>"}, True),
        ({
            "type": "html",
            "html": "<p>Hello</p>",
            "text": "This is a link",
            "title": "This is a link"
        }, True),
    )
    def test_html_content_type(self, test_data):
        """
        Tests validation for `html` content type.

        Args:
            self
            test_data (tuple): 1st element is the datastructure to test,
                and the second one indicates wether it's valid or not.
        """
        content_item, is_valid = test_data
        self._content_type_validation_test_helper(content_item, is_valid)

    @ddt.data(
        ({"type": "image"}, False),
        ({"type": "image", "url": "http://ex.com/image"}, True),
        ({
            "type": "image",
            "url": "http://ex.com/image",
            "text": "This is a link",
            "title": "This is a link"
        }, True),

        # invalid icon
        ({"type": "image", "url": "https://example.com/image", "icon": {}}, False),
        # valid icon
        ({
            "type": "image",
            "url": "https://example.com/image",
            "icon": {"url": "https://ex.com/icon", "width": 20, "height": 20}
        }, True),

        # invalid thumbnail
        ({"type": "image", "url": "https://example.com/image", "thumbnail": {}}, False),
        # valid thumbnail
        ({
            "type": "image",
            "url": "https://example.com/image",
            "thumbnail": {"url": "https://ex.com/icon", "width": 20, "height": 20}
        }, True),
    )
    def test_image_content_type(self, test_data):
        """
        Tests validation for `image` content type.

        Args:
            self
            test_data (tuple): 1st element is the datastructure to test,
                and the second one indicates wether it's valid or not.
        """
        content_item, is_valid = test_data
        self._content_type_validation_test_helper(content_item, is_valid)


@ddt.ddt
class LtiDeepLinkingContentEndpointTestCase(LtiDeepLinkingTestCase):
    """
    Test ``deep_linking_content_endpoint`` view.
    """

    def setUp(self):
        super().setUp()

        self.launch_data = Lti1p3LaunchData(
            user_id="1",
            user_role="student",
            config_id=self.lti_config.config_id,
            resource_link_id="resource_link_id",
        )
        self.launch_data_key = cache_lti_1p3_launch_data(self.launch_data)

        self.url = '/lti_consumer/v1/lti/{}/lti-dl/content?launch_data_key={}'.format(
            self.lti_config.id, self.launch_data_key
        )

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
        resp = self.client.get(
            '/lti_consumer/v1/lti/200/lti-dl/content?launch_data_key={}'.format(self.launch_data_key)
        )
        self.assertEqual(resp.status_code, 404)

    def test_missing_required_launch_data_key_param(self):
        """
        Check that a 400 error is returned when required launch_data_key query parameter is not provided.
        """
        # Use a new URL instead of self.url so that we do not include a launch_data_key.
        url = '/lti_consumer/v1/lti/{}/lti-dl/content'.format(
            self.lti_config.id
        )
        response = self.client.get(url, {})
        self.assertEqual(response.status_code, 400)

    def test_missing_launch_data(self):
        """
        Check that a 400 error is returned when required launch_data_key query parameter is not associated with
        launch_data in the cache.
        """
        # Use a new URL instead of self.url so that we include a launch_data_key that is not associated with any
        # launch_data in the cache.
        url = '/lti_consumer/v1/lti/{}/lti-dl/content'.format(
            self.lti_config.id
        )
        response = self.client.get(url, {"launch_data_key": "launch_data_key"})
        self.assertEqual(response.status_code, 400)

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
        expected_title = '{} | Deep Linking Contents'.format(self.xblock.display_name)
        self.assertContains(resp, expected_title)

    @ddt.data(
        {'url': 'https://example.com'},
        {'url': 'https://example.com', 'title': 'With Title'},
        {'url': 'https://example.com', 'title': 'With Title', 'text': 'With Text'},
        {
            'url': 'https://example.com', 'title': 'With Title', 'text': 'With Text',
            'icon': {'url': 'https://link.to.icon', 'width': '20px', 'height': '20px'},
        },
        {
            'url': 'https://example.com', 'title': 'With Title', 'text': 'With Text',
            'thumbnail': {'url': 'https://link.to.thumbnail', 'width': '20px', 'height': '20px'},
        },
        {
            'url': 'https://example.com', 'title': 'With Title', 'text': 'With Text',
            'window': {'targetName': 'newWindow', 'windowFeatures': 'width=200px,height=200px'},
        },
    )
    @patch('lti_consumer.plugin.views.has_block_access', return_value=True)
    def test_dl_content_type_link(self, test_data, has_block_access_patcher):  # pylint: disable=unused-argument
        """
        Test if link content type successfully rendered.
        """
        attributes = {'type': LtiDlContentItem.LINK}
        attributes.update(test_data)

        LtiDlContentItem.objects.create(
            lti_configuration=self.lti_config,
            content_type=LtiDlContentItem.LINK,
            attributes=attributes
        )

        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

        if test_data.get('title'):
            self.assertContains(resp, '<h2>{}</h2>'.format(test_data['title']))

        if test_data.get('text'):
            self.assertContains(resp, '<p>{}</p>'.format(test_data['text']))

        # if icon exists
        if test_data.get('icon'):
            self.assertContains(
                resp,
                '<img src="{}" width="{}" height="{}" />'.format(
                    test_data['icon']['url'],
                    test_data['icon']['width'],
                    test_data['icon']['height'],
                )
            )

        # if thumbnail exists
        if test_data.get('thumbnail'):
            self.assertContains(
                resp,
                '<img src="{}" width="{}" height="{}" />'.format(
                    test_data['thumbnail']['url'],
                    test_data['thumbnail']['width'],
                    test_data['thumbnail']['height'],
                )
            )

        # if window property exists
        if test_data.get('window'):
            self.assertContains(
                resp,
                'onclick="window.open(\'{}\', \'{}\', \'{}\')"'.format(
                    test_data['url'],
                    test_data['window']['targetName'],
                    test_data['window']['windowFeatures'],
                )
            )
            # if window property exists then only onclick will work.
            self.assertContains(resp, 'href="#"')
        else:
            # otherwise, the link should be on the href of the anchor tag.
            self.assertContains(resp, 'href="{}"'.format(test_data['url']))

    @ddt.data(
        {'url': 'https://example.com', 'html': '<i>Hello World!</i>'},
        {'url': 'https://example.com', 'html': '<i>Hello World!</i>', 'title': 'With Title'},
        {'url': 'https://example.com', 'html': '<i>Hello World!</i>', 'title': 'With Title', 'text': 'With Text'},
        {'url': 'https://example.com', 'html': '<img alt="alt text" src="location_to_image">', 'title': 'With Title'},
    )
    @patch('lti_consumer.plugin.views.has_block_access', return_value=True)
    def test_dl_content_type_html(self, test_data, has_block_access_patcher):  # pylint: disable=unused-argument
        """
        Test if html content type successfully rendered.
        """
        attributes = {'type': LtiDlContentItem.HTML_FRAGMENT}
        attributes.update(test_data)

        LtiDlContentItem.objects.create(
            lti_configuration=self.lti_config,
            content_type=LtiDlContentItem.HTML_FRAGMENT,
            attributes=attributes
        )

        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

        if test_data.get('title'):
            self.assertContains(resp, '<h2>{}</h2>'.format(test_data['title']))

        if test_data.get('text'):
            self.assertContains(resp, '<p>{}</p>'.format(test_data['text']))

        self.assertContains(resp, test_data['html'])

    @ddt.data(
        {'url': 'https://path.to.image'},
        {'url': 'https://path.to.image', 'title': 'With Title'},
        {'url': 'https://path.to.image', 'title': 'With Title', 'text': 'With Text'},
        {
            'url': 'https://path.to.image', 'title': 'With Title', 'text': 'With Text',
            'width': '400px', 'height': '200px',
        },
        {
            'url': 'https://path.to.image', 'title': 'With Title', 'text': 'With Text',
            'icon': {'url': 'https://path.to.icon', 'width': '20px', 'height': '20px'},
        },
        {
            'url': 'https://path.to.image', 'title': 'With Title', 'text': 'With Text',
            'thumbnail': {'url': 'https://path.to.thumbnail', 'width': '20px', 'height': '20px'},
        },
    )
    @patch('lti_consumer.plugin.views.has_block_access', return_value=True)
    def test_dl_content_type_image(self, test_data, has_block_access):  # pylint: disable=unused-argument
        """
        Test if image content type successfully rendered.
        """
        attributes = {'type': LtiDlContentItem.IMAGE}
        attributes.update(test_data)

        LtiDlContentItem.objects.create(
            lti_configuration=self.lti_config,
            content_type=LtiDlContentItem.IMAGE,
            attributes=attributes
        )

        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

        if test_data.get('title'):
            self.assertContains(resp, '<h2>{}</h2>'.format(test_data['title']))
            self.assertContains(resp, 'alt="{}"'.format(test_data['title']))

        if test_data.get('text'):
            self.assertContains(resp, '<p>{}</p>'.format(test_data['text']))

        if test_data.get('thumbnail'):
            self.assertContains(resp, '<a href="{}"'.format(test_data['url']))
            self.assertContains(resp, '<img src="{}"'.format(test_data['thumbnail']['url']))
        elif test_data.get('icon'):
            self.assertContains(resp, '<a href="{}"'.format(test_data['url']))
            self.assertContains(resp, '<img src="{}"'.format(test_data['icon']['url']))
        else:
            self.assertContains(resp, '<img src="{}"'.format(test_data['url']))

        if test_data.get('width'):
            self.assertContains(resp, 'width="{}"'.format(test_data['width']))

        if test_data.get('height'):
            self.assertContains(resp, 'height="{}"'.format(test_data['height']))

    @patch('lti_consumer.plugin.views.has_block_access', return_value=True)
    def test_dl_content_multiple_lti_resource_links(self, has_block_access):  # pylint: disable=unused-argument
        """
        Test if multiple `ltiResourceLink` content types are successfully rendered.
        """
        content_items = []
        for _ in range(3):
            content_items.append(
                LtiDlContentItem.objects.create(
                    lti_configuration=self.lti_config,
                    content_type=LtiDlContentItem.LTI_RESOURCE_LINK,
                    attributes={}
                )
            )

        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

        # Check that there's three LTI Resource links presented with the correct launch_data_key query parameter and the
        # correct deep_linking_content_item_id parameter in the launch_data.
        lti_message_hints = re.findall('lti_message_hint=(\\w*)', str(resp.content))

        for lti_message_hint in lti_message_hints:
            self.assertContains(
                resp,
                f"lti_message_hint={lti_message_hint}"
            )
