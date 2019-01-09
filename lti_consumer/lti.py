"""
This module encapsulates code which implements the LTI specification.

For more details see:
https://www.imsglobal.org/activity/learning-tools-interoperability
"""

import logging
import urllib
import json

from six import text_type

from .exceptions import LtiError
from .oauth import get_oauth_request_signature, verify_oauth_body_signature


log = logging.getLogger(__name__)


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
        LtiError: if verification fails
    """
    try:
        json_obj = json.loads(json_str)
    except (ValueError, TypeError):
        msg = "Supplied JSON string in request body could not be decoded: {}".format(json_str)
        log.error("[LTI] %s", msg)
        raise LtiError(msg)

    # The JSON object must be a dict. If a non-empty list is passed in,
    # use the first element, but only if it is a dict
    if isinstance(json_obj, list) and len(json_obj) >= 1:
        json_obj = json_obj[0]

    if not isinstance(json_obj, dict):
        msg = ("Supplied JSON string is a list that does not contain an object as the first element. {}"
               .format(json_str))
        log.error("[LTI] %s", msg)
        raise LtiError(msg)

    # '@type' must be "Result"
    result_type = json_obj.get("@type")
    if result_type != "Result":
        msg = "JSON object does not contain correct @type attribute (should be 'Result', is z{})".format(result_type)
        log.error("[LTI] %s", msg)
        raise LtiError(msg)

    # '@context' must be present as a key
    if '@context' not in json_obj:
        msg = "JSON object does not contain required key @context"
        log.error("[LTI] %s", msg)
        raise LtiError(msg)

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
                raise LtiError(msg)
        except (TypeError, ValueError) as err:
            msg = "Could not convert resultScore to float: {}".format(err.message)
            log.error("[LTI] %s", msg)
            raise LtiError(msg)

    return score, json_obj.get('comment', "")


class LtiConsumer(object):
    """
    Limited implementation of the LTI 1.1/2.0 specification.

    For the LTI 1.1 specification see:
    https://www.imsglobal.org/specs/ltiv1p1

    For the LTI 2.0 specification see:
    https://www.imsglobal.org/specs/ltiv2p0
    """
    CONTENT_TYPE_RESULT_JSON = 'application/vnd.ims.lis.v2.result+json'

    def __init__(self, xblock):
        self.xblock = xblock

    def get_signed_lti_parameters(self):
        """
        Signs LTI launch request and returns signature and OAuth parameters.

        Arguments:
            None

        Returns:
            dict: LTI launch parameters
        """

        # Must have parameters for correct signing from LTI:
        lti_parameters = {
            text_type('user_id'): self.xblock.user_id,
            text_type('oauth_callback'): text_type('about:blank'),
            text_type('launch_presentation_return_url'): '',
            text_type('lti_message_type'): text_type('basic-lti-launch-request'),
            text_type('lti_version'): text_type('LTI-1p0'),
            text_type('roles'): self.xblock.role,

            # Parameters required for grading:
            text_type('resource_link_id'): self.xblock.resource_link_id,
            text_type('lis_result_sourcedid'): self.xblock.lis_result_sourcedid,

            text_type('context_id'): self.xblock.context_id,
            text_type('custom_component_display_name'): self.xblock.display_name,

            text_type('context_title'): self.xblock.course.display_name_with_default,
            text_type('context_label'): self.xblock.course.display_org_with_default,
        }

        if self.xblock.due:
            lti_parameters['custom_component_due_date'] = self.xblock.due.strftime('%Y-%m-%d %H:%M:%S')
            if self.xblock.graceperiod:
                lti_parameters['custom_component_graceperiod'] = str(self.xblock.graceperiod.total_seconds())

        if self.xblock.has_score:
            lti_parameters.update({
                text_type('lis_outcome_service_url'): self.xblock.outcome_service_url
            })

        self.xblock.user_email = ""
        self.xblock.user_username = ""
        self.xblock.user_language = ""

        # Username, email, and language can't be sent in studio mode, because the user object is not defined.
        # To test functionality test in LMS

        if callable(self.xblock.runtime.get_real_user):
            real_user_object = self.xblock.runtime.get_real_user(self.xblock.runtime.anonymous_student_id)
            self.xblock.user_email = getattr(real_user_object, "email", "")
            self.xblock.user_username = getattr(real_user_object, "username", "")
            user_preferences = getattr(real_user_object, "preferences", None)

            if user_preferences is not None:
                language_preference = user_preferences.filter(key='pref-lang')
                if len(language_preference) == 1:
                    self.xblock.user_language = language_preference[0].value

        if self.xblock.ask_to_send_username and self.xblock.user_username:
            lti_parameters["lis_person_sourcedid"] = self.xblock.user_username
        if self.xblock.ask_to_send_email and self.xblock.user_email:
            lti_parameters["lis_person_contact_email_primary"] = self.xblock.user_email
        if self.xblock.user_language:
            lti_parameters["launch_presentation_locale"] = self.xblock.user_language

        # Appending custom parameter for signing.
        lti_parameters.update(self.xblock.prefixed_custom_parameters)

        for processor in self.xblock.get_parameter_processors():
            try:
                default_params = getattr(processor, 'lti_xblock_default_params', {})
                lti_parameters.update(default_params)
                lti_parameters.update(processor(self.xblock) or {})
            except Exception:  # pylint: disable=broad-except
                # Log the error without causing a 500-error.
                # Useful for catching casual runtime errors in the processors.
                log.exception('Error in XBlock LTI parameter processor "%s"', processor)

        headers = {
            # This is needed for body encoding:
            'Content-Type': 'application/x-www-form-urlencoded',
        }

        key, secret = self.xblock.lti_provider_key_secret
        oauth_signature = get_oauth_request_signature(key, secret, self.xblock.launch_url, headers, lti_parameters)

        # Parse headers to pass to template as part of context:
        oauth_signature = dict([param.strip().replace('"', '').split('=') for param in oauth_signature.split(',')])

        oauth_signature[u'oauth_nonce'] = oauth_signature.pop(u'OAuth oauth_nonce')

        # oauthlib encodes signature with
        # 'Content-Type': 'application/x-www-form-urlencoded'
        # so '='' becomes '%3D'.
        # We send form via browser, so browser will encode it again,
        # So we need to decode signature back:
        oauth_signature[u'oauth_signature'] = urllib.unquote(oauth_signature[u'oauth_signature']).decode('utf8')

        # Add LTI parameters to OAuth parameters for sending in form.
        lti_parameters.update(oauth_signature)
        return lti_parameters

    def get_result(self, user):  # pylint: disable=unused-argument
        """
        Helper request handler for GET requests to LTI 2.0 result endpoint

        GET handler for lti_2_0_result.  Assumes all authorization has been checked.

        Arguments:
            request (xblock.django.request.DjangoWebobRequest):  Request object (unused)
            real_user (django.contrib.auth.models.User):  Actual user linked to anon_id in request path suffix

        Returns:
            webob.response:  response to this request, in JSON format with status 200 if success
        """
        self.xblock.runtime.rebind_noauth_module_to_user(self.xblock, user)

        response = {
            "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
            "@type": "Result"
        }
        if self.xblock.module_score is not None:
            response['resultScore'] = round(self.xblock.module_score, 2)
            response['comment'] = self.xblock.score_comment

        return response

    def delete_result(self, user):  # pylint: disable=unused-argument
        """
        Helper request handler for DELETE requests to LTI 2.0 result endpoint

        DELETE handler for lti_2_0_result.  Assumes all authorization has been checked.

        Arguments:
            request (xblock.django.request.DjangoWebobRequest):  Request object (unused)
            real_user (django.contrib.auth.models.User):  Actual user linked to anon_id in request path suffix

        Returns:
            webob.response:  response to this request.  status 200 if success
        """
        self.xblock.clear_user_module_score(user)
        return {}

    def put_result(self, user, result_json):
        """
        Helper request handler for PUT requests to LTI 2.0 result endpoint

        PUT handler for lti_2_0_result.  Assumes all authorization has been checked.

        Arguments:
            request (xblock.django.request.DjangoWebobRequest):  Request object
            real_user (django.contrib.auth.models.User):  Actual user linked to anon_id in request path suffix

        Returns:
            webob.response:  response to this request.  status 200 if success.  404 if body of PUT request is malformed
        """
        score, comment = parse_result_json(result_json)

        if score is None:
            # According to http://www.imsglobal.org/lti/ltiv2p0/ltiIMGv2p0.html#_Toc361225514
            # PUTting a JSON object with no "resultScore" field is equivalent to a DELETE.
            self.xblock.clear_user_module_score(user)
        else:
            self.xblock.set_user_module_score(user, score, self.xblock.max_score(), comment)

        return {}

    def verify_result_headers(self, request, verify_content_type=True):
        """
        Helper method to validate LTI 2.0 REST result service HTTP headers.  returns if correct, else raises LtiError

        Arguments:
            request (xblock.django.request.DjangoWebobRequest):  Request object
            verify_content_type (bool):  If true, verifies the content type of the request is that spec'ed by LTI 2.0

        Returns:
            nothing, but will only return if verification succeeds

        Raises:
            LtiError if verification fails
        """
        content_type = request.headers.get('Content-Type')
        if verify_content_type and content_type != LtiConsumer.CONTENT_TYPE_RESULT_JSON:
            log.error("[LTI]: v2.0 result service -- bad Content-Type: %s", content_type)
            raise LtiError(
                "For LTI 2.0 result service, Content-Type must be %s.  Got %s",
                LtiConsumer.CONTENT_TYPE_RESULT_JSON,
                content_type
            )

        __, secret = self.xblock.lti_provider_key_secret
        try:
            return verify_oauth_body_signature(request, secret, self.xblock.outcome_service_url)
        except (ValueError, LtiError) as err:
            log.error("[LTI]: v2.0 result service -- OAuth body verification failed: %s", err.message)
            raise LtiError(err.message)
