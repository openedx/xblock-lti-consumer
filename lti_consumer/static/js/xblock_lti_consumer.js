function LtiConsumerXBlock(runtime, element) {
    var gettext;
    if ('XBlockLtiConsumerI18N' in window) {
        // Use local translations
        gettext = function(string) {
            var translated = window.XBlockLtiConsumerI18N.gettext(string);
            // if lti-consumer translation is the same as the input, check if global has a different value
            // This is useful for overriding the XBlock's string by themes (only for English)
            if (string === translated && 'gettext' in window) {
                translated = window.gettext(string);
            }
            return translated;
        };
    } else if ('gettext' in window) {
        // Use edxapp's global translations
        gettext = window.gettext;
    }

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
                        // LTI 1.1 launch URLs are XBlock handler URLs that point to the lti_launch_handler method of
                        // the XBlock. When we get the handler URL from the runtime, it returns a relative URL without a
                        // protocol or hostname. However, in LTI 1.3, the launch URLs come from user input, including
                        // the values of fields on the XBlock or fields in the database. These URLs should be absolute
                        // URLs with a protocol and hostname, so we should not prepend a protocol and hostname to those
                        // URLs.
                        var launch_url = $modal.data('launch-url');

                        if (ltiVersion === 'lti_1p1') {
                            launch_url = window.location.origin + launch_url
                        }

                        window.parent.postMessage(
                            {
                                'type': 'plugin.modal',
                                'payload': {
                                    'url': launch_url,
                                    'title': $modal.find('iframe').attr('title'),
                                    'width': $modal.data('width')
                                }
                            },
                            document.referrer
                        );
                        return;
                    }

                    // Set iframe src attribute to launch LTI provider.
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

            // In order to scope the dialog container to the lti-consumer-container, grab the ID of the
            // lti-consumer-container ancestor and append it to the ID of the dialog container.
            var container_id = triggerElement.closest(".lti-consumer-container").attr("id");
            var dialog_container_id = "dialog-container-" + container_id;

            // Hide the button that triggered the event, i.e. the launch button.
            triggerElement.hide();

            $('<div id="' + dialog_container_id + '"></div>').insertAfter(triggerElement) // TODO: this will need some cute styling. It looks like trash but it works.
                .append('<p>' + message + '</p>')

            var $dialog_container = $("#" + dialog_container_id);

            if (showCancelButton) {
                $dialog_container
                .append('<button style="margin-right:1rem" id="cancel-button">' + gettext("Cancel") + '</button>');
            }
            $dialog_container.append('<button id="confirm-button">' + gettext('OK') + '</button>');

            // When a learner clicks "OK" or "Cancel" in the consent dialog, remove the consent dialog, show the launch
            // button, and resolve the promise.
            $dialog_container.find('#confirm-button').click(function () {
                // Show the button that triggered the event, i.e. the launch button.
                triggerElement.show();
                $dialog_container.remove()
                $('body').append('<h1>Confirm Dialog Result: <i>Yes</i></h1>');
                def.resolve("OK");
            })
            $dialog_container.find('#cancel-button').click(function () {
                // Hide the button that triggered the event, i.e. the launch button.
                triggerElement.show()
                $dialog_container.remove()
                $('body').append('<h1>Confirm Dialog Result: <i>No</i></h1>');
                def.resolve("Cancel");
            })
            return def.promise();
        };

        var $element = $(element);
        var $ltiContainer = $element.find('.lti-consumer-container');
        var askToSendUsername = $ltiContainer.data('ask-to-send-username') == 'True';
        var askToSendFullName = $ltiContainer.data('ask-to-send-full-name') == 'True';
        var askToSendEmail = $ltiContainer.data('ask-to-send-email') == 'True';
        var ltiVersion = $ltiContainer.data('lti-version');

        function renderPIIConsentPromptIfRequired(onSuccess, showCancelButton=true) {
            if (askToSendUsername && askToSendFullName && askToSendEmail) {
                msg = gettext(
                    'Click OK to have your username, full name, and e-mail address sent to a 3rd party application.'
                );
            }
            else if (askToSendUsername && askToSendEmail) {
                msg = gettext('Click OK to have your username and e-mail address sent to a 3rd party application.');
            }
            else if (askToSendUsername && askToSendFullName) {
                msg = gettext('Click OK to have your username and full name sent to a 3rd party application.');
            }
            else if (askToSendFullName && askToSendEmail) {
                msg = gettext('Click OK to have your full name and e-mail address sent to a 3rd party application.');
            }
            else if (askToSendUsername) {
                msg = gettext('Click OK to have your username sent to a 3rd party application.');
            } else if (askToSendFullName) {
                msg = gettext('Click OK to have your full name sent to a 3rd party application.');
            } else if (askToSendEmail) {
                msg = gettext('Click OK to have your e-mail address sent to a 3rd party application.');
            } else {
                onSuccess('OK');
                return;
            }

            if (showCancelButton) {
                msg += '\n\n' + gettext('Click Cancel to return to this page without sending your information.');
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
