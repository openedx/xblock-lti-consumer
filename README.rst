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
   * Set the ``Tool Launch URL`` to ``https://lti-ri.imsglobal.org/lti/tools/``

4. In Studio, you'll see a few parameters being displayed in the preview:

.. code::

    Client ID: f0532860-cb34-47a9-b16c-53deb077d4de
    Deployment ID: 1
    # Note that these are LMS URLS
    Keyset URL: http://localhost:18000/api/lti_consumer/v1/public_keysets/block-v1:OpenCraft+LTI101+2020_T2+type@lti_consumer+block@efc55c7abb87430883433bfafb83f054
    Access Token URL: http://localhost:18000/api/lti_consumer/v1/token/block-v1:OpenCraft+LTI101+2020_T2+type@lti_consumer+block@efc55c7abb87430883433bfafb83f054
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

    Tool Launch URL: https://lti-ri.imsglobal.org/lti/tools/[tool_id]/launches
    Tool Initiate Login URL: https://lti-ri.imsglobal.org/lti/tools/[tool_id]/login_initiations
    Tool Public key: Public key from key page.

8. Publish block, log into LMS and navigate to the LTI block page.
9. Click ``Send Request`` and verify that the LTI launch was successful.

.. admonition:: Testing using ``ngrok``

    When launching LTI 1.3 requests through ``ngrok``, make sure your LMS is serving session cookies marked as
    ``Secure`` and with the ``SameSite`` attribute set to ``None``. You can do this by changing ``SESSION_COOKIE_SECURE: true``
    and ``DCS_SESSION_COOKIE_SAMESITE: None`` in your ``lms.yml`` configuration files. Note that this will break logins
    for locally accessed URLs in the devstack.


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



LTI Advantage Features
======================

This XBlock supports LTI 1.3 and the following LTI Avantage services:

* Deep Linking (LTI-DL)
* Assignments and Grades services (LTI-AGS)
* Names and Roles Provisioning services (LTI-NRP)

To enable LTI-AGS, you need to set **LTI Assignment and Grades Service** in Studio to
allow tools to send back grades. There's two grade interaction models implemented:

* **Allow tools to submit grades only (declarative)(Default)**: enables LTI-AGS and
  creates a single fixed LineItem that the tools can send grades too.
* **Allow tools to manage and submit grades (programmatic)**: enables LTI-AGS and
  enables full access to LTI-AGS endpoints. Tools will be able to create, manage and
  delete multiple LineItems, and set multiple grades per student per problem.
  *In this implementation, the tool is responsible for managing grades and linking them in the LMS.*

To enable LTI-DL and its capabilities, you need to set these settings in the block:

1. Locate the **Deep linking** setting and set it to **True (enabled)**.
2. Set **Deep Linking Launch URL** setting. You can retrieve it from the tool you’re integrating with.
   If it’s not provided, try using the same value as in the LTI 1.3 Tool Launch URL.

To enable LTI-NRPS, you set **Enable LTI NRPS** to **True** in the block settings on Studio.


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

Please See the [releases tab](https://github.com/edx/xblock-lti-consumer/releases) for the complete changelog.

3.4.5 - 2022-03-16
------------------

* Fix LTI Deep Linking return endpoint permission checking method by replacing the old one with the proper
  Studio API call.

3.4.4 - 2022-03-03
------------------

* Fix LTI 1.3 Deep Linking launch url - always perform launch on launch URL, but update `target_link_uri` when
  loading deep linking content.
  See LTI 1.3 spec at: https://www.imsglobal.org/spec/lti/v1p3#target-link-uri

3.4.3 - 2022-02-01
------------------

* Fix LTI 1.1 template rendering when using embeds in the platform

3.4.2 - 2022-02-01
------------------

* Fix LTI 1.1 form rendering so it properly renders quotes present in titles.
* Migrate LTI 1.1 launch template from Mako to Django template.
* Internationalize LTI 1.1 launch template.

3.4.1 - 2022-02-01
------------------

* Fix the target_link_uri parameter on OIDC login preflight url parameter so it matches 
  claim message definition of the field.
  See docs at https://www.imsglobal.org/spec/lti/v1p3#target-link-uri

3.4.0 - 2022-01-31
------------------

* Fix the version number by bumping it up to 3.4.0

3.3.0 - 2022-01-20
-------------------

* Added support for specifying LTI 1.3 JWK URLs.

3.2.0 - 2022-01-18
-------------------

* Dynamic custom parameters support with the help of template parameter processors.

3.1.2 - 2021-11-12
-------------------

* The modal to confirm information transfer on open of lti in new tab/window has been updated
  because of a change in how browsers handle iframe permissions.

3.1.0 - 2021-10-?
-------------------

* The changes which led to this version change were not adequetly documented.

3.0.1 - 2021-07-09
-------------------

* Added multi device support on student_view for mobile.


3.0.0 - 2021-06-16
-------------------

* Rename `CourseEditLTIFieldsEnabledFlag` to `CourseAllowPIISharingInLTIFlag`
  to highlight its increased scope.
* Use `CourseAllowPIISharingInLTIFlag` for LTI1.3 in lieu of the current
  `CourseWaffleFlag`.


2.11.0 - 2021-06-10
-------------------

* NOTE: This release requires a corresponding change in edx-platform that was
  implemented in https://github.com/edx/edx-platform/pull/27529
  As such, this release cannot be installed in releases before Maple.
* Move ``CourseEditLTIFieldsEnabledFlag`` from ``edx-platform`` to this repo
  while retaining data from existing model.


2.10.1 - 2021-06-09
-------------------

* LTI 1.3 and LTI Advantage features are now enabled by default.
* LTI 1.3 settings were simplified to reduce confusion when setting up a LTI tool.
* Code quality issues fixed


2.9.1 - 2021-06-03
------------------

* LTI Advantage - NRP Service: this completes Advantage compliance.


2.8.0 - 2021-04-13
------------------

* LTI Advantage - AGS Service: Added support for programmatic grade management by LTI tools.
* Improved grade publishing to LMS when using LTI-AGS.
* Increase LTI 1.3 token validity to 1h.


2.7.0 - 2021-02-16
------------------

* Add support for presenting `ltiResourceLink` content from deep linking.


2.6.0 - 2021-02-16
------------------

* Deep Linking content presentation implementation, for resource links, HTML,
  HTML links, and images.

* Fix bug with `config_id` migration where an entry was created _during_
  the migration and did _not_ receive a valid UUID value.


2.5.3 - 2021-01-26
------------------

* LTI Deep Linking Launch implementation, implementing DeepLinking Classes and request
  request preparation.
* LTI Deep Linking response endpoint implementation, along with model to store selected configuration and
  content items.

2.5.2 - 2021-01-20
------------------

* Fix issue with migration that causes migration failure due to duplicate `config_id` values.

2.5.1 - 2021-01-19
------------------

* Simplify LTI 1.3 launches by removing OIDC launch start view.

2.5.0 - 2021-01-15
------------------

* Add LTI 1.1 config on model.

2.4.0 - 2020-12-02
------------------

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


.. |Build Status| image:: https://github.com/edx/xblock-lti-consumer/workflows/Python%20CI/badge.svg?branch=master
  :target: https://github.com/edx/xblock-lti-consumer/actions?query=workflow%3A%22Python+CI%22

.. |Coveralls| image:: https://coveralls.io/repos/edx/xblock-lti-consumer/badge.svg?branch=master&service=github
  :target: https://coveralls.io/github/edx/xblock-lti-consumer?branch=master
