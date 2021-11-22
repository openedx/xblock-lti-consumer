function LtiConsumerXBlock(runtime, element) {
    $(function ($) {
        // Adapted from leanModal v1.1 by Ray Stone - http://finelysliced.com.au
        // Dual licensed under the MIT and GPL
        // Renamed leanModal to iframeModal to avoid clash with platform-provided leanModal
        // which removes the href attribute from iframe elements upon modal closing
        $.fn.extend({
            iframeModal: function (options) {
                var $trigger = $(this);
                var modal_id = $trigger.data("target");
                var defaults = {top: 100, overlay: 0.5, closeButton: null};
                var overlay_id = (modal_id + '_lean-overlay').replace('#', '');
                var overlay = $("<div id='" + overlay_id + "' class='lean-overlay'></div>");
                $("body").append(overlay);
                options = $.extend(defaults, options);
                return this.each(function () {
                    var o = options;
                    $(this).click(function (e) {
                        var $modal = $(modal_id);
                        // If we are already in an iframe, skip creation of the modal, since
                        // it won't look good, anyway. Instead, we post a message to the parent
                        // window, requesting creation of a modal there.
                        // This is used by the courseware microfrontend.
                        if (window !== window.parent) {
                            window.parent.postMessage(
                                {
                                    'type': 'plugin.modal',
                                    'payload': {
                                        'url': window.location.origin + $modal.data('launch-url'),
                                        'title': $modal.find('iframe').attr('title'),
                                        'width': $modal.data('width')
                                    }
                                },
                                document.referrer
                            );
                            return;
                        }
                        // Set iframe src attribute to launch LTI provider
                        $modal.find('iframe').attr('src', $modal.data('launch-url'));
                        $("#" + overlay_id).click(function () {
                            close_modal(modal_id)
                        });
                        $(o.closeButton).click(function () {
                            close_modal(modal_id)
                        });
                        var modal_height = $(modal_id).outerHeight();
                        var modal_width = $(modal_id).outerWidth();
                        $("#" + overlay_id).css({"display": "block", opacity: 0});
                        $("#" + overlay_id).fadeTo(200, o.overlay);
                        $(modal_id).css({
                            "display": "block"
                        });
                        $(modal_id).fadeTo(200, 1);
                        $(modal_id).attr('aria-hidden', false);
                        $('body').css('overflow', 'hidden');

                        e.preventDefault();

                        /* Manage focus for modal dialog */
                        /* Set focus on close button */
                        $(o.closeButton).focus();

                        /* Redirect close button to iframe */
                        $(o.closeButton).on('keydown', function (e) {
                           if (e.which === 9) {
                               e.preventDefault();
                               // This is a workaround due to Firefox triggering focus calls oddly.
                               setTimeout(function () {
                                   $modal.find('iframe')[0].contentWindow.focus();
                               }, 1);
                           }
                        });

                        /* Redirect non-iframe tab to close button */
                        var $inputs = $('select, input, textarea, button, a').filter(':visible').not(o.closeButton);
                        $inputs.on('focus', function(e) {
                            e.preventDefault();
                            $(options.closeButton).focus();
                        });
                    });
                });
                function close_modal(modal_id) {
                    var $modal = $(modal_id);
                    $('select, input, textarea, button, a').off('focus');
                    $("#" + overlay_id).fadeOut(200);
                    $modal.css({"display": "none"});
                    $modal.attr('aria-hidden', true);
                    $modal.find('iframe').attr('src', '');
                    $('body').css('overflow', 'auto');
                    $trigger.focus();
                }
            }
        });

        var $element = $(element);
        var $ltiContainer = $element.find('.lti-consumer-container');
        var askToSendUsername = $ltiContainer.data('ask-to-send-username') == 'True';
        var askToSendEmail = $ltiContainer.data('ask-to-send-email') == 'True';

        // Apply click handler to modal launch button
        $element.find('.btn-lti-modal').iframeModal({top: 200, closeButton: '.close-modal'});

        // Apply click handler to new window launch button
        $element.find('.btn-lti-new-window').click(function(){

            // If this instance is configured to require username and/or email, ask user if it is okay to send them
            // Do not launch if it is not okay
            var destination = $(this).data('target')

            function confirmDialog(message) {
                var def = $.Deferred();
                $('<div></div>').appendTo('body') // TODO: this will need some cute styling. It looks like trash but it works.
                  .html('<div><p>' + message + '</p></div>')
                  .dialog({
                    modal: true,
                    title: 'Confirm',
                    zIndex: 10000,
                    autoOpen: true,
                    width: 'auto',
                    resizable: false,
                    dialogClass: 'confirm-dialog',
                    buttons: {
                      OK: function() {
                        $('body').append('<h1>Confirm Dialog Result: <i>Yes</i></h1>');
                        def.resolve("OK");
                        $(this).dialog("close");
                      },
                      Cancel: function() {
                        $('body').append('<h1>Confirm Dialog Result: <i>No</i></h1>');
                        def.resolve("Cancel");
                        $(this).dialog("close");
                      }
                    },
                    close: function(event, ui) {
                      $(this).remove();
                    }
                  }).prev().css('background', 'white').css('color', '#000').css('border-color', 'transparent');
                return def.promise();
              };

            if(askToSendUsername && askToSendEmail) {
                msg = gettext("Click OK to have your username and e-mail address sent to a 3rd party application.\n\nClick Cancel to return to this page without sending your information.");
            } else if (askToSendUsername) {
                msg = gettext("Click OK to have your username sent to a 3rd party application.\n\nClick Cancel to return to this page without sending your information.");
            } else if (askToSendEmail) {
                msg = gettext("Click OK to have your e-mail address sent to a 3rd party application.\n\nClick Cancel to return to this page without sending your information.");
            } else {
                window.open(destination);
            }
            $.when(confirmDialog(msg)).then(
                function(status) {
                    if (status == "OK") {
                        window.open(destination);
                    }
                }
            );
        });
    });
}
