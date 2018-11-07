"""
XBlock implementation of the LTI (Learning Tools Interoperability) consumer specification.

Resources
---------

Background and detailed LTI specification can be found at:

    http://www.imsglobal.org/specs/ltiv1p1p1/implementation-guide

This module is based on the version 1.1.1 of the LTI specification by the
IMS Global authority. For authentication, it uses OAuth1.

When responding back to the LTI tool provider, we must issue a correct
response. Types of responses and their message payload is available at:

    Table A1.2 Interpretation of the 'CodeMajor/severity' matrix.
    http://www.imsglobal.org/gws/gwsv1p0/imsgws_wsdlBindv1p0.html

A resource to test the LTI protocol (PHP realization):

    http://www.imsglobal.org/developers/LTI/test/v1p1/lms.php

We have also begun to add support for LTI 1.2/2.0.  We will keep this
docstring in synch with what support is available.  The first LTI 2.0
feature to be supported is the REST API results service, see specification
at
http://www.imsglobal.org/lti/ltiv2p0/uml/purl.imsglobal.org/vocab/lis/v2/outcomes/Result/service.html

What is supported:
------------------

1.) Display of simple LTI in iframe or a new window.
2.) Multiple LTI components on a single page.
3.) The use of multiple LTI providers per course.
4.) Use of advanced LTI component that provides back a grade.
    A) LTI 1.1.1 XML endpoint
        a.) The LTI provider sends back a grade to a specified URL.
        b.) Currently only action "update" is supported. "Read", and "delete"
            actions initially weren't required.
    B) LTI 2.0 Result Service JSON REST endpoint
       (http://www.imsglobal.org/lti/ltiv2p0/uml/purl.imsglobal.org/vocab/lis/v2/outcomes/Result/service.html)
        a.) Discovery of all such LTI http endpoints for a course.  External tools GET from this discovery
            endpoint and receive URLs for interacting with individual grading units.
            (see lms/djangoapps/courseware/views.py:get_course_lti_endpoints)
        b.) GET, PUT and DELETE in LTI Result JSON binding
            (http://www.imsglobal.org/lti/ltiv2p0/mediatype/application/vnd/ims/lis/v2/result+json/index.html)
            for a provider to synchronize grades into edx-platform.  Reading, Setting, and Deleteing
            Numeric grades between 0 and 1 and text + basic HTML feedback comments are supported, via
            GET / PUT / DELETE HTTP methods respectively
"""

import logging
import bleach
import re
import json
import urllib

from collections import namedtuple
from webob import Response

from django.utils import timezone

from xblock.core import String, Scope, List, XBlock
from xblock.fields import Boolean, Float, Integer
from xblock.fragment import Fragment
from xblock.validation import ValidationMessage

from xblockutils.resources import ResourceLoader
from xblockutils.studio_editable import StudioEditableXBlockMixin

from .exceptions import LtiError
from .oauth import log_authorization_header
from .lti import LtiConsumer
from .outcomes import OutcomeService
from .utils import _

log = logging.getLogger(__name__)

DOCS_ANCHOR_TAG_OPEN = (
    "<a "
    "target='_blank' "
    "href='"
    "http://edx.readthedocs.org"
    "/projects/open-edx-building-and-running-a-course/en/latest/exercises_tools/lti_component.html"
    "'>"
)
RESULT_SERVICE_SUFFIX_PARSER = re.compile(r"^user/(?P<anon_id>\w+)", re.UNICODE)
ROLE_MAP = {
    'student': u'Student',
    'staff': u'Administrator',
    'instructor': u'Instructor',
}
LTI_PARAMETERS = [
    'lti_message_type',
    'lti_version',
    'resource_link_title',
    'resource_link_description',
    'user_image',
    'lis_person_name_given',
    'lis_person_name_family',
    'lis_person_name_full',
    'lis_person_contact_email_primary',
    'lis_person_sourcedid',
    'role_scope_mentor',
    'context_type',
    'context_title',
    'context_label',
    'launch_presentation_locale',
    'launch_presentation_document_target',
    'launch_presentation_css_url',
    'launch_presentation_width',
    'launch_presentation_height',
    'launch_presentation_return_url',
    'tool_consumer_info_product_family_code',
    'tool_consumer_info_version',
    'tool_consumer_instance_guid',
    'tool_consumer_instance_name',
    'tool_consumer_instance_description',
    'tool_consumer_instance_url',
    'tool_consumer_instance_contact_email',
    'custom_component_due_date',
    'custom_component_graceperiod',
    'custom_cohort',
    'custom_team',
    'custom_component_display_name'
]


