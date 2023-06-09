""""
Tests for LTI 1.3 proctoring endpoint views.
"""
import uuid
from unittest.mock import call, patch

import ddt
from Cryptodome.PublicKey import RSA
from django.contrib.auth import get_user_model
from django.test.testcases import TestCase
from edx_django_utils.cache import TieredCache, get_cache_key
from jwkest.jwk import RSAKey
from jwkest.jwt import BadSyntax

from lti_consumer.data import Lti1p3LaunchData, Lti1p3ProctoringLaunchData
from lti_consumer.lti_1p3.exceptions import (BadJwtSignature, InvalidClaimValue, MalformedJwtToken,
                                             MissingRequiredClaim, NoSuitableKeys)
from lti_consumer.lti_1p3.key_handlers import PlatformKeyHandler
from lti_consumer.models import LtiConfiguration
from lti_consumer.utils import get_data_from_cache


@ddt.ddt
class TestLti1p3ProctoringStartProctoringAssessmentEndpoint(TestCase):
    """Tests for the start_proctoring_assessment_endpoint endpoint."""

    def setUp(self):
        super().setUp()

        self.url = "/lti_consumer/v1/start_proctoring_assessment"

        # Set up user.
        self._setup_user()

        # Set up an LtiConfiguration instance for the integration.
        self.lti_config = LtiConfiguration.objects.create(
            version=LtiConfiguration.LTI_1P3,
            lti_1p3_proctoring_enabled=True,
            config_store=LtiConfiguration.CONFIG_ON_DB,
        )

        # Set up cached data necessary for this endpoint: launch_data and session_data.
        self._setup_cached_data()

        # Set up a public key - private key pair that allows encoding and decoding a Tool JWT.
        self.rsa_key_id = str(uuid.uuid4())
        self.private_key = RSA.generate(2048)
        self.key = RSAKey(
            key=self.private_key,
            kid=self.rsa_key_id
        )
        self.public_key = self.private_key.publickey().export_key().decode()

        self.lti_config.lti_1p3_tool_public_key = self.public_key
        self.lti_config.save()

    def _setup_user(self):
        """Sets up the requesting user instance."""
        self.user = get_user_model().objects.create_user(
            username="user",
            password="password"
        )
        self.client.login(username="user", password="password")

    def _setup_cached_data(self):
        """Sets up data in the cache necessary for the view: launch_data and session_data."""
        self.common_cache_key_arguments = {
            "app": "lti",
            "user_id": self.user.id,
            "resource_link_id": "resource_link_id",
        }

        # Cache session_data.
        self.session_data_key = get_cache_key(
            **self.common_cache_key_arguments,
            key="session_data"
        )
        TieredCache.set_all_tiers(self.session_data_key, "session_data")

        # Cache launch_data.
        proctoring_launch_data = Lti1p3ProctoringLaunchData(attempt_number=2)
        launch_data = Lti1p3LaunchData(
            user_id="1",
            user_role=None,
            config_id=self.lti_config.config_id,
            resource_link_id="resource_link_id",
            proctoring_launch_data=proctoring_launch_data,
            context_id="course-v1:testU+DemoX+Demo_Course",
            context_title="http://localhost:2000",
            context_label="block-v1:testU+DemoX+Demo_Course+type@sequential+block@1234",
        )

        self.launch_data_key = get_cache_key(
            **self.common_cache_key_arguments,
            key="launch_data"
        )
        TieredCache.set_all_tiers(self.launch_data_key, launch_data)

    def create_tool_jwt_token(self, **kwargs):
        """
        Creates and returns a signed JWT token to act as a Tool JWT.

        Arguments:
            * kwargs: Keyword arguments representing key, value pairs to include in the JWT token. This allows callers
                to override default claims in the JWT token.
        """
        lti_consumer = self.lti_config.get_lti_consumer()

        token = {
            "iss": lti_consumer.client_id,
            "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiStartAssessment",
            "https://purl.imsglobal.org/spec/lti/claim/version": "1.3.0",
            "https://purl.imsglobal.org/spec/lti-ap/claim/session_data": "session_data",
            "https://purl.imsglobal.org/spec/lti/claim/resource_link": {"id": "resource_link_id"},
            "https://purl.imsglobal.org/spec/lti-ap/claim/attempt_number": 2,
        }

        token.update(**kwargs)

        # Encode and sign the Tool JWT using the private key. The PlatformKeyHandler class is the only key handler that
        # currently has code to encode and sign a JWT, so we use that class. The ToolKeyHandler will be used in the view
        # to decode this JWT using the corresponding public key.
        platform_key_handler = PlatformKeyHandler(self.private_key.export_key(), self.rsa_key_id)
        signed_token = platform_key_handler.encode_and_sign(token)

        return signed_token

    def test_valid_token(self):
        """Tests the happy path of the start_proctoring_assessment_endpoint."""
        response = self.client.post(
            self.url,
            {
                "JWT": self.create_tool_jwt_token()
            },
        )
        self.assertEqual(response.status_code, 200)

    def test_unparsable_token(self):
        """Tests that a call to the start_assessment_endpoint with an unparsable token results in a 400 response."""
        with patch("lti_consumer.plugin.views.JWT.unpack") as mock_jwt_unpack_method:
            mock_jwt_unpack_method.side_effect = BadSyntax(value="", msg="")

            response = self.client.post(
                self.url,
                {
                    "JWT": self.create_tool_jwt_token()
                },
            )
            self.assertEqual(response.status_code, 400)

    def test_lti_configuration_does_not_exist(self):
        """
        Tests that a call to the start_assessment_endpoint with an "iss" Tool JWT token claim that does not correspond
        to an LtiConfiguration instance results in a 404 response.
        """
        tool_jwt_token_overrides = {"iss": "iss"}
        tool_jwt_token = self.create_tool_jwt_token(**tool_jwt_token_overrides)

        response = self.client.post(
            self.url,
            {
                "JWT": tool_jwt_token
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_not_proctoring_consumer(self):
        """
        Tests that a call to the start_assessment_endpoint with an "iss" Tool JWT token claim that corresponds to
        an LtiConfiguration instance that does not have proctoring enabled results in a 400 response.
        """
        # Disable LTI Assessment and Grades Services so we don't set it up unnecessarily. Otherwise, an exception is
        # raised because there is no location field set on the LtiConfiguration instance.
        with patch("lti_consumer.models.LtiConfiguration.get_lti_advantage_ags_mode") as get_lti_ags_mode_mock:
            get_lti_ags_mode_mock.return_value = self.lti_config.LTI_ADVANTAGE_AGS_DISABLED
            self.lti_config.lti_1p3_proctoring_enabled = False
            self.lti_config.save()

            response = self.client.post(
                self.url,
                {
                    "JWT": self.create_tool_jwt_token()
                },
            )
            self.assertEqual(response.status_code, 400)

    def test_cache_miss_launch_data(self):
        """Tests that a call to the start_assessment_endpoint with no cached launch_data results in a 400 response."""
        TieredCache.set_all_tiers(self.launch_data_key, None)

        response = self.client.post(
            self.url,
            {
                "JWT": self.create_tool_jwt_token()
            },
        )
        self.assertEqual(response.status_code, 400)

    @ddt.data(BadJwtSignature, InvalidClaimValue, MalformedJwtToken, MissingRequiredClaim, NoSuitableKeys)
    def test_check_and_decode_token_exception_handling(self, exception):
        """Tests that a call to the start_assessment_endpoint with an invalid token results in a 400 response."""
        with patch("lti_consumer.lti_1p3.consumer.LtiProctoringConsumer.check_and_decode_token") as mock_method:
            mock_method.side_effect = exception()

            response = self.client.post(
                self.url,
                {
                    "JWT": self.create_tool_jwt_token()
                },
            )
            self.assertEqual(response.status_code, 400)

    def test_cached_end_assessment_return_valid(self):
        """
        Tests that a call to the start_assessment_endpoint with a valid end_assessment_return Tool JWT token claim
        results in a 200 response and correct data in the cache.
        """
        end_assessment_return = True

        tool_jwt_token_overrides = {
            "https://purl.imsglobal.org/spec/lti-ap/claim/end_assessment_return": end_assessment_return,
        }
        tool_jwt_token = self.create_tool_jwt_token(**tool_jwt_token_overrides)

        response = self.client.post(
            self.url,
            {
                "JWT": tool_jwt_token
            },
        )

        self.assertEqual(response.status_code, 200)

        end_assessment_return_cache_key = get_cache_key(**self.common_cache_key_arguments, key="end_assessment_return")
        end_assessment_return = get_data_from_cache(end_assessment_return_cache_key)
        self.assertEqual(end_assessment_return, int(end_assessment_return))

    def test_cached_end_assessment_return_invalid(self):
        """
        Tests that a call to the start_assessment_endpoint with an invalid end_assessment_return Tool JWT token claim
        results in a 200 response and correct data in the cache.
        """
        end_assessment_return = "end_assessment_return"

        tool_jwt_token_overrides = {
            "https://purl.imsglobal.org/spec/lti-ap/claim/end_assessment_return": end_assessment_return,
        }
        tool_jwt_token = self.create_tool_jwt_token(**tool_jwt_token_overrides)

        response = self.client.post(
            self.url,
            {
                "JWT": tool_jwt_token
            },
        )

        self.assertEqual(response.status_code, 200)

        end_assessment_return_cache_key = get_cache_key(**self.common_cache_key_arguments, key="end_assessment_return")
        end_assessment_return = get_data_from_cache(end_assessment_return_cache_key)
        self.assertEqual(end_assessment_return, None)

    @patch("lti_consumer.plugin.views.LTI_1P3_PROCTORING_ASSESSMENT_STARTED.send")
    def test_lti_1p3_proctoring_assessment_started_signal(self, mock_assessment_started_signal):
        """
        Tests that a successful call to the start_assessment_endpoint emits the LTI_1P3_PROCTORING_ASSESSMENT_STARTED
        Django signal.
        """
        self.client.post(
            self.url,
            {
                "JWT": self.create_tool_jwt_token()
            },
        )

        self.assertTrue(mock_assessment_started_signal.called)
        self.assertEqual(mock_assessment_started_signal.call_count, 1)

        expected_call_args = call(
            sender=None,
            attempt_number=2,
            resource_link={'id': 'resource_link_id'},
            user_id=self.user.id,
        )
        self.assertEqual(mock_assessment_started_signal.call_args, expected_call_args)

    def test_start_assessment_endpoint_returns_valid_html(self):
        """
        Tests that a successful call to the start_assessment_endpoint returns the correct html response.
        """
        response = self.client.post(
            self.url,
            {
                "JWT": self.create_tool_jwt_token()
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('Return to exam', response.content.decode('utf-8'))
