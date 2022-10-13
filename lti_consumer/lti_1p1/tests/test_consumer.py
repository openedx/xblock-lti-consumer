"""
Unit tests for lti_consumer.lti_1p1.consumer module
"""

import unittest

from unittest.mock import Mock, patch

from lti_consumer.lti_1p1.exceptions import Lti1p1Error
from lti_consumer.lti_1p1.consumer import LtiConsumer1p1, parse_result_json
from lti_consumer.tests.test_utils import make_request

INVALID_JSON_INPUTS = [
    ([
        "kk",   # ValueError
        "{{}",  # ValueError
        "{}}",  # ValueError
        3,       # TypeError
        {},      # TypeError
    ], "Supplied JSON string in request body could not be decoded"),
    ([
        "3",        # valid json, not array or object
        "[]",       # valid json, array too small
        "[3, {}]",  # valid json, 1st element not an object
    ], "Supplied JSON string is a list that does not contain an object as the first element"),
    ([
        '{"@type": "NOTResult"}',  # @type key must have value 'Result'
    ], "JSON object does not contain correct @type attribute"),
    ([
        # @context missing
        '{"@type": "Result", "resultScore": 0.1}',
    ], "JSON object does not contain required key"),
    ([
        '''
        {"@type": "Result",
         "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
         "resultScore": 100}'''  # score out of range
    ], "score value outside the permitted range of 0.0-1.0."),
    ([
        '''
        {"@type": "Result",
         "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
         "resultScore": -2}'''  # score out of range
    ], "score value outside the permitted range of 0.0-1.0."),
    ([
        '''
        {"@type": "Result",
         "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
         "resultScore": "1b"}''',   # score ValueError
        '''
        {"@type": "Result",
         "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
         "resultScore": {}}''',   # score TypeError
    ], "Could not convert resultScore to float"),
]

VALID_JSON_INPUTS = [
    ('''
    {"@type": "Result",
     "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
     "resultScore": 0.1}''', 0.1, ""),  # no comment means we expect ""
    ('''
    [{"@type": "Result",
     "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
     "@id": "anon_id:abcdef0123456789",
     "resultScore": 0.1}]''', 0.1, ""),  # OK to have array of objects -- just take the first.  @id is okay too
    ('''
    {"@type": "Result",
     "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
     "resultScore": 0.1,
     "comment": "ಠ益ಠ"}''', 0.1, "ಠ益ಠ"),  # unicode comment
    ('''
    {"@type": "Result",
     "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result"}''', None, ""),  # no score means we expect None
    ('''
    {"@type": "Result",
     "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
     "resultScore": 0.0}''', 0.0, ""),  # test lower score boundary
    ('''
    {"@type": "Result",
     "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
     "resultScore": 1.0}''', 1.0, ""),  # test upper score boundary
]

GET_RESULT_RESPONSE = {
    "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
    "@type": "Result",
}


class TestParseResultJson(unittest.TestCase):
    """
    Unit tests for `lti_consumer.lti_1p1.consumer.parse_result_json`
    """

    def test_invalid_json(self):
        """
        Test invalid json raises exception
        """
        for error_inputs, error_message in INVALID_JSON_INPUTS:
            for error_input in error_inputs:
                with self.assertRaisesRegex(Lti1p1Error, error_message):
                    parse_result_json(error_input)

    def test_valid_json(self):
        """
        Test valid json returns expected values
        """
        for json_str, expected_score, expected_comment in VALID_JSON_INPUTS:
            score, comment = parse_result_json(json_str)
            self.assertEqual(score, expected_score)
            self.assertEqual(comment, expected_comment)


