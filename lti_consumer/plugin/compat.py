"""
Compatibility layer to isolate core-platform method calls from implementation.
"""
import logging
from typing import Callable

from django.core.exceptions import ValidationError
from django.forms import ModelForm
from opaque_keys.edx.keys import CourseKey

from lti_consumer.exceptions import LtiError


log = logging.getLogger(__name__)


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
    from crum import impersonate
    from django.contrib.auth.models import AnonymousUser
    from xmodule.modulestore.django import modulestore
    from lms.djangoapps.courseware.module_render import get_module_for_descriptor_internal

    # Retrieve descriptor from modulestore
    descriptor = modulestore().get_item(location)

    # ensure `crum.get_current_user` returns AnonymousUser. It returns None when outside
    # of request scope which causes error during block loading.
    user = AnonymousUser()
    with impersonate(user):
        # Load block, attaching it to AnonymousUser
        get_module_for_descriptor_internal(
            user=user,
            descriptor=descriptor,
            student_data=None,
            course_id=location.course_key,
            track_function=None,
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
        grader_response=comment,
    )


def user_has_access(*args, **kwargs):
    """
    Import and run `has_access` from LMS
    """
    # pylint: disable=import-error,import-outside-toplevel
    from lms.djangoapps.courseware.access import has_access
    return has_access(*args, **kwargs)


def get_course_by_id(course_key):
    """
    Import and run `get_course_by_id` from LMS

    TODO: Once the LMS has fully switched over to this new path [1],
    we can remove the legacy (LMS) import support here.

    - [1] https://github.com/edx/edx-platform/pull/27289
    """
    # pylint: disable=import-outside-toplevel
    try:
        from openedx.core.lib.courses import get_course_by_id as lms_get_course_by_id
    except ImportError:
        from lms.djangoapps.courseware.courses import get_course_by_id as lms_get_course_by_id
    return lms_get_course_by_id(course_key)


def user_course_access(*args, **kwargs):
    """
    Import and run `check_course_access` from LMS
    """
    # pylint: disable=import-error,import-outside-toplevel
    from lms.djangoapps.courseware.courses import check_course_access
    return check_course_access(*args, **kwargs)


def batch_get_or_create_externalids(users):
    """
    Given a list of user, returns corresponding external id's

    External ID's are created when a student actually launches
    LTI from LMS. But when providing course member information
    to a third party tool, not every member has External ID's
    available. To create one by one would be a performance issue.
    This method provides a faster way to create ExternalIds in batch.
    """
    # pylint: disable=import-error,import-outside-toplevel
    from openedx.core.djangoapps.external_user_ids.models import ExternalId
    return ExternalId.batch_get_or_create_user_ids(users, 'lti')


def get_course_members(course_key):
    """
    Returns a dict containing all users associated with the given course
    """
    # pylint: disable=import-error,import-outside-toplevel
    from lms.djangoapps.course_api.api import get_course_members as core_get_course_members
    from lms.djangoapps.course_api.exceptions import OverEnrollmentLimitException

    try:
        return core_get_course_members(course_key)
    except OverEnrollmentLimitException as ex:
        raise LtiError('NRPS is not available for {}'.format(course_key)) from ex


def request_cached(func) -> Callable[[Callable], Callable]:
    """
    Import the `request_cached` decorator from LMS and apply it if available.
    """
    try:
        # pylint: disable=import-outside-toplevel
        from openedx.core.lib.cache_utils import request_cached as lms_request_cached
        return lms_request_cached(func)
    except ImportError:
        log.warning("Unable to import `request_cached`. This is normal if running tests.")
        return func


def clean_course_id(model_form: ModelForm) -> CourseKey:
    """
    Import and run `clean_course_id` from LMS
    """
    # pylint: disable=import-error,import-outside-toplevel
    from openedx.core.lib.courses import clean_course_id as lms_clean_course_id
    return lms_clean_course_id(model_form)
