from django.core.management.base import BaseCommand, CommandError

from app.models import AvgLine


class Command(BaseCommand):
    def handle(self, *args, **options):
        print(AvgLine.objects.all().count())
