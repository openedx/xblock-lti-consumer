"""
Unit tests for LtiConsumerXBlock
"""

from __future__ import absolute_import

from datetime import timedelta
import json
import uuid

import ddt
import six
from six.moves.urllib import parse
from Crypto.PublicKey import RSA
from django.test.testcases import TestCase
from django.utils import timezone
from jwkest.jwk import RSAKey
from mock import Mock, PropertyMock, patch

from lti_consumer.exceptions import LtiError
from lti_consumer.lti_consumer import LtiConsumerXBlock, parse_handler_suffix
from lti_consumer.tests.unit import test_utils
from lti_consumer.tests.unit.test_utils import (FAKE_USER_ID, make_request,
                                                make_xblock)
from lti_consumer.lti_1p3.tests.utils import create_jwt


HTML_PROBLEM_PROGRESS = '<div class="problem-progress">'
HTML_ERROR_MESSAGE = '<h3 class="error_message">'
HTML_LAUNCH_MODAL_BUTTON = 'btn-lti-modal'
HTML_LAUNCH_NEW_WINDOW_BUTTON = 'btn-lti-new-window'
HTML_IFRAME = '<iframe'


class TestLtiConsumerXBlock(TestCase):
    """
    Unit tests for LtiConsumerXBlock.max_score()
    """

    def setUp(self):
        super(TestLtiConsumerXBlock, self).setUp()
        self.xblock_attributes = {
            'launch_url': 'http://www.example.com',
        }
        self.xblock = make_xblock('lti_consumer', LtiConsumerXBlock, self.xblock_attributes)


