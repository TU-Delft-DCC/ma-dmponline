from stats.mappings import Mappings
from django.core.management.base import BaseCommand
from stats.helpers import print


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("-i", "--id", type=int)

    def handle(self, *args, **options):
        plan_id = options["id"] if options["id"] else exit(1)
        mapping = Mappings(v1=True)
        print(mapping.get_start_end_date(plan_id))
