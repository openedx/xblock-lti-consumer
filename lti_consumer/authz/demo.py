"""
Demo data for reusable LTI configuration permissions.

Recreates the worked example from the LTI roles and permissions proposal, plus a
library. The ``seed_lti_authz_demo`` command loads it for manual testing and the
unit tests check :data:`EXPECTED` against it, so both use the same table.

Courses W, X and Y belong to MIT; course Z belongs to WGU; library L belongs to MIT.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from openedx_authz.api.users import assign_role_to_user_in_scope

from lti_consumer.models import Lti1p3Passport

from .permissions import INSTANCE_CONTEXT, assign_lti_manager, org_context

COURSE_W = "course-v1:MIT+W+2026"
COURSE_X = "course-v1:MIT+X+2026"
COURSE_Z = "course-v1:WGU+Z+2026"
LIBRARY_L = "lib:MIT:L"

# Configuration name -> context.
CONFIGS = {
    "A": COURSE_W,
    "B": org_context("MIT"),
    "C": COURSE_X,
    "D": INSTANCE_CONTEXT,
    "E": org_context("WGU"),
    "F": LIBRARY_L,
}

# Username -> (role, context) assignments. ``lti_manager`` goes through
# ``assign_lti_manager`` so org and instance grants fan out.
ASSIGNMENTS = {
    "user1": [("course_staff", COURSE_W)],
    "user2": [("lti_manager", org_context("MIT"))],
    "user3": [("lti_manager", COURSE_X)],
    "user4": [("lti_manager", INSTANCE_CONTEXT)],
    "user5": [("course_editor", COURSE_Z)],
    "user6": [("library_author", LIBRARY_L)],
}
STAFF_USERNAME = "staff"
PASSWORD = "demo"

ALL = set(CONFIGS)

# Username -> {action: configurations the user may perform it on}.
EXPECTED = {
    "user1": {"view": {"A", "B", "D"}, "create": {"A"}, "edit": {"A"}, "delete": set()},
    "user2": {"view": {"A", "B", "C", "D", "F"}, "create": {"A", "B", "C", "F"},
              "edit": {"A", "B", "C", "F"}, "delete": {"A", "B", "C", "F"}},
    "user3": {"view": {"B", "C", "D"}, "create": {"C"}, "edit": {"C"}, "delete": {"C"}},
    "user4": {"view": ALL, "create": ALL, "edit": ALL, "delete": ALL},
    "user5": {"view": {"D", "E"}, "create": set(), "edit": set(), "delete": set()},
    "user6": {"view": {"B", "D", "F"}, "create": {"F"}, "edit": {"F"}, "delete": set()},
    STAFF_USERNAME: {"view": ALL, "create": ALL, "edit": ALL, "delete": ALL},
}


def seed():
    """
    Load the authz schema, then create the demo users, role assignments and configurations.

    Safe to run more than once. Returns ``{config name: Lti1p3Passport}``.
    """
    # The command ignores verbosity, so discard its report.
    call_command("load_authz_schema", stdout=StringIO())

    user_model = get_user_model()
    for username in [*ASSIGNMENTS, STAFF_USERNAME]:
        user, _ = user_model.objects.get_or_create(username=username)
        user.is_staff = user.is_superuser = username == STAFF_USERNAME
        user.set_password(PASSWORD)
        user.save()

    for username, assignments in ASSIGNMENTS.items():
        for role, context_key in assignments:
            if role == "lti_manager":
                assign_lti_manager(username, context_key)
            else:
                assign_role_to_user_in_scope(username, role, context_key)

    configs = {}
    for name, context_key in CONFIGS.items():
        configs[name], _ = Lti1p3Passport.objects.update_or_create(
            name=f"Config {name}",
            defaults={
                "context_key": context_key,
                "lti_1p3_tool_keyset_url": f"https://tool-{name.lower()}.example.com/.well-known/jwks.json",
            },
        )
    return configs
