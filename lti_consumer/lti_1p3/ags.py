"""
LTI Advantage Assignments and Grades service implementation
"""


class LtiAgs:
    """
    LTI Advantage Consumer

    Implements LTI Advantage Services and ties them in
    with the LTI Consumer. This only handles the LTI
    message claim inclusion and token handling.

    Available services:
    * Assignments and Grades services (partial support)

    Reference: https://www.imsglobal.org/lti-advantage-overview
    """
    def __init__(
        self,
        lineitems_url,
        lineitem_url=None,
        allow_creating_lineitems=True,
        results_service_enabled=True,
        scores_service_enabled=True,
    ):
        """
        Instance class with LTI AGS Global settings.
        """
        # If the platform allows creating lineitems, set this
        # to True.
        self.allow_creating_lineitems = allow_creating_lineitems

        # Result and scores services
        self.results_service_enabled = results_service_enabled
        self.scores_service_enabled = scores_service_enabled

        # Lineitems urls
        self.lineitems_url = lineitems_url
        self.lineitem_url = lineitem_url

    def get_available_scopes(self):
        """
        Retrieves list of available token scopes in this instance.
        """
        scopes = []

        if self.allow_creating_lineitems:
            scopes.append('https://purl.imsglobal.org/spec/lti-ags/scope/lineitem')
        else:
            scopes.append('https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly')

        if self.results_service_enabled:
            scopes.append('https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly')

        if self.scores_service_enabled:
            scopes.append('https://purl.imsglobal.org/spec/lti-ags/scope/score')

        return scopes

    def get_lti_ags_launch_claim(self):
        """
        Returns LTI AGS Claim to be injected in the LTI launch message.
        """

        claim_values = {
            "scope": self.get_available_scopes(),
            "lineitems": self.lineitems_url,
        }

        if self.lineitem_url:
            claim_values["lineitem"] = self.lineitem_url

        return {
            "https://purl.imsglobal.org/spec/lti-ags/claim/endpoint": claim_values,
        }
