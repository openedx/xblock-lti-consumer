"""
Unit tests for lti_consumer.utils module
"""
from unittest.mock import Mock, patch

import ddt
from django.test.testcases import TestCase

from lti_consumer.lti_1p3.constants import LTI_1P3_CONTEXT_TYPE
from lti_consumer.utils import (
    get_lti_1p3_context_types_claim,
    get_lti_1p3_launch_data_cache_key,
    cache_lti_1p3_launch_data,
    get_data_from_cache,
)


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
