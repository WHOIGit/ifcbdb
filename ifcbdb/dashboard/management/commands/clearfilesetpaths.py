from django.core.management.base import BaseCommand, CommandError
from tqdm import tqdm

from dashboard.models import Bin, Dataset, bin_query


class Command(BaseCommand):
    help = ('clear cached fileset paths for every bin in a dataset, forcing '
            'each bin to re-resolve its raw fileset from the data directories '
            'on next access')

    def add_arguments(self, parser):
        parser.add_argument('dataset', type=str, help='name of dataset to process')
        parser.add_argument('--keep-data-directory', action='store_true',
                            help='clear only the cached path, leaving the cached '
                                 'data_directory pointer in place')
        parser.add_argument('--dry-run', action='store_true',
                            help='report how many bins would be cleared without '
                                 'writing any changes')
        parser.add_argument('--batch-size', type=int, default=1000,
                            help='number of bins to update per bulk_update (default: 1000)')

    def handle(self, *args, **options):
        dataset_name = options['dataset']
        batch_size = options['batch_size']
        keep_dd = options['keep_data_directory']
        dry_run = options['dry_run']

        if not Dataset.objects.filter(name=dataset_name).exists():
            raise CommandError('no such dataset: {}'.format(dataset_name))

        # filter_skip=False so skipped bins get their cache cleared too
        qs = (bin_query(dataset_name=dataset_name, filter_skip=False)
              .order_by('pid'))
        total = qs.count()
        if total == 0:
            self.stdout.write('no bins found in dataset {}'.format(dataset_name))
            return

        fields = ['path'] if keep_dd else ['path', 'data_directory']
        self.stdout.write('{}clearing cached fileset path{} for {} bins in dataset {}'.format(
            '[dry run] would be ' if dry_run else '',
            '' if keep_dd else ' and data_directory', total, dataset_name))

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                '{}: dry run, no changes written ({} bins would be cleared)'.format(
                    dataset_name, total)))
            return

        cleared = 0
        batch = []
        pbar = tqdm(total=total)

        def flush(batch):
            if batch:
                Bin.objects.bulk_update(batch, fields)
            return len(batch)

        for bin_obj in qs.iterator(chunk_size=batch_size):
            bin_obj.path = ''
            if not keep_dd:
                bin_obj.data_directory = None
            batch.append(bin_obj)
            pbar.update(1)
            if len(batch) >= batch_size:
                cleared += flush(batch)
                batch = []
        cleared += flush(batch)
        pbar.close()

        self.stdout.write(self.style.SUCCESS(
            '{}: cleared cached fileset paths for {} bins'.format(dataset_name, cleared)))
