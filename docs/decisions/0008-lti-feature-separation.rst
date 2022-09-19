0008 LTI Feature Control
#########################################################

Status
******
**Proposed**

Context
*******

Even after the refactoring described in :doc:`0006-pluggable-lti-configuration.rst` and :doc:`0007-lti-1p3-decoupling.rst` the xblock-lti-consumer library has features which will not work outside of the LMS.

For example, grading endpoints modify objects which exist only in the LMS. NRPS requires access to the full user object. If you attempt to use these LTI features in another IDA such as exams, they will fail.

The :code:`LtiConfiguration` model contains data for all of these features even though not all of them will be used and may not even be available in non-LMS installations.

On the plus side, the first planned LTI use outside of the LMS is in the exam service where it will be managed by mode knowledgeable site staff via the admin pages rather than by course staff. And LTI use outside of an xblock requires code support, so even before this setup it will have to work in the IDA context during development.

What if anything should we do to prevent LTI from being configured in impossible ways?

Decision
********

Initially, we will continue on the path described in previous ADRs to pull LTI launch out of the xblock.

Once we have separated LTI launch and used it in an IDA we will have a better idea of how it works in practice. At that point we will split the generic LTI parts into their own library which will be imported by the xblock specific features. We expect tat LTI Advantage and its endpoints will remain in the xblock library, while the LTI 1.1 and 1.3 launch code moves into this new library.

As part of this split we will separate the grab-bag :code:`LtiConfiguration` into LTI launch and LTI advantage configurations. One config object will become at least two, we do not currently know the correct split.

We will not implement an LTI feature control object in settings or feature flags.

Consequences
************

* First, finish the work described in earlier ADRs to separate launch from xblock.
* Use LTI somewhere other than the LMS to learn how that really behaves.
* Using that experience, separate xblock and LMS features from the base LTI library.

Rejected Alternatives
******************

* We could control which LTI features are available using Django settings. This would place LTI information into the settings files of various IDA which include the LTI library. It would be difficult for IDA maintainers to properly test and confusing for most IDA users to read.
* We could check feature availability at runtime, so for example the grades endpoint can fail early when it detects that there is no way to actually correctly modify grades. This introspective code will be confusing for most readers for the small benefit of better errors.
* We could add an additional configuration object which describes what features of the regular configuration object are actually available. This adds another setup step to get LTI working and introduces possible conflict between configuration levels.

All of these seemed too confusing to future users and maintainers for too little benefit.


