import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from django.http import HttpResponse, FileResponse, Http404
from django.core.files.base import ContentFile
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.lib.units import mm

from .models import (
    Asset,
    MaintenanceTask,
    TaskChecklistItem,
    Site,
    ChecklistTemplate,
    ChecklistTemplateItem,
)

@login_required
def dashboard(request):
    if request.method == "POST" and request.POST.get("action") == "start_task":
        task_id = request.POST.get("task_id", "").strip()
        if task_id:
            task = get_object_or_404(MaintenanceTask, id=task_id)
            if task.status in {"scheduled", "in_progress"}:
                task.status = "in_progress"
                task.save(update_fields=["status"])
            return redirect("task_detail", task_id=task.id)

    total_assets = Asset.objects.count()
    total_sites = Site.objects.count()
    open_tasks = MaintenanceTask.objects.exclude(status__in=["done", "cancelled"]).count()
    task_stats = MaintenanceTask.objects.aggregate(
        total=Count("id"),
        scheduled=Count("id", filter=Q(status="scheduled")),
        in_progress=Count("id", filter=Q(status="in_progress")),
        done=Count("id", filter=Q(status="done")),
    )

    sites = Site.objects.annotate(
        asset_count=Count("assets", distinct=True),
        open_tasks=Count("tasks", filter=Q(tasks__status__in=["scheduled", "in_progress"]), distinct=True),
    ).order_by("name")

    upcoming_tasks = (
        MaintenanceTask.objects.select_related("site")
        .filter(status__in=["scheduled", "in_progress"])
        .order_by("scheduled_for")[:6]
    )
    recent_done_tasks = (
        MaintenanceTask.objects.select_related("site")
        .filter(status="done")
        .order_by("-scheduled_for")[:4]
    )
    recent_assets = Asset.objects.select_related("site").order_by("-created_at")[:6]

    return render(
        request,
        "dashboard.html",
        {
            "task_stats": task_stats,
            "sites": sites,
            "upcoming_tasks": upcoming_tasks,
            "recent_done_tasks": recent_done_tasks,
            "recent_assets": recent_assets,
            "total_assets": total_assets,
            "total_sites": total_sites,
            "open_tasks": open_tasks,
            "active_page": "dashboard",
        },
    )

def healthz(request):
    return HttpResponse("ok", content_type="text/plain")

@login_required
def asset_by_token(request, token):
    asset = get_object_or_404(Asset, qr_token=token)
    related_tasks = list(
        MaintenanceTask.objects.filter(checklist_items__asset=asset)
        .select_related("site")
        .distinct()
        .order_by("-scheduled_for")[:8]
    )
    if not related_tasks:
        related_tasks = list(
            MaintenanceTask.objects.filter(site=asset.site)
            .select_related("site")
            .order_by("-scheduled_for")[:6]
        )
    checklist_items = (
        TaskChecklistItem.objects.filter(asset=asset)
        .select_related("task")
        .order_by("-id")[:6]
    )
    return render(
        request,
        "asset.html",
        {
            "asset": asset,
            "tasks": related_tasks,
            "checklist_items": checklist_items,
            "active_page": "assets",
        },
    )

def _qr_png_bytes(url: str) -> bytes:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def _parse_datetime_local(value: str):
    if not value:
        return timezone.now()
    parsed = parse_datetime(value)
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return timezone.now()
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed

def _format_datetime_for_pdf(value):
    if not value:
        return "-"
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.strftime("%d/%m/%Y %H:%M")

def _create_checklist_from_template(task, template, asset=None):
    items = []
    for item in template.items.all():
        items.append(
            TaskChecklistItem(
                task=task,
                asset=asset,
                template_item=item,
                label_snapshot=item.label,
                item_type=item.item_type,
                required=item.required,
                unit=item.unit,
            )
        )
    if items:
        TaskChecklistItem.objects.bulk_create(items)

def _format_task_item_answer(item):
    if item.item_type == "yesno":
        if item.value_bool is True:
            return "SI"
        if item.value_bool is False:
            return "NO"
        return "-"
    if item.item_type == "number":
        if item.value_number is None:
            return "-"
        unit = f" {item.unit}" if item.unit else ""
        return f"{item.value_number}{unit}"
    if item.item_type == "photo":
        return "Foto allegata" if item.attachment else "-"
    return item.value_text or "-"

