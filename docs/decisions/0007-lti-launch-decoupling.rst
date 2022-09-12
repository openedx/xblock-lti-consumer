0007 Decouple LTI Launches from XBlock and edX Platform
#######################################################

Status
******
**Draft (=> Accepted)**

Context
*******

**Definitions**

In this document, the terms "launch context" and "launch information" are used. Launch context describes the
technological environment or application in which an LTI launch occurs. For example, the launch context may be an
XBlock, a course, a Django application, an independently deployable application (IDA), etc. Launch information describes
information included in or necessary for an LTI launch. Launch information is relative to the launch context. For
example, a user identifier or a user role is launch information. Launch information may refer to data that are used as
query or form parameters of a request, as claims in a JSON web token (JWT), or as data needed by the library to
function.

**Problems**

Open edX would like to support the following LTI launch use cases:

* content launches from an XBlock launch context
* content launches from multiple XBlocks, reusing LTIConfigurations between them (i.e. course launch context)
* content launches from outside an XBlock launch context in the platform (e.g. LTI course tabs, LTI 1.3 embedded
  discussions)
* content launches from an independently deployable application (i.e. IDA or Django application context)

This library implements both LTI 1.1 and LTI 1.3 launches.

**LTI 1.1**

Currently, LTI 1.1 launches are already decoupled from the XBlock and the edx-platform. The `lti_embed
<https://github.com/openedx/xblock-lti-consumer/blob/master/lti_consumer/lti_1p1/contrib/django.py#L13>`_ function
accepts a series of arguments that define necessary launch information and returns an HTML template with Javascript that
initiates an LTI 1.1 launch. No additional work is required to decouple LTI 1.1 launches, but this document will
describe changes necessary to bring LTI 1.1 launches in alignment with the below strategy for LTI 1.3 launches.

**LTI 1.3**

LTI 1.3 launches rely on the ``location`` field of the ``LtiConfiguration`` model. The ``location`` field is
a ``UsageKeyField`` and represents the location of the XBlock associated with the ``LtiConfiguration`` instance. This
association was made because, originally, the XBlock was the source of truth for LTI configuration information and was
the only launch context in which LTI launches occurred.

The dependence on the ``location`` field prevents LTI 1.3 launches from being possible outside the launch context of an
XBlock. This prevents Open edX from using LTI more widely across the platform and across the ecosystem, because its use
is restricted to specific launch contexts in which ``location`` is meaningful.

For example, because ``LTIConfiguration`` instances are associated with a particular ``location``, it is not possible
for a ``LtiConfiguration`` to be reused across different XBlocks (i.e. a course launch context), even if the
``LtiConfiguration`` would be identical amongst the different XBlocks.

In an LTI 1.3 launch, the ``location`` field is used to determine the
``https://purl.imsglobal.org/spec/lti/claim/roles`` and ``https://purl.imsglobal.org/spec/lti/claim/context`` claims of
the LTI 1.3 launch. In an LTI 1.3 launch, the ``https://purl.imsglobal.org/spec/lti/claim/roles`` claim is required, and
the ``https://purl.imsglobal.org/spec/lti/claim/context`` claim is optional. This couples the LTI 1.3 launches to the
XBlock through the ``location`` field.

Furthermore, LTI 1.3 launches are also dependent on functions imported from edx-platform. These functions are used `to
get the requesting user's role
<https://github.com/openedx/xblock-lti-consumer/blob/master/lti_consumer/plugin/views.py#L182>`_, `to get the requesting
user's external ID <https://github.com/openedx/xblock-lti-consumer/blob/master/lti_consumer/plugin/views.py#L183>`_, `to
get the course key from the location field
<https://github.com/openedx/xblock-lti-consumer/blob/master/lti_consumer/plugin/views.py#L181>`_, etc. This prevents LTI
1.3 launches from running outside of the platform.

https://github.com/openedx/xblock-lti-consumer/pull/254 decoupled the LTI 1.3 launch handler endpoint
``launch_gate_endpoint``, the LTI 1.3 keyset endpoint ``public_keyset_endpoint``, and the LTI 1.3 access token endpoint
``access_token_endpoint`` from the XBlock by moving these endpoints into the Django plugin. This was the first step in
decoupling the XBlock from the LTI 1.3 launch. This decision describes how to fully decouple the LTI 1.3 launch from the
XBlock and how to modify the LTI 1.1 launch to follow this pattern.

Decision
********

**LTI 1.3**

* For backwards compatability, we will not remove references to the ``location`` field from the
  ``public_keyset_endpoint`` and ``access_token_endpoint`` endpoint. This is because LTI 1.3 integrations may exist in
  the platform and in other installations that use URLs that contain the
  ``usage_key`` in them.
