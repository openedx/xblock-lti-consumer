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