def _build_task_report_pdf(task, items):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    margin_x = 18 * mm
    content_width = width - (2 * margin_x)
    line_height = 5 * mm
    indent = 5 * mm
    y = height - 22 * mm
    label_width = 36 * mm

    def ensure_space(required_height):
        nonlocal y
        if y - required_height < 20 * mm:
            c.showPage()
            y = height - 22 * mm

    def draw_wrapped(text, x, max_width, font_name, font_size, leading=None):
        nonlocal y
        text = "" if text is None else str(text)
        lines = simpleSplit(text, font_name, font_size, max_width)
        if not lines:
            lines = [""]
        leading = leading or line_height
        ensure_space(len(lines) * leading)
        c.setFont(font_name, font_size)
        for line in lines:
            c.drawString(x, y, line)
            y -= leading

    def draw_section_title(title):
        nonlocal y
        ensure_space(8 * mm)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(margin_x, y, title)
        y -= 3 * mm
        c.setLineWidth(0.5)
        c.line(margin_x, y, width - margin_x, y)
        y -= 5 * mm

    def draw_label_value(label, value):
        nonlocal y
        if value is None or value == "":
            value_text = "-"
        else:
            value_text = str(value)
        lines = simpleSplit(value_text, "Helvetica", 10, content_width - label_width)
        if not lines:
            lines = [""]
        ensure_space(len(lines) * line_height)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(margin_x, y, f"{label}:")
        c.setFont("Helvetica", 10)
        for line in lines:
            c.drawString(margin_x + label_width, y, line)
            y -= line_height
        y -= 1.5 * mm

    c.setFont("Helvetica-Bold", 16)
    c.drawString(margin_x, y, "Report intervento")
    y -= 8 * mm

    draw_section_title("Dati intervento")
    draw_label_value("Sede", task.site.name)
    draw_label_value("Titolo", task.title)
    draw_label_value("Stato", task.get_status_display())
    draw_label_value("Pianificato", _format_datetime_for_pdf(task.scheduled_for))
    draw_label_value("Data esecuzione", _format_datetime_for_pdf(task.completed_at))
    draw_label_value("Report generato", _format_datetime_for_pdf(timezone.now()))

    if task.notes:
        draw_section_title("Note")
        c.setFont("Helvetica", 10)
        for raw_line in task.notes.splitlines():
            if not raw_line:
                ensure_space(line_height)
                y -= line_height
                continue
            draw_wrapped(raw_line, margin_x, content_width, "Helvetica", 10, leading=4.5 * mm)

    draw_section_title("Checklist")

    for idx, item in enumerate(items, start=1):
        label = f"{idx}. {item.label_snapshot}"
        draw_wrapped(label, margin_x, content_width, "Helvetica-Bold", 10, leading=4.5 * mm)
        answer = _format_task_item_answer(item)
        draw_wrapped(f"Risposta: {answer}", margin_x + indent, content_width - indent, "Helvetica", 10, leading=4.5 * mm)
        if item.asset:
            draw_wrapped(f"Asset: {item.asset.name}", margin_x + indent, content_width - indent, "Helvetica", 9, leading=4.5 * mm)
        y -= 1.5 * mm

    if not items:
        draw_wrapped("Nessuna voce in checklist.", margin_x, content_width, "Helvetica", 10, leading=4.5 * mm)

    c.showPage()
    c.save()
    return buf.getvalue()

def asset_qr_png(request, asset_id: int):
    asset = get_object_or_404(Asset, id=asset_id)
    png = _qr_png_bytes(asset.qr_url)
    resp = HttpResponse(png, content_type="image/png")
    resp["Content-Disposition"] = f'inline; filename="asset-{asset.id}-qr.png"'
    return resp

def asset_label_pdf(request, asset_id: int):
    asset = get_object_or_404(Asset, id=asset_id)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    # Simple single-label layout (centered)
    qr_png = _qr_png_bytes(asset.qr_url)
    qr_image = ImageReader(io.BytesIO(qr_png))

    # draw title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20*mm, height - 25*mm, asset.site.name)

    c.setFont("Helvetica", 12)
    c.drawString(20*mm, height - 35*mm, f"Asset: {asset.name}")
    if asset.asset_type:
        c.drawString(20*mm, height - 42*mm, f"Tipo: {asset.asset_type}")
    if asset.serial:
        c.drawString(20*mm, height - 49*mm, f"Seriale: {asset.serial}")

    # QR image
    qr_size = 60*mm
    c.drawImage(qr_image, 20*mm, height - 120*mm, width=qr_size, height=qr_size, mask='auto')

    c.setFont("Helvetica", 9)
    c.drawString(20*mm, height - 125*mm, asset.qr_url)

    c.showPage()
    c.save()

    pdf = buf.getvalue()
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="asset-{asset.id}-label.pdf"'
    return resp

