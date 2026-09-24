"""
Tests for LTI Advantage Assignments and Grades Service views.
"""
from datetime import datetime
from unittest.mock import patch, Mock

from django.core.exceptions import ValidationError
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

    def test_grade_publish_with_zero_score(self):
        """
        Test that a `scoreGiven` of 0 is published like any other score.

        `score_given` is falsy for a `FloatField` value of `0.0`. Before this fix, the guard used
        a truthiness check (`and instance.score_given`) and silently skipped a legitimate zero
        score; it must now use `is not None` so 0 is treated as a present, valid grade.
        """
        line_item = LtiAgsLineItem.objects.create(
            lti_configuration=self.lti_config,
            resource_id="test",
            resource_link_id=self.location,
            label="test label",
            score_maximum=100
        )

        LtiAgsScore.objects.create(
            line_item=line_item,
            score_given=0,
            score_maximum=100,
            activity_progress=LtiAgsScore.COMPLETED,
            grading_progress=LtiAgsScore.FULLY_GRADED,
            user_id="test",
            timestamp=datetime.now(),
        )

        self._block_mock.set_user_module_score.assert_called_once()
        call_args = self._block_mock.set_user_module_score.call_args.args
        self.assertEqual(call_args[1], 0)

    def test_grade_publish_not_done_when_score_given_missing(self):
        """
        Test that grade publish is still skipped (not errored) when `score_given` is absent, e.g.
        an AGS "erase score" request that nulls out `scoreGiven`/`scoreMaximum`.

        Unlike the zero-score case above, this is unchanged behavior: `score_given=None` was
        already falsy under the old truthiness check, and is also caught by the new
        `is not None` check, so this is a lock-in test rather than a new assertion.
        """
        line_item = LtiAgsLineItem.objects.create(
            lti_configuration=self.lti_config,
            resource_id="test",
            resource_link_id=self.location,
            label="test label",
            score_maximum=100
        )

        LtiAgsScore.objects.create(
            line_item=line_item,
            score_given=None,
            score_maximum=None,
            activity_progress=LtiAgsScore.COMPLETED,
            grading_progress=LtiAgsScore.FULLY_GRADED,
            user_id="test",
            timestamp=datetime.now(),
        )

        self._block_mock.set_user_module_score.assert_not_called()
        self._compat_mock.load_block_as_user.assert_not_called()

    def test_grade_publish_not_done_when_score_maximum_zero(self):
        """
        Test that `score_maximum=0` alongside a set `score_given` is rejected at save time,
        never reaching the publish signal at all.

        This combination can't be produced through the AGS API (the serializer rejects a
        `scoreMaximum` of 0). It previously could still be produced via the Django admin or
        direct ORM access -- `MinValueValidator(0)` and the old `LtiAgsScore.clean()` both
        permitted it (0 is a valid, non-`None` value) -- reaching this signal, whose normalized-
        score division would otherwise crash on it (worked around, at the time, by a
        `score_maximum > 0` guard in the signal itself).

        `LtiAgsScore.clean()` now rejects `score_maximum <= 0` whenever `score_given` is set
        (not just `score_maximum is None`), closing the gap at the source: this state can no
        longer be saved at all, so the signal's own guard is never exercised by it. See
        `lti_consumer.tests.unit.test_models.TestLtiAgsScoreModel.
        test_score_max_fails_when_zero_with_score_given_set` for the model-level assertion.
        """
        line_item = LtiAgsLineItem.objects.create(
            lti_configuration=self.lti_config,
            resource_id="test",
            resource_link_id=self.location,
            label="test label",
            score_maximum=100
        )

        with self.assertRaises(ValidationError):
            LtiAgsScore.objects.create(
                line_item=line_item,
                score_given=10,
                score_maximum=0,
                activity_progress=LtiAgsScore.COMPLETED,
                grading_progress=LtiAgsScore.FULLY_GRADED,
                user_id="test",
                timestamp=datetime.now(),
            )

        self._block_mock.set_user_module_score.assert_not_called()
        self._compat_mock.load_block_as_user.assert_not_called()
