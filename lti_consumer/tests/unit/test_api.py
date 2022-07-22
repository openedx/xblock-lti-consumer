"""
Tests for LTI API.
"""
from unittest.mock import Mock, patch
import ddt

from Cryptodome.PublicKey import RSA
from django.test.testcases import TestCase
from opaque_keys.edx.locations import Location

from lti_consumer.api import (
    _get_or_create_local_lti_config,
    get_lti_1p3_content_url,
    get_deep_linking_data,
    get_lti_1p3_launch_info,
    get_lti_1p3_launch_start_url,
    get_lti_consumer
)
from lti_consumer.lti_xblock import LtiConsumerXBlock
from lti_consumer.models import LtiConfiguration, LtiDlContentItem
from lti_consumer.tests.unit.test_utils import make_xblock


class Lti1P3TestCase(TestCase):
    """
    Reusable test case for testing LTI 1.3 configurations.
    """
    def setUp(self):
        """
        Set up an empty block configuration.
        """
        self.xblock = None
        self.lti_config = None

        return super().setUp()

    def _setup_lti_block(self):
        """
        Set's up an LTI block that is used in some tests.
        """
        # Generate RSA and save exports
        rsa_key = RSA.generate(1024)
        public_key = rsa_key.publickey().export_key()

        xblock_attributes = {
            'lti_version': 'lti_1p3',
            'lti_1p3_launch_url': 'http://tool.example/launch',
            'lti_1p3_oidc_url': 'http://tool.example/oidc',
            # We need to set the values below because they are not automatically
            # generated until the user selects `lti_version == 'lti_1p3'` on the
            # Studio configuration view.
            'lti_1p3_tool_public_key': public_key,
        }
        self.xblock = make_xblock('lti_consumer', LtiConsumerXBlock, xblock_attributes)
        # Set dummy location so that UsageKey lookup is valid
        self.xblock.location = 'block-v1:course+test+2020+type@problem+block@test'
        # Create lti configuration
        self.lti_config = LtiConfiguration.objects.create(
            location=self.xblock.location
        )


@ddt.ddt
class TestGetOrCreateLocalLtiConfiguration(TestCase):
    """
    Unit tests for _get_or_create_local_lti_config API method.
    """
    def test_create_lti_config_if_inexistent(self):
        """
        Check if the API creates a model if no object matching properties is found.
        """
        location = 'block-v1:course+test+2020+type@problem+block@test'
        lti_version = LtiConfiguration.LTI_1P3

        # Check that there's nothing in the models
        self.assertEqual(LtiConfiguration.objects.all().count(), 0)

        # Call API
        lti_config = _get_or_create_local_lti_config(
            lti_version=lti_version,
            block_location=location
        )

        # Check if the object was created
        self.assertEqual(lti_config.version, lti_version)
        self.assertEqual(str(lti_config.location), location)
        self.assertEqual(lti_config.config_store, LtiConfiguration.CONFIG_ON_XBLOCK)

    def test_retrieve_existing(self):
        """
        Check if the API retrieves a model if the configuration matches.
        """
        location = 'block-v1:course+test+2020+type@problem+block@test'
        lti_version = LtiConfiguration.LTI_1P1

        lti_config = LtiConfiguration.objects.create(
            location=location
        )

        # Call API
        lti_config_retrieved = _get_or_create_local_lti_config(
            lti_version=lti_version,
            block_location=location
        )

        # Check if the object was created
        self.assertEqual(LtiConfiguration.objects.all().count(), 1)
        self.assertEqual(lti_config_retrieved, lti_config)

    def test_update_lti_version(self):
        """
        Check if the API retrieves the config and updates the API version.
        """
        location = 'block-v1:course+test+2020+type@problem+block@test'

        lti_config = LtiConfiguration.objects.create(
            location=location,
            version=LtiConfiguration.LTI_1P1
        )

        # Call API
        _get_or_create_local_lti_config(
            lti_version=LtiConfiguration.LTI_1P3,
            block_location=location
        )

        # Check if the object was created
        lti_config.refresh_from_db()
        self.assertEqual(lti_config.version, LtiConfiguration.LTI_1P3)

    @ddt.data(LtiConfiguration.CONFIG_ON_XBLOCK, LtiConfiguration.CONFIG_EXTERNAL, LtiConfiguration.CONFIG_ON_DB)
    def test_create_lti_config_config_store(self, config_store):
        """
        Check if the config_store parameter to _get_or_create_local_lti_config is used to change
        the config_store field of the LtiConfiguration model appropriately.
        """
        location = 'block-v1:course+test+2020+type@problem+block@test'
        lti_version = LtiConfiguration.LTI_1P3
        lti_config = _get_or_create_local_lti_config(
            lti_version=lti_version,
            block_location=location,
            config_store=config_store,
        )

        self.assertEqual(lti_config.config_store, config_store)

    def test_external_config_values_are_cleared(self):
        """
        Check if the API clears external configuration values when external id is none
        """
        location = 'block-v1:course+test+2020+type@problem+block@test'
        lti_version = LtiConfiguration.LTI_1P3

        lti_config = LtiConfiguration.objects.create(
            location=location,
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_EXTERNAL,
            external_id="test_plugin:test-id"
        )

        _get_or_create_local_lti_config(
            lti_version=lti_version,
            block_location=location,
            external_id=None
        )

        lti_config.refresh_from_db()
        self.assertEqual(lti_config.version, lti_version)
        self.assertEqual(str(lti_config.location), location)
        self.assertEqual(lti_config.config_store, LtiConfiguration.CONFIG_ON_XBLOCK)
        self.assertEqual(lti_config.external_id, None)


