/**
 * Javascript for LTI Consumer Studio View.
*/
function LtiConsumerXBlockInitStudio(runtime, element) {
    // Run parent function to set up studio view base JS
    StudioEditableXBlockMixin(runtime, element);

    // Define LTI 1.1 and 1.3 fields
    const lti1P1FieldList = [
        "lti_id",
        "launch_url"
    ];

    const lti1P3FieldList = [
        "lti_1p3_launch_url",
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
     * Show or hide LTI fields depending on which version is selected in
     * the lti_version field.
     */
    function toggleLtiFields() {
        const ltiVersionField = $(element).find('#xb-field-edit-lti_version');
        const selectedVersion = ltiVersionField.children("option:selected").val();

        // If LTI version field isn't present, then LTI 1.3 support is disabled
        // so show all LTI 1.1 fields.
        if (selectedVersion === undefined) {
            lti1P1FieldList.forEach(function (field) {
                toggleFieldVisibility(field, true);
            });

            return false;
        }

        lti1P1FieldList.forEach(function (field) {
            toggleFieldVisibility(
                field,
                selectedVersion === "lti_1p1"
            );
        });

        lti1P3FieldList.forEach(function (field) {
            toggleFieldVisibility(
                field,
                selectedVersion === "lti_1p3"
            );
        });
    }

    /**
     * Only display the field appropriate for the selected key mode.
     */
    function toggleLtiToolKeyMode() {
        const ltiKeyModeField = $(element).find('#xb-field-edit-lti_1p3_tool_key_mode');

        // find the field containers
        const ltiKeysetUrlField = $(element).find('[data-field-name=lti_1p3_tool_keyset_url]');
        const ltiPublicKeyField = $(element).find('[data-field-name=lti_1p3_tool_public_key]');

        const selectedKeyMode = ltiKeyModeField.children("option:selected").val();
        if (selectedKeyMode === 'public_key') {
            ltiKeysetUrlField.hide();
            ltiPublicKeyField.show();
        } else if (selectedKeyMode === 'keyset_url') {
            ltiPublicKeyField.hide();
            ltiKeysetUrlField.show();
        }
    }

    /**
     * Toggle visibility of LTI configuration fields based on the config type
     *
     *  new - Show all the LTI 1.1/1.3 config fields
     *  database - Do not show the LTI 1.1/1.3 config fields
     *  external - Show only the External Config ID field
     */
    function toggleLtiConfigType() {
        const configType = $(element).find('#xb-field-edit-config_type').val();
        const configFields = lti1P1FieldList.concat(lti1P3FieldList, ['lti_version']);

        if ((configType === "external") || (configType === "database")) {
            // hide the lti_version and all the LTI 1.1 and LTI 1.3 fields
            configFields.forEach(function (field) {
                toggleFieldVisibility(field, false);
            })
        } else {
            // show the lti_version and toggleLtiFields to auto decide which fields are shown
            toggleFieldVisibility("lti_version", true);
            toggleLtiFields();
        }

        toggleFieldVisibility("external_config", configType === "external");
    }

    // Call once component is instanced to hide fields
    toggleLtiFields();
    toggleLtiToolKeyMode();
    toggleLtiConfigType();

    // Bind to onChange method of lti_version selector
    $(element).find('#xb-field-edit-lti_version').bind('change', function () {
        toggleLtiFields();
    });

    // Bind to onChange method of lti_1p3_tool_key_mode selector
    $(element).find('#xb-field-edit-lti_1p3_tool_key_mode').bind('change', function () {
        toggleLtiToolKeyMode();
    });

    $(element).find('#xb-field-edit-config_type').bind('change', function () {
        toggleLtiConfigType();
    });
}
