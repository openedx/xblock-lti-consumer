###################
LTI Consumer XBlock
###################

| |status-badge| |license-badge| |ci-badge| |codecov-badge| |pypi-badge|

Purpose
*******

This XBlock implements the consumer side of the LTI specification enabling
integration of third-party LTI provider tools.

Getting Started
***************

Installation
============

The LTI Consumer XBlock is installed as by default on every Open edX instance.

For details regarding how to deploy a different version, see the "`Installing extra xblocks and requirements`_" section of Tutor documentation.

.. _Installing extra xblocks and requirements: https://docs.tutor.edly.io/configuration.html#installing-extra-xblocks-and-requirements

Enabling in Studio
------------------

You can enable the LTI Consumer XBlock in Studio through the
advanced settings.

1. From the main page of a specific course, navigate to
   ``Settings ->    Advanced Settings`` from the top menu.
2. Check for the ``advanced_modules`` policy key, and add
   ``"lti_consumer"`` to the policy value list.
3. Click the "Save changes" button.

Developing
===========

The following steps assumes you have a working Tutor dev setup.

#. Clone the repo

    .. code-block:: bash

       git clone git@github.com:openedx/xblock-lti-consumer.git

#. Add it as a Tutor mount, and update your environment

    .. code-block:: bash

       tutor mounts add /path/to/xblock-lti-consumer
       tutor dev launch

This will add the cloned repo to the ``lms`` and the ``cms`` containers at ``/mnt/xblock-lti-consumer`` and install it as an editable pip pacakge.
Any changes made to the Python code will auto-reload both ``lms`` and ``cms`` services.

Common Development Tasks
------------------------

Before performing any of the following tasks, create a virtual environment and activate it.

.. code-block:: bash

   python -m venv .venv
   source .venv/bin/activate

#. Changes to style rules should be made to the Sass files, compiled to CSS, and committed to the git repository.

   .. code-block:: bash

      make compile-sass

#. Running tests

   .. code-block:: bash

      pytest ./path/to/new/tests

#. Run quality checks

   .. code-block:: bash

      make quality

Development Workflow
--------------------

#. Fork and clone the repo.
#. Set up the dev environment as mentioned above.
#. Create a new branch.
#. Make necessary changes.
#. Run tests and quality checks.
#. Add a changelog entry to CHANGELOG.rst
#. Commit all your changes
#. Open a PR and ask for review.

Package Requirements
--------------------

setup.py contains a list of package dependencies which are required for this XBlock package.
This list is what is used to resolve dependencies when an upstream project is consuming
this XBlock package. requirements.txt is used to install the same dependencies when running
the tests for this package.

Further Development Info
------------------------

See the `developer guide`_ for implementation details and other developer concerns.

.. _developer guide: ./docs/developing.rst

Testing
*******

Unit Testing
============

* To run all of the unit tests at once, run ``make test``
* To run tests on individual files in development, run ``python ./test.py -k=[name of test file without .py]``
* For example, if you want to run the tests in test_permissions.py, run ``python ./test.py -k=test_permissions``
* To run a specific test in a file, run something like ``python ./test.py -k=test_permissions.TestClass.test_function``

Testing Against an LTI Provider
===============================

LTI 1.1
-------

http://lti.tools/saltire/ provides a "Test Tool Provider" service that allows
you to see messages sent by an LTI consumer.

We have some useful documentation on how to set this up here:
https://docs.openedx.org/en/latest/educators/how-tos/course_development/exercise_tools/set_up_lti_1_1_component.html

1. In Studio Advanced settings, set the value of the "LTI Passports" field to "test:test:secret" -
   this will set the OAuth client key and secret used to send a message to the test LTI provider.
2. Create an LTI Consumer problem in a course in Studio (after enabling it in "advanced_modules"
   as seen above).  Make a unit, select "Advanced", then "LTI Consumer".
