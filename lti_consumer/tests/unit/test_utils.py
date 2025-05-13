"""
Unit tests for lti_consumer.utils module
"""
from unittest.mock import Mock, patch

import ddt
from django.test.testcases import TestCase

from opaque_keys.edx.locator import CourseLocator
from lti_consumer.lti_1p3.constants import LTI_1P3_CONTEXT_TYPE
from lti_consumer.utils import (
    choose_lti_1p3_redirect_uris,
    get_lti_1p3_context_types_claim,
    get_lti_1p3_launch_data_cache_key,
    cache_lti_1p3_launch_data,
    get_data_from_cache,
    model_to_dict,
    external_multiple_launch_urls_enabled,
)

LAUNCH_URL = "http://tool.launch"
DEEP_LINK_URL = "http://tool.deep.launch"


@ddt.ddt
class TestGetLti1p3ContextTypesClaim(TestCase):
    """
    Tests for the get_lti_1p3_context_types_claim function of the utils module.
    """

    @ddt.data(
        (["course_offering"], [LTI_1P3_CONTEXT_TYPE.course_offering]),
        (["course_offering", "group"], [LTI_1P3_CONTEXT_TYPE.course_offering, LTI_1P3_CONTEXT_TYPE.group]),
    )
    @ddt.unpack
    def test_get_lti_1p3_context_types_claim(self, argument, expected_output):
        """
        Test that get_lti_1p3_context_types_claim returns the correct context_types.
        """
        lti_context_types_claims = get_lti_1p3_context_types_claim(argument)

        self.assertEqual(lti_context_types_claims, expected_output)

    @ddt.data(
        ["course_offering", "nonsense"],
        ["nonsense"],
    )
    def test_get_lti_1p3_context_types_claim_invalid(self, argument):
        """
        Test that get_lti_1p3_context_types_claim if any of the context_types are invalid.
        """
        with self.assertRaises(ValueError):
            get_lti_1p3_context_types_claim(argument)


@ddt.ddt
class TestCacheUtilities(TestCase):
    """
    Tests for the cache utilities in the utils module.
    """

    @patch('lti_consumer.utils.get_cache_key')
    @ddt.data(None, "1")
    def test_get_lti_1p3_launch_data_cache_key(self, deep_linking_content_item_id, mock_get_cache_key):
        """
        Test that get_lti_1p3_launch_data_cache_key calls the get_cache_key function with the correct arguments.
        """
        mock_launch_data = Mock()
        mock_launch_data.user_id = "1"
        mock_launch_data.resource_link_id = "1"
        mock_launch_data.deep_linking_content_item_id = deep_linking_content_item_id

        get_lti_1p3_launch_data_cache_key(mock_launch_data)

        get_cache_key_kwargs = {
            "app": "lti",
            "key": "launch_data",
            "user_id": "1",
            "resource_link_id": "1"
        }

        if deep_linking_content_item_id:
            get_cache_key_kwargs['deep_linking_content_item_id'] = deep_linking_content_item_id

        mock_get_cache_key.assert_called_with(
            **get_cache_key_kwargs
        )

    @patch('lti_consumer.utils.TieredCache.set_all_tiers')
    @patch('lti_consumer.utils.get_lti_1p3_launch_data_cache_key')
    def test_cache_lti_1p3_launch_data(self, mock_get_cache_key, mock_set_all_tiers):
        """
        Test that cache_lti_1p3_launch_data caches the launch_data and returns the cache key.
        """
        mock_launch_data = Mock()

        mock_get_cache_key.return_value = "launch_data_cache_key"

        cache_lti_1p3_launch_data(mock_launch_data)

        mock_get_cache_key.assert_called_with(mock_launch_data)
        mock_set_all_tiers.assert_called_with("launch_data_cache_key", mock_launch_data, django_cache_timeout=600)

    @patch('lti_consumer.utils.TieredCache.get_cached_response')
    @ddt.data(True, False)
    def test_get_data_from_cache(self, is_found, mock_get_cached_response):
        """
        Test that get_data_from_cache returns the data from the cache correctly or returns None if the data
        is not in the cache.
        """
        mock_cached_data = Mock()
        mock_cached_data.value = "value"
        mock_cached_data.is_found = is_found

        mock_get_cached_response.return_value = mock_cached_data

        value = get_data_from_cache("key")

        if is_found:
            self.assertEqual(value, "value")
        else:
            self.assertIsNone(value)

    @ddt.data(
        ("", "", [], []),
        (LAUNCH_URL, "", [], [LAUNCH_URL]),
        ("", DEEP_LINK_URL, [], [DEEP_LINK_URL]),
        (LAUNCH_URL, DEEP_LINK_URL, [], [LAUNCH_URL, DEEP_LINK_URL]),
        (LAUNCH_URL, DEEP_LINK_URL, ["http://other.url"], ["http://other.url"]),
    )
    @ddt.unpack
    def test_choose_lti_1p3_redirect_uri_returns_expected(self, launch_url, deep_link_url, redirect_uris, expected):
        """
        Returns redirect_uris if set, else returns launch/deep_link urls as defaults
        """
        result = choose_lti_1p3_redirect_uris(
            redirect_uris=redirect_uris,
            launch_url=launch_url,
            deep_link_url=deep_link_url
        )

        assert result == expected


