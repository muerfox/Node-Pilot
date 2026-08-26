from django.contrib import admin

from apps.permissions.models import Permission, Role, RoleAssignment

admin.site.register(Permission)
admin.site.register(Role)
admin.site.register(RoleAssignment)