class TestGetLtiConsumer(TestCase):
    """
    Unit tests for get_lti_consumer API method.
    """
    def test_retrieve_with_block(self):
        """
        Check if the API creates a model if no object matching properties is found.
        """
        block = Mock()
        block.location = 'block-v1:course+test+2020+type@problem+block@test'
        block.lti_version = LtiConfiguration.LTI_1P3
        LtiConfiguration.objects.create(location=block.location)

        # Call API
        with patch("lti_consumer.models.LtiConfiguration.get_lti_consumer") as mock_get_lti_consumer:
            get_lti_consumer(block=block)
            mock_get_lti_consumer.assert_called_once()

        # Check that there's just a single LTI Config in the models
        self.assertEqual(LtiConfiguration.objects.all().count(), 1)

    def test_retrieve_with_id(self):
        """
        Check if the API retrieves a model if the configuration matches.
        """
        location = 'block-v1:course+test+2020+type@problem+block@test'
        lti_config = LtiConfiguration.objects.create(location=location)

        # Call API
        with patch("lti_consumer.models.LtiConfiguration.get_lti_consumer") as mock_get_lti_consumer:
            get_lti_consumer(config_id=lti_config.id)
            mock_get_lti_consumer.assert_called_once()

    def test_retrieve_from_external_configuration(self):
        """
        Check if the API creates a model from the external configuration ID
        """
        external_id = 'my-plugin:my-lti-tool'

        block = Mock()
        block.config_type = 'external'
        block.location = Location('edx', 'Demo_Course', '2020', 'T2', 'UNIV')
        block.external_config = external_id
        block.lti_version = LtiConfiguration.LTI_1P1

        # Call API
        with patch("lti_consumer.models.LtiConfiguration.get_lti_consumer") as mock_get_lti_consumer, \
                patch("lti_consumer.api.get_external_config_from_filter") as mock_get_from_filter:
            mock_get_from_filter.return_value = {"version": "lti_1p1"}
            get_lti_consumer(block=block)
            mock_get_lti_consumer.assert_called_once()
            mock_get_from_filter.assert_called_once_with({"course_key": block.location.course_key}, external_id)

        # Check that there's just a single LTI Config in the models
        self.assertEqual(LtiConfiguration.objects.all().count(), 1)


