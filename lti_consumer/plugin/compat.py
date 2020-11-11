"""
Compatibility layer to isolate core-platform method calls from implementation.
"""
from django.core.exceptions import ValidationError
from lti_consumer.exceptions import LtiError


def run_xblock_handler(*args, **kwargs):
    """
    Import and run `handle_xblock_callback` from LMS
    """
    # pylint: disable=import-error,import-outside-toplevel
    from lms.djangoapps.courseware.module_render import handle_xblock_callback
    return handle_xblock_callback(*args, **kwargs)


def run_xblock_handler_noauth(*args, **kwargs):
    """
    Import and run `handle_xblock_callback_noauth` from LMS
    """
    # pylint: disable=import-error,import-outside-toplevel
    from lms.djangoapps.courseware.module_render import handle_xblock_callback_noauth
    return handle_xblock_callback_noauth(*args, **kwargs)


def load_block_as_anonymous_user(location):
    """
    Load a block as anonymous user.

    This uses a few internal courseware methods to retrieve the descriptor
    and bind an AnonymousUser to it, in a similar fashion as a `noauth` XBlock
    handler.
    """
    # pylint: disable=import-error,import-outside-toplevel
    from django.contrib.auth.models import AnonymousUser
    from xmodule.modulestore.django import modulestore
    from lms.djangoapps.courseware.module_render import get_module_for_descriptor_internal

    # Retrieve descriptor from modulestore
    descriptor = modulestore().get_item(location)

    # Load block, attaching it to AnonymousUser
    get_module_for_descriptor_internal(
        user=AnonymousUser(),
        descriptor=descriptor,
        student_data=None,
        course_id=location.course_key,
        track_function=None,
        xqueue_callback_url_prefix="",
        request_token="",
    )

    return descriptor


def get_user_from_external_user_id(external_user_id):
    """
    Import ExternalId model and find user by external_user_id
    """
    # pylint: disable=import-error,import-outside-toplevel
    from openedx.core.djangoapps.external_user_ids.models import ExternalId
    try:
        external_id = ExternalId.objects.get(
            external_user_id=external_user_id,
            external_id_type__name='lti'
        )
        return external_id.user
    except ExternalId.DoesNotExist as exception:
        raise LtiError('Invalid User') from exception
    except ValidationError as exception:
        raise LtiError('Invalid userID') from exception


def load_block(key):
    # pylint: disable=import-outside-toplevel,import-error
    from xmodule.modulestore.django import modulestore
    return modulestore().get_item(key)


def publish_grade(block, user, score, possible, only_if_higher=False, score_deleted=None, comment=None):
    """
    Import grades signals and publishes score by triggering SCORE_PUBLISHED signal.
    """
    # pylint: disable=import-error,import-outside-toplevel
    from lms.djangoapps.grades.api import signals as grades_signals

    # publish score
    grades_signals.SCORE_PUBLISHED.send(
        sender=None,
        block=block,
        user=user,
        raw_earned=score,
        raw_possible=possible,
        only_if_higher=only_if_higher,
        score_deleted=score_deleted,
        grader_response=comment
    )
