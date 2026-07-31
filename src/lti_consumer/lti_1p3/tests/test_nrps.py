"""
Unit tests for LTI 1.3 NRPS claim implementation
"""
from __future__ import absolute_import, unicode_literals

from django.test.testcases import TestCase

from lti_consumer.lti_1p3.nprs import LtiNrps


class TestLtiNrps(TestCase):
    """
    Unit tests for LtiNrps class
    """
    def test_get_available_scopes(self):
        """
        Test if proper scopes are returned.
        """
        nrps = LtiNrps(
            "http://example.com/20/membership"
        )
        scopes = nrps.get_available_scopes()

        self.assertEqual(
            scopes,
            ['https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly'],
        )

    def test_get_lti_nrps_launch_claim(self):
        """
        Test if the launch claim is properly formed
        """
        context_memberships_url = "http://example.com/20/membership"

        ags = LtiNrps(
            context_memberships_url,
        )

        self.assertEqual(
            ags.get_lti_nrps_launch_claim(),
            {
                "https://purl.imsglobal.org/spec/lti-nrps/claim/namesroleservice": {
                    "context_memberships_url": context_memberships_url,
                    "service_versions": ["2.0"]
                }
            }
        )
