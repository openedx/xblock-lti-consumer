"""
Unit tests for LtiConsumerXBlock
"""

import json
import logging
from datetime import timedelta
from unittest.mock import Mock, PropertyMock, patch

import ddt
from Cryptodome.PublicKey import RSA
from django.conf import settings as dj_settings
from django.test import override_settings
from django.test.testcases import TestCase
from django.utils import timezone
from jwkest.jwk import RSAKey, KEYS

from lti_consumer.api import get_lti_1p3_launch_info
from lti_consumer.exceptions import LtiError
from lti_consumer.lti_1p3.tests.utils import create_jwt
from lti_consumer.lti_xblock import LtiConsumerXBlock, parse_handler_suffix
from lti_consumer.tests.unit import test_utils
from lti_consumer.tests.unit.test_utils import FAKE_USER_ID, make_jwt_request, make_request, make_xblock
from lti_consumer.utils import resolve_custom_parameter_template

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
        super().setUp()
        self.xblock_attributes = {
            'launch_url': 'http://www.example.com',
        }
        self.xblock = make_xblock('lti_consumer', LtiConsumerXBlock, self.xblock_attributes)


class TestIndexibility(TestCase):
    """
    Test indexibility of Lti Consumer XBlock
    """
    def setUp(self):
        super().setUp()
        self.xblock_attributes = {
            'launch_url': 'http://www.example.com',
            'display_name': 'Example LTI Consumer Application',
            'description': 'An example application to demonstrate LTI Consumer'
        }
        self.xblock = make_xblock('lti_consumer', LtiConsumerXBlock, self.xblock_attributes)

    def test_indexibility(self):
        self.assertEqual(
            self.xblock.index_dictionary(),
            {
                'content_type': 'LTI Consumer',
                'content': {
                    'display_name': 'Example LTI Consumer Application',
                    'description': 'An example application to demonstrate LTI Consumer'
                }
            }
        )


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
        self.assertEqual(self.xblock.context_id, str(self.xblock.course_id))

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
        fake_user = Mock()
        fake_user.opt_attrs = {
            'edx-platform.user_role': 'student'
        }
        self.xblock.runtime.service(self, 'user').get_current_user = Mock(return_value=fake_user)
        self.assertEqual(self.xblock.role, 'Student,Learner')

        fake_user.opt_attrs = {
            'edx-platform.user_role': 'guest'
        }
        self.xblock.runtime.service(self, 'user').get_current_user = Mock(return_value=fake_user)
        self.assertEqual(self.xblock.role, 'Student,Learner')

        fake_user.opt_attrs = {
            'edx-platform.user_role': 'staff'
        }
        self.xblock.runtime.service(self, 'user').get_current_user = Mock(return_value=fake_user)
        self.assertEqual(self.xblock.role, 'Administrator')

        fake_user.opt_attrs = {
            'edx-platform.user_role': 'instructor'
        }
        self.xblock.runtime.service(self, 'user').get_current_user = Mock(return_value=fake_user)
        self.assertEqual(self.xblock.role, 'Instructor')

    def test_course(self):
        """
        Test `course` calls modulestore.get_course
        """
        mock_get_course = self.xblock.runtime.modulestore.get_course
        mock_get_course.return_value = None
        course = self.xblock.course

        self.assertTrue(mock_get_course.called)
        self.assertIsNone(course)

    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.course')
    def test_lti_provider_key_secret(self, mock_course):
        """
        Test `lti_provider_key_secret` returns correct key and secret
        """
        provider = 'lti_provider'
        key = 'test'
        secret = 'secret'
        self.xblock.lti_id = provider
        type(mock_course).lti_passports = PropertyMock(return_value=[f"{provider}:{key}:{secret}"])
        lti_provider_key, lti_provider_secret = self.xblock.lti_provider_key_secret

        self.assertEqual(lti_provider_key, key)
        self.assertEqual(lti_provider_secret, secret)

    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.course')
    def test_lti_provider_key_with_extra_colons(self, mock_course):
        """
        Test `lti_provider_key` returns correct key and secret, even if key has more colons.
        """
        provider = 'lti_provider'
        key = '1:10:test'
        secret = 'secret'
        self.xblock.lti_id = provider
        type(mock_course).lti_passports = PropertyMock(return_value=[f"{provider}:{key}:{secret}"])
        lti_provider_key, lti_provider_secret = self.xblock.lti_provider_key_secret

        self.assertEqual(lti_provider_key, key)
        self.assertEqual(lti_provider_secret, secret)

    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.course')
    def test_lti_provider_key_secret_not_found(self, mock_course):
        """
        Test `lti_provider_key_secret` returns correct key and secret
        """
        provider = 'lti_provider'
        key = 'test'
        secret = 'secret'
        self.xblock.lti_id = 'wrong_provider'
        type(mock_course).lti_passports = PropertyMock(return_value=[f"{provider}:{key}:{secret}"])
        lti_provider_key, lti_provider_secret = self.xblock.lti_provider_key_secret

        self.assertEqual(lti_provider_key, '')
        self.assertEqual(lti_provider_secret, '')

    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.course')
    def test_lti_provider_key_secret_corrupt_lti_passport(self, mock_course):
        """
        Test `lti_provider_key_secret` when a corrupt lti_passport is encountered
        """
        provider = 'lti_provider'
        key = 'test'
        secret = 'secret'
        self.xblock.lti_id = provider
        type(mock_course).lti_passports = PropertyMock(return_value=[f"{provider}{key}{secret}"])

        with self.assertRaises(LtiError):
            _, _ = self.xblock.lti_provider_key_secret

    def test_user_id(self):
        """
        Test `user_id` returns the user_id string
        """
        fake_user = Mock()
        fake_user.opt_attrs = {
            'edx-platform.anonymous_user_id': FAKE_USER_ID
        }

        self.xblock.runtime.service(self, 'user').get_current_user = Mock(return_value=fake_user)
        self.assertEqual(self.xblock.user_id, FAKE_USER_ID)

    def test_user_id_none(self):
        """
        Test `user_id` raises LtiError when the user id cannot be returned
        """
        fake_user = Mock()
        fake_user.opt_attrs = {
            'edx-platform.anonymous_user_id': None
        }

        self.xblock.runtime.service(self, 'user').get_current_user = Mock(return_value=fake_user)

        with self.assertRaises(LtiError):
            __ = self.xblock.user_id

    def test_resource_link_id(self):
        """
        Test `resource_link_id` returns appropriate string
        """
        self.assertEqual(
            self.xblock.resource_link_id,
            f"{self.xblock.runtime.hostname}-{self.xblock.location.html_id()}"
        )

    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.context_id')
    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.resource_link_id')
    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.user_id', PropertyMock(return_value=FAKE_USER_ID))
    def test_lis_result_sourcedid(self, mock_resource_link_id, mock_context_id):
        """
        Test `lis_result_sourcedid` returns appropriate string
        """
        mock_resource_link_id.__get__ = Mock(return_value='resource_link_id')
        mock_context_id.__get__ = Mock(return_value='context_id')

        self.assertEqual(self.xblock.lis_result_sourcedid, f"context_id:resource_link_id:{FAKE_USER_ID}")

    def test_outcome_service_url(self):
        """
        Test `outcome_service_url` calls `runtime.handler_url` with thirdparty kwarg
        """
        handler_url = 'http://localhost:8005/outcome_service_handler'
        self.xblock.runtime.handler_url = Mock(return_value=f"{handler_url}/?")
        url = self.xblock.outcome_service_url

        self.xblock.runtime.handler_url.assert_called_with(self.xblock, 'outcome_service_handler', thirdparty=True)
        self.assertEqual(url, handler_url)

    def test_result_service_url(self):
        """
        Test `result_service_url` calls `runtime.handler_url` with thirdparty kwarg
        """
        handler_url = 'http://localhost:8005/result_service_handler'
        self.xblock.runtime.handler_url = Mock(return_value=f"{handler_url}/?")
        url = self.xblock.result_service_url

        self.xblock.runtime.handler_url.assert_called_with(self.xblock, 'result_service_handler', thirdparty=True)
        self.assertEqual(url, handler_url)

    def test_prefixed_custom_parameters(self):
        """
        Test `prefixed_custom_parameters` appropriately prefixes the configured custom params
        """
        now = timezone.now()
        one_day = timedelta(days=1)
        self.xblock.due = now
        self.xblock.graceperiod = one_day

        self.xblock.custom_parameters = ['param_1=true', 'param_2 = false', 'lti_version=1.1']

        expected_params = {
            'custom_component_display_name': self.xblock.display_name,
            'custom_component_due_date': now.strftime('%Y-%m-%d %H:%M:%S'),
            'custom_component_graceperiod': str(one_day.total_seconds()),
            'custom_param_1': 'true',
            'custom_param_2': 'false',
            'lti_version': '1.1'
        }

        params = self.xblock.prefixed_custom_parameters

        self.assertEqual(params, expected_params)

    @patch('lti_consumer.lti_xblock.resolve_custom_parameter_template')
    def test_templated_custom_parameters(self, mock_resolve_custom_parameter_template):
        """
        Test `prefixed_custom_parameters` when a custom parameter with templated value has been provided.
        """
        now = timezone.now()
        one_day = timedelta(days=1)
        self.xblock.due = now
        self.xblock.graceperiod = one_day
        self.xblock.custom_parameters = ['dynamic_param_1=${template_value}', 'param_2=false']
        mock_resolve_custom_parameter_template.return_value = 'resolved_template_value'
        expected_params = {
            'custom_component_display_name': self.xblock.display_name,
            'custom_component_due_date': now.strftime('%Y-%m-%d %H:%M:%S'),
            'custom_component_graceperiod': str(one_day.total_seconds()),
            'custom_dynamic_param_1': 'resolved_template_value',
            'custom_param_2': 'false',
        }

        params = self.xblock.prefixed_custom_parameters

        self.assertEqual(params, expected_params)
        mock_resolve_custom_parameter_template.assert_called_once_with(self.xblock, '${template_value}')

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

        self.assertFalse(self.xblock.is_past_due())

    def test_is_past_due_with_graceperiod(self):
        """
        Test `is_past_due` when a graceperiod has been defined
        """
        now = timezone.now()
        self.xblock.graceperiod = timedelta(days=1)

        self.xblock.due = now
        self.assertFalse(self.xblock.is_past_due())

        self.xblock.due = now - timedelta(days=2)
        self.assertTrue(self.xblock.is_past_due())

    def test_is_past_due_no_graceperiod(self):
        """
        Test `is_past_due` when no graceperiod has been defined
        """
        now = timezone.now()
        self.xblock.graceperiod = None

        self.xblock.due = now - timedelta(days=1)
        self.assertTrue(self.xblock.is_past_due())

        self.xblock.due = now + timedelta(days=1)
        self.assertFalse(self.xblock.is_past_due())

    def test_is_past_due_timezone_now_called(self):
        """
        Test `is_past_due` calls django.utils.timezone.now to get current datetime
        """
        now = timezone.now()
        self.xblock.graceperiod = None
        self.xblock.due = now
        with patch('lti_consumer.lti_xblock.timezone.now', wraps=timezone.now) as mock_timezone_now:
            __ = self.xblock.is_past_due()
            self.assertTrue(mock_timezone_now.called)


