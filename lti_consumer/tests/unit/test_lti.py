# -*- coding: utf-8 -*-
"""
Unit tests for lti_consumer.lti module
"""

import unittest

from datetime import timedelta
from mock import Mock, PropertyMock, patch

from django.utils import timezone

from lti_consumer.tests.unit.test_utils import FAKE_USER_ID, make_request
from lti_consumer.tests.unit.test_lti_consumer import TestLtiConsumerXBlock

from lti_consumer.lti import parse_result_json, LtiConsumer
from lti_consumer.exceptions import LtiError


INVALID_JSON_INPUTS = [
    ([
        u"kk",   # ValueError
        u"{{}",  # ValueError
        u"{}}",  # ValueError
        3,       # TypeError
        {},      # TypeError
    ], u"Supplied JSON string in request body could not be decoded"),
    ([
        u"3",        # valid json, not array or object
        u"[]",       # valid json, array too small
        u"[3, {}]",  # valid json, 1st element not an object
    ], u"Supplied JSON string is a list that does not contain an object as the first element"),
    ([
        u'{"@type": "NOTResult"}',  # @type key must have value 'Result'
    ], u"JSON object does not contain correct @type attribute"),
    ([
        # @context missing
        u'{"@type": "Result", "resultScore": 0.1}',
    ], u"JSON object does not contain required key"),
    ([
        u'''
        {"@type": "Result",
         "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
         "resultScore": 100}'''  # score out of range
    ], u"score value outside the permitted range of 0.0-1.0."),
    ([
        u'''
        {"@type": "Result",
         "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
         "resultScore": -2}'''  # score out of range
    ], u"score value outside the permitted range of 0.0-1.0."),
    ([
        u'''
        {"@type": "Result",
         "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
         "resultScore": "1b"}''',   # score ValueError
        u'''
        {"@type": "Result",
         "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
         "resultScore": {}}''',   # score TypeError
    ], u"Could not convert resultScore to float"),
]

VALID_JSON_INPUTS = [
    (u'''
    {"@type": "Result",
     "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
     "resultScore": 0.1}''', 0.1, u""),  # no comment means we expect ""
    (u'''
    [{"@type": "Result",
     "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
     "@id": "anon_id:abcdef0123456789",
     "resultScore": 0.1}]''', 0.1, u""),  # OK to have array of objects -- just take the first.  @id is okay too
    (u'''
    {"@type": "Result",
     "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
     "resultScore": 0.1,
     "comment": "ಠ益ಠ"}''', 0.1, u"ಠ益ಠ"),  # unicode comment
    (u'''
    {"@type": "Result",
     "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result"}''', None, u""),  # no score means we expect None
    (u'''
    {"@type": "Result",
     "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
     "resultScore": 0.0}''', 0.0, u""),  # test lower score boundary
    (u'''
    {"@type": "Result",
     "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
     "resultScore": 1.0}''', 1.0, u""),  # test upper score boundary
]

GET_RESULT_RESPONSE = {
    "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
    "@type": "Result",
}


class TestParseResultJson(unittest.TestCase):
    """
    Unit tests for `lti_consumer.lti.parse_result_json`
    """

    def test_invalid_json(self):
        """
        Test invalid json raises exception
        """
        for error_inputs, error_message in INVALID_JSON_INPUTS:
            for error_input in error_inputs:
                with self.assertRaisesRegexp(LtiError, error_message):
                    parse_result_json(error_input)

    def test_valid_json(self):
        """
        Test valid json returns expected values
        """
        for json_str, expected_score, expected_comment in VALID_JSON_INPUTS:
            score, comment = parse_result_json(json_str)
            self.assertEqual(score, expected_score)
            self.assertEqual(comment, expected_comment)


