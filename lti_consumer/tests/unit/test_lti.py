# -*- coding: utf-8 -*-
"""
Unit tests for lti_consumer.lti module
"""

import unittest

from datetime import timedelta
from mock import Mock, PropertyMock, patch
from six import text_type

from django.utils import timezone

from lti_consumer.tests.unit.test_utils import make_request, patch_signed_parameters
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

    def _update_xblock_for_signed_parameters(self):
        """
        Prepare the LTI XBlock for signing the parameters.
        """
        self.lti_consumer.xblock.due = timezone.now()
        self.lti_consumer.xblock.graceperiod = timedelta(days=1)
        self.lti_consumer.xblock.has_score = True
        self.lti_consumer.xblock.ask_to_send_username = True
        self.lti_consumer.xblock.ask_to_send_email = True
        self.lti_consumer.xblock.runtime.get_real_user.return_value = Mock(
            email='edx@example.com',
            username='edx',
            preferences=Mock(filter=Mock(return_value=[Mock(value='en')]))
        )

    @patch_signed_parameters
    def test_get_signed_lti_parameters(self):
        """
        Test `get_signed_lti_parameters` returns the correct dict
        """
        self._update_xblock_for_signed_parameters()
        expected_lti_parameters = {
            text_type('user_id'): self.lti_consumer.xblock.user_id,
            text_type('oauth_callback'): 'about:blank',
            text_type('launch_presentation_return_url'): '',
            text_type('lti_message_type'): 'basic-lti-launch-request',
            text_type('lti_version'): 'LTI-1p0',
            text_type('roles'): self.lti_consumer.xblock.role,
            text_type('resource_link_id'): self.lti_consumer.xblock.resource_link_id,
            text_type('lis_result_sourcedid'): self.lti_consumer.xblock.lis_result_sourcedid,
            text_type('context_id'): self.lti_consumer.xblock.context_id,
            text_type('lis_outcome_service_url'): self.lti_consumer.xblock.outcome_service_url,
            text_type('custom_component_display_name'): self.lti_consumer.xblock.display_name,
            text_type('custom_component_due_date'): self.lti_consumer.xblock.due.strftime('%Y-%m-%d %H:%M:%S'),
            text_type('custom_component_graceperiod'): str(self.lti_consumer.xblock.graceperiod.total_seconds()),
            'lis_person_sourcedid': 'edx',
            'lis_person_contact_email_primary': 'edx@example.com',
            'launch_presentation_locale': 'en',
            text_type('custom_param_1'): 'custom1',
            text_type('custom_param_2'): 'custom2',
            text_type('oauth_nonce'): 'fake_nonce',
            'oauth_timestamp': 'fake_timestamp',
            'oauth_version': 'fake_version',
            'oauth_signature_method': 'fake_method',
            'oauth_consumer_key': 'fake_consumer_key',
            'oauth_signature': 'fake_signature',
            text_type('context_label'): self.lti_consumer.xblock.course.display_org_with_default,
            text_type('context_title'): self.lti_consumer.xblock.course.display_name_with_default,
        }
        self.assertEqual(self.lti_consumer.get_signed_lti_parameters(), expected_lti_parameters)

        # Test that `lis_person_sourcedid`, `lis_person_contact_email_primary`, and `launch_presentation_locale`
        # are not included in the returned LTI parameters when a user cannot be found
        self.lti_consumer.xblock.runtime.get_real_user.return_value = {}
        del expected_lti_parameters['lis_person_sourcedid']
        del expected_lti_parameters['lis_person_contact_email_primary']
        del expected_lti_parameters['launch_presentation_locale']
        self.assertEqual(self.lti_consumer.get_signed_lti_parameters(), expected_lti_parameters)

    @patch_signed_parameters
    @patch('lti_consumer.lti.log')
    def test_parameter_processors(self, mock_log):
        self._update_xblock_for_signed_parameters()
        self.xblock.enable_processors = True

        with patch('lti_consumer.lti_consumer.LtiConsumerXBlock.get_settings', return_value={
            'parameter_processors': [
                'lti_consumer.tests.unit.test_utils:dummy_processor',
            ],
        }):
            params = self.lti_consumer.get_signed_lti_parameters()
            assert '' == params['custom_author_country']
            assert 'author@example.com' == params['custom_author_email']
            assert not mock_log.exception.called

    @patch_signed_parameters
    @patch('lti_consumer.lti.log')
    def test_default_params(self, mock_log):
        self._update_xblock_for_signed_parameters()
        self.xblock.enable_processors = True

        with patch('lti_consumer.lti_consumer.LtiConsumerXBlock.get_settings', return_value={
            'parameter_processors': [
                'lti_consumer.tests.unit.test_utils:defaulting_processor',
            ],
        }):
            params = self.lti_consumer.get_signed_lti_parameters()
            assert '' == params['custom_country']
            assert 'Lex' == params['custom_name']
            assert not mock_log.exception.called

    @patch_signed_parameters
    @patch('lti_consumer.lti.log')
    def test_default_params_with_error(self, mock_log):
        self._update_xblock_for_signed_parameters()
        self.xblock.enable_processors = True

        with patch('lti_consumer.lti_consumer.LtiConsumerXBlock.get_settings', return_value={
            'parameter_processors': [
                'lti_consumer.tests.unit.test_utils:faulty_processor',
            ],
        }):
            params = self.lti_consumer.get_signed_lti_parameters()
            assert 'Lex' == params['custom_name']
            assert mock_log.exception.called

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

        assert mock_log.error.called

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

        assert mock_log.error.called

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

        assert mock_log.error.called
