from django.core.management.base import BaseCommand
from django.db import transaction

from apps.permissions.catalog import DEFAULT_ROLES, PERMISSION_CATALOG
from apps.permissions.models import Permission, Role


class Command(BaseCommand):
    help = "Seed the RBAC permission catalog and default system roles (Admin/Operator/Viewer)."

    @transaction.atomic
    def handle(self, *args, **options):
        created_perms = 0
        for codename, description in PERMISSION_CATALOG.items():
            _, created = Permission.objects.update_or_create(codename=codename, defaults={"description": description})
            created_perms += int(created)

        created_roles = 0
        for role_name, codenames in DEFAULT_ROLES.items():
            role, created = Role.objects.get_or_create(name=role_name, organization=None, defaults={"is_system": True})
            role.is_system = True
            role.save(update_fields=["is_system"])
            role.permissions.set(Permission.objects.filter(codename__in=codenames))
            created_roles += int(created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(PERMISSION_CATALOG)} permissions ({created_perms} new) "
                f"and {len(DEFAULT_ROLES)} system roles ({created_roles} new)."
            )
        )
