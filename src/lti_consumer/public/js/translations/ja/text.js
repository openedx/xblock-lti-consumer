
            (function(global){
                var XBlockLtiConsumerI18N = {
                  init: function() {
                    

'use strict';
{
  const globals = this;
  const django = globals.django || (globals.django = {});

  
  django.pluralidx = function(n) {
    const v = 0;
    if (typeof v === 'boolean') {
      return v ? 1 : 0;
    } else {
      return v;
    }
  };
  

  /* gettext library */

  django.catalog = django.catalog || {};
  
  const newcatalog = {
    "Accept grades past deadline": "\u7de0\u5207\u3092\u904e\u304e\u305f\u63a1\u70b9\u3092\u53d7\u7406\u3059\u308b",
    "Add the key/value pair for any custom parameters, such as the page your e-book should open to or the background color for this component. Ex. [\"page=1\", \"color=white\"]<br />See the {docs_anchor_open}edX LTI documentation{anchor_close} for more details on this setting.": "\u30ab\u30b9\u30bf\u30e0\u30d1\u30e9\u30e1\u30fc\u30bf\u7528\u306e\u30ad\u30fc\uff0f\u5024\u306e\u30da\u30a2\u3092\u8ffd\u52a0\u3057\u3066\u304f\u3060\u3055\u3044\u3002\u30d1\u30e9\u30e1\u30fc\u30bf\u306e\u4f8b\u3068\u3057\u3066\u306f\u3001e-book\u3067\u958b\u304f\u30da\u30fc\u30b8\u3084\u3001\u3053\u306e\u30b3\u30f3\u30dd\u30fc\u30cd\u30f3\u30c8\u306e\u80cc\u666f\u8272\u306a\u3069\u304c\u3042\u308a\u307e\u3059\u3002\u4f8b\u3001[\"page=1\", \"color=white\"]<br />\u8a73\u7d30\u306f{docs_anchor_open}edX LTI\u30c9\u30ad\u30e5\u30e1\u30f3\u30c8{anchor_close}\u3092\u53c2\u7167\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
    "Button Text": "\u30dc\u30bf\u30f3\u30c6\u30ad\u30b9\u30c8",
    "Comment as returned from grader, LTI2.0 spec": "LTI2.0 spec\u306e\u63a1\u70b9\u8005\u304b\u3089\u306e\u30b3\u30e1\u30f3\u30c8",
    "Could not get user id for current request": "\u73fe\u5728\u306e\u8981\u6c42\u306e\u30e6\u30fc\u30b6\u30fcID\u3092\u53d6\u5f97\u3067\u304d\u307e\u305b\u3093\u3067\u3057\u305f",
    "Custom Parameters": "\u30ab\u30b9\u30bf\u30e0\u30d1\u30e9\u30e1\u30fc\u30bf",
    "Display Name": "\u8868\u793a\u540d",
    "Enter a description of the third party application. If requesting username and/or email, use this text box to inform users why their username and/or email will be forwarded to a third party application.": "\u30b5\u30fc\u30c9\u30d1\u30fc\u30c6\u30a3\u30fc\u88fd\u30a2\u30d7\u30ea\u30b1\u30fc\u30b7\u30e7\u30f3\u306b\u3064\u3044\u3066\u306e\u8a18\u8ff0\u3092\u5165\u529b\u3057\u307e\u3059\u3002\u30e6\u30fc\u30b6\u30fc\u540d\u3084\u30e1\u30fc\u30eb\u30a2\u30c9\u30ec\u30b9\u306e\u5165\u529b\u3092\u6c42\u3081\u308b\u5834\u5408\u306f\u3001\u3053\u306e\u30c6\u30ad\u30b9\u30c8\u30dc\u30c3\u30af\u30b9\u306b\u306a\u305c\u30e6\u30fc\u30b6\u30fc\u540d\u3084\u30e1\u30fc\u30eb\u30a2\u30c9\u30ec\u30b9\u306e\u5165\u529b\u304c\u5fc5\u8981\u306a\u306e\u304b\u3001\u307e\u305f\u305d\u308c\u3089\u304c\u30b5\u30fc\u30c9\u30d1\u30fc\u30c6\u30a3\u88fd\u30a2\u30d7\u30ea\u30b1\u30fc\u30b7\u30e7\u30f3\u306b\u8ee2\u9001\u3055\u308c\u308b\u3053\u3068\u3092\u77e5\u3089\u305b\u3066\u304f\u3060\u3055\u3044\u3002",
    "Enter the LTI ID for the external LTI provider. This value must be the same LTI ID that you entered in the LTI Passports setting on the Advanced Settings page.<br />See the {docs_anchor_open}edX LTI documentation{anchor_close} for more details on this setting.": "\u5916\u90e8\u306eLTI\u30d7\u30ed\u30d0\u30a4\u30c0\u30fc\u7528\u306eLTI ID\u3092\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044\u3002\u3053\u306e\u5024\u306f\u8a73\u7d30\u8a2d\u5b9a\u30da\u30fc\u30b8\u306eLTI\u30d1\u30b9\u30dd\u30fc\u30c8\u306b\u5165\u529b\u3055\u308c\u305f\u3082\u306e\u3068\u540c\u3058\u3067\u3042\u308b\u5fc5\u8981\u304c\u3042\u308a\u307e\u3059\u3002<br />\u8a73\u7d30\u306f{docs_anchor_open}edX LTI\u30c9\u30ad\u30e5\u30e1\u30f3\u30c8{anchor_close}\u3092\u53c2\u7167\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
    "Enter the URL of the external tool that this component launches. This setting is only used when Hide External Tool is set to False.<br />See the {docs_anchor_open}edX LTI documentation{anchor_close} for more details on this setting.": "\u3053\u306e\u30b3\u30f3\u30dd\u30fc\u30cd\u30f3\u30c8\u304c\u8d77\u52d5\u3059\u308b\u5916\u90e8\u30c4\u30fc\u30eb\u306eURL\u3092\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044\u3002\u3053\u306e\u8a2d\u5b9a\u306f\u5916\u90e8\u30c4\u30fc\u30eb\u975e\u8868\u793a\u8a2d\u5b9a\u3092False\u306b\u3057\u305f\u6642\u306e\u307f\u4f7f\u7528\u3055\u308c\u307e\u3059\u3002<br />\u8a73\u7d30\u306f{docs_anchor_open}edX LTI\u30c9\u30ad\u30e5\u30e1\u30f3\u30c8{anchor_close}\u3092\u53c2\u7167\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
    "Enter the desired pixel height of the iframe which will contain the LTI tool. This setting is only used when Hide External Tool is set to False and LTI Launch Target is set to Inline.": "LTI\u30c4\u30fc\u30eb\u304c\u542b\u307e\u308c\u308biframe\u306e\u30d4\u30af\u30bb\u30eb\u306e\u9ad8\u3055\u3092\u5165\u529b\u3057\u307e\u3059\u3002\u3053\u308c\u306f\u3001\u5916\u90e8\u30c4\u30fc\u30eb\u3092\u975e\u8868\u793a\u306b\u3059\u308b\u8a2d\u5b9a\u3092False\u306b\u3057\u3001LTI\u8d77\u52d5\u30bf\u30fc\u30b2\u30c3\u30c8\u3092\u30a4\u30f3\u30e9\u30a4\u30f3\u306b\u8a2d\u5b9a\u3057\u3066\u3044\u308b\u5834\u5408\u306b\u306e\u307f\u4f7f\u7528\u3055\u308c\u307e\u3059\u3002",
    "Enter the desired viewport percentage height of the modal overlay which will contain the LTI tool. This setting is only used when Hide External Tool is set to False and LTI Launch Target is set to Modal.": "LTI\u30c4\u30fc\u30eb\u3092\u542b\u3080\u30e2\u30fc\u30c0\u30eb\u30aa\u30fc\u30d0\u30fc\u30ec\u30a4\u306e\u5fc5\u8981\u306a\u30d3\u30e5\u30fc\u30dd\u30fc\u30c8\u306e\u30d1\u30fc\u30bb\u30f3\u30c6\u30fc\u30b8\u306e\u9ad8\u3055\u3092\u5165\u529b\u3057\u307e\u3059\u3002\u3053\u308c\u306f\u3001\u5916\u90e8\u30c4\u30fc\u30eb\u3092\u975e\u8868\u793a\u306b\u3059\u308b\u8a2d\u5b9a\u3092False\u306b\u3057\u3001LTI\u8d77\u52d5\u30bf\u30fc\u30b2\u30c3\u30c8\u3092\u30e2\u30fc\u30c0\u30eb\u306b\u8a2d\u5b9a\u3057\u3066\u3044\u308b\u5834\u5408\u306b\u306e\u307f\u4f7f\u7528\u3055\u308c\u307e\u3059\u3002",
    "Enter the desired viewport percentage width of the modal overlay which will contain the LTI tool. This setting is only used when Hide External Tool is set to False and LTI Launch Target is set to Modal.": "LTI\u30c4\u30fc\u30eb\u3092\u542b\u3080\u30e2\u30fc\u30c0\u30eb\u30aa\u30fc\u30d0\u30fc\u30ec\u30a4\u306e\u5fc5\u8981\u306a\u30d3\u30e5\u30fc\u30dd\u30fc\u30c8\u306e\u30d1\u30fc\u30bb\u30f3\u30c6\u30fc\u30b8\u306e\u5e45\u3092\u5165\u529b\u3057\u307e\u3059\u3002\u3053\u308c\u306f\u3001\u5916\u90e8\u30c4\u30fc\u30eb\u3092\u975e\u8868\u793a\u306b\u3059\u308b\u8a2d\u5b9a\u3092False\u306b\u3057\u3001LTI\u8d77\u52d5\u30bf\u30fc\u30b2\u30c3\u30c8\u3092\u30e2\u30fc\u30c0\u30eb\u306b\u8a2d\u5b9a\u3057\u3066\u3044\u308b\u5834\u5408\u306b\u306e\u307f\u4f7f\u7528\u3055\u308c\u307e\u3059\u3002",
    "Enter the name that students see for this component. Analytics reports may also use the display name to identify this component.": "\u3053\u306e\u30a2\u30a4\u30c6\u30e0\u306e\u305f\u3081\u306e\u53d7\u8b1b\u8005\u306b\u8868\u793a\u3055\u308c\u308b\u540d\u524d\u3092\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044\u3002\u3053\u306e\u540d\u524d\u306f\u3001\u5206\u6790\u30ec\u30dd\u30fc\u30c8\u4f5c\u6210\u6642\u306b\u30a2\u30a4\u30c6\u30e0\u3092\u8b58\u5225\u3059\u308b\u305f\u3081\u306b\u4f7f\u308f\u308c\u307e\u3059\u3002",
    "Enter the number of points possible for this component.  The default value is 1.0.  This setting is only used when Scored is set to True.": "\u3053\u306e\u30a2\u30a4\u30c6\u30e0\u304c\u5b9f\u884c\u3067\u304d\u308b\u30dd\u30a4\u30f3\u30c8\u306e\u6570\u3092\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044\u3002\u30c7\u30d5\u30a9\u30eb\u30c8\u5024\u306f1.0\u3067\u3059\u3002\u3053\u306e\u8a2d\u5b9a\u306f\u3001\u63a1\u70b9\u6e08\u304cTrue\u306e\u6642\u306b\u306e\u307f\u4f7f\u308f\u308c\u307e\u3059\u3002",
    "Enter the text on the button used to launch the third party application. This setting is only used when Hide External Tool is set to False and LTI Launch Target is set to Modal or New Window.": "\u30b5\u30fc\u30c9\u30d1\u30fc\u30c6\u30a3\u88fd\u30a2\u30d7\u30ea\u30b1\u30fc\u30b7\u30e7\u30f3\u306e\u8d77\u52d5\u306b\u4f7f\u7528\u3059\u308b\u30dc\u30bf\u30f3\u306b\u30c6\u30ad\u30b9\u30c8\u3092\u5165\u529b\u3057\u307e\u3059\u3002\u3053\u308c\u306f\u3001\u5916\u90e8\u30c4\u30fc\u30eb\u3092\u975e\u8868\u793a\u306b\u3059\u308b\u8a2d\u5b9a\u3092False\u306b\u3057\u3001LTI\u8d77\u52d5\u30bf\u30fc\u30b2\u30c3\u30c8\u3092\u30e2\u30fc\u30c0\u30eb\u307e\u305f\u306f\u65b0\u3057\u3044\u30a6\u30a3\u30f3\u30c9\u30a6\u306b\u8a2d\u5b9a\u3057\u3066\u3044\u308b\u5834\u5408\u306b\u306e\u307f\u4f7f\u7528\u3055\u308c\u307e\u3059\u3002",
    "Hide External Tool": "\u5916\u90e8\u30c4\u30fc\u30eb\u3092\u96a0\u3059",
    "Inline Height": "\u30a4\u30f3\u30e9\u30a4\u30f3\u9ad8\u3055",
    "LTI Application Information": "LTI\u30a2\u30d7\u30ea\u30b1\u30fc\u30b7\u30e7\u30f3\u306e\u60c5\u5831",
    "LTI Consumer": "LTI\u30b3\u30f3\u30b7\u30e5\u30fc\u30de",
    "LTI ID": "LTI ID",
    "LTI Launch Target": "LTI\u8d77\u52d5\u30bf\u30fc\u30b2\u30c3\u30c8",
    "LTI URL": "LTI URL",
    "Modal Height": "\u30e2\u30fc\u30c0\u30eb\u9ad8\u3055",
    "Modal Width": "\u30e2\u30fc\u30c0\u30eb\u5e45",
    "No valid user id found in endpoint URL": "\u30a8\u30f3\u30c9\u30dd\u30a4\u30f3\u30c8URL\u306b\u6709\u52b9\u306a\u30e6\u30fc\u30b6\u30fcID\u304c\u898b\u3064\u304b\u308a\u307e\u305b\u3093\u3067\u3057\u305f",
    "Request user's email": "\u30e6\u30fc\u30b6\u30fc\u306e\u30e1\u30fc\u30eb\u30a2\u30c9\u30ec\u30b9\u3092\u8981\u6c42\u3059\u308b",
    "Request user's username": "\u30e6\u30fc\u30b6\u30fc\u540d\u3092\u8981\u6c42\u3059\u308b",
    "Scored": "\u63a1\u70b9\u6e08\u307f",
    "Select Inline if you want the LTI content to open in an IFrame in the current page. Select Modal if you want the LTI content to open in a modal window in the current page. Select New Window if you want the LTI content to open in a new browser window. This setting is only used when Hide External Tool is set to False.": "LTI\u30b3\u30f3\u30c6\u30f3\u30c4\u3092\u73fe\u5728\u306e\u30da\u30fc\u30b8\u306eIFrame\u3067\u958b\u304f\u5834\u5408\u306f\u3001\u30a4\u30f3\u30e9\u30a4\u30f3\u3092\u9078\u629e\u3057\u307e\u3059\u3002LTI\u30b3\u30f3\u30c6\u30f3\u30c4\u3092\u73fe\u5728\u306e\u30da\u30fc\u30b8\u306e\u30e2\u30fc\u30c0\u30eb\u30a6\u30a3\u30f3\u30c9\u30a6\u3067\u958b\u304f\u5834\u5408\u306f\u3001\u30e2\u30fc\u30c0\u30eb\u3092\u9078\u629e\u3057\u307e\u3059\u3002LTI\u30b3\u30f3\u30c6\u30f3\u30c4\u3092\u65b0\u3057\u3044\u30d6\u30e9\u30a6\u30b6\u30fc\u30a6\u30a3\u30f3\u30c9\u30a6\u3067\u958b\u304f\u5834\u5408\u306f\u3001\u65b0\u3057\u3044\u30a6\u30a3\u30f3\u30c9\u30a6\u3092\u9078\u629e\u3057\u307e\u3059\u3002\u3053\u308c\u306f\u3001\u5916\u90e8\u30c4\u30fc\u30eb\u3092\u975e\u8868\u793a\u306b\u3059\u308b\u8a2d\u5b9a\u3092False\u306b\u3057\u3066\u3044\u308b\u5834\u5408\u306b\u306e\u307f\u4f7f\u7528\u3055\u308c\u307e\u3059\u3002",
    "Select True if this component will receive a numerical score from the external LTI system.": "\u3053\u306e\u30a2\u30a4\u30c6\u30e0\u304c\u5916\u90e8\u306eLTI\u30b7\u30b9\u30c6\u30e0\u304b\u3089\u6570\u5024\u3092\u53d7\u3051\u53d6\u308b\u5834\u5408\u306fTrue\u3092\u9078\u629e\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
    "Select True if you want to use this component as a placeholder for syncing with an external grading  system rather than launch an external tool.  This setting hides the Launch button and any IFrames for this component.": "\u5916\u90e8\u30c4\u30fc\u30eb\u3092\u8d77\u52d5\u3059\u308b\u306e\u3067\u306f\u306a\u304f\u3001\u5916\u90e8\u306e\u63a1\u70b9\u30b7\u30b9\u30c6\u30e0\u3068\u540c\u671f\u3059\u308b\u305f\u3081\u306e\u4ee3\u7528\u3068\u3057\u3066\u3053\u306e\u30a2\u30a4\u30c6\u30e0\u3092\u4f7f\u7528\u3059\u308b\u5834\u5408\u306f\u3001True\u3092\u9078\u629e\u3057\u3066\u304f\u3060\u3055\u3044\u3002\u3053\u306e\u8a2d\u5b9a\u306b\u3088\u308a\u3001\u8d77\u52d5\u30dc\u30bf\u30f3\u3068\u3001\u3053\u306e\u30a2\u30a4\u30c6\u30e0\u7528\u306eIFrame\u306f\u975e\u8868\u793a\u306b\u306a\u308a\u307e\u3059\u3002",
    "Select True to allow third party systems to post grades past the deadline.": "\u30b5\u30fc\u30c9\u30d1\u30fc\u30c6\u30a3\u30fc\u88fd\u30b7\u30b9\u30c6\u30e0\u3067\u7de0\u5207\u3092\u904e\u304e\u305f\u63a1\u70b9\u306e\u6295\u7a3f\u3092\u8a31\u53ef\u3059\u308b\u306b\u306fTrue\u3092\u9078\u629e\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
    "Select True to request the user's email address.": "\u30e6\u30fc\u30b6\u30fc\u306e\u30e1\u30fc\u30eb\u30a2\u30c9\u30ec\u30b9\u3092\u8981\u6c42\u3059\u308b\u5834\u5408\u306f\u3001True\u3092\u9078\u629e\u3057\u307e\u3059\u3002",
    "Select True to request the user's username.": "\u30e6\u30fc\u30b6\u30fc\u540d\u3092\u8981\u6c42\u3059\u308b\u5834\u5408\u306f\u3001True\u3092\u9078\u629e\u3057\u307e\u3059\u3002",
    "The score kept in the xblock KVS -- duplicate of the published score in django DB": "xblock KVS\u306e\u5f97\u70b9 -- django DB\u4e2d\u306e\u516c\u958b\u5f97\u70b9\u306e\u8907\u88fd",
    "[LTI]: Real user not found against anon_id: {}": "[LTI]: anon_id\u306b\u5bfe\u3057\u3066\u5b9f\u969b\u306e\u30e6\u30fc\u30b6\u30fc\u304c\u898b\u3064\u304b\u308a\u307e\u305b\u3093\u3067\u3057\u305f: {}"
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
    "DATETIME_FORMAT": "Y\u5e74n\u6708j\u65e5G:i",
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
    "DATE_FORMAT": "Y\u5e74n\u6708j\u65e5",
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
    "MONTH_DAY_FORMAT": "n\u6708j\u65e5",
    "NUMBER_GROUPING": 0,
    "SHORT_DATETIME_FORMAT": "Y/m/d G:i",
    "SHORT_DATE_FORMAT": "Y/m/d",
    "THOUSAND_SEPARATOR": ",",
    "TIME_FORMAT": "G:i",
    "TIME_INPUT_FORMATS": [
      "%H:%M:%S",
      "%H:%M:%S.%f",
      "%H:%M"
    ],
    "YEAR_MONTH_FORMAT": "Y\u5e74n\u6708"
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
        