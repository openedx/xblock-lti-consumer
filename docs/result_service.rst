LTI 2.0 Result Service 2.0
**************************

The `LTI 2.0 Result Service 2.0 <https://www.imsglobal.org/lti/model/uml/purl.imsglobal.org/vocab/lis/v2/outcomes/Result/service.html>`_
is a REST API that allows reading and updating individual Learning Information Services Result resources. See also
`10.2 LIS Result Service <https://www.imsglobal.org/specs/ltiv2p0/implementation-guide#toc-43>`_. A Result represents
an Outcome, or a grade, for an LTI component.

The implementation in ``xblock-lti-consumer`` supports the "GET", "PUT", and "DELETE" request types.

Testing
=======

Setup
-----

* Set up an LTI 1.1/1.2 component in Studio and publish it. You can use the SaLTIre Test Tool Provider, as described in
  the README.rst file in the root of this repository. The following instructions assume you are using the SaLTIre Test
  Tool Provider.

  * Set "Scored" to True on the LTI 1.1/1.2 component.

* Set up your preferred API development and testing tool, like Postman. The following instructions assume you are using
  Postman, but they should be generalizable to any API development and testing tool.
    
  * Set the request method to the correct request type. The Result Service supports "GET", "PUT", and "DELETE" request
    types.
  * Set the URL to the Result Service URL. You can get the Result Service URL by visting the LMS LTI rest endpoints
    view. Go to ``https://<LMS_DOMAIN>/courses/<COURSE_ID>/lti_rest_endpoints/``, find your LTI component, and select
    the ``lti_2_0_result_service_json_endpoint``. Note that you should use ``http`` as the protocol if you are using
    devstack. The URL will be of the form
    ``https://<LMS_DOMAIN>>/courses/<COURSE_ID>>/xblock/<USAGE_KEY>/handler_noauth/result_service_handler/user/{anon_user_id}``.
    You will need to substitute an appropriate value for ``anon_user_id``.

    * If you are using the SaLTIre Test Tool Provider, the
      ``sourcedId`` will be displayed live in the LTI component in the LMS under the "Message Parameters" section; it
      is the ``lis_result_sourcedid``.
    * If you do not have the ``lti_consumer.enable_external_user_id_1p1_launches`` ``CourseWaffleFlag`` enabled, you
      can also find the anonymous user ID in the CSV you can download from 
      Instructor Dashboard > Data Download > Get Student Anonymized IDs CSV.

  * If you're using the "PUT" request type, set the "Content-Type" header under "Headers" to
    ``application/vnd.ims.lis.v2.result+json``. In Postman, you must redefine the header in order to override the
    default "Content-Type" header, which is computed automatically.
  * Set the Body type to "raw".
  * Set the Body contents to the JSON below. You can update the value of the "resultScore" key to change the score
    or "comment", as needed.
  * Set the Authorization header by following the directions below.
  * Send the request.

    .. code:: json

        {
            "@context" : "http://purl.imsglobal.org/ctx/lis/v2/Result",
            "@type" : "Result",
            "resultScore" : 0.83,
            "comment" : "This is exceptional work."
        }

Computing the Authorization Header
----------------------------------

* In order for a Tool Provider to send a Basic Outcomes Service request, it must do so securely. It does so by signing
  the request using OAuth1. You will need to sign the request.
* OAuth1 was intended to sign form-based requests, but the Basic Outcomes Service requests use an "Plain Old XML" (POX)
  payload.
* OAuth1 has an extension called OAuth body signing, which we use to sign a non-form-based request.
* OAuth body signing has two steps.

#. Hash the request body.

   #. The OAuth1 header ``oauth_signature_method`` defines which hashing method to use.
   #. The hashed value is stored in the OAuth1 Authorization header under the ``oauth_body_hash`` key.
        
#. Sign the OAuth Authorization header using the shared secret.

   #. The hashed value is stored in the OAuth1 Authorization header under the ``oauth_signature`` key.

Instructions
^^^^^^^^^^^^

* Open a Python shell. Install the ``oauthlib`` Python package.

  * Alternatively, you can open a Django shell in the LMS or Studio devstack container with ``make lms-shell`` or
    ``make studio-shell``, respectively. ``oauthlib`` is installed in both containers as a necessary dependency of
    ``xblock-lti-consumer``.

* Run the following commands to compute the Authorization header. The below commands assume you are making a "PUT"
  request. You will need to change ``json_body``, ``http_method``, and ``headers`` if you are making a "GET" or
  "DELETE" request.

  * The values for ``client_key`` and ``client_secret`` come from your LTI passport string, as described in the
    README.rst file in the root of this repository.

    .. code:: python

        >>> from oauthlib import oauth1
        >>> client_key="test"
        >>> client_secret="secret"
        >>> client = oauth1.Client(client_key=client_key, client_secret=client_secret)
        >>> result_service_url = "http://localhost:18000/courses/course-v1:edX+1717N1+Y2022N1/xblock/block-v1:edX+1717N1+Y2022N1+type@lti_consumer+block@1bca781ee09347a6800ad29c346abc07/handler_noauth/result_service_handler/user/1bc0b578-6f17-4e32-917a-94dc63edddda"
        >>> json_body = """{
        >>>     "@context" : "http://purl.imsglobal.org/ctx/lis/v2/Result",
        >>>     "@type" : "Result",
        >>>     "resultScore" : 0.83,
        >>>     "comment": "This is exceptional work."
        >>> }"""
        >>> uri, headers, body = client.sign(result_service_url, http_method=<"PUT">, body=json_body, headers={"Content-Type": "application/vnd.ims.lis.v2.result+json"})
 
* The value of ``headers`` should look something like this.

  .. code:: python

      {'Content-Type': 'text/xml','Authorization': 'OAuth oauth_nonce="5609288327616222561669665375", oauth_timestamp="1669665375", oauth_version="1.0", oauth_signature_method="HMAC-SHA1", oauth_consumer_key="test", oauth_body_hash="vAVegN28HcixFW7OuHgfx0Ld%2Bdk%3D", oauth_signature="4Or9QJKG66jFHpZU6JeyNHcYdDk%3D"'}

* Take the Authorization header and set the Authorization header under "Headers" to the value in your preferred API
  development and testing tool. 

Troubleshooting
---------------

* If you see the following error when trying to upload an outcome 
  ``lti_consumer.lti_1p1.exceptions.Lti1p1Error: OAuthbody hash verification has failed``, your body hash was
  incorrectly computed. Make sure that ``result_body`` matches the body you are including as data in your "PUT"
  request. A breakpoint in the Result Service request code can be helpful to see the value of the request body
  as compared to the ``oauth_body_hash`` provided in the Authorization header.
* If you’re switching between anonymous user IDs and external user IDs (i.e. toggling the 
  ``lti_consumer.enable_external_user_id_1p1_launches`` ``CourseWaffleFlag``, you’ll need to update your URL in Postman
  with the correct ``anon_user_id`` and recompute and reset the Authorization header in your preferred API development
  and testing tool using the instructions above.