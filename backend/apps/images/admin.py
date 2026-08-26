from django.contrib import admin

from apps.images.models import Image, ImageUploadSession

admin.site.register(Image)
admin.site.register(ImageUploadSession)
