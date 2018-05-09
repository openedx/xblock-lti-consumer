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
