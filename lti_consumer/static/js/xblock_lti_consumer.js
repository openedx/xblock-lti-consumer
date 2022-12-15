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
                var defaults = { top: 100, overlay: 0.5, closeButton: null };
                var overlay_id = (modal_id + '_lean-overlay').replace('#', '');
                var overlay = $("<div id='" + overlay_id + "' class='lean-overlay'></div>");
                $("body").append(overlay);
                options = $.extend(defaults, options);
                return this.each(function () {
                    var o = options;

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
                    $("#" + overlay_id).css({ "display": "block", opacity: 0 });
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
                    $inputs.on('focus', function (e) {
                        e.preventDefault();
                        $(options.closeButton).focus();
                    });

                });
                function close_modal(modal_id) {
                    var $modal = $(modal_id);
                    $('select, input, textarea, button, a').off('focus');
                    $("#" + overlay_id).fadeOut(200);
                    $modal.css({ "display": "none" });
                    $modal.attr('aria-hidden', true);
                    $modal.find('iframe').attr('src', '');
                    $('body').css('overflow', 'auto');
                    $trigger.focus();
                }
            }
        });

        function confirmDialog(message, triggerElement, showCancelButton) {
            var def = $.Deferred();
            // Hide the button that triggered the event, i.e. the launch button.
            triggerElement.hide();

            $('<div id="dialog-container"></div>').insertAfter(triggerElement) // TODO: this will need some cute styling. It looks like trash but it works.
                .append('<p>' + message + '</p>')
            if (showCancelButton) {
                $('#dialog-container')
                .append('<button style="margin-right:1rem" id="cancel-button">Cancel</button>');
            }
            $('#dialog-container').append('<button id="confirm-button">OK</button>');

            // When a learner clicks "OK" or "Cancel" in the consent dialog, remove the consent dialog, show the launch
            // button, and resolve the promise.
            $('#confirm-button').click(function () {
                // Show the button that triggered the event, i.e. the launch button.
                triggerElement.show();
                $("#dialog-container").remove()
                $('body').append('<h1>Confirm Dialog Result: <i>Yes</i></h1>');
                def.resolve("OK");
            })
            $('#cancel-button').click(function () {
                // Hide the button that triggered the event, i.e. the launch button.
                triggerElement.show()
                $("#dialog-container").remove()
                $('body').append('<h1>Confirm Dialog Result: <i>No</i></h1>');
                def.resolve("Cancel");
            })
            return def.promise();
        };

        var $element = $(element);
        var $ltiContainer = $element.find('.lti-consumer-container');
        var askToSendUsername = $ltiContainer.data('ask-to-send-username') == 'True';
        var askToSendEmail = $ltiContainer.data('ask-to-send-email') == 'True';

        function renderPIIConsentPromptIfRequired(onSuccess, showCancelButton=true) {
            if (askToSendUsername && askToSendEmail) {
                msg = gettext("Click OK to have your username and e-mail address sent to a 3rd party application.\n\nClick Cancel to return to this page without sending your information.");
            } else if (askToSendUsername) {
                msg = gettext("Click OK to have your username sent to a 3rd party application.\n\nClick Cancel to return to this page without sending your information.");
            } else if (askToSendEmail) {
                msg = gettext("Click OK to have your e-mail address sent to a 3rd party application.\n\nClick Cancel to return to this page without sending your information.");
            } else {
                onSuccess("OK");
                return;
            }
            $.when(confirmDialog(msg, $(this), showCancelButton)).then(onSuccess);
        }

        // Render consent dialog for inline elements immediately.
        var $ltiIframeContainerElement = $element.find('#lti-iframe-container');
        $ltiIframeContainerElement.each(function () {
            var ltiIframeTarget = $ltiIframeContainerElement.data('target')
            renderPIIConsentPromptIfRequired.apply(this, [
                function (status) {
                    if (status === 'OK') {
                        // After getting consent to share PII, set the src attribute of the iframe to start the launch.
                        $ltiIframeContainerElement.find('iframe').attr('src', ltiIframeTarget);
                    }
                },
                false
            ]);
        })

        // Apply click handler to modal launch button.
        var $ltiModalButton = $element.find('.btn-lti-modal');
        $ltiModalButton.click(function () {
            renderPIIConsentPromptIfRequired.apply(this, [
                function (status) {
                    if (status === 'OK') {
                        $ltiModalButton.iframeModal({
                            top: 200, closeButton: '.close-modal'
                        })
                    }
                }
            ]);
        });

        // Apply click handler to new window launch button.
        var $ltiNewWindowButton = $element.find('.btn-lti-new-window');
        $ltiNewWindowButton.click(function () {
            renderPIIConsentPromptIfRequired.apply(this, [
                function (status) {
                    if (status == "OK") {
                        window.open(
                            $ltiNewWindowButton.data('target')
                        );
                    }
                }
            ]);
        });
    });
}
