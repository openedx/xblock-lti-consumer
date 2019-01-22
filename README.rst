LTI Consumer XBlock |Build Status| |Coveralls|
----------------------------------------------

This XBlock implements the consumer side of the LTI specification enabling
integration of third-party LTI provider tools.

Installation
------------

Install the requirements into the python virtual environment of your
``edx-platform`` installation by running the following command from the
root folder:

.. code:: bash

    $ pip install -r requirements.txt

Installing in Docker Devstack
-----------------------------

Assuming that your ``devstack`` repo lives at ``~/code/devstack``
and that ``edx-platform`` lives right alongside that directory, you'll want
to checkout ``xblock-lti-consumer`` and have it live in ``~/code/src/xblock-lti-consumer``.
This will make it so that you can access it inside an LMS container shell
and easily make modifications for local testing.

Run ``make lms-shell`` from your ``devstack`` directory to enter a running LMS container.
Once in there, you can do the following to have your devstack pointing at a local development
version of ``xblock-lti-consumer``:

.. code:: bash

    $ pushd /edx/src/xblock-lti-consumer
    $ virtualenv venv/
    $ source venv/bin/activate
    $ make install
    $ make test  # optional, if you want to see that everything works
    $ deactivate
    $ pushd  # should take you back to /edx/app/edxapp/edx-platform
    $ pip uninstall -y lti_consumer_xblock
    $ pip install -e /edx/src/xblock-lti-consumer

Enabling in Studio
------------------

You can enable the LTI Consumer XBlock in Studio through the
advanced settings.

1. From the main page of a specific course, navigate to
   ``Settings ->    Advanced Settings`` from the top menu.
2. Check for the ``advanced_modules`` policy key, and add
   ``"lti_consumer"`` to the policy value list.
3. Click the "Save changes" button.

Testing Against an LTI Provider
-------------------------------

http://lti.tools/saltire/ provides a "Test Tool Provider" service that allows
you to see messages sent by an LTI consumer.

We have some useful documentation on how to set this up here:
http://edx.readthedocs.io/projects/open-edx-building-and-running-a-course/en/latest/exercises_tools/lti_component.html#lti-authentication-information

1. In Studio Advanced settings, set the value of the "LTI Passports" field to "test:test:secret" -
   this will set the oauth client key and secret used to send a message to the test LTI provider.
2. Create an LTI Consumer problem in a course in studio (after enabling it in "advanced_modules"
   as seen above).  Make a unit, select "Advanced", then "LTI Consumer".
3. Click edit and fill in the following fields:
   ``LTI ID``: "test"
   ``LTI URL``: "https://lti.tools/saltire/tp"
4. Click save.  The unit should refresh and you should see "Passed" in the "Verification" field of
   the message tab in the LTI Tool Provider emulator.
5. Click the "Publish" button.
6. View the unit in your local LMS.  If you get an ``ImportError: No module named lti_consumer``, you
   should ``docker-compose restart lms`` (since we previously uninstalled the lti_consumer to get the
   tests for this repo running inside an LMS container).  From here, you can see the contents of the
   messages that we are sending as an LTI Consumer in the "Message Parameters" part of the "Message" tab.

Custom LTI Parameters
---------------------
This XBlock sends a number of parameters to the provider including some optional parameters. To keep the XBlock
somewhat minimal, some parameters were omitted like ``lis_person_name_full`` among others.
At the same time the XBlock allows passing extra parameters to the LTI provider via parameter processor functions.

Defining an LTI Parameter Processors
====================================
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
=============================================

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

Workbench installation and settings
-----------------------------------

Install to the workbench's virtualenv by running the following command
from the xblock-lti-consumer repo root with the workbench's virtualenv activated:

.. code:: bash

    $ make install

Running tests
-------------

From the xblock-lti-consumer repo root, run the tests with the following command:

.. code:: bash

    $ make test

Running code quality check
--------------------------

From the xblock-lti-consumer repo root, run the quality checks with the following command:

.. code:: bash

    $ make quality

Compiling Sass
--------------

This XBlock uses Sass for writing style rules. The Sass is compiled
and committed to the git repo using:

.. code:: bash

    $ make compile-sass

Changes to style rules should be made to the Sass files, compiled to CSS,
and committed to the git repository.

Package Requirements
--------------------

setup.py contains a list of package dependencies which are required for this XBlock package.
This list is what is used to resolve dependencies when an upstream project is consuming
this XBlock package. requirements.txt is used to install the same dependencies when running
the tests for this package.

Downloading translations from Transifex
-------------------------------------

If you want to download translations from Transifex install
`transifex client <https://docs.transifex.com/client/installing-the-client/>`_ and run this command while
inside project root directory

.. code:: bash

    $ tx pull -f --mode=reviewed -l en,ar,es_419,fr,he,hi,ko_KR,pt_BR,ru,zh_CN

License
-------

The LTI Consumer XBlock is available under the Apache Version 2.0 License.


.. |Build Status| image:: https://travis-ci.org/edx/xblock-lti-consumer.svg
  :target: https://travis-ci.org/edx/xblock-lti-consumer

.. |Coveralls| image:: https://coveralls.io/repos/edx/xblock-lti-consumer/badge.svg?branch=master&service=github
  :target: https://coveralls.io/github/edx/xblock-lti-consumer?branch=master
