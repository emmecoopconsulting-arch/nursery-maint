from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from mainapp import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.dashboard, name="home"),
    path("healthz", views.healthz, name="healthz"),
    path("assets/", views.asset_list, name="asset_list"),
    path("tasks/", views.task_list, name="task_list"),
    path("sites/", views.site_list, name="site_list"),
    path("sites/<int:site_id>/", views.site_detail, name="site_detail"),
    path("a/<uuid:token>/", views.asset_by_token, name="asset_by_token"),
    path("asset/<int:asset_id>/qr.png", views.asset_qr_png, name="asset_qr_png"),
    path("asset/<int:asset_id>/label.pdf", views.asset_label_pdf, name="asset_label_pdf"),
    path("task/<int:task_id>/", views.task_detail, name="task_detail"),
    path("task/<int:task_id>/report.pdf", views.task_report_pdf, name="task_report_pdf"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
