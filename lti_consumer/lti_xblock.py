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
import re
import urllib.parse
from collections import namedtuple
from importlib import import_module
import pkg_resources

import bleach
from django.conf import settings
from django.utils import timezone, translation
from web_fragments.fragment import Fragment

from webob import Response
from xblock.core import List, Scope, String, XBlock
from xblock.fields import Boolean, Float, Integer
from xblock.validation import ValidationMessage
from xblockutils.resources import ResourceLoader
from xblockutils.studio_editable import StudioEditableXBlockMixin

from .data import Lti1p3LaunchData
from .exceptions import LtiError
from .lti_1p1.consumer import LtiConsumer1p1, parse_result_json, LTI_PARAMETERS
from .lti_1p1.oauth import log_authorization_header
from .outcomes import OutcomeService
from .plugin import compat
from .track import track_event
from .utils import (
    _,
    resolve_custom_parameter_template,
    external_config_filter_enabled,
    external_user_id_1p1_launches_enabled,
    database_config_enabled,
)

log = logging.getLogger(__name__)

DOCS_ANCHOR_TAG_OPEN = (
    "<a "
    "target='_blank' "
    "href='"
    "http://edx.readthedocs.org"
    "/projects/open-edx-building-and-running-a-course/en/latest/exercises_tools/lti_component.html"
    "'>"
)
RESULT_SERVICE_SUFFIX_PARSER = re.compile(r"^user/(?P<anon_id>[\w-]+)", re.UNICODE)
LTI_1P1_ROLE_MAP = {
    'student': 'Student,Learner',
    'staff': 'Administrator',
    'instructor': 'Instructor',
}
CUSTOM_PARAMETER_TEMPLATE_TAGS = ('${', '}')


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


def valid_config_type_values(block):
    """
    Return a list of valid values for the config_type XBlock field.

    Always return "new" as a config_type value. Determine whether the "database" and "external" config_type values are
    valid value options, depending on the state of the appropriate toggle.
    """
    values = [
        {"display_name": _("Configuration on block"), "value": "new"}
    ]

    if database_config_enabled(block.scope_ids.usage_id.context_key):
        values.append({"display_name": _("Database Configuration"), "value": "database"})

    if external_config_filter_enabled(block.scope_ids.usage_id.context_key):
        values.append({"display_name": _("Reusable Configuration"), "value": "external"})

    return values


LaunchTargetOption = namedtuple('LaunchTargetOption', ['display_name', 'value'])


class LaunchTarget:
    """
    Constants for launch_target field options
    """
    IFRAME = LaunchTargetOption('Inline', 'iframe')
    MODAL = LaunchTargetOption('Modal', 'modal')
    NEW_WINDOW = LaunchTargetOption('New Window', 'new_window')


