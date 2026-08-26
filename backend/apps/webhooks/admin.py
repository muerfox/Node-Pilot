from django.contrib import admin

from apps.webhooks.models import Webhook, WebhookDelivery

admin.site.register(Webhook)
admin.site.register(WebhookDelivery)
