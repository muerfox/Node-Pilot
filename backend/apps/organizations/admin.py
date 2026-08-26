from django.contrib import admin

from apps.organizations.models import Membership, Organization, Project, Quota

admin.site.register(Organization)
admin.site.register(Project)
admin.site.register(Membership)
admin.site.register(Quota)
