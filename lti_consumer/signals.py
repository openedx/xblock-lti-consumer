"""
LTI Consumer related Signal handlers
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from lti_consumer.models import LtiAgsScore
from lti_consumer.plugin import compat


log = logging.getLogger(__name__)


@receiver(post_save, sender=LtiAgsScore, dispatch_uid='publish_grade_on_score_update')
def publish_grade_on_score_update(sender, instance, **kwargs):  # pylint: disable=unused-argument
    """
    Publish grade to xblock whenever score saved/updated and its grading_progress is set to FullyGraded.

    This method DOES NOT WORK on Studio, since it relies on APIs only available and configured
    in the LMS. Trying to trigger this signal from Studio (from the Django-admin interface, for example)
    throw an exception.
    """
    # Before starting to publish grades to the LMS, check that:
    # 1. The grade being submitted in the final one - `FullyGraded`
    # 2. This LineItem is linked to a LMS grade - the `LtiResouceLinkId` field is set
    # 3. There's a valid grade in this score - `scoreGiven` is set
    if instance.grading_progress == LtiAgsScore.FULLY_GRADED \
            and instance.line_item.resource_link_id \
            and instance.score_given:
        try:
            # Load block using LMS APIs and check if the block is graded and still accept grades.
            block = compat.load_block_as_anonymous_user(instance.line_item.resource_link_id)
            if block.has_score and (not block.is_past_due() or block.accept_grades_past_due):
                # Map external ID to platform user
                user = compat.get_user_from_external_user_id(instance.user_id)

                # The LTI AGS spec allow tools to send grades higher than score maximum, so
                # we have to cap the score sent to the gradebook to the maximum allowed value.
                # Also, this is an normalized score ranging from 0 to 1.
                score = min(instance.score_given, instance.score_maximum) / instance.score_maximum

                # Set module score using XBlock custom method to do so.
                # This saves the score on both the XBlock's K/V store as well as in
                # the LMS database.
                log.info(
                    "Publishing LTI grade from block %s to LMS. User: %s (score: %s)",
                    block.location,
                    user,
                    score,
                )
                block.set_user_module_score(user, score, block.max_score(), instance.comment)

        # This is a catch all exception to catch and log any issues related to loading the block
        # from the modulestore and other LMS API calls
        except Exception as exc:
            log.exception(
                "Error while publishing score %r to block %s to LMS: %s",
                instance,
                instance.line_item.resource_link_id,
                exc,
            )
            raise exc