class TestGetLti1p3LaunchInfo(TestCase):
    """
    Unit tests for get_lti_consumer API method.
    """
    def setUp(self):
        # Patch internal method to avoid calls to modulestore
        patcher = patch(
            'lti_consumer.models.LtiConfiguration.get_lti_consumer',
        )
        self.addCleanup(patcher.stop)
        self._get_lti_consumer_patch = patcher.start()
        mock_consumer = Mock()
        mock_consumer.prepare_preflight_url.return_value = "http://example.com"
        self._get_lti_consumer_patch.return_value = mock_consumer

        return super().setUp()

    def test_no_parameters(self):
        """
        Check if the API creates a model if no object matching properties is found.
        """
        with self.assertRaises(Exception):
            get_lti_1p3_launch_info()

    def test_retrieve_with_id(self):
        """
        Check if the API retrieves the launch with id.
        """
        location = 'block-v1:course+test+2020+type@problem+block@test'
        lti_config = LtiConfiguration.objects.create(location=location)

        # Call and check returns
        launch_info = get_lti_1p3_launch_info(config_id=lti_config.id)

        # Not checking all data here, there's a test specific for that
        self.assertEqual(launch_info['client_id'], lti_config.lti_1p3_client_id)

    def test_retrieve_with_block(self):
        """
        Check if the API creates the model and retrieved correct info.
        """
        block = Mock()
        block.location = 'block-v1:course+test+2020+type@problem+block@test'
        block.lti_version = LtiConfiguration.LTI_1P3

        # Create LTI Config and Deep linking object
        lti_config = LtiConfiguration.objects.create(location=block.location)
        LtiDlContentItem.objects.create(
            lti_configuration=lti_config,
            content_type=LtiDlContentItem.IMAGE,
            attributes={"test": "this is a test attribute"}
        )

        # Call API
        launch_info = get_lti_1p3_launch_info(block=block)

        # Retrieve created config and check full launch info data
        lti_config = LtiConfiguration.objects.get()
        self.assertEqual(
            launch_info,
            {
                'client_id': lti_config.lti_1p3_client_id,
                'keyset_url': 'https://example.com/api/lti_consumer/v1/public_keysets/{}'.format(
                    lti_config.location
                ),
                'deployment_id': '1',
                'oidc_callback': 'https://example.com/api/lti_consumer/v1/launch/',
                'token_url': 'https://example.com/api/lti_consumer/v1/token/{}'.format(
                    lti_config.location
                ),
                'deep_linking_launch_url': 'http://example.com',

                'deep_linking_content_items':
                    '[\n    {\n        "test": "this is a test attribute"\n    }\n]',
            }
        )

    def test_launch_info_for_lti_config_without_location(self):
        """
        Check if the API can return launch info for LtiConfiguration objects without
        specified block location.
        """
        lti_config = LtiConfiguration.objects.create(version=LtiConfiguration.LTI_1P3)
        LtiDlContentItem.objects.create(
            lti_configuration=lti_config,
            content_type=LtiDlContentItem.IMAGE,
            attributes={"test": "this is a test attribute"}
        )
        launch_info = get_lti_1p3_launch_info(config_id=lti_config.id)
        self.assertEqual(
            launch_info,
            {
                'client_id': lti_config.lti_1p3_client_id,
                'keyset_url': 'https://example.com/api/lti_consumer/v1/public_keysets/{}'.format(
                    lti_config.config_id
                ),
                'deployment_id': '1',
                'oidc_callback': 'https://example.com/api/lti_consumer/v1/launch/',
                'token_url': 'https://example.com/api/lti_consumer/v1/token/{}'.format(
                    lti_config.config_id
                ),
                'deep_linking_launch_url': 'http://example.com',

                'deep_linking_content_items':
                    '[\n    {\n        "test": "this is a test attribute"\n    }\n]',
            }
        )



