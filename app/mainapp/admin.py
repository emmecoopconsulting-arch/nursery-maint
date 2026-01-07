from django.contrib import admin
from .models import (
    Site, Asset,
    MaintenancePlan, MaintenanceTask,
    ChecklistTemplate, ChecklistTemplateItem,
    TaskChecklistItem,
)

@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    search_fields = ("name", "address")
    list_display = ("name", "address")

@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    search_fields = ("name", "serial", "vendor", "asset_type")
    list_filter = ("site", "status", "asset_type")
    list_display = ("name", "site", "asset_type", "status", "serial")
    readonly_fields = ("qr_token", "qr_preview", "qr_url_display")

    def qr_preview(self, obj):
        if not obj.pk:
            return "-"
        return f'<img src="/asset/{obj.id}/qr.png" style="max-width:180px" />'
    qr_preview.short_description = "QR"
    qr_preview.allow_tags = True

    def qr_url_display(self, obj):
        return obj.qr_url
    qr_url_display.short_description = "URL (nel QR)"

    class Media:
        css = {"all": ()}

class ChecklistTemplateItemInline(admin.TabularInline):
    model = ChecklistTemplateItem
    extra = 0

@admin.register(ChecklistTemplate)
class ChecklistTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "site")
    inlines = [ChecklistTemplateItemInline]

class TaskChecklistItemInline(admin.TabularInline):
    model = TaskChecklistItem
    extra = 0

@admin.register(MaintenanceTask)
class MaintenanceTaskAdmin(admin.ModelAdmin):
    list_display = ("title", "site", "scheduled_for", "status")
    list_filter = ("site", "status")
    search_fields = ("title", "notes")
    inlines = [TaskChecklistItemInline]

@admin.register(MaintenancePlan)
class MaintenancePlanAdmin(admin.ModelAdmin):
    list_display = ("title", "site", "frequency", "next_due", "active")
    list_filter = ("site", "frequency", "active")
    search_fields = ("title",)

@admin.register(TaskChecklistItem)
class TaskChecklistItemAdmin(admin.ModelAdmin):
    list_display = ("task", "label_snapshot", "item_type", "asset")
    list_filter = ("item_type", "task__site")
    search_fields = ("label_snapshot", "value_text")
