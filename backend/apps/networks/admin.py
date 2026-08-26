from django.contrib import admin

from apps.networks.models import IPAddress, IPPool, Network, Subnet

admin.site.register(Network)
admin.site.register(Subnet)
admin.site.register(IPPool)
admin.site.register(IPAddress)
