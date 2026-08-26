from django.contrib import admin

from apps.backups.models import Backup, BackupSchedule, BackupTarget

admin.site.register(BackupTarget)
admin.site.register(Backup)
admin.site.register(BackupSchedule)
