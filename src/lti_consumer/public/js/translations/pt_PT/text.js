
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
    "Accept grades past deadline": "Data limite para aceitar notas",
    "Access Token URL: ": "URL de token de acesso: ",
    "Add the key/value pair for any custom parameters, such as the page your e-book should open to or the background color for this component. Ex. [\"page=1\", \"color=white\"]<br />See the {docs_anchor_open}edX LTI documentation{anchor_close} for more details on this setting.": "Adicione o par chave/valor para quaisquer par\u00e2metros personalizados, como, por exemplo, a p\u00e1gina que seu e-book deve abrir ou a cor de fundo para este componente. Ex. [\"page=1\", \"color=white\"]<br />Veja a {docs_anchor_open}documenta\u00e7\u00e3o sobre LTI edX{anchor_close} para obter mais detalhes sobre esta configura\u00e7\u00e3o.",
    "Allow tools to manage and submit grade (programmatic)": "Permitir ferramentas para gerir e submeter notas (program\u00e1tico)",
    "Allow tools to submit grades only (declarative)": "Permitir que os instrumentos submetam apenas notas (declarativo)",
    "Button Text": "Texto do Bot\u00e3o",
    "CONFIG_ON_XBLOCK and CONFIG_EXTERNAL are not supported for LTI 1.3 Proctoring Services.": "CONFIG_ON_XBLOCK e CONFIG_EXTERNAL n\u00e3o s\u00e3o suportados pelos servi\u00e7os de supervis\u00e3o de avalia\u00e7\u00e3o LTI 1.3.",
    "Cancel": "Cancelar",
    "Click Cancel to return to this page without sending your information.": "Clique em Cancelar para regressar a esta p\u00e1gina sem enviar as suas informa\u00e7\u00f5es.",
    "Click OK to have your e-mail address sent to a 3rd party application.": "Clique em OK para que o seu endere\u00e7o de correio electr\u00f3nico seja enviado para uma aplica\u00e7\u00e3o de terceiros.",
    "Click OK to have your username and e-mail address sent to a 3rd party application.": "Clique em OK para que o seu nome de utilizador e endere\u00e7o de correio electr\u00f3nico sejam enviados para uma aplica\u00e7\u00e3o de terceiros.",
    "Click OK to have your username sent to a 3rd party application.": "Clique em OK para que o seu nome de utilizador seja enviado para uma aplica\u00e7\u00e3o de terceiros.",
    "Client ID used by LTI tool": "ID do cliente usado pela ferramenta LTI",
    "Client ID: ": "ID do cliente: ",
    "Client key provided by the LTI tool provider.": "Chave do cliente fornecida pelo provedor da ferramenta LTI.",
    "Client secret provided by the LTI tool provider.": "Segredo do cliente fornecido pelo provedor da ferramenta LTI.",
    "Comment as returned from grader, LTI2.0 spec": "O coment\u00e1rio apresentado pelo avaliador, especifica\u00e7\u00e3o LTI2.0",
    "Configuration Stored on XBlock fields": "Configura\u00e7\u00e3o armazenada em campos XBlock",
    "Configuration Stored on external service": "Configura\u00e7\u00e3o armazenada num servi\u00e7o externo",
    "Configuration Stored on this model": "Configura\u00e7\u00e3o armazenada neste modelo",
    "Configuration Type": "Tipo de configura\u00e7\u00e3o",
    "Configuration on block": "Configura\u00e7\u00e3o em bloco",
    "Could not get user data for current request": "N\u00e3o foi poss\u00edvel obter os dados do utilizador para o pedido actual",
    "Could not get user id for current request": "N\u00e3o foi poss\u00edvel obter ID de usu\u00e1rio para a solicita\u00e7\u00e3o atual",
    "Could not parse LTI passport: {lti_passport!r}. Should be \"id:key:secret\" string.": "N\u00e3o foi poss\u00edvel analisar o passaporte LTI: {lti_passport!r}. Deve ser a string \"id:key:secret\".",
    "Could not parse custom parameter: {custom_parameter!r}. Should be \"x=y\" string.": "N\u00e3o foi poss\u00edvel analisar o par\u00e2metro personalizado: {custom_parameter!r}. Deve ser uma string \"x=y\".",
    "Custom Parameters": "Par\u00e2metros personalizados",
    "Custom Parameters must be a list": "Os par\u00e2metros personalizados devem ser uma lista",
    "DEPRECATED - This is now stored in the LtiConfiguration model.": "DEPRECATED - Isto agora est\u00e1 armazenado no modelo LtiConfiguration.",
    "Database Configuration": "Configura\u00e7\u00e3o da base de dados",
    "Deep Linking Launch - Configure tool": "Lan\u00e7amento de Deep Linking - Configurar ferramenta",
    "Deep Linking Launch URL": "URL de lan\u00e7amento Deep Linking",
    "Deep Linking is configured on this tool.": "Deep Linking \u00e9 configurado nesta ferramenta.",
    "Deep linking": "Liga\u00e7\u00e3o profunda",
    "Deployment ID: ": "ID de instala\u00e7\u00e3o: ",
    "Disabled": "Desativado",
    "Display Name": "Nome",
    "Enable LTI NRPS": "Ativar LTI NRPS",
    "Enable LTI Names and Role Provisioning Services.": "Habilitar Nomes e Servi\u00e7os de Provis\u00e3o de Fun\u00e7\u00f5es LTI.",
    "Enable the LTI-AGS service and select the functionality enabled for LTI tools. The 'declarative' mode (default) will provide a tool with a LineItem created from the XBlock settings, while the 'programmatic' one will allow tools to manage, create and link the grades.": "Activar o servi\u00e7o LTI-AGS e seleccionar a funcionalidade activada para as ferramentas LTI. O modo 'declarativo' (por defeito) fornecer\u00e1 uma ferramenta com um LineItem criado a partir das defini\u00e7\u00f5es do XBlock, enquanto que o modo 'program\u00e1tico' permitir\u00e1 \u00e0s ferramentas gerir, criar e ligar as notas.",
    "Enter a description of the third party application. If requesting username and/or email, use this text box to inform users why their username and/or email will be forwarded to a third party application.": "Insira uma descri\u00e7\u00e3o da aplica\u00e7\u00e3o de terceiros. Se solicitar o nome de utilizador e/ou o e-mail, use esta caixa de texto para informar os utilizadores sobre o motivo pelo qual o seu nome de utilizador e/ou e-mail ser\u00e3o encaminhados para uma aplica\u00e7\u00e3o de terceiros.",
    "Enter the LTI 1.3 Tool Launch URL. <br />This is the URL the LMS will use to launch the LTI Tool.": "Insira o URL de inicializa\u00e7\u00e3o da ferramenta LTI 1.3.<br /> Este \u00e9 o URL que o LMS usar\u00e1 para iniciar a ferramenta LTI.",
    "Enter the LTI 1.3 Tool OIDC Authorization url (can also be called login or login initiation URL).<br />This is the URL the LMS will use to start a LTI authorization prior to doing the launch request.": "Digite o URL de autoriza\u00e7\u00e3o OIDC da ferramenta LTI 1.3 (tamb\u00e9m pode ser chamado de login ou URL de in\u00edcio de login).<br /> Este \u00e9 o URL que o LMS usar\u00e1 para iniciar uma autoriza\u00e7\u00e3o LTI antes de fazer a solicita\u00e7\u00e3o de inicializa\u00e7\u00e3o.",
    "Enter the LTI 1.3 Tool's JWK keysets URL.<br />This link should retrieve a JSON file containing public keys and signature algorithm information, so that the LMS can check if the messages and launch requests received have the signature from the tool.<br /><b>This is not required when doing LTI 1.3 Launches without LTI Advantage nor Basic Outcomes requests.</b>": "Insira o URL dos conjuntos de chaves JWK da ferramenta LTI 1.3.<br /> Este link deve recuperar um ficheiro JSON contendo chaves p\u00fablicas e informa\u00e7\u00f5es do algoritmo de assinatura, para que o LMS possa verificar se as mensagens e solicita\u00e7\u00f5es de inicializa\u00e7\u00e3o recebidas possuem a assinatura da ferramenta.<br /> <b>Isso n\u00e3o \u00e9 necess\u00e1rio ao fazer LTI 1.3 Launchs sem LTI Advantage nem solicita\u00e7\u00f5es de resultados b\u00e1sicos.</b>",
    "Enter the LTI 1.3 Tool's public key.<br />This is a string that starts with '-----BEGIN PUBLIC KEY-----' and is required so that the LMS can check if the messages and launch requests received have the signature from the tool.<br /><b>This is not required when doing LTI 1.3 Launches without LTI Advantage nor Basic Outcomes requests.</b>": "Insira a chave p\u00fablica da ferramenta LTI 1.3.<br /> Esta \u00e9 uma string que come\u00e7a com '-----BEGIN PUBLIC KEY-----' e \u00e9 necess\u00e1ria para que o LMS possa verificar se as mensagens e solicita\u00e7\u00f5es de inicializa\u00e7\u00e3o recebidas possuem a assinatura da ferramenta.<br /> <b>Isto n\u00e3o \u00e9 necess\u00e1rio ao fazer LTI 1.3 Launchs sem LTI Advantage nem solicita\u00e7\u00f5es de resultados b\u00e1sicos.</b>",
    "Enter the LTI Advantage Deep Linking Launch URL. If the tool does not specify one, use the same value as 'Tool Launch URL'.": "Introduza o URL de lan\u00e7amento do LTI Advantage Deep Linking. Se a ferramenta n\u00e3o especificar uma, utilizar o mesmo valor que 'URL de lan\u00e7amento da ferramenta'.",
    "Enter the LTI ID for the external LTI provider. This value must be the same LTI ID that you entered in the LTI Passports setting on the Advanced Settings page.<br />See the {docs_anchor_open}edX LTI documentation{anchor_close} for more details on this setting.": "Insira a LTI ID para o fornecedor do LTI externo. Este valor deve ser o mesmo que foi inserido na configura\u00e7\u00e3o de passaportes LTI na p\u00e1gina Configura\u00e7\u00f5es Avan\u00e7adas.<br />Veja a {docs_anchor_open}documenta\u00e7\u00e3o sobre LTI da edX{anchor_close} para obter mais detalhes sobre esta configura\u00e7\u00e3o.",
    "Enter the URL of the external tool that this component launches. This setting is only used when Hide External Tool is set to False.<br />See the {docs_anchor_open}edX LTI documentation{anchor_close} for more details on this setting.": "Insira o URL da ferramenta externa lan\u00e7ada por este componente. Esta configura\u00e7\u00e3o \u00e9 usada apenas quando Ocultar a Ferramenta Externa for configurada como False.<br />Veja a {docs_anchor_open}documenta\u00e7\u00e3o sobre LTI edX{anchor_close} para obter mais detalhes sobre esta configura\u00e7\u00e3o.",
    "Enter the desired pixel height of the iframe which will contain the LTI tool. This setting is only used when Hide External Tool is set to False and LTI Launch Target is set to Inline.": "Insira a altura desejada do pixel do iframe que conter\u00e1 a ferramenta LTI. Essa configura\u00e7\u00e3o s\u00f3 \u00e9 usada quando ocultar ferramenta externa \u00e9 definida como false e o destino de inicializa\u00e7\u00e3o LTI \u00e9 definido como inline.",
    "Enter the desired viewport percentage height of the modal overlay which will contain the LTI tool. This setting is only used when Hide External Tool is set to False and LTI Launch Target is set to Modal.": "Insira a altura da porcentagem de viewport desejada da sobreposi\u00e7\u00e3o modal que conter\u00e1 a ferramenta LTI. Essa configura\u00e7\u00e3o s\u00f3 \u00e9 usada quando ocultar ferramenta externa \u00e9 definida como false e o destino de inicializa\u00e7\u00e3o LTI \u00e9 definido como modal.",
    "Enter the desired viewport percentage width of the modal overlay which will contain the LTI tool. This setting is only used when Hide External Tool is set to False and LTI Launch Target is set to Modal.": "Insira a largura da porcentagem de viewport desejada da sobreposi\u00e7\u00e3o modal que conter\u00e1 a ferramenta LTI. Essa configura\u00e7\u00e3o s\u00f3 \u00e9 usada quando ocultar ferramenta externa \u00e9 definida como false e o destino de inicializa\u00e7\u00e3o LTI \u00e9 definido como modal.",
    "Enter the name that students see for this component. Analytics reports may also use the display name to identify this component.": "Insira o nome que os estudantes veem para este componente. Os relat\u00f3rios do Analytics tamb\u00e9m podem usar o nome para identificar este componente.",
    "Enter the number of points possible for this component.  The default value is 1.0.  This setting is only used when Scored is set to True.": "Insira o n\u00famero de pontos poss\u00edveis para este componente. O valor padr\u00e3o \u00e9 1.0. Esta configura\u00e7\u00e3o \u00e9 usada apenas quando Marcar estiver definido como Verdadeiro.",
    "Enter the reusable LTI external configuration ID provided by the support staff.": "Introduza o ID de configura\u00e7\u00e3o externa reutiliz\u00e1vel do LTI fornecido pela equipa de suporte.",
    "Enter the text on the button used to launch the third party application. This setting is only used when Hide External Tool is set to False and LTI Launch Target is set to Modal or New Window.": "Insira o texto no bot\u00e3o usado para iniciar a aplica\u00e7\u00e3o de terceiros. Esta configura\u00e7\u00e3o s\u00f3 \u00e9 usada quando Ocultar Ferramenta Externa \u00e9 definida como False e LTI Launch Target \u00e9 definido como modal ou nova janela.",
    "Hide External Tool": "Ocultar Ferramenta Externa",
    "If you run deep linking again, the content above will be replaced.": "Se voc\u00ea executar links diretos novamente, o conte\u00fado acima ser\u00e1 substitu\u00eddo.",
    "If you're seeing this on a live course, please contact the course staff.": "Se estiver a ver isto num curso ao vivo, por favor contacte a equipa do curso.",
    "Inline Height": "Altura da linha",
    "Invalid LTI configuration.": "Configura\u00e7\u00e3o de LTI inv\u00e1lida.",
    "Invalid token header. No credentials provided.": "Cabe\u00e7alho do 'token' inv\u00e1lido. Nenhuma credencial fornecida.",
    "Invalid token header. Token string should not contain spaces.": "Cabe\u00e7alho de token inv\u00e1lido. A string de token n\u00e3o deve conter espa\u00e7os.",
    "Invalid token signature.": "Assinatura de token inv\u00e1lida.",
    "Keyset URL: ": "URL do conjunto de chaves: ",
    "LTI 1.3 Block Client ID - DEPRECATED": "LTI 1.3 Identifica\u00e7\u00e3o do cliente do bloco - DESCONTINUADO",
    "LTI 1.3 Block Key - DEPRECATED": "Chave de bloco LTI 1.3 - DEPRECIADO",
    "LTI 1.3 Launches can only be performed from the LMS.": "Os lan\u00e7amentos do LTI 1.3 s\u00f3 podem ser executados a partir do LMS.",
    "LTI Application Information": "Informa\u00e7\u00e3o sobre a aplica\u00e7\u00e3o LTI",
    "LTI Assignment and Grades Service": "Servi\u00e7o de Tarefas e de Classifica\u00e7\u00e3o de LTI",
    "LTI Configuration stored on the model for LTI 1.3 must have a value for one of lti_1p3_tool_public_key or lti_1p3_tool_keyset_url.": "A configura\u00e7\u00e3o de LTI armazenada no modelo para LTI 1.3 deve ter um valor para uma das chaves lti_1p3_tool_public_key ou lti_1p3_tool_keyset_url.",
    "LTI Configuration stores on XBlock needs a block location set.": "Os armazenamentos de configura\u00e7\u00e3o LTI no XBlock precisam de um conjunto de localiza\u00e7\u00e3o de bloco.",
    "LTI Consumer": "Consumidor LTI",
    "LTI Deep Linking": "LTI Deep Linking",
    "LTI Deep Linking failed.": "LTI Deep Linking falhou.",
    "LTI ID": "LTI ID",
    "LTI Launch Target": "Alvo de Lan\u00e7amento LTI",
    "LTI Reusable Configuration ID": "ID de configura\u00e7\u00e3o reutiliz\u00e1vel LTI",
    "LTI URL": "LTI URL",
    "LTI Version": "Vers\u00e3o LTI",
    "LTI configuration data.": "Dados de configura\u00e7\u00e3o LTI.",
    "LTI configuration not found.": "Configura\u00e7\u00e3o LTI n\u00e3o encontrada.",
    "Login URL: ": "URL de login: ",
    "Missing LTI 1.3 authentication token.": "Falta o 'token' de autentica\u00e7\u00e3o LTI 1.3.",
    "Modal Height": "Altura da caixa de integra\u00e7\u00e3o",
    "Modal Width": "Largura Modal",
    "No valid user id found in endpoint URL": "Nenhum ID de utilizador v\u00e1lido no URL de destino",
    "OK": "OK",
    "Platform's generated JWK keyset.": "Conjunto de chaves JWK gerado pela plataforma.",
    "Platform's generated Private key ID": "ID da chave privada gerada pela plataforma",
    "Platform's generated Private key. Keep this value secret.": "Chave privada gerada pela plataforma. Mantenha esse valor em segredo.",
    "Please check that you have course staff permissions and double check this block's LTI settings.": "Verifique se voc\u00ea tem permiss\u00f5es de equipe do curso e verifique novamente as configura\u00e7\u00f5es de LTI deste bloco.",
    "Press to Launch": "Pressione para iniciar",
    "Registered Redirect URIs": "URIs de redireccionamento registados",
    "Request user's email": "Solicitar email de utilizador",
    "Request user's username": "Solicitar o nome do utilizador",
    "Reusable Configuration": "Configura\u00e7\u00e3o reutiliz\u00e1vel",
    "Scored": "Pontua\u00e7\u00e3o",
    "Select 'Configuration on block' to configure a new LTI Tool. If the support staff provided you with a pre-configured LTI reusable Tool ID, select'Reusable Configuration' and enter it in the text field below.": "Seleccione 'Configuration on block' para configurar uma nova Ferramenta LTI. Se a equipa de suporte lhe tiver fornecido um ID de ferramenta reutiliz\u00e1vel LTI pr\u00e9-configurado, seleccione 'Configura\u00e7\u00e3o reutiliz\u00e1vel' e introduza-o no campo de texto abaixo.",
    "Select Inline if you want the LTI content to open in an IFrame in the current page. Select Modal if you want the LTI content to open in a modal window in the current page. Select New Window if you want the LTI content to open in a new browser window. This setting is only used when Hide External Tool is set to False.": "Selecione Inline se desejar que o conte\u00fado LTI seja aberto num IFrame na p\u00e1gina atual. Selecione modal se desejar que o conte\u00fado LTI seja aberto em uma janela modal na p\u00e1gina atual. Selecione nova janela se desejar que o conte\u00fado LTI seja aberto em uma nova janela do navegador. Essa configura\u00e7\u00e3o s\u00f3 \u00e9 usada quando ocultar ferramenta externa \u00e9 definida como false.",
    "Select True if this component will receive a numerical score from the external LTI system.": "Selecione Verdadeiro se a inten\u00e7\u00e3o for que este componente receba uma pontua\u00e7\u00e3o num\u00e9rica atrav\u00e9s do sistema externo LTI.",
    "Select True if you want to enable LTI Advantage Deep Linking.": "Selecione True se quiser activar LTI Advantage Deep Linking.",
    "Select True if you want to use this component as a placeholder for syncing with an external grading  system rather than launch an external tool.  This setting hides the Launch button and any IFrames for this component.": "Selecione Verdadeiro se desejar utilizar este componente como espa\u00e7o reservado para sincronizar com um sistema de classifica\u00e7\u00e3o externo em vez de iniciar uma ferramenta externa. Esta configura\u00e7\u00e3o oculta o bot\u00e3o Iniciar e qualquer IFrames para este componente.",
    "Select True to allow third party systems to post grades past the deadline.": "Selecione Verdadeiro para permitir que sistemas de terceiros publiquem notas ap\u00f3s a data limite.",
    "Select True to request the user's email address.": "Selecionar Verdadeiro para solicitar o email de utilizador.",
    "Select True to request the user's username.": "Selecionar Verdadeiro para solicitar o nome de utilizador",
    "Select True to send the extra parameters, which might contain Personally Identifiable Information. The processors are site-wide, please consult the site administrator if you have any questions.": "Seleccione True para enviar os par\u00e2metros extra, que podem conter Informa\u00e7\u00e3o Pessoal Identific\u00e1vel. Os processadores s\u00e3o em todo o site, por favor consulte o administrador do site se tiver alguma d\u00favida.",
    "Select how the tool's public key information will be specified.": "Selecione como as informa\u00e7\u00f5es de chave p\u00fablica da ferramenta ser\u00e3o especificadas.",
    "Select the LTI version that your tool supports.<br />The XBlock LTI Consumer fully supports LTI 1.1.1, LTI 1.3 and LTI Advantage features.": "Selecione a vers\u00e3o LTI compat\u00edvel com sua ferramenta.<br /> O XBlock LTI Consumer suporta totalmente os recursos LTI 1.1.1, LTI 1.3 e LTI Advantage.",
    "Send extra parameters": "Enviar par\u00e2metros extras",
    "Students don't have permissions to perform LTI Deep Linking configuration launches.": "Os alunos n\u00e3o t\u00eam permiss\u00e3o para executar inicializa\u00e7\u00f5es de configura\u00e7\u00e3o de LTI Deep Linking.",
    "The Deep Linking configuration stored is presented below:": "A configura\u00e7\u00e3o do Deep Linking armazenada \u00e9 apresentada a seguir:",
    "The LTI Deep Linking content was successfully saved in the LMS.": "O conte\u00fado LTI Deep Linking foi salvo com sucesso no LMS.",
    "The URL of the external tool that initiates the launch.": "URL da ferramenta externa que inicia a inicializa\u00e7\u00e3o.",
    "The score kept in the xblock KVS -- duplicate of the published score in django DB": "A pontua\u00e7\u00e3o mantida no xblock KVS -- duplicado da pontua\u00e7\u00e3o publicada no django DB",
    "The selected content type is not supported by Open edX.": "O tipo de conte\u00fado selecionado n\u00e3o \u00e9 suportado pelo Open edX.",
    "There was an error while launching the LTI tool.": "Ocorreu um erro ao lan\u00e7ar a ferramenta LTI.",
    "There was an error while starting your LTI proctored assessment.": "Ocorreu um erro ao iniciar a sua avalia\u00e7\u00e3o supervisionada LTI.",
    "To do that, make sure the block is published and click the link below:": "Para isso, certifique-se de que o bloco \u00e9 publicado e clique no link abaixo:",
    "To set up the LTI integration, you need to register the LMS in the tool with the information provided below.": "Para configurar a integra\u00e7\u00e3o LTI, voc\u00ea precisa se registar no LMS na ferramenta com as informa\u00e7\u00f5es fornecidas abaixo.",
    "Tool Initiate Login URL": "URL de in\u00edcio de sess\u00e3o da ferramenta",
    "Tool Keyset URL": "URL do conjunto de chaves da ferramenta",
    "Tool Launch URL": "URL de lan\u00e7amento da ferramenta",
    "Tool Public Key": "Ferramenta Chave P\u00fablica",
    "Tool Public Key Mode": "Modo de chave p\u00fablica da ferramenta",
    "Unauthorized.": "N\u00e3o autorizado.",
    "Valid urls the Tool may request us to redirect the id token to. The redirect uris are often the same as the launch url/deep linking url so if this field is empty, it will use them as the default. If you need to use different redirect uri's, enter them here. If you use this field you must enter all valid redirect uri's the tool may request.": "URLs v\u00e1lidos para os quais a ferramenta pode solicitar o redireccionamento do token de id. Os urls de redireccionamento s\u00e3o frequentemente os mesmos que o url de lan\u00e7amento/url de liga\u00e7\u00e3o profunda, pelo que, se este campo estiver vazio, ser\u00e3o utilizados como predefini\u00e7\u00e3o. Se precisar de utilizar URLs de redireccionamento diferentes, introduza-as aqui. Se utilizar este campo, tem de introduzir todos os uri de redireccionamento v\u00e1lidos que a ferramenta possa solicitar.",
    "You can configure this tool's content using LTI Deep Linking.": "Voc\u00ea pode configurar o conte\u00fado desta ferramenta usando LTI Deep Linking.",
    "You can safely close this page now.": "Voc\u00ea pode fechar esta p\u00e1gina com seguran\u00e7a agora.",
    "You don't have access to save LTI Content Items.": "Voc\u00ea n\u00e3o tem acesso para salvar itens de conte\u00fado LTI.",
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
        