class TestProperties(TestLtiConsumerXBlock):
    """
    Unit tests for LtiConsumerXBlock properties
    """

    def test_descriptor(self):
        """
        Test `descriptor` returns the XBLock object
        """
        self.assertEqual(self.xblock.descriptor, self.xblock)

    def test_workbench_scenarios(self):
        """
        Basic tests that `workbench_scenarios()` returns a well formed scenario.
        """
        scenarios = self.xblock.workbench_scenarios()
        assert isinstance(scenarios, list)
        assert len(scenarios) == 1, 'Keep it to a single scenario with multiple squences.'

        scenario = scenarios[0]
        assert scenario[0] == 'LTI Consumer XBlock'
        assert '<lti_consumer' in scenario[1]

    def test_settings(self):
        """
        Test that the XBlock is using the SettingsService correctly.
        """
        sample_settings_bucket = {
            'parameter_processors': [],
        }

        self.xblock.runtime.service = Mock(
            return_value=Mock(
                get_settings_bucket=Mock(return_value=sample_settings_bucket)
            )
        )

        assert self.xblock.get_settings() == sample_settings_bucket

    def test_settings_without_service(self):
        """
        Test that the XBlock can work without the SettingsService.
        """
        self.xblock.runtime.service = Mock(return_value=None)
        assert self.xblock.get_settings() == {}

    def test_context_id(self):
        """
        Test `context_id` returns unicode course id
        """
        self.assertEqual(self.xblock.context_id, six.text_type(self.xblock.course_id))  # pylint: disable=no-member

    def test_validate(self):
        """
        Test that if custom_parameters is empty string, a validation error is added
        """
        self.xblock.custom_parameters = ''
        validation = self.xblock.validate()
        self.assertFalse(validation.empty)

    def test_role(self):
        """
        Test `role` returns the correct LTI role string
        """
        self.xblock.runtime.get_user_role.return_value = 'student'
        self.assertEqual(self.xblock.role, 'Student')

        self.xblock.runtime.get_user_role.return_value = 'guest'
        self.assertEqual(self.xblock.role, 'Student')

        self.xblock.runtime.get_user_role.return_value = 'staff'
        self.assertEqual(self.xblock.role, 'Administrator')

        self.xblock.runtime.get_user_role.return_value = 'instructor'
        self.assertEqual(self.xblock.role, 'Instructor')

    def test_course(self):
        """
        Test `course` calls modulestore.get_course
        """
        mock_get_course = self.xblock.runtime.descriptor_runtime.modulestore.get_course
        mock_get_course.return_value = None
        course = self.xblock.course

        self.assertTrue(mock_get_course.called)
        self.assertIsNone(course)

    @patch('lti_consumer.lti_consumer.LtiConsumerXBlock.course')
    def test_lti_provider_key_secret(self, mock_course):
        """
        Test `lti_provider_key_secret` returns correct key and secret
        """
        provider = 'lti_provider'
        key = 'test'
        secret = 'secret'
        self.xblock.lti_id = provider
        type(mock_course).lti_passports = PropertyMock(return_value=["{}:{}:{}".format(provider, key, secret)])
        lti_provider_key, lti_provider_secret = self.xblock.lti_provider_key_secret

        self.assertEqual(lti_provider_key, key)
        self.assertEqual(lti_provider_secret, secret)

    @patch('lti_consumer.lti_consumer.LtiConsumerXBlock.course')
    def test_lti_provider_key_secret_not_found(self, mock_course):
        """
        Test `lti_provider_key_secret` returns correct key and secret
        """
        provider = 'lti_provider'
        key = 'test'
        secret = 'secret'
        self.xblock.lti_id = 'wrong_provider'
        type(mock_course).lti_passports = PropertyMock(return_value=["{}:{}:{}".format(provider, key, secret)])
        lti_provider_key, lti_provider_secret = self.xblock.lti_provider_key_secret

        self.assertEqual(lti_provider_key, '')
        self.assertEqual(lti_provider_secret, '')

    @patch('lti_consumer.lti_consumer.LtiConsumerXBlock.course')
    def test_lti_provider_key_secret_corrupt_lti_passport(self, mock_course):
        """
        Test `lti_provider_key_secret` when a corrupt lti_passport is encountered
        """
        provider = 'lti_provider'
        key = 'test'
        secret = 'secret'
        self.xblock.lti_id = provider
        type(mock_course).lti_passports = PropertyMock(return_value=["{}{}{}".format(provider, key, secret)])

        with self.assertRaises(LtiError):
            _, _ = self.xblock.lti_provider_key_secret

    def test_user_id(self):
        """
        Test `user_id` returns the user_id string
        """
        self.xblock.runtime.anonymous_student_id = FAKE_USER_ID
        self.assertEqual(self.xblock.user_id, FAKE_USER_ID)

    def test_user_id_url_encoded(self):
        """
        Test `user_id` url encodes the user id
        """
        self.xblock.runtime.anonymous_student_id = 'user_id?&. '
        self.assertEqual(self.xblock.user_id, 'user_id%3F%26.%20')

    def test_user_id_none(self):
        """
        Test `user_id` raises LtiError when the user id cannot be returned
        """
        self.xblock.runtime.anonymous_student_id = None
        with self.assertRaises(LtiError):
            __ = self.xblock.user_id

    def test_resource_link_id(self):
        """
        Test `resource_link_id` returns appropriate string
        """
        self.assertEqual(
            self.xblock.resource_link_id,
            "{}-{}".format(self.xblock.runtime.hostname, self.xblock.location.html_id())  # pylint: disable=no-member
        )

    @patch('lti_consumer.lti_consumer.LtiConsumerXBlock.context_id')
    @patch('lti_consumer.lti_consumer.LtiConsumerXBlock.resource_link_id')
    @patch('lti_consumer.lti_consumer.LtiConsumerXBlock.user_id', PropertyMock(return_value=FAKE_USER_ID))
    def test_lis_result_sourcedid(self, mock_resource_link_id, mock_context_id):
        """
        Test `lis_result_sourcedid` returns appropriate string
        """
        mock_resource_link_id.__get__ = Mock(return_value='resource_link_id')
        mock_context_id.__get__ = Mock(return_value='context_id')

        self.assertEqual(self.xblock.lis_result_sourcedid, "context_id:resource_link_id:{}".format(FAKE_USER_ID))

    def test_outcome_service_url(self):
        """
        Test `outcome_service_url` calls `runtime.handler_url` with thirdparty kwarg
        """
        handler_url = 'http://localhost:8005/outcome_service_handler'
        self.xblock.runtime.handler_url = Mock(return_value="{}/?".format(handler_url))
        url = self.xblock.outcome_service_url

        self.xblock.runtime.handler_url.assert_called_with(self.xblock, 'outcome_service_handler', thirdparty=True)
        self.assertEqual(url, handler_url)

    def test_result_service_url(self):
        """
        Test `result_service_url` calls `runtime.handler_url` with thirdparty kwarg
        """
        handler_url = 'http://localhost:8005/result_service_handler'
        self.xblock.runtime.handler_url = Mock(return_value="{}/?".format(handler_url))
        url = self.xblock.result_service_url

        self.xblock.runtime.handler_url.assert_called_with(self.xblock, 'result_service_handler', thirdparty=True)
        self.assertEqual(url, handler_url)

    def test_prefixed_custom_parameters(self):
        """
        Test `prefixed_custom_parameters` appropriately prefixes the configured custom params
        """
        self.xblock.custom_parameters = ['param_1=true', 'param_2 = false', 'lti_version=1.1']
        params = self.xblock.prefixed_custom_parameters

        self.assertEqual(params, {u'custom_param_1': u'true', u'custom_param_2': u'false', u'lti_version': u'1.1'})

    def test_invalid_custom_parameter(self):
        """
        Test `prefixed_custom_parameters` when a custom parameter has been configured with the wrong format
        """
        self.xblock.custom_parameters = ['param_1=true', 'param_2=false', 'lti_version1.1']

        with self.assertRaises(LtiError):
            __ = self.xblock.prefixed_custom_parameters

    def test_is_past_due_no_due_date(self):
        """
        Test `is_past_due` is False when there is no due date
        """
        self.xblock.due = None
        self.xblock.graceperiod = timedelta(days=1)

        self.assertFalse(self.xblock.is_past_due)

    def test_is_past_due_with_graceperiod(self):
        """
        Test `is_past_due` when a graceperiod has been defined
        """
        now = timezone.now()
        self.xblock.graceperiod = timedelta(days=1)

        self.xblock.due = now
        self.assertFalse(self.xblock.is_past_due)

        self.xblock.due = now - timedelta(days=2)
        self.assertTrue(self.xblock.is_past_due)

    def test_is_past_due_no_graceperiod(self):
        """
        Test `is_past_due` when no graceperiod has been defined
        """
        now = timezone.now()
        self.xblock.graceperiod = None

        self.xblock.due = now - timedelta(days=1)
        self.assertTrue(self.xblock.is_past_due)

        self.xblock.due = now + timedelta(days=1)
        self.assertFalse(self.xblock.is_past_due)

    def test_is_past_due_timezone_now_called(self):
        """
        Test `is_past_due` calls django.utils.timezone.now to get current datetime
        """
        now = timezone.now()
        self.xblock.graceperiod = None
        self.xblock.due = now
        with patch('lti_consumer.lti_consumer.timezone.now', wraps=timezone.now) as mock_timezone_now:
            __ = self.xblock.is_past_due
            self.assertTrue(mock_timezone_now.called)


