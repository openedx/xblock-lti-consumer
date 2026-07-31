"""
This module encapsulates code which implements the LTI specification.

For more details see:
https://www.imsglobal.org/activity/learning-tools-interoperability
"""

import json
import logging
import urllib.parse

from django.conf import settings

from .exceptions import Lti1p1Error
from .oauth import get_oauth_request_signature, verify_oauth_body_signature

log = logging.getLogger(__name__)

LTI_PARAMETERS = [
    'lti_message_type',
    'lti_version',
    'resource_link_title',
    'resource_link_description',
    'user_image',
    'lis_person_name_given',
    'lis_person_name_family',
    'lis_person_name_full',
    'lis_person_contact_email_primary',
    'lis_person_sourcedid',
    'role_scope_mentor',
    'context_type',
    'context_title',
    'context_label',
    'launch_presentation_locale',
    'launch_presentation_document_target',
    'launch_presentation_css_url',
    'launch_presentation_width',
    'launch_presentation_height',
    'launch_presentation_return_url',
    'tool_consumer_info_product_family_code',
    'tool_consumer_info_version',
    'tool_consumer_instance_guid',
    'tool_consumer_instance_name',
    'tool_consumer_instance_description',
    'tool_consumer_instance_url',
    'tool_consumer_instance_contact_email',
]


def parse_result_json(json_str):
    """
    Helper method for verifying LTI 2.0 JSON object contained in the body of the request.

    The json_str must be loadable.  It can either be an dict (object) or an array whose first element is an dict,
    in which case that first dict is considered.
    The dict must have the "@type" key with value equal to "Result",
    "resultScore" key with value equal to a number [0, 1], if "resultScore" is not
    included in the JSON body, score will be returned as None
    The "@context" key must be present, but we don't do anything with it.  And the "comment" key may be
    present, in which case it must be a string.

    Arguments:
        json_str (unicode):  The body of the LTI 2.0 results service request, which is a JSON string

    Returns:
        (float, str):  (score, [optional]comment) if parsing is successful

    Raises:
        Lti1p1Error: if verification fails
    """
    try:
        json_obj = json.loads(json_str)
    except (ValueError, TypeError) as err:
        msg = f"Supplied JSON string in request body could not be decoded: {json_str!r}"
        log.error("[LTI] %s", msg)
        raise Lti1p1Error(msg) from err

    # The JSON object must be a dict. If a non-empty list is passed in,
    # use the first element, but only if it is a dict
    if isinstance(json_obj, list) and len(json_obj) >= 1:
        json_obj = json_obj[0]

    if not isinstance(json_obj, dict):
        msg = ("Supplied JSON string is a list that does not contain an object as the first element. {}"
               .format(json_str))
        log.error("[LTI] %s", msg)
        raise Lti1p1Error(msg)

    # '@type' must be "Result"
    result_type = json_obj.get("@type")
    if result_type != "Result":
        msg = f"JSON object does not contain correct @type attribute (should be 'Result', is {result_type!r})"
        log.error("[LTI] %s", msg)
        raise Lti1p1Error(msg)

    # '@context' must be present as a key
    if '@context' not in json_obj:
        msg = "JSON object does not contain required key @context"
        log.error("[LTI] %s", msg)
        raise Lti1p1Error(msg)

    # Return None if the resultScore key is missing, this condition
    # will be handled by the upstream caller of this function
    if "resultScore" not in json_obj:
        score = None
    else:
        # if present, 'resultScore' must be a number between 0 and 1 inclusive
        try:
            score = float(json_obj.get('resultScore', "unconvertable"))  # Check if float is present and the right type
            if not 0.0 <= score <= 1.0:
                msg = 'score value outside the permitted range of 0.0-1.0.'
                log.error("[LTI] %s", msg)
                raise Lti1p1Error(msg)
        except (TypeError, ValueError) as err:
            msg = "Could not convert resultScore to float: {}".format(str(err))
            log.error("[LTI] %s", msg)
            raise Lti1p1Error(msg) from err

    return score, json_obj.get('comment', "")


