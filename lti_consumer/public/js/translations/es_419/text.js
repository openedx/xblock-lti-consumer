
            (function(global){
                var XBlockLtiConsumerI18N = {
                  init: function() {
                    

'use strict';
{
  const globals = this;
  const django = globals.django || (globals.django = {});

  
  django.pluralidx = function(n) {
    const v = n == 1 ? 0 : n != 0 && n % 1000000 == 0 ? 1 : 2;
    if (typeof v === 'boolean') {
      return v ? 1 : 0;
    } else {
      return v;
    }
  };
  

  /* gettext library */

  django.catalog = django.catalog || {};
  
  const newcatalog = {
    "Accept grades past deadline": "Aceptar notas despu\u00e9s de la fecha l\u00edmite",
    "Access Token URL: ": "URL del token de acceso:",
    "Add the key/value pair for any custom parameters, such as the page your e-book should open to or the background color for this component. Ex. [\"page=1\", \"color=white\"]<br />See the {docs_anchor_open}edX LTI documentation{anchor_close} for more details on this setting.": "Agregue el par clave / valor para cualquier par\u00e1metro personalizado, como la p\u00e1gina a la que su libro electr\u00f3nico debe abrirse o el color de fondo para este componente. Ej. [\"page=1\", \"color=white\"]<br />Consulte la {docs_anchor_open} documentaci\u00f3n de edX LTI {anchor_close} para obtener m\u00e1s detalles sobre esta configuraci\u00f3n",
    "Allow tools to manage and submit grade (programmatic)": "Permite que las herramientas env\u00eden calificaciones (program\u00e1tico)",
    "Allow tools to submit grades only (declarative)": "Permite que las herramientas env\u00eden \u00fanicamente calificaciones (declarativo)",
    "Button Text": "Texto para el bot\u00f3n",
    "Cancel": "Cancelar",
    "Click Cancel to return to this page without sending your information.": "Clic en CANCELAR para volver a est\u00e1 p\u00e1gina sin que se que env\u00ede su informaci\u00f3n.",
    "Click OK to have your e-mail address sent to a 3rd party application.": "Haz Clic en ACEPTAR para que tu correo electr\u00f3nico sea enviado a una aplicaci\u00f3n de 3ros.",
    "Click OK to have your username and e-mail address sent to a 3rd party application.": "Haz Clic en ACEPTAR para que tu nombre de usuario y correo electr\u00f3nico sean enviados a una aplicaci\u00f3n de 3ros.",
    "Click OK to have your username sent to a 3rd party application.": "Haz Clic en ACEPTAR para que su nombre de usuario sea enviado a una aplicaci\u00f3n de 3ros.",
    "Client ID used by LTI tool": "ID del cliente usado por la herramienta LTI",
    "Client ID: ": "ID de cliente:",
    "Client key provided by the LTI tool provider.": "Llave de cliente suministrada por el proveedor de la herramienta LTI.",
    "Client secret provided by the LTI tool provider.": "Secreto de cliente suministrado por el proveedor de la herramienta LTI.",
    "Comment as returned from grader, LTI2.0 spec": "El comentario tal y como fue enviado por el evaluador, LTI2.0 spec",
    "Configuration Stored on XBlock fields": "Configuraci\u00f3n almacenada en campos de XBlocks",
    "Configuration Stored on this model": "Configuraci\u00f3n almacenada en este modelo",
    "Could not get user id for current request": "No se pudo obtener el id de usuario para esta petici\u00f3n",
    "Could not parse LTI passport: {lti_passport!r}. Should be \"id:key:secret\" string.": "No fu\u00e9 posible parsear el pasaporte LTI: {lti_passport!r}. Deber\u00eda ser una cadena de tipo \"id:key:secret\".",
    "Could not parse custom parameter: {custom_parameter!r}. Should be \"x=y\" string.": "No fu\u00e9 posible parsear el parametro: {custom_parameter!r}. Deber\u00eda ser una cadena tipo \"x=y\".",
    "Custom Parameters": "Par\u00e1metros personalizados",
    "Custom Parameters must be a list": "Los par\u00e1metros personalizados deben ser una lista",
    "DEPRECATED - This is now stored in the LtiConfiguration model.": "DEPRECADO - Esto ahora se almacena en el modelo LtiConfiguration.",
    "Deep Linking Launch - Configure tool": "Herramienta de configuraci\u00f3n para lanzamiento de Deep Linking",
    "Deep Linking Launch URL": "URL de lanzamiento para Deep Linking",
    "Deep Linking is configured on this tool.": "Deep Linking est\u00e1 configurado para esta herramienta.",
    "Deep linking": "Deep linking",
    "Deployment ID: ": "ID del deployment:",
    "Disabled": "Invalidar",
    "Display Name": "Nombre a mostrar",
    "Enable LTI NRPS": "Habilitar LTI NRPS",
    "Enable LTI Names and Role Provisioning Services.": "Habilitar los servicios de provisi\u00f3n de nombres y roles de LTI.",
    "Enable the LTI-AGS service and select the functionality enabled for LTI tools. The 'declarative' mode (default) will provide a tool with a LineItem created from the XBlock settings, while the 'programmatic' one will allow tools to manage, create and link the grades.": "Habilite el servicio AGS de LTI y seleccione la funcionalidad habilitada para las herramientas LTI. El modo 'declarativo' (por defecto) le dar\u00e1 una herramienta con un LineItem creado a partir de las configuraciones del Xblock, mientras el modo 'program\u00e1tico' le permitir\u00e1 a las herramientas administrar, crear y enlazar las calificaciones.",
    "Enter a description of the third party application. If requesting username and/or email, use this text box to inform users why their username and/or email will be forwarded to a third party application.": "Provea una descripci\u00f3n de la aplicaci\u00f3n de un tercero. Si se solicita el nombre del usuario o su correo, use este cuadro de texto para informar al usuario que su nombre de usuario y su correo ser\u00e1n redireccionados a una aplicaci\u00f3n de un tercero.",
    "Enter the LTI 1.3 Tool Launch URL. <br />This is the URL the LMS will use to launch the LTI Tool.": "Ingrese la URL para lanzar la herramienta LTI 1.3. <br />Esta es la URL que el LMS usar\u00e1 para abrir la herramienta LTI.",
    "Enter the LTI 1.3 Tool OIDC Authorization url (can also be called login or login initiation URL).<br />This is the URL the LMS will use to start a LTI authorization prior to doing the launch request.": "Ingrese la URL de autorizaci\u00f3n OIDC de la herramienta LTI 1.3 (tambien llamada URL de login, o de inicio de sesi\u00f3n). <br />Esta es la URL que el LMS usar\u00e1 para iniciar la autorizaci\u00f3n con el componente LTI antes de comenzar.",
    "Enter the LTI 1.3 Tool's JWK keysets URL.<br />This link should retrieve a JSON file containing public keys and signature algorithm information, so that the LMS can check if the messages and launch requests received have the signature from the tool.<br /><b>This is not required when doing LTI 1.3 Launches without LTI Advantage nor Basic Outcomes requests.</b>": "Ingrese la clave p\u00fablica de la herramienta LTI 1.3.<br />Esta cadena de texto comienza con '-----BEGIN PUBLIC KEY-----' y es requerida por el LMS para verificar los mensajes recibidos desde la herramienta externa.<br /><b>No es requerida cuando se hace el lanzamiento de la herramienta sin LTI Advantage ni para peticiones sencillas.</b>",
    "Enter the LTI 1.3 Tool's public key.<br />This is a string that starts with '-----BEGIN PUBLIC KEY-----' and is required so that the LMS can check if the messages and launch requests received have the signature from the tool.<br /><b>This is not required when doing LTI 1.3 Launches without LTI Advantage nor Basic Outcomes requests.</b>": "Ingrese la llave p\u00fablica de la herramienta LTI 1.3.<br />Esta cadena de texto comienza con '-----BEGIN PUBLIC KEY-----' y es requerida por el LMS para verificar los mensajes recibidos desde la herramienta externa.<br /><b>No es requerida cuando se hace el lanzamiento de la herramienta sin LTI Advantage ni para peticiones sencillas.</b>",
    "Enter the LTI Advantage Deep Linking Launch URL. If the tool does not specify one, use the same value as 'Tool Launch URL'.": "Ingrese la URL de lanzamiento para LTI Advantage Deep Linking. Si la herramienta no especifica una direcci\u00f3n, use la misma direcci\u00f3n URL para lanzamiento de la herramienta.",
    "Enter the LTI ID for the external LTI provider. This value must be the same LTI ID that you entered in the LTI Passports setting on the Advanced Settings page.<br />See the {docs_anchor_open}edX LTI documentation{anchor_close} for more details on this setting.": "Introduzca el ID LTI para el proveedor LTI externo. Este valor debe ser el mismo ID LTI que ingres\u00f3 en la configuraci\u00f3n de Pasaportes LTI en la p\u00e1gina Configuraci\u00f3n avanzada.<br />Consulte la {docs_anchor_open} documentaci\u00f3n de edX LTI {anchor_close} para obtener m\u00e1s detalles sobre esta configuraci\u00f3n.",
    "Enter the URL of the external tool that this component launches. This setting is only used when Hide External Tool is set to False.<br />See the {docs_anchor_open}edX LTI documentation{anchor_close} for more details on this setting.": "Ingrese la URL de la herramienta externa que este componente inicia. Esta configuraci\u00f3n s\u00f3lo se utiliza cuando Ocultar herramienta externa se establece en Falso.<br />Consulte la {docs_anchor_open} documentaci\u00f3n de edX LTI {anchor_close} para obtener m\u00e1s detalles sobre esta configuraci\u00f3n.",
    "Enter the desired pixel height of the iframe which will contain the LTI tool. This setting is only used when Hide External Tool is set to False and LTI Launch Target is set to Inline.": "Introduzca la altura en p\u00edxeles deseada del iframe que contendr\u00e1 la herramienta LTI. Esta opci\u00f3n s\u00f3lo se utiliza cuando Ocultar herramienta externa se establece en False y Target para el LTI se establece en Inline.",
    "Enter the desired viewport percentage height of the modal overlay which will contain the LTI tool. This setting is only used when Hide External Tool is set to False and LTI Launch Target is set to Modal.": "Ingrese la altura de porcentaje de visualizaci\u00f3n deseada de la superposici\u00f3n modal que contendr\u00e1 la herramienta LTI. Esta opci\u00f3n s\u00f3lo se utiliza cuando Ocultar herramienta externa se establece en False y Target para el LTI se establece en Modal.",
    "Enter the desired viewport percentage width of the modal overlay which will contain the LTI tool. This setting is only used when Hide External Tool is set to False and LTI Launch Target is set to Modal.": "Ingrese el ancho de porcentaje de la ventana de visualizaci\u00f3n de la superposici\u00f3n modal que contendr\u00e1 la herramienta LTI. Esta opci\u00f3n s\u00f3lo se utiliza cuando Ocultar herramienta externa se establece en False y Target para el LTI se establece en Modal.",
    "Enter the name that students see for this component. Analytics reports may also use the display name to identify this component.": "Ingrese el nombre que los estudiantes ver\u00e1n para este componente. Los reportes de Analytics tambi\u00e9n pueden utilizar el nombre para mostrar para identificar este componente.",
    "Enter the number of points possible for this component.  The default value is 1.0.  This setting is only used when Scored is set to True.": "Ingrese el n\u00famero de puntos posibles para este componente. El valor por defecto es 1.0. Este valor solo se utiliza cuando el par\u00e1metro de calificaci\u00f3n est\u00e1 definido como True.",
    "Enter the text on the button used to launch the third party application. This setting is only used when Hide External Tool is set to False and LTI Launch Target is set to Modal or New Window.": "Ingrese el texto en el bot\u00f3n usado para iniciar la aplicaci\u00f3n de terceros. Esta opci\u00f3n s\u00f3lo se utiliza cuando Ocultar herramienta externa se establece en Falso y el Target para el LTI se establece en Modal o Nueva Ventana.",
    "Hide External Tool": "Ocultar la herramienta externa",
    "If you run deep linking again, the content above will be replaced.": "Si ejecuta Deep Linking nuevamente, todo el contenido de arriba ser\u00e1 reemplazado.",
    "If you're seeing this on a live course, please contact the course staff.": "Si usted est\u00e1 viendo esto en un curso en vivo, por favor contacte al equipo del curso.",
    "Inline Height": "Altura Inline",
    "Invalid LTI configuration.": "Configuraci\u00f3n LTI inv\u00e1lida",
    "Invalid token header. No credentials provided.": "Encabezado de token inv\u00e1lido. No se suministraron las credenciales.",
    "Invalid token header. Token string should not contain spaces.": "Encabezado de token inv\u00e1lido. La cadena de caracteres del token no debe contener espacios.",
    "Invalid token signature.": "Firma de token inv\u00e1lida.",
    "Keyset URL: ": "URL del Keyset:",
    "LTI 1.3 Block Client ID - DEPRECATED": "LTI 1.3 Block Client ID - DEPRECADO",
    "LTI 1.3 Block Key - DEPRECATED": "LTI 1.3 Block Key - DEPRECADO",
    "LTI 1.3 Launches can only be performed from the LMS.": "Los lanzamientos de LTI 1.3 solo pueden ser realizados desde el LMS.",
    "LTI Application Information": "Informaci\u00f3n sobre la aplicaci\u00f3n LTI",
    "LTI Assignment and Grades Service": "Servicio de Tareas y Calificaciones de LTI",
    "LTI Configuration stores on XBlock needs a block location set.": "Las configuraciones LTI para XBlock necesitan una ubicaci\u00f3n de bloque.",
    "LTI Consumer": "Consumidor LTI",
    "LTI Deep Linking": "Deep Linking de LTI",
    "LTI Deep Linking failed.": "Fall\u00f3 el Deep Linking de LTI",
    "LTI ID": "ID de LTI",
    "LTI Launch Target": "Target para el LTI",
    "LTI URL": "URL de LTI",
    "LTI Version": "Versi\u00f3n LTI",
    "LTI configuration data.": "Datos de configuraci\u00f3n de LTI",
    "LTI configuration not found.": "No se encontr\u00f3 la configuraci\u00f3n LTI.",
    "Login URL: ": "URL de inicio de sesi\u00f3n:",
    "Missing LTI 1.3 authentication token.": "El token de autenticaci\u00f3n de LTI 1.3 no se encuentra disponible.",
    "Modal Height": "Altura del modal",
    "Modal Width": "Ancho del modal",
    "No valid user id found in endpoint URL": "No se encontr\u00f3 un id de usuario v\u00e1lido en el URL del endpoint",
    "OK": "Aceptar",
    "Platform's generated JWK keyset.": "JWK keyset generado para la plataforma",
    "Platform's generated Private key ID": "Llave privada generada para la plataforma.",
    "Platform's generated Private key. Keep this value secret.": "Llave privada generada para la plataforma. Mantenga este valor en secreto.",
    "Please check that you have course staff permissions and double check this block's LTI settings.": "Por favor verifique que tiene permisos de staff en el curso y confirme las configuraciones de LTI para este bloque.",
    "Press to Launch": "Pulsar para iniciar",
    "Request user's email": "Solicitar la direcci\u00f3n de correo del usuario",
    "Request user's username": "Solicite el nombre p\u00fablico del usuario",
    "Scored": "Puntuado",
    "Select Inline if you want the LTI content to open in an IFrame in the current page. Select Modal if you want the LTI content to open in a modal window in the current page. Select New Window if you want the LTI content to open in a new browser window. This setting is only used when Hide External Tool is set to False.": "Seleccione Inline si desea que el contenido LTI se abra en un IFrame en la p\u00e1gina actual. Seleccione Modal si desea que el contenido LTI se abra en una ventana modal en la p\u00e1gina actual. Seleccione Nueva ventana si desea que el contenido LTI se abra en una nueva ventana del navegador. Esta configuraci\u00f3n s\u00f3lo se utiliza cuando Ocultar herramienta externa se establece en Falso.",
    "Select True if this component will receive a numerical score from the external LTI system.": "Seleccione True si este componente recibir\u00e1 una puntuaci\u00f3n num\u00e9rica desde un sistema LTI externo.",
    "Select True if you want to enable LTI Advantage Deep Linking.": "Seleccione True si desea habiliitar el Deep Linking de LTI Advantage.",
    "Select True if you want to use this component as a placeholder for syncing with an external grading  system rather than launch an external tool.  This setting hides the Launch button and any IFrames for this component.": "Seleccione True si desea usar este componente como marcador para sincronizarse con un servicio externo en lugar de lanzar una herramienta externa. Esta opci\u00f3n oculta el bot\u00f3n de Lanzar y cualquier iframe para este componente.",
    "Select True to allow third party systems to post grades past the deadline.": "Seleccione True para permitir que sistemas de terceros publiquen calificaciones despu\u00e9s de la fecha l\u00edmite.",
    "Select True to request the user's email address.": "Seleccione True para solicitar el correo electr\u00f3nico del usuario.",
    "Select True to request the user's username.": "Seleccione True para solicitar el nombre de usuario.",
    "Select True to send the extra parameters, which might contain Personally Identifiable Information. The processors are site-wide, please consult the site administrator if you have any questions.": "Seleccione True praa enviar los par\u00e1metros adicionales, los cuales pueden contener informaci\u00f3n de identificaci\u00f3n personal. Los procesadores son para todo el sitio, por favor consulte al administrador del sitio si tiene cualquier pregunta.",
    "Select how the tool's public key information will be specified.": "Seleccione c\u00f3mo se especificar\u00e1 la informaci\u00f3n de la clave p\u00fablica de la herramienta.",
    "Select the LTI version that your tool supports.<br />The XBlock LTI Consumer fully supports LTI 1.1.1, LTI 1.3 and LTI Advantage features.": "Seleccione la versi\u00f3n de LTI que su herramienta soporta. <br />El Xblock LTI Consumer soporta completamente las caracter\u00edsticas de LTI 1.1.1, LTI 1.3 y LTI Advantage.",
    "Send extra parameters": "Enviar par\u00e1metros adicionales",
    "Students don't have permissions to perform LTI Deep Linking configuration launches.": "Los estudiantes no tienen permisos para lanzar configuraciones de LTI Deep Linking.",
    "The Deep Linking configuration stored is presented below:": "La configuraci\u00f3n guardada de Deep Linking se presenta a continuaci\u00f3n:",
    "The LTI Deep Linking content was successfully saved in the LMS.": "El contenido de Deep Linking de LTI fu\u00e9 guardado con exito en el LMS.",
    "The URL of the external tool that initiates the launch.": "URL de la herramienta externa que inicia el lanzamiento.",
    "The score kept in the xblock KVS -- duplicate of the published score in django DB": "La calificaci\u00f3n almacenada en xblock KVS -- un duplicado de la calificaci\u00f3n publicada en django DB",
    "The selected content type is not supported by Open edX.": "El tipo de contenido seleccionado no est\u00e1 soportado por Open edX.",
    "To do that, make sure the block is published and click the link below:": "Para hacer esto, asegurese de que el bloque est\u00e9 publicado y haga clic en el link a continuaci\u00f3n:",
    "To set up the LTI integration, you need to register the LMS in the tool with the information provided below.": "Para configurar la integraci\u00f3n LTI, debe registrar al LMS en la herramienta externa con la informaci\u00f3n suministrada a continuaci\u00f3n.",
    "Tool Initiate Login URL": "URL para iniciar el login en la herramienta externa",
    "Tool Keyset URL": "URL del conjunto de claves de la herramienta",
    "Tool Launch URL": "URL para lanzar la herramienta",
    "Tool Public Key": "Llave p\u00fablica de la herramienta",
    "Tool Public Key Mode": "Modo de clave p\u00fablica de la herramienta",
    "Unauthorized.": "No autorizado.",
    "You can configure this tool's content using LTI Deep Linking.": "Puede configurar el contenido de esta herramienta usando LTI deep linking",
    "You can safely close this page now.": "Puede cerrar esta p\u00e1gina ahora.",
    "You don't have access to save LTI Content Items.": "Usted no tiene acceso para guardar items de contenido LTI.",
    "[LTI]: Real user not found against anon_id: {}": "[LTI]: No se encontr\u00f3 un usuario que coincidiera con anon_id: {}"
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
    "DATETIME_FORMAT": "j \\d\\e F \\d\\e Y \\a \\l\\a\\s H:i",
    "DATETIME_INPUT_FORMATS": [
      "%d/%m/%Y %H:%M:%S",
      "%d/%m/%Y %H:%M:%S.%f",
      "%d/%m/%Y %H:%M",
      "%d/%m/%y %H:%M:%S",
      "%d/%m/%y %H:%M:%S.%f",
      "%d/%m/%y %H:%M",
      "%Y-%m-%d %H:%M:%S",
      "%Y-%m-%d %H:%M:%S.%f",
      "%Y-%m-%d %H:%M",
      "%Y-%m-%d"
    ],
    "DATE_FORMAT": "j \\d\\e F \\d\\e Y",
    "DATE_INPUT_FORMATS": [
      "%d/%m/%Y",
      "%d/%m/%y",
      "%Y-%m-%d"
    ],
    "DECIMAL_SEPARATOR": ",",
    "FIRST_DAY_OF_WEEK": 1,
    "MONTH_DAY_FORMAT": "j \\d\\e F",
    "NUMBER_GROUPING": 3,
    "SHORT_DATETIME_FORMAT": "d/m/Y H:i",
    "SHORT_DATE_FORMAT": "d/m/Y",
    "THOUSAND_SEPARATOR": ".",
    "TIME_FORMAT": "H:i",
    "TIME_INPUT_FORMATS": [
      "%H:%M:%S",
      "%H:%M:%S.%f",
      "%H:%M"
    ],
    "YEAR_MONTH_FORMAT": "F \\d\\e Y"
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
        