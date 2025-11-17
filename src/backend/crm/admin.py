from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.forms.models import BaseModelFormSet, ModelForm
from django.http.request import HttpRequest

from .models import (
    Brand,
    Document,
    DocumentItem,
    Inventory,
    Product,
    ProductPriceLevel,
    Warehouse,
)

admin.site.register(LogEntry)

# -----------------------------
# BRAND
# -----------------------------
@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "country")
    search_fields = ("name",)


# -----------------------------
# PRODUCT
# -----------------------------
class ProductPriceLevelInline(admin.TabularInline):
    model = ProductPriceLevel
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "brand", "sale_price")
    search_fields = ("name", "sku")
    list_filter = ("brand",)
    inlines = [ProductPriceLevelInline]


# -----------------------------
# WAREHOUSE
# -----------------------------
@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("name", "location")
    search_fields = ("name", "location")


# -----------------------------
# INVENTORY (только просмотр)
# -----------------------------
@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    readonly_fields = ("product", "warehouse", "quantity")
    list_display = ("product", "warehouse", "quantity")
    list_filter = ("warehouse",)
    search_fields = ("product__name", "product__sku")


# -----------------------------
# DOCUMENT + ITEMS INLINE
# -----------------------------
class DocumentItemInline(admin.TabularInline):
    model = DocumentItem
    extra = 0
    readonly_fields = ("price",)
    fields = ("product", "quantity", "price")


@admin.action(description="Провести документ")
def post_document(modeladmin, request, queryset):
    for doc in queryset:
        doc.post()


@admin.action(description="Скасувати проведення")
def unpost_document(modeladmin, request, queryset):
    for doc in queryset:
        doc.unpost()


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    readonly_fields = ("doc_date", "status")
    list_display = ("id", "doc_type", "status", "doc_date", "src_warehouse", "dst_warehouse")
    list_filter = ("doc_type", "status", "src_warehouse", "dst_warehouse")
    search_fields = ("id",)
    inlines = [DocumentItemInline]
    actions = [post_document, unpost_document]

    def save_related(self, request: HttpRequest, form: ModelForm, formsets: BaseModelFormSet, change: bool) -> None:
        super().save_related(request, form, formsets, change)
        form.instance.recalc_prices()

    def get_readonly_fields(self, request, obj=None):
        """
        Если документ уже проведён — всё становится readonly.
        """
        if obj and obj.status == Document.Status.POSTED:
            return tuple(self.readonly_fields) + (
                "doc_type",
                "src_warehouse",
                "dst_warehouse",
                "note",
            )
        return self.readonly_fields

    def has_delete_permission(self, request, obj=None):
        """
        Нельзя удалять проведённые документы.
        """
        if obj and obj.status == Document.Status.POSTED:
            return False
        return super().has_delete_permission(request, obj)
