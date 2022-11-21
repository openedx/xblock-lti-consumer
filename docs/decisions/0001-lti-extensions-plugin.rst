Platform wide LTI support
----------------------------

Status
======

Accepted

Context
=======

The LTI Consumer implementation in the Open edX platform is currently limited to LTI launches inside XBlocks.

The goal of this ADR is to:

#. Define an architecture to enable LTI launch and configuration for multiple contexts (from block level to platform level).
#. Make LTI configuration reusable throughout a context.
#. Support both LTI 1.1 and LTI 1.3, as well as LTI Advantage.

Decisions
=========

Develop LTI related code to be reusable in the platform context, and allow LTI to be configured for different contexts in the platform.
This requires adding a separation layer between the framework presenting the content and the LTI logic, configuration and storage layer.

The first steps were already taken to move towards this implementation with these PRs:

`Merge LTI 1.3 support to master`_: Implemented support for LTI 1.3 by creating a framework agnostic python module that handles the
LTI specific logic (such as launch message creation, token verification and OIDC flows) and passing responses as JSON objects to be
interpreted and presented by the XBlock LTI consumer.
The module is easily reusable in contexts outside the XBlock and all the code in `lti_consumer/lti_1p3` don't rely on XBlock or
Django specific features.
The PR uses the XBlock's fields to store LTI configuration.

`Add support for LTI embeds in course tabs and elsewhere`_: This is a partial implementation of logic separation for the LTI 1.1
consumer to allow LTI launches from outside the context of an XBlock, following the guidelines set by the LTI 1.3 implementation.
While this is a smaller step than the implementation above, it allows LTI 1.1 launches on any LMS/Studio view, but doesn't implement
the configuration storage.

.. _`Merge LTI 1.3 support to master`: https://github.com/openedx/xblock-lti-consumer/pull/82
.. _`Add support for LTI embeds in course tabs and elsewhere`: https://github.com/openedx/xblock-lti-consumer/pull/77


A few actions that need to be taken to achieve the desired architecture are outlined below:

Centralized configuration for LTI launches
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use Django models to store LTI related configuration and launch data for all LTI integrations.
This will provide a consistent configuration store throughout the platform and a single point of
maintenance and development for LTI related features (good since the LTI Specification is well defined).

Additionaly this would include configurations UI on Studio (to enable setup by instructors) and
also through Django Admin (enable for larger contexts: programs or platform-wide).


New LTI Python API
~~~~~~~~~~~~~~~~~~

A new Python API needs to be developed to provide LTI support platform wide.
This API should provide methods to configure, modify and perform LTI launches
from multiple platform contexts (Django, XBlocks).

A centralized launch & configuration API will make LTI integration consistent
across all platform's contexts.

Change folder structure and rename repository
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To better reflect the new repo usage, rename the repository to "openedx-lti-consumer" and
change the folder structure.

Here is the new proposed folder structure::

  # Django plugabble app main folder
  lti_consumer/

  # Python APIs - following Inter App APIs guidelines
  lti_consumer/api.py

  # LTI specific logic (no storage)
  lti_consumer/lti_1p1
  lti_consumer/lti_1p3

  # LTI Configuration, launch and services storage
  lti_consumer/models/

  # Pluggable extensions points that can be used in the platform
  lti_consumer/extensions/
  lti_consumer/extensions/xblock.py  # To replace current XBlock LTI Consumer, can use course import/export hooks to change settings
  lti_consumer/extensions/django.py  # To easily enable LTI embeds anywhere in the platform
  lti_consumer/extensions/course_tab.py  # Inherit Django extension above and add helpers to use course context for a few use cases (forum tab, course embed)

(Here are the `Inter App APIs`_ guidelines.)

.. _`Inter App APIs`: https://github.com/openedx/edx-platform/blob/master/docs/decisions/0002-inter-app-apis.rst

Tech Debt
=========

The current LTI implementation stores launch configuration and user data in XBlock Settings fields.
We'll need a transition phase and a migration path before fully deprecating the old configuration storage.

The transition phase can allow configuring LTI integration both locally (on the XBlock) and using the
generic configuration.


Consequences
============

* LTI configuration will be independent from courses, so secret keys, access tokens and general LTI launch configuration won't
  be carried over when importing/exporting courses for security purposes. LTI Tools need to be reconfigured or use contexts available
  whitin the course/organization.

* The LTI consumer will use Django models to store launch configuration (being a plugin, that's already possible).

* Enables LTI integration throughout the platform, without limitations of XBlocks and even outside a course context.