class TestModelToDict(TestCase):
    """
    Tests for the model_to_dict function.
    """

    def setUp(self):
        super().setUp()
        self.model_object = Mock()

    @patch('lti_consumer.utils.copy.deepcopy', return_value={'test': 'test', '_test': 'test'})
    def test_with_exclude_argument(self, deepcopy_mock):
        """
        Test model_to_dict function with exclude argument.
        """
        self.assertEqual(model_to_dict(self.model_object, ['test']), {})
        deepcopy_mock.assert_called_once_with(self.model_object.__dict__)

    @patch('lti_consumer.utils.copy.deepcopy', side_effect=AttributeError())
    def test_with_attribute_error(self, deepcopy_mock):
        """
        Test model_to_dict function with AttributeError exception.
        """
        self.assertEqual(model_to_dict(self.model_object), {})
        deepcopy_mock.assert_called_once_with(self.model_object.__dict__)

    @patch('lti_consumer.utils.copy.deepcopy', side_effect=TypeError())
    def test_with_type_error(self, deepcopy_mock):
        """
        Test model_to_dict function with TypeError exception.
        """
        self.assertEqual(model_to_dict(self.model_object), {})
        deepcopy_mock.assert_called_once_with(self.model_object.__dict__)


class TestExternalMultipleLaunchUrlsEnabled(TestCase):
    """
    Tests for the external_multiple_launch_urls_enabled function.
    """

    @patch("lti_consumer.utils.get_external_multiple_launch_urls_waffle_flag")
    def test_flag_enabled(self, mock_waffle_flag):
        """
        Test that the function returns True when the waffle flag is enabled.
        """
        mock_waffle_flag.return_value.is_enabled.return_value = True
        course_key = CourseLocator(org="test_org", course="test_course", run="test_run")

        result = external_multiple_launch_urls_enabled(course_key)

        self.assertTrue(result)
        mock_waffle_flag.return_value.is_enabled.assert_called_once_with(course_key)

    @patch("lti_consumer.utils.get_external_multiple_launch_urls_waffle_flag")
    def test_flag_disabled(self, mock_waffle_flag):
        """
        Test that the function returns False when the waffle flag is disabled.
        """
        mock_waffle_flag.return_value.is_enabled.return_value = False
        course_key = CourseLocator(org="test_org", course="test_course", run="test_run")
        result = external_multiple_launch_urls_enabled(course_key)

        self.assertFalse(result)
        mock_waffle_flag.return_value.is_enabled.assert_called_once_with(course_key)
