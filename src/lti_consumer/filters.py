"""
Module that contains the openedx filters for this XBlock
"""
from typing import Dict

from openedx_filters.tooling import OpenEdxPublicFilter


class LTIConfigurationListed(OpenEdxPublicFilter):
    """
    Filter used to fetch LTI Tools configurations to be used in the LTI Consumer
    XBlock
    """

    filter_type = "org.openedx.xblock.lti_consumer.configuration.listed.v1"

    @classmethod
    def run_filter(cls, context: Dict, config_id: str, configurations: Dict):
        """
        Execute the filter with the signature specified.

        Arguments:
            context (dict): context dictionary of the LTI Consumer XBlock view
            config_id (str): configuration ID to get a specific configuration
            configurations (str): a map of plugin specific config ids and the configuration dicts
        """
        data = super().run_pipeline(context=context, config_id=config_id, configurations=configurations)
        return data.get("context"), data.get("config_id"), data.get("configurations")


def get_external_config_from_filter(context, config_id=''):
    """
    Thin wrapper around the LTIConfigurationListed filter to get the external
    configuration values using a certain context and config_id.
    """
    # .. filter: org.openedx.xblock.lti_consumer.configuration.listed.v1
    _, _, configurations = LTIConfigurationListed.run_filter(context=context, config_id=config_id, configurations={})
    if config_id:
        return configurations.get(config_id, {})
    return configurations