class TestLtiConsumer(TestLtiConsumerXBlock):
    """
    Unit tests for LtiConsumer
    """

    def setUp(self):
        super(TestLtiConsumer, self).setUp()
        self.lti_consumer = LtiConsumer(self.xblock)

    @patch(
        'lti_consumer.lti.get_oauth_request_signature',
        Mock(return_value=(
            'OAuth oauth_nonce="fake_nonce", '
            'oauth_timestamp="fake_timestamp", oauth_version="fake_version", oauth_signature_method="fake_method", '
            'oauth_consumer_key="fake_consumer_key", oauth_signature="fake_signature"'
        ))
    )
    @patch(
        'lti_consumer.lti_consumer.LtiConsumerXBlock.prefixed_custom_parameters',
        PropertyMock(return_value={u'custom_param_1': 'custom1', u'custom_param_2': 'custom2'})
    )
    @patch(
        'lti_consumer.lti_consumer.LtiConsumerXBlock.lti_provider_key_secret',
        PropertyMock(return_value=('t', 's'))
    )
    @patch('lti_consumer.lti_consumer.LtiConsumerXBlock.user_id', PropertyMock(return_value=FAKE_USER_ID))
    def test_get_signed_lti_parameters(self):
        """
        Test `get_signed_lti_parameters` returns the correct dict
        """
        self.lti_consumer.xblock.due = timezone.now()
        self.lti_consumer.xblock.graceperiod = timedelta(days=1)

        expected_lti_parameters = {
            u'user_id': self.lti_consumer.xblock.user_id,
            u'oauth_callback': u'about:blank',
            u'launch_presentation_return_url': '',
            u'lti_message_type': u'basic-lti-launch-request',
            u'lti_version': 'LTI-1p0',
            u'roles': self.lti_consumer.xblock.role,
            u'resource_link_id': self.lti_consumer.xblock.resource_link_id,
            u'lis_result_sourcedid': self.lti_consumer.xblock.lis_result_sourcedid,
            u'context_id': self.lti_consumer.xblock.context_id,
            u'lis_outcome_service_url': self.lti_consumer.xblock.outcome_service_url,
            u'custom_component_display_name': self.lti_consumer.xblock.display_name,
            u'custom_component_due_date': self.lti_consumer.xblock.due.strftime('%Y-%m-%d %H:%M:%S'),
            u'custom_component_graceperiod': str(self.lti_consumer.xblock.graceperiod.total_seconds()),
            u'custom_user_id': unicode(5),
            'lis_person_sourcedid': 'edx',
            'lis_person_contact_email_primary': 'edx@example.com',
            'lis_person_name_given': 'Jane',
            'lis_person_name_family': 'Doe',
            'lis_person_name_full': 'Jane Doe',
            'launch_presentation_locale': 'en',
            u'custom_param_1': 'custom1',
            u'custom_param_2': 'custom2',
            u'oauth_nonce': 'fake_nonce',
            'oauth_timestamp': 'fake_timestamp',
            'oauth_version': 'fake_version',
            'oauth_signature_method': 'fake_method',
            'oauth_consumer_key': 'fake_consumer_key',
            'oauth_signature': u'fake_signature'
        }
        self.lti_consumer.xblock.has_score = True
        self.lti_consumer.xblock.ask_to_send_username = True
        self.lti_consumer.xblock.ask_to_send_email = True
        self.lti_consumer.xblock.ask_to_send_first_name = True
        self.lti_consumer.xblock.ask_to_send_last_name = True
        self.lti_consumer.xblock.ask_to_send_full_name = True
        self.lti_consumer.xblock.runtime.get_real_user.return_value = Mock(
            id=5,
            email='edx@example.com',
            username='edx',
            profile=Mock(filter=Mock(return_value=[Mock(value='Jane Doe')])),
            preferences=Mock(filter=Mock(return_value=[Mock(value='en')]))
        )
        self.assertEqual(self.lti_consumer.get_signed_lti_parameters(), expected_lti_parameters)

        # Test that `lis_person_name_family` returns empty string when `lis_person_name_full`
        # contains only one name
        expected_lti_parameters.update({
            "lis_person_name_family": "",
            "lis_person_name_full": "Jane"
        })
        self.lti_consumer.xblock.runtime.get_real_user.return_value = Mock(
            id=5,
            email='edx@example.com',
            username='edx',
            profile=Mock(filter=Mock(return_value=[Mock(value='Jane')])),
            preferences=Mock(filter=Mock(return_value=[Mock(value='en')]))
        )
        self.assertEqual(self.lti_consumer.get_signed_lti_parameters(), expected_lti_parameters)

        # Test that `custom_user_id`, `lis_person_sourcedid`, `lis_person_contact_email_primary`,
        # `lis_person_name_given`, `lis_person_name_family`, `lis_person_name_full`
        # and `launch_presentation_locale` are not included in the returned
        # LTI parameters when a user cannot be found
        self.lti_consumer.xblock.runtime.get_real_user.return_value = {}
        del expected_lti_parameters['custom_user_id']
        del expected_lti_parameters['lis_person_sourcedid']
        del expected_lti_parameters['lis_person_contact_email_primary']
        del expected_lti_parameters['lis_person_name_given']
        del expected_lti_parameters['lis_person_name_family']
        del expected_lti_parameters['lis_person_name_full']
        del expected_lti_parameters['launch_presentation_locale']
        self.assertEqual(self.lti_consumer.get_signed_lti_parameters(), expected_lti_parameters)

    def test_get_result(self):
        """
        Test `get_result` returns valid json response
        """
        self.xblock.module_score = 0.9
        self.xblock.score_comment = 'Great Job!'
        response = dict(GET_RESULT_RESPONSE)
        response.update({
            "resultScore": self.xblock.module_score,
            "comment": self.xblock.score_comment
        })
        self.assertEqual(self.lti_consumer.get_result(Mock()), response)

        self.xblock.module_score = None
        self.xblock.score_comment = ''
        self.assertEqual(self.lti_consumer.get_result(Mock()), GET_RESULT_RESPONSE)

    @patch('lti_consumer.lti_consumer.LtiConsumerXBlock.clear_user_module_score')
    def test_delete_result(self, mock_clear):
        """
        Test `delete_result` calls `LtiConsumerXBlock.clear_user_module_score`
        """
        user = Mock()
        response = self.lti_consumer.delete_result(user)

        mock_clear.assert_called_with(user)
        self.assertEqual(response, {})

    @patch('lti_consumer.lti_consumer.LtiConsumerXBlock.max_score', Mock(return_value=1.0))
    @patch('lti_consumer.lti_consumer.LtiConsumerXBlock.set_user_module_score')
    @patch('lti_consumer.lti_consumer.LtiConsumerXBlock.clear_user_module_score')
    @patch('lti_consumer.lti.parse_result_json')
    def test_put_result(self, mock_parse, mock_clear, mock_set):
        """
        Test `put_result` calls `LtiConsumerXBlock.set_user_module_score`
        or `LtiConsumerXblock.clear_user_module_score` if resultScore not included in request
        """
        user = Mock()
        score = 0.9
        comment = 'Great Job!'

        mock_parse.return_value = (score, comment)
        response = self.lti_consumer.put_result(user, '')
        mock_set.assert_called_with(user, score, 1.0, comment)
        self.assertEqual(response, {})

        mock_parse.return_value = (None, '')
        response = self.lti_consumer.put_result(user, '')
        mock_clear.assert_called_with(user)
        self.assertEqual(response, {})

    @patch('lti_consumer.lti.log')
    def test_verify_result_headers_verify_content_type_true(self, mock_log):
        """
        Test wrong content type raises exception if `verify_content_type` is True
        """
        request = make_request('')

        with self.assertRaises(LtiError):
            self.lti_consumer.verify_result_headers(request)
            self.assertTrue(mock_log.called)

    @patch('lti_consumer.lti.verify_oauth_body_signature', Mock(return_value=True))
    @patch('lti_consumer.lti_consumer.LtiConsumerXBlock.lti_provider_key_secret', PropertyMock(return_value=('t', 's')))
    def test_verify_result_headers_verify_content_type_false(self):
        """
        Test content type check skipped if `verify_content_type` is False
        """
        request = make_request('')
        request.environ['CONTENT_TYPE'] = LtiConsumer.CONTENT_TYPE_RESULT_JSON
        response = self.lti_consumer.verify_result_headers(request, False)

        self.assertTrue(response)

    @patch('lti_consumer.lti.verify_oauth_body_signature', Mock(return_value=True))
    @patch('lti_consumer.lti_consumer.LtiConsumerXBlock.lti_provider_key_secret', PropertyMock(return_value=('t', 's')))
    def test_verify_result_headers_valid(self):
        """
        Test True is returned if request is valid
        """
        request = make_request('')
        request.environ['CONTENT_TYPE'] = LtiConsumer.CONTENT_TYPE_RESULT_JSON
        response = self.lti_consumer.verify_result_headers(request)

        self.assertTrue(response)

    @patch('lti_consumer.lti.verify_oauth_body_signature', Mock(side_effect=LtiError))
    @patch('lti_consumer.lti_consumer.LtiConsumerXBlock.lti_provider_key_secret', PropertyMock(return_value=('t', 's')))
    @patch('lti_consumer.lti.log')
    def test_verify_result_headers_lti_error(self, mock_log):
        """
        Test exception raised if request header verification raises error
        """
        request = make_request('')
        request.environ['CONTENT_TYPE'] = LtiConsumer.CONTENT_TYPE_RESULT_JSON

        with self.assertRaises(LtiError):
            self.lti_consumer.verify_result_headers(request)
            self.assertTrue(mock_log.called)

    @patch('lti_consumer.lti.verify_oauth_body_signature', Mock(side_effect=ValueError))
    @patch('lti_consumer.lti_consumer.LtiConsumerXBlock.lti_provider_key_secret', PropertyMock(return_value=('t', 's')))
    @patch('lti_consumer.lti.log')
    def test_verify_result_headers_value_error(self, mock_log):
        """
        Test exception raised if request header verification raises error
        """
        request = make_request('')
        request.environ['CONTENT_TYPE'] = LtiConsumer.CONTENT_TYPE_RESULT_JSON

        with self.assertRaises(LtiError):
            self.lti_consumer.verify_result_headers(request)
            self.assertTrue(mock_log.called)
