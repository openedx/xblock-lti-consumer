LTI 1.1/1.2 Basic Outcomes Service 1.1
**************************************

The `LTI 1.1/1.2 Basic Outcomes Service 1.1 <http://www.imsglobal.org/spec/lti-bo/v1p1/>`_ is a service that
"supports setting, retrieving and deleting LIS [Learning Information Services] results associated with a particular
user/resource combination."

The implementation in ``xblock-lti-consumer`` currently only supports the ``replaceResult`` request type.

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
    
  * Set the request method to "POST".
  * Set the URL to the Basic Outcomes Service URL. You can get the Basic Outcomes URL in one of two ways.
        
    * If you are using the SaLTIre Test Tool Provider, the Basic Outcomes Service URL will be displayed live in the
      LTI component in the LMS under the "Message Parameters" section; it is the ``lis_outcome_service_url``.
    * Alternatively, you can visit the LMS LTI rest endpoints view. Go to
      ``https://<LMS_DOMAIN>/courses/<COURSE_ID>/lti_rest_endpoints/``, find your LTI component, and select the
      ``lti_1_1_result_service_xml_endpoint``. Note that you should use ``http`` as the protocol if you are using
      devstack.

  * Set the Body type to "raw".
  * Set the Body contents to the POX ("Plain Old XML") below. You will need to update the value of the
    ``sourcedId`` element with the appropriate ``sourcedId``. If you are using the SaLTIre Test Tool Provider, the
    ``sourcedId`` will be displayed live in the LTI component in the LMS under the "Message Parameters" section; it
    is the ``lis_result_sourcedid``. You can also update the ``resultScore`` element to change the score.
  * Set the Authorization header under "Headers" by following the directions below.
  * Send the request.

    .. code:: xml

      <?xml version="1.0" encoding="UTF-8"?>
      <imsx_POXEnvelopeRequest xmlns="http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">
      <imsx_POXHeader>
      <imsx_POXRequestHeaderInfo>
         <imsx_version>V1.0</imsx_version>
         <imsx_messageIdentifier>999999123</imsx_messageIdentifier>
      </imsx_POXRequestHeaderInfo>
      </imsx_POXHeader>
      <imsx_POXBody>
      <replaceResultRequest>
         <resultRecord>
         <sourcedGUID>
               <sourcedId>course-v1%3AedX%2B1717N1%2BY2022N1:localhost%3A18000-1bca781ee09347a6800ad29c346abc07:0c30252236e467a695663b9aed8d3e5d</sourcedId>
         </sourcedGUID>
         <result>
               <resultScore>
               <language>en</language>
               <textString>0.90</textString>
               </resultScore>
         </result>
         </resultRecord>
      </replaceResultRequest>
      </imsx_POXBody>
      </imsx_POXEnvelopeRequest>

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

* Run the following commands to compute the Authorization header.

  * The values for ``client_key`` and ``client_secret`` come from your LTI passport string, as described in the
    README.rst file in the root of this repository.

    .. code:: python

        >>> from oauthlib import oauth1
        >>> client_key="test"
        >>> client_secret="secret"
        >>> client = oauth1.Client(client_key=client_key, client_secret=client_secret)
        >>> basic_outcomes_url = "http://localhost:18000/courses/course-v1:edX+1717N1+Y2022N1/xblock/block-v1:edX+1717N1+Y2022N1+type@lti_consumer+block@1bca781ee09347a6800ad29c346abc07/handler_noauth/outcome_service_handler"
        >>> basic_outcomes_body = """<?xml version="1.0" encoding="UTF-8"?>
        ... <imsx_POXEnvelopeRequest xmlns="http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">
        ... <imsx_POXHeader>
        ...   <imsx_POXRequestHeaderInfo>
        ...     <imsx_version>V1.0</imsx_version>
        ...     <imsx_messageIdentifier>999999123</imsx_messageIdentifier>
        ...   </imsx_POXRequestHeaderInfo>
        ... </imsx_POXHeader>
        ... <imsx_POXBody>
        ...   <replaceResultRequest>
        ...     <resultRecord>
        ...       <sourcedGUID>
        ...         <sourcedId>course-v1%3AedX%2B1717N1%2BY2022N1:localhost%3A18000-1bca781ee09347a6800ad29c346abc07:0c30252236e467a695663b9aed8d3e5d</sourcedId>
        ...       </sourcedGUID>
        ...       <result>
        ...         <resultScore>
        ...           <language>en</language>
        ...           <textString>0.90</textString>
        ...         </resultScore>
        ...       </result>
        ...     </resultRecord>
        ...   </replaceResultRequest>
        ... </imsx_POXBody>
        ... </imsx_POXEnvelopeRequest>"""
        >>> uri, headers, body = client.sign(basic_outcomes_url, http_method="POST", body=basic_outcomes_body, headers={"Content-Type": "text/xml"})

* The value of ``headers`` should look something like this.

  .. code:: python

      {'Content-Type': 'text/xml','Authorization': 'OAuth oauth_nonce="5609288327616222561669665375", oauth_timestamp="1669665375", oauth_version="1.0", oauth_signature_method="HMAC-SHA1", oauth_consumer_key="test", oauth_body_hash="vAVegN28HcixFW7OuHgfx0Ld%2Bdk%3D", oauth_signature="4Or9QJKG66jFHpZU6JeyNHcYdDk%3D"'}


* Take the Authorization header and set the Authorization header under "Headers" to the value in your preferred API
  development and testing tool. 

Troubleshooting
---------------

* If you see the following error when trying to upload an outcome 
  ``lti_consumer.lti_1p1.exceptions.Lti1p1Error: OAuthbody hash verification has failed``, your body hash was
  incorrectly computed. Make sure that ``basic_outcomes_body`` matches the body you are including as data in your "POST"
  request. A breakpoint in the Basic Outcomes Service request code can be helpful to see the value of the request body
  as compared to the ``oauth_body_hash`` provided in the Authorization header.
* If you’re switching between anonymous user IDs and external user IDs (i.e. toggling the 
  ``lti_consumer.enable_external_user_id_1p1_launches`` ``CourseWaffleFlag``, you’ll need to update your XML in Postman
  with the correct ``sourcedId`` and recompute and reset the Authorization header in your preferred API development and
  testing tool using the instructions above.