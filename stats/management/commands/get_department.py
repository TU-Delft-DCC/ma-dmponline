from django.core.management.base import BaseCommand
from stats.helpers import print
from stats.mappings import ESBConnection


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("-e", "--email-address", type=str)

    def handle(self, *args, **options):
        email_address = (
            options["email_address"] if options["email_address"] else exit(1)
        )
        esb = ESBConnection()
        print(esb.get_department(email_address))
