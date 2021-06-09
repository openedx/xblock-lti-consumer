"""
Utility functions for LTI Consumer block
"""
from django.conf import settings
from lti_consumer.plugin.compat import get_lti_pii_course_waffle_flag


def _(text):
    """
    Make '_' a no-op so we can scrape strings
    """
    return text


def expose_pii_fields(course_key):
    """
    Returns `true` if Use's PII fields can be exposed to LTI endpoints
    for given course key. ex - LTI-NRPS Context Membership Endpoint.

    Args:
        course_key
    """
    return get_lti_pii_course_waffle_flag().is_enabled(course_key)


def get_lms_base():
    """
    Returns LMS base url to be used as issuer on OAuth2 flows

    TODO: This needs to be improved and account for Open edX sites and
    organizations.
    One possible improvement is to use `contentstore.get_lms_link_for_item`
    and strip the base domain name.
    """
    return settings.LMS_ROOT_URL


def get_lms_lti_keyset_link(location):
    """
    Returns an LMS link to LTI public keyset endpoint

    :param location: the location of the block
    """
    return "{lms_base}/api/lti_consumer/v1/public_keysets/{location}".format(
        lms_base=get_lms_base(),
        location=str(location),
    )


def get_lms_lti_launch_link():
    """
    Returns an LMS link to LTI Launch endpoint

    :param location: the location of the block
    """
    return "{lms_base}/api/lti_consumer/v1/launch/".format(
        lms_base=get_lms_base(),
    )


def get_lms_lti_access_token_link(location):
    """
    Returns an LMS link to LTI Launch endpoint

    :param location: the location of the block
    """
    return "{lms_base}/api/lti_consumer/v1/token/{location}".format(
        lms_base=get_lms_base(),
        location=str(location),
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
