"""
Tests for LTI API.
"""
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

import ddt
from Cryptodome.PublicKey import RSA
from django.test.testcases import TestCase
from edx_django_utils.cache import get_cache_key
from opaque_keys.edx.keys import UsageKey

from lti_consumer.api import (
    _get_config_by_config_id,
    config_id_for_block,
    get_deep_linking_data,
    get_end_assessment_return,
    get_lti_1p3_content_url,
    get_lti_1p3_launch_info,
    get_lti_1p3_launch_start_url,
    _get_or_create_local_lti_config,
    validate_lti_1p3_launch_data,
)
from lti_consumer.data import Lti1p3LaunchData, Lti1p3ProctoringLaunchData
from lti_consumer.lti_xblock import LtiConsumerXBlock
from lti_consumer.models import Lti1p3Passport, LtiConfiguration, LtiDlContentItem
from lti_consumer.tests.test_utils import TestBaseWithPatch, make_xblock
from lti_consumer.utils import get_data_from_cache

# it's convenient to have this in lowercase to compare to URLs
_test_config_id = "6c440bf4-face-beef-face-e8bcfb1e53bd"


class Lti1P3TestCase(TestBaseWithPatch):
    """
    Reusable test case for testing LTI 1.3 configurations.
    """
    def setUp(self):
        """
        Set up an empty block configuration.
        """
        self._setup_lti_block()

        super().setUp()

    def _setup_lti_block(self):
        """
        Set's up an LTI block that is used in some tests.
        """
        # Generate RSA and save exports
        rsa_key = RSA.generate(1024)
        public_key = rsa_key.publickey().export_key()

        xblock_attributes = {
            'lti_version': LtiConfiguration.LTI_1P3,
            'lti_1p3_launch_url': 'http://tool.example/launch',
            'lti_1p3_oidc_url': 'http://tool.example/oidc',
            # We need to set the values below because they are not automatically
            # generated until the user selects `lti_version == 'lti_1p3'` on the
            # Studio configuration view.
            'lti_1p3_tool_public_key': public_key,
        }
        self.xblock = make_xblock('lti_consumer', LtiConsumerXBlock, xblock_attributes)
        self.location = self.xblock.scope_ids.usage_id
        self.other_location = UsageKey.from_string("block-v1:course+101+2024+type@lti_consumer+block@test")


@ddt.ddt
class TestConfigIdForBlock(Lti1P3TestCase):
    """
    Test config ID for block which is either a simple lookup
    or creates the config if it hasn't existed before. Config
    creation forks on store type.
    """
    def setUp(self):
        super().setUp()

        xblock_attributes = {
            'lti_version': LtiConfiguration.LTI_1P1,
        }
        self.xblock = make_xblock('lti_consumer', LtiConsumerXBlock, xblock_attributes)

    def test_double_fetch(self):
        self.xblock.config_type = 'database'
        config_id = config_id_for_block(self.xblock)
        self.assertIsNotNone(config_id)
        config = _get_config_by_config_id(config_id)
        self.assertEqual(LtiConfiguration.CONFIG_ON_DB, config.config_store)

        # fetch again, shouldn't make a new one
        second_config_id = config_id_for_block(self.xblock)
        self.assertEqual(config_id, second_config_id)

    @ddt.data(
        ('external', LtiConfiguration.CONFIG_EXTERNAL),
        ('database', LtiConfiguration.CONFIG_ON_DB),
        ('any other val', LtiConfiguration.CONFIG_ON_XBLOCK),
    )
    @patch('lti_consumer.api.get_external_config_from_filter')
    def test_store_types(self, mapping_pair, mock_external_config):
        mock_external_config.return_value = {"version": LtiConfiguration.LTI_1P3}
        str_store, result_store = mapping_pair
        self.xblock.config_type = str_store
        config_id = config_id_for_block(self.xblock)
        self.assertIsNotNone(config_id)
        config = _get_config_by_config_id(config_id)
        self.assertEqual(result_store, config.config_store)


