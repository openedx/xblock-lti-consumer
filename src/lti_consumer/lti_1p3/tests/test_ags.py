"""
Unit tests for LTI 1.3 consumer implementation
"""

from django.test.testcases import TestCase

from lti_consumer.lti_1p3.ags import LtiAgs


class TestLtiAgs(TestCase):
    """
    Unit tests for LtiAgs class
    """
    def test_instance_ags_no_permissions(self):
        """
        Test enabling LTI AGS with no permissions.
        """
        ags = LtiAgs(
            "http://example.com/lineitem",
            allow_creating_lineitems=False,
            results_service_enabled=False,
            scores_service_enabled=False
        )
        scopes = ags.get_available_scopes()

        # Disabling all permissions will only allow the tool to
        # list and retrieve LineItems
        self.assertEqual(
            scopes,
            ['https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly'],
        )

    def test_instance_ags_all_permissions(self):
        """
        Test enabling LTI AGS with all permissions.
        """
        ags = LtiAgs(
            "http://example.com/lineitem",
            allow_creating_lineitems=True,
            results_service_enabled=True,
            scores_service_enabled=True
        )
        scopes = ags.get_available_scopes()

        # Check available scopes
        self.assertIn('https://purl.imsglobal.org/spec/lti-ags/scope/lineitem', scopes)
        self.assertIn('https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly', scopes)
        self.assertIn('https://purl.imsglobal.org/spec/lti-ags/scope/score', scopes)

    def test_get_lti_ags_launch_claim(self):
        """
        Test if the launch claim is properly formed
        """
        ags = LtiAgs(
            "http://example.com/lineitem",
            allow_creating_lineitems=False,
            results_service_enabled=False,
            scores_service_enabled=False
        )

        self.assertEqual(
            ags.get_lti_ags_launch_claim(),
            {
                "https://purl.imsglobal.org/spec/lti-ags/claim/endpoint": {
                    "scope": [
                        "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly"
                    ],
                    "lineitems": "http://example.com/lineitem",
                }
            }
        )
