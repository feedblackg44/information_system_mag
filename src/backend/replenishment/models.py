from decimal import Decimal

from erp.models import Product, Warehouse
from django.conf import settings
from django.db import models


class TaskNotification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = models.TextField()
    message_type = models.CharField(max_length=20, default='success') # success, error, warning
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Notification for {self.user}: {self.message[:20]}"


class ForecastData(models.Model):
    """
    Stores the result of the Prophet forecast (ADS).
    This table is typically updated by a nightly background job.
    """

    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name="forecast_data",
        verbose_name="Продукт",
    )
    ads = models.DecimalField(
        "Середньодобовий продаж (ADS)",
        max_digits=10,
        decimal_places=2,
        default=Decimal(0),
    )
    last_updated = models.DateTimeField("Останнє оновлення", auto_now=True)

    def __str__(self):
        return f"ADS for {self.product.sku}: {self.ads}"


class ReplenishmentReport(models.Model):
    """
    Represents one run of the replenishment algorithm. Stores global parameters.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Чернетка (розрахунок)"
        ORDER_CREATED = "ORDER_CREATED", "Замовлення сформовано"

    created_at = models.DateTimeField("Створено", auto_now_add=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Користувач"
    )
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.CASCADE, verbose_name="Склад поповнення"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="Статус",
    )

    global_coverage_days = models.PositiveIntegerField(
        "Цільове покриття (днів)", default=14
    )
    global_credit_terms = models.PositiveIntegerField(
        "Кредитні умови (днів)", default=45
    )
    
    min_budget = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal(0))
    max_budget = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal(0))
    max_investment_period = models.PositiveIntegerField(default=0)
    
    deals_variants_json = models.BinaryField(
        "Дані алгоритму (Pickle)", 
        null=True, blank=True
    )

    def __str__(self):
        return f"Звіт №{self.id} від {self.user} ({self.created_at.date()})"  # type: ignore


class ReplenishmentItem(models.Model):
    """
    A single row in the replenishment table.
    Uses denormalization (snapshots) for auditability but retains FKs for integrity.
    """

    report = models.ForeignKey(
        ReplenishmentReport,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Звіт",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        verbose_name="Продукт (ID)",
    )
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.CASCADE, verbose_name="Склад"
    )

    brand_name = models.CharField("Бренд", max_length=128)
    product_sku = models.CharField("SKU Продукту", max_length=64)
    product_name = models.CharField("Назва Продукту", max_length=256)

    inventory = models.DecimalField(
        "Запаси на складі", max_digits=10, decimal_places=2, default=Decimal(0)
    )
    average_daily_sales = models.DecimalField(
        "Середньодобовий продаж (ADS)", max_digits=10, decimal_places=2
    )
    sale_price = models.DecimalField("Ціна продажу", max_digits=10, decimal_places=2)

    purchase_price = models.DecimalField(
        "Закупівельна ціна", max_digits=10, decimal_places=2
    )
    pricelevel_minimum_quantity = models.PositiveIntegerField(
        "Мін. кількість для ціни", default=1
    )

    system_coverage_days = models.PositiveIntegerField(
        "Цільове покриття (днів)", default=0
    )
    credit_terms = models.PositiveIntegerField("Кредитні умови (днів)", default=0)
    system_suggested_quantity = models.PositiveIntegerField(
        "Система пропонує замовити", default=0
    )

    best_quantity = models.PositiveIntegerField(
        "Оптимальна кількість для замовлення", default=0
    )

    class Meta:
        unique_together = ("report", "product", "warehouse")
        verbose_name = "Рядок поповнення"
        verbose_name_plural = "Рядки поповнення"
        
        ordering = ['product__brand__name', 'product__sku']

    def __str__(self):
        return f"{self.product_sku} ({self.product_name}) у Звіті №{self.report.id}"  # type: ignore
