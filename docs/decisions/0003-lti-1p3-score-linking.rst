LTI Advantage AGS Score Linking
-------------------------------

Status
======

In Review

Context
=======

LTI Advantage provides new ways for LTI tools to push grades back into the platform through the `Assignment and Grades Services (AGS)`_,
which don't map 1:1 with the grading and gradebook structure present in Open edX.

There's two models of interaction to pushing grades to the platform in the LTI AGS services:

1. Declarative: the platform creates a LineItem (equivalent of a gradebook line/grade) and tools can only push results to that item.
2. Programmatic: the tool uses the AGS endpoints to manage it's own line items and grades. The tool is responsible for linking each line item to the resourceLinks, which means that a tool might not link a grade to it's respective problem.

See a more detailed description in the `Coupled vs decoupled line items`_ section of the spec.

.. _`Assignment and Grades Services (AGS)`: https://www.imsglobal.org/spec/lti-ags/v2p0
.. _`Coupled vs decoupled line items`: https://www.imsglobal.org/spec/lti-ags/v2p0#coupled-vs-decoupled-line-items


Decisions
=========

Given the platform's fixed gradebook structure, we'll implement the declarative interaction model detailed in the
`LTS-AGS Spec - Declarative interation model`_.

In the future, we want to enable the platform to have full LTI Advantage compatibility, so we need to allow both the declarative and programmatic
interaction models to happen. There's already full support for the programmatic approach, but we decided to restrict the tool's access since we
don't want to deal with mixing and averaging multiple grades in the current implementation.

.. _`LTS-AGS Spec - Declarative interation model`: https://www.imsglobal.org/spec/lti-ags/v2p0#declarative-

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
   * - start_date_time
     - The problem's start date, if available in the block's attributes.
   * - end_date_time
     - The problem's end date, if available in the block's attributes.

Consequences
============

This will NOT make the platform LTI compliant since it doesn't allow the programmatic grade interaction.
