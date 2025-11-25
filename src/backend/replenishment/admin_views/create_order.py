from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from replenishment.models import ReplenishmentReport
from django.db import transaction
from replenishment.services import create_purchase_document


@staff_member_required
@transaction.atomic
def create_order_view(request, object_id):
    report = get_object_or_404(ReplenishmentReport, pk=object_id)
    
    try:
        new_doc = create_purchase_document(report)
        
        messages.success(request, f"Документ Приходу №{new_doc.id} успішно сформовано у статусі ЧЕРНЕТКА. Будь ласка, перевірте його та проведіть.")  # type: ignore
        
        doc_admin_url = reverse(f'admin:{new_doc._meta.app_label}_document_change', args=[new_doc.id])  # type: ignore
        
        return redirect(doc_admin_url)
        
    except Exception as e:
        messages.error(request, f"Помилка створення документа: {e}")
    
    return redirect(reverse('admin:replenishment_replenishmentreport_change', args=[report.id]))  # type: ignore
