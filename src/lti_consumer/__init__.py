"""
Runtime will load the XBlock class from here.
"""
from importlib.metadata import version

from .apps import LTIConsumerApp
from .lti_xblock import LtiConsumerXBlock

__version__ = version("lti-consumer-xblock")
