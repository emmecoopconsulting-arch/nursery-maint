import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone

class Site(models.Model):
    name = models.CharField(max_length=120)
    address = models.CharField(max_length=255, blank=True, default="")
    notes = models.TextField(blank=True, default="")

    def __str__(self):
        return self.name

class Asset(models.Model):
    STATUS_CHOICES = [
        ("active", "Attivo"),
        ("out_of_service", "Fuori servizio"),
        ("disposed", "Dismesso"),
    ]

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="assets")
    name = models.CharField(max_length=160)
    asset_type = models.CharField(max_length=80, blank=True, default="")
    serial = models.CharField(max_length=80, blank=True, default="")
    vendor = models.CharField(max_length=120, blank=True, default="")
    purchase_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

    qr_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    qr_image = models.ImageField(upload_to="qr/", blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.site.name})"

    @property
    def qr_url(self):
        return f"{settings.BASE_URL}/a/{self.qr_token}/"

class MaintenancePlan(models.Model):
    FREQ_CHOICES = [
        ("weekly", "Settimanale"),
        ("monthly", "Mensile"),
        ("quarterly", "Trimestrale"),
        ("yearly", "Annuale"),
    ]
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="plans")
    title = models.CharField(max_length=160)
    frequency = models.CharField(max_length=20, choices=FREQ_CHOICES, default="monthly")
    next_due = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)
    assigned_to = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f"{self.site.name} - {self.title}"

class MaintenanceTask(models.Model):
    STATUS_CHOICES = [
        ("scheduled", "Programmato"),
        ("in_progress", "In corso"),
        ("done", "Chiuso"),
        ("cancelled", "Annullato"),
    ]
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="tasks")
    plan = models.ForeignKey(MaintenancePlan, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")

    title = models.CharField(max_length=160)
    scheduled_for = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="scheduled")
    notes = models.TextField(blank=True, default="")
    report_pdf = models.FileField(upload_to="reports/", null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="created_tasks")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.site.name} - {self.title}"

class ChecklistTemplate(models.Model):
    name = models.CharField(max_length=160)
    site = models.ForeignKey(Site, null=True, blank=True, on_delete=models.SET_NULL, related_name="checklist_templates")

    def __str__(self):
        return self.name

class ChecklistTemplateItem(models.Model):
    TYPE_CHOICES = [
        ("yesno", "SI/NO"),
        ("number", "Numero"),
        ("text", "Testo"),
        ("photo", "Foto"),
    ]
    template = models.ForeignKey(ChecklistTemplate, on_delete=models.CASCADE, related_name="items")
    order = models.PositiveIntegerField(default=0)
    label = models.CharField(max_length=220)
    item_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="yesno")
    required = models.BooleanField(default=False)
    unit = models.CharField(max_length=20, blank=True, default="")

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.template.name} - {self.label}"

class TaskChecklistItem(models.Model):
    task = models.ForeignKey(MaintenanceTask, on_delete=models.CASCADE, related_name="checklist_items")
    asset = models.ForeignKey(Asset, null=True, blank=True, on_delete=models.SET_NULL, related_name="checklist_items")

    template_item = models.ForeignKey(ChecklistTemplateItem, null=True, blank=True, on_delete=models.SET_NULL)
    label_snapshot = models.CharField(max_length=220)
    item_type = models.CharField(max_length=20, default="yesno")
    required = models.BooleanField(default=False)
    unit = models.CharField(max_length=20, blank=True, default="")

    # values
    value_text = models.TextField(blank=True, default="")
    value_number = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    value_bool = models.BooleanField(null=True, blank=True)
    attachment = models.FileField(upload_to="attachments/", null=True, blank=True)

    def __str__(self):
        return f"{self.task} - {self.label_snapshot}"