3. Click edit and fill in the following fields:
   ``LTI ID``: "test"
   ``LTI URL``: "https://saltire.lti.app/tool"
   **Note:** If you are using more than one same LTI xblocks in the same unit,
   please append the ``norefresh`` parameter to the LTI URL to avoid any
   potential failures. Then LTI URL will look like this:
   ``https://saltire.lti.app/tool?norefresh``.
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

#. Set up a local tunnel (using **ngrok** or a similar tool) to get a URL accessible from the internet.
#. Add the following settings to ``edx-platform/lms/envs/private.py`` and ``edx-platform/cms/envs/private.py``:

   .. code-block:: python

      LTI_BASE="http://localhost:18000"
      LTI_API_BASE="http://<your_ngrok>.ngrok.io"

#. Create a new course, and add the ``lti_consumer`` block to the advanced modules list.
#. In the course, create a new unit and add the LTI block.

   * Set ``LTI Version`` to ``LTI 1.3``.
   * Set the ``Tool Launch URL`` to ``https://lti-ri.imsglobal.org/lti/tools/``

#. In Studio, you'll see a few parameters being displayed in the preview:

.. code::

    Client ID: f0532860-cb34-47a9-b16c-53deb077d4de
    Deployment ID: 1
    # Note that these are LMS URLS
    Keyset URL: http://1234.ngrok.io/api/lti_consumer/v1/public_keysets/88e45ecbd-7cce-4fa0-9537-23e9f7288ad9
    Access Token URL: http://1234.ngrok.io/api/lti_consumer/v1/token/8e45ecbd-7cce-4fa0-9537-23e9f7288ad9
    OIDC Callback URL: http://localhost:18000/api/lti_consumer/v1/launch/


