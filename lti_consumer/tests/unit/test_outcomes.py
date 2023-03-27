"""
Unit tests for lti_consumer.outcomes module
"""

import textwrap
import unittest
from copy import copy
from unittest.mock import Mock, PropertyMock, patch

import ddt

from lti_consumer.exceptions import LtiError
from lti_consumer.outcomes import OutcomeService, parse_grade_xml_body
from lti_consumer.tests.test_utils import make_request
from lti_consumer.tests.unit.test_lti_xblock import TestLtiConsumerXBlock

REQUEST_BODY_TEMPLATE_VALID = textwrap.dedent("""
    <?xml version="1.0" encoding="UTF-8"?>
    <imsx_POXEnvelopeRequest xmlns="http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">
      <imsx_POXHeader>
        <imsx_POXRequestHeaderInfo>
          <imsx_version>V1.0</imsx_version>
          <imsx_messageIdentifier>{msg_id}</imsx_messageIdentifier>
        </imsx_POXRequestHeaderInfo>
      </imsx_POXHeader>
      <imsx_POXBody>
        <{action}>
          <resultRecord>
            <sourcedGUID>
              <sourcedId>{sourced_id}</sourcedId>
            </sourcedGUID>
            <result>
              <resultScore>
                <language>en-us</language>
                <textString>{score}</textString>
              </resultScore>
            </result>
          </resultRecord>
        </{action}>
      </imsx_POXBody>
    </imsx_POXEnvelopeRequest>
""")

REQUEST_BODY_TEMPLATE_MISSING_MSG_ID = textwrap.dedent("""
    <?xml version="1.0" encoding="UTF-8"?>
    <imsx_POXEnvelopeRequest xmlns="http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">
      <imsx_POXHeader>
        <imsx_POXRequestHeaderInfo>
          <imsx_version>V1.0</imsx_version>
        </imsx_POXRequestHeaderInfo>
      </imsx_POXHeader>
    </imsx_POXEnvelopeRequest>
""")

REQUEST_BODY_TEMPLATE_MISSING_SOURCED_ID = textwrap.dedent("""
    <?xml version="1.0" encoding="UTF-8"?>
    <imsx_POXEnvelopeRequest xmlns="http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">
      <imsx_POXHeader>
        <imsx_POXRequestHeaderInfo>
          <imsx_version>V1.0</imsx_version>
          <imsx_messageIdentifier>{msg_id}</imsx_messageIdentifier>
        </imsx_POXRequestHeaderInfo>
      </imsx_POXHeader>
      <imsx_POXBody>
        <{action}>
          <resultRecord>
            <sourcedGUID>
            </sourcedGUID>
          </resultRecord>
        </{action}>
      </imsx_POXBody>
    </imsx_POXEnvelopeRequest>
""")

REQUEST_BODY_TEMPLATE_MISSING_BODY = textwrap.dedent("""
    <?xml version="1.0" encoding="UTF-8"?>
    <imsx_POXEnvelopeRequest xmlns="http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">
      <imsx_POXHeader>
        <imsx_POXRequestHeaderInfo>
          <imsx_version>V1.0</imsx_version>
          <imsx_messageIdentifier>{msg_id}</imsx_messageIdentifier>
        </imsx_POXRequestHeaderInfo>
      </imsx_POXHeader>
    </imsx_POXEnvelopeRequest>
""")

REQUEST_BODY_TEMPLATE_MISSING_ACTION = textwrap.dedent("""
    <?xml version="1.0" encoding="UTF-8"?>
    <imsx_POXEnvelopeRequest xmlns="http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">
      <imsx_POXHeader>
        <imsx_POXRequestHeaderInfo>
          <imsx_version>V1.0</imsx_version>
          <imsx_messageIdentifier>{msg_id}</imsx_messageIdentifier>
        </imsx_POXRequestHeaderInfo>
      </imsx_POXHeader>
      <imsx_POXBody>
      </imsx_POXBody>
    </imsx_POXEnvelopeRequest>
""")

