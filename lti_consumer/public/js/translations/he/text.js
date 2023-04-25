
            (function(global){
                var XBlockLtiConsumerI18N = {
                  init: function() {
                    

'use strict';
{
  const globals = this;
  const django = globals.django || (globals.django = {});

  
  django.pluralidx = function(n) {
    const v = (n == 1 && n % 1 == 0) ? 0 : (n == 2 && n % 1 == 0) ? 1: (n % 10 == 0 && n % 1 == 0 && n > 10) ? 2 : 3;
    if (typeof v === 'boolean') {
      return v ? 1 : 0;
    } else {
      return v;
    }
  };
  

  /* gettext library */

  django.catalog = django.catalog || {};
  
  const newcatalog = {
    "Accept grades past deadline": "\u05e7\u05d1\u05dc \u05e6\u05d9\u05d5\u05e0\u05d9\u05dd \u05dc\u05d0\u05d7\u05e8 \u05d4\u05de\u05d5\u05e2\u05d3 \u05d4\u05e1\u05d5\u05e4\u05d9",
    "Add the key/value pair for any custom parameters, such as the page your e-book should open to or the background color for this component. Ex. [\"page=1\", \"color=white\"]<br />See the {docs_anchor_open}edX LTI documentation{anchor_close} for more details on this setting.": "\u05d4\u05d5\u05e1\u05e3 \u05d0\u05ea \u05e6\u05de\u05d3 \u05de\u05e4\u05ea\u05d7/\u05e2\u05e8\u05da \u05dc\u05db\u05dc \u05e4\u05e8\u05de\u05d8\u05e8 \u05d1\u05d4\u05ea\u05d0\u05de\u05d4 \u05d0\u05d9\u05e9\u05d9\u05ea \u05db\u05de\u05d5 \u05d4\u05d3\u05e3 \u05e9\u05d1\u05d5 \u05d4\u05e1\u05e4\u05e8 \u05d4\u05d0\u05dc\u05e7\u05d8\u05e8\u05d5\u05e0\u05d9 \u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d9\u05e4\u05ea\u05d7 \u05d0\u05d5 \u05e6\u05d1\u05e2 \u05d4\u05e8\u05e7\u05e2 \u05e9\u05dc \u05de\u05e8\u05db\u05d9\u05d1 \u05d6\u05d4. \u05dc\u05d3\u05d5\u05d2\u05de\u05d4. [\"page=1\", \"color=white\"]<br />\u05e8\u05d0\u05d4 \u05d0\u05ea {docs_anchor_open}edX LTI \u05ea\u05d9\u05e2\u05d5\u05d3{anchor_close} \u05dc\u05e4\u05e8\u05d8\u05d9\u05dd \u05e0\u05d5\u05e1\u05e4\u05d9\u05dd \u05d0\u05d5\u05d3\u05d5\u05ea \u05d4\u05d2\u05d3\u05e8\u05d4 \u05d6\u05d5.",
    "Button Text": "\u05d8\u05e7\u05e1\u05d8 \u05ea\u05d7\u05ea\u05d9",
    "Comment as returned from grader, LTI2.0 spec": "\u05d4\u05e2\u05e8\u05d4 \u05d7\u05d5\u05d6\u05e8\u05ea \u05de\u05de\u05e2\u05e0\u05d9\u05e7 \u05d4\u05e6\u05d9\u05d5\u05df, LTI2.0 spec",
    "Could not get user id for current request": "\u05dc\u05d0 \u05e0\u05d9\u05ea\u05df \u05dc\u05d4\u05e9\u05d9\u05d2 \u05de\u05d6\u05d4\u05d4 \u05de\u05e9\u05ea\u05de\u05e9 \u05dc\u05d1\u05e7\u05e9\u05d4 \u05d4\u05e0\u05d5\u05db\u05d7\u05d9\u05ea",
    "Custom Parameters": "\u05e4\u05e8\u05de\u05d8\u05e8\u05d9\u05dd \u05de\u05d5\u05ea\u05d0\u05de\u05d9\u05dd \u05d0\u05d9\u05e9\u05d9\u05ea",
    "Display Name": "\u05d4\u05e6\u05d2 \u05e9\u05dd",
    "Enter a description of the third party application. If requesting username and/or email, use this text box to inform users why their username and/or email will be forwarded to a third party application.": "\u05d9\u05e9 \u05dc\u05d4\u05d6\u05d9\u05df \u05ea\u05d9\u05d0\u05d5\u05e8 \u05e9\u05dc \u05d9\u05d9\u05e9\u05d5\u05dd \u05e6\u05d3 \u05d2'. \u05d1\u05d1\u05e7\u05e9\u05ea \u05e9\u05dd \u05de\u05e9\u05ea\u05de\u05e9 \u05d5/\u05d0\u05d5 \u05db\u05ea\u05d5\u05d1\u05ea \u05d3\u05d5\u05d0\u05f4\u05dc, \u05d9\u05e9 \u05dc\u05d4\u05e9\u05ea\u05de\u05e9 \u05d1\u05ea\u05d9\u05d1\u05ea \u05d8\u05e7\u05e1\u05d8 \u05d6\u05d5 \u05e2\u05dc \u05de\u05e0\u05ea \u05dc\u05d4\u05d5\u05d3\u05d9\u05e2 \u05dc\u05de\u05e9\u05ea\u05de\u05e9\u05d9\u05dd \u05de\u05d3\u05d5\u05e2 \u05e9\u05dd \u05d4\u05de\u05e9\u05ea\u05de\u05e9 \u05d5/\u05d0\u05d5 \u05db\u05ea\u05d5\u05d1\u05ea \u05d4\u05d3\u05d5\u05d0\u05f4 \u05dc \u05e9\u05dc\u05d4\u05dd \u05ea\u05d5\u05e2\u05d1\u05e8 \u05dc\u05d9\u05d9\u05e9\u05d5\u05dd \u05e9\u05dc \u05d2\u05d5\u05e8\u05dd \u05e6\u05d3 \u05d2'.",
    "Enter the LTI ID for the external LTI provider. This value must be the same LTI ID that you entered in the LTI Passports setting on the Advanced Settings page.<br />See the {docs_anchor_open}edX LTI documentation{anchor_close} for more details on this setting.": "\u05d4\u05d6\u05df \u05d0\u05ea \u05de\u05d6\u05d4\u05d4 \u05d4-LTI \u05dc\u05e1\u05e4\u05e7 \u05d4-LTI \u05d4\u05d7\u05d9\u05e6\u05d5\u05e0\u05d9. \u05e2\u05e8\u05da \u05d6\u05d4 \u05d7\u05d9\u05d9\u05d1 \u05dc\u05d4\u05d9\u05d5\u05ea \u05d6\u05d4\u05d4 \u05dc\u05de\u05d6\u05d4\u05d4 LTI \u05e9\u05d4\u05d6\u05e0\u05ea \u05d1\u05d4\u05d2\u05d3\u05e8\u05d5\u05ea LTI Passports \u05d4\u05e0\u05de\u05e6\u05d0 \u05d1\u05e2\u05de\u05d5\u05d3 \u05d4\u05d4\u05d2\u05d3\u05e8\u05d5\u05ea \u05d4\u05de\u05ea\u05e7\u05d3\u05de\u05d5\u05ea.<br />\u05dc\u05e4\u05e8\u05d8\u05d9\u05dd \u05e0\u05d5\u05e1\u05e4\u05d9\u05dd \u05d0\u05d5\u05d3\u05d5\u05ea \u05d4\u05d2\u05d3\u05e8\u05d4 \u05d6\u05d5, \u05e8\u05d0\u05d4 {docs_anchor_open}edX LTI \u05ea\u05d9\u05e2\u05d5\u05d3{anchor_close}.",
    "Enter the URL of the external tool that this component launches. This setting is only used when Hide External Tool is set to False.<br />See the {docs_anchor_open}edX LTI documentation{anchor_close} for more details on this setting.": "\u05d4\u05d6\u05df \u05d0\u05ea \u05db\u05ea\u05d5\u05d1\u05ea \u05d4\u05d0\u05ea\u05e8 \u05e9\u05dc \u05d4\u05db\u05dc\u05d9 \u05d4\u05d7\u05d9\u05e6\u05d5\u05e0\u05d9 \u05e9\u05e8\u05db\u05d9\u05d1 \u05d6\u05d4 \u05de\u05e4\u05e2\u05d9\u05dc. \u05e0\u05d9\u05ea\u05df \u05dc\u05d4\u05e9\u05ea\u05de\u05e9 \u05d1\u05d4\u05d2\u05d3\u05e8\u05d4 \u05d6\u05d5 \u05d0\u05da \u05d5\u05e8\u05e7 \u05db\u05d0\u05e9\u05e8 \u05d4\u05d0\u05e4\u05e9\u05e8\u05d5\u05ea '\u05d4\u05e1\u05ea\u05e8 \u05db\u05dc\u05d9 \u05d7\u05d9\u05e6\u05d5\u05e0\u05d9' \u05e0\u05de\u05e6\u05d0\u05ea \u05d1\u05de\u05e6\u05d1 'False'.<br />\u05dc\u05e4\u05e8\u05d8\u05d9\u05dd \u05e0\u05d5\u05e1\u05e4\u05d9\u05dd \u05d0\u05d5\u05d3\u05d5\u05ea \u05d4\u05d2\u05d3\u05e8\u05d4 \u05d6\u05d5, \u05e8\u05d0\u05d4 {docs_anchor_open}edX LTI \u05ea\u05d9\u05e2\u05d5\u05d3{anchor_close}.",
    "Enter the desired pixel height of the iframe which will contain the LTI tool. This setting is only used when Hide External Tool is set to False and LTI Launch Target is set to Inline.": "\u05d4\u05d6\u05df \u05d0\u05ea \u05d2\u05d5\u05d1\u05d4 \u05d4\u05e4\u05d9\u05e7\u05e1\u05dc\u05d9\u05dd \u05d4\u05de\u05d1\u05d5\u05e7\u05e9 \u05e9\u05dc \u05d4-iframe \u05e9\u05d9\u05db\u05dc\u05d5\u05dc \u05d0\u05ea \u05db\u05dc\u05d9 \u05d4-LTI. \u05e0\u05d9\u05ea\u05df \u05dc\u05d4\u05e9\u05ea\u05de\u05e9 \u05d1\u05d4\u05d2\u05d3\u05e8\u05d4 \u05d6\u05d5 \u05d0\u05da \u05d5\u05e8\u05e7 \u05db\u05d0\u05e9\u05e8 \u05d4\u05d0\u05e4\u05e9\u05e8\u05d5\u05ea '\u05d4\u05e1\u05ea\u05e8 \u05db\u05dc\u05d9 \u05d7\u05d9\u05e6\u05d5\u05e0\u05d9' \u05e0\u05de\u05e6\u05d0\u05ea \u05d1\u05de\u05e6\u05d1 '\u05dc\u05d0 \u05e0\u05db\u05d5\u05df' \u05d5\u05db\u05d0\u05e9\u05e8 LTI Launch Target \u05de\u05d5\u05d2\u05d3\u05e8 \u05db-Inline.",
    "Enter the desired viewport percentage height of the modal overlay which will contain the LTI tool. This setting is only used when Hide External Tool is set to False and LTI Launch Target is set to Modal.": "\u05d4\u05d6\u05df \u05d0\u05ea \u05d0\u05d7\u05d5\u05d6 \u05d2\u05d5\u05d1\u05d4 \u05d4\u05d0\u05e9\u05e0\u05d1 \u05e9\u05dc \u05db\u05d9\u05e1\u05d5\u05d9 \u05d4-modal \u05e9\u05d9\u05db\u05dc\u05d5\u05dc \u05d0\u05ea \u05db\u05dc\u05d9 \u05d4-LTI. \u05e0\u05d9\u05ea\u05df \u05dc\u05d4\u05e9\u05ea\u05de\u05e9 \u05d1\u05d4\u05d2\u05d3\u05e8\u05d4 \u05d6\u05d5 \u05d0\u05da \u05d5\u05e8\u05e7 \u05db\u05d0\u05e9\u05e8 \u05d4\u05d0\u05e4\u05e9\u05e8\u05d5\u05ea '\u05d4\u05e1\u05ea\u05e8 \u05db\u05dc\u05d9 \u05d7\u05d9\u05e6\u05d5\u05e0\u05d9' \u05e0\u05de\u05e6\u05d0\u05ea \u05d1\u05de\u05e6\u05d1 '\u05dc\u05d0 \u05e0\u05db\u05d5\u05df' \u05d5\u05db\u05d0\u05e9\u05e8 LTI Launch Target \u05de\u05d5\u05d2\u05d3\u05e8 \u05db-Modal.",
    "Enter the desired viewport percentage width of the modal overlay which will contain the LTI tool. This setting is only used when Hide External Tool is set to False and LTI Launch Target is set to Modal.": "\u05d4\u05d6\u05df \u05d0\u05ea \u05d0\u05d7\u05d5\u05d6 \u05e8\u05d5\u05d7\u05d1 \u05d4\u05d0\u05e9\u05e0\u05d1 \u05e9\u05dc \u05db\u05d9\u05e1\u05d5\u05d9 \u05d4-modal \u05e9\u05d9\u05db\u05dc\u05d5\u05dc \u05d0\u05ea \u05db\u05dc\u05d9 \u05d4-LTI. \u05e0\u05d9\u05ea\u05df \u05dc\u05d4\u05e9\u05ea\u05de\u05e9 \u05d1\u05d4\u05d2\u05d3\u05e8\u05d4 \u05d6\u05d5 \u05d0\u05da \u05d5\u05e8\u05e7 \u05db\u05d0\u05e9\u05e8 \u05d4\u05d0\u05e4\u05e9\u05e8\u05d5\u05ea '\u05d4\u05e1\u05ea\u05e8 \u05db\u05dc\u05d9 \u05d7\u05d9\u05e6\u05d5\u05e0\u05d9' \u05e0\u05de\u05e6\u05d0\u05ea \u05d1\u05de\u05e6\u05d1 '\u05dc\u05d0 \u05e0\u05db\u05d5\u05df' \u05d5\u05db\u05d0\u05e9\u05e8 LTI Launch Target \u05de\u05d5\u05d2\u05d3\u05e8 \u05db-Modal.",
    "Enter the name that students see for this component. Analytics reports may also use the display name to identify this component.": "\u05d9\u05e9 \u05dc\u05d4\u05d6\u05d9\u05df \u05d0\u05ea \u05e9\u05dd \u05d4\u05de\u05e8\u05db\u05d9\u05d1 \u05e9\u05e8\u05d5\u05d0\u05d9\u05dd \u05d4\u05dc\u05d5\u05de\u05d3\u05d9\u05dd. \u05d3\u05d5\u05d7\u05d5\u05ea \u05d4\u05e0\u05d9\u05ea\u05d5\u05d7 \u05d9\u05db\u05d5\u05dc\u05d9\u05dd \u05dc\u05d4\u05e9\u05ea\u05de\u05e9 \u05d2\u05dd \u05d1\u05e9\u05dd \u05d4\u05ea\u05e6\u05d5\u05d2\u05d4 \u05dc\u05d6\u05d9\u05d4\u05d5\u05d9 \u05de\u05e8\u05db\u05d9\u05d1 \u05d6\u05d4.",
    "Enter the number of points possible for this component.  The default value is 1.0.  This setting is only used when Scored is set to True.": "\u05d4\u05d6\u05df \u05d0\u05ea \u05de\u05e1\u05e4\u05e8 \u05d4\u05e0\u05e7\u05d5\u05d3\u05d5\u05ea \u05d4\u05d0\u05e4\u05e9\u05e8\u05d9\u05d5\u05ea \u05dc\u05de\u05e8\u05db\u05d9\u05d1 \u05d6\u05d4.  \u05d1\u05e8\u05d9\u05e8\u05ea \u05d4\u05de\u05d7\u05d3\u05dc \u05d4\u05d9\u05d0 1.0. \u05e0\u05d9\u05ea\u05df \u05dc\u05d4\u05e9\u05ea\u05de\u05e9 \u05d1\u05d4\u05d2\u05d3\u05e8\u05d4 \u05d6\u05d5 \u05d0\u05da \u05d5\u05e8\u05e7 \u05db\u05d0\u05e9\u05e8 '\u05e7\u05d9\u05d1\u05dc \u05e6\u05d9\u05d5\u05df' \u05de\u05d5\u05d2\u05d3\u05e8 \u05db-\u05e0\u05db\u05d5\u05df.",
    "Enter the text on the button used to launch the third party application. This setting is only used when Hide External Tool is set to False and LTI Launch Target is set to Modal or New Window.": "\u05d4\u05d6\u05df \u05d1\u05ea\u05d7\u05ea\u05d9\u05ea \u05d0\u05ea \u05d4\u05d8\u05e7\u05e1\u05d8 \u05d4\u05de\u05e9\u05de\u05e9 \u05dc\u05d4\u05e4\u05e2\u05dc\u05ea \u05d4\u05d0\u05e4\u05dc\u05d9\u05e7\u05e6\u05d9\u05d4 \u05e9\u05dc \u05e6\u05d3 \u05e9\u05dc\u05d9\u05e9\u05d9. \u05e0\u05d9\u05ea\u05df \u05dc\u05d4\u05e9\u05ea\u05de\u05e9 \u05d1\u05d4\u05d2\u05d3\u05e8\u05d4 \u05d6\u05d5 \u05d0\u05da \u05d5\u05e8\u05e7 \u05db\u05d0\u05e9\u05e8 \u05d4\u05d0\u05e4\u05e9\u05e8\u05d5\u05ea '\u05d4\u05e1\u05ea\u05e8 \u05db\u05dc\u05d9 \u05d7\u05d9\u05e6\u05d5\u05e0\u05d9' \u05e0\u05de\u05e6\u05d0\u05ea \u05d1\u05de\u05e6\u05d1 '\u05dc\u05d0 \u05e0\u05db\u05d5\u05df' \u05d5\u05db\u05d0\u05e9\u05e8 LTI Launch Target \u05de\u05d5\u05d2\u05d3\u05e8 \u05db-Modal \u05d0\u05d5 \u05d7\u05dc\u05d5\u05df \u05d7\u05d3\u05e9.",
    "Hide External Tool": "\u05d4\u05e1\u05ea\u05e8 \u05db\u05dc\u05d9 \u05d7\u05d9\u05e6\u05d5\u05e0\u05d9",
    "Inline Height": "\u05d2\u05d5\u05d1\u05d4 \u05d4-inline",
    "LTI Application Information": "\u05de\u05d9\u05d3\u05e2 \u05d0\u05d5\u05d3\u05d5\u05ea \u05d0\u05e4\u05dc\u05d9\u05e7\u05e6\u05d9\u05d9\u05ea LTI",
    "LTI Consumer": "\u05e6\u05e8\u05db\u05df LTI",
    "LTI ID": "\u05de\u05d6\u05d4\u05d4 LTI",
    "LTI Launch Target": "\u05d9\u05e2\u05d3 \u05d4\u05e9\u05e7\u05ea LTI",
    "LTI URL": "\u05db\u05ea\u05d5\u05d1\u05ea \u05d4-URL \u05e9\u05dc LTI",
    "Modal Height": "\u05d2\u05d5\u05d1\u05d4 \u05d4-Modal",
    "Modal Width": "\u05e8\u05d5\u05d7\u05d1 \u05d4-Modal",
    "No valid user id found in endpoint URL": "\u05dc\u05d0 \u05e0\u05de\u05e6\u05d0 \u05de\u05d6\u05d4\u05d4 \u05de\u05e9\u05ea\u05de\u05e9 \u05ea\u05e7\u05e3 \u05d1\u05db\u05ea\u05d5\u05d1\u05ea \u05d4-URL \u05d4\u05e1\u05d5\u05e4\u05d9\u05ea",
    "Request user's email": "\u05d1\u05e7\u05e9 \u05d0\u05ea \u05db\u05ea\u05d5\u05d1\u05ea \u05d4\u05d3\u05d5\u05d0\u05f4\u05dc \u05e9\u05dc \u05d4\u05de\u05e9\u05ea\u05de\u05e9",
    "Request user's username": "\u05d1\u05e7\u05e9 \u05d0\u05ea \u05e9\u05dd \u05d4\u05de\u05e9\u05ea\u05de\u05e9 \u05e9\u05dc \u05d4\u05de\u05e9\u05ea\u05de\u05e9",
    "Scored": "\u05e7\u05d9\u05d1\u05dc \u05e6\u05d9\u05d5\u05df",
    "Select Inline if you want the LTI content to open in an IFrame in the current page. Select Modal if you want the LTI content to open in a modal window in the current page. Select New Window if you want the LTI content to open in a new browser window. This setting is only used when Hide External Tool is set to False.": "\u05d1\u05d7\u05e8 \u05d0\u05ea \u05d4\u05d0\u05e4\u05e9\u05e8\u05d5\u05ea Inline \u05d0\u05dd \u05d1\u05e8\u05e6\u05d5\u05e0\u05da \u05e9\u05ea\u05d5\u05db\u05df \u05d4-LTI \u05d9\u05e4\u05ea\u05d7 \u05d1\u05e2\u05de\u05d5\u05d3 \u05d4\u05e0\u05d5\u05db\u05d7\u05d9 \u05d1- IFrame. \u05d1\u05d7\u05e8 \u05d0\u05ea \u05d4\u05d0\u05e4\u05e9\u05e8\u05d5\u05ea Modal \u05d0\u05dd \u05d1\u05e8\u05e6\u05d5\u05e0\u05da \u05e9\u05ea\u05d5\u05db\u05df \u05d4-LTI \u05d9\u05e4\u05ea\u05d7 \u05d1\u05e2\u05de\u05d5\u05d3 \u05d4\u05e0\u05d5\u05db\u05d7\u05d9 \u05d1\u05d7\u05dc\u05d5\u05df Modal. \u05d1\u05d7\u05e8 \u05d0\u05ea \u05d4\u05d0\u05e4\u05e9\u05e8\u05d5\u05ea New Window \u05d0\u05dd \u05d1\u05e8\u05e6\u05d5\u05e0\u05da \u05e9\u05ea\u05d5\u05db\u05df \u05d4-LTI \u05d9\u05e4\u05ea\u05d7 \u05d1\u05d7\u05dc\u05d5\u05df \u05d3\u05e4\u05d3\u05e4\u05df \u05d7\u05d3\u05e9. \u05e0\u05d9\u05ea\u05df \u05dc\u05d4\u05e9\u05ea\u05de\u05e9 \u05d1\u05d4\u05d2\u05d3\u05e8\u05d4 \u05d6\u05d5 \u05d0\u05da \u05d5\u05e8\u05e7 \u05db\u05d0\u05e9\u05e8 \u05d4\u05d0\u05e4\u05e9\u05e8\u05d5\u05ea '\u05d4\u05e1\u05ea\u05e8 \u05db\u05dc\u05d9 \u05d7\u05d9\u05e6\u05d5\u05e0\u05d9' \u05e0\u05de\u05e6\u05d0\u05ea \u05d1\u05de\u05e6\u05d1 '\u05dc\u05d0 \u05e0\u05db\u05d5\u05df'.",
    "Select True if this component will receive a numerical score from the external LTI system.": "\u05d1\u05d7\u05e8 \u05d1\u05d0\u05e4\u05e9\u05e8\u05d5\u05ea \u05e0\u05db\u05d5\u05df \u05d0\u05dd \u05de\u05e8\u05db\u05d9\u05d1 \u05d6\u05d4 \u05d9\u05e7\u05d1\u05dc \u05e6\u05d9\u05d5\u05df \u05de\u05e1\u05e4\u05e8\u05d9 \u05de\u05de\u05e2\u05e8\u05db\u05ea \u05d4-LTI \u05d4\u05d7\u05d9\u05e6\u05d5\u05e0\u05d9\u05ea.",
    "Select True if you want to use this component as a placeholder for syncing with an external grading  system rather than launch an external tool.  This setting hides the Launch button and any IFrames for this component.": "\u05d1\u05d7\u05e8 \u05d1\u05d0\u05e4\u05e9\u05e8\u05d5\u05ea '\u05e0\u05db\u05d5\u05df' \u05d0\u05dd \u05d1\u05e8\u05e6\u05d5\u05e0\u05da \u05dc\u05d4\u05e9\u05ea\u05de\u05e9 \u05d1\u05de\u05e8\u05db\u05d9\u05d1 \u05d6\u05d4 \u05db\u05e9\u05d5\u05de\u05e8 \u05de\u05e7\u05d5\u05dd \u05e2\u05d1\u05d5\u05e8 \u05e1\u05e0\u05db\u05e8\u05d5\u05df \u05e2\u05dd \u05de\u05e2\u05e8\u05db\u05ea \u05e6\u05d9\u05d5\u05e0\u05d9\u05dd \u05d7\u05d9\u05e6\u05d5\u05e0\u05d9\u05ea \u05d1\u05de\u05e7\u05d5\u05dd \u05dc\u05d4\u05e4\u05e2\u05d9\u05dc \u05db\u05dc\u05d9 \u05d7\u05d9\u05e6\u05d5\u05e0\u05d9.  \u05d4\u05d2\u05d3\u05e8\u05d4 \u05d6\u05d5 \u05de\u05e1\u05ea\u05d9\u05e8\u05d4 \u05d0\u05ea \u05dc\u05d7\u05e6\u05df '\u05d4\u05e4\u05e2\u05dc' \u05d5\u05db\u05dc IFrames \u05e2\u05d1\u05d5\u05e8 \u05de\u05e8\u05db\u05d9\u05d1 \u05d6\u05d4.",
    "Select True to allow third party systems to post grades past the deadline.": "\u05d1\u05d7\u05e8 \u05d1\u05d0\u05e4\u05e9\u05e8\u05d5\u05ea '\u05e0\u05db\u05d5\u05df' \u05e2\u05dc \u05de\u05e0\u05ea \u05dc\u05d0\u05e4\u05e9\u05e8 \u05dc\u05de\u05e2\u05e8\u05db\u05d5\u05ea \u05e6\u05d3 \u05e9\u05dc\u05d9\u05e9\u05d9 \u05dc\u05e4\u05e8\u05e1\u05dd \u05e6\u05d9\u05d5\u05e0\u05d9\u05dd \u05dc\u05d0\u05d7\u05e8 \u05d4\u05de\u05d5\u05e2\u05d3 \u05d4\u05e1\u05d5\u05e4\u05d9.",
    "Select True to request the user's email address.": "\u05d1\u05d7\u05e8 \u05d1\u05d0\u05e4\u05e9\u05e8\u05d5\u05ea '\u05e0\u05db\u05d5\u05df' \u05e2\u05dc \u05de\u05e0\u05ea \u05dc\u05d1\u05e7\u05e9 \u05d0\u05ea \u05db\u05ea\u05d5\u05d1\u05ea \u05d3\u05d5\u05d0\u05f4\u05dc \u05d4\u05de\u05e9\u05ea\u05de\u05e9.",
    "Select True to request the user's username.": "\u05d1\u05d7\u05e8 \u05d1\u05d0\u05e4\u05e9\u05e8\u05d5\u05ea '\u05e0\u05db\u05d5\u05df' \u05e2\u05dc \u05de\u05e0\u05ea \u05dc\u05d1\u05e7\u05e9 \u05d0\u05ea \u05e9\u05dd \u05d4\u05de\u05e9\u05ea\u05de\u05e9 \u05e9\u05dc \u05d4\u05de\u05e9\u05ea\u05de\u05e9.",
    "The score kept in the xblock KVS -- duplicate of the published score in django DB": "\u05d4\u05e6\u05d9\u05d5\u05df \u05e0\u05e9\u05de\u05e8 \u05d1- xblock KVS \u2013 \u05e9\u05db\u05e4\u05d5\u05dc \u05d4\u05e6\u05d9\u05d5\u05df \u05d4\u05de\u05e4\u05d5\u05e8\u05e1\u05dd \u05d1-django DB",
    "[LTI]: Real user not found against anon_id: {}": "[LTI]: \u05dc\u05d0 \u05e0\u05de\u05e6\u05d0 \u05de\u05e9\u05ea\u05de\u05e9 \u05d0\u05de\u05d9\u05ea\u05d9 \u05de\u05d5\u05dc anon_id: {}"
  };
  for (const key in newcatalog) {
    django.catalog[key] = newcatalog[key];
  }
  

  if (!django.jsi18n_initialized) {
    django.gettext = function(msgid) {
      const value = django.catalog[msgid];
      if (typeof value === 'undefined') {
        return msgid;
      } else {
        return (typeof value === 'string') ? value : value[0];
      }
    };

    django.ngettext = function(singular, plural, count) {
      const value = django.catalog[singular];
      if (typeof value === 'undefined') {
        return (count == 1) ? singular : plural;
      } else {
        return value.constructor === Array ? value[django.pluralidx(count)] : value;
      }
    };

    django.gettext_noop = function(msgid) { return msgid; };

    django.pgettext = function(context, msgid) {
      let value = django.gettext(context + '\x04' + msgid);
      if (value.includes('\x04')) {
        value = msgid;
      }
      return value;
    };

    django.npgettext = function(context, singular, plural, count) {
      let value = django.ngettext(context + '\x04' + singular, context + '\x04' + plural, count);
      if (value.includes('\x04')) {
        value = django.ngettext(singular, plural, count);
      }
      return value;
    };

    django.interpolate = function(fmt, obj, named) {
      if (named) {
        return fmt.replace(/%\(\w+\)s/g, function(match){return String(obj[match.slice(2,-2)])});
      } else {
        return fmt.replace(/%s/g, function(match){return String(obj.shift())});
      }
    };


    /* formatting library */

    django.formats = {
    "DATETIME_FORMAT": "j \u05d1F Y H:i",
    "DATETIME_INPUT_FORMATS": [
      "%Y-%m-%d %H:%M:%S",
      "%Y-%m-%d %H:%M:%S.%f",
      "%Y-%m-%d %H:%M",
      "%m/%d/%Y %H:%M:%S",
      "%m/%d/%Y %H:%M:%S.%f",
      "%m/%d/%Y %H:%M",
      "%m/%d/%y %H:%M:%S",
      "%m/%d/%y %H:%M:%S.%f",
      "%m/%d/%y %H:%M"
    ],
    "DATE_FORMAT": "j \u05d1F Y",
    "DATE_INPUT_FORMATS": [
      "%Y-%m-%d",
      "%m/%d/%Y",
      "%m/%d/%y",
      "%b %d %Y",
      "%b %d, %Y",
      "%d %b %Y",
      "%d %b, %Y",
      "%B %d %Y",
      "%B %d, %Y",
      "%d %B %Y",
      "%d %B, %Y"
    ],
    "DECIMAL_SEPARATOR": ".",
    "FIRST_DAY_OF_WEEK": 0,
    "MONTH_DAY_FORMAT": "j \u05d1F",
    "NUMBER_GROUPING": 0,
    "SHORT_DATETIME_FORMAT": "d/m/Y H:i",
    "SHORT_DATE_FORMAT": "d/m/Y",
    "THOUSAND_SEPARATOR": ",",
    "TIME_FORMAT": "H:i",
    "TIME_INPUT_FORMATS": [
      "%H:%M:%S",
      "%H:%M:%S.%f",
      "%H:%M"
    ],
    "YEAR_MONTH_FORMAT": "F Y"
  };

    django.get_format = function(format_type) {
      const value = django.formats[format_type];
      if (typeof value === 'undefined') {
        return format_type;
      } else {
        return value;
      }
    };

    /* add to global namespace */
    globals.pluralidx = django.pluralidx;
    globals.gettext = django.gettext;
    globals.ngettext = django.ngettext;
    globals.gettext_noop = django.gettext_noop;
    globals.pgettext = django.pgettext;
    globals.npgettext = django.npgettext;
    globals.interpolate = django.interpolate;
    globals.get_format = django.get_format;

    django.jsi18n_initialized = true;
  }
};


                  }
                };
                XBlockLtiConsumerI18N.init();
                global.XBlockLtiConsumerI18N = XBlockLtiConsumerI18N;
            }(this));
        