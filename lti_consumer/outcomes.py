"""
This module adds support for the LTI Outcomes Management Service.

For more details see:
https://www.imsglobal.org/specs/ltiomv1p0
"""

import logging
from xml.sax.saxutils import escape
from urllib.parse import unquote

from lxml import etree
from xblockutils.resources import ResourceLoader

from .exceptions import LtiError
from .lti_1p1.oauth import verify_oauth_body_signature

log = logging.getLogger(__name__)


def parse_grade_xml_body(body):
    """
    Parses values from the Outcome Service XML.

    XML body should contain nsmap with namespace, that is specified in LTI specs.

    Arguments:
        body (str): XML Outcome Service request body

    Returns:
        tuple: imsx_messageIdentifier, sourcedId, score, action

    Raises:
        LtiError
            if submitted score is outside the permitted range
            if the XML is missing required entities
            if there was a problem parsing the XML body
    """
    lti_spec_namespace = "http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0"
    namespaces = {'def': lti_spec_namespace}
    data = body.strip()
    if isinstance(body, str):
        data = body.strip().encode('utf-8')

    try:
        parser = etree.XMLParser(ns_clean=True, recover=True, encoding='utf-8')
        root = etree.fromstring(data, parser=parser)
    except etree.XMLSyntaxError as ex:
        raise LtiError(str(ex) or 'Body is not valid XML') from ex

    try:
        imsx_message_identifier = root.xpath("//def:imsx_messageIdentifier", namespaces=namespaces)[0].text or ''
    except IndexError as ex:
        raise LtiError('Failed to parse imsx_messageIdentifier from XML request body') from ex

    try:
        body = root.xpath("//def:imsx_POXBody", namespaces=namespaces)[0]
    except IndexError as ex:
        raise LtiError('Failed to parse imsx_POXBody from XML request body') from ex

    try:
        action = body.getchildren()[0].tag.replace('{' + lti_spec_namespace + '}', '')
    except IndexError as ex:
        raise LtiError('Failed to parse action from XML request body') from ex

    try:
        sourced_id = root.xpath("//def:sourcedId", namespaces=namespaces)[0].text
    except IndexError as ex:
        raise LtiError('Failed to parse sourcedId from XML request body') from ex

    try:
        score = root.xpath("//def:textString", namespaces=namespaces)[0].text
    except IndexError as ex:
        raise LtiError('Failed to parse score textString from XML request body') from ex

    # Raise exception if score is not float or not in range 0.0-1.0 regarding spec.
    score = float(score)
    if not 0.0 <= score <= 1.0:
        raise LtiError('score value outside the permitted range of 0.0-1.0')

    return imsx_message_identifier, sourced_id, score, action


class OutcomeService:
    """
    Service for handling LTI Outcome Management Service requests.

    For more details see:
    https://www.imsglobal.org/specs/ltiomv1p0
    """

    def __init__(self, xblock):
        self.xblock = xblock

    def handle_request(self, request):
        """
        Handler for Outcome Service requests.

        Parses and validates XML request body. Currently, only the
        replaceResultRequest action is supported.

        Example of request body from LTI provider::

        <?xml version = "1.0" encoding = "UTF-8"?>
            <imsx_POXEnvelopeRequest xmlns = "some_link (may be not required)">
              <imsx_POXHeader>
                <imsx_POXRequestHeaderInfo>
                  <imsx_version>V1.0</imsx_version>
                  <imsx_messageIdentifier>528243ba5241b</imsx_messageIdentifier>
                </imsx_POXRequestHeaderInfo>
              </imsx_POXHeader>
              <imsx_POXBody>
                <replaceResultRequest>
                  <resultRecord>
                    <sourcedGUID>
                      <sourcedId>feb-123-456-2929::28883</sourcedId>
                    </sourcedGUID>
                    <result>
                      <resultScore>
                        <language>en-us</language>
                        <textString>0.4</textString>
                      </resultScore>
                    </result>
                  </resultRecord>
                </replaceResultRequest>
              </imsx_POXBody>
            </imsx_POXEnvelopeRequest>

        See /templates/xml/outcome_service_response.xml for the response body format.

        Arguments:
            request (xblock.django.request.DjangoWebobRequest): Request object for current HTTP request

        Returns:
            str: Outcome Service XML response
        """
        resource_loader = ResourceLoader(__name__)
        response_xml_template = resource_loader.load_unicode('/templates/xml/outcome_service_response.xml')

        # Returns when `action` is unsupported.
        # Supported actions:
        #   - replaceResultRequest.
        unsupported_values = {
            'imsx_codeMajor': 'unsupported',
            'imsx_description': 'Target does not support the requested operation.',
            'imsx_messageIdentifier': 'unknown',
            'response': ''
        }
        # Returns if:
        #   - past due grades are not accepted and grade is past due
        #   - score is out of range
        #   - can't parse response from TP;
        #   - can't verify OAuth signing or OAuth signing is incorrect.
        failure_values = {
            'imsx_codeMajor': 'failure',
            'imsx_description': 'The request has failed.',
            'imsx_messageIdentifier': 'unknown',
            'response': ''
        }
        request_body = request.body.decode('utf-8')

        if not self.xblock.accept_grades_past_due and self.xblock.is_past_due():
            failure_values['imsx_description'] = "Grade is past due"
            return response_xml_template.format(**failure_values)

        try:
            imsx_message_identifier, sourced_id, score, action = parse_grade_xml_body(request_body)
        except LtiError as ex:
            body = escape(request_body) if request_body else ''
            error_message = "Request body XML parsing error: {} {}".format(str(ex), body)
            log.debug("[LTI]: %s", error_message)
            failure_values['imsx_description'] = error_message
            return response_xml_template.format(**failure_values)

        # Verify OAuth signing.
        __, secret = self.xblock.lti_provider_key_secret
        try:
            verify_oauth_body_signature(request, secret, self.xblock.outcome_service_url)
        except (ValueError, LtiError) as ex:
            failure_values['imsx_messageIdentifier'] = escape(imsx_message_identifier)
            error_message = "OAuth verification error: " + escape(str(ex))
            failure_values['imsx_description'] = error_message
            log.debug("[LTI]: %s", error_message)
            return response_xml_template.format(**failure_values)

        user_id = unquote(sourced_id.split(':')[-1])
        real_user = self.xblock.get_lti_1p1_user_from_user_id(user_id)

        if not real_user:  # that means we can't save to database, as we do not have real user id.
            failure_values['imsx_messageIdentifier'] = escape(imsx_message_identifier)
            failure_values['imsx_description'] = "User not found."
            return response_xml_template.format(**failure_values)

        if action == 'replaceResultRequest':
            self.xblock.set_user_module_score(real_user, score, self.xblock.max_score())

            values = {
                'imsx_codeMajor': 'success',
                'imsx_description': f'Score for {sourced_id} is now {score}',
                'imsx_messageIdentifier': escape(imsx_message_identifier),
                'response': '<replaceResultResponse/>'
            }
            log.debug("[LTI]: Grade is saved.")
            return response_xml_template.format(**values)

        unsupported_values['imsx_messageIdentifier'] = escape(imsx_message_identifier)
        log.debug("[LTI]: Incorrect action.")
        return response_xml_template.format(**unsupported_values)
