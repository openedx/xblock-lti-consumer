"""
openedx-authz integration for reusable LTI configurations.

The ``authz.schema`` entry point points at :func:`get_schema_resources`, so
openedx-authz's ``load_authz_schema`` command picks up the permissions and
roles in ``schema/``.
"""

SCHEMA_DIRECTORIES = ("lti_consumer/authz/schema",)


def get_schema_resources():
    """
    Return the package-anchored directories holding this package's authz schema.
    """
    return list(SCHEMA_DIRECTORIES)
