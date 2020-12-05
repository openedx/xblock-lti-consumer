"""
Unit tests for LTI 1.3 consumer implementation
"""

from unittest.mock import MagicMock

import ddt
from Cryptodome.PublicKey import RSA
from django.test.testcases import TestCase

from lti_consumer.lti_1p3.consumer import LtiConsumer1p3
from lti_consumer.models import LtiConfiguration
from lti_consumer.lti_1p3.extensions.rest_framework.permissions import (
    LtiAgsPermissions,
    LtiNrpsContextMembershipsPermissions,
)


# Variables required for testing and verification
ISS = "http://test-platform.example/"
OIDC_URL = "http://test-platform/oidc"
LAUNCH_URL = "http://test-platform/launch"
CLIENT_ID = "1"
DEPLOYMENT_ID = "1"
NONCE = "1234"
STATE = "ABCD"
# Consider storing a fixed key
RSA_KEY_ID = "1"
RSA_KEY = RSA.generate(2048).export_key('PEM')


@ddt.ddt
class TestLtiAuthentication(TestCase):
    """
    Unit tests for Lti1p3ApiAuthentication class
    """
    def setUp(self):
        super().setUp()

        # Set up consumer
        self.lti_consumer = LtiConsumer1p3(
            iss=ISS,
            lti_oidc_url=OIDC_URL,
            lti_launch_url=LAUNCH_URL,
            client_id=CLIENT_ID,
            deployment_id=DEPLOYMENT_ID,
            rsa_key=RSA_KEY,
            rsa_key_id=RSA_KEY_ID,
            # Use the same key for testing purposes
            tool_key=RSA_KEY
        )

        # Create LTI Configuration
        self.lti_configuration = LtiConfiguration.objects.create(
            version=LtiConfiguration.LTI_1P3,
        )

        # Create mock request
        self.mock_request = MagicMock()
        self.mock_request.lti_consumer = self.lti_consumer

    def _make_token(self, scopes):
        """
        Return a valid token with the required scopes.
        """
        # Generate a valid access token
        return self.lti_consumer.key_handler.encode_and_sign(
            {
                "sub": self.lti_consumer.client_id,
                "iss": self.lti_consumer.iss,
                "scopes": " ".join(scopes),
            },
            expiration=3600
        )

    @ddt.data(
        (["https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly"], True),
        (["https://purl.imsglobal.org/spec/lti-ags/scope/lineitem"], True),
        (["https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly"], False),
        (["https://purl.imsglobal.org/spec/lti-ags/scope/score"], False),
        (
            [
                "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly",
                "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem",
            ],
            True
        ),
    )
    @ddt.unpack
    def test_read_only_lineitem_list(self, token_scopes, is_allowed):
        """
        Test if LineItem is readable when any of the allowed scopes is
        included in the token.
        """
        perm_class = LtiAgsPermissions()
        mock_view = MagicMock()

        # Make token and include it in the mock request
        token = self._make_token(token_scopes)
        self.mock_request.headers = {
            "Authorization": f"Bearer {token}"
        }

        # Test list view
        mock_view.action = 'list'
        self.assertEqual(
            perm_class.has_permission(self.mock_request, mock_view),
            is_allowed,
        )

        # Test retrieve view
        mock_view.action = 'retrieve'
        self.assertEqual(
            perm_class.has_permission(self.mock_request, mock_view),
            is_allowed,
        )

    def test_lineitem_no_permissions(self):
        """
        Test if LineItem is readable when any of the allowed scopes is
        included in the token.
        """
        perm_class = LtiAgsPermissions()
        mock_view = MagicMock()

        # Make token and include it in the mock request
        token = self._make_token([])
        self.mock_request.headers = {
            "Authorization": f"Bearer {token}"
        }

        # Test list view
        mock_view.action = 'list'
        self.assertFalse(
            perm_class.has_permission(self.mock_request, mock_view),
        )

        # Test retrieve view
        mock_view.action = 'retrieve'
        self.assertFalse(
            perm_class.has_permission(self.mock_request, mock_view),
        )

    @ddt.data(
        (["https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly"], False),
        (["https://purl.imsglobal.org/spec/lti-ags/scope/lineitem"], True),
        (["https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly"], False),
        (["https://purl.imsglobal.org/spec/lti-ags/scope/score"], False),
        (
            [
                "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly",
                "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem",
            ],
            True
        ),
    )
    @ddt.unpack
    def test_lineitem_write_permissions(self, token_scopes, is_allowed):
        """
        Test if write operations on LineItem are allowed with the correct token.
        """
        perm_class = LtiAgsPermissions()
        mock_view = MagicMock()

        # Make token and include it in the mock request
        token = self._make_token(token_scopes)
        self.mock_request.headers = {
            "Authorization": f"Bearer {token}"
        }

        for action in ['create', 'update', 'partial_update', 'delete']:
            # Test list view
            mock_view.action = action
            self.assertEqual(
                perm_class.has_permission(self.mock_request, mock_view),
                is_allowed
            )

    def test_unregistered_action_not_allowed(self):
        """
        Test unauthorized when trying to post to unregistered action.
        """
        perm_class = LtiAgsPermissions()
        mock_view = MagicMock()

        # Make token and include it in the mock request
        token = self._make_token([])
        self.mock_request.headers = {
            "Authorization": f"Bearer {token}"
        }

        # Test list view
        mock_view.action = 'invalid-action'
        self.assertFalse(
            perm_class.has_permission(self.mock_request, mock_view),
        )

    @ddt.data(
        (["https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly"], False),
        (["https://purl.imsglobal.org/spec/lti-ags/scope/lineitem"], False),
        (["https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly"], True),
        (["https://purl.imsglobal.org/spec/lti-ags/scope/score"], False),
    )
    @ddt.unpack
    def test_results_action_permissions(self, token_scopes, is_allowed):
        """
        Test if write operations on LineItem are allowed with the correct token.
        """
        perm_class = LtiAgsPermissions()
        mock_view = MagicMock()

        # Make token and include it in the mock request
        token = self._make_token(token_scopes)
        self.mock_request.headers = {
            "Authorization": f"Bearer {token}"
        }

        # Test results view
        mock_view.action = 'results'
        self.assertEqual(
            perm_class.has_permission(self.mock_request, mock_view),
            is_allowed,
        )

    @ddt.data(
        (["https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly"], False),
        (["https://purl.imsglobal.org/spec/lti-ags/scope/lineitem"], False),
        (["https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly"], False),
        (["https://purl.imsglobal.org/spec/lti-ags/scope/score"], True),
    )
    @ddt.unpack
    def test_scores_action_permissions(self, token_scopes, is_allowed):
        """
        Test if write operations on LineItem are allowed with the correct token.
        """
        perm_class = LtiAgsPermissions()
        mock_view = MagicMock()

        # Make token and include it in the mock request
        token = self._make_token(token_scopes)
        self.mock_request.headers = {
            "Authorization": f"Bearer {token}"
        }

        # Test scores view
        mock_view.action = 'scores'
        self.assertEqual(
            perm_class.has_permission(self.mock_request, mock_view),
            is_allowed,
        )

    @ddt.data(
        (["https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly"], True),
        ([], False),
    )
    @ddt.unpack
    def test_nrps_membership_permissions(self, token_scopes, is_allowed):
        """
        Test if LTI NRPS Context membership endpoint is availabe for correct token.
        """
        perm_class = LtiNrpsContextMembershipsPermissions()

        mock_view = MagicMock()

        # Make token and include it in the mock request
        token = self._make_token(token_scopes)
        self.mock_request.headers = {
            "Authorization": "Bearer {}".format(token)
        }

        # Test scores view
        mock_view.action = 'list'
        self.assertEqual(
            perm_class.has_permission(self.mock_request, mock_view),
            is_allowed,
        )
