Unified Flag for Enabling Sharing of PII in LTI
-----------------------------------------------

Status
======

Proposal

Context
=======

LTI integrations can be enhanced by sharing some level of personal information
about users, such as their username and email. Sharing such information allows
for a smoother registration flow among other benefits.

The `LTI XBlock has options
<https://github.com/openedx/xblock-lti-consumer/blob/edec2a68282a2a1fc2b2036e1989d60688fa6b19/lti_consumer/lti_xblock.py#L471-L487>`_
called ``ask_to_send_username`` and ``ask_to_send_email`` that enable sending
such PII to the external tool. However, `by default these options are not
visible
<https://github.com/openedx/xblock-lti-consumer/blob/edec2a68282a2a1fc2b2036e1989d60688fa6b19/lti_consumer/lti_xblock.py#L588-L599>`_
to course authors, and there is no way to send PII to LTI tools. In order to
even enable these options to appear in the LTI XBlock configuration, you need
to first set a `configuration flag
<https://github.com/openedx/edx-platform/blob/e19ba34f5a564285b3a20a7298c20ca640ca5aa0/cms/djangoapps/xblock_config/models.py#L38-L86>`_
via Django admin in studio.

This configuration flag unlocks the editing of the above fields after which
those fields can be set to allow sharing of PII. The configuration flag works
on a course-wide level, while the flags above work on a per-LTI-XBlock-basis.

With the recent addition of LTI Course tabs, there is need for a similar
mechanism for enabling sending of PII. What needs to be determined is whether
we should use the same flag for the purpose, or create a new flag for this use
with LTI tabs.

The arguments for creating a new flag are:

1. The scope of the current flag doesn't match the new use case.
2. Currently the flag is implemented in studio, while the flag now needs to be
   used in LMS and MFEs.
3. Keeping flags separate allows controlling this flag separately for course
   tabs vs XBlocks.

The arguments for using the same flag are:

1. As part of `EDUCATOR-121 <https://openedx.atlassian.net/browse/EDUCATOR-121>`_
   this config flag is already supposed to be moved to the LTI XBlock, which
   would make it usable from LMS and Studio.
2. The name and scope can both be changed while retaining the data.
3. It's confusing to have two flags with very similar purposes.
4. There is already a double layer of flags here. Enabling this flag will enable
   configuring other option which in turn enable sending PII data. Adding
   another separate flag doesn't help the situation. Even if the flag is only
   needed for either tabs or XBlocks, there is another step to enabling sharing
   PII which can simply be skipped if undesired.

Decision
========

Given the above context it makes sense to move the existing flag to the LTI
XBlock while making sure it uses the same data table. This move means that the
flag will now be accessible via LMS and Studio, which is what is needed.

The LTI course tabs code will be modified to check this value before allowing
the sending of PII even if the tab's configuration allows sending PII.

Currently, if this flag is enabled for a course, and the `ask_to_send_*` options
are enabled for an XBlock, disabling this flag will not stop the XBlock from
sending PII. This flag will *only* disable editing the `ask_to_send_*` options.
This might not be desirable behavior. So we can also modify the scope of this
flag to be the final arbiter of whether PII sharing is allowed or not instead
of just controlling if those fields are editable.

Additionally, any PII sharing via LTI1.3 can also be folded under the same flag.

We should also add an indication to users that this flag is the reason for their
inability to edit these fields in UI instead of just hiding the fields. Users
can be given information about getting this flag enabled for their course.

Consequences
============

If this proposal is implemented, there will be one consistent flag
(``CourseEditLTIFieldsEnabledFlag``) that can be set for a course to
enable/disable sharing of PII via LTI. This flag will apply for all LTI
XBlocks, and for all LTI course tabs (currently only Discussions LTI tab).

Additionally, if ``CourseEditLTIFieldsEnabledFlag`` is enabled for a course and
subsequently disabled, then existing sharing of PII via LTI will stop across
all LTI versions used by any course tab or LTI XBlock.

A quick breakdown of how different options will work together once this
proposal is implemented:

- **CourseEditLTIFieldsEnabledFlag**: When this flag is disabled for a course
  (the default), course authors will not see any options to send PII and no PII
  will be sent by any LTI tool embedded in the course using course tabs or the
  official LTI XBlock. If this flag was once enabled, and PII sharing options
  were also enabled, they will be **overridden** by this flag.

- **ask_to_send_username** and **ask_to_send_email**: If the above flag is
  enabled the course author will see a UI with these options in the LTI
  Course block (and course LTI tab configuration once that UI for that is
  available). These optons can only be set if the above flag is enabled,
  otherwise API operations to enable them should fail and their value will be
  overridden to disabled.
