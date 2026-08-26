from django.urls import path

from apps.metrics.views import NodeMetricsView, VMMetricsView

urlpatterns = [
    path("metrics/nodes/<uuid:uuid>/", NodeMetricsView.as_view(), name="node-metrics"),
    path("metrics/vms/<uuid:uuid>/", VMMetricsView.as_view(), name="vm-metrics"),
]
