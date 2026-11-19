"""
Exceptions for the LTI Consumer.
"""


class LtiError(Exception):
    """
    General error class for LTI Consumer usage.
    """


class ExternalConfigurationNotFound(Exception):
    """
    This exception is used  when a reusable external configuration
    is not found for a given external ID.
    """


class ReusableConfigurationError(Exception):
    """Framework-independent failure for reusable configuration operations.

    Category is one of invalid, conflict, forbidden or not_found. Field is an
    optional dotted member address, for example context.key or lti_1p3.oidc_url.
    Message wording is not contract; adapters translate the category and field
    address into HTTP responses.
    """

    def __init__(self, category, messages, field=None):
        if isinstance(messages, (list, tuple)):
            messages = list(messages)
        else:
            messages = [messages]
        self.category = category
        self.field = field
        self.messages = [str(message) for message in messages]
        super().__init__(*self.messages)
