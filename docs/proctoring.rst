#######################
LTI Proctoring Features
#######################

Using LTI Proctoring Features
*****************************

Currently, this library supports a subset of the functionality in the `1EdTech Proctoring Services Specification
<http://www.imsglobal.org/spec/proctoring/v1p0>`_. It supports the Proctoring Assessment Messages (i.e. the in-browser
LTI proctoring launches), but it does not support the Assessment Control Service (i.e. the proctoring service calls).
These proctoring features are currently only supported for LTI integrations using the ``CONFIG_ON_DB`` ``config_store``
option.

To enable LTI Proctoring features, you need to set the **Enable LTI Proctoring Services** field of the
``LtiConfiguration`` model to ``True``.

To start an LTI 1.3 launch with the ``LtiStartProctoring`` or ``LtiEndAssessment`` LTI message, you need to call
the ``get_lti_1p3_launch_start_url`` Python API function with the appropriate arguments. You will need to make a request against the URL
returned by this function. The ``launch_data`` argument will contain all data necessary for the LTI 1.3 launch. The
``launch_data`` argument must be an instance of the ``Lti1p3LaunchData`` data class. In order to support the proctoring
features, you must also supply a value for the ``proctoring_launch_data`` field of the ``Lti1p3LaunchData`` class. The
``proctoring_launch_data`` argument must be an instance of the ``Lti1p3ProctoringLaunchData`` class.

LTI Start Proctoring Launch
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Below is an example instantiation of the ``Lti1p3LaunchData`` class for an ``LtiStartProctoring`` LTI message. Please
see the docstring of both data classes for more detailed documentation.

This library implements the view that handles the ``LtiStartAssessment`` LTI message that is sent by the tool. The name
of the URL for this view is ``lti_consumer.start_proctoring_assessment_endpoint``. You should use this URL as the
``start_assessment_url``.

.. code:: python

    proctoring_start_assessment_url = urljoin(
            <URL_ROOT>,
            reverse('lti_consumer:lti_consumer.start_proctoring_assessment_endpoint')
        )

    proctoring_launch_data = Lti1p3ProctoringLaunchData(
        attempt_number=<attempt_number>,
        start_assessment_url=proctoring_start_assessment_url,
    )

    launch_data = Lti1p3LaunchData(
        user_id=<user_id>,
        user_role=<user_role>,
        config_id=<config_id>,
        resource_link_id=<resource_link_id>,
        message_type="LtiStartProctoring",
        proctoring_launch_data=proctoring_launch_data,
    )

    return redirect(get_lti_1p3_launch_start_url(launch_data))


Note that for an ``LtiStartProctoring`` LTI launch message, the ``message_type`` field of the ``Lti1p3LaunchData``
instance must be ``LtiStartProctoring`` and the ``start_assessment_url`` field of the ``Lti1p3ProctoringLaunchData``
instance must be supplied.

LTI End Assessment Launch
^^^^^^^^^^^^^^^^^^^^^^^^^

Below is an example instantiation of the ``Lti1p3LaunchData`` class for an ``LtiStartProctoring`` LTI message. Please
see the docstring of both data classes for more detailed documentation.

In order to determine whether the platform should send an ``LtiEndAssessment`` LTI message to the tool, you should use
the ``get_end_assessment_return`` Python API function. This will return a boolean representing whether the tool
requested that the platform send an ``LtiEndAssessment`` LTI message at the end of the proctored assessment.

.. code:: python

    end_assessment_return = get_end_assessment_return(<user_id>, <resource_link_id>)

    if end_assessment_return:
        proctoring_launch_data = Lti1p3ProctoringLaunchData(
            attempt_number=<attempt_number>,
        )

        launch_data = Lti1p3LaunchData(
            user_id=<user_id>,
            user_role=<user_role>,
            config_id=<config_id>,
            resource_link_id=<resource_link_id>,
            message_type="LtiEndAssessment",
            proctoring_launch_data=proctoring_launch_data,
        )

        return redirect(get_lti_1p3_launch_start_url(launch_data))


Note that for an ``LtiEndAssessment`` LTI launch message, the ``message_type`` field of the ``Lti1p3LaunchData``
instance must be ``LtiEndAssessment``. Unlike the ``LtiStartProctoring`` message, the ``start_assessment_url`` field of
the ``Lti1p3ProctoringLaunchData`` instance should not be supplied.
