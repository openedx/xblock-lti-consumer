Pluggable and re-usable LTI configuration
-----------------------------------------


Status
======

Proposal

Context
=======

LTI Tools provide extra funcionality and allows course creators to embed external interactive content
in the LMS through a standardized setup.

Currently in the Open edX platform:

* Each LTI tool needs to be configured individually, sometimes requiring multiple valiables to be set to get a working integration. This makes the course creation process cumbersome on courses that heavily rely on LTI components.
* There's no support for instance-wide LTI tool configuration or any sort of pluggable LTI configurations.

This proposal aims to solve these issues by introducing a mechanism to allow LTI configuration pluggability 
and changes to the XBlock to allow re-using configurations to reduce instructor friction.


Decision
========

The decision is to enable LTI reusability and pluggability using a filter hook (as defined in `OEP-50`_) to fetch re-usable LTI configurations
from external plugins. 

With this implementation the plugins are responsible for storing the LTI configuration and credentials, while the LTI consumer handles displaying the content.

To enable this, the LTI Configuration model needs to be modified to:

#. Allow externally configured tools (a new :code:`CONFIG_EXTERNAL` choice for the configuration storage).
#. A new fields to store an namespaced tools id in the format (:code:`plugin_name:identifier`).
#. Changes to the :code:`get_lti_consumer` methods to allow instancing a :code:`LtiConsumer` from externally managed configurations.

The filter will allow the XBlock LTI Consumer to query re-usable and/or plugabble LTI configurations and display them to course 
creators as configuration options in Studio. 
The filter response should contain all the necessary information for the XBlock to locate and and use the externally managed LTI configuration.

The inputs for the filter pipeline should be:

* The course ID, so that each filter is able to evaluate and return only configurations available to that context.
* A dictionary in which LTI configurations will be added/modified by each plugin. 

Filter responses are accumulative and receive the output of the previous function (`Filter tooling - pipeline behaviour`_),
so the filters will initially recieve an empty dictionary and each filter will incrementally add its available configurations,
using a namespaced key with the plugin name plus an internal identifier (Example: :code:`lti_plugin_1:random-identifier`).

1. Initial state of filter input

.. code-block:: json

    {}


2. After the first filter is run:

.. code-block:: json

    {
        "lti_plugin_1:a-plugin-interal-indentifier": {
            "lti_version": "LTI_1P1",
            "lti_1p1_client_key": "LTI KEY",
            "lti_1p1_client_secret": "LTI SECRET",
            "launch_url": "https://saltire.lti.app/tool",
            "tool_name": "Saltire LTI test tool",
        },
        "lti_plugin_1:another-indentifier": {
            ...
        }
    }

This filter has two purposes:

#. Allow the XBlock LTI Consumer to display users a list of available re-usable configurations.
#. Return LTI configuration data so that the LTI Consumer is able to spawn a `LtiConsumer` class.

When an user launches a re-usable configuration, the LTI consumer model will run the filter pipeline, retrieve the credentials if they are available,
instance the appropriate :code:`LtiConsumer` and return it to the XBlock for usage.

Related feature flags
=====================

.. list-table::
   :widths: auto
   :header-rows: 1

   * - Toggle name
     - Type
     - Behavior
   * - LTI_ENABLE_REUSABLE_CONFIGURATIONS
     - Feature flag
     - This flag enables LTI Configuration reusability and will display an extra field during the LTI 
       configuration that will allow selection from pre-set configurations.


Changes to the LTI Consumer XBlock
==================================

To allow re-usability, the XBlock will need the following changes:

#. An extra configuration type will need to be added to the *LTI Version field*: :code:`Use predefined LTI configuration`
#. When the option above is selected, a new field must be presented so that the user can pick one of the available re-usable configurations.
#. The methods to retrieve the LTI consumer will need to be reworked to factor in re-usable configurations.
#. Some LTI endpoints that are tied to the XBlock will need to be decoupled from the XBlock runtime urls to remove :code:`LocationKey` dependencies.


Implementation concerns/Consequences
====================================

#. The `LtiConfiguration` model needs to be decoupled from XBlocks so that grades and student information don't get mixed between instances.

.. _OEP-50: https://open-edx-proposals.readthedocs.io/en/latest/architectural-decisions/oep-0050-hooks-extension-framework.html
.. _Filter tooling - pipeline behaviour: https://github.com/eduNEXT/openedx-filters/blob/main/docs/decisions/0003-hooks-filter-tooling-pipeline.rst