class LtiConsumer1p1:
    """
    Limited implementation of the LTI 1.1.

    For the LTI 1.1 specification see:
    https://www.imsglobal.org/specs/ltiv1p1
    """
    CONTENT_TYPE_RESULT_JSON = 'application/vnd.ims.lis.v2.result+json'

    def __init__(self, lti_launch_url, oauth_key, oauth_secret):
        """
        Initialize LTI 1.1 Consumer class

        Arguments:
            lti_launch_url (string):  URL to which the LTI Launch should be sent
            oauth_key (string):  OAuth consumer key
            oauth_secret (string):  OAuth consumer secret
        """
        self.lti_launch_url = lti_launch_url
        self.oauth_key = oauth_key
        self.oauth_secret = oauth_secret

        # IMS LTI data
        self.lti_user_data = None
        self.lti_context_data = None
        self.lti_outcome_service_url = None
        self.lti_launch_presentation_locale = None
        self.lti_custom_parameters = None

        # Extra claims - used for custom parameter processors
        self.extra_claims = {}

    def set_user_data(
            self,
            user_id,
            roles,
            result_sourcedid,
            person_sourcedid=None,
            person_contact_email_primary=None,
            person_name_full=None,
    ):
        """
        Set user data/roles

        Arguments:
            user_id (string):  Unique value identifying the user
            roles (string):  A comma separated list of role values
            result_sourcedid (string):  Indicates the LIS Result Identifier (if any)
                and uniquely identifies a row and column within the Tool Consumer gradebook
            person_sourcedid (string):  LIS identifier for the user account performing the launch
            person_contact_email_primary (string):  Primary contact email address of the user
            person_name_full (string): Full name of the user
        """
        self.lti_user_data = {
            'user_id': user_id,
            'roles': roles,
            'lis_result_sourcedid': result_sourcedid,
        }

        # Additional user identity data
        # Optional user data that can be sent to the tool, if the block is configured to do so
        if person_sourcedid:
            self.lti_user_data.update({
                'lis_person_sourcedid': person_sourcedid,
            })

        if person_contact_email_primary:
            self.lti_user_data.update({
                'lis_person_contact_email_primary': person_contact_email_primary,
            })

        if person_name_full:
            self.lti_user_data.update({
                'lis_person_name_full': person_name_full,
            })

    def set_context_data(self, context_id, context_title, context_label):
        """
        Set LTI context data

        Arguments:
            context_id (string):  Opaque identifier used to uniquely identify the
                context that contains the link being launched
            context_title (string):  Plain text title of the context
            context_label (string):  Plain text label for the context
        """
        self.lti_context_data = {
            'context_id': context_id,
            'context_title': context_title,
            'context_label': context_label,
        }

    def set_outcome_service_url(self, outcome_service_url):
        """
        Set outcome_service_url for scoring

        Arguments:
            outcome_service_url (string):  URL pointing to the outcome service. This
                is required if the Tool Consumer is accepting outcomes for launches
                associated with the resource_link_id
        """
        self.lti_outcome_service_url = {
            'lis_outcome_service_url': outcome_service_url,
        }

    def set_launch_presentation_locale(self, launch_presentation_locale):
        """
        Set launch presentation locale

        Arguments:
            launch_presentation_locale (string):  Language, country and variant as
                represented using the IETF Best Practices for Tags for Identifying
                Languages (BCP-47)
        """
        self.lti_launch_presentation_locale = {
            'launch_presentation_locale': launch_presentation_locale
        }

    def set_custom_parameters(self, custom_parameters):
        """
        Sets custom parameters configured for LTI launch

        Arguments:
            custom_parameters (dict):  Dictionary of custom key/value parameters
                to be included in the LTI Launch

        Raises:
            ValueError if custom_parameters is not a dict
        """
        if not isinstance(custom_parameters, dict):
            raise ValueError("Custom parameters must be a key/value dictionary.")

        self.lti_custom_parameters = custom_parameters

    def set_extra_claims(self, claim):
        """
        Updates launch extra claims using python's dict .update method
        """
        if not isinstance(claim, dict):
            raise ValueError('Invalid extra claim: {!r} is not a dict.'.format(claim))
        self.extra_claims.update(claim)

    def generate_launch_request(self, resource_link_id):
        """
        Signs LTI launch request and returns signature and OAuth parameters.

        Arguments:
            resource_link_id (string):  Opaque identifier guaranteed to be unique
                for every placement of the link

        Returns:
            dict: LTI launch parameters
        """

        # Must have parameters for correct signing from LTI:
        lti_parameters = {
            'oauth_callback': 'about:blank',
            'launch_presentation_return_url': '',
            'lti_message_type': 'basic-lti-launch-request',
            'lti_version': 'LTI-1p0',

            # Parameters required for grading:
            'resource_link_id': resource_link_id,

            'tool_consumer_info_product_family_code': str(settings.PLATFORM_NAME),
        }

        # Check if user data is set, then append it to lti message
        # Raise if isn't set, since some user data is required for the launch
        if self.lti_user_data:
            lti_parameters.update(self.lti_user_data)
        else:
            raise ValueError("Required user data isn't set.")

        # Check if context data is set, then append it to lti message
        # Raise if isn't set, since all context data is required for the launch
        if self.lti_context_data:
            lti_parameters.update(self.lti_context_data)
        else:
            raise ValueError("Required context data isn't set.")

        if self.lti_outcome_service_url:
            lti_parameters.update(self.lti_outcome_service_url)

        if self.lti_launch_presentation_locale:
            lti_parameters.update(self.lti_launch_presentation_locale)

        # Appending custom parameter for signing.
        if self.lti_custom_parameters:
            lti_parameters.update(self.lti_custom_parameters)

        # Extra claims - from custom parameter processors
        if self.extra_claims:
            lti_parameters.update(self.extra_claims)

        headers = {
            # This is needed for body encoding:
            'Content-Type': 'application/x-www-form-urlencoded',
        }

        oauth_signature = get_oauth_request_signature(
            self.oauth_key,
            self.oauth_secret,
            self.lti_launch_url,
            headers,
            lti_parameters
        )

        # Parse headers to pass to template as part of context:
        oauth_signature = dict([param.strip().replace('"', '').split('=') for param in oauth_signature.split(',')])

        oauth_signature['oauth_nonce'] = oauth_signature.pop('OAuth oauth_nonce')

        # oauthlib encodes signature with
        # 'Content-Type': 'application/x-www-form-urlencoded'
        # so '='' becomes '%3D'.
        # We send form via browser, so browser will encode it again,
        # So we need to decode signature back:
        oauth_signature['oauth_signature'] = urllib.parse.unquote(
            oauth_signature['oauth_signature']
        )

        # Add LTI parameters to OAuth parameters for sending in form.
        lti_parameters.update(oauth_signature)
        return lti_parameters

    def get_result(self, result_score=None, score_comment=None):
        """
        Returns response body for GET requests to LTI 2.0 result endpoint

        Arguments:
            result_score (float):  The result score of the user
            score_comment (string):  A text comment describing the score

        Returns:
            dict:  response to this request, in JSON format with resultScore and comment if provided
        """
        response = {
            "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
            "@type": "Result"
        }
        if result_score is not None:
            response['resultScore'] = round(result_score, 2)
            response['comment'] = score_comment

        return response

    def delete_result(self):
        """
        Returns response body for DELETE requests to LTI 2.0 result endpoint
        """
        return {}

    def put_result(self):
        """
        Returns response body for PUT requests to LTI 2.0 result endpoint
        """
        return {}

    def verify_result_headers(self, request, verify_content_type=True):
        """
        Helper method to validate LTI 2.0 REST result service HTTP headers.  returns if correct, else raises Lti1p1Error

        Arguments:
            request (webob.Request):  Request object
            verify_content_type (bool):  If true, verifies the content type of the request is that spec'ed by LTI 2.0

        Returns:
            nothing, but will only return if verification succeeds

        Raises:
            Lti1p1Error if verification fails
        """
        content_type = request.headers.get('Content-Type')
        if verify_content_type and content_type != LtiConsumer1p1.CONTENT_TYPE_RESULT_JSON:
            log.error("[LTI]: v2.0 result service -- bad Content-Type: %s", content_type)
            error_msg = "For LTI 2.0 result service, Content-Type must be {}.  Got {}".format(
                LtiConsumer1p1.CONTENT_TYPE_RESULT_JSON,
                content_type
            )
            raise Lti1p1Error(error_msg)

        # Check if scoring data is set, then append it to lti message
        # Raise if isn't set, since some scoring data is required for the launch
        if self.lti_outcome_service_url:
            outcome_service_url = self.lti_outcome_service_url['lis_outcome_service_url']
        else:
            log.error("[LTI]: v2.0 result service -- lis_outcome_service_url not set")
            raise ValueError("Required outcome_service_url not set.")

        try:
            return verify_oauth_body_signature(request, self.oauth_secret, outcome_service_url)
        except (ValueError, Lti1p1Error) as err:
            log.error("[LTI]: v2.0 result service -- OAuth body verification failed: %s", str(err))
            raise Lti1p1Error(str(err)) from err
