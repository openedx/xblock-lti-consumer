Changelog
=========

..
   All enhancements and patches to xblock-lti-consumer will be documented
   in this file.  It adheres to the structure of https://keepachangelog.com/ ,
   but in reStructuredText instead of Markdown (for ease of incorporation into
   Sphinx documentation and the PyPI description).

   This project adheres to Semantic Versioning (https://semver.org/).

.. There should always be an "Unreleased" section for changes pending release.

Please See the [releases tab](https://github.com/edx/xblock-lti-consumer/releases) for the complete changelog.

Unreleased
~~~~~~~~~~

4.4.0 - 2022-08-17
------------------
* Move the LTI 1.3 Access Token and Launch Callback endpoint logic from the XBlock to the Django views
* Adds support for accessing LTI 1.3 URLs using both location and the lti_config_id

4.2.2 - 2022-06-30
------------------
* Fix server 500 error when using names/roles and grades services, due to not returning a user during auth.

4.2.1 - 2022-06-27
------------------
* Add event tracking to LTI launches

4.0.1 - 2022-05-09
------------------
* Add `Learner` to LTI launch roles in addition to the `Student` value

4.0.0 - 2022-05-09
------------------

* Adds support for loading external LTI configurations from Open edX plugins implementing filters for the event
  `org.openedx.xblock.lti_consumer.configuration.listed.v1`. This can be enabled by setting a Course Waffle Flag
  `lti_consumer.enable_external_config_filter` for specific courses.

3.4.7 - 2022-07-08
------------------
* Fix server 500 error when using names/roles and grades services, due to not returning a user during auth.
  This is a bugfix backport of 4.2.2 for the Nutmeg release.

3.4.6 - 2022-03-31
------------------

* Fix rendering of `lti_1p3_launch_error.html` and `lti_1p3_permission_error.html` templates

3.4.5 - 2022-03-16
------------------

* Fix LTI Deep Linking return endpoint permission checking method by replacing the old one with the proper
  Studio API call.

3.4.4 - 2022-03-03
------------------

* Fix LTI 1.3 Deep Linking launch url - always perform launch on launch URL, but update `target_link_uri` when
  loading deep linking content.
  See LTI 1.3 spec at: https://www.imsglobal.org/spec/lti/v1p3#target-link-uri

3.4.3 - 2022-02-01
------------------

* Fix LTI 1.1 template rendering when using embeds in the platform

3.4.2 - 2022-02-01
------------------

* Fix LTI 1.1 form rendering so it properly renders quotes present in titles.
* Migrate LTI 1.1 launch template from Mako to Django template.
* Internationalize LTI 1.1 launch template.

3.4.1 - 2022-02-01
------------------

* Fix the target_link_uri parameter on OIDC login preflight url parameter so it matches 
  claim message definition of the field.
  See docs at https://www.imsglobal.org/spec/lti/v1p3#target-link-uri

3.4.0 - 2022-01-31
------------------

* Fix the version number by bumping it up to 3.4.0

3.3.0 - 2022-01-20
-------------------

* Added support for specifying LTI 1.3 JWK URLs.

3.2.0 - 2022-01-18
-------------------

* Dynamic custom parameters support with the help of template parameter processors.

3.1.2 - 2021-11-12
-------------------

* The modal to confirm information transfer on open of lti in new tab/window has been updated
  because of a change in how browsers handle iframe permissions.

3.1.0 - 2021-10-?
-------------------

* The changes which led to this version change were not adequetly documented.

3.0.1 - 2021-07-09
-------------------

* Added multi device support on student_view for mobile.


3.0.0 - 2021-06-16
-------------------

* Rename `CourseEditLTIFieldsEnabledFlag` to `CourseAllowPIISharingInLTIFlag`
  to highlight its increased scope.
* Use `CourseAllowPIISharingInLTIFlag` for LTI1.3 in lieu of the current
  `CourseWaffleFlag`.


2.11.0 - 2021-06-10
-------------------

* NOTE: This release requires a corresponding change in edx-platform that was
  implemented in https://github.com/edx/edx-platform/pull/27529
  As such, this release cannot be installed in releases before Maple.
* Move ``CourseEditLTIFieldsEnabledFlag`` from ``edx-platform`` to this repo
  while retaining data from existing model.


2.10.1 - 2021-06-09
-------------------

* LTI 1.3 and LTI Advantage features are now enabled by default.
* LTI 1.3 settings were simplified to reduce confusion when setting up a LTI tool.
* Code quality issues fixed


2.9.1 - 2021-06-03
------------------

* LTI Advantage - NRP Service: this completes Advantage compliance.


2.8.0 - 2021-04-13
------------------

* LTI Advantage - AGS Service: Added support for programmatic grade management by LTI tools.
* Improved grade publishing to LMS when using LTI-AGS.
* Increase LTI 1.3 token validity to 1h.


2.7.0 - 2021-02-16
------------------

* Add support for presenting `ltiResourceLink` content from deep linking.


2.6.0 - 2021-02-16
------------------

* Deep Linking content presentation implementation, for resource links, HTML,
  HTML links, and images.

* Fix bug with `config_id` migration where an entry was created _during_
  the migration and did _not_ receive a valid UUID value.


2.5.3 - 2021-01-26
------------------

* LTI Deep Linking Launch implementation, implementing DeepLinking Classes and request
  request preparation.
* LTI Deep Linking response endpoint implementation, along with model to store selected configuration and
  content items.

2.5.2 - 2021-01-20
------------------

* Fix issue with migration that causes migration failure due to duplicate `config_id` values.

2.5.1 - 2021-01-19
------------------

* Simplify LTI 1.3 launches by removing OIDC launch start view.

2.5.0 - 2021-01-15
------------------

* Add LTI 1.1 config on model.

2.4.0 - 2020-12-02
------------------

* Partially implemented the Assignment and Grades Service to enable tools
  reporting grades back.  Tools cannot create new LineItems.

2.3 – 2020-08-27
----------------

* Move LTI configuration access to plugin model.

2.2 – 2020-08-19
----------------

* Modals are sent to the parent window to work well with the courseware
  micro-frontend.  A new message is sent to the parent window to request a
  modal containing the contents ot the LTI launch iframe.

2.1 – 2020-08-03
----------------

* The LTI consumer XBlock is now indexable.

* Implement the LTI 1.3 context claim.

2.0.0 – 2020-06-26
------------------

* LTI 1.3 support.

