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
        "lti_1p3_tool_public_key"
    ];

    /**
     * Query a field using the `data-field-name` attribute and hide/show it.
     *
     * params:
     *   field: string. Value of the field's `data-field-name` attribute.
     *   visible: boolean. `true` shows the container, and `false` hides it.
     */
    function toggleFieldVisibility(field, visible) {
        const componentQuery = '[data-field-name="'+ field + '"]';
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

    // Call once component is instanced to hide fields
    toggleLtiFields();

    // Bind to onChange method of lti_version selector
    $(element).find('#xb-field-edit-lti_version').bind('change', function() {
        toggleLtiFields();
     });

}