class TestEditableFields(TestLtiConsumerXBlock):
    """
    Unit tests for LtiConsumerXBlock.editable_fields
    """

    def get_mock_lti_configuration(self, editable):
        """
        Returns a mock object of lti-configuration service

        Arguments:
            editable (bool): This indicates whether the LTI fields (i.e. 'ask_to_send_username' and
            'ask_to_send_email') are editable.
        """
        lti_configuration = Mock()
        lti_configuration.configuration = Mock()
        lti_configuration.configuration.lti_access_to_learners_editable = Mock(
            return_value=editable
        )
        return lti_configuration

    def are_fields_editable(self, fields):
        """
        Returns whether the fields passed in as an argument, are editable.

        Arguments:
            fields (list): list containing LTI Consumer XBlock's field names.
        """
        return all(field in self.xblock.editable_fields for field in fields)

    @patch('lti_consumer.lti_consumer.lti_1p3_enabled', return_value=False)
    def test_editable_fields_with_no_config(self, lti_1p3_enabled_mock):
        """
        Test that LTI XBlock's fields (i.e. 'ask_to_send_username' and 'ask_to_send_email')
        are editable when lti-configuration service is not provided.
        """
        self.xblock.runtime.service.return_value = None
        # Assert that 'ask_to_send_username' and 'ask_to_send_email' are editable.
        self.assertTrue(self.are_fields_editable(fields=['ask_to_send_username', 'ask_to_send_email']))
        lti_1p3_enabled_mock.assert_called()

    @patch('lti_consumer.lti_consumer.lti_1p3_enabled', return_value=False)
    def test_editable_fields_when_editing_allowed(self, lti_1p3_enabled_mock):
        """
        Test that LTI XBlock's fields (i.e. 'ask_to_send_username' and 'ask_to_send_email')
        are editable when this XBlock is configured to allow it.
        """
        # this XBlock is configured to allow editing of LTI fields
        self.xblock.runtime.service.return_value = self.get_mock_lti_configuration(editable=True)
        # Assert that 'ask_to_send_username' and 'ask_to_send_email' are editable.
        self.assertTrue(self.are_fields_editable(fields=['ask_to_send_username', 'ask_to_send_email']))
        lti_1p3_enabled_mock.assert_called()

    @patch('lti_consumer.lti_consumer.lti_1p3_enabled', return_value=False)
    def test_editable_fields_when_editing_not_allowed(self, lti_1p3_enabled_mock):
        """
        Test that LTI XBlock's fields (i.e. 'ask_to_send_username' and 'ask_to_send_email')
        are not editable when this XBlock is configured to not to allow it.
        """
        # this XBlock is configured to not to allow editing of LTI fields
        self.xblock.runtime.service.return_value = self.get_mock_lti_configuration(editable=False)
        # Assert that 'ask_to_send_username' and 'ask_to_send_email' are not editable.
        self.assertFalse(self.are_fields_editable(fields=['ask_to_send_username', 'ask_to_send_email']))
        lti_1p3_enabled_mock.assert_called()

    @patch('lti_consumer.lti_consumer.lti_1p3_enabled', return_value=True)
    def test_lti_1p3_fields_appear_when_enabled(self, lti_1p3_enabled_mock):
        """
        Test that LTI 1.3 XBlock's fields appear when `lti_1p3_enabled` returns True.
        """
        self.assertTrue(
            self.are_fields_editable(
                fields=[
                    'lti_version',
                    'lti_1p3_launch_url',
                    'lti_1p3_oidc_url',
                    'lti_1p3_tool_public_key',
                ]
            )
        )
        lti_1p3_enabled_mock.assert_called()


class TestStudentView(TestLtiConsumerXBlock):
    """
    Unit tests for LtiConsumerXBlock.student_view()
    """

    def test_has_score_false(self):
        """
        Test `has_score` is True
        """
        self.xblock.has_score = False
        fragment = self.xblock.student_view({})

        self.assertNotIn(HTML_PROBLEM_PROGRESS, fragment.content)

    def test_has_score_true(self):
        """
        Test `has_score` is True and `weight` has been configured
        """
        self.xblock.has_score = True
        fragment = self.xblock.student_view({})

        self.assertIn(HTML_PROBLEM_PROGRESS, fragment.content)

    def test_launch_target_iframe(self):
        """
        Test when `launch_target` is iframe
        """
        self.xblock.launch_target = 'iframe'
        fragment = self.xblock.student_view({})

        self.assertNotIn(HTML_LAUNCH_MODAL_BUTTON, fragment.content)
        self.assertNotIn(HTML_LAUNCH_NEW_WINDOW_BUTTON, fragment.content)
        self.assertIn(HTML_IFRAME, fragment.content)

    def test_launch_target_modal(self):
        """
        Test when `launch_target` is modal
        """
        self.xblock.launch_target = 'modal'
        fragment = self.xblock.student_view({})

        self.assertIn(HTML_LAUNCH_MODAL_BUTTON, fragment.content)
        self.assertNotIn(HTML_LAUNCH_NEW_WINDOW_BUTTON, fragment.content)
        self.assertIn(HTML_IFRAME, fragment.content)

    def test_launch_target_new_window(self):
        """
        Test when `launch_target` is iframe
        """
        self.xblock.launch_target = 'new_window'
        fragment = self.xblock.student_view({})

        self.assertIn(HTML_LAUNCH_NEW_WINDOW_BUTTON, fragment.content)
        self.assertNotIn(HTML_LAUNCH_MODAL_BUTTON, fragment.content)
        self.assertNotIn(HTML_IFRAME, fragment.content)

    def test_no_launch_url(self):
        """
        Test `launch_url` has not been configured
        """
        self.xblock.launch_url = ''
        fragment = self.xblock.student_view({})

        self.assertIn(HTML_ERROR_MESSAGE, fragment.content)

    def test_no_launch_url_hide_launch_true(self):
        """
        Test `launch_url` has not been configured and `hide_launch` is True
        """
        self.xblock.launch_url = ''
        self.xblock.hide_launch = True
        fragment = self.xblock.student_view({})

        self.assertNotIn(HTML_ERROR_MESSAGE, fragment.content)

    def test_author_view(self):
        """
        Test that the `author_view` is the same as student view when using LTI 1.1.
        """
        self.assertEqual(
            self.xblock.student_view({}).content,
            self.xblock.author_view({}).content
        )


class TestLtiLaunchHandler(TestLtiConsumerXBlock):
    """
    Unit tests for LtiConsumerXBlock.lti_launch_handler()
    """

    @patch('lti_consumer.lti.LtiConsumer.get_signed_lti_parameters')
    def test_handle_request_called(self, mock_get_signed_lti_parameters):
        """
        Test LtiConsumer.get_signed_lti_parameters is called and a 200 HTML response is returned
        """
        request = make_request('', 'GET')
        response = self.xblock.lti_launch_handler(request)

        assert mock_get_signed_lti_parameters.called
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'text/html')