class TestEditableFields(TestLtiConsumerXBlock):
    """
    Unit tests for LtiConsumerXBlock.editable_fields
    """

    def setUp(self):
        super().setUp()
        self.waffle_patch = patch('lti_consumer.lti_xblock.external_config_filter_enabled')
        self.mock_flag = self.waffle_patch.start()

    def tearDown(self):
        self.waffle_patch.stop()
        super().tearDown()

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

    def test_editable_fields_with_no_config(self):
        """
        Test that LTI XBlock's fields (i.e. 'ask_to_send_username' and 'ask_to_send_email')
        are editable when lti-configuration service is not provided.
        """
        self.xblock.runtime.service.return_value = None
        # Assert that 'ask_to_send_username' and 'ask_to_send_email' are editable.
        self.assertTrue(self.are_fields_editable(fields=['ask_to_send_username', 'ask_to_send_email']))

    def test_editable_fields_when_editing_allowed(self):
        """
        Test that LTI XBlock's fields (i.e. 'ask_to_send_username' and 'ask_to_send_email')
        are editable when this XBlock is configured to allow it.
        """
        # this XBlock is configured to allow editing of LTI fields
        self.xblock.runtime.service.return_value = self.get_mock_lti_configuration(editable=True)
        # Assert that 'ask_to_send_username' and 'ask_to_send_email' are editable.
        self.assertTrue(self.are_fields_editable(fields=['ask_to_send_username', 'ask_to_send_email']))

    def test_editable_fields_when_editing_not_allowed(self):
        """
        Test that LTI XBlock's fields (i.e. 'ask_to_send_username' and 'ask_to_send_email')
        are not editable when this XBlock is configured to not to allow it.
        """
        # this XBlock is configured to not to allow editing of LTI fields
        self.xblock.runtime.service.return_value = self.get_mock_lti_configuration(editable=False)
        # Assert that 'ask_to_send_username' and 'ask_to_send_email' are not editable.
        self.assertFalse(self.are_fields_editable(fields=['ask_to_send_username', 'ask_to_send_email']))

    def test_lti_1p3_fields_appear(self):
        """
        Test that LTI 1.3 XBlock's fields appear when `lti_1p3_enabled` returns True.
        """
        self.assertTrue(
            self.are_fields_editable(
                fields=[
                    'lti_version',
                    'lti_1p3_launch_url',
                    'lti_1p3_oidc_url',
                    'lti_1p3_tool_key_mode',
                    'lti_1p3_tool_keyset_url',
                    'lti_1p3_tool_public_key',
                    'lti_advantage_deep_linking_enabled',
                    'lti_advantage_deep_linking_launch_url',
                    'lti_1p3_enable_nrps'
                ]
            )
        )

    def test_external_config_fields_are_editable_only_when_waffle_flag_is_set(self):
        """
        Test that the external configuration fields are editable only when the waffle flag is set.
        """
        self.mock_flag.return_value = True
        self.assertTrue(self.are_fields_editable(fields=['config_type', 'external_config']))

        self.mock_flag.return_value = False
        self.assertFalse(self.are_fields_editable(fields=['config_type', 'external_config']))


