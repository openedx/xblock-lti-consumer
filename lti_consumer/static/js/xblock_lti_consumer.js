function LtiConsumerXBlock(runtime, element) {

    var $element = $(element);

    $(function ($) {
        // Adapted from leanModal v1.1 by Ray Stone - http://finelysliced.com.au
        // Dual licensed under the MIT and GPL
        // Renamed leanModal to iframeModal to avoid clash with platform-provided leanModal
        // which removes the href attribute from iframe elements upon modal closing
        $.fn.extend({
            iframeModal: function (options) {
                var $trigger = $(this);
                var modal_id = "#" + $element.find(".lti-modal").attr("id");
                var defaults = {top: 100, overlay: 0.5, closeButton: null};
                var overlay_id = (modal_id + '_lean-overlay').replace('#', '');
                var overlay = $("<div id='" + overlay_id + "' class='lean-overlay'></div>");
                $("body").append(overlay);
                options = $.extend(defaults, options);
                return this.each(function () {
                    var o = options;
                    $(this).click(function (e) {
                        var $modal = $(modal_id);
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
                               $(modal_id).find('iframe')[0].contentWindow.focus();
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

        var $ltiContainer = $element.find('.lti-consumer-container');
        var askToSendUsername = $ltiContainer.data('ask-to-send-username') == 'True';
        var askToSendEmail = $ltiContainer.data('ask-to-send-email') == 'True';

        // Apply click handler to modal launch button
        $element.find('.btn-lti-modal').iframeModal({top: 200, closeButton: '.close-modal'});

        // Apply click handler to new window launch button
        $element.find('.btn-lti-new-window').click(function(){
            var launch = true;

            // If this instance is configured to require username and/or email, ask user if it is okay to send them
            // Do not launch if it is not okay
            if(askToSendUsername && askToSendEmail) {
                launch = confirm(gettext("Click OK to have your username and e-mail address sent to a 3rd party application.\n\nClick Cancel to return to this page without sending your information."));
            } else if (askToSendUsername) {
                launch = confirm(gettext("Click OK to have your username sent to a 3rd party application.\n\nClick Cancel to return to this page without sending your information."));
            } else if (askToSendEmail) {
                launch = confirm(gettext("Click OK to have your e-mail address sent to a 3rd party application.\n\nClick Cancel to return to this page without sending your information."));
            }

            if (launch) {
                window.open($(this).data('target'));
            }
        });
    });
}