class TestOutcomeServiceHandler(TestLtiConsumerXBlock):
    """
    Unit tests for LtiConsumerXBlock.outcome_service_handler()
    """

    @patch('lti_consumer.outcomes.OutcomeService.handle_request')
    def test_handle_request_called(self, mock_handle_request):
        """
        Test OutcomeService.handle_request is called and a 200 XML response is returned
        """
        request = make_request('', 'POST')
        response = self.xblock.outcome_service_handler(request)

        assert mock_handle_request.called
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'application/xml')


class TestResultServiceHandler(TestLtiConsumerXBlock):
    """
    Unit tests for LtiConsumerXBlock.result_service_handler()
    """

    def setUp(self):
        super(TestResultServiceHandler, self).setUp()
        self.lti_provider_key = 'test'
        self.lti_provider_secret = 'secret'
        self.xblock.runtime.debug = False
        self.xblock.runtime.get_real_user = Mock()
        self.xblock.accept_grades_past_due = True

    @patch('lti_consumer.lti_consumer.log_authorization_header')
    @patch('lti_consumer.lti_consumer.LtiConsumerXBlock.lti_provider_key_secret')
    def test_runtime_debug_true(self, mock_lti_provider_key_secret, mock_log_auth_header):
        """
        Test `log_authorization_header` is called when runtime.debug is True
        """
        mock_lti_provider_key_secret.__get__ = Mock(return_value=(self.lti_provider_key, self.lti_provider_secret))
        self.xblock.runtime.debug = True
        request = make_request('', 'GET')
        self.xblock.result_service_handler(request)

        mock_log_auth_header.assert_called_with(request, self.lti_provider_key, self.lti_provider_secret)

    @patch('lti_consumer.lti_consumer.log_authorization_header')
    def test_runtime_debug_false(self, mock_log_auth_header):
        """
        Test `log_authorization_header` is not called when runtime.debug is False
        """
        self.xblock.runtime.debug = False
        self.xblock.result_service_handler(make_request('', 'GET'))

        assert not mock_log_auth_header.called

    @patch('lti_consumer.lti_consumer.LtiConsumerXBlock.is_past_due')
    def test_accept_grades_past_due_false_and_is_past_due_true(self, mock_is_past_due):
        """
        Test 404 response returned when `accept_grades_past_due` is False
        and `is_past_due` is True
        """
        mock_is_past_due.__get__ = Mock(return_value=True)
        self.xblock.accept_grades_past_due = False
        response = self.xblock.result_service_handler(make_request('', 'GET'))

        self.assertEqual(response.status_code, 404)

    @patch('lti_consumer.lti.LtiConsumer.get_result')
    @patch('lti_consumer.lti.LtiConsumer.verify_result_headers', Mock(return_value=True))
    @patch('lti_consumer.lti_consumer.parse_handler_suffix')
    @patch('lti_consumer.lti_consumer.LtiConsumerXBlock.is_past_due')
    def test_accept_grades_past_due_true_and_is_past_due_true(self, mock_is_past_due, mock_parse_suffix,
                                                              mock_get_result):
        """
        Test 200 response returned when `accept_grades_past_due` is True and `is_past_due` is True
        """
        mock_is_past_due.__get__ = Mock(return_value=True)
        mock_parse_suffix.return_value = FAKE_USER_ID
        mock_get_result.return_value = {}
        response = self.xblock.result_service_handler(make_request('', 'GET'))

        self.assertEqual(response.status_code, 200)

    @patch('lti_consumer.lti_consumer.parse_handler_suffix')
    def test_parse_suffix_raises_error(self, mock_parse_suffix):
        """
        Test 404 response returned when the user id cannot be parsed from the request path suffix
        """
        mock_parse_suffix.side_effect = LtiError()
        response = self.xblock.result_service_handler(make_request('', 'GET'))

        self.assertEqual(response.status_code, 404)

    @patch('lti_consumer.lti.LtiConsumer.verify_result_headers')
    @patch('lti_consumer.lti_consumer.parse_handler_suffix')
    def test_verify_headers_raises_error(self, mock_parse_suffix, mock_verify_result_headers):
        """
        Test 401 response returned when `verify_result_headers` raises LtiError
        """
        mock_parse_suffix.return_value = FAKE_USER_ID
        mock_verify_result_headers.side_effect = LtiError()
        response = self.xblock.result_service_handler(make_request('', 'GET'))

        self.assertEqual(response.status_code, 401)

    @patch('lti_consumer.lti.LtiConsumer.verify_result_headers', Mock(return_value=True))
    @patch('lti_consumer.lti_consumer.parse_handler_suffix')
    def test_bad_user_id(self, mock_parse_suffix):
        """
        Test 404 response returned when a user cannot be found
        """
        mock_parse_suffix.return_value = FAKE_USER_ID
        self.xblock.runtime.get_real_user.return_value = None
        response = self.xblock.result_service_handler(make_request('', 'GET'))

        self.assertEqual(response.status_code, 404)

    @patch('lti_consumer.lti.LtiConsumer.verify_result_headers', Mock(return_value=True))
    @patch('lti_consumer.lti_consumer.parse_handler_suffix')
    def test_bad_request_method(self, mock_parse_suffix):
        """
        Test 404 response returned when the request contains an unsupported method
        """
        mock_parse_suffix.return_value = FAKE_USER_ID
        response = self.xblock.result_service_handler(make_request('', 'POST'))

        self.assertEqual(response.status_code, 404)

    @patch('lti_consumer.lti.LtiConsumer.get_result')
    @patch('lti_consumer.lti.LtiConsumer.verify_result_headers', Mock(return_value=True))
    @patch('lti_consumer.lti_consumer.parse_handler_suffix')
    def test_get_result_raises_error(self, mock_parse_suffix, mock_get_result):
        """
        Test 404 response returned when the LtiConsumer result service handler methods raise an exception
        """
        mock_parse_suffix.return_value = FAKE_USER_ID
        mock_get_result.side_effect = LtiError()
        response = self.xblock.result_service_handler(make_request('', 'GET'))

        self.assertEqual(response.status_code, 404)

    @patch('lti_consumer.lti.LtiConsumer.get_result')
    @patch('lti_consumer.lti.LtiConsumer.verify_result_headers', Mock(return_value=True))
    @patch('lti_consumer.lti_consumer.parse_handler_suffix')
    def test_get_result_called(self, mock_parse_suffix, mock_get_result):
        """
        Test 200 response and LtiConsumer.get_result is called on a GET request
        """
        mock_parse_suffix.return_value = FAKE_USER_ID
        mock_get_result.return_value = {}
        response = self.xblock.result_service_handler(make_request('', 'GET'))

        assert mock_get_result.called
        self.assertEqual(response.status_code, 200)

    @patch('lti_consumer.lti.LtiConsumer.put_result')
    @patch('lti_consumer.lti.LtiConsumer.verify_result_headers', Mock(return_value=True))
    @patch('lti_consumer.lti_consumer.parse_handler_suffix')
    def test_put_result_called(self, mock_parse_suffix, mock_put_result):
        """
        Test 200 response and LtiConsumer.put_result is called on a PUT request
        """
        mock_parse_suffix.return_value = FAKE_USER_ID
        mock_put_result.return_value = {}
        response = self.xblock.result_service_handler(make_request('', 'PUT'))

        assert mock_put_result.called
        self.assertEqual(response.status_code, 200)

    @patch('lti_consumer.lti.LtiConsumer.delete_result')
    @patch('lti_consumer.lti.LtiConsumer.verify_result_headers', Mock(return_value=True))
    @patch('lti_consumer.lti_consumer.parse_handler_suffix')
    def test_delete_result_called(self, mock_parse_suffix, mock_delete_result):
        """
        Test 200 response and LtiConsumer.delete_result is called on a DELETE request
        """
        mock_parse_suffix.return_value = FAKE_USER_ID
        mock_delete_result.return_value = {}
        response = self.xblock.result_service_handler(make_request('', 'DELETE'))

        assert mock_delete_result.called
        self.assertEqual(response.status_code, 200)

    def test_get_outcome_service_url_with_default_parameter(self):
        """
        Test `get_outcome_service_url` with default parameter
        """
        handler_url = 'http://localhost:8005/outcome_service_handler'
        self.xblock.runtime.handler_url = Mock(return_value="{}/?".format(handler_url))
        url = self.xblock.get_outcome_service_url()

        self.xblock.runtime.handler_url.assert_called_with(self.xblock, 'outcome_service_handler', thirdparty=True)
        self.assertEqual(url, handler_url)

    def test_get_outcome_service_url_with_service_name_grade_handler(self):
        """
        Test `get_outcome_service_url` calls service name grade_handler
        """
        handler_url = 'http://localhost:8005/outcome_service_handler'
        self.xblock.runtime.handler_url = Mock(return_value="{}/?".format(handler_url))
        url = self.xblock.get_outcome_service_url('grade_handler')

        self.xblock.runtime.handler_url.assert_called_with(self.xblock, 'outcome_service_handler', thirdparty=True)
        self.assertEqual(url, handler_url)

    def test_get_outcome_service_url_with_service_name_lti_2_0_result_rest_handler(self):
        """
        Test `get_outcome_service_url` calls with service name lti_2_0_result_rest_handler
        """
        handler_url = 'http://localhost:8005/result_service_handler'
        self.xblock.runtime.handler_url = Mock(return_value="{}/?".format(handler_url))
        url = self.xblock.get_outcome_service_url('lti_2_0_result_rest_handler')

        self.xblock.runtime.handler_url.assert_called_with(self.xblock, 'result_service_handler', thirdparty=True)
        self.assertEqual(url, handler_url)