class TestGetLti1p1Consumer(TestLtiConsumerXBlock):
    """
    Unit tests for LtiConsumerXBlock._get_lti_consumer()
    """
    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.course')
    @patch('lti_consumer.models.LtiConsumer1p1')
    def test_lti_1p1_consumer_created(self, mock_lti_consumer, mock_course):
        """
        Test LtiConsumer1p1 is created with the launch_url, oauth_key, and oauth_secret
        """
        provider = 'lti_provider'
        key = 'test'
        secret = 'secret'
        self.xblock.lti_id = provider
        self.xblock.location = 'block-v1:course+test+2020+type@problem+block@test'
        type(mock_course).lti_passports = PropertyMock(return_value=[f"{provider}:{key}:{secret}"])

        with patch('lti_consumer.models.LtiConfiguration.block', return_value=self.xblock):
            self.xblock._get_lti_consumer()  # pylint: disable=protected-access

        mock_lti_consumer.assert_called_with(self.xblock.launch_url, key, secret)


class TestExtractRealUserData(TestLtiConsumerXBlock):
    """
    Unit tests for LtiConsumerXBlock.extract_real_user_data()
    """

    def test_get_real_user_callable(self):
        """
        Test user_email, and user_username available, but not user_language
        See also documentation of new user service:
        https://github.com/openedx/XBlock/blob/master/xblock/reference/user_service.py
        """
        fake_user = Mock()
        fake_user_email = 'abc@example.com'
        fake_user.emails = [fake_user_email]
        fake_username = 'fake'
        fake_user.opt_attrs = {
            "edx-platform.username": fake_username
        }

        self.xblock.runtime.service(self, 'user').get_current_user = Mock(return_value=fake_user)

        real_user_data = self.xblock.extract_real_user_data()
        self.assertEqual(real_user_data['user_email'], fake_user_email)
        self.assertEqual(real_user_data['user_username'], fake_username)
        self.assertIsNone(real_user_data['user_language'])

    def test_get_real_user_callable_with_language_preference(self):
        """
        Test user_language available
        See also documentation of new user service:
        https://github.com/openedx/XBlock/blob/master/xblock/reference/user_service.py
        """
        fake_user = Mock()
        fake_user.emails = ['abc@example.com']
        fake_user.full_name = 'fake'
        pref_language = "en"
        fake_user.opt_attrs = {
            "edx-platform.user_preferences": {
                "pref-lang": "en"
            }
        }

        self.xblock.runtime.service(self, 'user').get_current_user = Mock(return_value=fake_user)

        real_user_data = self.xblock.extract_real_user_data()
        self.assertEqual(real_user_data['user_language'], pref_language)


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

    def setUp(self):
        super().setUp()
        self.mock_lti_consumer = Mock(generate_launch_request=Mock(return_value={}))
        self.xblock._get_lti_consumer = Mock(return_value=self.mock_lti_consumer)  # pylint: disable=protected-access
        self.xblock.due = timezone.now()
        self.xblock.graceperiod = timedelta(days=1)

        fake_user = Mock()
        fake_user_email = 'abc@example.com'
        fake_user.emails = [fake_user_email]
        fake_username = 'fake'
        fake_user.opt_attrs = {
            "edx-platform.username": fake_username
        }

        self.xblock.runtime.service(self, 'user').get_current_user = Mock(return_value=fake_user)

    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.course')
    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.user_id', PropertyMock(return_value=FAKE_USER_ID))
    def test_generate_launch_request_called(self, mock_course):
        """
        Test LtiConsumer.generate_launch_request is called and a 200 HTML response is returned
        """
        provider = 'lti_provider'
        key = 'test'
        secret = 'secret'
        type(mock_course).lti_passports = PropertyMock(return_value=[f"{provider}:{key}:{secret}"])

        request = make_request('', 'GET')
        response = self.xblock.lti_launch_handler(request)

        self.mock_lti_consumer.generate_launch_request.assert_called_with(self.xblock.resource_link_id)
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
        super().setUp()
        self.lti_provider_key = 'test'
        self.lti_provider_secret = 'secret'
        self.xblock.runtime.get_real_user = Mock()
        self.xblock.accept_grades_past_due = True
        self.mock_lti_consumer = Mock()
        self.xblock._get_lti_consumer = Mock(return_value=self.mock_lti_consumer)  # pylint: disable=protected-access

    @override_settings(DEBUG=True)
    @patch('lti_consumer.lti_xblock.log_authorization_header')
    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.lti_provider_key_secret')
    def test_runtime_debug_true(self, mock_lti_provider_key_secret, mock_log_auth_header):
        """
        Test `log_authorization_header` is called when settings.DEBUG is True
        """
        mock_lti_provider_key_secret.__get__ = Mock(return_value=(self.lti_provider_key, self.lti_provider_secret))
        request = make_request('', 'GET')
        self.xblock.result_service_handler(request)

        mock_log_auth_header.assert_called_with(request, self.lti_provider_key, self.lti_provider_secret)

    @patch('lti_consumer.lti_xblock.log_authorization_header')
    def test_runtime_debug_false(self, mock_log_auth_header):
        """
        Test `log_authorization_header` is not called when settings.DEBUG is False
        """
        self.xblock.result_service_handler(make_request('', 'GET'))

        assert not mock_log_auth_header.called

    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.is_past_due')
    def test_accept_grades_past_due_false_and_is_past_due_true(self, mock_is_past_due):
        """
        Test 404 response returned when `accept_grades_past_due` is False
        and `is_past_due` is True
        """
        mock_is_past_due.return_value = True
        self.xblock.accept_grades_past_due = False
        response = self.xblock.result_service_handler(make_request('', 'GET'))

        self.assertEqual(response.status_code, 404)

    @patch('lti_consumer.lti_1p1.consumer.LtiConsumer1p1.verify_result_headers', Mock(return_value=True))
    @patch('lti_consumer.lti_xblock.parse_handler_suffix')
    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.is_past_due')
    def test_accept_grades_past_due_true_and_is_past_due_true(self, mock_is_past_due, mock_parse_suffix):
        """
        Test 200 response returned when `accept_grades_past_due` is True and `is_past_due` is True
        """
        mock_is_past_due.return_value = True
        mock_parse_suffix.return_value = FAKE_USER_ID
        self.mock_lti_consumer.get_result.return_value = {}
        response = self.xblock.result_service_handler(make_request('', 'GET'))

        self.assertEqual(response.status_code, 200)

    @patch('lti_consumer.lti_xblock.parse_handler_suffix')
    def test_parse_suffix_raises_error(self, mock_parse_suffix):
        """
        Test 404 response returned when the user id cannot be parsed from the request path suffix
        """
        mock_parse_suffix.side_effect = LtiError()
        response = self.xblock.result_service_handler(make_request('', 'GET'))

        self.assertEqual(response.status_code, 404)

    @patch('lti_consumer.lti_xblock.parse_handler_suffix')
    def test_verify_headers_raises_error(self, mock_parse_suffix):
        """
        Test 401 response returned when `verify_result_headers` raises LtiError
        """
        mock_parse_suffix.return_value = FAKE_USER_ID
        self.mock_lti_consumer.verify_result_headers.side_effect = LtiError()
        response = self.xblock.result_service_handler(make_request('', 'GET'))

        self.assertEqual(response.status_code, 401)

    @patch('lti_consumer.lti_1p1.consumer.LtiConsumer1p1.verify_result_headers', Mock(return_value=True))
    @patch('lti_consumer.lti_xblock.parse_handler_suffix')
    def test_bad_user_id(self, mock_parse_suffix):
        """
        Test 404 response returned when a user cannot be found
        """
        mock_parse_suffix.return_value = FAKE_USER_ID
        self.xblock.runtime.get_real_user.return_value = None
        response = self.xblock.result_service_handler(make_request('', 'GET'))

        self.assertEqual(response.status_code, 404)

    @patch('lti_consumer.lti_1p1.consumer.LtiConsumer1p1.verify_result_headers', Mock(return_value=True))
    @patch('lti_consumer.lti_xblock.parse_handler_suffix')
    def test_bad_request_method(self, mock_parse_suffix):
        """
        Test 404 response returned when the request contains an unsupported method
        """
        mock_parse_suffix.return_value = FAKE_USER_ID
        response = self.xblock.result_service_handler(make_request('', 'POST'))

        self.assertEqual(response.status_code, 404)

    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock._result_service_get')
    @patch('lti_consumer.lti_1p1.consumer.LtiConsumer1p1.verify_result_headers', Mock(return_value=True))
    @patch('lti_consumer.lti_xblock.parse_handler_suffix')
    def test_get_result_raises_error(self, mock_parse_suffix, mock_result_service_get):
        """
        Test 404 response returned when the LtiConsumerXBlock._result_service_* methods raise an exception
        """
        mock_parse_suffix.return_value = FAKE_USER_ID
        mock_result_service_get.side_effect = LtiError()
        response = self.xblock.result_service_handler(make_request('', 'GET'))

        self.assertEqual(response.status_code, 404)

    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock._result_service_get')
    @patch('lti_consumer.lti_1p1.consumer.LtiConsumer1p1.verify_result_headers', Mock(return_value=True))
    @patch('lti_consumer.lti_xblock.parse_handler_suffix')
    def test_result_service_get_called(self, mock_parse_suffix, mock_result_service_get):
        """
        Test 200 response and LtiConsumerXBlock._result_service_get is called on a GET request
        """
        mock_parse_suffix.return_value = FAKE_USER_ID
        mock_result_service_get.return_value = {}
        response = self.xblock.result_service_handler(make_request('', 'GET'))

        assert mock_result_service_get.called
        self.assertEqual(response.status_code, 200)

    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock._result_service_put')
    @patch('lti_consumer.lti_1p1.consumer.LtiConsumer1p1.verify_result_headers', Mock(return_value=True))
    @patch('lti_consumer.lti_xblock.parse_handler_suffix')
    def test_result_service_put_called(self, mock_parse_suffix, mock_result_service_put):
        """
        Test 200 response and LtiConsumerXBlock._result_service_put is called on a PUT request
        """
        mock_parse_suffix.return_value = FAKE_USER_ID
        mock_result_service_put.return_value = {}
        response = self.xblock.result_service_handler(make_request('', 'PUT'))

        assert mock_result_service_put.called
        self.assertEqual(response.status_code, 200)

    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock._result_service_delete')
    @patch('lti_consumer.lti_1p1.consumer.LtiConsumer1p1.verify_result_headers', Mock(return_value=True))
    @patch('lti_consumer.lti_xblock.parse_handler_suffix')
    def test_result_service_delete_called(self, mock_parse_suffix, mock_result_service_delete):
        """
        Test 200 response and LtiConsumerXBlock._result_service_delete is called on a DELETE request
        """
        mock_parse_suffix.return_value = FAKE_USER_ID
        mock_result_service_delete.return_value = {}
        response = self.xblock.result_service_handler(make_request('', 'DELETE'))

        assert mock_result_service_delete.called
        self.assertEqual(response.status_code, 200)

    def test_consumer_get_result_called(self):
        """
        Test runtime calls rebind_noauth_module_to_user and LtiConsumer.get_result is called on a GET request
        """
        mock_runtime = self.xblock.runtime = Mock()
        mock_lti_consumer = Mock()
        mock_user = Mock()

        self.xblock._result_service_get(mock_lti_consumer, mock_user)  # pylint: disable=protected-access

        mock_runtime.rebind_noauth_module_to_user.assert_called_with(self.xblock, mock_user)
        mock_lti_consumer.get_result.assert_called_with()

    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.module_score', PropertyMock(return_value=0.5))
    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.score_comment', PropertyMock(return_value='test'))
    def test_consumer_get_result_called_with_score_details(self):
        """
        Test LtiConsumer.get_result is called with module_score and score_comment on a GET request with a module_score
        """
        mock_lti_consumer = Mock()
        mock_user = Mock()

        self.xblock._result_service_get(mock_lti_consumer, mock_user)  # pylint: disable=protected-access

        mock_lti_consumer.get_result.assert_called_with(0.5, 'test')

    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.clear_user_module_score', Mock(return_value=True))
    @patch('lti_consumer.lti_xblock.parse_result_json')
    def test_consumer_put_result_called(self, mock_parse_result_json):
        """
        Test parse_result_json and LtiConsumer.put_result is called on a PUT request
        """
        mock_parse_result_json.return_value = (None, None)
        mock_lti_consumer = Mock()
        mock_user = Mock()

        self.xblock._result_service_put(mock_lti_consumer, mock_user, '')  # pylint: disable=protected-access

        assert mock_parse_result_json.called
        assert mock_lti_consumer.put_result.called

    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.clear_user_module_score')
    @patch('lti_consumer.lti_xblock.parse_result_json', Mock(return_value=(None, None)))
    def test_clear_user_module_score_called_when_no_score_available(self, mock_clear_user_module_score):
        """
        Test LtiConsumerXBlock.clear_user_module_score is called on a PUT request with no score
        """
        mock_lti_consumer = Mock()
        mock_user = Mock()
        self.xblock._result_service_put(mock_lti_consumer, mock_user, '')  # pylint: disable=protected-access

        mock_clear_user_module_score.assert_called_with(mock_user)

    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.set_user_module_score')
    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.max_score', Mock(return_value=10))
    @patch('lti_consumer.lti_xblock.parse_result_json', Mock(return_value=(1, 'comment')))
    def test_set_user_module_score_called_when_score_available(self, mock_set_user_module_score):
        """
        Test LtiConsumerXBlock.set_user_module_score is called on a PUT request with a score
        """
        mock_lti_consumer = Mock()
        mock_user = Mock()
        self.xblock._result_service_put(mock_lti_consumer, mock_user, '')  # pylint: disable=protected-access

        mock_set_user_module_score.assert_called_with(mock_user, 1, 10, 'comment')

    @patch('lti_consumer.lti_xblock.LtiConsumerXBlock.clear_user_module_score')
    def test_consumer_delete_result_called(self, mock_clear_user_module_score):
        """
        Test LtiConsumerXBlock.clear_user_module_score is called on a PUT request with no score
        """
        mock_lti_consumer = Mock()
        mock_user = Mock()
        self.xblock._result_service_delete(mock_lti_consumer, mock_user)  # pylint: disable=protected-access

        mock_clear_user_module_score.assert_called_with(mock_user)
        assert mock_lti_consumer.delete_result.called

    def test_get_outcome_service_url_with_default_parameter(self):
        """
        Test `get_outcome_service_url` with default parameter
        """
        handler_url = 'http://localhost:8005/outcome_service_handler'
        self.xblock.runtime.handler_url = Mock(return_value=f"{handler_url}/?")
        url = self.xblock.get_outcome_service_url()

        self.xblock.runtime.handler_url.assert_called_with(self.xblock, 'outcome_service_handler', thirdparty=True)
        self.assertEqual(url, handler_url)

    def test_get_outcome_service_url_with_service_name_grade_handler(self):
        """
        Test `get_outcome_service_url` calls service name grade_handler
        """
        handler_url = 'http://localhost:8005/outcome_service_handler'
        self.xblock.runtime.handler_url = Mock(return_value=f"{handler_url}/?")
        url = self.xblock.get_outcome_service_url('grade_handler')

        self.xblock.runtime.handler_url.assert_called_with(self.xblock, 'outcome_service_handler', thirdparty=True)
        self.assertEqual(url, handler_url)

    def test_get_outcome_service_url_with_service_name_lti_2_0_result_rest_handler(self):
        """
        Test `get_outcome_service_url` calls with service name lti_2_0_result_rest_handler
        """
        handler_url = 'http://localhost:8005/result_service_handler'
        self.xblock.runtime.handler_url = Mock(return_value=f"{handler_url}/?")
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
        parsed = parse_handler_suffix(f"user/{FAKE_USER_ID}")
        self.assertEqual(parsed, FAKE_USER_ID)


