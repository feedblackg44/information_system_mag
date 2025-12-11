from erp.models import Warehouse
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime
from django.utils.timezone import make_aware
from generator.utils import generate_brands, generate_products, empty_warehouse


class Command(BaseCommand):
    help = "Generate brands, products and price levels"

    def add_arguments(self, parser):
        parser.add_argument("--warehouse", type=str, default="Main Warehouse")
        parser.add_argument("--brands", type=int, default=30)
        parser.add_argument("--max-products-per-brand", type=int, default=10)
        parser.add_argument("--max-price-levels", type=int, default=5)
        parser.add_argument("--from-scratch", action="store_true")
        
        parser.add_argument(
            "--months",
            type=int,
            default=0,
            help="Amount of months"
        )

        parser.add_argument(
            "--days",
            type=int,
            default=0,
            help="Amount of days"
        )
        
        parser.add_argument(
            "--datetime",
            type=str,
            default="",
            help="Date in YYYY-MM-DD HH:MM:SS format"
        )
        

    def handle(self, *args, **options):
        months = options["months"]
        days = options["days"]
        warehouse = options["warehouse"]
        date_str = options["datetime"]
        
        if date_str:
            dt = parse_datetime(date_str)
            if dt:
                target_date = make_aware(dt)
            else:
                raise ValueError("Wrong datetime format.")
        else:
            target_date = None

        total_days = months * 30 + days
        if total_days <= 0:
            total_days = 90

        self.stdout.write(
            self.style.WARNING(
                f"Generating for {total_days} days for warehouse '{warehouse}'..."
            )
        )
        
        if not Warehouse.objects.exists():
            Warehouse.objects.create(
                name="Main Warehouse",
                location="Kyiv"
            )
            self.stdout.write(self.style.SUCCESS("Created default warehouse"))

        def func_to_show(msg, end="\n"):
            return self.stdout.write(msg, ending=end)
        
        if options["from_scratch"]:
            empty_warehouse(warehouse, func_to_show=func_to_show)
        
        brands = generate_brands(options["brands"])
        
        generate_products(
            warehouse,
            brands,
            total_days,
            target_date=target_date,
            max_products_per_brand=options["max_products_per_brand"],
            max_price_levels=options["max_price_levels"],
            func_to_show=func_to_show
        )

        self.stdout.write(self.style.SUCCESS("Catalog and inventory generation complete"))