#. Set up a tool in the IMS Global reference implementation (https://lti-ri.imsglobal.org/lti/tools/).

   * Click on ``Add tool`` at the top of the page (https://lti-ri.imsglobal.org/lti/tools).
   * Add the parameters and URLs provided by the block, and generate a private key on https://lti-ri.imsglobal.org/keygen/index and paste it there (don't close the tab, you'll need the public key later).

#. Go back to Studio, and edit the block adding its settings (you'll find them by scrolling down https://lti-ri.imsglobal.org/lti/tools/ until you find the tool you just created):

.. code::

    Tool Launch URL: https://lti-ri.imsglobal.org/lti/tools/[tool_id]/launches
    Tool Initiate Login URL: https://lti-ri.imsglobal.org/lti/tools/[tool_id]/login_initiations
    Tool Public key: Public key from key page.

#. Publish block, log into LMS and navigate to the LTI block page.
#. Click ``Send Request`` and verify that the LTI launch was successful.

See also https://docs.openedx.org/en/latest/educators/how-tos/course_development/exercise_tools/set_up_lti_1_3_component.html


LTI Advantage Features
----------------------

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


LTI 1.1/1.2 Basic Outcomes Service 1.1
--------------------------------------

This XBlock supports `LTI 1.1/1.2 Basic Outcomes Service 1.0 <http://www.imsglobal.org/spec/lti-bo/v1p1/>`_. Please see these
`LTI 1.1/1.2 Basic Outcomes Service 1.0 instructions <https://github.com/openedx/xblock-lti-consumer/tree/master/docs/basic_outcomes_service.rst>`_
for testing the LTI 1.1/1.2 Basic Outcomes Service 1.1 implementation.

LTI 2.0 Result Service 2.0
--------------------------

This XBlock supports `LTI 2.0 Result Service 2.0 <https://www.imsglobal.org/lti/model/uml/purl.imsglobal.org/vocab/lis/v2/outcomes/Result/service.html>`_.
Please see the `LTI 2.0 Result Service 2.0 instructions <https://github.com/openedx/xblock-lti-consumer/tree/master/docs/result_service.rst>`_
for testing the LTI 2.0 Result Service 2.0 implementation.

LTI Reusable configuration
**************************

The LTI Consumer XBlock supports configuration reusability via plugins.
It is compatible with both LTI 1.1 and LTI 1.3.
All values (including the access token and keyset URL for LTI 1.3)
are shared across the XBlocks with the same external configuration ID.
This eliminates the need to have a tool deployment for each XBlock.

How to Setup
============

1. Install and setup the `openedx-ltistore`_ plugin on the LMS and Studio.
2. Go to LMS admin -> WAFFLE_UTILS -> Waffle flag course override
   (http://localhost:18000/admin/waffle_utils/waffleflagcourseoverridemodel/).
3. Create a waffle flag course override with these values:
    - Waffle flag: lti_consumer.enable_external_config_filter
    - Course id: <your course id>
    - Override choice: Force On
    - Enabled: True
4. Create a new external LTI configuration and use it in the XBlock.
   This is explained in the README of the `openedx-ltistore`_ repository.

5. (Optional) Allows overriding of the `lti_1p3_launch_url` per block:
   - Waffle flag: `lti_consumer.enable_external_multiple_launch_urls`

.. _openedx-ltistore: https://github.com/open-craft/openedx-ltistore

Getting Help
************

If you're having trouble, we have discussion forums at
https://discuss.openedx.org where you can connect with others in the
community.

Our real-time conversations are on Slack. You can request a `Slack
invitation`_, then join our `community Slack workspace`_.

For anything non-trivial, the best path is to open an issue in this
repository with as many details about the issue you are facing as you
can provide.

https://github.com/openedx/xblock-lti-consumer/issues

For more information about these options, see the `Getting Help`_ page.

.. _Slack invitation: https://openedx.org/slack
.. _community Slack workspace: https://openedx.slack.com/
.. _Getting Help: https://openedx.org/getting-help

License
*******

The code in this repository is licensed under the AGPL v3 License unless
otherwise noted.

Please see `LICENSE.txt <LICENSE.txt>`_ for details.

Contributing
************

Contributions are very welcome.
Please read `How To Contribute <https://openedx.org/r/how-to-contribute>`_ for details.

This project is currently accepting all types of contributions, bug fixes,
security fixes, maintenance work, or new features.  However, please make sure
to have a discussion about your new feature idea with the maintainers prior to
beginning development to maximize the chances of your change being accepted.
You can start a conversation by creating a new issue on this repo summarizing
your idea.

The Open edX Code of Conduct
****************************

All community members are expected to follow the `Open edX Code of Conduct`_.

.. _Open edX Code of Conduct: https://openedx.org/code-of-conduct/

People
******

The assigned maintainers for this component and other project details may be
found in `Backstage`_. Backstage pulls this data from the ``catalog-info.yaml``
file in this repo.

.. _Backstage: https://backstage.openedx.org/catalog/default/component/xblock-lti-consumer

Reporting Security Issues
*************************

Please do not report security issues in public. Please email security@openedx.org.

.. |ci-badge| image:: https://github.com/openedx/xblock-lti-consumer/workflows/Python%20CI/badge.svg?branch=master
    :target: https://github.com/openedx/xblock-lti-consumer/actions?query=workflow%3A%22Python+CI%22
    :alt: Test suite status

.. |codecov-badge| image:: https://codecov.io/github/openedx/xblock-lti-consumer/coverage.svg?branch=master
    :target: https://codecov.io/github/openedx/xblock-lti-consumer?branch=master
    :alt: Code coverage

.. |status-badge| image:: https://img.shields.io/badge/Status-Maintained-brightgreen
    :alt: Maintained

.. |license-badge| image:: https://img.shields.io/github/license/openedx/xblock-lti-consumer.svg
    :target: https://github.com/openedx/edx-rest-api-client/blob/master/LICENSE
    :alt: License

.. |pypi-badge| image:: https://img.shields.io/pypi/v/lti-consumer-xblock.svg
    :target: https://pypi.python.org/pypi/lti-consumer-xblock/
    :alt: PyPI
