
            (function(global){
                var XBlockLtiConsumerI18N = {
                  init: function() {
                    

'use strict';
{
  const globals = this;
  const django = globals.django || (globals.django = {});

  
  django.pluralidx = function(n) {
    const v = (n != 1);
    if (typeof v === 'boolean') {
      return v ? 1 : 0;
    } else {
      return v;
    }
  };
  

  /* gettext library */

  django.catalog = django.catalog || {};
  
  const newcatalog = {
    "Accept grades past deadline": "Data limite para aceitar notas",
    "Access Token URL: ": "URL de token de acesso: ",
    "Add the key/value pair for any custom parameters, such as the page your e-book should open to or the background color for this component. Ex. [\"page=1\", \"color=white\"]<br />See the {docs_anchor_open}edX LTI documentation{anchor_close} for more details on this setting.": "Adicione o par chave/valor para quaisquer par\u00e2metros personalizados, como, por exemplo, a p\u00e1gina que seu e-book deve abrir ou a cor de fundo para este componente. Ex. [\"page=1\", \"color=white\"]<br />Veja a {docs_anchor_open}documenta\u00e7\u00e3o sobre LTI edX{anchor_close} para obter mais detalhes sobre esta configura\u00e7\u00e3o.",
    "Button Text": "Texto do Bot\u00e3o",
    "Click OK to have your e-mail address sent to a 3rd party application.\n\nClick Cancel to return to this page without sending your information.": "Clique em OK para enviar o seu endere\u00e7o de email para uma aplica\u00e7\u00e3o de terceiros.\n\nClique em Cancelar para regressar a esta p\u00e1gina sem enviar as suas informa\u00e7\u00f5es.",
    "Click OK to have your username and e-mail address sent to a 3rd party application.\n\nClick Cancel to return to this page without sending your information.": "Clique em OK para enviar o seu nome de utilizador e endere\u00e7o de email para uma aplica\u00e7\u00e3o de terceiros.\n\nClique em Cancelar para regressar a esta p\u00e1gina sem enviar as suas informa\u00e7\u00f5es.",
    "Click OK to have your username sent to a 3rd party application.\n\nClick Cancel to return to this page without sending your information.": "Clique em OK para enviar o seu nome de utilizador para uma aplica\u00e7\u00e3o de terceiros.\n\nClique em Cancelar para regressar a esta p\u00e1gina sem enviar as suas informa\u00e7\u00f5es.",
    "Client ID: ": "ID do cliente: ",
    "Comment as returned from grader, LTI2.0 spec": "O coment\u00e1rio apresentado pelo avaliador, especifica\u00e7\u00e3o LTI2.0",
    "Could not get user id for current request": "N\u00e3o foi poss\u00edvel obter ID de usu\u00e1rio para a solicita\u00e7\u00e3o atual",
    "Custom Parameters": "Par\u00e2metros personalizados",
    "Deployment ID: ": "ID de instala\u00e7\u00e3o: ",
    "Disabled": "Desativado",
    "Display Name": "Nome",
    "Enter a description of the third party application. If requesting username and/or email, use this text box to inform users why their username and/or email will be forwarded to a third party application.": "Insira uma descri\u00e7\u00e3o da aplica\u00e7\u00e3o de terceiros. Se solicitar o nome de utilizador e/ou o e-mail, use esta caixa de texto para informar os utilizadores sobre o motivo pelo qual o seu nome de utilizador e/ou e-mail ser\u00e3o encaminhados para uma aplica\u00e7\u00e3o de terceiros.",
    "Enter the LTI ID for the external LTI provider. This value must be the same LTI ID that you entered in the LTI Passports setting on the Advanced Settings page.<br />See the {docs_anchor_open}edX LTI documentation{anchor_close} for more details on this setting.": "Insira a LTI ID para o fornecedor do LTI externo. Este valor deve ser o mesmo que foi inserido na configura\u00e7\u00e3o de passaportes LTI na p\u00e1gina Configura\u00e7\u00f5es Avan\u00e7adas.<br />Veja a {docs_anchor_open}documenta\u00e7\u00e3o sobre LTI da edX{anchor_close} para obter mais detalhes sobre esta configura\u00e7\u00e3o.",
    "Enter the URL of the external tool that this component launches. This setting is only used when Hide External Tool is set to False.<br />See the {docs_anchor_open}edX LTI documentation{anchor_close} for more details on this setting.": "Insira o URL da ferramenta externa lan\u00e7ada por este componente. Esta configura\u00e7\u00e3o \u00e9 usada apenas quando Ocultar a Ferramenta Externa for configurada como False.<br />Veja a {docs_anchor_open}documenta\u00e7\u00e3o sobre LTI edX{anchor_close} para obter mais detalhes sobre esta configura\u00e7\u00e3o.",
    "Enter the desired pixel height of the iframe which will contain the LTI tool. This setting is only used when Hide External Tool is set to False and LTI Launch Target is set to Inline.": "Insira a altura desejada do pixel do iframe que conter\u00e1 a ferramenta LTI. Essa configura\u00e7\u00e3o s\u00f3 \u00e9 usada quando ocultar ferramenta externa \u00e9 definida como false e o destino de inicializa\u00e7\u00e3o LTI \u00e9 definido como inline.",
    "Enter the desired viewport percentage height of the modal overlay which will contain the LTI tool. This setting is only used when Hide External Tool is set to False and LTI Launch Target is set to Modal.": "Insira a altura da porcentagem de viewport desejada da sobreposi\u00e7\u00e3o modal que conter\u00e1 a ferramenta LTI. Essa configura\u00e7\u00e3o s\u00f3 \u00e9 usada quando ocultar ferramenta externa \u00e9 definida como false e o destino de inicializa\u00e7\u00e3o LTI \u00e9 definido como modal.",
    "Enter the desired viewport percentage width of the modal overlay which will contain the LTI tool. This setting is only used when Hide External Tool is set to False and LTI Launch Target is set to Modal.": "Insira a largura da porcentagem de viewport desejada da sobreposi\u00e7\u00e3o modal que conter\u00e1 a ferramenta LTI. Essa configura\u00e7\u00e3o s\u00f3 \u00e9 usada quando ocultar ferramenta externa \u00e9 definida como false e o destino de inicializa\u00e7\u00e3o LTI \u00e9 definido como modal.",
    "Enter the name that students see for this component. Analytics reports may also use the display name to identify this component.": "Insira o nome que os estudantes veem para este componente. Os relat\u00f3rios do Analytics tamb\u00e9m podem usar o nome para identificar este componente.",
    "Enter the number of points possible for this component.  The default value is 1.0.  This setting is only used when Scored is set to True.": "Insira o n\u00famero de pontos poss\u00edveis para este componente. O valor padr\u00e3o \u00e9 1.0. Esta configura\u00e7\u00e3o \u00e9 usada apenas quando Marcar estiver definido como Verdadeiro.",
    "Enter the text on the button used to launch the third party application. This setting is only used when Hide External Tool is set to False and LTI Launch Target is set to Modal or New Window.": "Insira o texto no bot\u00e3o usado para iniciar a aplica\u00e7\u00e3o de terceiros. Esta configura\u00e7\u00e3o s\u00f3 \u00e9 usada quando Ocultar Ferramenta Externa \u00e9 definida como False e LTI Launch Target \u00e9 definido como modal ou nova janela.",
    "Hide External Tool": "Ocultar Ferramenta Externa",
    "Inline Height": "Altura da linha",
    "Keyset URL: ": "URL do conjunto de chaves: ",
    "LTI Application Information": "Informa\u00e7\u00e3o sobre a aplica\u00e7\u00e3o LTI",
    "LTI Consumer": "Consumidor LTI",
    "LTI ID": "LTI ID",
    "LTI Launch Target": "Alvo de Lan\u00e7amento LTI",
    "LTI URL": "LTI URL",
    "Login URL: ": "URL de login: ",
    "Modal Height": "Altura da caixa de integra\u00e7\u00e3o",
    "Modal Width": "Largura Modal",
    "No valid user id found in endpoint URL": "Nenhum ID de utilizador v\u00e1lido no URL de destino",
    "Request user's email": "Solicitar email de utilizador",
    "Request user's username": "Solicitar o nome do utilizador",
    "Scored": "Pontua\u00e7\u00e3o",
    "Select Inline if you want the LTI content to open in an IFrame in the current page. Select Modal if you want the LTI content to open in a modal window in the current page. Select New Window if you want the LTI content to open in a new browser window. This setting is only used when Hide External Tool is set to False.": "Selecione Inline se desejar que o conte\u00fado LTI seja aberto num IFrame na p\u00e1gina atual. Selecione modal se desejar que o conte\u00fado LTI seja aberto em uma janela modal na p\u00e1gina atual. Selecione nova janela se desejar que o conte\u00fado LTI seja aberto em uma nova janela do navegador. Essa configura\u00e7\u00e3o s\u00f3 \u00e9 usada quando ocultar ferramenta externa \u00e9 definida como false.",
    "Select True if this component will receive a numerical score from the external LTI system.": "Selecione Verdadeiro se a inten\u00e7\u00e3o for que este componente receba uma pontua\u00e7\u00e3o num\u00e9rica atrav\u00e9s do sistema externo LTI.",
    "Select True if you want to use this component as a placeholder for syncing with an external grading  system rather than launch an external tool.  This setting hides the Launch button and any IFrames for this component.": "Selecione Verdadeiro se desejar utilizar este componente como espa\u00e7o reservado para sincronizar com um sistema de classifica\u00e7\u00e3o externo em vez de iniciar uma ferramenta externa. Esta configura\u00e7\u00e3o oculta o bot\u00e3o Iniciar e qualquer IFrames para este componente.",
    "Select True to allow third party systems to post grades past the deadline.": "Selecione Verdadeiro para permitir que sistemas de terceiros publiquem notas ap\u00f3s a data limite.",
    "Select True to request the user's email address.": "Selecionar Verdadeiro para solicitar o email de utilizador.",
    "Select True to request the user's username.": "Selecionar Verdadeiro para solicitar o nome de utilizador",
    "The score kept in the xblock KVS -- duplicate of the published score in django DB": "A pontua\u00e7\u00e3o mantida no xblock KVS -- duplicado da pontua\u00e7\u00e3o publicada no django DB",
    "To do that, make sure the block is published and click the link below:": "Para isso, certifique-se de que o bloco \u00e9 publicado e clique no link abaixo:",
    "Unauthorized.": "N\u00e3o autorizado.",
    "[LTI]: Real user not found against anon_id: {}": "[LTI]: usu\u00e1rio real n\u00e3o encontrado contra anon_id: {}"
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
    "DATETIME_FORMAT": "j \\d\\e F \\d\\e Y \u00e0\\s H:i",
    "DATETIME_INPUT_FORMATS": [
      "%Y-%m-%d %H:%M:%S",
      "%Y-%m-%d %H:%M:%S.%f",
      "%Y-%m-%d %H:%M",
      "%d/%m/%Y %H:%M:%S",
      "%d/%m/%Y %H:%M:%S.%f",
      "%d/%m/%Y %H:%M",
      "%d/%m/%y %H:%M:%S",
      "%d/%m/%y %H:%M:%S.%f",
      "%d/%m/%y %H:%M",
      "%Y-%m-%d"
    ],
    "DATE_FORMAT": "j \\d\\e F \\d\\e Y",
    "DATE_INPUT_FORMATS": [
      "%Y-%m-%d",
      "%d/%m/%Y",
      "%d/%m/%y"
    ],
    "DECIMAL_SEPARATOR": ",",
    "FIRST_DAY_OF_WEEK": 0,
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
        