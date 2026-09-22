
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
    "Display Name": "Nome de exibi\u00e7\u00e3o",
    "Enter the name that students see for this component. Analytics reports may also use the display name to identify this component.": "Forne\u00e7a o nome que os alunos ver\u00e3o para este componente. Os relat\u00f3rios de an\u00e1lise tamb\u00e9m poder\u00e3o usar o nome de exibi\u00e7\u00e3o para identificar este componente. ",
    "Inline Height": "Altura do embutido",
    "LTI Application Information": "Informa\u00e7\u00f5es do aplicativo LTI",
    "LTI Consumer": "Consumidor de LTI",
    "LTI ID": "ID do LTI",
    "Modal Height": "Altura do modal",
    "Modal Width": "Largura do modal",
    "No valid user id found in endpoint URL": "Nenhuma ID de usu\u00e1rio v\u00e1lido encontrada no ponto de extremidade da URL"
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
        