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
        const ltiVersionField = $(element).find('#xb-field-edit-lti_version');
        const selectedVersion = ltiVersionField.children("option:selected").val();
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
     *  new - Show all the LTI 1.1/1.3 config fields
     *  database - Do not show the LTI 1.1/1.3 config fields
     *  external - Show only the External Config ID field
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
        } else if (configType === "database") {
            // Hide the LTI 1.1 and LTI 1.3 fields. The XBlock will remain the source of truth for the lti_version,
            // so do not hide it and continue to allow editing it from the XBlock edit menu in Studio.
            databaseConfigHiddenFields.forEach(function (field) {
                fieldsToHide.push(field);
            })
        } else {
            // No fields should be hidden based on a config_type of 'new'.
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
        const configFields = lti1P1FieldList.concat(lti1P3FieldList);
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

    function initializeLtiToolAutocomplete() {
        const searchBoxSelector = "#xb-field-edit-launch_url"; // Selector for the launch URL input box
        const weightFieldSelector = "#xb-field-edit-weight";
        //const dropdownSelector = "#xb-field-edit-lti_tool_urls"; // Selector for the dropdown field

        let storedLtiTools = []; // To store the fetched tools

        // Fetch tools based on course_shortName and store them
        function fetchLtiTools(courseShortName, callback) {
            const api_url = "https://" + window.location.hostname + "/extras/get_lti_tool_urls";
            $.ajax({
                type: "POST",
                url: api_url,
                data: {
                    course_shortName: courseShortName
                },
                success: function (data) {
                    if (data.ltiTools) {
                        storedLtiTools = data.ltiTools; // Store the response
                        console.log(storedLtiTools);
                        callback(storedLtiTools); // Invoke callback with the data
                    } else {
                        console.error("Invalid API response:", data);
                        callback([]);
                    }
                },
                error: function (error) {
                    console.error("Error fetching LTI tools:", error);
                    callback([]);
                }
            });
        }

        // Filter stored tools based on the search term
        function filterTools(searchTerm) {
            return storedLtiTools.filter(tool =>
                tool.tool_name.toLowerCase().includes(searchTerm.toLowerCase())
            ).map(tool => ({
                label: tool.tool_name, 
                value: tool.tool_url,
                grade: tool.grade !== null ? tool.grade : "1.0"
            }));
        }

        $(searchBoxSelector).autocomplete({
            source: function (request, response) {
                const filteredTools = filterTools(request.term);
                response(filteredTools);
            },
            minLength: 2,
            autoFocus: true,
            delay: 200,
            select: function (event, ui) {
                $(searchBoxSelector).val(ui.item.value); // Update search box
                console.log("Selected tool:", ui.item);

                // Check if grade exists and update weight field
                if (ui.item.grade !== null) {
                    $(weightFieldSelector).val(ui.item.grade).trigger("change");
                } else {
                    console.log("Grade is null for the selected item.");
                }
            }
        }).on("input", function () {
            $(this).autocomplete("search");
        });        

        // Fetch tools on load using course_shortName
        const courseShortName = window.location.href.split("+")[1] + "|" + window.location.href.split("+")[2];
        fetchLtiTools(courseShortName, function () {
            console.log("Fetched LTI tools:", storedLtiTools);
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

    $(element).find('#xb-field-edit-config_type').bind('change', function () {
        toggleLtiFields();
    });

    if ($('#xb-field-edit-launch_url').length > 0) {
        initializeLtiToolAutocomplete();
    }

    $(element).find('.xblock-actions .save-button').on('click', function (e) {
        const lms_url = document.querySelector('.action-item .button-view').href;
        const selected_tool = $(element).find('#xb-field-edit-launch_url').val();
        if (selected_tool) {
            const update_moodle_block_url = "https://" + window.location.hostname + "/extras/update_moodle_block_url";
            $.ajax({
                type: "POST",
                url: update_moodle_block_url,
                data: {
                    lms_url: lms_url,
                    selected_tool: selected_tool
                },
                success: function (data) {
                    console.log(data);
                },
                error: function (error) {
                    console.error("Error while updating moodle block url:", error);
                }
            });
        }
    });
}
