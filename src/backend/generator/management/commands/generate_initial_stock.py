from django.core.management.base import BaseCommand
from generator.utils import generate_initial_stock


class Command(BaseCommand):
    help = "Initialize stock levels for all products"

    def add_arguments(self, parser):
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
            "--warehouse",
            type=str,
            default="Main Warehouse",
            help="Warehouse name"
        )

    def handle(self, *args, **options):
        months = options["months"]
        days = options["days"]
        warehouse = options["warehouse"]

        total_days = months * 30 + days
        if total_days <= 0:
            total_days = 90

        self.stdout.write(
            self.style.WARNING(
                f"Generating initial stock for {total_days} days for warehouse '{warehouse}'..."
            )
        )
        
        def func_to_show(msg, end="\n"):
            return self.stdout.write(msg, ending=end)
        
        doc = generate_initial_stock(warehouse, total_days, func_to_show=func_to_show)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done! Created document {doc}."  # type: ignore
            )
        )