@XBlock.needs('i18n')
@XBlock.needs('rebind_user')
@XBlock.wants('user')
@XBlock.wants('settings')
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

    block_settings_key = 'lti_consumer'

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
    config_type = String(
        display_name=_("Configuration Type"),
        scope=Scope.settings,
        values_provider=valid_config_type_values,
        default="new",
        help=_(
            "Select 'Configuration on block' to configure a new LTI Tool. "
            "If the support staff provided you with a pre-configured LTI reusable Tool ID, select"
            "'Reusable Configuration' and enter it in the text field below."
        )
    )

    lti_version = String(
        display_name=_("LTI Version"),
        scope=Scope.settings,
        values=[
            {"display_name": "LTI 1.1/1.2", "value": "lti_1p1"},
            {"display_name": "LTI 1.3", "value": "lti_1p3"},
        ],
        default="lti_1p1",
        help=_(
            "Select the LTI version that your tool supports."
            "<br />The XBlock LTI Consumer fully supports LTI 1.1.1, "
            "LTI 1.3 and LTI Advantage features."
        ),
    )

    external_config = String(
        display_name=_("LTI Reusable Configuration ID"),
        scope=Scope.settings,
        help=_("Enter the reusable LTI external configuration ID provided by the support staff."),
    )

    # LTI 1.3 fields
    lti_1p3_launch_url = String(
        display_name=_("Tool Launch URL"),
        default='',
        scope=Scope.settings,
        help=_(
            "Enter the LTI 1.3 Tool Launch URL. "
            "<br />This is the URL the LMS will use to launch the LTI Tool."
        ),
    )
    lti_1p3_oidc_url = String(
        display_name=_("Tool Initiate Login URL"),
        default='',
        scope=Scope.settings,
        help=_(
            "Enter the LTI 1.3 Tool OIDC Authorization url (can also be called login or login initiation URL)."
            "<br />This is the URL the LMS will use to start a LTI authorization "
            "prior to doing the launch request."
        ),
    )
    lti_1p3_redirect_uris = List(
        display_name=_("Registered Redirect URIs"),
        help=_(
            "Valid urls the Tool may request us to redirect the id token to. The redirect uris "
            "are often the same as the launch url/deep linking url so if this field is "
            "empty, it will use them as the default. If you need to use different redirect "
            "uri's, enter them here. If you use this field you must enter all valid redirect "
            "uri's the tool may request."
        ),
        scope=Scope.settings
    )

    lti_1p3_tool_key_mode = String(
        display_name=_("Tool Public Key Mode"),
        scope=Scope.settings,
        values=[
            {"display_name": "Public Key", "value": "public_key"},
            {"display_name": "Keyset URL", "value": "keyset_url"},
        ],
        default="public_key",
        help=_(
            "Select how the tool's public key information will be specified."
        ),
    )
    lti_1p3_tool_keyset_url = String(
        display_name=_("Tool Keyset URL"),
        default='',
        scope=Scope.settings,
        help=_(
            "Enter the LTI 1.3 Tool's JWK keysets URL."
            "<br />This link should retrieve a JSON file containing"
            " public keys and signature algorithm information, so"
            " that the LMS can check if the messages and launch"
            " requests received have the signature from the tool."
            "<br /><b>This is not required when doing LTI 1.3 Launches"
            " without LTI Advantage nor Basic Outcomes requests.</b>"
        ),
    )
    lti_1p3_tool_public_key = String(
        display_name=_("Tool Public Key"),
        multiline_editor=True,
        default='',
        scope=Scope.settings,
        help=_(
            "Enter the LTI 1.3 Tool's public key."
            "<br />This is a string that starts with '-----BEGIN PUBLIC KEY-----' and is required "
            "so that the LMS can check if the messages and launch requests received have the signature "
            "from the tool."
            "<br /><b>This is not required when doing LTI 1.3 Launches without LTI Advantage nor "
            "Basic Outcomes requests.</b>"
        ),
    )

    lti_1p3_enable_nrps = Boolean(
        display_name=_("Enable LTI NRPS"),
        help=_("Enable LTI Names and Role Provisioning Services."),
        default=False,
        scope=Scope.settings
    )

    # DEPRECATED - These variables were moved to the LtiConfiguration Model
    lti_1p3_client_id = String(
        display_name=_("LTI 1.3 Block Client ID - DEPRECATED"),
        default='',
        scope=Scope.settings,
        help=_("DEPRECATED - This is now stored in the LtiConfiguration model."),
    )
    lti_1p3_block_key = String(
        display_name=_("LTI 1.3 Block Key - DEPRECATED"),
        default='',
        scope=Scope.settings
    )

    # Switch to enable/disable the LTI Advantage Deep linking service
    lti_advantage_deep_linking_enabled = Boolean(
        display_name=_("Deep linking"),
        help=_("Select True if you want to enable LTI Advantage Deep Linking."),
        default=False,
        scope=Scope.settings
    )
    lti_advantage_deep_linking_launch_url = String(
        display_name=_("Deep Linking Launch URL"),
        default='',
        scope=Scope.settings,
        help=_(
            "Enter the LTI Advantage Deep Linking Launch URL. If the tool does not specify one, "
            "use the same value as 'Tool Launch URL'."
        ),
    )
    lti_advantage_ags_mode = String(
        display_name=_("LTI Assignment and Grades Service"),
        values=[
            {"display_name": _("Disabled"), "value": "disabled"},
            {"display_name": _("Allow tools to submit grades only (declarative)"), "value": "declarative"},
            {"display_name": _("Allow tools to manage and submit grade (programmatic)"), "value": "programmatic"},
        ],
        default='declarative',
        scope=Scope.settings,
        help=_(
            "Enable the LTI-AGS service and select the functionality enabled for LTI tools. "
            "The 'declarative' mode (default) will provide a tool with a LineItem created from the XBlock settings, "
            "while the 'programmatic' one will allow tools to manage, create and link the grades."
        ),
    )

    # LTI 1.1 fields
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

    # Misc
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
    ask_to_send_full_name = Boolean(
        display_name=_("Request user's full name"),
        # Translators: This is used to request the user's full name for a third party service.
        help=_("Select True to request the user's full name."),
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

    enable_processors = Boolean(
        display_name=_("Send extra parameters"),
        help=_("Select True to send the extra parameters, which might contain Personally Identifiable Information. "
               "The processors are site-wide, please consult the site administrator if you have any questions."),
        default=False,
        scope=Scope.settings
    )

    # Possible editable fields
    editable_field_names = (
        'display_name', 'description', 'config_type', 'lti_version', 'external_config',
        # LTI 1.3 variables
        'lti_1p3_launch_url', 'lti_1p3_redirect_uris', 'lti_1p3_oidc_url',
        'lti_1p3_tool_key_mode', 'lti_1p3_tool_keyset_url', 'lti_1p3_tool_public_key',
        'lti_1p3_enable_nrps',
        # LTI Advantage variables
        'lti_advantage_deep_linking_enabled', 'lti_advantage_deep_linking_launch_url',
        'lti_advantage_ags_mode',
        # LTI 1.1 variables
        'lti_id', 'launch_url',
        # Other parameters
        'custom_parameters', 'launch_target', 'button_text', 'inline_height', 'modal_height',
        'modal_width', 'has_score', 'weight', 'hide_launch', 'accept_grades_past_due',
        'ask_to_send_username', 'ask_to_send_full_name', 'ask_to_send_email', 'enable_processors',
    )

    # Author view
    has_author_view = True

    @staticmethod
    def workbench_scenarios():
        """
        Gather scenarios to be displayed in the workbench
        """
        scenarios = [
            ('LTI Consumer XBlock',
             '''<sequence_demo>
                    <lti_consumer
                        display_name="LTI Consumer - New Window"
                        lti_id="test"
                        description=""
                        ask_to_send_username="False"
                        ask_to_send_email="False"
                        enable_processors="True"
                        launch_target="new_window"
                        launch_url="https://lti.tools/saltire/tp" />

                    <lti_consumer
                        display_name="LTI Consumer - IFrame"
                        lti_id="test"
                        ask_to_send_username="False"
                        ask_to_send_email="False"
                        enable_processors="True"
                        description=""
                        launch_target="iframe"
                        launch_url="https://lti.tools/saltire/tp" />
                </sequence_demo>
             '''),
        ]
        return scenarios

    @staticmethod
    def _get_statici18n_js_url(loader):  # pragma: no cover
        """
        Returns the Javascript translation file for the currently selected language, if any found by
        `pkg_resources`
        """
        lang_code = translation.get_language()
        if not lang_code:
            return None
        text_js = 'public/js/translations/{lang_code}/text.js'
        country_code = lang_code.split('-')[0]
        for code in (translation.to_locale(lang_code), lang_code, country_code):
            if pkg_resources.resource_exists(loader.module_name, text_js.format(lang_code=code)):
                return text_js.format(lang_code=code)
        return None

    def validate_field_data(self, validation, data):
        if not isinstance(data.custom_parameters, list):
            _ = self.runtime.service(self, "i18n").ugettext
            validation.add(ValidationMessage(ValidationMessage.ERROR, str(
                _("Custom Parameters must be a list")
            )))

        # keyset URL and public key are mutually exclusive
        if data.lti_1p3_tool_key_mode == 'keyset_url':
            data.lti_1p3_tool_public_key = ''
        elif data.lti_1p3_tool_key_mode == 'public_key':
            data.lti_1p3_tool_keyset_url = ''

    def validate(self):
        """
        Validate this XBlock's configuration
        """
        validation = super().validate()
        _ = self.runtime.service(self, "i18n").ugettext
        # Check if lti_id exists in the LTI passports of the current course. (LTI 1.1 only)
        # This validation is just for the Unit page in Studio; we don't want to block users from saving
        # a new LTI ID before they've added it to advanced settings, but we do want to warn them about it.
        # If we put this check in validate_field_data(), the settings editor wouldn't let them save changes.
        if self.lti_version == "lti_1p1" and self.lti_id:
            lti_passport_ids = [lti_passport.split(':')[0].strip() for lti_passport in self.course.lti_passports]
            if self.lti_id.strip() not in lti_passport_ids:
                validation.add(ValidationMessage(ValidationMessage.WARNING, str(
                    _("The specified LTI ID is not configured in this course's Advanced Settings.")
                )))
        return validation

    def get_settings(self):
        """
        Get the XBlock settings bucket via the SettingsService.
        """
        settings_service = self.runtime.service(self, 'settings')
        if settings_service:
            return settings_service.get_settings_bucket(self)

        return {}

    def get_parameter_processors(self):
        """
        Read the parameter processor functions from the settings and return their functions.
        """
        if not self.enable_processors:
            return

        try:
            for path in self.get_settings().get('parameter_processors', []):
                module_path, func_name = path.split(':', 1)
                module = import_module(module_path)
                yield getattr(module, func_name)
        except Exception:
            log.exception('Something went wrong in reading the LTI XBlock configuration.')
            raise

    def get_pii_sharing_enabled(self):
        """
        Returns whether PII can be transmitted via this XBlock. This controls both whether the PII sharing XBlock
        fields ask_to_send_username, ask_to_send_full_name, and ask_to_send_email are displayed in Studio and whether
        these data are shared in LTI launches, regardless of the values of the settings on the XBlock.
        """
        config_service = self.runtime.service(self, 'lti-configuration')
        if config_service:
            is_already_sharing_learner_info = (
                self.ask_to_send_username or
                self.ask_to_send_full_name or
                self.ask_to_send_email
            )
            return config_service.configuration.lti_access_to_learners_editable(
                self.scope_ids.usage_id.context_key,
                is_already_sharing_learner_info,
            )

        # TODO: The LTI configuration service is currently only available from the studio_view. This means that
        #       the CourseAllowPIISharingInLTIFlag does not control PII sharing in the author_view or student_view,
        #       because the service is not defined in those contexts.
        return True

    @property
    def editable_fields(self):
        """
        Return a list of editable fields that should be editable by the user. Any XBlock fields not included in the
        returned list are not available or visible to the user to be edited.

        Note that the Javascript in xblock_studio_view.js shows and hides various fields depending on the option
        currently selected for these fields. Because editable_fields defines a list of fields when that's used rendering
        the Studio edit view, it cannot support the dynamic experience we want the user to have when editing the XBlock.
        This property should return the set of all properties the user should be able to modify based on the current
        environment. For example, if the external_config_filter_enabled flag is not enabled, the external_config field
        should not be a part of editable_fields, because no user can edit this field in this case. On the other hand, if
        the currently selected config_type is 'database', the fields that are otherwise stored in the database should
        still be a part of editable_fields, because a user may select a different config_type from the menu, and we want
        those fields to become editable at that time. The Javascript will determine when to show or to hide a given
        field.

        Fields that are potentially filtered out include "config_type", "external_config", "ask_to_send_username",
        "ask_to_send_full_name", and "ask_to_send_email".
        """
        editable_fields = self.editable_field_names
        noneditable_fields = []

        is_database_config_enabled = database_config_enabled(self.scope_ids.usage_id.context_key)
        is_external_config_filter_enabled = external_config_filter_enabled(self.scope_ids.usage_id.context_key)

        # If neither additional config_types are enabled, do not display the "config_type" field to users, as "new" is
        # the only option and does not make sense without other options.
        if not is_database_config_enabled and not is_external_config_filter_enabled:
            noneditable_fields.append('config_type')

        # If the enable_external_config_filter is not enabled, do not display the "external_config" field to users.
        if not is_external_config_filter_enabled:
            noneditable_fields.append('external_config')

        # update the editable fields if this XBlock is configured to not to allow the
        # editing of 'ask_to_send_username', 'ask_to_send_full_name', and 'ask_to_send_email'.
        pii_sharing_enabled = self.get_pii_sharing_enabled()
        if not pii_sharing_enabled:
            noneditable_fields.extend(['ask_to_send_username', 'ask_to_send_full_name', 'ask_to_send_email'])

        editable_fields = tuple(
            field
            for field in editable_fields
            if field not in noneditable_fields
        )

        return editable_fields

    @property
    def descriptor(self):
        """
        Returns this XBlock object.

        This is for backwards compatibility with the XModule API.
        Some LMS code still assumes a descriptor attribute on the XBlock object.
        """
        return self

    @property
    def context_id(self):
        """
        Return context_id.

        context_id is an opaque identifier that uniquely identifies the context (e.g., a course)
        that contains the link being launched.
        """
        return str(self.scope_ids.usage_id.context_key)

    @property
    def role(self):
        """
        Get system user role.
        """
        user = self.runtime.service(self, 'user').get_current_user()
        if not user.opt_attrs["edx-platform.is_authenticated"]:
            raise LtiError(self.ugettext("Could not get user data for current request"))

        return user.opt_attrs.get('edx-platform.user_role', 'student')

    @property
    def course(self):
        """
        Return course by course id.
        """
        return self.runtime.modulestore.get_course(self.scope_ids.usage_id.context_key)

    @property
    def lti_provider_key_secret(self):
        """
        Obtains client_key and client_secret credentials from current course.
        """
        for lti_passport in self.course.lti_passports:
            try:
                # NOTE While unpacking the lti_passport by using ":" as delimiter, first item will be lti_id,
                #  last item will be client_secret and the rest are considered as client_key.
                #  So you can have more than one colon for client_key.
                lti_id, *key, secret = [i.strip() for i in lti_passport.split(':')]
                if not key:
                    raise ValueError
                key = ':'.join(key)
            except ValueError as err:
                msg = self.ugettext(
                    'Could not parse LTI passport: {lti_passport!r}. Should be "id:key:secret" string.'
                ).format(lti_passport=lti_passport)
                raise LtiError(msg) from err

            if lti_id == self.lti_id.strip():
                return key, secret

        return '', ''

    @property
    def lms_user_id(self):
        """
        Returns the edx-platform database user id for the current user.
        """
        user_id = self.runtime.service(self, 'user').get_current_user().opt_attrs.get(
            'edx-platform.user_id', None)

        if user_id is None:
            raise LtiError(self.ugettext("Could not get user id for current request"))
        return user_id

    @property
    def anonymous_user_id(self):
        """
        Returns the opaque anonymous_student_id for the current user.
        This defaults to 'student' when testing in studio.
        It will return the proper anonymous ID in the LMS.
        """
        user_id = self.runtime.service(self, 'user').get_current_user().opt_attrs.get(
            'edx-platform.anonymous_user_id', None)

        if user_id is None:
            raise LtiError(self.ugettext("Could not get user id for current request"))
        return str(user_id)

    def get_icon_class(self):
        """ Returns the icon class """
        if self.graded and self.has_score:  # pylint: disable=no-member
            return 'problem'
        return 'other'

    @property
    def external_user_id(self):
        """
        Returns the opaque external user id for the current user.
        """
        user_id = self.runtime.service(self, 'user').get_external_user_id('lti')
        if user_id is None:
            raise LtiError(self.ugettext("Could not get user id for current request"))
        return str(user_id)

    def get_lti_1p1_user_id(self):
        """
        Returns the user ID to send to an LTI tool during an LTI 1.1/2.0 launch. If the
        enable_external_user_id_1p1_launches CourseWaffleFlag is enabled for the course, returns the external_user_id
        defined by the external_user_ids Djangoapp. Otherwise, returns the anonymous_user_id.

        This addresses cases where LTI tools require a static, opaque user_id that is consistent across contexts. On an
        opt-in basis, courses can be set up to send the external_user_id instead of the anonymous_user_id. Note that
        toggling this flag in a running course carries the risk of breaking the LTI integrations in the course. This
        flag should also only be enabled for new courses in which no LTI attempts have been made.
        """
        if external_user_id_1p1_launches_enabled(self.scope_ids.usage_id.context_key):
            return self.external_user_id

        return self.anonymous_user_id

    def get_lti_1p1_user_from_user_id(self, user_id):
        """
        Returns the user object associated with a user_id. This is used in LTI 1.1/2.0 integrations for calls to the
        LTI 1.1 Basic Outcomes service and the LTI 2.0 Results service. Tool Providers may make calls to this library's
        endpoints with a user identifier. This function returns a user object associated with that user identifier.

        The user identifier may be a course-anonymized user ID (i.e. the anonymous_user_id) or the global, consistent
        user ID (i.e. the external_user_id). This functions returns the correct User object.
        """
        if external_user_id_1p1_launches_enabled(self.scope_ids.usage_id.context_key):
            try:
                return compat.get_user_from_external_user_id(user_id)
            except LtiError:
                return None
        else:
            return self.runtime.service(self, 'user').get_user_by_anonymous_id(user_id)

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
        return str(urllib.parse.quote(f"{settings.LMS_BASE}-{self.scope_ids.usage_id.html_id()}"))

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
            context=urllib.parse.quote(self.context_id),
            resource_link=self.resource_link_id,
            user_id=self.get_lti_1p1_user_id()
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
                except ValueError as err:
                    _ = self.runtime.service(self, "i18n").ugettext
                    msg = self.ugettext(
                        'Could not parse custom parameter: {custom_parameter!r}. Should be "x=y" string.'
                    ).format(custom_parameter=custom_parameter)
                    raise LtiError(msg) from err

                # LTI specs: 'custom_' should be prepended before each custom parameter, as pointed in link above.
                if param_name not in LTI_PARAMETERS:
                    param_name = 'custom_' + param_name

                if (param_value.startswith(CUSTOM_PARAMETER_TEMPLATE_TAGS[0]) and
                        param_value.endswith(CUSTOM_PARAMETER_TEMPLATE_TAGS[1])):
                    param_value = resolve_custom_parameter_template(self, param_value)

                custom_parameters[param_name] = param_value

        custom_parameters['custom_component_display_name'] = str(self.display_name)

        if self.due:
            custom_parameters.update({
                'custom_component_due_date': self.due.strftime('%Y-%m-%d %H:%M:%S')
            })
            if self.graceperiod:
                custom_parameters.update({
                    'custom_component_graceperiod': str(self.graceperiod.total_seconds())
                })

        return custom_parameters

    def is_past_due(self):
        """
        Is it now past this problem's due date, including grace period?
        """
        due_date = self.due
        if self.graceperiod is not None and due_date:
            close_date = due_date + self.graceperiod
        else:
            close_date = due_date
        return close_date is not None and timezone.now() > close_date

    def _get_lti_consumer(self):
        """
        Returns a preconfigured LTI consumer depending on the value.

        If the block is configured to use LTI 1.1, set up a
        base LTI 1.1 consumer class.

        If the block is configured to use LTI 1.3, set up a
        base LTI 1.3 consumer class with all block related
        configuration services.

        This uses the LTI API to fetch the configuration
        from the models and instance the LTI client.

        This class does NOT store state between calls.
        """
        # Runtime import since this will only run in the
        # Open edX LMS/Studio environments.
        # pylint: disable=import-outside-toplevel
        from lti_consumer.api import config_id_for_block, get_lti_consumer

        return get_lti_consumer(config_id_for_block(self))

    def extract_real_user_data(self):
        """
        Extract and return real user data from the runtime
        """
        user = self.runtime.service(self, 'user').get_current_user()

        if not user.opt_attrs["edx-platform.is_authenticated"]:
            raise LtiError(self.ugettext("Could not get user data for current request"))

        user_data = {
            'user_email': None,
            'user_username': None,
            'user_full_name': user.full_name,
            'user_language': None,
        }

        try:
            user_data['user_email'] = user.emails[0]
        except IndexError:
            user_data['user_email'] = None

        user_data['user_username'] = user.opt_attrs.get("edx-platform.username", None)
        user_data['user_language'] = user.opt_attrs.get("edx-platform.user_preferences", {}).get("pref-lang", None)

        return user_data

    def studio_view(self, context):
        """
        Get Studio View fragment
        """
        loader = ResourceLoader(__name__)
        fragment = super().studio_view(context)

        fragment.add_javascript(loader.load_unicode("static/js/xblock_studio_view.js"))
        fragment.initialize_js('LtiConsumerXBlockInitStudio')

        return fragment

    def author_view(self, context):
        """
        XBlock author view of this component.

        If using LTI 1.1 it shows a launch preview of the XBlock.
        If using LTI 1.3 it displays a fragment with parameters that
        need to be set on the LTI Tool to make the integration work.
        """
        if self.lti_version == "lti_1p1":
            return self.student_view(context)

        # Runtime import since this will only run in the
        # Open edX LMS/Studio environments.
        # pylint: disable=import-outside-toplevel
        from lti_consumer.api import get_lti_1p3_launch_info

        # Retrieve LTI 1.3 Launch information
        launch_data = self.get_lti_1p3_launch_data()
        context.update(
            get_lti_1p3_launch_info(
                launch_data,
            )
        )

        # Render template
        fragment = Fragment()
        loader = ResourceLoader(__name__)
        fragment.add_content(
            loader.render_django_template(
                '/templates/html/lti_1p3_studio.html',
                context,
                i18n_service=self.runtime.service(self, 'i18n')
            ),
        )
        fragment.add_css(loader.load_unicode('static/css/student.css'))
        fragment.add_javascript(loader.load_unicode('static/js/xblock_lti_consumer.js'))
        statici18n_js_url = self._get_statici18n_js_url(loader)
        if statici18n_js_url:
            fragment.add_javascript_url(self.runtime.local_resource_url(self, statici18n_js_url))
        fragment.initialize_js('LtiConsumerXBlock')
        return fragment

    @XBlock.supports("multi_device")
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
        statici18n_js_url = self._get_statici18n_js_url(loader)
        if statici18n_js_url:
            fragment.add_javascript_url(self.runtime.local_resource_url(self, statici18n_js_url))
        fragment.initialize_js('LtiConsumerXBlock')
        return fragment

    @XBlock.handler
    def lti_launch_handler(self, request, suffix=''):  # pylint: disable=unused-argument
        """
        XBlock handler for launching LTI 1.1 tools.

        Displays a form which is submitted via Javascript
        to send the LTI launch POST request to the LTI
        provider.

        Arguments:
            request (xblock.django.request.DjangoWebobRequest): Request object for current HTTP request
            suffix (unicode): Request path after "lti_launch_handler/"

        Returns:
            webob.response: HTML LTI launch form
        """
        lti_consumer = self._get_lti_consumer()

        # Occassionally, users try to do an LTI launch while they are unauthenticated. It is not known why this occurs.
        # Sometimes, it is due to a web crawlers; other times, it is due to actual users of the platform. Regardless,
        # return a 400 response with an appropriate error template.
        try:
            real_user_data = self.extract_real_user_data()
            user_id = self.get_lti_1p1_user_id()
            role = self.role

            # Convert the LMS role into an LTI 1.1 role.
            role = LTI_1P1_ROLE_MAP.get(role, 'Student,Learner')

            result_sourcedid = self.lis_result_sourcedid
        # Fails if extract_real_user_data() fails
        except LtiError as err:
            loader = ResourceLoader(__name__)
            template = loader.render_django_template('/templates/html/lti_launch_error.html',
                                                     context={"error_msg": err})
            return Response(template, status=400, content_type='text/html')

        username = None
        full_name = None
        email = None

        # Send PII fields only if this XBlock is configured to allow the sending PII.
        pii_sharing_enabled = self.get_pii_sharing_enabled()
        if pii_sharing_enabled:
            if self.ask_to_send_username and real_user_data['user_username']:
                username = real_user_data['user_username']
            if self.ask_to_send_full_name and real_user_data['user_full_name']:
                full_name = real_user_data['user_full_name']
            if self.ask_to_send_email and real_user_data['user_email']:
                email = real_user_data['user_email']

        lti_consumer.set_user_data(
            user_id,
            role,
            result_sourcedid=result_sourcedid,
            person_sourcedid=username,
            person_contact_email_primary=email,
            person_name_full=full_name,
        )

        lti_consumer.set_context_data(
            self.context_id,
            self.course.display_name_with_default,
            self.course.display_org_with_default
        )

        if self.has_score:
            lti_consumer.set_outcome_service_url(self.outcome_service_url)

        if real_user_data['user_language']:
            lti_consumer.set_launch_presentation_locale(real_user_data['user_language'])

        lti_consumer.set_custom_parameters(self.prefixed_custom_parameters)

        for processor in self.get_parameter_processors():
            try:
                default_params = getattr(processor, 'lti_xblock_default_params', {})
                lti_consumer.set_extra_claims(default_params)
                lti_consumer.set_extra_claims(processor(self) or {})
            except Exception:  # pylint: disable=broad-except
                # Log the error without causing a 500-error.
                # Useful for catching casual runtime errors in the processors.
                log.exception('Error in XBlock LTI parameter processor "%s"', processor)

        lti_parameters = lti_consumer.generate_launch_request(self.resource_link_id)

        # emit tracking event
        event = {
            'lti_version': lti_parameters.get('lti_version'),
            'user_roles': lti_parameters.get('roles'),
            'launch_url': lti_consumer.lti_launch_url,
        }
        track_event('xblock.launch_request', event)

        loader = ResourceLoader(__name__)
        context = self._get_context_for_template()
        context.update({'lti_parameters': lti_parameters})
        template = loader.render_django_template('/templates/html/lti_launch.html', context)
        return Response(template, content_type='text/html')

    @XBlock.handler
    def lti_1p3_access_token(self, request, suffix=''):  # pylint: disable=unused-argument
        """
        XBlock handler for creating access tokens for the LTI 1.3 tool.
        This endpoint is only valid when a LTI 1.3 tool is being used.
        Returns:
            django.http.HttpResponse:
                Either an access token or error message detailing the failure.
                All responses are RFC 6749 compliant.
        References:
            Sucess: https://tools.ietf.org/html/rfc6749#section-4.4.3
            Failure: https://tools.ietf.org/html/rfc6749#section-5.2
        """
        if self.lti_version != "lti_1p3":
            return Response(status=404)

        # Asserting that the consumer can be created. This makes sure that the LtiConfiguration
        # object exists before calling the Django View
        assert self._get_lti_consumer()
        # Runtime import because this can only be run in the LMS/Studio Django
        # environments. Importing the views on the top level will cause RuntimeErorr
        from lti_consumer.plugin.views import access_token_endpoint  # pylint: disable=import-outside-toplevel
        return access_token_endpoint(request, usage_id=str(self.scope_ids.usage_id))

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
        lti_consumer = self._get_lti_consumer()
        lti_consumer.set_outcome_service_url(self.outcome_service_url)

        if settings.DEBUG:
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

        user = self.get_lti_1p1_user_from_user_id(anon_id)
        if not user:  # that means we can't save to database, as we do not have real user id.
            msg = _("[LTI]: Real user not found against anon_id: {}").format(anon_id)
            log.info(msg)
            return Response(status=404)  # have to do 404 due to spec, but 400 is better, with error msg in body

        try:
            # Call the appropriate LtiConsumer1p1 method
            args = [lti_consumer, user]
            if request.method == 'PUT':
                # Request body should be passed as an argument
                # to result handler method on PUT
                args.append(request.body)
            response_body = getattr(
                self,
                f"_result_service_{request.method.lower()}"
            )(*args)
        except (AttributeError, LtiError):
            return Response(status=404)

        return Response(
            json_body=response_body,
            content_type=LtiConsumer1p1.CONTENT_TYPE_RESULT_JSON,
        )

    def _result_service_get(self, lti_consumer, user):
        """
        Helper request handler for GET requests to LTI 2.0 result endpoint

        GET handler for lti_2_0_result.  Assumes all authorization has been checked.

        Arguments:
            lti_consumer (lti_consumer.lti_1p1.LtiConsumer1p1):  LtiConsumer object that manages Lti1.1 interaction
            user (django.contrib.auth.models.User):  Actual user linked to anon_id in request path suffix

        Returns:
            dict:  response to this request as dictated by the LtiConsumer
        """
        self.runtime.service(self, 'rebind_user').rebind_noauth_module_to_user(self, user)
        args = []
        if self.module_score:
            args.extend([self.module_score, self.score_comment])
        return lti_consumer.get_result(*args)

    def _result_service_delete(self, lti_consumer, user):
        """
        Helper request handler for DELETE requests to LTI 2.0 result endpoint

        DELETE handler for lti_2_0_result.  Assumes all authorization has been checked.

        Arguments:
            lti_consumer (lti_consumer.lti_1p1.LtiConsumer1p1):  LtiConsumer object that manages Lti1.1 interaction
            user (django.contrib.auth.models.User):  Actual user linked to anon_id in request path suffix

        Returns:
            dict:  response to this request as dictated by the LtiConsumer
        """
        self.clear_user_module_score(user)
        return lti_consumer.delete_result()

    def _result_service_put(self, lti_consumer, user, result_json):
        """
        Helper request handler for PUT requests to LTI 2.0 result endpoint

        PUT handler for lti_2_0_result.  Assumes all authorization has been checked.

        Arguments:
            lti_consumer (lti_consumer.lti_1p1.LtiConsumer1p1):  LtiConsumer object that manages Lti1.1 interaction
            request (xblock.django.request.DjangoWebobRequest):  Request object
            real_user (django.contrib.auth.models.User):  Actual user linked to anon_id in request path suffix

        Returns:
            dict:  response to this request as dictated by the LtiConsumer
        """
        score, comment = parse_result_json(result_json)

        if score is None:
            # According to http://www.imsglobal.org/lti/ltiv2p0/ltiIMGv2p0.html#_Toc361225514
            # PUTting a JSON object with no "resultScore" field is equivalent to a DELETE.
            self.clear_user_module_score(user)
        else:
            self.set_user_module_score(user, score, self.max_score(), comment)
        return lti_consumer.put_result()

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

    def set_user_module_score(self, user, score, max_score, comment=''):
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

        self.runtime.service(self, 'rebind_user').rebind_noauth_module_to_user(self, user)

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

    def _get_lti_launch_url(self, consumer):
        """
        Return the LTI launch URL.
        """
        launch_url = self.launch_url

        # The lti_launch_url property only exists on the LtiConsumer1p1. The LtiConsumer1p3 does not have an
        # attribute with this name, so ensure that we're accessing it on the appropriate consumer class.
        if consumer and self.config_type in ("database", "external") and self.lti_version == "lti_1p1":
            launch_url = consumer.lti_launch_url

        return launch_url

    def get_lti_1p3_launch_data(self):
        """
        Return an instance of Lti1p3LaunchData, containing necessary data for an LTI 1.3 launch.
        """
        # Runtime import since this will only run in the
        # Open edX LMS/Studio environments.
        # TODO: Replace this with a more appropriate API function that is intended for public use.
        # pylint: disable=import-outside-toplevel
        from lti_consumer.api import config_id_for_block
        config_id = config_id_for_block(self)

        location = self.scope_ids.usage_id
        course_key = str(location.context_key)

        username = None
        full_name = None
        email = None

        pii_sharing_enabled = self.get_pii_sharing_enabled()
        if pii_sharing_enabled:
            user_data = self.extract_real_user_data()

            if self.ask_to_send_username and user_data['user_username']:
                username = user_data['user_username']
            if self.ask_to_send_full_name and user_data['user_full_name']:
                full_name = user_data['user_full_name']
            if self.ask_to_send_email and user_data['user_email']:
                email = user_data['user_email']

        launch_data = Lti1p3LaunchData(
            user_id=self.lms_user_id,
            user_role=self.role,
            config_id=config_id,
            resource_link_id=str(location),
            external_user_id=self.external_user_id,
            preferred_username=username,
            name=full_name,
            email=email,
            launch_presentation_document_target="iframe",
            context_id=course_key,
            context_type=["course_offering"],
            context_title=self.get_context_title(),
            context_label=course_key,
        )

        return launch_data

    def get_context_title(self):
        """
        Return the title attribute of the context_claim for LTI 1.3 launches. This information is included in the
        launch_data query or form parameter of the LTI 1.3 third-party login initiation request.
        """
        course_key = self.scope_ids.usage_id.context_key
        course = compat.get_course_by_id(course_key)

        return " - ".join([
            course.display_name_with_default,
            course.display_org_with_default
        ])

    def _get_lti_block_launch_handler(self):
        """
        Return the LTI block launch handler.
        """
        # The "external" config_type is not supported for LTI 1.3, only LTI 1.1. Therefore, ensure that we define
        # the lti_block_launch_handler using LTI 1.1 logic for "external" config_types.
        # TODO: This needs to change when the LTI 1.3 support is added to the external config_type in the future.
        if self.lti_version == 'lti_1p1' or self.config_type == "external":
            lti_block_launch_handler = self.runtime.handler_url(self, 'lti_launch_handler').rstrip('/?')
        else:
            launch_data = self.get_lti_1p3_launch_data()

            # Retrieve and set LTI 1.3 Launch start URL
            # Runtime import since this will only run in the Open edX LMS/Studio environments.
            from lti_consumer.api import get_lti_1p3_content_url  # pylint: disable=import-outside-toplevel
            lti_block_launch_handler = get_lti_1p3_content_url(
                launch_data,
            )

        return lti_block_launch_handler

    def _get_lti_1p3_launch_url(self, consumer):
        """
        Return the LTI launch URL for LTI 1.3 integrations.
        """
        lti_1p3_launch_url = self.lti_1p3_launch_url.strip()

        # The "external" config_type is not supported for LTI 1.3, only LTI 1.1. Therefore, ensure that we define
        # the lti_1p3_launch_url using the LTI 1.3 consumer only for config_types that support LTI 1.3.
        # TODO: This needs to change when the LTI 1.3 support is added to the external config_type in the future.
        if consumer and self.lti_version == "lti_1p3" and self.config_type == "database":
            lti_1p3_launch_url = consumer.launch_url

        return lti_1p3_launch_url

    def _get_context_for_template(self):
        """
        Returns the context dict for LTI templates.

        Arguments:
            None

        Returns:
            dict: Context variables for templates
        """
        # For more context on ALLOWED_TAGS and ALLOWED_ATTRIBUTES
        # Look into this documentation URL see https://bleach.readthedocs.io/en/latest/clean.html#allowed-tags-tags
        # This lets all plaintext through.
        allowed_tags = bleach.sanitizer.ALLOWED_TAGS | {'img'}
        allowed_attributes = dict(bleach.sanitizer.ALLOWED_ATTRIBUTES, **{'img': ['src', 'alt']})
        sanitized_comment = bleach.clean(self.score_comment, tags=allowed_tags, attributes=allowed_attributes)

        lti_consumer = None
        # Don't pull from the Django database unless the config_type is one that stores the LTI configuration in the
        # database.
        if self.config_type in ("database", "external"):
            lti_consumer = self._get_lti_consumer()

        launch_url = self._get_lti_launch_url(lti_consumer)
        lti_block_launch_handler = self._get_lti_block_launch_handler()
        lti_1p3_launch_url = self._get_lti_1p3_launch_url(lti_consumer)

        # The values of ask_to_send_username, ask_to_send_full_name, and ask_to_send_email should only apply if PII
        # sharing is enabled.
        pii_sharing_enabled = self.get_pii_sharing_enabled()

        return {
            'launch_url': launch_url.strip(),
            'lti_1p3_launch_url': lti_1p3_launch_url,
            'element_id': self.scope_ids.usage_id.html_id(),
            'element_class': self.category,
            'launch_target': self.launch_target,
            'display_name': self.display_name,
            'form_url': lti_block_launch_handler,
            'hide_launch': self.hide_launch,
            'has_score': self.has_score,
            'weight': self.weight,
            'module_score': self.module_score,
            'comment': sanitized_comment,
            'description': self.description,
            'ask_to_send_username': self.ask_to_send_username if pii_sharing_enabled else False,
            'ask_to_send_full_name': self.ask_to_send_full_name if pii_sharing_enabled else False,
            'ask_to_send_email': self.ask_to_send_email if pii_sharing_enabled else False,
            'button_text': self.button_text,
            'inline_height': self.inline_height,
            'modal_vertical_offset': self._get_modal_position_offset(self.modal_height),
            'modal_horizontal_offset': self._get_modal_position_offset(self.modal_width),
            'modal_width': self.modal_width,
            'accept_grades_past_due': self.accept_grades_past_due,
            'lti_version': self.lti_version,
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
        if not viewport_percentage:
            viewport_percentage = 80        # set to default value in case viewport_percentage is None
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

    def index_dictionary(self):
        """
        Return dictionary prepared with module content and type for indexing.
        """
        # return key/value fields in a Python dict object
        # values may be numeric / string or dict
        # default implementation is an empty dict
        xblock_body = super().index_dictionary()

        index_body = {
            "display_name": self.display_name,
            "description": self.description,
        }

        if "content" in xblock_body:
            xblock_body["content"].update(index_body)
        else:
            xblock_body["content"] = index_body

        xblock_body["content_type"] = "LTI Consumer"

        return xblock_body
