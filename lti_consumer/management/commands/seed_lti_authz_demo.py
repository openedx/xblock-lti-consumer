"""
Seed demo users, roles and configurations for trying LTI configuration permissions by hand.
"""

from django.core.management.base import BaseCommand
from django.urls import reverse

from lti_consumer.authz import demo

ACTION_LETTERS = {"view": "v", "create": "c", "edit": "e", "delete": "d"}


class Command(BaseCommand):
    """
    Load the authz schema and the worked-example demo data, then print what to check.
    """

    help = __doc__

    def handle(self, *args, **options):
        configs = demo.seed()

        self.stdout.write(f"Users (password '{demo.PASSWORD}'):")
        for username, assignments in demo.ASSIGNMENTS.items():
            roles = ", ".join(f"{role} @ {context}" for role, context in assignments)
            self.stdout.write(f"  {username:6} {roles}")
        self.stdout.write(f"  {demo.STAFF_USERNAME:6} global staff / superuser")

        self.stdout.write("\nConfigurations:")
        for name, config in configs.items():
            url = reverse("lti_consumer:lti-configurations-permissions", kwargs={"passport_id": config.passport_id})
            self.stdout.write(f"  {name}  {config.context_key:22} {url}")

        self.stdout.write("\nExpected permissions (v=view c=create e=edit d=delete, - = none):")
        self.stdout.write("  " + " " * 6 + "".join(f" {name:5}" for name in configs))
        for username, expected in demo.EXPECTED.items():
            cells = []
            for name in configs:
                letters = "".join(letter for action, letter in ACTION_LETTERS.items() if name in expected[action])
                cells.append(f" {letters or '-':5}")
            self.stdout.write(f"  {username:6}" + "".join(cells))
