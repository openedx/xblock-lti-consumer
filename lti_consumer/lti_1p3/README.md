# LTI 1.3 Consumer Class

This implements a LTI 1.3 compliant consumer class which is request agnostic and can
be reused in different contexts (XBlock, Django plugin, and even on other frameworks).

This doesn't implement any data storage, just the methods required for handling LTI messages
and Access Tokens.

Features:
- LTI 1.3 Launch with full OIDC flow
- Support for custom parameters claim
- Support for launch presentation claim
- Access token creation

This implementation was based on the following IMS Global Documents:
- LTI 1.3 Core Specification: http://www.imsglobal.org/spec/lti/v1p3/
- IMS Global Security Framework: https://www.imsglobal.org/spec/security/v1p0/


## Using this class

To perform LTI launches, you'll need to store and manage a few resources and endpoints.

### Data storage

LTI variables from tool:
* **lti_oidc_url**: The tool's OIDC login initiation URL, needs to be stored and passed to the consumer every time it's instanced.
* **lti_launch_url**: The tool's LTI launch URL, where the platform submit's the actual LTI launch request with the signed LTI message.
* **tool_key**: The tool's public key, in raw PEM format. This will be used to verify message signatures from the tool to the platform. This is not required if this module is just used to launch LTI tools (without LTI advantage support).

LTI configuration from platform:
* **client_id**: Tool specific client ID, to separate multiple tool configurations (can be the same as the `rsa_key_id`).
* **deployment_id**: Deployment specific key ID ([spec reference](http://www.imsglobal.org/spec/lti/v1p3/#tool-deployment)). Used if deploying multi-tenant instances of LTI consumer, otherwise just a fixed string known be the tool.
* **rsa_key**: a raw PEM export of a RSA key. The minimum required is a SHA-256 (RS256) key (and also recommended to maximize interoperability).
* **rsa_key_id**: the key id for the RSA key above. Should be unique for every key used for LTI platform wide to avoid signature validation issues.

### Endpoints

To run LTI launches, 2 endpoints are required:
* **Launch Callback URL:** URL in the platform that the Tool will redirect to with response variables from preflight request made to OIDC endpoints.
* **Keyset URL:** URL that the tool will use to fetch the public key of the platform (a [JWK as defined in RFC7517](https://tools.ietf.org/html/rfc7517)). This URL should be publicly accessible and return the contents of the `get_public_keyset` function as a JSON.

### Example implementation

Here's a example LTI Launch using Django in the edX platform.

```python
def _get_lti1p3_consumer():
	"""
    Returns an configured instance of LTI consumer.
    """
    return LtiConsumer1p3(
      # Tool urls
      lti_oidc_url=lti_1p3_oidc_url,
      lti_launch_url=lti_1p3_launch_url,
      # Platform and deployment configuration
      iss=get_lms_base(),
      client_id=lti_1p3_client_id,
      deployment_id="1",
      # Platform key
      rsa_key=lti_1p3_block_key,
      rsa_key_id=lti_1p3_client_id,
      # Tool key
      tool_key=lti_1p3_tool_public_key,
    )


def public_keyset(request):
    """
    Return LTI Public Keyset url.

    This endpoint must be configured in the tool.
    """
    return JsonResponse(
      _get_lti1p3_consumer().get_public_keyset(),
      content_type='application/json'
    )

def lti_preflight_request(request):
    """
    Endpoint that'll render the initial OIDC authorization request form
    and submit it to the tool.

    The platform needs to know the tool OIDC endpoint.
    """
    lti_consumer = _get_lti1p3_consumer()
    context = lti_consumer.prepare_preflight_url()

    # This template should render a simple redirection to the URL
    # provided by the context through the `oidc_url` key above.
    # This can also be a redirect.
    return render(request, 'templates/lti_1p3_oidc.html', context)

def lti_launch_endpoint(request):
    """
    Platform endpoint that'll receive OIDC login request variables and generate launch request.
    """
    lti_consumer = _get_lti1p3_consumer()
    context = {}

    # Required user claim data
    lti_consumer.set_user_data(
      user_id=request.user.id,
      # Pass django user role to library
      role='student'
    )

    context.update({
      "preflight_response": request.GET.dict(),
      "launch_request": lti_consumer.generate_launch_request(
        resource_link=self.resource_link_id,
        preflight_response=request.GET
      )
    })

    context.update({'launch_url': self.lti_1p3_launch_url})
    # This template should render a form, and then submit it to the tool's launch URL, as
    # described in http://www.imsglobal.org/spec/lti/v1p3/#lti-message-general-details
    return render(request, 'templates/lti_launch_request_form.html', context)
```