class TestMaxScore(TestLtiConsumerXBlock):
    """
    Unit tests for LtiConsumerXBlock.max_score()
    """

    def test_max_score_when_scored(self):
        """
        Test `max_score` when has_score is True
        """
        self.xblock.has_score = True
        self.xblock.weight = 1.0

        self.assertEqual(self.xblock.max_score(), 1.0)

    def test_max_score_when_not_scored(self):
        """
        Test `max_score` when has_score is False
        """
        self.xblock.has_score = False
        self.xblock.weight = 1.0

        self.assertIsNone(self.xblock.max_score())


class TestSetScore(TestLtiConsumerXBlock):
    """
    Unit tests for LtiConsumerXBlock.set_user_module_score() and LtiConsumerXBlock.clear_user_module_score()
    """

    def test_rebind_called(self):
        """
        Test that `runtime.rebind_noauth_module_to_user` is called
        """
        user = Mock(user_id=FAKE_USER_ID)
        self.xblock.set_user_module_score(user, 0.92, 1.0, 'Great Job!')

        self.xblock.runtime.rebind_noauth_module_to_user.assert_called_with(self.xblock, user)

    def test_publish_grade_event_called(self):
        """
        Test that `runtime.publish` is called
        """
        user = Mock(id=FAKE_USER_ID)
        score = 0.92
        max_score = 1.0
        self.xblock.set_user_module_score(user, score, max_score)

        self.xblock.runtime.publish.assert_called_with(self.xblock, 'grade', {
            'value': score,
            'max_value': max_score,
            'user_id': FAKE_USER_ID
        })

    def test_score_is_none(self):
        """
        Test when score parameter is None
        """
        max_score = 1.0
        user = Mock(id=FAKE_USER_ID)
        self.xblock.set_user_module_score(user, None, max_score)

        self.assertEqual(self.xblock.module_score, None)

    def test_max_score_is_none(self):
        """
        Test when max_score parameter is None
        """
        user = Mock(id=FAKE_USER_ID)
        self.xblock.set_user_module_score(user, 0.92, None)

        self.assertEqual(self.xblock.module_score, None)

    def test_score_and_max_score_populated(self):
        """
        Test when both score and max_score parameters are not None
        """
        user = Mock(id=FAKE_USER_ID)
        score = 0.92
        max_score = 1.0
        self.xblock.set_user_module_score(user, score, max_score)

        self.assertEqual(self.xblock.module_score, score * max_score)

    def test_no_comment_param(self):
        """
        Test when no comment parameter is passed
        """
        self.xblock.set_user_module_score(Mock(), 0.92, 1.0)

        self.assertEqual(self.xblock.score_comment, '')

    def test_comment_param(self):
        """
        Test when comment parameter is passed
        """
        comment = 'Great Job!'
        self.xblock.set_user_module_score(Mock(), 0.92, 1.0, comment)

        self.assertEqual(self.xblock.score_comment, comment)

    @patch('lti_consumer.LtiConsumerXBlock.set_user_module_score')
    def test_clear_user_module_score(self, mock_set_user_module_score):
        """
        Test that clear_user_module_score calls set_user_module_score with params set to None
        """
        user = Mock()
        self.xblock.clear_user_module_score(user)
        mock_set_user_module_score.assert_called_with(user, None, None)


