"""
Tests for LTI Consumer signal handlers.
"""
from datetime import datetime
from unittest.mock import Mock, patch

from ddt import data, ddt, unpack
from django.test import TestCase
from opaque_keys.edx.keys import UsageKey
from openedx_events.content_authoring.data import LibraryBlockData, XBlockData

from lti_consumer.models import LtiAgsLineItem, LtiAgsScore, LtiConfiguration
from lti_consumer.signals.signals import (
    delete_child_lti_configurations,
    delete_lib_lti_configuration,
    delete_lti_configuration,
)


class PublishGradeOnScoreUpdateTest(TestCase):
    """
    Test the `publish_grade_on_score_update` signal.
    """

    def setUp(self):
        """
        Set up resources for signal testing.
        """
        self.location = UsageKey.from_string(
            "block-v1:course+test+2020+type@problem+block@test"
        )

        # Patch internal method to avoid calls to modulestore
        self._block_mock = Mock()
        self._block_mock.display_name = "consumer"
        self._block_mock.context_id = "some-context-id"
        compat_mock = patch("lti_consumer.models.compat")
        self.addCleanup(compat_mock.stop)
        self._compat_mock = compat_mock.start()
        self._compat_mock.get_user_from_external_user_id.return_value = Mock()
        self._compat_mock.load_block_as_user.return_value = self._block_mock
        self._compat_mock.load_enough_xblock.return_value = self._block_mock
        self._block_mock.lti_1p3_passport_id = "e9feb139-4e4c-4fb1-96ee-e614f1e04356"

        signals_compat_mock = patch("lti_consumer.signals.signals.compat")
        self.addCleanup(signals_compat_mock.stop)
        self._signals_compat_mock = signals_compat_mock.start()
        self._signals_compat_mock.get_user_from_external_user_id.return_value = Mock()
        self._signals_compat_mock.load_block_as_user.return_value = self._block_mock
        self._signals_compat_mock.load_enough_xblock.return_value = self._block_mock
        self._block_mock.lti_1p3_passport_id = "e9feb139-4e4c-4fb1-96ee-e614f1e04356"
        # Create configuration
        self.lti_config = LtiConfiguration.objects.create(
            location=self.location,
            version=LtiConfiguration.LTI_1P3,
        )

    def test_grade_publish_not_done_when_wrong_line_item(self):
        """
        Test grade publish after for a different UsageKey than set on
        `lti_config.location`.
        """
        # Create LineItem with `resource_link_id` != `lti_config.id`
        line_item = LtiAgsLineItem.objects.create(
            lti_configuration=self.lti_config,
            resource_id="test",
            resource_link_id=UsageKey.from_string(
                "block-v1:course+test+2020+type@problem+block@different"
            ),
            label="test label",
            score_maximum=100
        )

        # Save score and check that LMS method wasn't called.
        LtiAgsScore.objects.create(
            line_item=line_item,
            score_given=1,
            score_maximum=1,
            activity_progress=LtiAgsScore.COMPLETED,
            grading_progress=LtiAgsScore.FULLY_GRADED,
            user_id="test",
            timestamp=datetime.now(),
        )

        # Check that methods to save grades are not called
        self._block_mock.set_user_module_score.assert_not_called()
        self._compat_mock.get_user_from_external_user_id.assert_not_called()
        self._compat_mock.load_block_as_user.assert_not_called()

    def test_grade_publish(self):
        """
        Test grade publish after if the UsageKey is equal to
        the one on `lti_config.location`.
        """
        # Create LineItem with `resource_link_id` != `lti_config.id`
        line_item = LtiAgsLineItem.objects.create(
            lti_configuration=self.lti_config,
            resource_id="test",
            resource_link_id=self.location,
            label="test label",
            score_maximum=100
        )

        # Save score and check that LMS method wasn't called.
        LtiAgsScore.objects.create(
            line_item=line_item,
            score_given=1,
            score_maximum=1,
            activity_progress=LtiAgsScore.COMPLETED,
            grading_progress=LtiAgsScore.FULLY_GRADED,
            user_id="test",
            timestamp=datetime.now(),
        )

        # Check that methods to save grades are called
        self._block_mock.set_user_module_score.assert_called_once()
        self._signals_compat_mock.get_user_from_external_user_id.assert_called_once()
        self._signals_compat_mock.load_block_as_user.assert_called_once()