@ddt.ddt
class TestGetContext(TestLtiConsumerXBlock):
    """
    Unit tests for LtiConsumerXBlock._get_context_for_template()
    """

    @ddt.data('lti_1p1', 'lti_1p3')
    @patch('lti_consumer.api.get_lti_1p3_content_url')
    def test_context_keys(self, lti_version, lti_api_patch):
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

        if lti_version == 'lti_1p3':
            lti_api_patch.assert_called_once()

    @ddt.data('a', 'abbr', 'acronym', 'b', 'blockquote', 'code', 'em', 'i', 'li', 'ol', 'strong', 'ul', 'img')
    def test_comment_allowed_tags(self, tag):
        """
        Test that allowed tags are not escaped in context['comment']
        """
        comment = '<{0}>This is a comment</{0}>!'.format(tag)
        self.xblock.set_user_module_score(Mock(), 0.92, 1.0, comment)
        context = self.xblock._get_context_for_template()  # pylint: disable=protected-access

        self.assertIn(f'<{tag}>', context['comment'])

    def test_comment_retains_image_src(self):
        """
        Test that image tag has src and other attrs are sanitized
        """
        comment = '<img src="example.com/image.jpeg" onerror="myFunction()">'
        self.xblock.set_user_module_score(Mock(), 0.92, 1.0, comment)
        context = self.xblock._get_context_for_template()  # pylint: disable=protected-access

        self.assertIn('<img src="example.com/image.jpeg">', context['comment'])


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
        with patch('lti_consumer.lti_xblock.LtiConsumerXBlock.get_settings', return_value=self.settings):
            processors = list(self.xblock.get_parameter_processors())
            assert len(processors) == 1, 'One processor should be enabled'
            # pylint: disable=comparison-with-callable
            assert processors[0] == test_utils.dummy_processor, 'Should load the correct function'

    def test_disabled_processors(self):
        self.xblock.enable_processors = False
        with patch('lti_consumer.lti_xblock.LtiConsumerXBlock.get_settings', return_value=self.settings):
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
    @patch('lti_consumer.lti_xblock.log')
    def test_faulty_configs(self, settings, mock_log):
        self.xblock.enable_processors = True
        with patch('lti_consumer.lti_xblock.LtiConsumerXBlock.get_settings', return_value=settings):
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
        super().setUp()

        self.xblock_attributes = {
            'lti_version': 'lti_1p3',
            'lti_1p3_launch_url': 'http://tool.example/launch',
            'lti_1p3_oidc_url': 'http://tool.example/oidc',
        }
        self.xblock = make_xblock('lti_consumer', LtiConsumerXBlock, self.xblock_attributes)
        # Set dummy location so that UsageKey lookup is valid
        self.xblock.location = 'block-v1:course+test+2020+type@problem+block@test'

        self.patcher = patch("lti_consumer.lti_xblock.external_config_filter_enabled")
        self.mock_filter_enabled = self.patcher.start()

    def tearDown(self) -> None:
        self.patcher.stop()
        super().tearDown()

    def test_launch_callback_endpoint(self):
        """
        Test the LTI 1.3 callback endpoint.
        """
        self.xblock.runtime.get_user_role.return_value = 'student'
        mock_user_service = Mock()
        mock_user_service.get_external_user_id.return_value = 2
        self.xblock.runtime.service.return_value = mock_user_service

        self.xblock.course.display_name_with_default = 'course_display_name'
        self.xblock.course.display_org_with_default = 'course_display_org'

        # Get LTI client_id
        client_id = get_lti_1p3_launch_info(block=self.xblock)['client_id']

        # Craft request sent back by LTI tool
        request = make_request('', 'GET')
        request.query_string = (
            f"client_id={client_id}&" +
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

    def test_launch_callback_endpoint_fails(self):
        """
        Test that the LTI 1.3 callback endpoint correctly display an error message.
        """
        self.xblock.runtime.get_user_role.return_value = 'student'
        mock_user_service = Mock()
        mock_user_service.get_external_user_id.return_value = 2
        self.xblock.runtime.service.return_value = mock_user_service

        self.xblock.course.display_name_with_default = 'course_display_name'
        self.xblock.course.display_org_with_default = 'course_display_org'

        # Make a fake invalid preflight request, with empty parameters
        request = make_request('', 'GET')
        response = self.xblock.lti_1p3_launch_callback(request)

        # Check response and assert that state was inserted
        self.assertEqual(response.status_code, 400)

        response_body = response.body.decode('utf-8')
        self.assertIn("There was an error while launching the LTI 1.3 tool.", response_body)
        self.assertNotIn("% trans", response_body)

    def test_launch_callback_endpoint_when_using_lti_1p1(self):
        """
        Test that the LTI 1.3 callback endpoind is unavailable when using 1.1.
        """
        self.xblock.lti_version = 'lti_1p1'
        self.xblock.save()
        response = self.xblock.lti_1p3_launch_callback(make_request('', 'GET'))
        self.assertEqual(response.status_code, 404)

    def test_studio_view(self):
        """
        Test that the studio settings view load the custom js.
        """
        self.xblock.location = Mock()
        self.xblock.location.__get__ = 'block-v1:course+test+2020+type@problem+block@test'
        self.xblock.location.course_key = 'course-v1:Demo_Course'
        response = self.xblock.studio_view({})
        self.assertEqual(response.js_init_fn, 'LtiConsumerXBlockInitStudio')

    @patch('lti_consumer.api.get_lti_1p3_launch_info')
    def test_author_view(self, mock_get_launch_info):
        """
        Test that the studio view loads LTI 1.3 view.
        """
        mock_get_launch_info.return_value = {
            'client_id': "mock-client_id",
            'keyset_url': "mock-keyset_url",
            'deployment_id': '1',
            'oidc_callback': "mock-oidc_callback",
            'token_url': "mock-token_url",
        }
        # Mock i18n service before fetching author view
        self.xblock.runtime.service.return_value = None
        response = self.xblock.author_view({})

        self.assertIn("mock-client_id", response.content)
        self.assertIn("mock-keyset_url", response.content)
        self.assertIn("mock-token_url", response.content)

    def test_launch_callback_endpoint_deep_linking(self):
        """
        Test the LTI 1.3 callback endpoint for deep linking requests.
        """
        self.xblock.runtime.get_user_role.return_value = 'staff'
        mock_user_service = Mock()
        mock_user_service.get_external_user_id.return_value = 2
        self.xblock.runtime.service.return_value = mock_user_service

        self.xblock.course.display_name_with_default = 'course_display_name'
        self.xblock.course.display_org_with_default = 'course_display_org'

        # Enable deep linking
        self.xblock.lti_advantage_deep_linking_enabled = True

        # Get LTI client_id
        client_id = get_lti_1p3_launch_info(block=self.xblock)['client_id']

        # Craft request sent back by LTI tool
        request = make_request('', 'GET')
        request.query_string = (
            "client_id={}&".format(client_id) +
            "redirect_uri=http://tool.example/launch&" +
            "state=state_test_123&" +
            "nonce=nonce&" +
            "login_hint=oidchint&" +
            "lti_message_hint=deep_linking_launch"
        )

        response = self.xblock.lti_1p3_launch_callback(request)

        # Check response
        self.assertEqual(response.status_code, 200)

    def test_launch_callback_endpoint_deep_linking_by_student(self):
        """
        Test that the callback endpoint errors out if students try to do a deep link launch.
        """
        self.xblock.runtime.get_user_role.return_value = 'student'
        mock_user_service = Mock()
        mock_user_service.get_external_user_id.return_value = 2
        self.xblock.runtime.service.return_value = mock_user_service

        self.xblock.course.display_name_with_default = 'course_display_name'
        self.xblock.course.display_org_with_default = 'course_display_org'

        # Enable deep linking
        self.xblock.lti_advantage_deep_linking_enabled = True

        # Get LTI client_id
        client_id = get_lti_1p3_launch_info(block=self.xblock)['client_id']

        # Craft request sent back by LTI tool
        request = make_request('', 'GET')
        request.query_string = (
            "client_id={}&".format(client_id) +
            "redirect_uri=http://tool.example/launch&" +
            "state=state_test_123&" +
            "nonce=nonce&" +
            "login_hint=oidchint&" +
            "lti_message_hint=deep_linking_launch"
        )

        response = self.xblock.lti_1p3_launch_callback(request)

        # Check response
        self.assertEqual(response.status_code, 403)
        response_body = response.body.decode('utf-8')
        self.assertIn("Students don't have permissions to perform", response_body)
        self.assertNotIn("% trans", response_body)

    @patch('lti_consumer.api.get_deep_linking_data')
    def test_callback_endpoint_dl_content_launch(self, mock_dl_data):
        """
        Test that the callback endpoint return the correct information when
        doing a `ltiResourceLink` deep linking launch.
        """
        self.xblock.runtime.get_user_role.return_value = 'student'
        mock_user_service = Mock()
        mock_user_service.get_external_user_id.return_value = 2
        self.xblock.runtime.service.return_value = mock_user_service
        self.xblock.course.display_name_with_default = 'course_display_name'
        self.xblock.course.display_org_with_default = 'course_display_org'

        # Set deep linking mock data
        mock_dl_data.return_value = {
            "url": "https://deep-link-content/",
            "custom": {
                "parameter": "custom",
            },
        }

        # Enable deep linking
        self.xblock.lti_advantage_deep_linking_enabled = True

        # Get LTI client_id
        client_id = get_lti_1p3_launch_info(block=self.xblock)['client_id']

        # Craft request sent back by LTI tool
        request = make_request('', 'GET')
        request.query_string = (
            "client_id={}&".format(client_id) +
            "redirect_uri=http://tool.example/launch&" +
            "state=state_test_123&" +
            "nonce=nonce&" +
            "login_hint=oidchint&" +
            "lti_message_hint=deep_linking_content_launch:1"
        )

        response = self.xblock.lti_1p3_launch_callback(request)
        content = response.body.decode('utf-8')

        # Check response
        self.assertEqual(response.status_code, 200)
        self.assertIn("http://tool.example/launch", content)


class TestLti1p3AccessTokenEndpoint(TestLtiConsumerXBlock):
    """
    Unit tests for LtiConsumerXBlock Access Token endpoint when using an LTI 1.3.
    """
    def setUp(self):
        super().setUp()

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
            'lti_1p3_tool_public_key': self.public_key,
        }
        self.xblock = make_xblock('lti_consumer', LtiConsumerXBlock, self.xblock_attributes)
        # Set dummy location so that UsageKey lookup is valid
        self.xblock.location = 'block-v1:course+test+2020+type@problem+block@test'

    def test_access_token_endpoint_when_using_lti_1p1(self):
        """
        Test that the LTI 1.3 access token endpoind is unavailable when using 1.1.
        """
        self.xblock.lti_version = 'lti_1p1'
        self.xblock.save()

        request = make_request(json.dumps({}), 'POST')
        request.content_type = 'application/json'

        response = self.xblock.lti_1p3_access_token(request)
        self.assertEqual(response.status_code, 404)

    def test_access_token_endpoint_no_post(self):
        """
        Test that the LTI 1.3 access token endpoind is unavailable when using 1.1.
        """
        request = make_request('', 'GET')

        response = self.xblock.lti_1p3_access_token(request)
        self.assertEqual(response.status_code, 405)

    def test_access_token_missing_claims(self):
        """
        Test request with missing parameters.
        """
        request = make_request(json.dumps({}), 'POST')
        request.content_type = 'application/json'

        response = self.xblock.lti_1p3_access_token(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json_body, {'error': 'invalid_request'})

    def test_access_token_malformed(self):
        """
        Test request with invalid JWT.
        """
        request = make_jwt_request("invalid-jwt")
        response = self.xblock.lti_1p3_access_token(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json_body, {'error': 'invalid_grant'})

    def test_access_token_invalid_grant(self):
        """
        Test request with invalid grant.
        """
        request = make_jwt_request("invalid-jwt", grant_type="password")
        request.content_type = 'application/x-www-form-urlencoded'

        response = self.xblock.lti_1p3_access_token(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json_body, {'error': 'unsupported_grant_type'})

    def test_access_token_invalid_client(self):
        """
        Test request with valid JWT but no matching key to check signature.
        """
        self.xblock.lti_1p3_tool_public_key = ''
        self.xblock.save()

        jwt = create_jwt(self.key, {})
        request = make_jwt_request(jwt)
        response = self.xblock.lti_1p3_access_token(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json_body, {'error': 'invalid_client'})

    def test_access_token(self):
        """
        Test request with valid JWT.
        """
        jwt = create_jwt(self.key, {})
        request = make_jwt_request(jwt)
        response = self.xblock.lti_1p3_access_token(request)
        self.assertEqual(response.status_code, 200)