* We will change the URLs that are displayed in Studio for the ``public_keyset_endpoint`` and
  ``access_token_endpoint` endpoints. This will prevent additional LTI 1.3 configurations that use the ``usage_key``. This
  makes us more able to deprecate URLs that use ``usage_key`` and to remove references to ``location``.
* The responsibility of determining the launch information included in an LTI launch (e.g. roles and context claims)
  will be that of the launch context in which the LTI 1.3 launch occurs (e.g. XBlock, IDA).
* For LTI 1.3 launches, launch information will be encoded in an instance of a launch data class called
  Lti1p3LaunchData.
* The library will expose a Python API function that will return the URL that initiates the LTI 1.3 launch - the third
  party initiated login URL. This Python API function may be `get_lti_1p3_content_url
  <https://github.com/openedx/xblock-lti-consumer/blob/master/lti_consumer/api.py#L186>`_.
* Each launch context will supply the launch information to the LTI 1.3 launch by including an instance of
  Lti1p3LaunchData as an argument to the aforementioned function. Each launch context will call this function to fetch
  the URL to trigger an LTI 1.3 launch.
* In order for this launch information to be available throughout the LTI 1.3 launch, the library will cache the the
  launch information provided by the launch context in the third-party initiated login request and include the cache_key
  in the ``lti_message_hint`` query or form parameter. This allows the library to read the launch_data out of the cache
  when necessary by using the ``lti_message_hint``.
* The third-party initiated login request ``login_hint`` query or form parameter will be used to include the user
  identifier. The ``login_hint`` will not be used to identify the ``LtiConfiguration`` instance. Information necessary
  to identify the ``LtiConfiguration`` instance will be included in the launch information instead.
* We will not describe how to decouple LTI Advantage Services in this document. This may be done at a later time.

**LTI 1.1**

* For LTI 1.1 launches, launch information will be encoded in an instance of a launch data class called
  Lti1p1LaunchData.
* In order to have a similar interface to LTI 1.3, we will modify the lti_embed function to use an instance of the
  Lti1p1LaunchData class.
* We will modify the ``LtiConsumerXBlock`` to use the `lti_embed
  <https://github.com/openedx/xblock-lti-consumer/blob/master/lti_consumer/lti_1p1/contrib/django.py#L13>`_ function to
  initiate the LTI 1.1 launch.

Consequences
************

* Basic LTI 1.3 launches will be decoupled from the XBlock and from the edX platform. This will allow Open edX to better
  leverage LTI across the platform and across the ecosystem.
* LTI Advantage Services will not be decoupled from the XBlock and from the edX platform. This means that LTI Advantage
  Services will not necessarily be available in all launch contexts. This fits our current needs, but it may not fit
  future needs. This challenge will need to be addressed in a future decision.

  * This means that the ``location`` field on the ``LtiConfiguration`` will need to remain for the time being, because
    it is currently used in our implementation of LTI Advantage Services.

* Individual launch contexts will be responsible for sending launch information to the library. This may pose a
  challenge if the launch information is stored in edX platform but the launch context is outside the edX platform (e.g.
  user role). A launch context may choose to determine or define this launch information on its own.
* This library will remain Open edX LTI Certified, because all three Advantage Services are supported on the
  ``CONFIG_ON_XBLOCK`` ``config_store`` setting.

Rejected Alternatives
******************

* Launch contexts define their own views, which import and wrap LTI 1.3 launch views. Launch contexts define launch
  information that they then pass to the LTI 1.3 launch views.

  * Importing and wrapping LTI 1.3 launch views requires a lot of boilerplate code within each launch context's code.
  * For an LTI 1.3 launch, each view would need to be imported and wrapped to supply launch information to each step of
    the LTI 1.3 launch.

* The ``login_hint`` encodes information about the launch context in which the LTI 1.3 launch is occurring, and the
  library determines the launch information based on the launch context.

  * This requires the library to be aware of various launch contexts and how to determine launch information for each
    launch context. This may make extension of the library to other launch contexts more challenging. Contexts would not
    be able to define their own launch information.
  * Launch contexts can simply fetch the URL that initiates the LTI 1.3 launch and trigger the LTI 1.3 launch without
    supplying information to the library.

* The ``lti_message_hint`` encodes the launch information necessary for an LTI 1.3 launch as a JWT.

  * Some browsers enforce limits on the length of URLs for GET requests, and because LTI Tools may make GET requests to
    views defined in this library that support ``lti_message_hint`` as a query or form parameter, using the 
    ``lti_message_hint`` parameter may not work properly in all browsers.

References
**********

* `Github Issue 273: Remove XBlock location dependencies from LTI 1.3 launches
  <https://github.com/openedx/xblock-lti-consumer/issues/273>`_
* `Github Pull Request 254: [BB-5559] Decouple LTI 1.3 from LTI Consumer XBlock functionality
  <https://github.com/openedx/xblock-lti-consumer/pull/254>`_
* `Github Pull Request 288: feat: decouple LTI 1.3 launch from the XBlockLtiConsumer
  <https://github.com/openedx/xblock-lti-consumer/pull/288>`_
* `Github Pull Request 294: API gets config from launch data via config_id
  <https://github.com/openedx/xblock-lti-consumer/pull/294>`_