class TestParseSuffix(TestLtiConsumerXBlock):
    """
    Unit tests for parse_handler_suffix()
    """

    def test_empty_suffix(self):
        """
        Test `parse_handler_suffix` when `suffix` parameter is an empty string
        """
        with self.assertRaises(LtiError):
            parse_handler_suffix("")

    def test_suffix_no_match(self):
        """
        Test `parse_handler_suffix` when `suffix` cannot be parsed
        """
        with self.assertRaises(LtiError):
            parse_handler_suffix("bogus_path/4")

    def test_suffix_match(self):
        """
        Test `parse_handler_suffix` when `suffix` parameter can be parsed
        :return:
        """
        parsed = parse_handler_suffix("user/{}".format(FAKE_USER_ID))
        self.assertEqual(parsed, FAKE_USER_ID)


@ddt.ddt
class TestGetContext(TestLtiConsumerXBlock):
    """
    Unit tests for LtiConsumerXBlock._get_context_for_template()
    """

    @ddt.data('lti_1p1', 'lti_1p3')
    def test_context_keys(self, lti_version):
        """
        Test `_get_context_for_template` returns dict with correct keys
        """
        self.xblock.lti_version = lti_version
        context_keys = (
            'launch_url', 'lti_1p3_launch_url', 'element_id', 'element_class', 'launch_target',
            'display_name', 'form_url', 'hide_launch', 'has_score', 'weight', 'module_score',
            'comment', 'description', 'ask_to_send_username', 'ask_to_send_email', 'button_text',
            'modal_vertical_offset', 'modal_horizontal_offset', 'modal_width',
            'accept_grades_past_due'
        )
        context = self.xblock._get_context_for_template()  # pylint: disable=protected-access

        for key in context_keys:
            self.assertIn(key, context)

    @ddt.data('a', 'abbr', 'acronym', 'b', 'blockquote', 'code', 'em', 'i', 'li', 'ol', 'strong', 'ul', 'img')
    def test_comment_allowed_tags(self, tag):
        """
        Test that allowed tags are not escaped in context['comment']
        """
        comment = u'<{0}>This is a comment</{0}>!'.format(tag)
        self.xblock.set_user_module_score(Mock(), 0.92, 1.0, comment)
        context = self.xblock._get_context_for_template()  # pylint: disable=protected-access

        self.assertIn('<{}>'.format(tag), context['comment'])

    def test_comment_retains_image_src(self):
        """
        Test that image tag has src and other attrs are sanitized
        """
        comment = u'<img src="example.com/image.jpeg" onerror="myFunction()">'
        self.xblock.set_user_module_score(Mock(), 0.92, 1.0, comment)
        context = self.xblock._get_context_for_template()  # pylint: disable=protected-access

        self.assertIn(u'<img src="example.com/image.jpeg">', context['comment'])


@ddt.ddt
class TestProcessorSettings(TestLtiConsumerXBlock):
    """
    Unit tests for the adding custom LTI parameters.
    """
    settings = {
        'parameter_processors': ['lti_consumer.tests.unit.test_utils:dummy_processor']
    }

    def test_no_processors_by_default(self):
        processors = list(self.xblock.get_parameter_processors())
        assert not processors, 'The processor list should empty by default.'

    def test_enable_processor(self):
        self.xblock.enable_processors = True
        with patch('lti_consumer.lti_consumer.LtiConsumerXBlock.get_settings', return_value=self.settings):
            processors = list(self.xblock.get_parameter_processors())
            assert len(processors) == 1, 'One processor should be enabled'
            # pylint: disable=bad-option-value, comparison-with-callable
            assert processors[0] == test_utils.dummy_processor, 'Should load the correct function'

    def test_disabled_processors(self):
        self.xblock.enable_processors = False
        with patch('lti_consumer.lti_consumer.LtiConsumerXBlock.get_settings', return_value=self.settings):
            processors = list(self.xblock.get_parameter_processors())
            assert not processors, 'No processor should be enabled'

    @ddt.data({
        # Bad processor list
        'parameter_processors': False,
    }, {
        # Bad object path, no separator
        'parameter_processors': [
            'zzzzz',
        ],
    }, {
        # Non-existent processor
        'parameter_processors': [
            'lti_consumer.tests.unit.test_utils:non_existent',
        ],
    })
    @patch('lti_consumer.lti_consumer.log')
    def test_faulty_configs(self, settings, mock_log):
        self.xblock.enable_processors = True
        with patch('lti_consumer.lti_consumer.LtiConsumerXBlock.get_settings', return_value=settings):
            with self.assertRaises(Exception):
                list(self.xblock.get_parameter_processors())
            assert mock_log.exception.called