@patch('lti_consumer.utils.log')
@patch('lti_consumer.utils.import_module')
class TestDynamicCustomParametersResolver(TestLtiConsumerXBlock):
    """
    Unit tests for lti_xblock utils resolve_custom_parameter_template method.
    """

    def setUp(self):
        super().setUp()

        self.logger = logging.getLogger()
        dj_settings.LTI_CUSTOM_PARAM_TEMPLATES = {
            'templated_param_value': 'customer_package.module:func',
        }
        self.mock_processor_module = Mock(func=Mock())

    def test_successful_resolve_custom_parameter_template(self, mock_import_module, *_):
        """
        Test a successful module import and execution. The template value to be resolved
        should be replaced by the processor.
        """

        custom_parameter_template_value = '${templated_param_value}'
        expected_resolved_value = 'resolved_value'
        mock_import_module.return_value = self.mock_processor_module
        self.mock_processor_module.func.return_value = expected_resolved_value

        resolved_value = resolve_custom_parameter_template(self.xblock, custom_parameter_template_value)

        mock_import_module.assert_called_once()
        self.assertEqual(resolved_value, expected_resolved_value)

    def test_resolve_custom_parameter_template_with_invalid_data_type_returned(self, mock_import_module, mock_log):
        """
        Test a successful module import and execution. The value returned by the processor should be a string object.
        Otherwise, it should log an error.
        """

        custom_parameter_template_value = '${templated_param_value}'
        mock_import_module.return_value = self.mock_processor_module
        self.mock_processor_module.func.return_value = 1

        resolved_value = resolve_custom_parameter_template(self.xblock, custom_parameter_template_value)

        self.assertEqual(resolved_value, custom_parameter_template_value)
        assert mock_log.error.called

    def test_resolve_custom_parameter_template_with_invalid_module(self, mock_import_module, mock_log):
        """
        Test a failed import with an undefined module. This should log an error.
        """
        mock_import_module.side_effect = ModuleNotFoundError
        custom_parameter_template_value = '${not_defined_parameter_template}'

        resolved_value = resolve_custom_parameter_template(self.xblock, custom_parameter_template_value)

        self.assertEqual(resolved_value, custom_parameter_template_value)
        assert mock_log.error.called

    def test_lti_custom_param_templates_not_configured(self, mock_import_module, mock_log):
        """
        Test the feature with LTI_CUSTOM_PARAM_TEMPLATES setting attribute not configured.
        """
        custom_parameter_template_value = '${templated_param_value}'

        dj_settings.__delattr__('LTI_CUSTOM_PARAM_TEMPLATES')

        resolved_value = resolve_custom_parameter_template(self.xblock, custom_parameter_template_value)

        self.assertEqual(resolved_value, custom_parameter_template_value)
        assert mock_log.error.called
        mock_import_module.asser_not_called()


