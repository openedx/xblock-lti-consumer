LTI Advantage AGS Score Linking
-------------------------------

Status
======

In Review

Context
=======

LTI Advantage provides new ways for LTI tools to push grades back into the platform through the `Assignment and Grades Services (AGS)`_,
which don't map 1:1 with the grading and gradebook structure present in Open edX.

There's two models of interation to pushing grades to the platform in the LTI AGS services:

1. Declarative: the platform creates a LineItem (equivalent of a gradebook line/grade) and tools can only push results to that item.
2. Programmatic: the tool uses the AGS endpoints to manage it's own line items and grades. The tool is responsible for linking each line item to the resourceLinks, which means that a tool might not link a grade to it's respective problem.

See a more detailed description in the `Coupled vs decoupled line items`_ section of the spec.

.. _`Assignment and Grades Services (AGS)`: https://www.imsglobal.org/spec/lti-ags/v2p0
.. _`Coupled vs decoupled line items`: https://www.imsglobal.org/spec/lti-ags/v2p0#coupled-vs-decoupled-line-items


Decisions
=========

We want to enable the platform to have full LTI Advantage compatibility, so we need to allow both interaction models to happen.

To do that, a configuration option will be available to course creators when adding a new graded LTI 1.3 block to a course.
This configuration will be called *Tool Grading Configuration* and offer the following options:

.. list-table::
   :widths: auto
   :header-rows: 1

   * - Option name
     - Behavior
   * - Only allow tools to push a single grade per student (Default)
     - This is the "declarative" approach, where the platform will create a single LineItem, and only allow read-only access to it.
       The tool is only able to read LineItems, push scores and retrieve grades.
   * - Allow tools to manage their own grades
     - This is the "programmatic" approach, where tools have full permissions to create, edit and delete LineItems, and well as
       pushing and retrieving grades. Note that there might be cases where a tool doesn't set a `resouceLinkId` leaving the grade
       unlinked to a problem. Also, the other edge case is when a tool pushes multiple grades for a single problem, in which case
       the implementation needs to decide on a criteria to merge the grades or pick one.

Declarative grade handling
~~~~~~~~~~~~~~~~~~~~~~~~~~
When the LTI configuration is created, a signal should trigger the creation of a LineItem if the tool is configured to use the declarative
model. The LineItem created will have the following attributes:

.. list-table::
   :widths: auto
   :header-rows: 1

   * - Attribute
     - Value
   * - lti_configuration
     - LTI configuration just created.
   * - resource_id
     - Blank, this is used by LTI tools in the programmatic interaction model.
   * - label
     - The problem title, derived from the block's attributes.
   * - score_maximum
     - Maximum score for this given problem, derived from the block's attributes.
   * - tag
     - Blank, this is used by LTI tools in the programmatic interaction model.
   * - start_date_time and end_date_time
     - The problem's start and end date, if available in the block's attributes.

Programmatic grade handling
~~~~~~~~~~~~~~~~~~~~~~~~~~~
No LineItems are created when the LTI configuration model is created, but the tools have permissions to create, update and
delete LineItems using the LineItem endpoint.

A *post_save* Django signal in the *LtiAgsScore* should be responsible for loading the XBlock from the modulestore,
bind the user to the session, and set the score (after doing the proper scaling using the `scoreMaximum` attribute).

If a tool creates and links multiple problems to the same grade, the platform will ??? the results.

???: Not sure what should be the behavior here:
1. Link just the latest grade submitted by the tool.
2. Average all items and submit average to block.

If a tool doesn't send any grades back or doesn't link any *resourceLinkId's* to a LineItem, the block will stay ungraded.

Consequences
============

1. This will make the platform LTI compliant and allow simpler grading workflows (if supported by tools).
2. When using the programmatic approach, tools might not send a grade back, leaving students ungraded.
3. Also when usint the programmatic approach, tools might send/link more than one grade for a given problem, and the criteria we're using to handle that is purely technical.
