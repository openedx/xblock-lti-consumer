/**
 * Javascript for LTI Consumer Studio View.
*/
function LtiConsumerXBlockInitStudio(runtime, element, data) {
    // Run parent function to set up studio view base JS
    StudioEditableXBlockMixin(runtime, element);

    // Define LTI 1.1 and 1.3 fields
    const lti1P1FieldList = [
        "lti_id",
        "launch_url"
    ];

    // The effective LTI version for a reusable ("external") config. Seeded with the value the
    // server resolved for the *saved* config, then refreshed over the handler whenever
    // config_type or external_config changes, so switching to "Reusable Configuration" in an
    // unsaved editor session does not filter on the block's stale `lti_version`.
    // `null` means "not resolved yet" and suppresses version-based filtering entirely, so a
    // field is never hidden on the strength of a value we do not have.
    let effectiveLtiVersion = data.EFFECTIVE_LTI_VERSION;

    const lti1P3FieldList = [
        "lti_1p3_launch_url",
        "lti_1p3_redirect_uris",
        "lti_1p3_oidc_url",
        "lti_1p3_tool_key_mode",
        "lti_1p3_tool_keyset_url",
        "lti_1p3_tool_public_key",
        "lti_advantage_ags_mode",
        "lti_advantage_deep_linking_enabled",
        "lti_advantage_deep_linking_launch_url",
        "lti_1p3_enable_nrps"
    ];

    /**
     * Query a field using the `data-field-name` attribute and hide/show it.
     *
     * params:
     *   field: string. Value of the field's `data-field-name` attribute.
     *   visible: boolean. `true` shows the container, and `false` hides it.
     */
    function toggleFieldVisibility(field, visible) {
        const componentQuery = '[data-field-name="' + field + '"]';
        const fieldContainer = element.find(componentQuery);

        if (visible) {
            fieldContainer.show();
        } else {
            fieldContainer.hide();
        }
    }

    /**
     * Return fields that should be hidden based on the selected lti version.
     */
    function getFieldsToHideForLtiVersion() {
        const configType = $(element).find('#xb-field-edit-config_type').val();
        let selectedVersion;

        if (configType === "external") {
            // For reusable configs the `lti_version` select is hidden (see
            // getFieldsToHideForLtiConfigType) and its stored value is not the version the
            // launch actually uses, so filtering on it would hide fields based on a stale
            // value -- including `lti_1p3_launch_url`, which that filter deliberately keeps
            // visible when external multiple launch URLs are enabled. Use the resolved
            // version instead, and hide nothing on version grounds until we have one.
            if (effectiveLtiVersion === null || effectiveLtiVersion === undefined) {
                return [];
            }
            selectedVersion = effectiveLtiVersion;
        } else {
            const ltiVersionField = $(element).find('#xb-field-edit-lti_version');
            selectedVersion = ltiVersionField.children("option:selected").val();
        }

        const fieldsToHide = [];

        if (selectedVersion === undefined || selectedVersion === "lti_1p1") {
            // If LTI version field isn't present, then LTI 1.3 support is disabled
            // so hide all LTI 1.3 fields. If the LTI version is LTI 1.1, also hide all LTI
            // 1.3 fields.
            lti1P3FieldList.forEach(function (field) {
                fieldsToHide.push(field);
            });
        } else if (selectedVersion === "lti_1p3") {
            lti1P1FieldList.forEach(function (field) {
                fieldsToHide.push(field);
            });
        } else { }

        return fieldsToHide;
    }


    /**
     * Return fields that should be hidden based on the selected config type.
     *
     *  new - Show all the LTI 1.1/1.3 config fields. Hide the Reusable Configuration ID field.
     *  database - Do not show the LTI 1.1/1.3 config fields. Hide the Reusable Configuration ID field.
     *  external - Show only the Reusable Configuration ID field. Hide LTI version, since it is
     *             determined by the reusable config itself, not editable on this block.
     */
    function getFieldsToHideForLtiConfigType() {
        const configType = $(element).find('#xb-field-edit-config_type').val();
        const databaseConfigHiddenFields = lti1P1FieldList.concat(lti1P3FieldList);
        const externalConfigHiddenFields = lti1P1FieldList.concat(lti1P3FieldList);
        const fieldsToHide = [];

        if (configType === "external") {
            // Hide LTI 1.1 and LTI 1.3 tool fields.
            externalConfigHiddenFields.forEach(function (field) {
                fieldsToHide.push(field);
            })
            // Conditionally show the LTI 1.3 launch URL field if external multiple launch URLs are enabled.
            if (data.EXTERNAL_MULTIPLE_LAUNCH_URLS_ENABLED) {
                const index = fieldsToHide.indexOf("lti_1p3_launch_url");
                if (index > -1) {
                    fieldsToHide.splice(index, 1);
                }
            }
            // LTI version is determined by the reusable config, not editable on this block.
            fieldsToHide.push("lti_version");
        } else if (configType === "database") {
            // Hide the LTI 1.1 and LTI 1.3 fields. The XBlock will remain the source of truth for the lti_version,
            // so do not hide it and continue to allow editing it from the XBlock edit menu in Studio.
            databaseConfigHiddenFields.forEach(function (field) {
                fieldsToHide.push(field);
            })
            // Reusable Configuration ID is not applicable for database-backed configuration.
            fieldsToHide.push("external_config");
        } else {
            // config_type of 'new': show all LTI 1.1/1.3 fields (handled above/below).
            // Reusable Configuration ID is not applicable when configuring the tool directly on the block.
            fieldsToHide.push("external_config");
        }

        return fieldsToHide;
    }

    /**
     * Return fields that should be hidden based on the selected key mode. This returns a list of of fields related to
     * lti tool key mode that should be hidden.
     */
    function getFieldsToHideForLtiToolKeyMode() {
        const ltiKeyModeField = $(element).find('#xb-field-edit-lti_1p3_tool_key_mode');
        const selectedKeyMode = ltiKeyModeField.children("option:selected").val();
        const fieldsToHide = [];

        if (selectedKeyMode === 'public_key') {
            fieldsToHide.push("lti_1p3_tool_keyset_url");
        } else if (selectedKeyMode === 'keyset_url') {
            fieldsToHide.push("lti_1p3_tool_public_key");
        }

        return fieldsToHide;
    }

    /**
     * Show or hide fields depending on the selected lti_version, config_type, and lti_1p3_tool_key_mode.
     */
    function toggleLtiFields() {
        // lti_version and external_config are toggled based on config_type (see
        // getFieldsToHideForLtiConfigType), not on the LTI 1.1/1.3 field lists, but they still
        // need to be reset to visible here so a later config_type change can show them again.
        const configFields = lti1P1FieldList.concat(lti1P3FieldList).concat(["lti_version", "external_config"]);
        const hiddenFields = new Set();

        // Start with the assumption that all configFields should be visible. After that, we whittle down the
        // list of visible fields based on the values of those fields.
        configFields.forEach(function (field) {
            toggleFieldVisibility(
                field,
                true
            );
        });

        let fieldsToHide;
        const hiddenFieldsFilters = [
            getFieldsToHideForLtiVersion,
            getFieldsToHideForLtiConfigType,
            getFieldsToHideForLtiToolKeyMode
        ];

        hiddenFieldsFilters.forEach(function (filter) {
            fieldsToHide = filter();

            fieldsToHide.forEach(function (field) {
                hiddenFields.add(field);
            })
        })

        for (const field of hiddenFields) {
            toggleFieldVisibility(field, false);
        }
    }

    /**
     * Refresh the effective LTI version for a reusable config, then re-apply the filters.
     *
     * The server can only resolve the version of the *saved* config, so switching Configuration
     * Type to "Reusable Configuration" - or editing the config ID - within one editor session
     * would otherwise keep filtering on a stale version, with the `lti_version` select hidden
     * and no way to correct it. This asks the block to resolve the ID currently in the form.
     */
    function refreshEffectiveLtiVersion() {
        const configType = $(element).find('#xb-field-edit-config_type').val();

        if (configType !== "external") {
            // Non-external configs filter on the visible `lti_version` select, so nothing to
            // resolve. Drop any previously resolved value so returning to "external" re-resolves.
            effectiveLtiVersion = null;
            toggleLtiFields();
            return;
        }

        const configId = $(element).find('#xb-field-edit-external_config').val();
        if (!configId) {
            // No ID to resolve yet. Leave the version unresolved rather than guessing, so the
            // LTI 1.3 fields stay reachable while the author is still filling the form in.
            effectiveLtiVersion = null;
            toggleLtiFields();
            return;
        }

        $.ajax({
            type: "POST",
            url: runtime.handlerUrl(element, 'resolve_external_config_version'),
            data: JSON.stringify({config_id: configId}),
            contentType: "application/json",
            dataType: "json"
        }).done(function (response) {
            effectiveLtiVersion = (response && response.found) ? response.version : null;
        }).fail(function () {
            // Lookup unavailable: stay unresolved rather than filtering on a guess.
            effectiveLtiVersion = null;
        }).always(function () {
            toggleLtiFields();
        });
    }

    // Call once component is instanced to hide fields
    toggleLtiFields();

    // Bind to onChange method of lti_version selector
    $(element).find('#xb-field-edit-lti_version').bind('change', function () {
        toggleLtiFields();
    });

    // Bind to onChange method of lti_1p3_tool_key_mode selector
    $(element).find('#xb-field-edit-lti_1p3_tool_key_mode').bind('change', function () {
        toggleLtiFields();
    });

    // Configuration Type drives which config the version comes from, so re-resolve rather
    // than just re-filtering. refreshEffectiveLtiVersion() calls toggleLtiFields() itself.
    $(element).find('#xb-field-edit-config_type').bind('change', function () {
        refreshEffectiveLtiVersion();
    });

    // Editing the reusable config ID changes which config the version comes from.
    $(element).find('#xb-field-edit-external_config').bind('change', function () {
        refreshEffectiveLtiVersion();
    });
}
