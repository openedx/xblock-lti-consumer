"""
Unit tests for lti_consumer.lti module
"""

from unittest.mock import ANY, Mock, patch

from django.test.testcases import TestCase

from lti_consumer.lti_1p1.contrib.django import lti_embed


class TestLtiEmbed(TestCase):
    """
    Unit tests for contrib.django.lti_embed
    """

    def setUp(self):
        super().setUp()
        self.html_element_id = 'html_element_id'
        self.lti_launch_url = 'lti_launch_url'
        self.oauth_key = 'oauth_key'
        self.oauth_secret = 'oauth_secret'
        self.resource_link_id = 'resource_link_id'
        self.user_id = 'user_id'
        self.roles = 'roles'
        self.context_id = 'context_id'
        self.context_title = 'context_title'
        self.context_label = 'context_label'
        self.result_sourcedid = 'result_sourcedid'

        # Patch calls to LMS event tracking
        self._mock_emit_track_event = Mock()
        track_event_patcher = patch(
            'lti_consumer.track.get_event_tracker',
            return_value=Mock(emit=self._mock_emit_track_event),
        )
        self.addCleanup(track_event_patcher.stop)
        track_event_patcher.start()

    def test_non_keyword_arguments_raise_type_error(self):
        with self.assertRaises(TypeError):
            lti_embed(  # pylint: disable=too-many-function-args,missing-kwoa
                self.html_element_id,
                self.lti_launch_url,
                self.oauth_key,
                self.oauth_secret,
                self.resource_link_id,
                self.user_id,
                self.roles,
                self.context_id,
                self.context_title,
                self.context_label,
                self.result_sourcedid
            )

    def test_missing_required_arguments_raise_type_error(self):
        with self.assertRaises(TypeError):
            # Missing result_sourcedid
            lti_embed(  # pylint: disable=missing-kwoa
                html_element_id=self.html_element_id,
                lti_launch_url=self.lti_launch_url,
                oauth_key=self.oauth_key,
                oauth_secret=self.oauth_secret,
                resource_link_id=self.resource_link_id,
                user_id=self.user_id,
                roles=self.roles,
                context_id=self.context_id,
                context_title=self.context_title,
                context_label=self.context_label
            )

    @patch('lti_consumer.lti_1p1.contrib.django.LtiConsumer1p1')
    def test_consumer_initialized_properly(self, mock_lti_consumer_class):
        lti_embed(
            html_element_id=self.html_element_id,
            lti_launch_url=self.lti_launch_url,
            oauth_key=self.oauth_key,
            oauth_secret=self.oauth_secret,
            resource_link_id=self.resource_link_id,
            user_id=self.user_id,
            roles=self.roles,
            context_id=self.context_id,
            context_title=self.context_title,
            context_label=self.context_label,
            result_sourcedid=self.result_sourcedid
        )

        mock_lti_consumer_class.assert_called_with(self.lti_launch_url, self.oauth_key, self.oauth_secret)

    @patch('lti_consumer.lti_1p1.contrib.django.LtiConsumer1p1.set_custom_parameters')
    @patch('lti_consumer.lti_1p1.contrib.django.LtiConsumer1p1.generate_launch_request', Mock(return_value={}))
    def test_custom_parameters_ignore_keyword_args_without_custom_prefix(self, mock_set_custom_parameters):
        lti_embed(
            html_element_id=self.html_element_id,
            lti_launch_url=self.lti_launch_url,
            oauth_key=self.oauth_key,
            oauth_secret=self.oauth_secret,
            resource_link_id=self.resource_link_id,
            user_id=self.user_id,
            roles=self.roles,
            context_id=self.context_id,
            context_title=self.context_title,
            context_label=self.context_label,
            result_sourcedid=self.result_sourcedid,
            custom_parameter_1='custom_parameter_1',
            custom_parameter_2='custom_parameter_2',
            parameter_3='parameter_3',
        )

        expected_custom_parameters = {
            'custom_parameter_1': 'custom_parameter_1',
            'custom_parameter_2': 'custom_parameter_2'
        }
        mock_set_custom_parameters.assert_called_with(expected_custom_parameters)

    @patch('lti_consumer.lti_1p1.contrib.django.LtiConsumer1p1.generate_launch_request', Mock(return_value={'a': 1}))
    @patch('lti_consumer.lti_1p1.contrib.django.ResourceLoader.render_django_template')
    def test_make_template_rendered_with_correct_context_and_returned(self, mock_render_django_template):
        fake_template = 'SOME_TEMPLATE'
        mock_render_django_template.return_value = fake_template

        rendered_template = lti_embed(
            html_element_id=self.html_element_id,
            lti_launch_url=self.lti_launch_url,
            oauth_key=self.oauth_key,
            oauth_secret=self.oauth_secret,
            resource_link_id=self.resource_link_id,
            user_id=self.user_id,
            roles=self.roles,
            context_id=self.context_id,
            context_title=self.context_title,
            context_label=self.context_label,
            result_sourcedid=self.result_sourcedid,
            custom_parameter_1='custom_parameter_1',
            custom_parameter_2='custom_parameter_2',
            parameter_3='parameter_3',
        )

        expected_context = {
            'element_id': self.html_element_id,
            'launch_url': self.lti_launch_url,
            'lti_parameters': {'a': 1}
        }
        mock_render_django_template.assert_called_with(ANY, expected_context)
        self.assertEqual(rendered_template, fake_template)

    @patch('lti_consumer.lti_1p1.contrib.django.LtiConsumer1p1.generate_launch_request')
    @patch('lti_consumer.lti_1p1.contrib.django.ResourceLoader.render_django_template', Mock())
    def test_emits_tracking_event(self, mock_launch_request):
        mock_launch_request.return_value = {
            'lti_version': 'LTI_1p1',
            'roles': self.roles,
        }
        lti_embed(
            html_element_id=self.html_element_id,
            lti_launch_url=self.lti_launch_url,
            oauth_key=self.oauth_key,
            oauth_secret=self.oauth_secret,
            resource_link_id=self.resource_link_id,
            user_id=self.user_id,
            roles=self.roles,
            context_id=self.context_id,
            context_title=self.context_title,
            context_label=self.context_label,
            result_sourcedid=self.result_sourcedid
        )

        self._mock_emit_track_event.assert_called_with(
            'edx.lti.embed.launch_request',
            {
                'lti_version': 'LTI_1p1',
                'user_roles': self.roles,
                'launch_url': self.lti_launch_url,
            }
        )
