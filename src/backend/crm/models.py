from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Brand(models.Model):
    name = models.CharField(max_length=128, unique=True)
    country = models.CharField(max_length=64)

    def __str__(self):
        return f"{self.name} ({self.country})"


class Product(models.Model):
    name = models.CharField(max_length=128)
    sku = models.CharField(max_length=64, unique=True)
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE)
    sale_price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.name} ({self.sku})"


class ProductPriceLevel(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    minimal_quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ("product", "minimal_quantity")

    def __str__(self):
        return f"{self.product.name} - {self.minimal_quantity} pcs at {self.price}"


class Warehouse(models.Model):
    name = models.CharField(max_length=128, unique=True)
    location = models.CharField(max_length=256, unique=True)

    def __str__(self):
        return f"{self.name} ({self.location})"


class Inventory(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ("product", "warehouse")

    def __str__(self):
        return f"{self.product.name} in {self.warehouse.name}: {self.quantity} pcs"


class Document(models.Model):
    class DocType(models.TextChoices):
        PURCHASE = "PURCHASE", "Прихід"
        SALE = "SALE", "Продаж"
        TRANSFER = "TRANSFER", "Переміщення"
        WRITE_OFF = "WRITE_OFF", "Списання"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Чернетка"
        POSTED = "POSTED", "Проведено"
        CANCELED = "CANCELED", "Скасовано"

    doc_type = models.CharField(max_length=16, choices=DocType.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    doc_date = models.DateTimeField(default=timezone.now)

    src_warehouse = models.ForeignKey(
        Warehouse, on_delete=models.CASCADE,
        related_name="documents_from",
        null=True, blank=True
    )

    dst_warehouse = models.ForeignKey(
        Warehouse, on_delete=models.CASCADE,
        related_name="documents_to",
        null=True, blank=True
    )

    note = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.doc_type} #{self.id}"  # type: ignore
    
    def recalc_prices(self):
        items = list(self.items.select_related("product", "product__brand"))  # type: ignore

        brand_groups = {}
        for item in items:
            brand = item.product.brand_id
            brand_groups.setdefault(brand, []).append(item)

        for brand_id, brand_items in brand_groups.items():
            total_qty = sum(item.quantity for item in brand_items)

            levels_by_product = {}

            for item in brand_items:
                product = item.product

                if product.id not in levels_by_product:
                    price_level = (
                        ProductPriceLevel.objects
                        .filter(
                            product=product,
                            minimal_quantity__lte=total_qty
                        )
                        .order_by("-minimal_quantity")
                        .first()
                    )

                    if not price_level:
                        price_level = (
                            ProductPriceLevel.objects
                            .filter(product=product)
                            .order_by("-minimal_quantity")
                            .first()
                        )

                    levels_by_product[product.id] = price_level

                level = levels_by_product[product.id]
                item.price = level.price * item.quantity

        DocumentItem.objects.bulk_update(items, ["price"])
    
    def clean(self):
        if self.doc_type == self.DocType.PURCHASE:
            if not self.dst_warehouse or self.src_warehouse:
                raise ValidationError("Прихід повинен мати тільки склад отримувача (dst_warehouse).")

        if self.doc_type == self.DocType.SALE:
            if not self.src_warehouse or self.dst_warehouse:
                raise ValidationError("Продаж повинен мати тільки склад відправника (src_warehouse).")

        if self.doc_type == self.DocType.WRITE_OFF:
            if not self.src_warehouse:
                raise ValidationError("Списання повинно мати склад відправника (src_warehouse).")
            if self.dst_warehouse:
                raise ValidationError("Списання не може мати склад отримувача.")

        if self.doc_type == self.DocType.TRANSFER:
            if not self.src_warehouse or not self.dst_warehouse:
                raise ValidationError("Переміщення повинно мати обидва склади.")
            if self.src_warehouse == self.dst_warehouse:
                raise ValidationError("Неможливо перемістити товар у той самий склад.")

    def post(self):
        """Провести документ: обновить остатки."""
        if self.status == self.Status.POSTED:
            raise ValidationError("Документ вже проведено.")

        self.clean()

        for item in self.items.all():  # type: ignore
            product = item.product
            qty = item.quantity

            if self.doc_type == self.DocType.PURCHASE:
                inv, _ = Inventory.objects.get_or_create(
                    product=product,
                    warehouse=self.dst_warehouse,
                    defaults={"quantity": 0}
                )
                inv.quantity += qty
                inv.save()

            elif self.doc_type == self.DocType.SALE:
                inv = Inventory.objects.get(
                    product=product,
                    warehouse=self.src_warehouse
                )
                if inv.quantity < qty:
                    raise ValidationError(f"Недостатньо товару '{product.name}' на складі.")
                inv.quantity -= qty
                inv.save()

            elif self.doc_type == self.DocType.WRITE_OFF:
                inv = Inventory.objects.get(
                    product=product,
                    warehouse=self.src_warehouse
                )
                if inv.quantity < qty:
                    raise ValidationError(f"Недостатньо товару '{product.name}' для списання.")
                inv.quantity -= qty
                inv.save()

            elif self.doc_type == self.DocType.TRANSFER:
                inv_src = Inventory.objects.get(
                    product=product,
                    warehouse=self.src_warehouse
                )
                if inv_src.quantity < qty:
                    raise ValidationError(f"Недостатньо товару '{product.name}' для переміщення.")
                inv_src.quantity -= qty
                inv_src.save()

                inv_dst, _ = Inventory.objects.get_or_create(
                    product=product,
                    warehouse=self.dst_warehouse,
                    defaults={"quantity": 0}
                )
                inv_dst.quantity += qty
                inv_dst.save()

        self.recalc_prices()

        self.status = self.Status.POSTED
        self.save()

    def unpost(self):
        """Скасувати проведення (повний відкат змін)"""
        if self.status != self.Status.POSTED:
            raise ValidationError("Документ не проведено.")

        for item in self.items.all():  # type: ignore
            product = item.product
            qty = item.quantity

            if self.doc_type == self.DocType.PURCHASE:
                inv = Inventory.objects.get(product=product, warehouse=self.dst_warehouse)
                if inv.quantity < qty:
                    raise ValidationError("Неможливо скасувати: на складі вже не вистачає товару.")
                inv.quantity -= qty
                inv.save()

            elif self.doc_type == self.DocType.SALE:
                inv, _ = Inventory.objects.get_or_create(
                    product=product, warehouse=self.src_warehouse, defaults={"quantity": 0}
                )
                inv.quantity += qty
                inv.save()

            elif self.doc_type == self.DocType.WRITE_OFF:
                inv, _ = Inventory.objects.get_or_create(
                    product=product, warehouse=self.src_warehouse, defaults={"quantity": 0}
                )
                inv.quantity += qty
                inv.save()

            elif self.doc_type == self.DocType.TRANSFER:
                inv_src, _ = Inventory.objects.get_or_create(
                    product=product, warehouse=self.src_warehouse, defaults={"quantity": 0}
                )
                inv_dst = Inventory.objects.get(
                    product=product, warehouse=self.dst_warehouse
                )

                if inv_dst.quantity < qty:
                    raise ValidationError("Неможливо скасувати: товар вже розібрали на складі отримувача.")

                inv_src.quantity += qty
                inv_src.save()

                inv_dst.quantity -= qty
                inv_dst.save()

        self.status = self.Status.CANCELED
        self.save()
    
    def save(self, *args, **kwargs):
        if self.pk is None:
            self.status = self.Status.DRAFT
        super().save(*args, **kwargs)


class DocumentItem(models.Model):
    document = models.ForeignKey(
        Document, 
        on_delete=models.CASCADE,
        related_name="items"
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        unique_together = ("document", "product")

    def __str__(self):
        return f"{self.product} x {self.quantity}"

    def save(self, *args, **kwargs):
        doc = self.document

        if doc.doc_type == Document.DocType.SALE:
            self.price = Decimal(self.product.sale_price) * self.quantity
        elif doc.doc_type == Document.DocType.WRITE_OFF:
            self.price = Decimal(self.product.sale_price) * self.quantity
        elif doc.doc_type == Document.DocType.TRANSFER:
            self.price = Decimal(0)
        elif doc.doc_type == Document.DocType.PURCHASE:
            first_level = (
                ProductPriceLevel.objects
                .filter(product=self.product)
                .order_by("minimal_quantity")
                .first()
            )
            if first_level:
                self.price = Decimal(first_level.price) * self.quantity
            else:
                self.price = Decimal(0)
        else:
            self.price = Decimal(0)

        super().save(*args, **kwargs)
