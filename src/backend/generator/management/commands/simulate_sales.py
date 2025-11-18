from django.core.management.base import BaseCommand
from generator.utils import simulate_sales


class Command(BaseCommand):
    help = "Simulates sales for a given period"

    def add_arguments(self, parser):
        parser.add_argument("--months", type=int, default=0)
        parser.add_argument("--days", type=int, default=0)
        parser.add_argument("--min-remain", type=float, default=0.0)
        parser.add_argument("--max-remain", type=float, default=0.1)

    def handle(self, *args, **opts):
        total_days = opts["months"] * 30 + opts["days"]
        if total_days == 0:
            total_days = 90

        self.stdout.write(f"Simulating sales for {total_days} days...")

        def func_to_show(message, end="\n"):
            self.stdout.write(message, ending=end)
        
        simulate_sales(
            total_days,
            min_remain=opts["min_remain"],
            max_remain=opts["max_remain"],
            func_to_show=func_to_show
        )

        self.stdout.write(self.style.SUCCESS("Done!"))
