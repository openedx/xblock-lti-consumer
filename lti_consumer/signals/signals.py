"""
LTI Consumer related Signal handlers
"""
import logging
import uuid

from django.db.models.signals import post_save
from django.dispatch import Signal, receiver
from openedx_events.content_authoring.data import DuplicatedXBlockData, LibraryBlockData, XBlockData
from openedx_events.content_authoring.signals import LIBRARY_BLOCK_DELETED, XBLOCK_DELETED, XBLOCK_DUPLICATED

from lti_consumer.models import Lti1p3Passport, LtiAgsScore, LtiConfiguration
from lti_consumer.plugin import compat
from lti_consumer.utils import model_to_dict

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
    # but still locking down access to the items that are using the LTI configuration.
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


@receiver(post_save, sender=LtiConfiguration, dispatch_uid='create_lti_1p3_passport')
def create_lti_1p3_passport(sender, instance: LtiConfiguration, **kwargs):  # pylint: disable=unused-argument
    instance.get_or_create_lti_1p3_passport()


@receiver(SignalHandler.pre_item_delete if SignalHandler else [])
def delete_child_lti_configurations(**kwargs):
    """
    Delete lti configuration from database for this block children.
    """
    usage_key = kwargs.get('usage_key')
    if usage_key:
        # Strip branch info
        usage_key = usage_key.for_branch(None)
        try:
            deleted_block = compat.load_enough_xblock(usage_key)
        except Exception as e:  # pylint: disable=broad-exception-caught
            log.warning(f"Cannot find xblock for key {usage_key}. Reason: {str(e)}. ")
            return
        block_locations = {str(deleted_block.location)}
        for block in compat.yield_dynamic_block_descendants(deleted_block, kwargs.get('user_id')):
            block_locations.add(str(block.location))

        LtiConfiguration.objects.filter(
            location__in=block_locations
        ).delete()
        log.info(f"Deleted {len(block_locations)} LTI configurations for block and its children in modulestore")
        result = Lti1p3Passport.objects.filter(lticonfiguration__isnull=True).delete()
        log.info(f"Deleted {result} lti 1.3 passport objects in library")


@receiver(XBLOCK_DELETED)
def delete_lti_configuration(**kwargs):
    """
    Delete lti configuration from database for this block.
    """
    xblock_info = kwargs.get("xblock_info", None)
    if not xblock_info or not isinstance(xblock_info, XBlockData):
        log.error("Received null or incorrect data for event")
        return

    LtiConfiguration.objects.filter(
        location=str(xblock_info.usage_key)
    ).delete()
    result = Lti1p3Passport.objects.filter(lticonfiguration__isnull=True).delete()
    log.info(f"Deleted {result} lti 1.3 passport objects in library")


@receiver(LIBRARY_BLOCK_DELETED)
def delete_lib_lti_configuration(**kwargs):
    """
    Delete lti configuration from database for this library block.
    """
    library_block = kwargs.get("library_block", None)
    if not library_block or not isinstance(library_block, LibraryBlockData):
        log.error("Received null or incorrect data for event")
        return

    LtiConfiguration.objects.filter(
        location=str(library_block.usage_key)
    ).delete()
    result = Lti1p3Passport.objects.filter(lticonfiguration__isnull=True).delete()
    log.info(f"Deleted {result} lti 1.3 passport objects in library")


@receiver(XBLOCK_DUPLICATED)
def duplicate_xblock_lti_configuration(**kwargs):
    """
    Duplicate LTI configuration from the source to the target xblock.
    """
    xblock_data = kwargs.get("xblock_info", None)
    if not xblock_data or not isinstance(xblock_data, DuplicatedXBlockData):
        log.error("Received null or incorrect data for event")
        return

    source_usage_key = str(xblock_data.source_usage_key)
    target_usage_key = str(xblock_data.usage_key)

    src_lti_config = LtiConfiguration.objects.filter(location=source_usage_key).first()
    if not src_lti_config:
        log.warning("No LTI configuration found to duplicate. source=%s", source_usage_key)
        return

    if LtiConfiguration.objects.filter(location=target_usage_key).exists():
        log.info(
            "Target already has LTI configuration. Skipping duplicate. target=%s source=%s",
            target_usage_key,
            source_usage_key,
        )
        return

    # Convert the LTI configuration to a dictionary and set the new location and config_id
    # to copy lticonfiguration data to the new location and config_id
    payload = model_to_dict(
        src_lti_config,
        # Include all unique fields and generated ones.
        exclude=["id", "pk", "location", "config_id"],
    )
    payload["location"] = target_usage_key
    payload["config_id"] = uuid.uuid4()

    try:
        LtiConfiguration.objects.create(**payload)
    except Exception:  # pylint: disable=broad-exception-caught
        log.exception(
            "Failed duplicating LTI configuration. source=%s target=%s",
            source_usage_key,
            target_usage_key,
        )


LTI_1P3_PROCTORING_ASSESSMENT_STARTED = Signal()
