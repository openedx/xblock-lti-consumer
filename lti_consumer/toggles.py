"""
Toggles for the xblock-lti-consumer library
"""
from edx_toggles.toggles import WaffleFlag

from lti_consumer.constants import WAFFLE_NAMESPACE

# Waffle Flags
# .. toggle_name: lti_consumer.enable_database_config
# .. toggle_implementation: CourseWaffleFlag
# .. toggle_default: False
# .. toggle_description: Enables storing and fetching LTI configuration from the database. This should only be enabled
#                        staff members. We do not want to expose the difference between "CONFIG_ON_DB" and
#                        CONFIG_ON_XBLOCK to non-staff Studio users. This flag is provided to allow staff Studio users
#                        to test and setup LTI configurations stored in the database.
# .. toggle_use_cases: open_edx
# .. toggle_creation_date: 2022-06-29
# .. toggle_warning: None.
ENABLE_DATABASE_CONFIG = 'enable_database_config'


def get_database_config_waffle_flag():
    return WaffleFlag(f'{WAFFLE_NAMESPACE}.{ENABLE_DATABASE_CONFIG}', __name__)
