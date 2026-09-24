"""
LTI Consumer related Signal handlers
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver, Signal

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
    line_item = instance.line_item
    lti_config = line_item.lti_configuration

    # Only save score if the `line_item.resource_link_id` is the same as
    # `lti_configuration.location` to prevent LTI tools to alter grades they don't
    # have permissions to.
    # TODO: This security mechanism will need to be reworked once we enable LTI 1.3
    # reusability to allow one configuration to save scores on multiple placements,
    # but still locking down access to the items that are using the LTI configurtion.
    if line_item.resource_link_id != lti_config.location:
        log.warning(
            "LTI tool tried publishing score %r to block %s (outside allowed scope of: %s).",
            instance,
            line_item.resource_link_id,
            lti_config.location,
        )
        return

    # The grade being submitted must be the final one - `FullyGraded`. This is routine, expected
    # tool behavior to not be the case yet (interim `Pending`/`InProgress` saves are far more
    # common than the final one), so it's silently skipped here, not logged, to avoid flooding
    # the logs.
    if instance.grading_progress != LtiAgsScore.FULLY_GRADED:
        return

    # From here on the score is final, so failing to publish it is the actionable case worth
    # logging below. Before publishing to the LMS, check that:
    # 1. This LineItem is linked to a LMS grade - the `LtiResouceLinkId` field is set
    # 2. There's a grade present in this score - `scoreGiven` is present
    # 3. `scoreMaximum` is a usable, positive denominator for the normalized score below
    # Note: (2) and (3) must be `is not None`/range checks, not truthiness checks, since a
    # `scoreGiven` or `scoreMaximum` of 0 is falsy but a legitimate value for the former.
    can_publish = (
        bool(line_item.resource_link_id) and
        instance.score_given is not None and
        instance.score_maximum is not None and
        instance.score_maximum > 0
    )
    if not can_publish:
        log.info(
            "LTI AGS grade publish skipped: score=%r grading_progress=%s resource_link_id=%s "
            "score_given=%s score_maximum=%s.",
            instance,
            instance.grading_progress,
            line_item.resource_link_id,
            instance.score_given,
            instance.score_maximum,
        )
        return

    try:
        # Load block using LMS APIs and check if the block is graded and still accept grades.
        block = compat.load_block_as_user(line_item.resource_link_id)
        if not block.has_score:
            log.info(
                "LTI AGS grade publish skipped: score=%r resource_link_id=%s has_score=%s.",
                instance,
                line_item.resource_link_id,
                block.has_score,
            )
        else:
            # Computed once and reused below: previously `is_past_due()`/`accept_grades_past_due`
            # were never evaluated at all when `has_score` was False (short-circuited by `and`),
            # so neither is touched here unless `has_score` is True.
            is_past_due = block.is_past_due()
            if not is_past_due or block.accept_grades_past_due:
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
                    block.scope_ids.usage_id,
                    user,
                    score,
                )
                block.set_user_module_score(user, score, block.max_score(), instance.comment)
            else:
                log.info(
                    "LTI AGS grade publish skipped: score=%r resource_link_id=%s has_score=%s "
                    "is_past_due=%s accept_grades_past_due=%s.",
                    instance,
                    line_item.resource_link_id,
                    block.has_score,
                    is_past_due,
                    block.accept_grades_past_due,
                )

    # This is a catch all exception to catch and log any issues related to loading the block
    # from the modulestore and other LMS API calls
    except Exception as exc:
        log.exception(
            "Error while publishing score %r to block %s to LMS: %s",
            instance,
            line_item.resource_link_id,
            exc,
        )
        raise exc


LTI_1P3_PROCTORING_ASSESSMENT_STARTED = Signal()
