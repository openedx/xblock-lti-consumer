"""
Tests for the LTI consumer filters.
"""
from unittest.mock import patch
from django.test import TestCase, override_settings


from openedx_filters import PipelineStep
from lti_consumer.filters import (
    LTIConfigurationListed,
    get_external_config_from_filter
)


class MyTestPipelineStep(PipelineStep):
    """
    Test pipeline step.
    """

    def run_filter(self, **kwargs):
        pass


class LTIConfigurationListedTestCase(TestCase):
    """
    Unit tests for the LTIConfigurationListed filter.
    """

    @override_settings(
        OPEN_EDX_FILTERS_CONFIG={
            "org.openedx.xblock.lti_consumer.configuration.listed.v1": {
                "pipeline": [
                    "lti_consumer.tests.unit.test_filters.MyTestPipelineStep"
                ],
                "fail_silently": True,
                "log_level": "debug",
            }
        }
    )
    @patch("lti_consumer.tests.unit.test_filters.MyTestPipelineStep")
    def test_filter_execution(self, mock_step):
        mock_step.__name__ = "MyTestPipelineStep"
        mock_step.return_value.run_filter.return_value = {
            "context": {},
            "config_id": "test-id",
            "configurations": {"my-plugin:provider-1": {"config": "config-1"}}
        }
        f = LTIConfigurationListed()
        data = f.run_filter(context={}, config_id="test-id", configurations={})
        self.assertEqual(data, ({}, "test-id", {"my-plugin:provider-1": {"config": "config-1"}}))


class TestGetExternalConfigFromFilter(TestCase):
    """
    Tests for the utility function get_external_config_from_filter which
    allows quickly pulling external configurations using the LTIConfigurationListed
    filter.
    """

    @patch("lti_consumer.filters.LTIConfigurationListed")
    def test_get_external_config_from_filter_returns_only_the_configs(self, mock_filter):
        context = {"course_id": "test-course"}
        config_id = ""
        configs = {
            "test-config-id": {},
            "another-config": {},
        }

        mock_filter.run_filter.return_value = (context, config_id, configs)
        self.assertEqual(get_external_config_from_filter(context), configs)

    @patch("lti_consumer.filters.LTIConfigurationListed")
    def test_it_returns_the_value_of_a_single_config_when_config_id_is_specified(self, mock_filter):
        demo_client = {
            "launch_url": "http://example.com/launch",
            "lti_version": "lti_1p1",
            "lti_consumer_secret": "secret",
        }
        context = {}
        config_id = "test_config_id"
        configs = {
            "test-config-id": demo_client,
            "another-config": {},
        }

        mock_filter.run_filter.return_value = (context, config_id, configs)
        self.assertDictEqual(get_external_config_from_filter(context, "test-config-id"), demo_client)
