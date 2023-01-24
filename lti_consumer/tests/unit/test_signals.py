"""
Tests for LTI Advantage Assignments and Grades Service views.
"""
from datetime import datetime
from unittest.mock import patch, Mock

from django.test import TestCase
from opaque_keys.edx.keys import UsageKey

from lti_consumer.models import LtiConfiguration, LtiAgsLineItem, LtiAgsScore


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

        # Create configuration
        self.lti_config = LtiConfiguration.objects.create(
            location=self.location,
            version=LtiConfiguration.LTI_1P3,
        )

        # Patch internal method to avoid calls to modulestore
        self._block_mock = Mock()
        compat_mock = patch("lti_consumer.signals.signals.compat")
        self.addCleanup(compat_mock.stop)
        self._compat_mock = compat_mock.start()
        self._compat_mock.get_user_from_external_user_id.return_value = Mock()
        self._compat_mock.load_block_as_user.return_value = self._block_mock

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
        self._compat_mock.get_user_from_external_user_id.assert_called_once()
        self._compat_mock.load_block_as_user.assert_called_once()
