from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime
from django.utils.timezone import make_aware
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
                f"Generating initial stock for {total_days} days for warehouse '{warehouse}'..."
            )
        )
        
        def func_to_show(msg, end="\n"):
            return self.stdout.write(msg, ending=end)
        
        doc = generate_initial_stock(
            warehouse, total_days, target_date=target_date, func_to_show=func_to_show
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done! Created document {doc}."  # type: ignore
            )
        )