REQUEST_BODY_TEMPLATE_MISSING_SCORE = textwrap.dedent("""
    <?xml version="1.0" encoding="UTF-8"?>
    <imsx_POXEnvelopeRequest xmlns="http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">
      <imsx_POXHeader>
        <imsx_POXRequestHeaderInfo>
          <imsx_version>V1.0</imsx_version>
          <imsx_messageIdentifier>{msg_id}</imsx_messageIdentifier>
        </imsx_POXRequestHeaderInfo>
      </imsx_POXHeader>
      <imsx_POXBody>
        <{action}>
          <resultRecord>
            <sourcedGUID>
              <sourcedId>{sourced_id}</sourcedId>
            </sourcedGUID>
            <result>
              <resultScore>
                <language>en-us</language>
              </resultScore>
            </result>
          </resultRecord>
        </{action}>
      </imsx_POXBody>
    </imsx_POXEnvelopeRequest>
""")

REQUEST_TEMPLATE_DEFAULTS = {
    'msg_id': '528243ba5241b',
    'sourced_id': 'lti_provider:localhost-i4x-2-3-lti-31de800015cf4afb973356dbe81496df:4xk1kn',
    'score': 0.5,
    'action': 'replaceResultRequest',
}

RESPONSE_BODY_TEMPLATE = textwrap.dedent("""
    <?xml version="1.0" encoding="UTF-8"?>
    <imsx_POXEnvelopeResponse xmlns = "http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">
        <imsx_POXHeader>
            <imsx_POXResponseHeaderInfo>
                <imsx_version>V1.0</imsx_version>
                <imsx_messageIdentifier>{msg_id}</imsx_messageIdentifier>
                <imsx_statusInfo>
                    <imsx_codeMajor>{code}</imsx_codeMajor>
                    <imsx_severity>status</imsx_severity>
                    <imsx_description>{description}</imsx_description>
                    <imsx_messageRefIdentifier>
                    </imsx_messageRefIdentifier>
                </imsx_statusInfo>
            </imsx_POXResponseHeaderInfo>
        </imsx_POXHeader>
        <imsx_POXBody>{response}</imsx_POXBody>
    </imsx_POXEnvelopeResponse>
""")


