from django.contrib import admin

from apps.virtual_machines.models import VirtualMachine, VMDisk, VMNic


class VMDiskInline(admin.TabularInline):
    model = VMDisk
    extra = 0


class VMNicInline(admin.TabularInline):
    model = VMNic
    extra = 0


@admin.register(VirtualMachine)
class VirtualMachineAdmin(admin.ModelAdmin):
    list_display = ["name", "organization", "project", "node", "status", "provisioning_state"]
    list_filter = ["status", "provisioning_state", "organization"]
    search_fields = ["name", "hostname"]
    inlines = [VMDiskInline, VMNicInline]
