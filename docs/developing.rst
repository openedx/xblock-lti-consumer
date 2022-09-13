LTI Consumer Implementations
============================

`LTI 1.1`_

`LTI 1.3`_

Custom LTI Parameters
=====================

This XBlock sends a number of parameters to the provider including some optional parameters. To keep the XBlock
somewhat minimal, some parameters were omitted like ``lis_person_name_full`` among others.
At the same time the XBlock allows passing extra parameters to the LTI provider via parameter processor functions.

Defining an LTI Parameter Processor
-----------------------------------

The parameter processor is a function that expects an XBlock instance, and returns a ``dict`` of
additional parameters for the LTI.
If a processor throws an exception, the exception is logged and suppressed.
If a processor returns ``None`` or any falsy value, no parameters will be added.

.. code:: python

    def team_info(xblock):
        course = get_team(xblock.user, lti_params.course.id)
        if not course:
            return

        return {
            'custom_course_id': unicode(course.id),
            'custom_course_name': course.name,
        }

A processor can define a list of default parameters ``lti_xblock_default_params``,
which is useful in case the processor had an exception.

It is recommended to define default parameters anyway, because it can simplify the implementation of the processor
function. Below is an example:

.. code:: python

    def dummy_processor(xblock):
        course = get_team(xblock.user, lti_params.course.id)  # If something went wrong default params will be used
        if not course:
            return  # Will use the default params

        return {
            'custom_course_id': unicode(course.id),
            'custom_course_name': course.name,
        }

    dummy_processor.lti_xblock_default_params = {
        'custom_course_id': '',
        'custom_course_name': '',
    }

If you're looking for a more realistic example, you can check the
`Tahoe LTI <https://github.com/appsembler/tahoe-lti>`_ repository at the
`Appsembler GitHub organization <https://github.com/appsembler/>`_.

Configuring the Parameter Processors Settings
---------------------------------------------

Using the standard XBlock settings interface the developer can provide a list of processor functions:
Those parameters are not sent by default. The course author can enable that on per XBlock instance
(aka module) by setting the **Send extra parameters** to ``true`` in Studio.

To configure parameter processors add the following snippet to your Ansible variable files:

.. code:: yaml

    EDXAPP_XBLOCK_SETTINGS:
      lti_consumer:
        parameter_processors:
          - 'customer_package.lti_processors:team_and_cohort'
          - 'example_package.lti_processors:extra_lti_params'

Dynamic LTI Custom Parameters
=============================

This XBlock gives us the capability to attach static and dynamic custom parameters in the custom parameters field,
in the case we need to declare a dynamic custom parameter we must set the value of the parameter as a templated parameter
wrapped with the tags '${' and '}' just like the following example:

.. code:: python

    ["static_param=static_value", "dynamic_custom_param=${templated_param_value}"]

Defining a dynamic LTI Custom Parameter Processor
-------------------------------------------------

The custom parameter processor is a function that expects an XBlock instance, and returns a ``string`` which should be the resolved value.
Exceptions must be handled by the processor itself.

.. code:: python

    def get_course_name(xblock):
        try:
            course = CourseOverview.objects.get(id=xblock.course.id)
        except CourseOverview.DoesNotExist:
            log.error('Course does not exist.')
            return ''

        return course.display_name

Note. The processor function must return a ``string`` object.

Configuring the LTI Dynamic Custom Parameters Settings
------------------------------------------------------

The setting LTI_CUSTOM_PARAM_TEMPLATES must be set in order to map the template value for the dynamic custom parameter
as the following example:

.. code:: python

    LTI_CUSTOM_PARAM_TEMPLATES = {
        'templated_param_value': 'customer_package.module:func',
    }

* 'templated_param_value': custom parameter template name.
* 'customer_package.module:func': custom parameter processor path and function name.