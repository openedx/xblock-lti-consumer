"""
LTI Consumer related Signal handlers
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import Signal, receiver
from openedx_events.content_authoring.data import LibraryBlockData, XBlockData
from openedx_events.content_authoring.signals import LIBRARY_BLOCK_DELETED, XBLOCK_DELETED

from lti_consumer.models import LtiAgsScore, LtiConfiguration, LtiXBlockConfig
from lti_consumer.plugin import compat

log = logging.getLogger(__name__)
SignalHandler = compat.get_signal_handler()


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

    # Before starting to publish grades to the LMS, check that:
    # 1. The grade being submitted in the final one - `FullyGraded`
    # 2. This LineItem is linked to a LMS grade - the `LtiResouceLinkId` field is set
    # 3. There's a valid grade in this score - `scoreGiven` is set
    if instance.grading_progress == LtiAgsScore.FULLY_GRADED \
            and line_item.resource_link_id \
            and instance.score_given:
        try:
            # Load block using LMS APIs and check if the block is graded and still accept grades.
            block = compat.load_block_as_user(line_item.resource_link_id)
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
                    block.scope_ids.usage_id,
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
                line_item.resource_link_id,
                exc,
            )
            raise exc


LTI_1P3_PROCTORING_ASSESSMENT_STARTED = Signal()


@receiver(SignalHandler.pre_item_deleted if SignalHandler else [])
def delete_child_lti_configurations(**kwargs):
    """
    Delete lti configurtion from database for this block children.
    """
    usage_key = kwargs.get('usage_key')
    if usage_key:
        # Strip branch info
        usage_key = usage_key.for_branch(None)
        try:
            deleted_block = compat.load_enough_xblock(usage_key)
        except Exception as e:
            log.warning(f"Cannot find xblock for key {usage_key}. Reason: {str(e)}. ")
            return
        id_list = {deleted_block.location}
        for block in compat.yield_dynamic_block_descendants(deleted_block, kwargs.get('user_id')):
            id_list.add(block.location)

        LtiXBlockConfig.objects.filter(
            location__in=id_list
        ).delete()
        log.info(f"Deleted {len(id_list)} lti xblock configurations in modulestore")
        result = LtiConfiguration.objects.filter(ltixblockconfig__isnull=True).delete()
        log.info(f"Deleted {result} lti configuration objects in library")


@receiver(XBLOCK_DELETED)
def delete_lti_configuration(**kwargs):
    """
    Delete lti configurtion from database for this block.
    """
    xblock_info = kwargs.get("xblock_info", None)
    if not xblock_info or not isinstance(xblock_info, XBlockData):
        log.error("Received null or incorrect data for event")
        return

    LtiXBlockConfig.objects.filter(
        location=xblock_info.usage_key
    ).delete()
    result = LtiConfiguration.objects.filter(ltixblockconfig__isnull=True).delete()
    log.info(f"Deleted {result} lti configuration objects in library")


@receiver(LIBRARY_BLOCK_DELETED)
def delete_lib_lti_configuration(**kwargs):
    """
    Delete lti configurtion from database for this library block.
    """
    library_block = kwargs.get("library_block", None)
    if not library_block or not isinstance(library_block, LibraryBlockData):
        log.error("Received null or incorrect data for event")
        return

    LtiXBlockConfig.objects.filter(
        location=library_block.usage_key
    ).delete()
    result = LtiConfiguration.objects.filter(ltixblockconfig__isnull=True).delete()
    log.info(f"Deleted {result} lti configuration objects in library")