class TestLtiConsumer1p1(unittest.TestCase):
    """
    Unit tests for LtiConsumer
    """

    def setUp(self):
        super().setUp()
        self.lti_launch_url = 'lti_launch_url'
        self.oauth_key = 'fake_consumer_key'
        self.oauth_secret = 'fake_signature'
        self.lti_consumer = LtiConsumer1p1(self.lti_launch_url, self.oauth_key, self.oauth_secret)

    def test_set_custom_parameters_with_non_dict_raises_error(self):
        with self.assertRaises(ValueError):
            self.lti_consumer.set_custom_parameters('custom_value')

    def test_generate_launch_request_with_no_user_data_raises_error(self):
        with self.assertRaises(ValueError):
            self.lti_consumer.generate_launch_request('resource_link_id')

    def test_generate_launch_request_with_no_context_data_raises_error(self):
        self.lti_consumer.set_user_data('user_id', 'roles', 'result_sourcedid')
        with self.assertRaises(ValueError):
            self.lti_consumer.generate_launch_request('resource_link_id')

    @patch(
        'lti_consumer.lti_1p1.consumer.get_oauth_request_signature',
        Mock(return_value=(
            'OAuth oauth_nonce="fake_nonce", '
            'oauth_timestamp="fake_timestamp", oauth_version="fake_version", oauth_signature_method="fake_method", '
            'oauth_consumer_key="fake_consumer_key", oauth_signature="fake_signature"'
        ))
    )
    def test_generate_launch_request_with_user_and_context_data_succeeds(self):
        user_id = 'user_id'
        roles = 'roles'
        result_sourcedid = 'result_sourcedid'
        context_id = 'context_id'
        context_title = 'context_title'
        context_label = 'context_label'
        resource_link_id = 'resource_link_id'

        self.lti_consumer.set_user_data(user_id, roles, result_sourcedid)
        self.lti_consumer.set_context_data(context_id, context_title, context_label)

        lti_parameters = self.lti_consumer.generate_launch_request(resource_link_id)

        expected_lti_parameters = {
            'oauth_callback': 'about:blank',
            'launch_presentation_return_url': '',
            'lti_message_type': 'basic-lti-launch-request',
            'lti_version': 'LTI-1p0',
            'user_id': user_id,
            'roles': roles,
            'lis_result_sourcedid': result_sourcedid,
            'context_id': context_id,
            'context_label': context_label,
            'context_title': context_title,
            'resource_link_id': resource_link_id,
            'oauth_nonce': 'fake_nonce',
            'oauth_timestamp': 'fake_timestamp',
            'oauth_version': 'fake_version',
            'oauth_signature_method': 'fake_method',
            'oauth_consumer_key': 'fake_consumer_key',
            'oauth_signature': 'fake_signature',
        }
        self.assertEqual(lti_parameters, expected_lti_parameters)

    @patch(
        'lti_consumer.lti_1p1.consumer.get_oauth_request_signature',
        Mock(return_value=(
            'OAuth oauth_nonce="fake_nonce", '
            'oauth_timestamp="fake_timestamp", oauth_version="fake_version", oauth_signature_method="fake_method", '
            'oauth_consumer_key="fake_consumer_key", oauth_signature="fake_signature"'
        ))
    )
    def test_generate_launch_request_with_all_optional_parameters_set_succeeds(self):
        user_id = 'user_id'
        roles = 'roles'
        result_sourcedid = 'result_sourcedid'
        person_sourcedid = 'person_sourcedid'
        person_contact_email_primary = 'person_contact_email_primary'
        context_id = 'context_id'
        context_title = 'context_title'
        context_label = 'context_label'
        outcome_service_url = 'outcome_service_url'
        launch_presentation_locale = 'launch_presentation_locale'
        custom_parameters = {
            'custom_parameter_1': 'custom1',
            'custom_parameter_2': 'custom2',
        }
        resource_link_id = 'resource_link_id'

        self.lti_consumer.set_user_data(
            user_id,
            roles,
            result_sourcedid,
            person_sourcedid=person_sourcedid,
            person_contact_email_primary=person_contact_email_primary
        )
        self.lti_consumer.set_context_data(context_id, context_title, context_label)
        self.lti_consumer.set_outcome_service_url(outcome_service_url)
        self.lti_consumer.set_launch_presentation_locale(launch_presentation_locale)
        self.lti_consumer.set_custom_parameters(custom_parameters)

        lti_parameters = self.lti_consumer.generate_launch_request(resource_link_id)

        expected_lti_parameters = {
            'oauth_callback': 'about:blank',
            'launch_presentation_return_url': '',
            'lti_message_type': 'basic-lti-launch-request',
            'lti_version': 'LTI-1p0',
            'user_id': user_id,
            'roles': roles,
            'lis_result_sourcedid': result_sourcedid,
            'lis_person_sourcedid': person_sourcedid,
            'lis_person_contact_email_primary': person_contact_email_primary,
            'context_id': context_id,
            'context_label': context_label,
            'context_title': context_title,
            'lis_outcome_service_url': outcome_service_url,
            'launch_presentation_locale': launch_presentation_locale,
            'custom_parameter_1': custom_parameters['custom_parameter_1'],
            'custom_parameter_2': custom_parameters['custom_parameter_2'],
            'resource_link_id': resource_link_id,
            'oauth_nonce': 'fake_nonce',
            'oauth_timestamp': 'fake_timestamp',
            'oauth_version': 'fake_version',
            'oauth_signature_method': 'fake_method',
            'oauth_consumer_key': 'fake_consumer_key',
            'oauth_signature': 'fake_signature',
        }
        self.assertEqual(lti_parameters, expected_lti_parameters)

    def test_get_result_with_no_score_or_comment(self):
        self.assertEqual(self.lti_consumer.get_result(), GET_RESULT_RESPONSE)

    def test_get_result_with_score_and_comment(self):
        score = 1.234
        comment = 'score_comment'

        full_response = GET_RESULT_RESPONSE
        full_response.update({
            'resultScore': 1.23,
            'comment': comment
        })
        self.assertEqual(self.lti_consumer.get_result(score, comment), full_response)

    def test_put_result(self):
        self.assertEqual(self.lti_consumer.put_result(), {})

    def test_delete_result(self):
        self.assertEqual(self.lti_consumer.delete_result(), {})

    @patch('lti_consumer.lti_1p1.consumer.log')
    def test_verify_result_headers_verify_content_type_true(self, mock_log):
        """
        Test wrong content type raises exception if `verify_content_type` is True
        """
        request = make_request('')

        with self.assertRaises(Lti1p1Error):
            self.lti_consumer.verify_result_headers(request)

        assert mock_log.error.called

    @patch('lti_consumer.lti_1p1.consumer.log')
    def test_verify_result_headers_no_outcome_service_url(self, mock_log):
        """
        Test exception raised if no outcome_service_url is set
        """
        request = make_request('')
        request.environ['CONTENT_TYPE'] = LtiConsumer1p1.CONTENT_TYPE_RESULT_JSON

        with self.assertRaises(ValueError):
            self.lti_consumer.verify_result_headers(request)

        assert mock_log.error.called

    @patch('lti_consumer.lti_1p1.consumer.verify_oauth_body_signature', Mock(side_effect=Lti1p1Error))
    @patch('lti_consumer.lti_1p1.consumer.log')
    def test_verify_result_headers_lti_error(self, mock_log):
        """
        Test exception raised if request header verification raises error
        """
        request = make_request('')
        request.environ['CONTENT_TYPE'] = LtiConsumer1p1.CONTENT_TYPE_RESULT_JSON

        self.lti_consumer.set_outcome_service_url('outcome_service_url')
        with self.assertRaises(Lti1p1Error):
            self.lti_consumer.verify_result_headers(request)

        assert mock_log.error.called

    @patch('lti_consumer.lti_1p1.consumer.verify_oauth_body_signature', Mock(side_effect=ValueError))
    @patch('lti_consumer.lti_1p1.consumer.log')
    def test_verify_result_headers_value_error(self, mock_log):
        """
        Test exception raised if request header verification raises error
        """
        request = make_request('')
        request.environ['CONTENT_TYPE'] = LtiConsumer1p1.CONTENT_TYPE_RESULT_JSON

        self.lti_consumer.set_outcome_service_url('outcome_service_url')
        with self.assertRaises(Lti1p1Error):
            self.lti_consumer.verify_result_headers(request)

        assert mock_log.error.called

    @patch('lti_consumer.lti_1p1.consumer.verify_oauth_body_signature', Mock(return_value=True))
    def test_verify_result_headers_valid(self):
        """
        Test True is returned if request is valid
        """
        request = make_request('')
        request.environ['CONTENT_TYPE'] = LtiConsumer1p1.CONTENT_TYPE_RESULT_JSON

        self.lti_consumer.set_outcome_service_url('outcome_service_url')
        response = self.lti_consumer.verify_result_headers(request)

        self.assertTrue(response)

    @patch('lti_consumer.lti_1p1.consumer.verify_oauth_body_signature', Mock(return_value=True))
    def test_verify_result_headers_verify_content_type_false_valid(self):
        """
        Test content type check skipped if `verify_content_type` is False
        """
        request = make_request('')
        request.environ['CONTENT_TYPE'] = LtiConsumer1p1.CONTENT_TYPE_RESULT_JSON

        self.lti_consumer.set_outcome_service_url('outcome_service_url')
        response = self.lti_consumer.verify_result_headers(request, False)

        self.assertTrue(response)
