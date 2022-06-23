"""
This module provides functionality for rendering an LTI embed without an XBlock.
"""

# See comment in docstring for explanation of the usage of ResourceLoader
from xblockutils.resources import ResourceLoader

from lti_consumer.track import track_event

from ..consumer import LtiConsumer1p1


def lti_embed(
        *,
        html_element_id,
        resource_link_id,
        user_id,
        roles,
        context_id,
        context_title,
        context_label,
        result_sourcedid,
        lti_consumer=None,
        lti_launch_url=None,
        oauth_key=None,
        oauth_secret=None,
        person_sourcedid=None,
        person_contact_email_primary=None,
        outcome_service_url=None,
        launch_presentation_locale=None,
        **custom_parameters
):
    """
    Returns an HTML template with JavaScript that will launch an LTI embed

    IMPORTANT NOTE: This method uses keyword only arguments as described in PEP 3102.
    Given the large number of arguments for this method, there is a  desire to
    guarantee that developers using this method know which arguments are being set
    to which values.
    See https://www.python.org/dev/peps/pep-3102/

    This method will use the LtiConsumer1p1 class to generate an HTML form and
    JavaScript that will automatically launch the LTI embedding, but it does not
    generate any response to encapsulate this content. The caller of this method
    must render the HTML on their own.

    Note: This method uses xblockutils.resources.ResourceLoader to load the HTML
    template used. The rationale for this is that ResourceLoader is agnostic
    to XBlock code and functionality. It is recommended that this remain in use
    until LTI1.3 support is merged, or a better means of loading the template is
    made available.

    Arguments:
        html_element_id (string):  Value to use as the HTML element id in the HTML form
        resource_link_id (string):  Opaque identifier guaranteed to be unique
            for every placement of the link
        user_id (string):  Unique value identifying the user
        roles (string):  A comma separated list of role values
        context_id (string):  Opaque identifier used to uniquely identify the
            context that contains the link being launched
        context_title (string):  Plain text title of the context
        context_label (string):  Plain text label for the context
        result_sourcedid (string):  Indicates the LIS Result Identifier (if any)
            and uniquely identifies a row and column within the Tool Consumer gradebook
        lti_consumer (LtiConsumer1p1): A pre-configured LtiConsumer1p1 object
            as an alternative to providing the launch url, oauth key and oauth secret
        lti_launch_url (string):  The URL to send the LTI Launch request to
        oauth_key (string):  The OAuth consumer key
        oauth_secret (string):  The OAuth consumer secret
        person_sourcedid (string):  LIS identifier for the user account performing the launch
        person_contact_email_primary (string):  Primary contact email address of the user
        outcome_service_url (string):  URL pointing to the outcome service. This
            is required if the Tool Consumer is accepting outcomes for launches
            associated with the resource_link_id
        launch_presentation_locale (string):  Language, country and variant as
            represented using the IETF Best Practices for Tags for Identifying
            Languages (BCP-47)
        custom_parameters (dict): Contains any other keyword arguments not listed
            above. It will filter out all arguments provided that do not start with
            'custom_' and will submit the remaining arguments on the LTI Launch form

    Returns:
        unicode: HTML template with the form and JavaScript to automatically
            launch the LTI embedding
    """
    if lti_consumer is None:
        lti_consumer = LtiConsumer1p1(lti_launch_url, oauth_key, oauth_secret)
    else:
        lti_launch_url = lti_consumer.lti_launch_url

    # Set LTI parameters from kwargs
    lti_consumer.set_user_data(
        user_id,
        roles,
        result_sourcedid,
        person_sourcedid=person_sourcedid,
        person_contact_email_primary=person_contact_email_primary
    )
    lti_consumer.set_context_data(
        context_id,
        context_title,
        context_label
    )

    if outcome_service_url:
        lti_consumer.set_outcome_service_url(outcome_service_url)

    if launch_presentation_locale:
        lti_consumer.set_launch_presentation_locale(launch_presentation_locale)

    lti_consumer.set_custom_parameters(
        {
            key: value
            for key, value in custom_parameters.items()
            if key.startswith('custom_')
        }
    )

    lti_parameters = lti_consumer.generate_launch_request(resource_link_id)

    # Prepare form data
    context = {
        'launch_url': lti_launch_url,
        'element_id': html_element_id
    }
    context.update({'lti_parameters': lti_parameters})

    # emit tracking event
    event = {
        'lti_version': lti_parameters.get('lti_version'),
        'user_roles': lti_parameters.get('roles'),
        'launch_url': lti_consumer.lti_launch_url,
    }
    track_event('embed.launch_request', event)

    # Render the form template and return the template
    loader = ResourceLoader(__name__)
    template = loader.render_django_template('../../templates/html/lti_launch.html', context)
    return template
