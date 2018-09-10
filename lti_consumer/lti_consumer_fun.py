import logging

from .lti_consumer import LtiConsumerXBlock

from django.conf import settings


logger = logging.getLogger('__name__')


class FUNLtiConsumerXBlockBase(LtiConsumerXBlock):
    def __init__(self, *args, **kwargs):
        super(FUNLtiConsumerXBlockBase, self).__init__(*args, **kwargs)

        if not self._runtime.__class__.__name__ == "ImportSystem":
            # We do not need this when importing course in studio
            self.set_editable_field_names()

    @classmethod
    def get_template(cls, boilerplate):
        """
        Returns a dict that will be used by modulestore to initialize xblock
        fields
        """
        template = {}
        template['metadata'] = cls.get_configuration(
            boilerplate)["default_values"]
        return template

    def set_editable_field_names(self):
        """
        Remove from editable_field_names list fields that we already have configured
        """
        self.editable_field_names = list(self.editable_field_names)
        name = self.description
        for field, _ in self.get_configuration(name)['default_values'].items():
            self.editable_field_names.pop(self.editable_field_names.index(field))

    @classmethod
    def get_configuration(cls, name):
        """
        Retrieving component configuration from Django settings
        """
        for component in settings.XBLOCKS_FACTORY["components"]:
            if component["module"] == "lti_consumer":
                conf = [
                    subclass for subclass in component["subclasses"]
                    if subclass["name"] == name]
                if conf:
                    return conf[0]
        return None

    @property
    def lti_provider_key_secret(self):
        """
        Override parent's method to use credentials from Django settings if
        available instead of courses settings
        """
        name = self.description
        configuration = self.get_configuration(name)
        if "lti" in configuration:
            return configuration["lti"]["key"], configuration["lti"]["secret"]
        return super(FUNLtiConsumerXBlockBase, self).lti_provider_key_secret


def add_dynamic_components(XBLOCKS_FACTORY, advanced_component_templates,
       categories, create_template_dict, course_advanced_keys):
    """
    Reads XBLOCKS_FACTORY configuration to create related button in studio
    to instanciate configured xblocks
    """
    if XBLOCKS_FACTORY:
        for component in XBLOCKS_FACTORY['components']:
            for class_info in component["subclasses"]:
                display_name = class_info["display"]
                key = component["module"] + "_" + class_info["name"]
                advanced_component_templates['templates'].append(
                    create_template_dict(
                        name=display_name,
                        category=component["module"],
                        support_level=False,
                        boilerplate_name=class_info["name"]
                        )
                )
            # Remove original overrided component
            try:
                course_advanced_keys.pop(
                    course_advanced_keys.index(component['module'])
                )
            except ValueError:
                pass
