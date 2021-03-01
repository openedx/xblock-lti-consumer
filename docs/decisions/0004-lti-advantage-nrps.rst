LTI Advantage NRPS (Names and Roles provisioning services)
----------------------------------------------------------

Status
======

In Review

Context
=======

One of the LTI Advantage services is the `Names and Roles Provisioning Services (NRPS)`_, which allows LTI tools
to retrieve a user list associated with the learning context and internally provision resources for them.

From the LTI-NRPS Specification:

    The Names and Role Provisioning Services is based on IMS Learning Information Services (LIS) [LIS-20]
    and W3C Organization Ontology [W3C-ORG]. It is concerned with providing access to data about users’ roles
    within organizations, a course being an example of an organization. So a very common purpose for this service
    is to provide a roster (list of enrolments) for a course.

The LTI-NRPS services has two services which provide user data in the following format:

.. code-block:: json
    {
        "id" : "https://lms.example.com/sections/2923/memberships",
        "context": {
            "id": "2923-abc",
            "label": "CPS 435",
            "title": "CPS 435 Learning Analytics",
        },
        "members" : [
            {
                "status" : "Active",
                "name": "Jane Q. Public",
                "picture" : "https://platform.example.edu/jane.jpg",
                "given_name" : "Jane",
                "family_name" : "Doe",
                "middle_name" : "Marie",
                "email": "jane@platform.example.edu",
                "user_id" : "0ae836b9-7fc9-4060-006f-27b2066ac545",
                "lis_person_sourcedid": "59254-6782-12ab",
                "roles": [
                    "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
                ]
            }
        ]
    }

Where the only required fields for each member are :code:`user_id` and :code:`roles`, to avoid unintended PII transmission to a third party.
But since one of the purposes of this API is to enable tools access to user PII, the implementation should provide a flag to enable the consumer
to pass additional PII parameters such as name, email, and a profile picture url.

The main issue with enabling this API (`even with pagination as defined in the spec`_) is that it would allow tools to scrape enrollments for all
students in a given course. Given the scale of some courses in edX.org, even if the API is made more performant with cursor pagination,
we're still left with an API pattern that would be actively encouraging clients out there to make hundreds of thousands of successive requests in order
to crawl enrollment data.

.. _`Names and Roles Provisioning Services (NRPS)`: http://www.imsglobal.org/spec/lti-nrps/v2p0
.. _`even with pagination as defined in the spec`: http://www.imsglobal.org/spec/lti-nrps/v2p0#limit-query-parameter

Decision
========

Implement the LTI NRPS for courses up to a predefined (and configurable) number of active enrollments.
Above that number, the service endpoint will return HTTP status 403 (Forbidden).

This is the simplest implementation that allows us to provide the LTI NRPS service and mitigate the concerns mentioned above.
The NRPS services availability and behavior will be controlled by the following toggles:

.. list-table::
   :widths: auto
   :header-rows: 1

   * - Toggle name
     - Type
     - Behavior
   * - LTI_NRPS_ENABLED
     - Feature flag
     - Enables and disables LTI NRPS globally in the Open edX instance. Is disabled by default.
   * - LTI_NRPS_ACTIVE_ENROLLMENT_LIMIT
     - Django setting
     - Controls the allowed number of active enrollments allowed where the API is still available.
       Defaults to 1000 active enrollments at first.
   * - LTI_NRPS_TRANSMIT_PII
     - CourseWaffleFlag
     - Allows the tool to access student and instructor PII (username, email, full name, profile picture).
       Defaults to False.


Consequences
============

* Small courses will be able to use LTI NRPS endpoints on their tools, up to a limited amount of users.
* Big MOOCs (with millions of users) won't be able to scrape enrollment data on edX and potentially cause stability issues.
*


Discarded solutions
===================

Don't implement NRPS
~~~~~~~~~~~~~~~~~~~~
This would not enable course creators to use LTI advantage tools that make use of this functionality.

Implement NRPS gated by course
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
While this would work, it adds a maintenance burden of keeping and updating a whitelist.
Also, long running MOOCs can grow to sizes that could potentially affect instance stability when
using the API.

Implement NRPS limiting the context of the data retrieved
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Complex to implement given the benefit. To get consistency on the LTI tool side, the implementation
would need to create user groups and effectively isolate them in the tool (potentially using a different resourceLink),
which doesn't work for a few LTI integrations (forums, course wide leaderboard, instructor grading inside the tool and others).