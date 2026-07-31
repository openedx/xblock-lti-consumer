LTI 1.1 Consumer Class
-

This is a work in progress implementation of a  LTI 1.1 compliant consumer class
which is request agnostic and can be reused in different contexts (XBlock,
Django plugin, and even on other frameworks).

This doesn't implement any data storage, just the methods required for handling
LTI messages.

Also provided is a helper method that can be used to generate an HTML fragment
which will automatically submit an LTI Launch request once rendered.

Features:
- LTI 1.1 Launch
- Support for custom parameters

This implementation was based on the following IMS Global Documents:
- LTI 1.1 Core Specification: https://www.imsglobal.org/specs/ltiv1p1/

### Using the `lti_embed` helper method

Below is a code snippet of a Django view that will render the HTML fragment
returned by the `lti_embed` helper method, automatically submit the launch
request, and redirect to the saLTIre tool.

```python
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

from lti_consumer.lti_1p1.contrib.django import lti_embed


@login_required
def basic_lti_embed(request):
    """
    Provides the LTI Embed outside of an xblock
    """

    return HttpResponse(lti_embed(
        html_element_id='direct-embed',
        lti_launch_url='http://lti.tools/saltire/tp',
        oauth_key='jisc.ac.uk',
        oauth_secret='secret',
        resource_link_id='unique-resource-link-id',
        user_id='student',
        roles='Student',
        context_id='some-page',
        context_title='Some page title',
        context_label='Some page label',
        result_sourcedid='unique-result-sourcedid',
        person_sourcedid=None,
        person_contact_email_primary=None,
        outcome_service_url=None,
        launch_presentation_locale=None
    ))
```

To render the LTI Launch within the same webpage as it is launched without
redirecting the user, simply enclose the template returned by `lti_embed` within
an `iframe`.

#### Important Note About `lti_embed`

This method uses keyword only arguments as described in
[PEP-3102](https://www.python.org/dev/peps/pep-3102/). As such, all arguments
passed to `lti_embed` must use specify the keyword associated to the value.
Given the large number of arguments for this method, there is a desire to
guarantee that developers using this method know which arguments are being set
to which values. This syntax is NOT backwards compatible with python 2.X, but is
compatible with python 3.5.X or higher.