class TestGetModalPositionOffset(TestLtiConsumerXBlock):
    """
    Unit tests for LtiConsumerXBlock._get_modal_position_offset()
    """

    def test_offset_calculation(self):
        """
        Test `_get_modal_position_offset` returns the correct value
        """
        offset = self.xblock._get_modal_position_offset(self.xblock.modal_height)  # pylint: disable=protected-access

        # modal_height defaults to 80, so offset should equal 10
        self.assertEqual(offset, 10)


class TestLtiConsumer1p3XBlock(TestCase):
    """
    Unit tests for LtiConsumerXBlock when using an LTI 1.3 tool.
    """
    def setUp(self):
        super(TestLtiConsumer1p3XBlock, self).setUp()

        self.xblock_attributes = {
            'lti_version': 'lti_1p3',
            'lti_1p3_launch_url': 'http://tool.example/launch',
            'lti_1p3_oidc_url': 'http://tool.example/oidc',
            # We need to set the values below because they are not automatically
            # generated until the user selects `lti_version == 'lti_1p3'` on the
            # Studio configuration view.
            'lti_1p3_client_id': str(uuid.uuid4()),
            'lti_1p3_block_key': RSA.generate(2048).export_key('PEM'),
        }
        self.xblock = make_xblock('lti_consumer', LtiConsumerXBlock, self.xblock_attributes)

    # pylint: disable=unused-argument
    @patch('lti_consumer.utils.get_lms_base', return_value="https://example.com")
    @patch('lti_consumer.lti_consumer.get_lms_base', return_value="https://example.com")
    def test_launch_request(self, mock_url, mock_url_2):
        """
        Test LTI 1.3 launch request
        """
        response = self.xblock.lti_1p3_launch_handler(make_request('', 'GET'))
        self.assertEqual(response.status_code, 200)

        # Check if tool OIDC url is on page
        self.assertIn(
            self.xblock_attributes['lti_1p3_oidc_url'],
            response.body.decode('utf-8')
        )

    # pylint: disable=unused-argument
    @patch('lti_consumer.utils.get_lms_base', return_value="https://example.com")
    @patch('lti_consumer.lti_consumer.get_lms_base', return_value="https://example.com")
    def test_launch_callback_endpoint(self, mock_url, mock_url_2):
        """
        Test that the LTI 1.3 callback endpoind.
        """
        self.xblock.runtime.get_user_role.return_value = 'student'
        mock_user_service = Mock()
        mock_user_service.get_external_user_id.return_value = 2
        self.xblock.runtime.service.return_value = mock_user_service

        # Craft request sent back by LTI tool
        request = make_request('', 'GET')
        request.query_string = (
            "client_id={}&".format(self.xblock_attributes['lti_1p3_client_id']) +
            "redirect_uri=http://tool.example/launch&" +
            "state=state_test_123&" +
            "nonce=nonce&" +
            "login_hint=oidchint"
        )

        response = self.xblock.lti_1p3_launch_callback(request)

        # Check response and assert that state was inserted
        self.assertEqual(response.status_code, 200)

        response_body = response.body.decode('utf-8')
        self.assertIn("state", response_body)
        self.assertIn("state_test_123", response_body)

    # pylint: disable=unused-argument
    @patch('lti_consumer.utils.get_lms_base', return_value="https://example.com")
    @patch('lti_consumer.lti_consumer.get_lms_base', return_value="https://example.com")
    def test_launch_callback_endpoint_fails(self, mock_url, mock_url_2):
        """
        Test that the LTI 1.3 callback endpoint correctly display an error message.
        """
        self.xblock.runtime.get_user_role.return_value = 'student'
        mock_user_service = Mock()
        mock_user_service.get_external_user_id.return_value = 2
        self.xblock.runtime.service.return_value = mock_user_service

        # Make a fake invalid preflight request, with empty parameters
        request = make_request('', 'GET')
        response = self.xblock.lti_1p3_launch_callback(request)

        # Check response and assert that state was inserted
        self.assertEqual(response.status_code, 400)

        response_body = response.body.decode('utf-8')
        self.assertIn("There was an error launching the LTI 1.3 tool.", response_body)

    def test_launch_callback_endpoint_when_using_lti_1p1(self):
        """
        Test that the LTI 1.3 callback endpoind is unavailable when using 1.1.
        """
        self.xblock.lti_version = 'lti_1p1'
        self.xblock.save()
        response = self.xblock.lti_1p3_launch_callback(make_request('', 'GET'))
        self.assertEqual(response.status_code, 404)

    # pylint: disable=unused-argument
    @patch('lti_consumer.utils.get_lms_base', return_value="https://example.com")
    @patch('lti_consumer.lti_consumer.get_lms_base', return_value="https://example.com")
    def test_keyset_endpoint(self, mock_url, mock_url_2):
        """
        Test that the LTI 1.3 keyset endpoind.
        """
        response = self.xblock.public_keyset_endpoint(make_request('', 'GET'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'application/json')
        self.assertEqual(response.content_disposition, 'attachment; filename=keyset.json')

    def test_keyset_endpoint_when_using_lti_1p1(self):
        """
        Test that the LTI 1.3 keyset endpoind is unavailable when using 1.1.
        """
        self.xblock.lti_version = 'lti_1p1'
        self.xblock.save()

        response = self.xblock.public_keyset_endpoint(make_request('', 'GET'))
        self.assertEqual(response.status_code, 404)

    @patch('lti_consumer.lti_consumer.lti_1p3_enabled', return_value=True)
    def test_studio_view(self, mock_lti_1p3_flag):
        """
        Test that the studio settings view load the custom js.
        """
        response = self.xblock.studio_view({})
        self.assertEqual(response.js_init_fn, 'LtiConsumerXBlockInitStudio')

    @patch('lti_consumer.lti_consumer.RSA')
    @patch('lti_consumer.lti_consumer.uuid')
    def test_clean_studio_edits(self, mock_uuid, mock_rsa):
        """
        Test that the clean studio edits function properly sets LTI 1.3 variables.
        """
        data = {'lti_version': 'lti_1p3'}
        # Setup mocks
        mock_uuid.uuid4.return_value = 'generated_uuid'
        mock_rsa.generate().export_key.return_value = 'generated_rsa_key'

        # Test that values are not overwriten if already present
        self.xblock.clean_studio_edits(data)
        self.assertEqual(data, {'lti_version': 'lti_1p3'})

        # Set empty variables to allow automatic generation
        self.xblock.lti_1p3_client_id = ''
        self.xblock.lti_1p3_block_key = ''
        self.xblock.save()

        # Check that variables are generated if empty
        self.xblock.clean_studio_edits(data)
        self.assertEqual(
            data,
            {
                'lti_version': 'lti_1p3',
                'lti_1p3_client_id': 'generated_uuid',
                'lti_1p3_block_key': 'generated_rsa_key'
            }
        )

    # pylint: disable=unused-argument
    @patch('lti_consumer.utils.get_lms_base', return_value="https://example.com")
    @patch('lti_consumer.lti_consumer.get_lms_base', return_value="https://example.com")
    def test_author_view(self, mock_url, mock_url_2):
        """
        Test that the studio view loads LTI 1.3 view.
        """
        response = self.xblock.author_view({})
        self.assertIn(self.xblock.lti_1p3_client_id, response.content)
        self.assertIn("https://example.com", response.content)


# pylint: disable=unused-argument
@patch('lti_consumer.utils.get_lms_base', return_value="https://example.com")
@patch('lti_consumer.lti_consumer.get_lms_base', return_value="https://example.com")
class TestLti1p3AccessTokenEndpoint(TestCase):
    """
    Unit tests for LtiConsumerXBlock Access Token endpoint when using an LTI 1.3.
    """
    def setUp(self):
        super(TestLti1p3AccessTokenEndpoint, self).setUp()

        self.rsa_key_id = "1"
        # Generate RSA and save exports
        rsa_key = RSA.generate(2048)
        self.key = RSAKey(
            key=rsa_key,
            kid=self.rsa_key_id
        )
        self.public_key = rsa_key.publickey().export_key()

        self.xblock_attributes = {
            'lti_version': 'lti_1p3',
            'lti_1p3_launch_url': 'http://tool.example/launch',
            'lti_1p3_oidc_url': 'http://tool.example/oidc',
            # We need to set the values below because they are not automatically
            # generated until the user selects `lti_version == 'lti_1p3'` on the
            # Studio configuration view.
            'lti_1p3_client_id': self.rsa_key_id,
            'lti_1p3_block_key': rsa_key.export_key('PEM'),
            # Use same key for tool key to make testing easier
            'lti_1p3_tool_public_key': self.public_key,
        }
        self.xblock = make_xblock('lti_consumer', LtiConsumerXBlock, self.xblock_attributes)

    def test_access_token_endpoint_when_using_lti_1p1(self, *args, **kwargs):
        """
        Test that the LTI 1.3 access token endpoind is unavailable when using 1.1.
        """
        self.xblock.lti_version = 'lti_1p1'
        self.xblock.save()

        request = make_request(json.dumps({}), 'POST')
        request.content_type = 'application/json'

        response = self.xblock.lti_1p3_access_token(request)
        self.assertEqual(response.status_code, 404)

    def test_access_token_endpoint_no_post(self, *args, **kwargs):
        """
        Test that the LTI 1.3 access token endpoind is unavailable when using 1.1.
        """
        request = make_request('', 'GET')

        response = self.xblock.lti_1p3_access_token(request)
        self.assertEqual(response.status_code, 405)

    def test_access_token_missing_claims(self, *args, **kwargs):
        """
        Test request with missing parameters.
        """
        request = make_request(json.dumps({}), 'POST')
        request.content_type = 'application/json'

        response = self.xblock.lti_1p3_access_token(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json_body, {'error': 'invalid_request'})

    def test_access_token_malformed(self, *args, **kwargs):
        """
        Test request with invalid JWT.
        """
        request = make_request(
            parse.urlencode({
                "grant_type": "client_credentials",
                "client_assertion_type": "something",
                "client_assertion": "invalid-jwt",
                "scope": "",
            }),
            'POST'
        )
        request.content_type = 'application/x-www-form-urlencoded'

        response = self.xblock.lti_1p3_access_token(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json_body, {'error': 'invalid_grant'})

    def test_access_token_invalid_grant(self, *args, **kwargs):
        """
        Test request with invalid grant.
        """
        request = make_request(
            parse.urlencode({
                "grant_type": "password",
                "client_assertion_type": "something",
                "client_assertion": "invalit-jwt",
                "scope": "",
            }),
            'POST'
        )
        request.content_type = 'application/x-www-form-urlencoded'

        response = self.xblock.lti_1p3_access_token(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json_body, {'error': 'unsupported_grant_type'})

    def test_access_token_invalid_client(self, *args, **kwargs):
        """
        Test request with valid JWT but no matching key to check signature.
        """
        self.xblock.lti_1p3_tool_public_key = ''
        self.xblock.save()

        jwt = create_jwt(self.key, {})
        request = make_request(
            parse.urlencode({
                "grant_type": "client_credentials",
                "client_assertion_type": "something",
                "client_assertion": jwt,
                "scope": "",
            }),
            'POST'
        )
        request.content_type = 'application/x-www-form-urlencoded'

        response = self.xblock.lti_1p3_access_token(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json_body, {'error': 'invalid_client'})

    def test_access_token(self, *args, **kwargs):
        """
        Test request with valid JWT.
        """
        jwt = create_jwt(self.key, {})
        request = make_request(
            parse.urlencode({
                "grant_type": "client_credentials",
                "client_assertion_type": "something",
                "client_assertion": jwt,
                "scope": "",
            }),
            'POST'
        )
        request.content_type = 'application/x-www-form-urlencoded'

        response = self.xblock.lti_1p3_access_token(request)
        self.assertEqual(response.status_code, 200)
