LTI Advantage AGS Score Linking
-------------------------------

Status
======

Accepted

Context
=======

LTI Advantage provides new ways for LTI tools to push grades back into the platform through the `Assignment and Grades Services (AGS)`_,
which don't map 1:1 with the grading and gradebook structure present in Open edX.

There are two models of interaction to pushing grades to the platform in the LTI AGS services:

1. Declarative: the platform creates a LineItem (equivalent of a gradebook line/grade) and tools can only push results to that item.
2. Programmatic: the tool uses the AGS endpoints to manage its own line items and grades. The tool is responsible for linking each line item to the resourceLinks, which means that a tool might not link a grade to its respective problem.

See a more detailed description in the `Coupled vs decoupled line items`_ section of the spec.

.. _`Assignment and Grades Services (AGS)`: https://www.imsglobal.org/spec/lti-ags/v2p0
.. _`Coupled vs decoupled line items`: https://www.imsglobal.org/spec/lti-ags/v2p0#coupled-vs-decoupled-line-items


Decisions
=========

To achieve full LTI Advantage compatibility on the platform we need to allow both the declarative and programmatic
interaction models to happen. In order to maximize tool support, we re-enabled the programmatic approach.
Note that this comes with caveats, explained in the consequences section below.

Given the platform's fixed gradebook structure, the declarative interaction model detailed in the
`LTI-AGS Spec - Declarative interaction model`_ is the default option when setting up an XBlock. This also ensures
we're not changing any setting of blocks already in use.

.. _LTS-AGS Spec - Declarative interaction model: https://www.imsglobal.org/spec/lti-ags/v2p0#declarative-


Declarative grade handling
~~~~~~~~~~~~~~~~~~~~~~~~~~
This is the default configuration for an LTI 1.3 XBlock.
When the XBlock is set up, a LineItem will be created with the attributes listed in the table below:

.. list-table::
   :widths: auto
   :header-rows: 1

   * - Attribute
     - Value
   * - lti_configuration
     - LTI configuration just created.
   * - resource_id
     - Blank, this is only used by LTI tools in the programmatic interaction model.
   * - label
     - The problem title, derived from the block's attributes.
   * - score_maximum
     - Maximum score for this given problem, derived from the block's attributes.
   * - tag
     - Blank, this is only used by LTI tools in the programmatic interaction model.
   * - start_date_time
     - The problem's start date, if available in the block's attributes.
   * - end_date_time
     - The problem's end date, if available in the block's attributes.

Using the :code:`declarative` mode, the tool won't be able to manage LineItems, just retrieve them and post grades for students.


Programmatic grade handling
~~~~~~~~~~~~~~~~~~~~~~~~~~~
When the programmatic grade handling is enabled, no LineItems will be created when the consumer is instanced, but the tokens issued
by the Access Token endpoint will have the :code:`lineitem` scope, which allows creating and managing LineItems in the platform.


Consequences
============

* This will make the LTI Consumer XBlock fully compliant to the LTI-AGS specification if the programmatic interaction model is selected in the XBlock settings.
* The :code:`programmatic` approach delegates the grade linking and handling to the tool and scores will only be linked back to the gradebook if the tools sets
a valid :code:`resourceLinkId` as defined in the LTI-AGS specification.