class TestGetLti1p3LaunchUrl(Lti1P3TestCase):
    """
    Unit tests for get_lti_1p3_launch_start_url API method.
    """
    def test_no_parameters(self):
        """
        Check if the API creates a model if no object matching properties is found.
        """
        with self.assertRaises(Exception):
            get_lti_1p3_launch_start_url()

    def test_retrieve_url(self):
        """
        Check if the correct launch url is retrieved
        """
        self._setup_lti_block()

        # Call API for normal LTI launch initiation
        launch_url = get_lti_1p3_launch_start_url(block=self.xblock, hint="test_hint")
        self.assertIn('login_hint=test_hint', launch_url)
        self.assertIn('lti_message_hint=', launch_url)

        # Call API for deep link launch
        launch_url = get_lti_1p3_launch_start_url(block=self.xblock, deep_link_launch=True)
        self.assertIn('lti_message_hint=deep_linking_launch', launch_url)


class TestGetLti1p3ContentUrl(Lti1P3TestCase):
    """
    Unit tests for get_lti_1p3_launch_start_url API method.
    """
    @patch("lti_consumer.api.get_lti_1p3_launch_start_url")
    def test_lti_content_presentation(self, mock_get_launch_url):
        """
        Check if the correct LTI content presentation is returned on a normal LTI Launch.
        """
        mock_get_launch_url.return_value = 'test_url'
        self._setup_lti_block()
        self.assertEqual(get_lti_1p3_content_url(block=self.xblock), 'test_url')

    def test_lti_content_presentation_single_link(self):
        """
        Check if the correct LTI content presentation is returned if a `ltiResourceLink`
        content type is present.
        """
        self._setup_lti_block()

        # Create LTI DL content items
        lti_content = LtiDlContentItem.objects.create(
            lti_configuration=self.lti_config,
            content_type=LtiDlContentItem.LTI_RESOURCE_LINK,
            attributes={},
        )

        # Call API to retrieve content item URL
        launch_url = get_lti_1p3_content_url(block=self.xblock)
        self.assertIn(
            # Checking for `deep_linking_content_launch:<content_item_id>`
            # URL Encoded `:` is `%3A`
            f'lti_message_hint=deep_linking_content_launch%3A{lti_content.id}',
            launch_url,
        )

    def test_lti_content_presentation_multiple_links(self):
        """
        Check if the correct LTI content presentation is returned if multiple LTI DL
        content items are set up.
        """
        self._setup_lti_block()

        # Create LTI DL content items
        for _ in range(3):
            LtiDlContentItem.objects.create(
                lti_configuration=self.lti_config,
                content_type=LtiDlContentItem.IMAGE,
                attributes={},
            )

        # Call API to retrieve content item URL
        self.assertIn(
            # Checking for the content presentation URL
            f"/api/lti_consumer/v1/lti/{self.lti_config.id}/lti-dl/content",
            get_lti_1p3_content_url(block=self.xblock),
        )


class TestGetLtiDlContentItemData(TestCase):
    """
    Unit tests for get_deep_linking_data API method.
    """
    def setUp(self):
        """
        Set up an empty block configuration.
        """
        self.lti_config = LtiConfiguration.objects.create(
            location='block-v1:course+test+2020+type@problem+block@test',
        )

        return super().setUp()

    def test_lti_retrieve_content_item(self):
        """
        Check if the API return the right content item.
        """
        content_item = LtiDlContentItem.objects.create(
            lti_configuration=self.lti_config,
            content_type=LtiDlContentItem.LTI_RESOURCE_LINK,
            attributes={"test": "test"},
        )

        data = get_deep_linking_data(
            deep_linking_id=content_item.id,
            config_id=self.lti_config.id,
        )

        self.assertEqual(
            data,
            {"test": "test"},
        )

    def test_only_related_lti_contents(self):
        """
        Check if the API fails if trying to retrieve a content item
        that the LtiConfiguration doesn't own.
        """
        content_item = LtiDlContentItem.objects.create(
            lti_configuration=None,
            content_type=LtiDlContentItem.LTI_RESOURCE_LINK,
            attributes={"test": "test"},
        )

        with self.assertRaises(Exception):
            get_deep_linking_data(
                deep_linking_id=content_item.id,
                config_id=self.lti_config.id,
            )
