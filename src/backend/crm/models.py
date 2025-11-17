from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models


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
    doc_date = models.DateTimeField(auto_now_add=True)

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
    
    def clean(self):
        # PURCHASE: only dst
        if self.doc_type == self.DocType.PURCHASE:
            if not self.dst_warehouse or self.src_warehouse:
                raise ValidationError("Прихід повинен мати тільки склад отримувача (dst_warehouse).")

        # SALE: only src
        if self.doc_type == self.DocType.SALE:
            if not self.src_warehouse or self.dst_warehouse:
                raise ValidationError("Продаж повинен мати тільки склад відправника (src_warehouse).")

        # WRITE_OFF: only src
        if self.doc_type == self.DocType.WRITE_OFF:
            if not self.src_warehouse:
                raise ValidationError("Списання повинно мати склад відправника (src_warehouse).")
            if self.dst_warehouse:
                raise ValidationError("Списання не може мати склад отримувача.")

        # TRANSFER: src and dst must exist AND differ
        if self.doc_type == self.DocType.TRANSFER:
            if not self.src_warehouse or not self.dst_warehouse:
                raise ValidationError("Переміщення повинно мати обидва склади.")
            if self.src_warehouse == self.dst_warehouse:
                raise ValidationError("Неможливо перемістити товар у той самий склад.")

    def post(self):
        """Провести документ: обновить остатки."""
        if self.status == self.Status.POSTED:
            raise ValidationError("Документ вже проведено.")

        # Проверить бизнес-валидацию
        self.clean()

        for item in self.items.all():  # type: ignore
            product = item.product
            qty = item.quantity

            # ------------ PURCHASE ------------
            if self.doc_type == self.DocType.PURCHASE:
                inv, _ = Inventory.objects.get_or_create(
                    product=product,
                    warehouse=self.dst_warehouse,
                    defaults={"quantity": 0}
                )
                inv.quantity += qty
                inv.save()

            # ------------ SALE ------------
            elif self.doc_type == self.DocType.SALE:
                inv = Inventory.objects.get(
                    product=product,
                    warehouse=self.src_warehouse
                )
                if inv.quantity < qty:
                    raise ValidationError(f"Недостатньо товару '{product.name}' на складі.")
                inv.quantity -= qty
                inv.save()

            # ------------ WRITE-OFF ------------
            elif self.doc_type == self.DocType.WRITE_OFF:
                inv = Inventory.objects.get(
                    product=product,
                    warehouse=self.src_warehouse
                )
                if inv.quantity < qty:
                    raise ValidationError(f"Недостатньо товару '{product.name}' для списання.")
                inv.quantity -= qty
                inv.save()

            # ------------ TRANSFER ------------
            elif self.doc_type == self.DocType.TRANSFER:
                # убавить на src
                inv_src = Inventory.objects.get(
                    product=product,
                    warehouse=self.src_warehouse
                )
                if inv_src.quantity < qty:
                    raise ValidationError(f"Недостатньо товару '{product.name}' для переміщення.")
                inv_src.quantity -= qty
                inv_src.save()

                # добавить на dst
                inv_dst, _ = Inventory.objects.get_or_create(
                    product=product,
                    warehouse=self.dst_warehouse,
                    defaults={"quantity": 0}
                )
                inv_dst.quantity += qty
                inv_dst.save()

        self.status = self.Status.POSTED
        self.save()

    def unpost(self):
        """Скасувати проведення (повний відкат змін)"""
        if self.status != self.Status.POSTED:
            raise ValidationError("Документ не проведено.")

        for item in self.items.all():  # type: ignore
            product = item.product
            qty = item.quantity

            # ------------ PURCHASE ------------
            if self.doc_type == self.DocType.PURCHASE:
                inv = Inventory.objects.get(product=product, warehouse=self.dst_warehouse)
                if inv.quantity < qty:
                    raise ValidationError("Неможливо скасувати: на складі вже не вистачає товару.")
                inv.quantity -= qty
                inv.save()

            # ------------ SALE ------------
            elif self.doc_type == self.DocType.SALE:
                inv, _ = Inventory.objects.get_or_create(
                    product=product, warehouse=self.src_warehouse, defaults={"quantity": 0}
                )
                inv.quantity += qty
                inv.save()

            # ------------ WRITE_OFF ------------
            elif self.doc_type == self.DocType.WRITE_OFF:
                inv, _ = Inventory.objects.get_or_create(
                    product=product, warehouse=self.src_warehouse, defaults={"quantity": 0}
                )
                inv.quantity += qty
                inv.save()

            # ------------ TRANSFER ------------
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

    def save(self, *args, recalc_prices=True, **kwargs):
        doc = self.document
        brand = self.product.brand

        if doc.doc_type == Document.DocType.SALE:
            self.price = Decimal(self.product.sale_price) * self.quantity

        elif doc.doc_type == Document.DocType.WRITE_OFF:
            self.price = Decimal(self.product.sale_price) * self.quantity

        elif doc.doc_type == Document.DocType.TRANSFER:
            self.price = Decimal(0)

        elif doc.doc_type == Document.DocType.PURCHASE:
            total_brand_qty = Decimal(0)

            for item in doc.items.all():  # type: ignore
                if item.product.brand == brand and item.pk != self.pk:
                    total_brand_qty += item.quantity

            total_brand_qty += self.quantity
            
            price_level = (
                ProductPriceLevel.objects
                .filter(
                    product=self.product,
                    minimal_quantity__lte=total_brand_qty
                )
                .order_by('-minimal_quantity')
                .first()
            )

            if not price_level:
                price_level = max(
                    ProductPriceLevel.objects.filter(product=self.product),
                    key=lambda pl: pl.minimal_quantity,
                    default=None
                )

            if not price_level:
                raise ValidationError(f"Для товару '{self.product.name}' не задано рівні цін.")

            self.price = Decimal(price_level.price) * self.quantity
        else:
            self.price = Decimal(0)

        super().save(*args, **kwargs)
        
        if not recalc_prices:
            return
        
        for item in doc.items.all():  # type: ignore
            if item.pk != self.pk:
                item.save(recalc_prices=False)
