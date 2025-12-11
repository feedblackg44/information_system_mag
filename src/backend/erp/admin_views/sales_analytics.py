from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import admin
from django.shortcuts import render
from django.db.models import Sum
from django.utils.dateparse import parse_date
from django.utils import timezone

from erp.models import Document, DocumentItem, Product, Warehouse


@staff_member_required
def sales_analytics_view(request):
    context = admin.site.each_context(request)

    product_id = request.GET.get("product")
    warehouse_id = request.GET.get("warehouse")
    date_from_str = request.GET.get("date_from")
    date_to_str = request.GET.get("date_to")

    qs = DocumentItem.objects.filter(
        document__doc_type=Document.DocType.SALE
    ).select_related("document", "product")

    if product_id:
        qs = qs.filter(product_id=product_id)

    if warehouse_id:
        qs = qs.filter(document__src_warehouse_id=warehouse_id)

    start_date = parse_date(date_from_str) if date_from_str else None
    end_date = parse_date(date_to_str) if date_to_str else None

    if start_date:
        qs = qs.filter(document__doc_date__date__gte=start_date)

    if end_date:
        qs = qs.filter(document__doc_date__date__lte=end_date)

    data_qs = (
        qs.values("document__doc_date__date")
        .annotate(total=Sum("quantity"))
        .order_by("document__doc_date__date")
    )

    sales_dict = {
        item["document__doc_date__date"]: float(item["total"]) 
        for item in data_qs
    }
    
    if not start_date or not end_date:
        if not sales_dict:
            current_date = timezone.now().date()
            if not start_date:
                start_date = current_date
            if not end_date:
                end_date = current_date
        else:
            dates = list(sales_dict.keys())
            if not start_date:
                start_date = min(dates)
            if not end_date:
                end_date = max(dates)

    labels = []
    values = []
    
    current_date = start_date
    while current_date <= end_date:
        labels.append(str(current_date))
        
        val = sales_dict.get(current_date, 0)
        values.append(val)
        
        current_date += timedelta(days=1)

    context.update({
        "title": "Аналітика продажів",
        "labels": labels,
        "values": values,
        "products": Product.objects.all(),
        "warehouses": Warehouse.objects.all(),
        "selected_product": product_id,
        "selected_warehouse": warehouse_id,
        "date_from": date_from_str or "",
        "date_to": date_to_str or "",
    })

    return render(request, "admin/sales_analytics.html", context)