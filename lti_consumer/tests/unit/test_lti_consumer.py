"""
Unit tests for LtiConsumerXBlock
"""

import unittest

from datetime import timedelta
from mock import Mock, PropertyMock, patch

from django.utils import timezone

from lti_consumer.tests.unit.test_utils import FAKE_USER_ID, make_xblock, make_request

from lti_consumer.lti_consumer import LtiConsumerXBlock, parse_handler_suffix
from lti_consumer.exceptions import LtiError


HTML_PROBLEM_PROGRESS = '<div class="problem-progress">'
HTML_ERROR_MESSAGE = '<h3 class="error_message">'
HTML_LAUNCH_MODAL_BUTTON = 'btn-lti-modal'
HTML_LAUNCH_NEW_WINDOW_BUTTON = 'btn-lti-new-window'
HTML_IFRAME = '<iframe'


class TestLtiConsumerXBlock(unittest.TestCase):
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

    def test_context_id(self):
        """
        Test `context_id` returns unicode course id
        """
        self.assertEqual(self.xblock.context_id, unicode(self.xblock.course_id))  # pylint: disable=no-member

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
            __, __ = self.xblock.lti_provider_key_secret

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

    @patch('lti_consumer.lti_consumer.timezone.now')
    def test_is_past_due_timezone_now_called(self, mock_timezone_now):
        """
        Test `is_past_due` calls django.utils.timezone.now to get current datetime
        """
        now = timezone.now()
        self.xblock.graceperiod = None
        self.xblock.due = now
        mock_timezone_now.return_value = now

        __ = self.xblock.is_past_due
        self.assertTrue(mock_timezone_now.called)


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


class TestGetContext(TestLtiConsumerXBlock):
    """
    Unit tests for LtiConsumerXBlock._get_context_for_template()
    """

    def test_context_keys(self):
        """
        Test `_get_context_for_template` returns dict with correct keys
        """
        context_keys = (
            'launch_url', 'element_id', 'element_class', 'launch_target', 'display_name', 'form_url', 'hide_launch',
            'has_score', 'weight', 'module_score', 'comment', 'description', 'ask_to_send_username',
            'ask_to_send_email', 'button_text', 'modal_vertical_offset', 'modal_horizontal_offset', 'modal_width',
            'accept_grades_past_due'
        )
        context = self.xblock._get_context_for_template()  # pylint: disable=protected-access

        for key in context_keys:
            self.assertIn(key, context)


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
