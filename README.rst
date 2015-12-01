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

Enabling in Studio
------------------

You can enable the LTI Consumer XBlock in Studio through the
advanced settings.

1. From the main page of a specific course, navigate to
   ``Settings ->    Advanced Settings`` from the top menu.
2. Check for the ``advanced_modules`` policy key, and add
   ``"lti_consumer"`` to the policy value list.
3. Click the "Save changes" button.

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

License
-------

The LTI Consumer XBlock is available under the Apache Version 2.0 License.


.. |Build Status| image:: https://travis-ci.org/edx/xblock-lti-consumer.svg
  :target: https://travis-ci.org/edx/xblock-lti-consumer

.. |Coveralls| image:: https://coveralls.io/repos/edx/xblock-lti-consumer/badge.svg?branch=master&service=github
  :target: https://coveralls.io/github/edx/xblock-lti-consumer?branch=master