@ddt
class TestDeleteLtiConfiguration(TestCase):
    """Tests for delete_lti_configuration function."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_usage_key = UsageKey.from_string("block-v1:course+101+2024+type@lti_consumer+block@test")

        self.xblock_data = Mock(spec=XBlockData)
        self.xblock_data.usage_key = self.mock_usage_key

    @patch('lti_consumer.signals.signals.Lti1p3Passport')
    @patch('lti_consumer.signals.signals.LtiConfiguration')
    @patch('lti_consumer.signals.signals.log')
    def test_delete_lti_configuration_success(self, mock_log, mock_lti_config, mock_passport):
        """Test successful deletion with various passport counts."""
        mock_lti_config.objects.filter.return_value.delete.return_value = None

        # Test with multiple passports deleted
        mock_passport.objects.filter.return_value.delete.return_value = (5, {'Lti1p3Passport': 5})
        delete_lti_configuration(xblock_info=self.xblock_data)

        mock_lti_config.objects.filter.assert_called_with(location=str(self.xblock_data.usage_key))
        mock_passport.objects.filter.assert_called_with(lticonfiguration__isnull=True)
        assert mock_log.info.call_count == 1
        assert "5" in mock_log.info.call_args[0][0]

        # Reset and test with no passports deleted
        mock_log.reset_mock()
        mock_lti_config.reset_mock()
        mock_passport.reset_mock()
        mock_lti_config.objects.filter.return_value.delete.return_value = None
        mock_passport.objects.filter.return_value.delete.return_value = (0, {})

        delete_lti_configuration(xblock_info=self.xblock_data)
        assert "0" in mock_log.info.call_args[0][0]

    @data(
        None,
        "invalid_string",
        {"usage_key": "test"},
        123,
    )
    @patch('lti_consumer.signals.signals.log')
    def test_delete_lti_configuration_invalid_input(self, invalid_input, mock_log):
        """Test with invalid xblock_info inputs."""
        delete_lti_configuration(xblock_info=invalid_input)
        mock_log.error.assert_called_once_with("Received null or incorrect data for event")

    @patch('lti_consumer.signals.signals.log')
    def test_delete_lti_configuration_missing_xblock_info(self, mock_log):
        """Test with missing xblock_info kwarg."""
        delete_lti_configuration()
        mock_log.error.assert_called_once_with("Received null or incorrect data for event")

    @patch('lti_consumer.signals.signals.Lti1p3Passport')
    @patch('lti_consumer.signals.signals.LtiConfiguration')
    @patch('lti_consumer.signals.signals.log')
    def test_delete_lti_configuration_extra_kwargs_ignored(self, mock_log, mock_lti_config, mock_passport):
        """Test that extra kwargs are safely ignored."""
        mock_lti_config.objects.filter.return_value.delete.return_value = None
        mock_passport.objects.filter.return_value.delete.return_value = (0, {})

        delete_lti_configuration(
            xblock_info=self.xblock_data,
            extra_param="ignored",
            another_param=123
        )

        mock_lti_config.objects.filter.assert_called_once()
        mock_log.error.assert_not_called()


@ddt
class TestDeleteChildLtiConfigurations(TestCase):
    """Tests for delete_child_lti_configurations function."""
    def setUp(self):
        """Set up test fixtures."""
        self.usage_key = UsageKey.from_string("block-v1:course+test+2020+type@problem+block@parent")

    def _create_child_block(self, block_id):
        """Helper to create a mock child block."""
        child = Mock()
        child.location = UsageKey.from_string(
            f"block-v1:course+test+2020+type@problem+block@{block_id}"
        )
        return child

    def _setup_mocks(self, children_count=0, passport_count=0, load_error=None):
        """Helper to setup common mock patches."""
        parent_block = Mock()
        parent_block.location = self.usage_key

        children = [self._create_child_block(f"child{i}") for i in range(children_count)]

        patches = {
            'compat': patch("lti_consumer.signals.signals.compat"),
            'lti_config': patch("lti_consumer.signals.signals.LtiConfiguration"),
            'passport': patch("lti_consumer.signals.signals.Lti1p3Passport"),
            'log': patch("lti_consumer.signals.signals.log"),
        }

        mocks = {name: p.start() for name, p in patches.items()}
        self.addCleanup(lambda: [p.stop() for p in patches.values()])

        if load_error:
            mocks['compat'].load_enough_xblock.side_effect = load_error
        else:
            mocks['compat'].load_enough_xblock.return_value = parent_block
            mocks['compat'].yield_dynamic_block_descendants.return_value = children

        mocks['lti_config'].objects.filter.return_value.delete.return_value = None
        mocks['passport'].objects.filter.return_value.delete.return_value = (
            passport_count,
            {'Lti1p3Passport': passport_count} if passport_count else {}
        )

        return mocks, parent_block, children

    @data(
        (0, 0),  # no children, no passports deleted
        (2, 2),  # 2 children, 2 passports deleted
        (1, 5),  # 1 child, 5 passports deleted
    )
    @unpack
    def test_delete_child_lti_configurations_success(self, children_count, passport_count):
        """Test successful deletion with various child/passport counts."""

        mocks, parent_block, children = self._setup_mocks(children_count, passport_count)

        delete_child_lti_configurations(usage_key=self.usage_key, user_id="test_user")

        # Verify load_enough_xblock called with stripped branch
        mocks['compat'].load_enough_xblock.assert_called_once_with(self.usage_key.for_branch(None))

        # Verify descendants iterator called
        mocks['compat'].yield_dynamic_block_descendants.assert_called_once_with(parent_block, "test_user")

        # Verify correct locations in filter
        call_args = mocks['lti_config'].objects.filter.call_args
        locations = call_args[1]['location__in']
        assert len(locations) == children_count + 1  # parent + children
        assert str(parent_block.location) in locations
        for child in children:
            assert str(child.location) in locations

        # Verify deletion logged
        assert mocks['log'].info.call_count >= 1

    @data(
        None,
        UsageKey.from_string("block-v1:course+test+2020+type@problem+block@parent").for_branch("branch"),
    )
    def test_delete_child_lti_configurations_invalid_usage_key(self, usage_key):
        """Test with None or missing usage_key."""
        mocks, _, _ = self._setup_mocks()

        if usage_key is None:
            delete_child_lti_configurations(usage_key=None)
        else:
            # Test branch stripping
            delete_child_lti_configurations(usage_key=usage_key, user_id="test_user")
            mocks['compat'].load_enough_xblock.assert_called_once_with(self.usage_key.for_branch(None))

    @data(
        Exception("Block not found"),
        ValueError("Invalid block"),
        RuntimeError("Load failed"),
    )
    def test_delete_child_lti_configurations_load_block_fails(self, error):
        """Test when load_enough_xblock raises exceptions."""
        mocks, _, _ = self._setup_mocks(load_error=error)

        delete_child_lti_configurations(usage_key=self.usage_key, user_id="test_user")

        # Verify warning logged with error details
        mocks['log'].warning.assert_called_once()
        warning_msg = mocks['log'].warning.call_args[0][0]
        assert "Cannot find xblock for key" in warning_msg
        assert str(error) in warning_msg

        # Verify no deletion attempted
        mocks['lti_config'].objects.filter.assert_not_called()

    def test_delete_child_lti_configurations_no_usage_key(self):
        """Test when usage_key is not provided."""
        with patch("lti_consumer.signals.signals.log") as mock_log:
            delete_child_lti_configurations(usage_key=None)

            # Should return early without logging
            mock_log.warning.assert_not_called()
            mock_log.info.assert_not_called()


@ddt
class TestDeleteLibLtiConfiguration(TestCase):
    """Tests for delete_lib_lti_configuration function."""

    def setUp(self):
        """Set up test fixtures."""
        self.library_block = Mock(spec=LibraryBlockData)
        self.library_block.usage_key = UsageKey.from_string(
            "lb:TestOrg:TestLibrary:problem:test_problem"
        )

    def _setup_mocks(self, passport_count=0):
        """Helper to setup common mock patches."""
        patches = {
            'lti_config': patch("lti_consumer.signals.signals.LtiConfiguration"),
            'passport': patch("lti_consumer.signals.signals.Lti1p3Passport"),
            'log': patch("lti_consumer.signals.signals.log"),
        }

        mocks = {name: p.start() for name, p in patches.items()}
        self.addCleanup(lambda: [p.stop() for p in patches.values()])

        mocks['lti_config'].objects.filter.return_value.delete.return_value = None
        mocks['passport'].objects.filter.return_value.delete.return_value = (
            passport_count,
            {'Lti1p3Passport': passport_count} if passport_count else {}
        )

        return mocks

    @data(0, 1, 5, 3)
    def test_delete_lib_lti_configuration_success(self, passport_count):
        """Test successful deletion with various passport counts."""
        mocks = self._setup_mocks(passport_count)

        delete_lib_lti_configuration(library_block=self.library_block)

        # Verify LtiConfiguration filter called with correct location
        mocks['lti_config'].objects.filter.assert_called_once_with(
            location=str(self.library_block.usage_key)
        )

        # Verify orphaned passports deleted
        mocks['passport'].objects.filter.assert_called_once_with(lticonfiguration__isnull=True)

        # Verify info logged with passport count
        mocks['log'].info.assert_called_once()
        log_msg = mocks['log'].info.call_args[0][0]
        assert str(passport_count) in log_msg
        if passport_count > 0:
            assert "lti 1.3 passport" in log_msg

    @data(
        None,
        "invalid_string",
        {"usage_key": "test"},
        123,
        Mock(),  # Mock without LibraryBlockData spec
    )
    def test_delete_lib_lti_configuration_invalid_input(self, library_block):
        """Test with invalid library_block inputs."""
        mocks = self._setup_mocks()

        delete_lib_lti_configuration(library_block=library_block)

        mocks['log'].error.assert_called_once_with("Received null or incorrect data for event")
        mocks['lti_config'].objects.filter.assert_not_called()

    def test_delete_lib_lti_configuration_missing_library_block(self):
        """Test when library_block kwarg is missing."""
        mocks = self._setup_mocks()

        delete_lib_lti_configuration()

        mocks['log'].error.assert_called_once_with("Received null or incorrect data for event")

    def test_delete_lib_lti_configuration_extra_kwargs_ignored(self):
        """Test that extra kwargs are safely ignored."""
        mocks = self._setup_mocks(passport_count=2)

        delete_lib_lti_configuration(
            library_block=self.library_block,
            extra_param="ignored",
            another_param=123
        )

        mocks['lti_config'].objects.filter.assert_called_once()
        mocks['log'].info.assert_called_once()
