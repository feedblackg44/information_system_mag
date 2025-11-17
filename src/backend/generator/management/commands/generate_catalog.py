from django.core.management.base import BaseCommand
from generator.utils import generate_brands, generate_products
from crm.models import Warehouse


class Command(BaseCommand):
    help = "Generate brands, products and price levels"

    def add_arguments(self, parser):
        parser.add_argument("--brands", type=int, default=5)
        parser.add_argument("--max_products_per_brand", type=int, default=5)
        parser.add_argument("--max_price_levels", type=int, default=5)

    def handle(self, *args, **options):
        brands = generate_brands(options["brands"])
        generate_products(
            brands,
            max_products_per_brand=options["max_products_per_brand"],
            max_price_levels=options["max_price_levels"]
        )

        if not Warehouse.objects.exists():
            Warehouse.objects.create(
                name="Main Warehouse",
                location="Kyiv"
            )
            self.stdout.write(self.style.SUCCESS("Created default warehouse."))

        self.stdout.write(self.style.SUCCESS("Catalog generation complete"))
