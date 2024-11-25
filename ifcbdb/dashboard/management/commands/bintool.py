from django.core.management.base import BaseCommand
from django.utils import timezone
from dashboard.models import bin_query, Dataset

class Command(BaseCommand):
    help = 'Filter bins, optionally remove/add them from/to datasets, and output the list of bin IDs'

    def add_arguments(self, parser):
        parser.add_argument('--dataset', type=str, help='Dataset name')
        parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
        parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
        parser.add_argument('--tags', nargs='+', help='List of tags')
        parser.add_argument('--instrument', type=int, help='Instrument number')
        parser.add_argument('--cruise', type=str, help='Cruise')
        parser.add_argument('--include-skipped', action='store_true', help='Include skipped bins')
        parser.add_argument('--sample-type', type=str, help='Sample type')
        parser.add_argument('--remove-dataset', type=str, help='Dataset name to remove filtered bins from')
        parser.add_argument('--add-dataset', type=str, help='Dataset name to add filtered bins to')

    def handle(self, *args, **options):
        dataset_name = options['dataset']
        start = timezone.datetime.strptime(options['start'], '%Y-%m-%d').date() if options['start'] else None
        end = timezone.datetime.strptime(options['end'], '%Y-%m-%d').date() if options['end'] else None
        tags = options['tags'] or []
        instrument_number = options['instrument']
        cruise = options['cruise']
        filter_skip = not options['include_skipped']
        sample_type = options['sample_type']
        remove_dataset_name = options.get('remove_dataset')
        add_dataset_name = options.get('add_dataset')

        bins = bin_query(
            dataset_name=dataset_name,
            start=start,
            end=end,
            tags=tags,
            instrument_number=instrument_number,
            cruise=cruise,
            filter_skip=filter_skip,
            sample_type=sample_type
        )

        bin_ids = bins.values_list('pid', flat=True)

        if remove_dataset_name is not None:
            try:
                dataset = Dataset.objects.get(name=remove_dataset_name)
                dataset.bins.through.objects.filter(bin__in=bins, dataset=dataset).delete()
                self.stdout.write(f"Removed filtered bins from dataset: {remove_dataset_name}")
            except Dataset.DoesNotExist:
                self.stderr.write(f"Dataset '{remove_dataset_name}' does not exist.")

        if add_dataset_name is not None:
            try:
                dataset = Dataset.objects.get(name=add_dataset_name)
                dataset.bins.add(*bins)
                self.stdout.write(f"Added filtered bins to dataset: {add_dataset_name}")
            except Dataset.DoesNotExist:
                self.stderr.write(f"Dataset '{add_dataset_name}' does not exist.")

        for bin_id in bin_ids:
            self.stdout.write(bin_id)