@ddt.ddt
class TestGetOrCreateLocalLtiConfiguration(Lti1P3TestCase):
    """
    Unit tests for _get_or_create_local_lti_config API method.
    """
    def test_create_lti_config_if_inexistent(self):
        """
        Check if the API creates a model if no object matching properties is found.
        """
        lti_version = LtiConfiguration.LTI_1P3

        # Check that there's 1 in the models
        self.assertEqual(LtiConfiguration.objects.all().count(), 0)

        # Call API
        lti_config = _get_or_create_local_lti_config(
            lti_version=lti_version,
            block=self.xblock
        )

        self.assertEqual(LtiConfiguration.objects.all().count(), 1)
        # Check if the object was created
        self.assertEqual(lti_config.version, lti_version)
        self.assertEqual(str(lti_config.location), str(self.location))
        self.assertEqual(lti_config.config_store, LtiConfiguration.CONFIG_ON_XBLOCK)

    def test_retrieve_existing(self):
        """
        Check if the API retrieves a model if the configuration matches.
        """
        lti_version = LtiConfiguration.LTI_1P1

        lti_config = LtiConfiguration.objects.create(
            location=self.location
        )

        # Call API
        lti_config_retrieved = _get_or_create_local_lti_config(
            lti_version=lti_version,
            block=self.xblock
        )

        # Check if the object was created
        self.assertEqual(LtiConfiguration.objects.all().count(), 1)
        self.assertEqual(lti_config_retrieved, lti_config)

    def test_update_lti_version(self):
        """
        Check if the API retrieves the config and updates the API version.
        """
        lti_config = LtiConfiguration.objects.create(
            location=self.location,
            version=LtiConfiguration.LTI_1P1
        )

        # Call API
        _get_or_create_local_lti_config(
            lti_version=LtiConfiguration.LTI_1P3,
            block=self.xblock
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
        lti_version = LtiConfiguration.LTI_1P3
        lti_config = _get_or_create_local_lti_config(
            lti_version=lti_version,
            block=self.xblock,
            config_store=config_store,
        )

        self.assertEqual(lti_config.config_store, config_store)

    def test_external_config_values_are_cleared(self):
        """
        Check if the API clears external configuration values when external id is none
        """
        lti_version = LtiConfiguration.LTI_1P3

        lti_config = LtiConfiguration.objects.create(
            location=self.location,
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_EXTERNAL,
            external_id="test_plugin:test-id"
        )

        _get_or_create_local_lti_config(
            lti_version=lti_version,
            block=self.xblock,
        )

        lti_config.refresh_from_db()
        self.assertEqual(lti_config.version, lti_version)
        self.assertEqual(str(lti_config.location), str(self.location))
        self.assertEqual(lti_config.config_store, LtiConfiguration.CONFIG_ON_XBLOCK)
        self.assertEqual(lti_config.external_id, None)

    def test_passport_created_on_first_call(self):
        """
        Check if a passport is created when none exists.
        """
        lti_version = LtiConfiguration.LTI_1P3

        lti_config = _get_or_create_local_lti_config(
            lti_version=lti_version,
            block=self.xblock
        )
        lti_config.refresh_from_db()

        self.assertIsNotNone(lti_config.lti_1p3_passport)

    def test_passport_updated_when_single_use(self):
        """
        Check if passport is updated when it's only used by one config.
        """
        passport = Lti1p3Passport.objects.create(
            lti_1p3_tool_public_key='old_key',
            lti_1p3_tool_keyset_url='old_url'
        )
        LtiConfiguration.objects.create(
            location=self.location,
            lti_1p3_passport=passport
        )

        self.xblock.lti_1p3_tool_public_key = 'new_key'
        self.xblock.lti_1p3_tool_keyset_url = 'new_url'

        _get_or_create_local_lti_config(
            lti_version=LtiConfiguration.LTI_1P3,
            block=self.xblock
        )

        passport.refresh_from_db()
        self.assertEqual(passport.lti_1p3_tool_public_key, 'new_key')
        self.assertEqual(passport.lti_1p3_tool_keyset_url, 'new_url')

    def test_passport_not_updated_when_config_store_not_on_xblock(self):
        """
        Ensure that when the existing LtiConfiguration is not stored on the XBlock
        (e.g., CONFIG_ON_DB), the passport is not updated even if block key values differ.
        """
        passport = Lti1p3Passport.objects.create(
            lti_1p3_tool_public_key='shared_key',
            lti_1p3_tool_keyset_url='shared_url'
        )
        # Create a configuration that uses the passport but is stored on DB
        LtiConfiguration.objects.create(
            location=self.location,
            lti_1p3_passport=passport,
            config_store=LtiConfiguration.CONFIG_ON_DB,
        )

        # Block has different keys, but since the config is not on XBlock,
        # _ensure_lti_passport should not update the shared passport.
        self.xblock.lti_1p3_tool_public_key = 'new_key'
        self.xblock.lti_1p3_tool_keyset_url = 'new_url'

        _get_or_create_local_lti_config(
            lti_version=LtiConfiguration.LTI_1P3,
            block=self.xblock,
            config_store=LtiConfiguration.CONFIG_ON_XBLOCK,
        )

        passport.refresh_from_db()
        # passport should remain unchanged
        self.assertEqual(passport.lti_1p3_tool_public_key, 'shared_key')
        self.assertEqual(passport.lti_1p3_tool_keyset_url, 'shared_url')

    def test_passport_not_saved_when_no_changes(self):
        """
        Ensure that passport.save() is not called when passport fields already match the
        XBlock values and no update is required.
        """
        passport = Lti1p3Passport.objects.create(
            lti_1p3_tool_public_key='matching_key',
            lti_1p3_tool_keyset_url='matching_url'
        )
        LtiConfiguration.objects.create(
            location=self.location,
            lti_1p3_passport=passport
        )

        # Make block keys match the passport
        self.xblock.lti_1p3_tool_public_key = 'matching_key'
        self.xblock.lti_1p3_tool_keyset_url = 'matching_url'

        with patch.object(Lti1p3Passport, 'save') as mock_save:
            _get_or_create_local_lti_config(
                lti_version=LtiConfiguration.LTI_1P3,
                block=self.xblock
            )
            mock_save.assert_not_called()

    def test_config_not_saved_when_no_changes(self):
        """
        Ensure that LtiConfiguration.save() is not called when no fields change.
        """
        # Create a config that already matches the block's current values
        LtiConfiguration.objects.create(
            location=self.location,
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_ON_XBLOCK,
        )

        # Ensure block has default external_config of None and LTI version matches
        with patch.object(LtiConfiguration, 'save') as mock_save:
            _get_or_create_local_lti_config(
                lti_version=LtiConfiguration.LTI_1P3,
                block=self.xblock,
                config_store=LtiConfiguration.CONFIG_ON_XBLOCK,
            )
            mock_save.assert_not_called()

    def test_new_passport_created_on_key_conflict(self):
        """
        Check if a new passport is created when block key differs and passport is shared.
        """
        passport = Lti1p3Passport.objects.create(
            lti_1p3_tool_public_key='shared_key',
            lti_1p3_tool_keyset_url='shared_url'
        )
        # Create two configs sharing the passport
        LtiConfiguration.objects.create(location=self.location, lti_1p3_passport=passport)
        LtiConfiguration.objects.create(location=self.other_location, lti_1p3_passport=passport)

        self.xblock.lti_1p3_tool_key_mode = 'public_key'
        self.xblock.lti_1p3_tool_public_key = 'new_key'

        _get_or_create_local_lti_config(
            lti_version=LtiConfiguration.LTI_1P3,
            block=self.xblock
        )

        # Original passport unchanged
        passport.refresh_from_db()
        self.assertEqual(passport.lti_1p3_tool_public_key, 'shared_key')

        # Block has new passport
        self.assertNotEqual(self.xblock.lti_1p3_passport_id, str(passport.passport_id))

    def test_passport_unchanged_when_keys_match(self):
        """
        Check if passport is not updated when block keys already match.
        """
        passport = Lti1p3Passport.objects.create(
            lti_1p3_tool_public_key='matching_key',
            lti_1p3_tool_keyset_url='matching_url'
        )
        lti_config = LtiConfiguration.objects.create(
            location=self.location,
            lti_1p3_passport=passport
        )

        self.xblock.lti_1p3_tool_public_key = 'matching_key'
        self.xblock.lti_1p3_tool_keyset_url = 'matching_url'

        original_passport_id = passport.passport_id

        _get_or_create_local_lti_config(
            lti_version=LtiConfiguration.LTI_1P3,
            block=self.xblock
        )

        # Same passport used
        self.assertEqual(Lti1p3Passport.objects.count(), 1)
        lti_config.refresh_from_db()
        self.assertEqual(str(lti_config.lti_1p3_passport.passport_id), str(original_passport_id))

    @ddt.data(
        ('public_key', 'lti_1p3_tool_public_key'),
        ('keyset_url', 'lti_1p3_tool_keyset_url')
    )
    @ddt.unpack
    def test_new_passport_on_key_mode_change(self, key_mode, key_field):
        """
        Check if a new passport is created when key_mode-specific field changes.
        """
        passport = Lti1p3Passport.objects.create(
            lti_1p3_tool_public_key='old_key',
            lti_1p3_tool_keyset_url='old_url'
        )
        LtiConfiguration.objects.create(location=self.location, lti_1p3_passport=passport)
        LtiConfiguration.objects.create(location=self.other_location, lti_1p3_passport=passport)

        self.xblock.lti_1p3_tool_key_mode = key_mode
        setattr(self.xblock, key_field, 'new_value')

        _get_or_create_local_lti_config(
            lti_version=LtiConfiguration.LTI_1P3,
            block=self.xblock
        )

        self.assertEqual(Lti1p3Passport.objects.count(), 2)

    def test_passport_updated_when_fields_empty(self):
        """
        Check if passport is updated when both key fields are empty.
        """
        passport = Lti1p3Passport.objects.create(
            lti_1p3_tool_public_key='',
            lti_1p3_tool_keyset_url=''
        )
        LtiConfiguration.objects.create(
            location=self.location,
            lti_1p3_passport=passport
        )

        self.xblock.lti_1p3_tool_public_key = 'new_key'
        self.xblock.lti_1p3_tool_keyset_url = 'new_url'

        _get_or_create_local_lti_config(
            lti_version=LtiConfiguration.LTI_1P3,
            block=self.xblock
        )

        passport.refresh_from_db()
        self.assertEqual(passport.lti_1p3_tool_public_key, 'new_key')


@ddt.ddt
class TestValidateLti1p3LaunchData(TestCase):
    """
    Unit tests for validate_lti_1p3_launch_data API method.
    """
    def setUp(self):
        # Patch internal method to avoid calls to modulestore
        super().setUp()
        patcher = patch(
            'lti_consumer.models.LtiConfiguration.get_lti_consumer',
        )
        self.addCleanup(patcher.stop)

    def _assert_required_context_id_message(self, validation_messages):
        """
        Assert that validation_messages is the correct list of validation_messages for the required context_id
        attribute.

        Arguments:
            validation_messages (list): a list of strings representing validation messages
        """
        self.assertEqual(
            validation_messages,
            ["The context_id attribute is required in the launch data if any optional context properties are provided."]
        )

    def test_valid(self):
        """
        Ensure that valid instances of Lti1p3LaunchData are appropriately validated.
        """
        launch_data = Lti1p3LaunchData(
            user_id="1",
            user_role="student",
            config_id=_test_config_id,
            resource_link_id="resource_link_id",
            context_id="1",
            context_type=["course_offering"],
        )

        is_valid, validation_messages = validate_lti_1p3_launch_data(launch_data)

        self.assertEqual(is_valid, True)
        self.assertEqual(validation_messages, [])

    def test_invalid_context_values_context_id_required(self):
        """
        Ensure that instances of Lti1p3LaunchData that are instantiated with optional context_* attributes also are
        instantiated with the context_id attribute.
        """
        launch_data = Lti1p3LaunchData(
            user_id="1",
            user_role="student",
            config_id=_test_config_id,
            resource_link_id="resource_link_id",
        )

        launch_data.context_type = ["course_offering"]
        is_valid, validation_messages = validate_lti_1p3_launch_data(launch_data)
        self.assertEqual(is_valid, False)
        self._assert_required_context_id_message(validation_messages)

        launch_data.context_title = "context_title"
        is_valid, validation_messages = validate_lti_1p3_launch_data(launch_data)
        self.assertEqual(is_valid, False)
        self._assert_required_context_id_message(validation_messages)

        launch_data.context_label = "context_label"
        is_valid, validation_messages = validate_lti_1p3_launch_data(launch_data)
        self.assertEqual(is_valid, False)
        self._assert_required_context_id_message(validation_messages)

    @ddt.data("cat", "")
    def test_invalid_user_role(self, user_role):
        """
        Ensure that instances of Lti1p3LaunchData are instantiated with a user_role that is in the LTI_1P3_ROLE_MAP.
        """
        launch_data = Lti1p3LaunchData(
            user_id="1",
            user_role=user_role,
            config_id=_test_config_id,
            resource_link_id="resource_link_id",
        )

        is_valid, validation_messages = validate_lti_1p3_launch_data(launch_data)

        self.assertEqual(is_valid, False)
        self.assertEqual(
            validation_messages,
            [f"The user_role attribute {user_role} is not a valid user_role."]
        )

    def test_none_user_role(self):
        """
        Ensure that instances of Lti1p3LaunchData can be instantiated with a value of None for user_role.
        """
        launch_data = Lti1p3LaunchData(
            user_id="1",
            user_role=None,
            config_id=_test_config_id,
            resource_link_id="resource_link_id",
        )

        is_valid, validation_messages = validate_lti_1p3_launch_data(launch_data)

        self.assertEqual(is_valid, True)
        self.assertEqual(validation_messages, [])

    def test_invalid_context_type(self):
        """
        Ensure that instances of Lti1p3LaunchData are instantiated with a context_type that is one of group,
        course_offering, course_section, or course_template.
        """
        context_type = "invalid_context"

        launch_data = Lti1p3LaunchData(
            user_id="1",
            user_role="student",
            config_id=_test_config_id,
            resource_link_id="resource_link_id",
            context_id="1",
            context_type=context_type,
        )

        is_valid, validation_messages = validate_lti_1p3_launch_data(launch_data)

        self.assertEqual(is_valid, False)
        self.assertEqual(
            validation_messages,
            [f"The context_type attribute {context_type} in the launch data is not a valid context_type."]
        )

    @ddt.data("LtiStartProctoring", "LtiEndAssessment")
    def test_required_proctoring_launch_data_for_proctoring_message_type(self, message_type):
        launch_data = Lti1p3LaunchData(
            user_id="1",
            user_role="student",
            config_id=_test_config_id,
            resource_link_id="resource_link_id",
            message_type=message_type
        )

        is_valid, validation_messages = validate_lti_1p3_launch_data(launch_data)

        self.assertEqual(is_valid, False)
        self.assertEqual(
            validation_messages,
            [
                "The proctoring_launch_data attribute is required if the message_type attribute is "
                "\"LtiStartProctoring\" or \"LtiEndAssessment\"."
            ]
        )

    @ddt.data(None, "")
    def test_required_start_assessment_url_for_start_proctoring_message_type(self, start_assessment_url):
        proctoring_launch_data = Lti1p3ProctoringLaunchData(attempt_number=1, start_assessment_url=start_assessment_url)

        launch_data = Lti1p3LaunchData(
            user_id="1",
            user_role="student",
            config_id=_test_config_id,
            resource_link_id="resource_link_id",
            message_type="LtiStartProctoring",
            proctoring_launch_data=proctoring_launch_data,
        )

        is_valid, validation_messages = validate_lti_1p3_launch_data(launch_data)

        self.assertEqual(is_valid, False)
        self.assertEqual(
            validation_messages,
            [
                "The proctoring_start_assessment_url attribute is required if the message_type attribute is"
                " \"LtiStartProctoring\"."
            ]
        )


class TestGetLti1p3LaunchInfo(Lti1P3TestCase):
    """
    Unit tests for get_lti_1p3_launch_info API method.
    """
    def setUp(self):
        self.maxDiff = 30000
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

    @staticmethod
    def _get_lti_1p3_launch_data():
        return Lti1p3LaunchData(
            user_id="1",
            user_role="student",
            config_id=_test_config_id,
            resource_link_id="resource_link_id",
        )

    def test_retrieve_with_id(self):
        """
        Check if the API retrieves the launch with id.
        """
        lti_config = LtiConfiguration.objects.create(
            location=self.location,
            config_id=_test_config_id,
        )

        launch_data = self._get_lti_1p3_launch_data()

        # Call and check returns
        launch_info = get_lti_1p3_launch_info(launch_data)
        lti_config.refresh_from_db()

        # Not checking all data here, there's a test specific for that
        self.assertEqual(launch_info['client_id'], lti_config.lti_1p3_client_id)

    def test_retrieve_with_block(self):
        """
        Check if the API creates the model and retrieved correct info.
        """
        launch_data = self._get_lti_1p3_launch_data()

        # Create LTI Config and Deep linking object
        lti_config = LtiConfiguration.objects.create(
            location=self.location,
            config_id=_test_config_id,
        )
        LtiDlContentItem.objects.create(
            lti_configuration=lti_config,
            content_type=LtiDlContentItem.IMAGE,
            attributes={"test": "this is a test attribute"}
        )

        # Call API
        launch_info = get_lti_1p3_launch_info(launch_data)

        # Retrieve created config and check full launch info data
        lti_config = LtiConfiguration.objects.get()
        self.assertEqual(
            launch_info,
            {
                'client_id': lti_config.lti_1p3_client_id,
                'keyset_url': f'https://example.com/api/lti_consumer/v1/public_keysets/{lti_config.passport_id}',
                'deployment_id': '1',
                'oidc_callback': 'https://example.com/api/lti_consumer/v1/launch/',
                'token_url': f'https://example.com/api/lti_consumer/v1/token/{lti_config.passport_id}',
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
        lti_config = LtiConfiguration.objects.create(
            version=LtiConfiguration.LTI_1P3,
            config_id=_test_config_id,
        )
        lti_config.refresh_from_db()
        LtiDlContentItem.objects.create(
            lti_configuration=lti_config,
            content_type=LtiDlContentItem.IMAGE,
            attributes={"test": "this is a test attribute"}
        )

        launch_data = self._get_lti_1p3_launch_data()

        launch_info = get_lti_1p3_launch_info(launch_data)
        self.assertEqual(
            launch_info,
            {
                'client_id': lti_config.lti_1p3_client_id,
                'keyset_url': f'https://example.com/api/lti_consumer/v1/public_keysets/{lti_config.passport_id}',
                'deployment_id': '1',
                'oidc_callback': 'https://example.com/api/lti_consumer/v1/launch/',
                'token_url': f'https://example.com/api/lti_consumer/v1/token/{lti_config.passport_id}',
                'deep_linking_launch_url': 'http://example.com',

                'deep_linking_content_items':
                    '[\n    {\n        "test": "this is a test attribute"\n    }\n]',
            }
        )

    @patch('lti_consumer.api.get_external_config_from_filter')
    def test_launch_info_for_lti_config_with_external_configuration(
        self,
        filter_mock,
    ):
        """
        Check if the API can return launch info for LtiConfiguration using
        an external configuration.
        """
        external_id = 'test-app:test-slug'
        external_config = {'lti_1p3_client_id': 'test-client-id', 'lti_1p3_deployment_id': '12'}
        filter_mock.return_value = external_config
        lti_config = LtiConfiguration.objects.create(
            version=LtiConfiguration.LTI_1P3,
            config_id=_test_config_id,
            config_store=LtiConfiguration.CONFIG_EXTERNAL,
            external_id=external_id,
        )

        launch_info = get_lti_1p3_launch_info(self._get_lti_1p3_launch_data())

        self.assertEqual(
            launch_info,
            {
                'client_id': external_config.get('lti_1p3_client_id'),
                'keyset_url': 'https://example.com/api/lti_consumer/v1/public_keysets/{}'.format(
                    lti_config.external_id.replace(':', '/'),
                ),
                'deployment_id': external_config.get('lti_1p3_deployment_id', '1'),
                'oidc_callback': 'https://example.com/api/lti_consumer/v1/launch/',
                'token_url': 'https://example.com/api/lti_consumer/v1/token/{}'.format(
                    lti_config.external_id.replace(':', '/'),
                ),
                'deep_linking_launch_url': 'http://example.com',
                'deep_linking_content_items': None,
            },
        )
        filter_mock.assert_called_once_with({}, external_id)


class TestGetLti1p3LaunchUrl(Lti1P3TestCase):
    """
    Unit tests for LTI 1.3 launch API methods.
    """
    def setUp(self):
        """
        Method to set up test data.
        """
        super().setUp()
        # Create lti configuration
        self.lti_config = LtiConfiguration.objects.create(
            config_id=_test_config_id,
            location=self.xblock.scope_ids.usage_id,
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_ON_XBLOCK,
        )

    def _get_lti_1p3_launch_data(self):
        return Lti1p3LaunchData(
            user_id="1",
            user_role="student",
            config_id=self.lti_config.config_id,
            resource_link_id="resource_link_id",
        )

    def test_get_normal_lti_launch_url(self):
        """
        Check if the correct launch url is retrieved for a normal LTI 1.3 launch.
        """

        launch_data = self._get_lti_1p3_launch_data()

        # Call API for normal LTI launch initiation.
        launch_url = get_lti_1p3_launch_start_url(launch_data)

        parameters = parse_qs(urlparse(launch_url).query)
        launch_data = get_data_from_cache(parameters.get("lti_message_hint")[0])

        self.assertEqual(launch_data.message_type, "LtiResourceLinkRequest")
        self.assertEqual(launch_data.deep_linking_content_item_id, None)

    def test_get_deep_linking_lti_launch_url(self):
        """
        Check if the correct launch url is retrieved for a deep linking LTI 1.3 launch.
        """

        launch_data = self._get_lti_1p3_launch_data()

        # Call API for normal LTI launch initiation.
        launch_url = get_lti_1p3_launch_start_url(launch_data, deep_link_launch=True)

        parameters = parse_qs(urlparse(launch_url).query)
        launch_data = get_data_from_cache(parameters.get("lti_message_hint")[0])

        self.assertEqual(launch_data.message_type, "LtiDeepLinkingRequest")
        self.assertEqual(launch_data.deep_linking_content_item_id, None)

    def test_get_deep_linking_content_item_launch_url(self):
        """
        Check if the correct launch url is retrieved for a deep linking content item LTI 1.3 launch.
        """

        launch_data = self._get_lti_1p3_launch_data()

        # Call API for normal LTI launch initiation.
        launch_url = get_lti_1p3_launch_start_url(launch_data)

        parameters = parse_qs(urlparse(launch_url).query)
        launch_url = get_lti_1p3_launch_start_url(launch_data, dl_content_id="1")

        parameters = parse_qs(urlparse(launch_url).query)
        launch_data = get_data_from_cache(parameters.get("lti_message_hint")[0])

        self.assertEqual(launch_data.message_type, "LtiResourceLinkRequest")
        self.assertEqual(launch_data.deep_linking_content_item_id, "1")


class TestGetLti1p3ContentUrl(Lti1P3TestCase):
    """
    Unit tests for get_lti_1p3_launch_start_url API method.
    """
    def setUp(self):
        """
        Method to set up test data.
        """
        super().setUp()
        # Create lti configuration
        self.lti_config = LtiConfiguration.objects.create(
            config_id=_test_config_id,
            location=self.xblock.scope_ids.usage_id,
            version=LtiConfiguration.LTI_1P3,
            config_store=LtiConfiguration.CONFIG_ON_XBLOCK,
        )

    def _get_lti_1p3_launch_data(self):
        return Lti1p3LaunchData(
            user_id="1",
            user_role="student",
            config_id=self.lti_config.config_id,
            resource_link_id="resource_link_id",
        )

    @patch("lti_consumer.api.get_lti_1p3_launch_start_url")
    def test_lti_content_presentation(self, mock_get_launch_url):
        """
        Check if the correct LTI content presentation is returned on a normal LTI Launch.
        """

        launch_data = self._get_lti_1p3_launch_data()

        mock_get_launch_url.return_value = 'test_url'
        self.assertEqual(get_lti_1p3_content_url(launch_data), 'test_url')

    def test_lti_content_presentation_single_link(self):
        """
        Check if the correct LTI content presentation is returned if a `ltiResourceLink`
        content type is present.
        """

        launch_data = self._get_lti_1p3_launch_data()

        # Create LTI DL content items
        lti_content = LtiDlContentItem.objects.create(
            lti_configuration=self.lti_config,
            content_type=LtiDlContentItem.LTI_RESOURCE_LINK,
            attributes={},
        )

        # Call API to retrieve content item URL
        launch_url = get_lti_1p3_content_url(launch_data)

        parameters = parse_qs(urlparse(launch_url).query)
        launch_data = get_data_from_cache(parameters.get("lti_message_hint")[0])

        self.assertEqual(lti_content.id, launch_data.deep_linking_content_item_id)
        self.assertEqual(launch_data.message_type, "LtiResourceLinkRequest")

    def test_lti_content_presentation_multiple_links(self):
        """
        Check if the correct LTI content presentation is returned if multiple LTI DL
        content items are set up.
        """

        launch_data = self._get_lti_1p3_launch_data()

        launch_data_key = get_cache_key(
            app="lti",
            key="launch_data",
            user_id=launch_data.user_id,
            resource_link_id=launch_data.resource_link_id
        )

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
            f"/api/lti_consumer/v1/lti/{self.lti_config.id}/lti-dl/content?launch_data_key={launch_data_key}",
            get_lti_1p3_content_url(launch_data),
        )


class TestGetLtiDlContentItemData(Lti1P3TestCase):
    """
    Unit tests for get_deep_linking_data API method.
    """
    def setUp(self):
        """
        Set up an empty block configuration.
        """
        super().setUp()
        self.lti_config = LtiConfiguration.objects.create(
            location='block-v1:course+test+2020+type@problem+block@test',
        )

    def test_lti_retrieve_content_item(self):
        """
        Check if the API return the right content item.
        """
        content_item = LtiDlContentItem.objects.create(
            lti_configuration=self.lti_config,
            content_type=LtiDlContentItem.LTI_RESOURCE_LINK,
            attributes={"test": "test"},
        )

        data = get_deep_linking_data(content_item.id, self.lti_config.config_id)

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
            get_deep_linking_data(content_item.id, self.lti_config.config_id)


class TestGetEndAssessmentReturn(TestCase):
    """
    Unit tests for get_end_assessment_return API method.
    """
    def setUp(self):
        # Patch internal method to avoid calls to modulestore
        super().setUp()
        patcher = patch(
            'lti_consumer.models.LtiConfiguration.get_lti_consumer',
        )
        self.addCleanup(patcher.stop)

    @patch('lti_consumer.api.get_data_from_cache')
    def test_get_end_assessment_return(self, mock_get_data_from_cache):
        """Ensures get_end_assessment_return returns whatever is in the cache."""

        get_data_from_cache_return_value = "end_assessment_return"

        mock_get_data_from_cache.return_value = get_data_from_cache_return_value

        self.assertEqual(get_end_assessment_return("user_id", "resource_link_id"), get_data_from_cache_return_value)
