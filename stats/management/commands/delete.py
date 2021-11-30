from django.core.management.base import BaseCommand, CommandError

from app.models import AvgLine


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("Deleting all objects...")
        AvgLine.objects.all().delete()
        print("Done.")