class TestParseGradeXmlBody(unittest.TestCase):
    """
    Unit tests for `lti_consumer.outcomes.parse_grade_xml_body`
    """

    def test_valid_request_body(self):
        """
        Test correct values returned on valid request body
        """
        msg_id, sourced_id, score, action = parse_grade_xml_body(
            REQUEST_BODY_TEMPLATE_VALID.format(**REQUEST_TEMPLATE_DEFAULTS)
        )

        self.assertEqual(msg_id, REQUEST_TEMPLATE_DEFAULTS['msg_id'])
        self.assertEqual(sourced_id, REQUEST_TEMPLATE_DEFAULTS['sourced_id'])
        self.assertEqual(score, REQUEST_TEMPLATE_DEFAULTS['score'])
        self.assertEqual(action, REQUEST_TEMPLATE_DEFAULTS['action'])

    def test_lower_score_boundary(self):
        """
        Test correct values returned on valid request body with a
        score that matches the lower boundary of allowed scores
        """
        data = copy(REQUEST_TEMPLATE_DEFAULTS)
        data['score'] = 0.0

        msg_id, sourced_id, score, action = parse_grade_xml_body(
            REQUEST_BODY_TEMPLATE_VALID.format(**data)
        )

        self.assertEqual(msg_id, data['msg_id'])
        self.assertEqual(sourced_id, data['sourced_id'])
        self.assertEqual(score, data['score'])
        self.assertEqual(action, data['action'])

    def test_upper_score_boundary(self):
        """
        Test correct values returned on valid request body with a
        score that matches the upper boundary of allowed scores
        """
        data = copy(REQUEST_TEMPLATE_DEFAULTS)
        data['score'] = 1.0

        msg_id, sourced_id, score, action = parse_grade_xml_body(
            REQUEST_BODY_TEMPLATE_VALID.format(**data)
        )

        self.assertEqual(msg_id, data['msg_id'])
        self.assertEqual(sourced_id, data['sourced_id'])
        self.assertEqual(score, data['score'])
        self.assertEqual(action, data['action'])

    def test_missing_msg_id(self):
        """
        Test missing <imsx_messageIdentifier> raises LtiError
        """
        with self.assertRaises(LtiError):
            _, _, _, _ = parse_grade_xml_body(
                REQUEST_BODY_TEMPLATE_MISSING_MSG_ID.format(**REQUEST_TEMPLATE_DEFAULTS)
            )

    def test_missing_sourced_id(self):
        """
        Test missing <sourcedId> raises LtiError
        """
        with self.assertRaises(LtiError):
            _, _, _, _ = parse_grade_xml_body(
                REQUEST_BODY_TEMPLATE_MISSING_SOURCED_ID.format(**REQUEST_TEMPLATE_DEFAULTS)
            )

    def test_missing_body(self):
        """
        Test missing <imsx_POXBody> raises LtiError
        """
        with self.assertRaises(LtiError):
            _, _, _, _ = parse_grade_xml_body(
                REQUEST_BODY_TEMPLATE_MISSING_BODY.format(**REQUEST_TEMPLATE_DEFAULTS)
            )

    def test_missing_action(self):
        """
        Test missing <replaceResultRequest> raises LtiError
        """
        with self.assertRaises(LtiError):
            _, _, _, _ = parse_grade_xml_body(
                REQUEST_BODY_TEMPLATE_MISSING_ACTION.format(**REQUEST_TEMPLATE_DEFAULTS)
            )

    def test_missing_score(self):
        """
        Test missing score <textString> raises LtiError
        """
        with self.assertRaises(LtiError):
            _, _, _, _ = parse_grade_xml_body(
                REQUEST_BODY_TEMPLATE_MISSING_SCORE.format(**REQUEST_TEMPLATE_DEFAULTS)
            )

    def test_score_outside_range(self):
        """
        Test score outside the range raises exception
        """
        data = copy(REQUEST_TEMPLATE_DEFAULTS)

        with self.assertRaises(LtiError):
            data['score'] = 10
            _, _, _, _ = parse_grade_xml_body(REQUEST_BODY_TEMPLATE_VALID.format(**data))

        with self.assertRaises(LtiError):
            data['score'] = -10
            _, _, _, _ = parse_grade_xml_body(REQUEST_BODY_TEMPLATE_VALID.format(**data))

    def test_invalid_score(self):
        """
        Test non-float score raises exception
        """
        data = copy(REQUEST_TEMPLATE_DEFAULTS)
        data['score'] = '1,0'

        with self.assertRaises(Exception):
            _, _, _, _ = parse_grade_xml_body(REQUEST_BODY_TEMPLATE_VALID.format(**data))

    def test_empty_xml(self):
        """
        Test empty xml raises exception
        """
        with self.assertRaises(LtiError):
            _, _, _, _ = parse_grade_xml_body('')

    def test_invalid_xml(self):
        """
        Test invalid xml raises exception
        """
        with self.assertRaises(LtiError):
            _, _, _, _ = parse_grade_xml_body('<xml>')

    def test_string_with_unicode_chars(self):
        """
        Test that system is tolerant to data which has unicode chars in
        strings which are not specified as unicode.
        """
        request_body_template = textwrap.dedent("""
            <?xml version="1.0" encoding="UTF-8"?>
            <imsx_POXEnvelopeRequest xmlns="http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">
              <imsx_POXHeader>
                <imsx_POXRequestHeaderInfo>
                  <imsx_version>V1.0</imsx_version>
                  <imsx_messageIdentifier>ţéšţ_message_id</imsx_messageIdentifier>
                </imsx_POXRequestHeaderInfo>
              </imsx_POXHeader>
              <imsx_POXBody>
                <ţéšţ_action>
                  <resultRecord>
                    <sourcedGUID>
                      <sourcedId>ţéšţ_sourced_id</sourcedId>
                    </sourcedGUID>
                    <result>
                      <resultScore>
                        <language>en-us</language>
                        <textString>1.0</textString>
                      </resultScore>
                    </result>
                  </resultRecord>
                </ţéšţ_action>
              </imsx_POXBody>
            </imsx_POXEnvelopeRequest>
        """)

        msg_id, sourced_id, score, action = parse_grade_xml_body(request_body_template)

        self.assertEqual(msg_id, 'ţéšţ_message_id')
        self.assertEqual(sourced_id, 'ţéšţ_sourced_id')
        self.assertEqual(score, 1.0)
        self.assertEqual(action, 'ţéšţ_action')


