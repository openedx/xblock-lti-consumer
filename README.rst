###################
LTI Consumer XBlock
###################

| |Build Status| |Coveralls|

This XBlock implements the consumer side of the LTI specification enabling
integration of third-party LTI provider tools.

Installation
============

Install the requirements into the Python virtual environment of your
``edx-platform`` installation by running the following command from the
root folder:

.. code:: bash

    $ pip install -r requirements/base.txt

Additionally, to enable LTI 1.3 Launch support, the following FEATURE flag needs to be set in `/edx/etc/studio.yml` in your LMS container:

.. code:: yaml

    FEATURES:
        LTI_1P3_ENABLED: true


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
===============================

LTI 1.1
-------

http://lti.tools/saltire/ provides a "Test Tool Provider" service that allows
you to see messages sent by an LTI consumer.

We have some useful documentation on how to set this up here:
http://edx.readthedocs.io/projects/open-edx-building-and-running-a-course/en/latest/exercises_tools/lti_component.html#lti-authentication-information

1. In Studio Advanced settings, set the value of the "LTI Passports" field to "test:test:secret" -
   this will set the OAuth client key and secret used to send a message to the test LTI provider.
2. Create an LTI Consumer problem in a course in Studio (after enabling it in "advanced_modules"
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


LTI 1.3
-------

IMS Global provides a reference implementation of LTI 1.3 that can be used to test the XBlock.

On LTI 1.3 the authentication mechanism used is OAuth2 using the Client Credentials grant, this means
that to configure the tool, the LMS needs to know the keyset URL or public key of the tool, and the tool
needs to know the LMS's one.

Instructions:

1. Set up a local tunnel tunneling the LMS (using `ngrok` or a similar tool) to get a URL accessible from the internet.
2. Create a new course, and add the `lti_consumer` block to the advanced modules list.
3. In the course, create a new unit and add the LTI block.

   * Set ``LTI Version`` to ``LTI 1.3``.
   * Set the ``LTI 1.3 Tool Launch URL`` to ``https://lti-ri.imsglobal.org/lti/tools/``

4. In Studio, you'll see a few parameters being displayed in the preview:

.. code::

    Client: f0532860-cb34-47a9-b16c-53deb077d4de
    Deployment ID: 1
    # Note that these are LMS URLS
    Keyset URL: http://localhost:18000/api/lti_consumer/v1/public_keysets/block-v1:OpenCraft+LTI101+2020_T2+type@lti_consumer+block@efc55c7abb87430883433bfafb83f054
    OAuth Token URL: http://localhost:18000/api/lti_consumer/v1/token/block-v1:OpenCraft+LTI101+2020_T2+type@lti_consumer+block@efc55c7abb87430883433bfafb83f054
    OIDC Callback URL: http://localhost:18000/api/lti_consumer/v1/launch/


5. Add the tunnel URL to the each of these URLs as it'll need to be accessed by the tool (hosted externally).

.. code::

    # This is <LMS_URL>/api/lti_consumer/v1/public_keysets/<BLOCK_LOCATION>
    https://647dd2e1.ngrok.io/api/lti_consumer/v1/public_keysets/block-v1:OpenCraft+LTI101+2020_T2+type@lti_consumer+block@996c72b16070434098bc598bd7d6dbde


6. Set up a tool in the IMS Global reference implementation (https://lti-ri.imsglobal.org/lti/tools/).

   * Click on ``Add tool`` at the top of the page (https://lti-ri.imsglobal.org/lti/tools).
   * Add the parameters and URLs provided by the block, and generate a private key on https://lti-ri.imsglobal.org/keygen/index and paste it there (don't close the tab, you'll need the public key later).

7. Go back to Studio, and edit the block adding its settings (you'll find them by scrolling down https://lti-ri.imsglobal.org/lti/tools/ until you find the tool you just created):

.. code::

    LTI 1.3 Tool Launch URL: https://lti-ri.imsglobal.org/lti/tools/[tool_id]/launches
    LTI 1.3 OIDC URL: https://lti-ri.imsglobal.org/lti/tools/[tool_id]/login_initiations
    LTI 1.3 Tool Public key: Public key from key page.

8. Publish block, log into LMS and navigate to the LTI block page.
9. Click ``Send Request`` and verify that the LTI launch was successful.

.. admonition:: Testing using ``ngrok``

    When launching LTI 1.3 requests through ``ngrok``, make sure you set ``DCS_SESSION_COOKIE_SAMESITE = 'None'`` in your
    ``devstack.py`` (located in /edx/app/edxapp/edx-platform/(lms|cms)/envs``) when doing LTI 1.3 launches in the
    devstack through ngrok. Do not forget to restart your services after updating the ``.py`` files.

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

Development
===========

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
---------------------------------------

If you want to download translations from Transifex install
`transifex client <https://docs.transifex.com/client/installing-the-client/>`_ and run this command while
inside project root directory:

.. code:: bash

    $ tx pull -f --mode=reviewed -l en,ar,es_419,fr,he,hi,ko_KR,pt_BR,ru,zh_CN

License
=======

The LTI Consumer XBlock is available under the AGPL v3 License.

Security
========

Please do not report security issues in public. Send security concerns via email to security@edx.org.

Changelog
=========

2.4 - 2020-12-01
----------------

* Partially implemented the Assignment and Grades Service to enable tools
  reporting grades back.  Tools cannot create new LineItems.

2.3 – 2020-08-27
----------------

* Move LTI configuration access to plugin model.

2.2 – 2020-08-19
----------------

* Modals are sent to the parent window to work well with the courseware
  micro-frontend.  A new message is sent to the parent window to request a
  modal containing the contents ot the LTI launch iframe.

2.1 – 2020-08-03
----------------

* The LTI consumer XBlock is now indexable.

* Implement the LTI 1.3 context claim.

2.0.0 – 2020-06-26
------------------

* LTI 1.3 support.


.. |Build Status| image:: https://travis-ci.org/edx/xblock-lti-consumer.svg
  :target: https://travis-ci.org/edx/xblock-lti-consumer

.. |Coveralls| image:: https://coveralls.io/repos/edx/xblock-lti-consumer/badge.svg?branch=master&service=github
  :target: https://coveralls.io/github/edx/xblock-lti-consumer?branch=master