class TestLti1p3AccessTokenJWK(TestCase):
    """
    Unit tests for LtiConsumerXBlock Access Token endpoint when using a
    LTI 1.3 setup with JWK authentication.
    """
    def setUp(self):
        super().setUp()
        self.xblock = make_xblock('lti_consumer', LtiConsumerXBlock, {
            'lti_version': 'lti_1p3',
            'lti_1p3_launch_url': 'http://tool.example/launch',
            'lti_1p3_oidc_url': 'http://tool.example/oidc',
            'lti_1p3_tool_keyset_url': "http://tool.example/keyset",
        })
        self.xblock.location = 'block-v1:course+test+2020+type@problem+block@test'
        self.xblock.save()

        self.key = RSAKey(key=RSA.generate(2048), kid="1")

        jwt = create_jwt(self.key, {})
        self.request = make_jwt_request(jwt)

    def make_keyset(self, keys):
        """
        Builds a keyset object with the given keys.
        """
        jwks = KEYS()
        jwks._keys = keys  # pylint: disable=protected-access
        return jwks

    @patch("lti_consumer.lti_1p3.key_handlers.load_jwks_from_url")
    def test_access_token_using_keyset_url(self, load_jwks_from_url):
        """
        Test request using the provider's keyset URL instead of a public key.
        """
        load_jwks_from_url.return_value = self.make_keyset([self.key])
        response = self.xblock.lti_1p3_access_token(self.request)
        load_jwks_from_url.assert_called_once_with("http://tool.example/keyset")
        self.assertEqual(response.status_code, 200)

    @patch("lti_consumer.lti_1p3.key_handlers.load_jwks_from_url")
    def test_access_token_using_keyset_url_with_empty_keys(self, load_jwks_from_url):
        """
        Test request where the provider's keyset URL returns an empty list of keys.
        """
        load_jwks_from_url.return_value = self.make_keyset([])
        response = self.xblock.lti_1p3_access_token(self.request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json_body, {"error": "invalid_client"})

    @patch("lti_consumer.lti_1p3.key_handlers.load_jwks_from_url")
    def test_access_token_using_keyset_url_with_wrong_keys(self, load_jwks_from_url):
        """
        Test request where the provider's keyset URL returns wrong keys.
        """
        key = RSAKey(key=RSA.generate(2048), kid="2")
        load_jwks_from_url.return_value = self.make_keyset([key])
        response = self.xblock.lti_1p3_access_token(self.request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json_body, {"error": "invalid_client"})

    @patch("jwkest.jwk.request")
    def test_access_token_using_keyset_url_that_fails(self, request):
        """
        Test request where the provider's keyset URL request fails.
        """
        request.side_effect = Exception("request fails")
        response = self.xblock.lti_1p3_access_token(self.request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json_body, {'error': 'invalid_client'})

    @patch("jwkest.jwk.request")
    def test_access_token_using_keyset_url_with_invalid_contents(self, request):
        """
        Test request where the provider's keyset URL doesn't return valid JSON.
        """
        response_mock = Mock()
        response_mock.status_code = 200
        response_mock.text = b'this is not a valid json'
        request.return_value = response_mock
        response = self.xblock.lti_1p3_access_token(self.request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json_body, {'error': 'invalid_client'})
