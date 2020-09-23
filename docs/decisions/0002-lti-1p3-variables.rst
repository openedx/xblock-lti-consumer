LTI 1.3 variable definition
---------------------------

Status
======

Provisional

Context
=======

The LTI 1.3 specification defines multiple variables related to course, context, problem, student id and PII.

The goal of this ADR is to provide well defined mappings from variables available in the platform and
variables required by LTI 1.3 launches.

Decisions
=========

The following sections go over required and optional variables in each supported claim in the LTI 1.3 implementation.
This ADR should be updated when new claims are added.

Deployment ID
~~~~~~~~~~~~~

.. list-table::
   :widths: auto
   :header-rows: 1

   * - LTI 1.3 variable name
     - Open edX
     - Reasoning
   * - https://purl.imsglobal.org/spec/lti/claim/deployment_id
     - "1" (fixed value)
     - We're using single-tenant deployments, were each key is used for a single XBlock. Even when moving up to the course level,
       we can keep this since multi-tenancy will only be required for instance wide configuration.

See http://www.imsglobal.org/spec/lti/v1p3/#single-tenant-tool-registered-and-deployed-once for more details.

Roles
~~~~~
The roles claim takes in a list of LTI 1.3 compliant roles from http://www.imsglobal.org/spec/lti/v1p3/#role-vocabularies.
The claim name is: https://purl.imsglobal.org/spec/lti/claim/roles.

The mappings from Open edX roles are shown in the table below:

.. list-table::
   :widths: auto
   :header-rows: 1

   * - Open edX role
     - LTI 1.3 Roles included
     - Reasoning
   * - guest
     - Empty
     - Guests users are not logged in, they shouldn't be able to access LTI content.
   * - student
     - 'http://purl.imsglobal.org/vocab/lis/v2/institution/person#Student'
     - Students only have permission to view and interact with the LTI content.
   * - instructor
     - 'http://purl.imsglobal.org/vocab/lis/v2/institution/person#Instructor'
       'http://purl.imsglobal.org/vocab/lis/v2/institution/person#Student'
     - Instructor have both instructor and student access to a tool. No admin permissions.
   * - staff
     - 'http://purl.imsglobal.org/vocab/lis/v2/system/person#Administrator'
       'http://purl.imsglobal.org/vocab/lis/v2/institution/person#Instructor'
       'http://purl.imsglobal.org/vocab/lis/v2/institution/person#Student'
     - A staff user should be able to modify the tool settings and have full access to the content and settings.

Resource link
~~~~~~~~~~~~~

This claim has properties for the resource link from which the launch message occurs. It represents a unique place in the course where the LTI launch happens.

.. list-table::
   :widths: auto
   :header-rows: 1

   * - Claim variable
     - Block location (on course context).
     - Reasoning
   * - id
     - Block location (on course context).
     - The resource link id needs to be a identifier unique to the deployment.
       In the Open edX platform, we already have an analog that is unique to the entire instance: block location.
   * - title
     - Display name (either from block or parent block)
       Empty if not available/applicable.
     - We use the `Display name` attribute to provide a descriptive title to the LTI tool.
       In case this isn't available in the launch context, this parameter isn't sent.
   * - description
     - Not implemented.
     - This is an optional field.

Reference: http://www.imsglobal.org/spec/lti/v1p3/#resource-link-claim-0

User claims
~~~~~~~~~~~
The user data claims are identifiers passed through the LTI message to send user data to the LTI tool.

.. list-table::
   :widths: auto
   :header-rows: 1

   * - Claim variable
     - Open edX
     - Reasoning
   * - sub
     - external user id (with the `lti` type)
     - Using the id provided by the external_user_id from openedx core.
       See https://github.com/edx/edx-platform/blob/master/openedx/core/djangoapps/external_user_ids/docs/decisions/0001-externalid.rst
   * - name
     - User full name
     - User full name as defined in the spec, gated by a feature flag to avoid leaking PII to external tools.
   * - email
     - User email address
     - User email, gated by a feature flag to avoid leaking PII to external tools (this flag should be off by default).

Reference: http://www.imsglobal.org/spec/lti/v1p3/#user-identity-claims-0


Context claim
~~~~~~~~~~~~~
This claim is optional and includes information about the context where LTI launch is happening.

.. list-table::
   :widths: auto
   :header-rows: 1

   * - Claim variable
     - Open edX
     - Reasoning
   * - id
     - course id if using CourseOffering
     - This claim requires a unique identifier per deployment,
       and Course ID is already unique platform-wide to represent a course.
   * - type
     - http://purl.imsglobal.org/vocab/lis/v2/course#CourseOffering
     - LTI launches will mostly occur in the context of courses.
       If launched from outside, the entire context claim should be omitted.
   * - label
     - Not used.
     - This is just a description field that is optional.
   * - title
     - `Organization` - `Course name`
     - Using a readable identifier of the organization and course name to the tool.

Reference: http://www.imsglobal.org/spec/lti/v1p3/#context-type-vocabulary



Tech Debt
=========

* The current LTI 1.3 implementation merged on `master` uses the internally generated resource id from the LTI 1.1.1 implementation.

Consequences
============

* Changing the resource id to the value defined above will lose contexts on all currently deployed XBlocks (since a different resource means the LTI is being launched
  in a different location from the Tool's POV).