def parse_handler_suffix(suffix):
    """
    Parser function for HTTP request path suffixes

    parses the suffix argument (the trailing parts of the URL) of the LTI2.0 REST handler.
    must be of the form "user/<anon_id>".  Returns anon_id if match found, otherwise raises LtiError

    Arguments:
        suffix (unicode):  suffix to parse

    Returns:
        unicode: anon_id if match found

    Raises:
        LtiError if suffix cannot be parsed or is not in its expected form
    """
    if suffix:
        match_obj = RESULT_SERVICE_SUFFIX_PARSER.match(suffix)
        if match_obj:
            return match_obj.group('anon_id')
    # fall-through handles all error cases
    msg = _("No valid user id found in endpoint URL")
    log.info("[LTI]: %s", msg)
    raise LtiError(msg)


LaunchTargetOption = namedtuple('LaunchTargetOption', ['display_name', 'value'])


class LaunchTarget(object):
    """
    Constants for launch_target field options
    """
    IFRAME = LaunchTargetOption('Inline', 'iframe')
    MODAL = LaunchTargetOption('Modal', 'modal')
    NEW_WINDOW = LaunchTargetOption('New Window', 'new_window')


@XBlock.needs('i18n')
@XBlock.wants('lti-configuration')
class LtiConsumerXBlock(StudioEditableXBlockMixin, XBlock):
    """
    This XBlock provides an LTI consumer interface for integrating
    third-party tools using the LTI specification.

    Except usual Xmodule structure it proceeds with OAuth signing.
    How it works::

    1. Get credentials from course settings.

    2.  There is minimal set of parameters need to be signed (presented for Vitalsource)::

            user_id
            oauth_callback
            lis_outcome_service_url
            lis_result_sourcedid
            launch_presentation_return_url
            lti_message_type
            lti_version
            roles
            *+ all custom parameters*

        These parameters should be encoded and signed by *OAuth1* together with
        `launch_url` and *POST* request type.

    3. Signing proceeds with client key/secret pair obtained from course settings.
        That pair should be obtained from LTI provider and set into course settings by course author.
        After that signature and other OAuth data are generated.

        OAuth data which is generated after signing is usual::

            oauth_callback
            oauth_nonce
            oauth_consumer_key
            oauth_signature_method
            oauth_timestamp
            oauth_version


    4. All that data is passed to form and sent to LTI provider server by browser via
        autosubmit via JavaScript.

        Form example::

            <form
                action="${launch_url}"
                name="ltiLaunchForm-${element_id}"
                class="ltiLaunchForm"
                method="post"
                target="ltiLaunchFrame-${element_id}"
                encType="application/x-www-form-urlencoded"
            >
                <input name="launch_presentation_return_url" value="" />
                <input name="lis_outcome_service_url" value="" />
                <input name="lis_result_sourcedid" value="" />
                <input name="lti_message_type" value="basic-lti-launch-request" />
                <input name="lti_version" value="LTI-1p0" />
                <input name="oauth_callback" value="about:blank" />
                <input name="oauth_consumer_key" value="${oauth_consumer_key}" />
                <input name="oauth_nonce" value="${oauth_nonce}" />
                <input name="oauth_signature_method" value="HMAC-SHA1" />
                <input name="oauth_timestamp" value="${oauth_timestamp}" />
                <input name="oauth_version" value="1.0" />
                <input name="user_id" value="${user_id}" />
                <input name="role" value="student" />
                <input name="oauth_signature" value="${oauth_signature}" />

                <input name="custom_1" value="${custom_param_1_value}" />
                <input name="custom_2" value="${custom_param_2_value}" />
                <input name="custom_..." value="${custom_param_..._value}" />

                <input type="submit" value="Press to Launch" />
            </form>

    5. LTI provider has same secret key and it signs data string via *OAuth1* and compares signatures.

        If signatures are correct, LTI provider redirects iframe source to LTI tool web page,
        and LTI tool is rendered to iframe inside course.

        Otherwise error message from LTI provider is generated.
    """

    display_name = String(
        display_name=_("Display Name"),
        help=_(
            "Enter the name that students see for this component. "
            "Analytics reports may also use the display name to identify this component."
        ),
        scope=Scope.settings,
        default=_("LTI Consumer"),
    )
    description = String(
        display_name=_("LTI Application Information"),
        help=_(
            "Enter a description of the third party application. "
            "If requesting username and/or email, use this text box to inform users "
            "why their username and/or email will be forwarded to a third party application."
        ),
        default="",
        scope=Scope.settings
    )
    lti_id = String(
        display_name=_("LTI ID"),
        help=_(
            "Enter the LTI ID for the external LTI provider. "
            "This value must be the same LTI ID that you entered in the "
            "LTI Passports setting on the Advanced Settings page."
            "<br />See the {docs_anchor_open}edX LTI documentation{anchor_close} for more details on this setting."
        ).format(
            docs_anchor_open=DOCS_ANCHOR_TAG_OPEN,
            anchor_close="</a>"
        ),
        default='',
        scope=Scope.settings
    )
    launch_url = String(
        display_name=_("LTI URL"),
        help=_(
            "Enter the URL of the external tool that this component launches. "
            "This setting is only used when Hide External Tool is set to False."
            "<br />See the {docs_anchor_open}edX LTI documentation{anchor_close} for more details on this setting."
        ).format(
            docs_anchor_open=DOCS_ANCHOR_TAG_OPEN,
            anchor_close="</a>"
        ),
        default='',
        scope=Scope.settings
    )
    custom_parameters = List(
        display_name=_("Custom Parameters"),
        help=_(
            "Add the key/value pair for any custom parameters, such as the page your e-book should open to or "
            "the background color for this component. Ex. [\"page=1\", \"color=white\"]"
            "<br />See the {docs_anchor_open}edX LTI documentation{anchor_close} for more details on this setting."
        ).format(
            docs_anchor_open=DOCS_ANCHOR_TAG_OPEN,
            anchor_close="</a>"
        ),
        scope=Scope.settings
    )
    launch_target = String(
        display_name=_("LTI Launch Target"),
        help=_(
            "Select Inline if you want the LTI content to open in an IFrame in the current page. "
            "Select Modal if you want the LTI content to open in a modal window in the current page. "
            "Select New Window if you want the LTI content to open in a new browser window. "
            "This setting is only used when Hide External Tool is set to False."
        ),
        default=LaunchTarget.IFRAME.value,
        scope=Scope.settings,
        values=[
            {"display_name": LaunchTarget.IFRAME.display_name, "value": LaunchTarget.IFRAME.value},
            {"display_name": LaunchTarget.MODAL.display_name, "value": LaunchTarget.MODAL.value},
            {"display_name": LaunchTarget.NEW_WINDOW.display_name, "value": LaunchTarget.NEW_WINDOW.value},
        ],
    )
    button_text = String(
        display_name=_("Button Text"),
        help=_(
            "Enter the text on the button used to launch the third party application. "
            "This setting is only used when Hide External Tool is set to False and "
            "LTI Launch Target is set to Modal or New Window."
        ),
        default="",
        scope=Scope.settings
    )
    inline_height = Integer(
        display_name=_("Inline Height"),
        help=_(
            "Enter the desired pixel height of the iframe which will contain the LTI tool. "
            "This setting is only used when Hide External Tool is set to False and "
            "LTI Launch Target is set to Inline."
        ),
        default=800,
        scope=Scope.settings
    )
    modal_height = Integer(
        display_name=_("Modal Height"),
        help=_(
            "Enter the desired viewport percentage height of the modal overlay which will contain the LTI tool. "
            "This setting is only used when Hide External Tool is set to False and "
            "LTI Launch Target is set to Modal."
        ),
        default=80,
        scope=Scope.settings
    )
    modal_width = Integer(
        display_name=_("Modal Width"),
        help=_(
            "Enter the desired viewport percentage width of the modal overlay which will contain the LTI tool. "
            "This setting is only used when Hide External Tool is set to False and "
            "LTI Launch Target is set to Modal."
        ),
        default=80,
        scope=Scope.settings
    )
    has_score = Boolean(
        display_name=_("Scored"),
        help=_("Select True if this component will receive a numerical score from the external LTI system."),
        default=False,
        scope=Scope.settings
    )
    weight = Float(
        display_name="Weight",
        help=_(
            "Enter the number of points possible for this component.  "
            "The default value is 1.0.  "
            "This setting is only used when Scored is set to True."
        ),
        default=1.0,
        scope=Scope.settings,
        values={"min": 0},
    )
    module_score = Float(
        help=_("The score kept in the xblock KVS -- duplicate of the published score in django DB"),
        default=None,
        scope=Scope.user_state
    )
    score_comment = String(
        help=_("Comment as returned from grader, LTI2.0 spec"),
        default="",
        scope=Scope.user_state
    )
    hide_launch = Boolean(
        display_name=_("Hide External Tool"),
        help=_(
            "Select True if you want to use this component as a placeholder for syncing with an external grading  "
            "system rather than launch an external tool.  "
            "This setting hides the Launch button and any IFrames for this component."
        ),
        default=False,
        scope=Scope.settings
    )
    accept_grades_past_due = Boolean(
        display_name=_("Accept grades past deadline"),
        help=_("Select True to allow third party systems to post grades past the deadline."),
        default=True,
        scope=Scope.settings
    )
    # Users will be presented with a message indicating that their e-mail/username would be sent to a third
    # party application. When "Open in New Page" is not selected, the tool automatically appears without any
    # user action.
    ask_to_send_username = Boolean(
        display_name=_("Request user's username"),
        # Translators: This is used to request the user's username for a third party service.
        help=_("Select True to request the user's username."),
        default=False,
        scope=Scope.settings
    )
    ask_to_send_email = Boolean(
        display_name=_("Request user's email"),
        # Translators: This is used to request the user's email for a third party service.
        help=_("Select True to request the user's email address."),
        default=False,
        scope=Scope.settings
    )

    # Possible editable fields
    editable_field_names = (
        'display_name', 'description', 'lti_id', 'launch_url', 'custom_parameters',
        'launch_target', 'button_text', 'inline_height', 'modal_height', 'modal_width',
        'has_score', 'weight', 'hide_launch', 'accept_grades_past_due', 'ask_to_send_username',
        'ask_to_send_email'
    )

    def validate_field_data(self, validation, data):
        if not isinstance(data.custom_parameters, list):
            _ = self.runtime.service(self, "i18n").ugettext
            validation.add(ValidationMessage(ValidationMessage.ERROR, unicode(_("Custom Parameters must be a list"))))

    @property
    def editable_fields(self):
        """
        Returns editable fields which may/may not contain 'ask_to_send_username' and
        'ask_to_send_email' fields depending on the configuration service.
        """
        editable_fields = self.editable_field_names
        # update the editable fields if this XBlock is configured to not to allow the
        # editing of 'ask_to_send_username' and 'ask_to_send_email'.
        config_service = self.runtime.service(self, 'lti-configuration')
        if config_service:
            is_already_sharing_learner_info = self.ask_to_send_email or self.ask_to_send_username
            if not config_service.configuration.lti_access_to_learners_editable(
                    self.course_id,
                    is_already_sharing_learner_info,
            ):
                editable_fields = tuple(
                    field
                    for field in self.editable_field_names
                    if field not in ('ask_to_send_username', 'ask_to_send_email')
                )

        return editable_fields

    @property
    def descriptor(self):
        """
        Returns this XBlock object.

        This is for backwards compatibility with the XModule API.
        Some LMS code still assumes a descriptor attribute on the XBlock object.
        See courseware.module_render.rebind_noauth_module_to_user.
        """
        return self

    @property
    def context_id(self):
        """
        Return context_id.

        context_id is an opaque identifier that uniquely identifies the context (e.g., a course)
        that contains the link being launched.
        """
        return unicode(self.course_id)  # pylint: disable=no-member

    @property
    def role(self):
        """
        Get system user role and convert it to LTI role.
        """
        return ROLE_MAP.get(self.runtime.get_user_role(), u'Student')

    @property
    def course(self):
        """
        Return course by course id.
        """
        return self.runtime.descriptor_runtime.modulestore.get_course(self.course_id)  # pylint: disable=no-member

    @property
    def lti_provider_key_secret(self):
        """
        Obtains client_key and client_secret credentials from current course.
        """
        for lti_passport in self.course.lti_passports:
            try:
                lti_id, key, secret = [i.strip() for i in lti_passport.split(':')]
            except ValueError:
                msg = self.ugettext('Could not parse LTI passport: {lti_passport}. Should be "id:key:secret" string.').\
                    format(lti_passport='{0!r}'.format(lti_passport))
                raise LtiError(msg)

            if lti_id == self.lti_id.strip():
                return key, secret

        return '', ''

    @property
    def user_id(self):
        """
        Returns the opaque anonymous_student_id for the current user.
        """
        user_id = self.runtime.anonymous_student_id
        if user_id is None:
            raise LtiError(self.ugettext("Could not get user id for current request"))
        return unicode(urllib.quote(user_id))

    @property
    def resource_link_id(self):
        """
        This is an opaque unique identifier that the LTI Tool Consumer guarantees will be unique
        within the Tool Consumer for every placement of the link.

        If the tool / activity is placed multiple times in the same context,
        each of those placements will be distinct.

        This value will also change if the item is exported from one system or
        context and imported into another system or context.

        resource_link_id is a required LTI launch parameter.

        Example:  u'edx.org-i4x-2-3-lti-31de800015cf4afb973356dbe81496df'

        Hostname, edx.org,
        makes resource_link_id change on import to another system.

        Last part of location, location.name - 31de800015cf4afb973356dbe81496df,
        is random hash, updated by course_id,
        this makes resource_link_id unique inside single course.

        First part of location is tag-org-course-category, i4x-2-3-lti.

        Location.name itself does not change on import to another course,
        but org and course_id change.

        So together with org and course_id in a form of
        i4x-2-3-lti-31de800015cf4afb973356dbe81496df this part of resource_link_id:
        makes resource_link_id to be unique among courses inside same system.
        """
        return unicode(urllib.quote(
            "{}-{}".format(self.runtime.hostname, self.location.html_id())  # pylint: disable=no-member
        ))

    @property
    def lis_result_sourcedid(self):
        """
        This field contains an identifier that indicates the LIS Result Identifier (if any)
        associated with this launch.  This field identifies a unique row and column within the
        TC gradebook.  This field is unique for every combination of context_id / resource_link_id / user_id.
        This value may change for a particular resource_link_id / user_id  from one launch to the next.
        The TP should only retain the most recent value for this field for a particular resource_link_id / user_id.
        This field is generally optional, but is required for grading.
        """
        return "{context}:{resource_link}:{user_id}".format(
            context=urllib.quote(self.context_id),
            resource_link=self.resource_link_id,
            user_id=self.user_id
        )

    @property
    def outcome_service_url(self):
        """
        Return URL for storing grades.

        To test LTI on sandbox we must use http scheme.

        While testing locally and on Jenkins, mock_lti_server use http.referer
        to obtain scheme, so it is ok to have http(s) anyway.

        The scheme logic is handled in lms/lib/xblock/runtime.py
        """
        return self.runtime.handler_url(self, "outcome_service_handler", thirdparty=True).rstrip('/?')

    @property
    def result_service_url(self):
        """
        Return URL for results.

        To test LTI on sandbox we must use http scheme.

        While testing locally and on Jenkins, mock_lti_server use http.referer
        to obtain scheme, so it is ok to have http(s) anyway.

        The scheme logic is handled in lms/lib/xblock/runtime.py
        """
        return self.runtime.handler_url(self, "result_service_handler", thirdparty=True).rstrip('/?')

    @property
    def prefixed_custom_parameters(self):
        """
        Apply prefix to configured custom LTI parameters

        LTI provides a list of default parameters that might be passed as
        part of the POST data. These parameters should not be prefixed.
        Likewise, The creator of an LTI link can add custom key/value parameters
        to a launch which are to be included with the launch of the LTI link.
        In this case, we will automatically add `custom_` prefix before this parameters.
        See http://www.imsglobal.org/LTI/v1p1p1/ltiIMGv1p1p1.html#_Toc316828520
        """

        # parsing custom parameters to dict
        custom_parameters = {}
        if isinstance(self.custom_parameters, list):
            for custom_parameter in self.custom_parameters:
                try:
                    param_name, param_value = [p.strip() for p in custom_parameter.split('=', 1)]
                except ValueError:
                    _ = self.runtime.service(self, "i18n").ugettext
                    # pylint: disable=line-too-long
                    msg = self.ugettext('Could not parse custom parameter: {custom_parameter}. Should be "x=y" string.').\
                        format(custom_parameter="{0!r}".format(custom_parameter))
                    raise LtiError(msg)

                # LTI specs: 'custom_' should be prepended before each custom parameter, as pointed in link above.
                if param_name not in LTI_PARAMETERS:
                    param_name = 'custom_' + param_name

                custom_parameters[unicode(param_name)] = unicode(param_value)
        return custom_parameters

    @property
    def is_past_due(self):
        """
        Is it now past this problem's due date, including grace period?
        """
        due_date = self.due  # pylint: disable=no-member
        if self.graceperiod is not None and due_date:  # pylint: disable=no-member
            close_date = due_date + self.graceperiod  # pylint: disable=no-member
        else:
            close_date = due_date
        return close_date is not None and timezone.now() > close_date

    def student_view(self, context):
        """
        XBlock student view of this component.

        Makes a request to `lti_launch_handler` either
        in an iframe or in a new window depending on the
        configuration of the instance of this XBlock

        Arguments:
            context (dict): XBlock context

        Returns:
            xblock.fragment.Fragment: XBlock HTML fragment
        """
        fragment = Fragment()
        loader = ResourceLoader(__name__)
        context.update(self._get_context_for_template())
        fragment.add_content(loader.render_mako_template('/templates/html/student.html', context))
        fragment.add_css(loader.load_unicode('static/css/student.css'))
        fragment.add_javascript(loader.load_unicode('static/js/xblock_lti_consumer.js'))
        fragment.initialize_js('LtiConsumerXBlock')
        return fragment

    @XBlock.handler
    def lti_launch_handler(self, request, suffix=''):  # pylint: disable=unused-argument
        """
        XBlock handler for launching the LTI provider.

        Displays a form which is submitted via Javascript
        to send the LTI launch POST request to the LTI
        provider.

        Arguments:
            request (xblock.django.request.DjangoWebobRequest): Request object for current HTTP request
            suffix (unicode): Request path after "lti_launch_handler/"

        Returns:
            webob.response: HTML LTI launch form
        """
        lti_consumer = LtiConsumer(self)
        lti_parameters = lti_consumer.get_signed_lti_parameters()
        loader = ResourceLoader(__name__)
        context = self._get_context_for_template()
        context.update({'lti_parameters': lti_parameters})
        template = loader.render_mako_template('/templates/html/lti_launch.html', context)
        return Response(template, content_type='text/html')

    @XBlock.handler
    def outcome_service_handler(self, request, suffix=''):  # pylint: disable=unused-argument
        """
        XBlock handler for LTI Outcome Service requests.

        Instantiates an `OutcomeService` instance to handle
        requests made by LTI providers to update a user's grade
        for this component.

        For details about the LTI Outcome Service see:
        https://www.imsglobal.org/specs/ltiomv1p0

        Arguments:
            request (xblock.django.request.DjangoWebobRequest): Request object for current HTTP request
            suffix (unicode): Request path after "outcome_service_handler/"

        Returns:
            webob.response: XML Outcome Service response
        """
        outcome_service = OutcomeService(self)
        return Response(outcome_service.handle_request(request), content_type="application/xml")

    @XBlock.handler
    def result_service_handler(self, request, suffix=''):
        """
        Handler function for LTI 2.0 JSON/REST result service.

        See http://www.imsglobal.org/lti/ltiv2p0/uml/purl.imsglobal.org/vocab/lis/v2/outcomes/Result/service.html
        An example JSON object:
        {
         "@context" : "http://purl.imsglobal.org/ctx/lis/v2/Result",
         "@type" : "Result",
         "resultScore" : 0.83,
         "comment" : "This is exceptional work."
        }
        For PUTs, the content type must be "application/vnd.ims.lis.v2.result+json".
        We use the "suffix" parameter to parse out the user from the end of the URL.  An example endpoint url is
        http://localhost:8000/courses/org/num/run/xblock/i4x:;_;_org;_num;_lti;_GUID/handler_noauth/lti_2_0_result_rest_handler/user/<anon_id>
        so suffix is of the form "user/<anon_id>"
        Failures result in 401, 404, or 500s without any body.  Successes result in 200.  Again see
        http://www.imsglobal.org/lti/ltiv2p0/uml/purl.imsglobal.org/vocab/lis/v2/outcomes/Result/service.html
        (Note: this prevents good debug messages for the client, so we might want to change this, or the spec)

        Arguments:
            request (xblock.django.request.DjangoWebobRequest):  Request object for current HTTP request
            suffix (unicode):  request path after "lti_2_0_result_rest_handler/".  expected to be "user/<anon_id>"

        Returns:
            webob.response:  response to this request.  See above for details.
        """
        lti_consumer = LtiConsumer(self)

        if self.runtime.debug:
            lti_provider_key, lti_provider_secret = self.lti_provider_key_secret
            log_authorization_header(request, lti_provider_key, lti_provider_secret)

        if not self.accept_grades_past_due and self.is_past_due:
            return Response(status=404)  # have to do 404 due to spec, but 400 is better, with error msg in body

        try:
            anon_id = parse_handler_suffix(suffix)
        except LtiError:
            return Response(status=404)  # 404 because a part of the URL (denoting the anon user id) is invalid
        try:
            lti_consumer.verify_result_headers(request, verify_content_type=True)
        except LtiError:
            return Response(status=401)  # Unauthorized in this case.  401 is right

        user = self.runtime.get_real_user(anon_id)
        if not user:  # that means we can't save to database, as we do not have real user id.
            msg = _("[LTI]: Real user not found against anon_id: {}").format(anon_id)
            log.info(msg)
            return Response(status=404)  # have to do 404 due to spec, but 400 is better, with error msg in body

        try:
            # Call the appropriate LtiConsumer method
            args = []
            if request.method == 'PUT':
                # Request body should be passed as an argument
                # to result handler method on PUT
                args.append(request.body)
            response_body = getattr(lti_consumer, "{}_result".format(request.method.lower()))(user, *args)
        except (AttributeError, LtiError):
            return Response(status=404)

        return Response(
            json.dumps(response_body),
            content_type=LtiConsumer.CONTENT_TYPE_RESULT_JSON,
        )

    def max_score(self):
        """
        Returns the configured number of possible points for this component.

        Arguments:
            None

        Returns:
            float: The number of possible points for this component
        """
        return self.weight if self.has_score else None

    def clear_user_module_score(self, user):
        """
        Clears the module user state, including grades and comments, and also scoring in db's courseware_studentmodule

        Arguments:
            user (django.contrib.auth.models.User):  Actual user whose module state is to be cleared

        Returns:
            nothing
        """
        self.set_user_module_score(user, None, None)

    def set_user_module_score(self, user, score, max_score, comment=u''):
        """
        Sets the module user state, including grades and comments, and also scoring in db's courseware_studentmodule

        Arguments:
            user (django.contrib.auth.models.User):  Actual user whose module state is to be set
            score (float):  user's numeric score to set.  Must be in the range [0.0, 1.0]
            max_score (float):  max score that could have been achieved on this module
            comment (unicode):  comments provided by the grader as feedback to the student

        Returns:
            nothing
        """
        if score is not None and max_score is not None:
            scaled_score = score * max_score
        else:
            scaled_score = None

        self.runtime.rebind_noauth_module_to_user(self, user)

        # have to publish for the progress page...
        self.runtime.publish(
            self,
            'grade',
            {
                'value': scaled_score,
                'max_value': max_score,
                'user_id': user.id,
            },
        )
        self.module_score = scaled_score
        self.score_comment = comment

    def _get_context_for_template(self):
        """
        Returns the context dict for LTI templates.

        Arguments:
            None

        Returns:
            dict: Context variables for templates
        """

        # use bleach defaults. see https://github.com/jsocol/bleach/blob/master/bleach/__init__.py
        # ALLOWED_TAGS are
        # ['a', 'abbr', 'acronym', 'b', 'blockquote', 'code', 'em', 'i', 'li', 'ol',  'strong', 'ul']
        #
        # ALLOWED_ATTRIBUTES are
        #     'a': ['href', 'title'],
        #     'abbr': ['title'],
        #     'acronym': ['title'],
        #
        # This lets all plaintext through.
        sanitized_comment = bleach.clean(self.score_comment)

        return {
            'launch_url': self.launch_url.strip(),
            'element_id': self.location.html_id(),  # pylint: disable=no-member
            'element_class': self.category,  # pylint: disable=no-member
            'launch_target': self.launch_target,
            'display_name': self.display_name,
            'form_url': self.runtime.handler_url(self, 'lti_launch_handler').rstrip('/?'),
            'hide_launch': self.hide_launch,
            'has_score': self.has_score,
            'weight': self.weight,
            'module_score': self.module_score,
            'comment': sanitized_comment,
            'description': self.description,
            'ask_to_send_username': self.ask_to_send_username,
            'ask_to_send_email': self.ask_to_send_email,
            'button_text': self.button_text,
            'inline_height': self.inline_height,
            'modal_vertical_offset': self._get_modal_position_offset(self.modal_height),
            'modal_horizontal_offset': self._get_modal_position_offset(self.modal_width),
            'modal_width': self.modal_width,
            'accept_grades_past_due': self.accept_grades_past_due,
        }

    def _get_modal_position_offset(self, viewport_percentage):
        """
        Returns the css position offset to apply to the modal window
        element when launch_target is modal. This enables us to position
        the modal window as a percentage of the viewport dimensions.

        Arguments:
            viewport_percentage (int): The percentage of the viewport that the modal should occupy

        Returns:
            float: The css position offset to apply to the modal window
        """
        return (100 - viewport_percentage) / 2

    def get_outcome_service_url(self, service_name="grade_handler"):
        """
        This function is called by get_course_lti_endpoints when using LTI result service to
        discover the LTI result endpoints.
        """

        # using string as mapped value instead of attributes to avoid unnecessary calls as both urls
        # are @property.
        mapping = {
            'grade_handler': 'outcome_service_url',
            'lti_2_0_result_rest_handler': 'result_service_url'
        }
        return getattr(self, mapping[service_name])
