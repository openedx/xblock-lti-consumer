"""
LTI Consumer related Signal handlers
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from lti_consumer.models import LtiAgsScore
from lti_consumer.plugin.compat import (
    publish_grade,
    load_block,
    get_user_from_external_user_id,
)


@receiver(post_save, sender=LtiAgsScore, dispatch_uid='publish_grade_on_score_update')
def publish_grade_on_score_update(sender, instance, **kwargs):  # pylint: disable=unused-argument
    """
    Publish grade to xblock whenever score saved/updated and its grading_progress is set to FullyGraded.
    """
    if instance.grading_progress == LtiAgsScore.FULLY_GRADED:
        block = load_block(instance.line_item.resource_link_id)
        if not block.is_past_due():
            user = get_user_from_external_user_id(instance.user_id)
            publish_grade(
                block,
                user,
                instance.score_given,
                instance.score_maximum,
                comment=instance.comment
            )
