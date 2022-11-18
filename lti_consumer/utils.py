"""
Utility functions for LTI Consumer block
"""
import logging
from importlib import import_module
from urllib.parse import urlencode

from django.conf import settings
from edx_django_utils.cache import get_cache_key, TieredCache

from lti_consumer.plugin.compat import (
    get_external_config_waffle_flag,
    get_external_user_id_1p1_launches_waffle_flag,
    get_database_config_waffle_flag,
)
from lti_consumer.lti_1p3.constants import LTI_1P3_CONTEXT_TYPE
from lti_consumer.lti_1p3.exceptions import InvalidClaimValue, MissingRequiredClaim

log = logging.getLogger(__name__)


def _(text):
    """
    Make '_' a no-op so we can scrape strings
    """
    return text


def get_lms_base():
    """
    Returns LMS base url to be used as issuer on OAuth2 flows
    and in various LTI URLs. For local testing it is often necessary
    to override the normal LMS base with a proxy such as ngrok, use
    the setting LTI_LMS_BASE_URL_OVERRIDE in your LMS settings if
    necessary.

    TODO: This needs to be improved and account for Open edX sites and
    organizations.
    One possible improvement is to use `contentstore.get_lms_link_for_item`
    and strip the base domain name.
    """
    if hasattr(settings, 'LTI_LMS_BASE_URL_OVERRIDE'):
        return settings.LTI_LMS_BASE_URL_OVERRIDE
    else:
        return settings.LMS_ROOT_URL


def get_lms_lti_keyset_link(config_id):
    """
    Returns an LMS link to LTI public keyset endpoint

    :param config_id: the config_id of the LtiConfiguration object
    """
    return "{lms_base}/api/lti_consumer/v1/public_keysets/{config_id}".format(
        lms_base=get_lms_base(),
        config_id=str(config_id),
    )


def get_lms_lti_launch_link():
    """
    Returns an LMS link to LTI Launch endpoint

    :param location: the location of the block
    """
    return "{lms_base}/api/lti_consumer/v1/launch/".format(
        lms_base=get_lms_base(),
    )


def get_lms_lti_access_token_link(config_id):
    """
    Returns an LMS link to LTI Launch endpoint

    :param config_id: the config_id of the LtiConfiguration object
    """
    return "{lms_base}/api/lti_consumer/v1/token/{config_id}".format(
        lms_base=get_lms_base(),
        config_id=str(config_id),
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


def get_lti_deeplinking_content_url(lti_config_id, launch_data):
    """
    Return the LTI Deep Linking content presentation endpoint

    :param lti_config_id: LTI configuration id
    :param launch_data: (lti_consumer.data.Lti1p3LaunchData): a class containing data necessary for an LTI 1.3 launch
    """
    url = "{lms_base}/api/lti_consumer/v1/lti/{lti_config_id}/lti-dl/content".format(
        lms_base=get_lms_base(),
        lti_config_id=str(lti_config_id),
    )
    url += "?"

    launch_data_key = cache_lti_1p3_launch_data(launch_data)

    url += urlencode({
        "launch_data_key": launch_data_key,
    })

    return url


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


def external_user_id_1p1_launches_enabled(course_key):
    """
    Returns whether the lti_consumer.enable_external_user_id_1p1_launches CourseWaffleFlag is enabled.
    Returns True if sending external user IDs in LTI 1.1 launches is enabled for the course via the CourseWaffleFlag.

    Arguments:
        course_key (opaque_keys.edx.locator.CourseLocator): Course Key
    """
    return get_external_user_id_1p1_launches_waffle_flag().is_enabled(course_key)


def database_config_enabled(course_key):
    """
    Return whether the lti_consumer.enable_database_config WaffleFlag is enabled. Return True if it is enabled;
    return False if it is not enabled.
    """
    return get_database_config_waffle_flag().is_enabled(course_key)


def get_lti_1p3_context_types_claim(context_types):
    """
    Return the LTI 1.3 context_type claim based on the context_type slug provided as an argument.

    Arguments:
        context_type (list): a list of context_types
    """
    lti_context_types = []

    for context_type in context_types:
        if context_type == "group":
            lti_context_types.append(LTI_1P3_CONTEXT_TYPE.group)
        elif context_type == "course_offering":
            lti_context_types.append(LTI_1P3_CONTEXT_TYPE.course_offering)
        elif context_type == "course_section":
            lti_context_types.append(LTI_1P3_CONTEXT_TYPE.course_section)
        elif context_type == "course_template":
            lti_context_types.append(LTI_1P3_CONTEXT_TYPE.course_template)
        else:
            raise ValueError("context_type is not a valid type.")

    return lti_context_types


def get_lti_1p3_launch_data_cache_key(launch_data):
    """
    Return the cache key for the instance of Lti1p3LaunchData.

    Arugments:
        launch_data (lti_consumer.data.Lti1p3LaunchData): a class containing data necessary for an LTI 1.3 launch
    """
    kwargs = {
        "app": "lti",
        "key": "launch_data",
        "user_id": launch_data.user_id,
        "resource_link_id": launch_data.resource_link_id
    }

    # If the LTI 1.3 launch is a deep linking launch to a particular content item, then the launch data should be cached
    # per content item to properly do an LTI 1.3 deep linking launch. Otherwise, deep linking launches to different
    # items will not work via the deep_linking_content_endpoint view, because launch data is cached at the time that the
    # preflight URL is generated.
    content_item_id = launch_data.deep_linking_content_item_id
    if content_item_id:
        kwargs["deep_linking_content_item_id"] = content_item_id

    return get_cache_key(**kwargs)


def cache_lti_1p3_launch_data(launch_data):
    """
    Insert the launch_data into the cache and return the cache key.

    Arguments:
        launch_data (lti_consumer.data.Lti1p3LaunchData): a class containing data necessary for an LTI 1.3 launch
    """
    launch_data_key = get_lti_1p3_launch_data_cache_key(launch_data)

    # Insert the data into the cache with a 600 second timeout.
    TieredCache.set_all_tiers(launch_data_key, launch_data, django_cache_timeout=600)

    return launch_data_key


def get_data_from_cache(cache_key):
    """
    Return data stored in the cache with the cache key, if it exists. If not, return none.

    Arguments:
    cache_key: the key for the data in the cache
    """
    cached_data = TieredCache.get_cached_response(cache_key)

    if cached_data.is_found:
        return cached_data.value

    return None


def check_token_claim(token, claim_key, expected_value=None, invalid_claim_error_msg=None):
    """
    Checks that the claim with key claim_key appears in the token. Raises a MissingRequiredClaim exception if it does
    not. If the optional arguments expected_value and invalid_claim_error_msg are provided, then checks that the claim
    in the token with the key claim_key matches the expected_value. Raises an InvalidClaimValue exception with the
    invalid_claim_error_msg as the message if not. If the invalid_claim_error_msg argument is provided, then a generic
    message is used.
    """
    claim_value = token.get(claim_key)

    if claim_value is None:
        raise MissingRequiredClaim(f"Token is missing required {claim_key} claim.")
    if expected_value and claim_value != expected_value:
        msg = invalid_claim_error_msg if invalid_claim_error_msg else f"The claim {claim_key} value is invalid."
        raise InvalidClaimValue(msg)
