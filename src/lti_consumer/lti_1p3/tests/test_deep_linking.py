"""
Unit tests for LTI 1.3 consumer implementation
"""
from __future__ import absolute_import, unicode_literals
from unittest.mock import patch

from django.test.testcases import TestCase
from lti_consumer.lti_1p3.constants import LTI_DEEP_LINKING_ACCEPTED_TYPES
from lti_consumer.lti_1p3.deep_linking import LtiDeepLinking
from lti_consumer.lti_1p3 import exceptions


class TestLtiDeepLinking(TestCase):
    """
    Unit tests for LtiDeepLinking class
    """

    def setUp(self):
        """
        Instance Deep Linking Class for testing.
        """
        super().setUp()

        self.dl = LtiDeepLinking(
            deep_linking_launch_url="launch_url",
            deep_linking_return_url="return_url"
        )

    def test_invalid_claim_type(self):
        """
        Test DeepLinking claim when invalid type is passed.
        """
        with self.assertRaises(exceptions.LtiDeepLinkingContentTypeNotSupported):
            self.dl.get_lti_deep_linking_launch_claim(
                accept_types=['invalid_type']
            )

    def test_claim_type_validation(self):
        """
        Test that claims are correctly passed back by the class.
        """
        with patch(
            'lti_consumer.lti_1p3.deep_linking.LTI_DEEP_LINKING_ACCEPTED_TYPES',
            ['test']
        ):
            self.dl.get_lti_deep_linking_launch_claim(
                accept_types=['test']
            )

    def test_no_accepted_claim_types(self):
        """
        Test DeepLinking when no claim data is passed.
        """
        message = self.dl.get_lti_deep_linking_launch_claim(
            extra_data="deep_linking_hint"
        )

        self.assertEqual(
            {
                'https://purl.imsglobal.org/spec/lti-dl/claim/deep_linking_settings': {
                    'accept_types': LTI_DEEP_LINKING_ACCEPTED_TYPES,
                    'accept_presentation_document_targets': [
                        'iframe',
                        'window',
                        'embed'
                    ],
                    'accept_multiple': True,
                    'auto_create': True,
                    'title': '',
                    'text': '',
                    'deep_link_return_url': 'return_url',
                    'data': "deep_linking_hint",
                }
            },
            message,
        )