@login_required
def task_report_pdf(request, task_id: int):
    task = get_object_or_404(MaintenanceTask, id=task_id)
    if not task.report_pdf:
        raise Http404("Report non disponibile")
    try:
        report_file = task.report_pdf.open("rb")
    except FileNotFoundError:
        raise Http404("Report non trovato")
    response = FileResponse(report_file, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="task-{task.id}-report.pdf"'
    return response

@login_required
def task_detail(request, task_id: int):
    task = get_object_or_404(MaintenanceTask, id=task_id)
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "update_task":
            status = request.POST.get("status", "").strip()
            valid_status = {value for value, _ in MaintenanceTask.STATUS_CHOICES}
            if status in valid_status:
                was_done = task.status == "done"
                task.status = status
                update_fields = ["status"]
                if status == "done" and (not was_done or task.completed_at is None):
                    task.completed_at = timezone.now()
                    update_fields.append("completed_at")
                task.save(update_fields=update_fields)
            return redirect("task_detail", task_id=task.id)
        if action == "generate_checklist":
            template_id = request.POST.get("template_id", "").strip()
            if template_id:
                template = get_object_or_404(ChecklistTemplate, id=template_id)
                asset_id = request.POST.get("asset_id", "").strip()
                asset = Asset.objects.filter(id=asset_id, site=task.site).first() if asset_id else None
                _create_checklist_from_template(task, template, asset=asset)
            return redirect("task_detail", task_id=task.id)
        if action == "add_checklist_item":
            label = request.POST.get("label", "").strip()
            if label:
                item_type = request.POST.get("item_type", "yesno").strip()
                valid_types = {value for value, _ in ChecklistTemplateItem.TYPE_CHOICES}
                if item_type not in valid_types:
                    item_type = "yesno"
                required = request.POST.get("required") == "on"
                unit = request.POST.get("unit", "").strip()
                asset_id = request.POST.get("asset_id", "").strip()
                asset = Asset.objects.filter(id=asset_id, site=task.site).first() if asset_id else None
                TaskChecklistItem.objects.create(
                    task=task,
                    asset=asset,
                    label_snapshot=label,
                    item_type=item_type,
                    required=required,
                    unit=unit,
                )
            return redirect("task_detail", task_id=task.id)
        if action == "save_answers":
            items = list(TaskChecklistItem.objects.filter(task=task))
            for item in items:
                if item.item_type == "yesno":
                    value = request.POST.get(f"item_{item.id}_yesno", "")
                    if value == "yes":
                        item.value_bool = True
                    elif value == "no":
                        item.value_bool = False
                    else:
                        item.value_bool = None
                elif item.item_type == "number":
                    value = request.POST.get(f"item_{item.id}_number", "").strip()
                    if value:
                        try:
                            item.value_number = Decimal(value)
                        except InvalidOperation:
                            item.value_number = None
                    else:
                        item.value_number = None
                elif item.item_type == "text":
                    item.value_text = request.POST.get(f"item_{item.id}_text", "").strip()
                elif item.item_type == "photo":
                    upload_key = f"item_{item.id}_photo"
                    if upload_key in request.FILES:
                        item.attachment = request.FILES[upload_key]
                item.save()
            if request.POST.get("close_task") == "1":
                completed_changed = False
                if task.status != "done" or task.completed_at is None:
                    task.completed_at = timezone.now()
                    completed_changed = True
                pdf_bytes = _build_task_report_pdf(task, items)
                filename = f"task-{task.id}-report.pdf"
                task.report_pdf.save(filename, ContentFile(pdf_bytes), save=False)
                task.status = "done"
                update_fields = ["status", "report_pdf"]
                if completed_changed:
                    update_fields.append("completed_at")
                task.save(update_fields=update_fields)
            return redirect("task_detail", task_id=task.id)

    items = TaskChecklistItem.objects.filter(task=task).select_related("asset").order_by("id")
    related_assets = Asset.objects.filter(checklist_items__task=task).distinct()
    checklist_templates = (
        ChecklistTemplate.objects.filter(Q(site=task.site) | Q(site__isnull=True))
        .select_related("site")
        .order_by("name")
    )
    site_assets = Asset.objects.filter(site=task.site).order_by("name")
    return render(
        request,
        "task.html",
        {
            "task": task,
            "items": items,
            "related_assets": related_assets,
            "checklist_templates": checklist_templates,
            "site_assets": site_assets,
            "status_choices": MaintenanceTask.STATUS_CHOICES,
            "item_type_choices": ChecklistTemplateItem.TYPE_CHOICES,
            "active_page": "tasks",
        },
    )

@login_required
def asset_list(request):
    status_filter = request.GET.get("status", "").strip()
    query = request.GET.get("q", "").strip()

    assets = Asset.objects.select_related("site")
    if status_filter:
        assets = assets.filter(status=status_filter)
    if query:
        assets = assets.filter(
            Q(name__icontains=query)
            | Q(asset_type__icontains=query)
            | Q(serial__icontains=query)
            | Q(site__name__icontains=query)
            | Q(vendor__icontains=query)
        )
    assets = assets.order_by("name")

    return render(
        request,
        "assets.html",
        {
            "assets": assets,
            "status_filter": status_filter,
            "query": query,
            "status_choices": Asset.STATUS_CHOICES,
            "active_page": "assets",
        },
    )

@login_required
def task_list(request):
    if request.method == "POST" and request.POST.get("action") == "create_task":
        title = request.POST.get("title", "").strip()
        site_id = request.POST.get("site_id", "").strip()
        if title and site_id:
            site = get_object_or_404(Site, id=site_id)
            scheduled_for = _parse_datetime_local(request.POST.get("scheduled_for", "").strip())
            status = request.POST.get("status", "scheduled").strip()
            valid_status = {value for value, _ in MaintenanceTask.STATUS_CHOICES}
            if status not in valid_status:
                status = "scheduled"
            notes = request.POST.get("notes", "").strip()
            task = MaintenanceTask.objects.create(
                site=site,
                title=title,
                scheduled_for=scheduled_for,
                status=status,
                notes=notes,
                created_by=request.user if request.user.is_authenticated else None,
            )
            template_id = request.POST.get("template_id", "").strip()
            asset_id = request.POST.get("asset_id", "").strip()
            if template_id:
                template = get_object_or_404(ChecklistTemplate, id=template_id)
                if template.site_id and template.site_id != site.id:
                    template = None
                asset = Asset.objects.filter(id=asset_id, site=site).first() if asset_id else None
                if template:
                    _create_checklist_from_template(task, template, asset=asset)
            return redirect("task_detail", task_id=task.id)

    status_filter = request.GET.get("status", "").strip()
    site_filter = request.GET.get("site", "").strip()
    query = request.GET.get("q", "").strip()

    tasks = MaintenanceTask.objects.select_related("site")
    if status_filter:
        tasks = tasks.filter(status=status_filter)
    if site_filter:
        tasks = tasks.filter(site_id=site_filter)
    if query:
        tasks = tasks.filter(Q(title__icontains=query) | Q(notes__icontains=query))
    tasks = tasks.order_by("-scheduled_for")

    sites = Site.objects.order_by("name")
    checklist_templates = ChecklistTemplate.objects.select_related("site").order_by("name")
    assets = Asset.objects.select_related("site").order_by("site__name", "name")

    return render(
        request,
        "tasks.html",
        {
            "tasks": tasks,
            "status_filter": status_filter,
            "site_filter": site_filter,
            "query": query,
            "status_choices": MaintenanceTask.STATUS_CHOICES,
            "sites": sites,
            "checklist_templates": checklist_templates,
            "assets": assets,
            "now_local": timezone.localtime(),
            "active_page": "tasks",
        },
    )

@login_required
def site_detail(request, site_id: int):
    site = get_object_or_404(Site, id=site_id)
    assets = site.assets.select_related("site").order_by("name")
    open_tasks = site.tasks.exclude(status__in=["done", "cancelled"]).order_by("scheduled_for")
    recent_done_tasks = site.tasks.filter(status="done").order_by("-scheduled_for")[:3]

    return render(
        request,
        "site_detail.html",
        {
            "site": site,
            "assets": assets,
            "open_tasks": open_tasks,
            "recent_done_tasks": recent_done_tasks,
            "active_page": "sites",
        },
    )

@login_required
def site_list(request):
    query = request.GET.get("q", "").strip()
    sites = Site.objects.annotate(
        asset_count=Count("assets", distinct=True),
        open_tasks=Count("tasks", filter=Q(tasks__status__in=["scheduled", "in_progress"]), distinct=True),
    ).order_by("name")
    if query:
        sites = sites.filter(Q(name__icontains=query) | Q(address__icontains=query))

    return render(
        request,
        "sites.html",
        {
            "sites": sites,
            "query": query,
            "active_page": "sites",
        },
    )
