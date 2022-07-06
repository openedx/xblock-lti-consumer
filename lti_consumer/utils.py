"""
Utility functions for LTI Consumer block
"""
import logging
from importlib import import_module
from uuid import UUID

from django.conf import settings

from lti_consumer.plugin.compat import get_external_config_waffle_flag, get_database_config_waffle_flag

log = logging.getLogger(__name__)


def _(text):
    """
    Make '_' a no-op so we can scrape strings
    """
    return text


def get_lms_base():
    """
    Returns LMS base url to be used as issuer on OAuth2 flows

    TODO: This needs to be improved and account for Open edX sites and
    organizations.
    One possible improvement is to use `contentstore.get_lms_link_for_item`
    and strip the base domain name.
    """
    return settings.LMS_ROOT_URL


def get_lms_lti_keyset_link(config_id: UUID):
    """
    Returns an LMS link to LTI public keyset endpoint

    :param config_id: the config_id of the LtiConfiguration object
    """
    return "{lms_base}/api/lti_consumer/v1/public_keysets/{location}".format(
        lms_base=get_lms_base(),
        location=str(config_id),
    )


def get_lms_lti_launch_link():
    """
    Returns an LMS link to LTI Launch endpoint

    :param location: the location of the block
    """
    return "{lms_base}/api/lti_consumer/v1/launch/".format(
        lms_base=get_lms_base(),
    )


def get_lms_lti_access_token_link(config_id: UUID):
    """
    Returns an LMS link to LTI Launch endpoint

    :param config_id: the config_id of the LtiConfiguration object
    """
    return "{lms_base}/api/lti_consumer/v1/token/{location}".format(
        lms_base=get_lms_base(),
        location=str(config_id),
    )


def get_lti_ags_lineitems_url(lti_config_id, lineitem_id=None):
    """
    Return the LTI AGS endpoint

    :param lti_config_id: LTI configuration id
    :param lineitem_id: LTI Line Item id. Single line item if given an id,
        otherwise returns list url
    """

    url = "{lms_base}/api/lti_consumer/v1/lti/{lti_config_id}/lti-ags".format(
        lms_base=get_lms_base(),
        lti_config_id=str(lti_config_id),
    )

    if lineitem_id:
        url += "/" + str(lineitem_id)

    return url


def get_lti_deeplinking_response_url(lti_config_id):
    """
    Return the LTI Deep Linking response endpoint

    :param lti_config_id: LTI configuration id
    """
    return "{lms_base}/api/lti_consumer/v1/lti/{lti_config_id}/lti-dl/response".format(
        lms_base=get_lms_base(),
        lti_config_id=str(lti_config_id),
    )


def get_lti_deeplinking_content_url(lti_config_id):
    """
    Return the LTI Deep Linking content presentation endpoint

    :param lti_config_id: LTI configuration id
    """
    return "{lms_base}/api/lti_consumer/v1/lti/{lti_config_id}/lti-dl/content".format(
        lms_base=get_lms_base(),
        lti_config_id=str(lti_config_id),
    )


def get_lti_nrps_context_membership_url(lti_config_id):
    """
    Returns The LTI NRPS Context Membership service URL.

    :param lti_config_id: LTI Configuration ID
    """

    return "{lms_base}/api/lti_consumer/v1/lti/{lti_config_id}/memberships".format(
        lms_base=get_lms_base(),
        lti_config_id=str(lti_config_id),
    )


def resolve_custom_parameter_template(xblock, template):
    """
    Return the value processed according to the template processor.
    The template processor must return a string object.

    :param xblock: LTI consumer xblock.
    :param template: processor key.
    """
    try:
        module_name, func_name = settings.LTI_CUSTOM_PARAM_TEMPLATES.get(
            template[2:len(template) - 1],
            ':',
        ).split(':', 1)
        template_value = getattr(
            import_module(module_name),
            func_name,
        )(xblock)

        if not isinstance(template_value, str):
            log.error('The \'%s\' processor must return a string object.', func_name)
            return template
    except ValueError:
        log.error(
            'Error while processing \'%s\' value. Reason: The template processor definition must be wrong.',
            template,
        )
        return template
    except (AttributeError, ModuleNotFoundError) as ex:
        log.error('Error while processing \'%s\' value. Reason: %s', template, str(ex))
        return template

    return template_value


def external_config_filter_enabled(course_key):
    """
    Returns True if external config filter is enabled for the course via Waffle Flag.

    Arguments:
        course_key (opaque_keys.edx.locator.CourseLocator): Course Key
    """
    return get_external_config_waffle_flag().is_enabled(course_key)


def database_config_enabled(course_key):
    """
    Return whether the lti_consumer.enable_database_config WaffleFlag is enabled. Return True if it is enabled;
    return False if it is not enabled.
    """
    return get_database_config_waffle_flag().is_enabled(course_key)
