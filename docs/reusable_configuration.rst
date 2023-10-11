##########################
LTI Reusable configuration
##########################

Currently, this library supports a mechanism that allows LTI configuration
pluggability and re-usability, this allows instructors to be able to re-use
LTI configuration values across multiple XBlocks, reducing the work a
instructor needs to do to set up an LTI consumer XBlock. This feature works
for both LTI 1.1 and LTI 1.3. This feature, in the case of LTI 1.3 greatly
reduces the work an instructor needs to dedicate to setting up multiple
XBlocks that use the same configuration, since all values, including the access
token and keyset URL, are shared across all XBlocks using the same
configuration, eliminating the need to have a tool deployment for each XBlock.

***********************
How to use this feature
***********************

Setup Openedx LTI Store
=======================

1. Install the openedx-ltistore plugin on the LMS and studio
   (https://github.com/open-craft/openedx-ltistore):

.. code-block:: bash

    make lms-shell
    pip install -e /edx/src/openedx-ltistore

2. Setup any existing openedx-filters configurations for both LMS and studio:

.. code-block:: python

    OPEN_EDX_FILTERS_CONFIG = {
        "org.openedx.xblock.lti_consumer.configuration.listed.v1": {
            "fail_silently": False,
            "pipeline": [
                "lti_store.pipelines.GetLtiConfigurations"
            ]
        }
    }

3. Restart the LMS & Studio for the latest config to take effect.

Setup course waffle flag
========================

1. Go to LMS admin > WAFFLE_UTILS > Waffle flag course override
   (http://localhost:18010/admin/waffle_utils/waffleflagcourseoverridemodel/).
2. Create a waffle flag course override with these values:
    - Waffle flag: lti_consumer.enable_external_config_filter
    - Course id: <your course id>
    - Override choice: Force On
    - Enabled: True

Create reusable LTI configuration
=================================

1. Go to LMS admin > LTI_STORE > External lti configurations
   (http://localhost:18010/admin/lti_store/externallticonfiguration/).
2. Create a new external LTI configuration.
3. On the list of external LTI configurations, note down the "Filter Key" value
   of the newly created configuration (Example: lti_store:1).

Setup LTI consumer XBlock on studio
===================================

1. Add "lti_consumer" to the "Advanced Module List" in
   the "Advanced Settings" of your course.
2. Add a new unit to the course and add "LTI Consumer"
   from the "Advanced" blocks.
3. Click the "Edit" button of the LTI Consumer block
   and set "Configuration Type" to "Reusable Configuration".
4. Set the "External configuration ID" to the filter key value we copied
   when we created the LTI configuration (Example: lti_store:1).
5. Click "Save".
6. (Optional) On an LTI 1.3 consumer XBlock, note down all the values
   you need to set up on the LTI tool.
6. Go to your live course and execute a launch.
7. That launch should work as expected.
