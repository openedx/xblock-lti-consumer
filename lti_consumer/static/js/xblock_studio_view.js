/**
 * Javascript for LTI Consumer Studio View.
 */
function LtiConsumerXBlockInitStudio(runtime, element, data) {
  let currentStep = "setup";

  /**
   * Query a field using the `data-field-name` attribute and hide/show it.
   *
   * @param {string} field - Value of the field's `data-field-name` attribute.
   * @param {boolean} visible - `true` shows the container, and `false` hides it.
   */
  function toggleFieldVisibility(field, visible) {
    const componentQuery = '[data-field-name="' + field + '"]';
    const fieldContainer = element.find(componentQuery);

    if (visible) {
      fieldContainer.removeClass("hidden");
    } else {
      fieldContainer.addClass("hidden");
    }
  }

  /**
   * Return the value of the selected radio button.
   * @param {string} fieldName - The name of the field to search for.
   * @returns {string} The value of the selected radio button.
   */
  function getRadioButtonValue(fieldName) {
    const options = $(element).find(`input[id^=${fieldName}_option-]`);

    for (let i = 0; i < options.length; i++) {
      if (options[i].checked) {
        return options[i].value;
      }
    }

    throw new Error(`No option selected for ${fieldName}`);
  }

  /**
   * Show or hide components depending on the selected lti_version and config_type.
   */
  function toggleLtiComponents() {
    const version = getRadioButtonValue("lti_version");
    let configType;
    try {
      configType = getFieldValue("config_type").value || "new";
    } catch (e) {
      // The waffle flag is not enabled, so we default to "new".
      configType = "new";
    }

    if (version === "lti_1p1") {
      $(element).find(".l1p1").removeClass("hidden");
      $(element).find(".l1p3").addClass("hidden");
    } else {
      $(element).find(".l1p1").addClass("hidden");
      $(element).find(".l1p3").removeClass("hidden");
      if (configType !== "new") {
        $(element).find(".no-external-config").addClass("hidden");
        $(element).find(".external-config").removeClass("hidden");
      } else {
        $(element).find(".external-config").addClass("hidden");
        $(element).find(".no-external-config").removeClass("hidden");
      }
    }

    if (configType === "new") {
      toggleFieldVisibility("lti_id", version === "lti_1p1");
      toggleFieldVisibility("external_config", false);
    } else {
      toggleFieldVisibility("lti_id", false);
      toggleFieldVisibility("external_config", true);
    }

    if (configType === "external") {
      if (data.EXTERNAL_MULTIPLE_LAUNCH_URLS_ENABLED) {
        // Conditionally show the LTI 1.3 launch URL field if external multiple launch URLs are enabled.
        toggleFieldVisibility("lti_1p3_launch_url", true);
        $(element).find(".field-group-lti-configuration-details.l1p3").removeClass("hidden");
      } else {
        toggleFieldVisibility("lti_1p3_launch_url", false);
        // Also hides the field-group-lti-configuration-details as it is empty in this case
        $(element).find(".field-group-lti-configuration-details.l1p3").addClass("hidden");
      }
    }
  }

  /*
   * Show or hide fields depending on the lti_advantage_deep_linking_enabled option.
   */
  function toggleDeepLinking() {
    const enabled = getRadioButtonValue("lti_advantage_deep_linking_enabled") === "true";

    $(element).find("[data-field-name=lti_advantage_deep_linking_launch_url]").toggleClass("hidden", !enabled);
  }

  /**
   * Show or hide fields depending on the selected has_score option.
   */
  function toggleHasScore() {
    const hasScore = getRadioButtonValue("has_score") === "true";
    const fields = ["weight", "accept_grades_past_due"];

    fields.forEach((field) => toggleFieldVisibility(field, hasScore));
  }

  /**
   * Show or hide fields depending on the selected hide_launch and launch_target options.
   */
  function toggleHideExternalTool() {
    const hideExternalTool = getRadioButtonValue("hide_launch") === "true";
    const fields = {
      inline_height: ["iframe"],
      modal_height: ["modal"],
      modal_width: ["modal"],
      button_text: ["modal", "new_window"],
    };

    const launchTarget = getRadioButtonValue("launch_target");

    if (hideExternalTool) {
      // Hide all related fields
      [
        "launch_target",
        ...Object.keys(fields), // Hide all fields in the object
      ].forEach((field) => toggleFieldVisibility(field, false));
    } else {
      toggleFieldVisibility("launch_target", true);

      // Set visibility according to the launch_target
      Object.entries(fields).forEach(([field, targets]) =>
        toggleFieldVisibility(field, targets.includes(launchTarget)),
      );
    }
  }

  /**
   * Show or hide fields related to the selected lti_1p3_tool_key_mode option.
   */
  function toggleLti1p3ToolKeyMode() {
    const deepLinkingEnabled = getRadioButtonValue("lti_advantage_deep_linking_enabled") === "true";
    const nprsEnabled = getRadioButtonValue("lti_1p3_enable_nrps") === "true";
    const agsModeEnabled = getRadioButtonValue("lti_advantage_ags_mode") !== "disabled";

    if (deepLinkingEnabled || nprsEnabled || agsModeEnabled) {
      $(element).find("[data-field-name=lti_1p3_tool_key_mode]").removeClass("hidden");

      const keyMode = getRadioButtonValue("lti_1p3_tool_key_mode");

      if (keyMode === "public_key") {
        $(element).find("[data-field-name=lti_1p3_tool_keyset_url]").addClass("hidden");
        $(element).find("[data-field-name=lti_1p3_tool_public_key]").removeClass("hidden");
      } else if (keyMode === "keyset_url") {
        $(element).find("[data-field-name=lti_1p3_tool_keyset_url]").removeClass("hidden");
        $(element).find("[data-field-name=lti_1p3_tool_public_key]").addClass("hidden");
      } else {
        throw new Error("This should never happen");
      }
    } else {
      $(element).find("[data-field-name=lti_1p3_tool_key_mode]").addClass("hidden");
      $(element).find("[data-field-name=lti_1p3_tool_keyset_url]").addClass("hidden");
      $(element).find("[data-field-name=lti_1p3_tool_public_key]").addClass("hidden");
    }
  }

  /**
   * Hide the current step and deactivate the step header.
   *
   * @param {string} step - The step to deactivate.
   */
  function deactivateCurrentStep() {
    $(element).find(`.step-header-${currentStep}`).removeClass("pgn__stepper-header-step-active");
    $(element).find(`.step-${currentStep}`).addClass("hidden");
  }

  /**
   * Show the current step and activate the step header.
   *
   * @param {string} step - The step to activate.
   */
  function activateCurrentStep() {
    $(element).find(`.step-header-${currentStep}`).addClass("pgn__stepper-header-step-active");
    $(element).find(`.step-${currentStep}`).removeClass("hidden");
  }

  /**
   * Change the current step.
   *
   * @param {string} step - The step to change to.
   */
  function changeStep(step) {
    deactivateCurrentStep();
    currentStep = step;
    activateCurrentStep();
    handlePrevNextButtonVisibility();
  }

  // Show or hide fields based on the selected options
  toggleLtiComponents();
  toggleDeepLinking();
  toggleLti1p3ToolKeyMode();
  toggleHasScore();
  toggleHideExternalTool();

  // Bind events to input/select fields to mark the field as set
  $(element)
    .find(".field-data-control")
    .bind("change input paste", function () {
      // Add a class to the field to indicate that the value has been changed
      const wrapper = $(this).closest("li.field");
      $(wrapper).addClass("is-set");
    });

  // Bind events to radio fields to mark the field as set
  $(element)
    .find("input[type=radio]")
    .bind("change", function () {
      // Add a class to the field to indicate that the value has been changed
      const wrapper = $(this).closest("li.field");
      $(wrapper).addClass("is-set");
    });

  // Bind to onChange method of lti_version selector
  $(element)
    .find("[id^=lti_version_option-]")
    .bind("change", function () {
      toggleLtiComponents();
    });

  // Bind to onChange method of lti_advantage_deep_linking_enabled selector
  $(element)
    .find("[id^=lti_advantage_deep_linking_enabled_option-]")
    .bind("change", function () {
      toggleDeepLinking();
      toggleLti1p3ToolKeyMode();
    });

  // Bind to onChange method of lti_1p3_enable_nrps selector
  $(element)
    .find("[id^=lti_1p3_enable_nrps_option-]")
    .bind("change", function () {
      toggleLti1p3ToolKeyMode();
    });

  // Bind to onChange method of lti_advantage_ags_mode selector
  $(element)
    .find("[id^=lti_advantage_ags_mode_option-]")
    .bind("change", function () {
      toggleLti1p3ToolKeyMode();
    });

  // Bind to onChange method of has_score selector
  $(element)
    .find("[id^=has_score_option-]")
    .bind("change", function () {
      toggleHasScore();
    });

  // Bind to onChange method of hide_launch selector
  $(element)
    .find("[id^=hide_launch_option-]")
    .bind("change", function () {
      toggleHideExternalTool();
    });

  // Bind to onChange method of launch_target selector
  $(element)
    .find("[id^=launch_target_option-]")
    .bind("change", function () {
      toggleHideExternalTool();
    });

  // Bind to onChange method of lti_1p3_tool_key_mode selector
  $(element)
    .find("[id^=lti_1p3_tool_key_mode_option-]")
    .bind("change", function () {
      toggleLti1p3ToolKeyMode();
    });

  // Bind to onChange method of config_type selector
  $(element)
    .find("[id^=xb-field-edit-config_type]")
    .bind("change", function () {
      toggleLtiComponents();
    });

  $(element)
    .find(".cancel-button")
    .bind("click", function () {
      runtime.notify("cancel", {});
    });

  function handlePrevNextButtonVisibility() {
    if (currentStep === "setup") {
      $(element).find(".previous-button").closest("li").addClass("hidden");
    } else {
      $(element).find(".previous-button").closest("li").removeClass("hidden");
    }

    if (currentStep === "review") {
      $(element).find(".next-button").closest("li").addClass("hidden");
      $(element).find(".save-button").closest("li").removeClass("hidden");
    } else {
      $(element).find(".next-button").closest("li").removeClass("hidden");
      $(element).find(".save-button").closest("li").addClass("hidden");
    }
  }

  $(element)
    .find(".next-button")
    .bind("click", function (e) {
      e.preventDefault();
      let nextStep;
      const version = getRadioButtonValue("lti_version");

      if (currentStep === "setup") {
        if (version === "lti_1p1") {
          nextStep = "review";
        } else {
          nextStep = "advantage";
        }
      } else if (currentStep === "advantage") {
        nextStep = "review";
      } else if (currentStep === "review") {
        throw new Error("This should never happen");
      }
      changeStep(nextStep);
    });

  $(element)
    .find(".previous-button")
    .bind("click", function (e) {
      e.preventDefault();
      let previousStep;
      const version = getRadioButtonValue("lti_version");

      if (currentStep === "setup") {
        throw new Error("This should never happen");
      } else if (currentStep === "advantage") {
        previousStep = "setup";
      } else if (currentStep === "review") {
        if (version === "lti_1p1") {
          previousStep = "setup";
        } else {
          previousStep = "advantage";
        }
      }
      changeStep(previousStep);
    });

  $(element)
    .find(".step-header-setup-link")
    .bind("click", function (e) {
      e.preventDefault();
      changeStep("setup");
    });

  $(element)
    .find(".step-header-advantage-link")
    .bind("click", function (e) {
      e.preventDefault();
      changeStep("advantage");
    });

  $(element)
    .find(".step-header-review-link")
    .bind("click", function (e) {
      e.preventDefault();
      changeStep("review");
    });

  /**
   * Return whether the field is set or not.
   *
   * @param {Element} field - The field to check.
   * @returns {boolean}  Whether the field is set or not.
   */
  function getIsSet(field) {
    const wrapper = $(field).closest("li.field");
    return $(wrapper).hasClass("is-set");
  }

  /**
   * Return the value of the field, or `null` if the field is not set.
   *
   * @param {string} fieldName - The name of the field to get the value of.
   * @returns {{isSet: boolean, value: string | null}} The value of the field, or `null` if the field is not set.
   */
  function getFieldValue(fieldName) {
    const field = $(element).find(`#xb-field-edit-${fieldName}`);
    let value;
    let isSet;

    if (field.length === 0) {
      // This is not a text/select field (or is not present), so we get the value of the select option.
      const options = $(element).find(`input[id^=${fieldName}_option-]`);
      if (options.length === 0) {
        // The field is not present, so we return isSet = false and value = null.
        return {
          isSet: false,
          value: null,
        };
      }
      return {
        isSet: getIsSet(options[0]),
        value: getRadioButtonValue(fieldName),
      };
    } else {
      isSet = getIsSet(field);
      if (field.attr("type") === "checkbox") {
        value = field.prop("checked");
      } else {
        value = field.val();
      }
      return {
        isSet,
        value,
      };
    }
  }

  $(element)
    .find(".save-button")
    .bind("click", function () {
      const { editableFields } = data;
      const handlerUrl = runtime.handlerUrl(element, "submit_studio_edits");
      const submitData = { values: {}, defaults: [] };
      for (const field of editableFields) {
        const { isSet, value } = getFieldValue(field);
        if (isSet) {
          submitData.values[field] = value;
        } else {
          submitData.defaults.push(field);
        }
      }

      // Transform the custom_parameters field into a list
      if ("custom_parameters" in submitData.values) {
        const customParameters = submitData.values.custom_parameters;
        try {
          submitData.values.custom_parameters = JSON.parse(customParameters);
        } catch (e) {
          runtime.notify("error", {
            title: gettext("Unable to update settings"),
            message: gettext("Unable to parse the custom parameters."),
          });
          return;
        }
      }

      // Transform the lti_1p3_redirect_uris field into a list
      if ("lti_1p3_redirect_uris" in submitData.values) {
        const redirectUris = submitData.values.lti_1p3_redirect_uris;
        try {
          submitData.values.lti_1p3_redirect_uris = JSON.parse(redirectUris);
        } catch (e) {
          runtime.notify("error", {
            title: gettext("Unable to update settings"),
            message: gettext("Unable to parse the redirect URIs."),
          });
          return;
        }
      }

      runtime.notify("save", { state: "start" });

      $.ajax({
        type: "POST",
        url: handlerUrl,
        data: JSON.stringify(submitData),
        dataType: "json",
        contentType: "application/json",
        global: false,
        success: function () {
          runtime.notify("save", { state: "end" });
        },
      }).fail(function (jqXHR) {
        var message = gettext(
          "This may be happening because of an error with our server or your internet connection. Try refreshing the page or making sure you are online.",
        );
        if (jqXHR.responseText) {
          try {
            message = JSON.parse(jqXHR.responseText).error;
            if (typeof message === "object" && message.messages) {
              // e.g. {"error": {"messages": [{"text": "Unknown user 'bob'!", "type": "error"}, ...]}} etc.
              message = $.map(message.messages, function (msg) {
                return msg.text;
              }).join(", ");
            }
          } catch (error) {
            message = jqXHR.responseText.substr(0, 300);
          }
        }
        runtime.notify("error", { title: gettext("Unable to update settings"), message: message });
      });
    });
}
