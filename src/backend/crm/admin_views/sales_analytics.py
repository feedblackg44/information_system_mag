from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import admin
from django.shortcuts import render
from django.db.models import Sum
from django.utils.dateparse import parse_date

from crm.models import Document, DocumentItem, Product, Warehouse


@staff_member_required
def sales_analytics_view(request):
    context = admin.site.each_context(request)

    product_id = request.GET.get("product")
    warehouse_id = request.GET.get("warehouse")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    qs = DocumentItem.objects.filter(
        document__doc_type=Document.DocType.SALE
    ).select_related("document", "product")

    if product_id:
        qs = qs.filter(product_id=product_id)

    if warehouse_id:
        qs = qs.filter(document__src_warehouse_id=warehouse_id)

    if date_from:
        qs = qs.filter(document__doc_date__date__gte=parse_date(date_from))

    if date_to:
        qs = qs.filter(document__doc_date__date__lte=parse_date(date_to))

    data = (
        qs.values("document__doc_date__date")
        .annotate(total=Sum("quantity"))
        .order_by("document__doc_date__date")
    )

    labels = [str(row["document__doc_date__date"]) for row in data]
    values = [float(row["total"]) for row in data]

    context.update({
        "title": "Аналітика продажів",
        "labels": labels,
        "values": values,
        "products": Product.objects.all(),
        "warehouses": Warehouse.objects.all(),
        "selected_product": product_id,
        "selected_warehouse": warehouse_id,
        "date_from": date_from or "",
        "date_to": date_to or "",
    })

    return render(request, "admin/sales_analytics.html", context)
