"""
LTI Proctoring Service implementation
"""


class LtiProctoring:
    """
    LTI 1.3 - Proctoring Services

    Reference:
    http://www.imsproject.org/spec/proctoring/v1p0
    """
    def __init__(
        self,
        attempt_number,
        session_data,
        resource_link,
        start_assessment_url=None,
    ):
        """
        Class initialization.
        """
        self.attempt_number = attempt_number
        self.session_data = session_data
        self.resource_link = resource_link
        self.start_assessment_url = start_assessment_url

    def _get_lti_proctoring_base_claims(self):
        """
        Returns claims common to all LTI Proctoring Services LTI launch messages, to be used when creating LTI launch
        messages.
        """
        proctoring_claims = {
            "https://purl.imsglobal.org/spec/lti-ap/claim/attempt_number": self.attempt_number,
            "https://purl.imsglobal.org/spec/lti-ap/claim/session_data": self.session_data,
        }

        return proctoring_claims

    def get_lti_proctoring_start_proctoring_claims(self):
        """
        Returns claims specific to LTI Proctoring Services LtiStartProctoring LTI launch message,
        to be injected into the LTI launch message.
        """
        proctoring_claims = self._get_lti_proctoring_base_claims()
        proctoring_claims.update({
            "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiStartProctoring",
            "https://purl.imsglobal.org/spec/lti-ap/claim/start_assessment_url": self.start_assessment_url,
        })

        return proctoring_claims

    def get_lti_proctoring_end_assessment_claims(self):
        """
        Returns claims specific to LTI Proctoring Services LtiEndAssessment LTI launch message,
        to be injected into the LTI launch message.
        """
        proctoring_claims = self._get_lti_proctoring_base_claims()
        proctoring_claims.update({
            "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiEndAssessment",
        })

        return proctoring_claims
