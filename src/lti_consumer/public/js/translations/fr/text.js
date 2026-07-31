
            (function(global){
                var XBlockLtiConsumerI18N = {
                  init: function() {
                    

'use strict';
{
  const globals = this;
  const django = globals.django || (globals.django = {});

  
  django.pluralidx = function(n) {
    const v = (n == 0 || n == 1) ? 0 : n != 0 && n % 1000000 == 0 ? 1 : 2;
    if (typeof v === 'boolean') {
      return v ? 1 : 0;
    } else {
      return v;
    }
  };
  

  /* gettext library */

  django.catalog = django.catalog || {};
  
  const newcatalog = {
    "Accept grades past deadline": "Accepter les notes apr\u00e8s la date limite",
    "Access Token URL: ": "URL du jeton d'acc\u00e8s\u00a0:",
    "Add the key/value pair for any custom parameters, such as the page your e-book should open to or the background color for this component. Ex. [\"page=1\", \"color=white\"]<br />See the {docs_anchor_open}edX LTI documentation{anchor_close} for more details on this setting.": "Ajoutez la paire cl\u00e9 / valeur pour tous les param\u00e8tres personnalis\u00e9s, tels que la page que votre livre \u00e9lectronique doit ouvrir ou la couleur d'arri\u00e8re-plan de ce composant. Ex. [\"page=1\", \"color=white\"]<br />Voir {docs_anchor_open}edX LTI documentation{anchor_close} pour plus de d\u00e9tails sur ce param\u00e8tre.",
    "Allow tools to manage and submit grade (programmatic)": "Autoriser les outils \u00e0 g\u00e9rer et soumettre la note (programmatique)",
    "Allow tools to submit grades only (declarative)": "Autoriser les outils \u00e0 soumettre des notes uniquement (d\u00e9claratif)",
    "Button Text": "Texte du bouton",
    "Client ID used by LTI tool": "ID Client utilis\u00e9 par l'outil LTI",
    "Client ID: ": "ID Client :",
    "Client key provided by the LTI tool provider.": "Cl\u00e9 client fournie par le fournisseur d'outils LTI.",
    "Client secret provided by the LTI tool provider.": "Secret client fourni par le fournisseur d'outils LTI.",
    "Comment as returned from grader, LTI2.0 spec": "Commentaire sous la forme retourn\u00e9 par l'\u00e9valuateur, sp\u00e9cification LTI2.0",
    "Configuration Stored on XBlock fields": "Configuration stock\u00e9e sur les champs du XBlock",
    "Configuration Stored on this model": "Configuration stock\u00e9e sur ce mod\u00e8le",
    "Could not get user id for current request": "Impossible d'obtenir l'ID utilisateur pour la demande en cours",
    "Could not parse LTI passport: {lti_passport!r}. Should be \"id:key:secret\" string.": "Impossible d'analyser le passeport LTI : {lti_passport!r}. Devrait \u00eatre une cha\u00eene \"id:key:secret\".",
    "Could not parse custom parameter: {custom_parameter!r}. Should be \"x=y\" string.": "Impossible d'analyser le param\u00e8tre personnalis\u00e9: {custom_parameter!r}. Doit \u00eatre une cha\u00eene \"x=y\".",
    "Custom Parameters": "Param\u00e8tres personnalis\u00e9s",
    "Custom Parameters must be a list": "Les param\u00e8tres personnalis\u00e9s doivent \u00eatre une liste",
    "DEPRECATED - This is now stored in the LtiConfiguration model.": "OBSOL\u00c8TE - Ceci est maintenant stock\u00e9 dans le mod\u00e8le LtiConfiguration.",
    "Deep Linking Launch - Configure tool": "Lancement de Deep Linking - Configuration de l'outil",
    "Deep Linking Launch URL": "URL de lancement Deep Linking",
    "Deep Linking is configured on this tool.": "Deep Linking est configur\u00e9 pour cet outil.",
    "Deep linking": "Deep linking",
    "Deployment ID: ": "ID de d\u00e9ploiement :",
    "Disabled": "D\u00e9sactiv\u00e9",
    "Display Name": "Nom d'affichage",
    "Enable LTI NRPS": "Activer LTI NRPS",
    "Enable LTI Names and Role Provisioning Services.": "Activez les LTI Names et les services de provisionnement de r\u00f4les.",
    "Enable the LTI-AGS service and select the functionality enabled for LTI tools. The 'declarative' mode (default) will provide a tool with a LineItem created from the XBlock settings, while the 'programmatic' one will allow tools to manage, create and link the grades.": "Activez le service LTI-AGS et s\u00e9lectionnez la fonctionnalit\u00e9 activ\u00e9e pour les outils LTI. Le mode \"d\u00e9claratif\" (par d\u00e9faut) fournira un outil avec un \u00e9l\u00e9ment de ligne cr\u00e9\u00e9 \u00e0 partir des param\u00e8tres XBlock, tandis que le mode \"programmatique\" permettra aux outils de g\u00e9rer, cr\u00e9er et lier les notes.",
    "Enter a description of the third party application. If requesting username and/or email, use this text box to inform users why their username and/or email will be forwarded to a third party application.": "Saisir une description de l'application tierce. Si vous demandez le nom d'utilisateur et/ou le mail, utilisez cette zone de texte pour informer les utilisateurs que leur nom d'utilisateur et/ou le mail seront transmis \u00e0 une application tierce.",
    "Enter the LTI 1.3 Tool Launch URL. <br />This is the URL the LMS will use to launch the LTI Tool.": "Entrez l'URL de lancement de l'outil LTI 1.3. <br /> Il s'agit de l'URL que le LMS utilisera pour lancer l'outil LTI.",
    "Enter the LTI 1.3 Tool OIDC Authorization url (can also be called login or login initiation URL).<br />This is the URL the LMS will use to start a LTI authorization prior to doing the launch request.": "Entrez l'URL d'autorisation OIDC de l'outil LTI 1.3 (peut \u00e9galement \u00eatre appel\u00e9e URL de connexion ou URL d'initiation de connexion).<br /> Il s'agit de l'URL que le LMS utilisera pour d\u00e9marrer une autorisation LTI avant de faire la demande de lancement.",
    "Enter the LTI 1.3 Tool's public key.<br />This is a string that starts with '-----BEGIN PUBLIC KEY-----' and is required so that the LMS can check if the messages and launch requests received have the signature from the tool.<br /><b>This is not required when doing LTI 1.3 Launches without LTI Advantage nor Basic Outcomes requests.</b>": "Entrez la cl\u00e9 publique de l'outil LTI 1.3.<br />Ceci est une cha\u00eene qui commence par '-----BEGIN PUBLIC KEY-----' et est n\u00e9cessaire pour que le LMS puisse v\u00e9rifier si les messages et demandes de lancement re\u00e7us ont la signature de l'outil.<br /><b>Cela n'est pas n\u00e9cessaire lors des lancements LTI 1.3 sans LTI Advantage ni demandes Basic Outcomes.</b>",
    "Enter the LTI Advantage Deep Linking Launch URL. If the tool does not specify one, use the same value as 'Tool Launch URL'.": "Saisissez l'URL de lancement LTI Advantage Deep Linking. Si l'outil n'en sp\u00e9cifie pas, utilisez la m\u00eame valeur que \u00ab URL de lancement de l'outil \u00bb.",
    "Enter the LTI ID for the external LTI provider. This value must be the same LTI ID that you entered in the LTI Passports setting on the Advanced Settings page.<br />See the {docs_anchor_open}edX LTI documentation{anchor_close} for more details on this setting.": "Entrez l'ID LTI du fournisseur LTI externe. Cette valeur doit \u00eatre identique \u00e0 l'ID LTI que vous avez entr\u00e9 dans le param\u00e8tre LTI Passports de la page des param\u00e8tres avanc\u00e9s.<br />Voir {docs_anchor_open}edX LTI documentation{anchor_close} pour plus de d\u00e9tails sur ce param\u00e8tre.",
    "Enter the URL of the external tool that this component launches. This setting is only used when Hide External Tool is set to False.<br />See the {docs_anchor_open}edX LTI documentation{anchor_close} for more details on this setting.": "Entrez l'URL de l'outil externe que ce composant lance. Ce param\u00e8tre est uniquement utilis\u00e9 lorsque l'option Masquer l'outil externe est d\u00e9finie sur False.<br />Voir {docs_anchor_open}edX LTI documentation{anchor_close} pour plus de d\u00e9tails sur ce param\u00e8tre.",
    "Enter the desired pixel height of the iframe which will contain the LTI tool. This setting is only used when Hide External Tool is set to False and LTI Launch Target is set to Inline.": "Entrez la hauteur de pixel souhait\u00e9e de l'iframe qui contiendra l'outil LTI. Ce param\u00e8tre est uniquement utilis\u00e9 lorsque masquer l'outil externe est d\u00e9fini sur False et que LTI Launch Target est d\u00e9fini sur Inline.",
    "Enter the desired viewport percentage height of the modal overlay which will contain the LTI tool. This setting is only used when Hide External Tool is set to False and LTI Launch Target is set to Modal.": "Entrez le pourcentage de hauteur de la fen\u00eatre de visualisation de la superposition modale qui contiendra l\u2019outil LTI. Ce param\u00e8tre est uniquement utilis\u00e9 lorsque masquer l'outil externe est d\u00e9fini sur False et que LTI Launch Target est d\u00e9fini sur Modal.",
    "Enter the desired viewport percentage width of the modal overlay which will contain the LTI tool. This setting is only used when Hide External Tool is set to False and LTI Launch Target is set to Modal.": "Entrez le pourcentage de largeur de la fen\u00eatre de superposition modale qui contiendra l\u2019outil LTI. Ce param\u00e8tre est uniquement utilis\u00e9 lorsque masquer l'outil externe est d\u00e9fini sur False et que LTI Launch Target est d\u00e9fini sur Modal.",
    "Enter the name that students see for this component. Analytics reports may also use the display name to identify this component.": "Entrez le nom que les \u00e9tudiants voient pour ce composant. Les rapports d'analyse peuvent \u00e9galement utiliser le nom d'affichage pour identifier ce composant.",
    "Enter the number of points possible for this component.  The default value is 1.0.  This setting is only used when Scored is set to True.": "Entrez le nombre de points possible pour ce composant. La valeur par d\u00e9faut est de 1,0. Ce param\u00e8tre est utilis\u00e9 uniquement lorsque Not\u00e9 est positionn\u00e9 sur Vrai.",
    "Enter the text on the button used to launch the third party application. This setting is only used when Hide External Tool is set to False and LTI Launch Target is set to Modal or New Window.": "Entrez le texte du bouton qui sera utilis\u00e9 pour lancer l'application tierce. Ce param\u00e8tre est utilis\u00e9 uniquement lorsque masquer l'outil externe est d\u00e9fini sur False et que LTI Launch Target est d\u00e9fini sur Modal ou Nouvelle fen\u00eatre.",
    "Hide External Tool": "Cacher l'outil externe",
    "If you run deep linking again, the content above will be replaced.": "Si vous ex\u00e9cutez \u00e0 nouveau Deep Linking, le contenu ci-dessus sera remplac\u00e9.",
    "If you're seeing this on a live course, please contact the course staff.": "Si vous voyez cela sur un cours actif veuillez contacter le personnel du cours.",
    "Inline Height": "Hauteur int\u00e9gr\u00e9",
    "Invalid LTI configuration.": "Configuration LTI non valide.",
    "Invalid token header. No credentials provided.": "En-t\u00eate de jeton non valide. Aucune information d'identification fournie.",
    "Invalid token header. Token string should not contain spaces.": "En-t\u00eate de jeton non valide. La cha\u00eene de jeton ne doit pas contenir d'espaces.",
    "Invalid token signature.": "Signature de jeton non valide.",
    "Keyset URL: ": "Keyset URL : ",
    "LTI 1.3 Block Client ID - DEPRECATED": "LTI 1.3 Block Client ID - OBSOL\u00c8TE",
    "LTI 1.3 Block Key - DEPRECATED": "LTI 1.3 Block Key - OBSOL\u00c8TE",
    "LTI 1.3 Launches can only be performed from the LMS.": "Les lancements LTI 1.3 ne peuvent \u00eatre effectu\u00e9s qu'\u00e0 partir du LMS.",
    "LTI Application Information": "Information sur l'application LTI",
    "LTI Assignment and Grades Service": "Service d'affectation et de notes LTI",
    "LTI Configuration stores on XBlock needs a block location set.": "Les configurations LTI sur stock\u00e9es sur XBlock ont besoin d'un ensemble d'emplacement de bloc.",
    "LTI Consumer": "Client LTI",
    "LTI Deep Linking": "LTI Deep Linking",
    "LTI Deep Linking failed.": "LTI Deep Linking a \u00e9chou\u00e9.",
    "LTI ID": "identifiant LTI",
    "LTI Launch Target": "Lancer la cible LTI",
    "LTI URL": "URL LTI",
    "LTI Version": "Version LTI",
    "LTI configuration data.": "Donn\u00e9es de configuration LTI.",
    "LTI configuration not found.": "Configuration LTI introuvable.",
    "Login URL: ": "URL de connexion\u00a0:",
    "Missing LTI 1.3 authentication token.": "Jeton d'authentification LTI 1.3 manquant.",
    "Modal Height": "Hauteur modale",
    "Modal Width": "Largeur modale",
    "No valid user id found in endpoint URL": "Aucun ID utilisateur valide trouv\u00e9 dans l'URL cible",
    "Platform's generated JWK keyset.": "Jeu de cl\u00e9s JWK g\u00e9n\u00e9r\u00e9 par la plate-forme.",
    "Platform's generated Private key ID": "ID de cl\u00e9 priv\u00e9e g\u00e9n\u00e9r\u00e9 par la plate-forme",
    "Platform's generated Private key. Keep this value secret.": "Cl\u00e9 priv\u00e9e g\u00e9n\u00e9r\u00e9e par la plateforme. Gardez cette valeur secr\u00e8te.",
    "Please check that you have course staff permissions and double check this block's LTI settings.": "Veuillez v\u00e9rifier que vous disposez des autorisations du personnel de cours et rev\u00e9rifier les param\u00e8tres LTI de ce bloc.",
    "Request user's email": "Demander l'e-mail de l'utilisateur",
    "Request user's username": "Demander le nom de l'utilisateur",
    "Scored": "A obtenu",
    "Select Inline if you want the LTI content to open in an IFrame in the current page. Select Modal if you want the LTI content to open in a modal window in the current page. Select New Window if you want the LTI content to open in a new browser window. This setting is only used when Hide External Tool is set to False.": "S\u00e9lectionnez Inline si vous souhaitez que le contenu LTI s'ouvre dans un IFrame de la page en cours. S\u00e9lectionnez Modal si vous souhaitez que le contenu LTI s'ouvre dans une fen\u00eatre modale de la page en cours. S\u00e9lectionnez Nouvelle Fen\u00eatre si vous souhaitez que le contenu LTI s'ouvre dans une nouvelle fen\u00eatre du navigateur. Ce param\u00e8tre est uniquement utilis\u00e9 lorsque l'option masquer l'outil externe est d\u00e9finie sur False.",
    "Select True if this component will receive a numerical score from the external LTI system.": "S\u00e9lectionnez Vrai si ce composant doit recevoir un score num\u00e9rique du syst\u00e8me LTI externe.",
    "Select True if you want to enable LTI Advantage Deep Linking.": "S\u00e9lectionnez Vrai si vous souhaitez activer LTI Advantage Deep Linking.",
    "Select True if you want to use this component as a placeholder for syncing with an external grading  system rather than launch an external tool.  This setting hides the Launch button and any IFrames for this component.": "S\u00e9lectionnez Vrai si vous voulez utiliser ce composant comme un espace r\u00e9serv\u00e9 pour la synchronisation avec un syst\u00e8me de notation externe plut\u00f4t que de lancer un outil externe. Ce param\u00e8tre masque le bouton de lancement ainsi que tous les IFrames pour ce composant.",
    "Select True to allow third party systems to post grades past the deadline.": "S\u00e9lectionner vrai (true) pour permettre aux syst\u00e8mes tierces de poster des notes apr\u00e8s la date limite.",
    "Select True to request the user's email address.": "Choisir vrai (true) afin de demander l'adresse e-mail de l'utilisateur.",
    "Select True to request the user's username.": "Choisir vrai (true) afin de demander le nom d'utilisateur.",
    "Select True to send the extra parameters, which might contain Personally Identifiable Information. The processors are site-wide, please consult the site administrator if you have any questions.": "S\u00e9lectionnez Vrai pour envoyer les param\u00e8tres suppl\u00e9mentaires, qui peuvent contenir des informations personnellement identifiables. Les processeurs sont \u00e0 l'\u00e9chelle du site, veuillez consulter l'administrateur du site si vous avez des questions.",
    "Select the LTI version that your tool supports.<br />The XBlock LTI Consumer fully supports LTI 1.1.1, LTI 1.3 and LTI Advantage features.": "S\u00e9lectionnez la version LTI prise en charge par votre outil.<br />Le consommateur XBlock LTI prend enti\u00e8rement en charge les fonctionnalit\u00e9s LTI 1.1.1, LTI 1.3 et LTI Advantage.",
    "Send extra parameters": "Envoyer des param\u00e8tres suppl\u00e9mentaires",
    "Students don't have permissions to perform LTI Deep Linking configuration launches.": "Les \u00e9tudiants ne sont pas autoris\u00e9s \u00e0 effectuer des lancements de configuration LTI Deep Linking.",
    "The Deep Linking configuration stored is presented below:": "La configuration de Deep Linking stock\u00e9e est pr\u00e9sent\u00e9e ci-dessous :",
    "The LTI Deep Linking content was successfully saved in the LMS.": "Le contenu LTI Deep Linking a \u00e9t\u00e9 enregistr\u00e9 avec succ\u00e8s dans le LMS.",
    "The URL of the external tool that initiates the launch.": "L'URL de l'outil externe qui initie le lancement.",
    "The score kept in the xblock KVS -- duplicate of the published score in django DB": "Le score conserv\u00e9 dans le xBlock KVS - duplicata du score publi\u00e9 dans django DB",
    "The selected content type is not supported by Open edX.": "Le type de contenu s\u00e9lectionn\u00e9 n'est pas pris en charge par Open edX.",
    "To do that, make sure the block is published and click the link below:": "Pour ce faire, assurez-vous que le bloc est publi\u00e9 et cliquez sur le lien ci-dessous :",
    "To set up the LTI integration, you need to register the LMS in the tool with the information provided below.": "Pour configurer l'int\u00e9gration LTI, vous devez enregistrer le LMS dans l'outil avec les informations fournies ci-dessous.",
    "Tool Initiate Login URL": "URL d'ouverture de session de l'outil",
    "Tool Launch URL": "URL de lancement de l'outil",
    "Tool Public Key": "Cl\u00e9 publique de l'outil",
    "Unauthorized.": "Non autoris\u00e9.",
    "You can configure this tool's content using LTI Deep Linking.": "Vous pouvez configurer le contenu de cet outil \u00e0 l'aide de LTI Deep Linking.",
    "You can safely close this page now.": "Vous pouvez maintenant fermer cette page en toute s\u00e9curit\u00e9.",
    "You don't have access to save LTI Content Items.": "Vous n'avez pas acc\u00e8s pour enregistrer les \u00e9l\u00e9ments de contenu LTI.",
    "[LTI]: Real user not found against anon_id: {}": "[LTI]: Utilisateur r\u00e9el non trouv\u00e9 pour anon_id: {}"
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
    "DATETIME_FORMAT": "j F Y H:i",
    "DATETIME_INPUT_FORMATS": [
      "%d/%m/%Y %H:%M:%S",
      "%d/%m/%Y %H:%M:%S.%f",
      "%d/%m/%Y %H:%M",
      "%d.%m.%Y %H:%M:%S",
      "%d.%m.%Y %H:%M:%S.%f",
      "%d.%m.%Y %H:%M",
      "%Y-%m-%d %H:%M:%S",
      "%Y-%m-%d %H:%M:%S.%f",
      "%Y-%m-%d %H:%M",
      "%Y-%m-%d"
    ],
    "DATE_FORMAT": "j F Y",
    "DATE_INPUT_FORMATS": [
      "%d/%m/%Y",
      "%d/%m/%y",
      "%d.%m.%Y",
      "%d.%m.%y",
      "%Y-%m-%d"
    ],
    "DECIMAL_SEPARATOR": ",",
    "FIRST_DAY_OF_WEEK": 1,
    "MONTH_DAY_FORMAT": "j F",
    "NUMBER_GROUPING": 3,
    "SHORT_DATETIME_FORMAT": "j N Y H:i",
    "SHORT_DATE_FORMAT": "j N Y",
    "THOUSAND_SEPARATOR": "\u00a0",
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
        