@ddt.ddt
class TestOutcomeService(TestLtiConsumerXBlock):
    """
    Unit tests for OutcomeService
    """

    def setUp(self):
        super().setUp()
        self.outcome_service = OutcomeService(self.xblock)

        # Set up user mock for LtiConsumerXBlock.get_lti_1p1_user_from_user_id method.
        self.mock_get_user_id_patcher = patch('lti_consumer.lti_xblock.LtiConsumerXBlock.get_lti_1p1_user_from_user_id')
        self.addCleanup(self.mock_get_user_id_patcher.stop)
        self.mock_get_user_id_patcher_enabled = self.mock_get_user_id_patcher.start()

        mock_user = Mock()
        mock_id = PropertyMock(return_value=1)
        type(mock_user).id = mock_id
        self.mock_get_user_id_patcher_enabled.return_value = mock_user

    @patch('lti_consumer.outcomes.verify_oauth_body_signature', Mock(return_value=True))
    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.lti_provider_key_secret', PropertyMock(return_value=('t', 's')))
    @patch('lti_consumer.outcomes.parse_grade_xml_body', Mock(return_value=('', '', 0.5, 'replaceResultRequest')))
    def test_handle_replace_result_success(self):
        """
        Test replace result request returns with success indicator
        """
        request = make_request('')

        values = {
            'code': 'success',
            'description': 'Score for  is now 0.5',
            'msg_id': '',
            'response': '<replaceResultResponse/>'
        }

        self.assertEqual(
            self.outcome_service.handle_request(request).strip(),
            RESPONSE_BODY_TEMPLATE.format(**values).strip()
        )

    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.is_past_due', Mock(return_value=True))
    def test_grade_past_due(self):
        """
        Test late grade returns failure response
        """
        request = make_request('')
        self.xblock.accept_grades_past_due = False
        response = self.outcome_service.handle_request(request)

        self.assertIn('failure', response)
        self.assertIn('Grade is past due', response)

    @patch('lti_consumer.outcomes.parse_grade_xml_body')
    def test_lti_error_not_raises_type_error(self, mock_parse):
        """
        Test XML parsing LtiError exception doesn't raise TypeError exception
        while escaping the request body.
        """
        request = make_request('test_string')

        mock_parse.side_effect = LtiError
        response = self.outcome_service.handle_request(request)
        self.assertNotIn('TypeError', response)
        self.assertNotIn('a bytes-like object is required', response)
        self.assertIn('Request body XML parsing error', response)

    @patch('lti_consumer.outcomes.parse_grade_xml_body')
    def test_xml_parse_lti_error(self, mock_parse):
        """
        Test XML parsing LtiError returns failure response
        """
        request = make_request('')

        mock_parse.side_effect = LtiError
        response = self.outcome_service.handle_request(request)
        self.assertIn('failure', response)
        self.assertIn('Request body XML parsing error', response)

    @patch('lti_consumer.outcomes.verify_oauth_body_signature')
    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.lti_provider_key_secret', PropertyMock(return_value=('t', 's')))
    @patch('lti_consumer.outcomes.parse_grade_xml_body', Mock(return_value=('', '', 0.5, 'replaceResultRequest')))
    def test_invalid_signature(self, mock_verify):
        """
        Test invalid oauth signature returns failure response
        """
        request = make_request('')

        mock_verify.side_effect = ValueError
        self.assertIn('failure', self.outcome_service.handle_request(request))

        mock_verify.side_effect = LtiError
        self.assertIn('failure', self.outcome_service.handle_request(request))

    @patch('lti_consumer.outcomes.verify_oauth_body_signature', Mock(return_value=True))
    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.lti_provider_key_secret', PropertyMock(return_value=('t', 's')))
    @patch('lti_consumer.outcomes.parse_grade_xml_body', Mock(return_value=('', '', 0.5, 'replaceResultRequest')))
    def test_user_not_found(self):
        """
        Test user not found returns failure response
        """
        request = make_request('')

        self.mock_get_user_id_patcher_enabled.return_value = None
        response = self.outcome_service.handle_request(request)

        self.assertIn('failure', response)
        self.assertIn('User not found', response)

    @patch('lti_consumer.outcomes.verify_oauth_body_signature', Mock(return_value=True))
    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.lti_provider_key_secret', PropertyMock(return_value=('t', 's')))
    @patch('lti_consumer.outcomes.parse_grade_xml_body', Mock(return_value=('', '', 0.5, 'unsupportedRequest')))
    def test_unsupported_action(self):
        """
        Test unsupported action returns unsupported response
        """
        request = make_request('')
        response = self.outcome_service.handle_request(request)

        self.assertIn('unsupported', response)
        self.assertIn('Target does not support the requested operation.', response)
