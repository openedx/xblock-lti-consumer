LTI 1.3 roles mapping update
----------------------------

Status
======

Provisional

Context
=======

Open edX LTI 1.3 launch code historically mapped course roles to institution and system role URIs.
This caused interoperability problems with tools that expect context role URIs in LTI launch and NRPS
membership responses.

LTI 1.3 roles claim allows role URIs from published LIS vocabularies, including:

* system roles
* institution roles
* context roles

In practice, LTI launches in Open edX happen in course context, so context roles are most relevant.
Open edX also has more explicit role values than ``staff``, ``instructor``, ``student``, and ``guest``.
These include course roles such as ``limited_staff``, ``finance_admin``, ``sales_admin``,
``beta_testers``, ``library_user``, ``ccx_coach``, and ``data_researcher``.
Open edX also defines discussion roles such as ``Administrator``, ``Moderator``,
``Group Moderator``, ``Community TA``, and ``Student``.
Global Django staff (``user.is_staff``) is represented in LTI mapping as ``global_staff``.

This ADR records updated mapping used for:

* LTI 1.3 launch roles claim
* LTI NRPS membership container member roles

This ADR supersedes Roles section from
`0002-lti-1p3-variables.rst <0002-lti-1p3-variables.rst>`_.

Decisions
=========

Launch roles claim
~~~~~~~~~~~~~~~~~~

For LTI launches, Open edX includes context role URIs plus neutral system and institution role URIs:

* ``http://purl.imsglobal.org/vocab/lis/v2/system/person#None``
* ``http://purl.imsglobal.org/vocab/lis/v2/institution/person#None``

Context role mapping is shown below.

.. list-table::
   :widths: auto
   :header-rows: 1

   * - Open edX role
     - LTI 1.3 roles included
     - Reasoning
   * - instructor
     - ``system/person#None``
       ``institution/person#None``
       ``membership#Administrator``
       ``membership#Instructor``
     - Course admin role in Open edX maps to highest course-context privilege.
   * - global_staff
     - ``system/person#Administrator``
       ``institution/person#Administrator``
       ``institution/person#Staff``
       ``institution/person#Faculty``
       ``institution/person#Instructor``
       ``membership#Administrator``
       ``membership#Instructor``
     - Global Django staff maps to instance-admin style LIS roles for tool launches.
   * - staff
     - ``system/person#None``
       ``institution/person#None``
       ``membership#Instructor``
     - Course staff should have instructor-level context access, but not course admin role.
   * - limited_staff
     - ``system/person#None``
       ``institution/person#None``
       ``membership#Instructor``
     - Limited staff derives from staff and should expose same course-context role to tools.
   * - student
     - ``system/person#None``
       ``institution/person#None``
       ``membership#Learner``
     - Standard learner mapping.
   * - guest
     - ``system/person#None``
       ``institution/person#None``
       ``membership#Learner``
     - Guest launch paths use learner-compatible mapping for interoperability.
   * - finance_admin
     - ``system/person#None``
       ``institution/person#None``
       ``membership#Learner``
     - No stronger LTI-specific course-context privilege required.
   * - sales_admin
     - ``system/person#None``
       ``institution/person#None``
       ``membership#Learner``
     - No stronger LTI-specific course-context privilege required.
   * - beta_testers
     - ``system/person#None``
       ``institution/person#None``
       ``membership#Learner``
     - No stronger LTI-specific course-context privilege required.
   * - library_user
     - ``system/person#None``
       ``institution/person#None``
       ``membership#Learner``
     - No stronger LTI-specific course-context privilege required.
   * - ccx_coach
     - ``system/person#None``
       ``institution/person#None``
       ``membership#Learner``
     - No stronger LTI-specific course-context privilege required.
   * - data_researcher
     - ``system/person#None``
       ``institution/person#None``
       ``membership#Learner``
     - No stronger LTI-specific course-context privilege required.
   * - org_course_creator_group
     - ``system/person#None``
       ``institution/person#None``
       ``membership#Learner``
     - Org-scoped role does not imply elevated privilege in specific course launch context.
   * - course_creator_group
     - ``system/person#None``
       ``institution/person#None``
       ``membership#Learner``
     - Platform-wide role does not imply elevated privilege in specific course launch context.
   * - support
     - ``system/person#None``
       ``institution/person#None``
       ``membership#Learner``
     - Support role should not expose elevated course-context privilege to tools by default.
   * - Administrator, Moderator, Student
     - ``system/person#None``
       ``institution/person#None``
       ``membership#Learner``
     - Discussion roles do not map cleanly to elevated LTI course-context privilege, so default to learner.
   * - Group Moderator, Community TA
     - ``system/person#None``
       ``institution/person#None``
       ``membership#Learner``
       ``membership#TeachingAssistant``
     - These discussion roles align with teaching-assistant style participation in course context.

NRPS membership roles
~~~~~~~~~~~~~~~~~~~~~

For NRPS membership responses, Open edX includes context roles only.

.. list-table::
   :widths: auto
   :header-rows: 1

   * - Open edX role
     - NRPS roles included
   * - instructor
     - ``membership#Administrator`` ``membership#Instructor``
   * - global_staff
     - ``membership#Administrator`` ``membership#Instructor``
   * - staff
     - ``membership#Instructor``
   * - limited_staff
     - ``membership#Instructor``
   * - Group Moderator, Community TA
     - ``membership#Learner`` ``membership#TeachingAssistant``
   * - all other explicitly mapped roles
     - ``membership#Learner``

Consequences
============

* Tool compatibility improves because context role URIs are now present in launch and NRPS flows.
* Open edX role handling becomes explicit for current known course, org, and global staff values.
* Older documentation in ``0002-lti-1p3-variables.rst`` remains historical and should not be treated as current source of truth for roles mapping.
