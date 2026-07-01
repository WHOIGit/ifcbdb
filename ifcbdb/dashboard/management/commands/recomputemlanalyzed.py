import glob
import multiprocessing as mp
import os

import ifcb
from ifcb.data.files import Fileset, FilesetBin

from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from tqdm import tqdm

from dashboard.models import Bin, DataDirectory, Dataset, bin_query


def _resolve_bin(pid, cached_path, search_dirs):
    """Locate the raw FilesetBin for a pid using only the filesystem (no ORM).

    `cached_path` is the bin's cached basepath (may be empty); `search_dirs` is
    a list of (directory_path, whitelist, blacklist) tuples to search in order.
    This mirrors Bin._get_bin() but is safe to run in a worker process.
    """
    if cached_path and os.path.exists(cached_path + '.adc'):
        return FilesetBin(Fileset(cached_path))
    for directory_path, whitelist, blacklist in search_dirs:
        data_directory = ifcb.DataDirectory(
            directory_path, whitelist=whitelist, blacklist=blacklist)
        try:
            return data_directory[pid]
        except KeyError:
            continue
    return None


def _load_excluded_pids(directory):
    """Collect the set of pids present in all *.parquet files in a directory.

    Only the pid column is read. These bins already have ml_analyzed from the
    parquet workflow, so we skip them entirely (no raw-file read).
    """
    import pyarrow.parquet as pq

    parquet_paths = sorted(glob.glob(os.path.join(directory, '*.parquet')))
    if not parquet_paths:
        raise CommandError('no parquet files found in {}'.format(directory))
    pids = set()
    for parquet_path in parquet_paths:
        table = pq.read_table(parquet_path, columns=['pid'])
        pids.update(table.column('pid').to_pylist())
    return pids, len(parquet_paths)


def _worker(task):
    """Compute ml_analyzed for one bin. Returns (pid, ml_analyzed, resolved_path, error)."""
    pid, cached_path, search_dirs = task
    try:
        raw_bin = _resolve_bin(pid, cached_path, search_dirs)
        if raw_bin is None:
            return pid, None, None, 'fileset not found'
        ml_analyzed = raw_bin.ml_analyzed
        resolved_path = os.path.splitext(raw_bin.fileset.adc_path)[0]
        return pid, ml_analyzed, resolved_path, None
    except Exception as exc:
        return pid, None, None, '{}: {}'.format(type(exc).__name__, exc)


class Command(BaseCommand):
    help = 'recompute ml_analyzed for every bin in a dataset from its raw files'

    def add_arguments(self, parser):
        parser.add_argument('dataset', type=str, help='name of dataset to process')
        parser.add_argument('-j', '--jobs', type=int, default=1,
                            help='number of parallel worker processes (default: 1)')
        parser.add_argument('--exclude-parquet-dir', type=str, default=None,
                            help='directory of bin_ml_analyzed parquet files; bins whose '
                                 'pid appears in them are skipped (catch stragglers only)')
        parser.add_argument('--batch-size', type=int, default=1000,
                            help='number of bins to process per chunk (default: 1000)')

    def _build_task(self, bin_obj):
        # candidate raw directories, mirroring Bin._get_bin() search order:
        # the cached data_directory first, then each dataset's raw dirs by priority
        search_dirs = []
        seen_ids = set()

        def add(directory):
            if (directory is not None and directory.kind == DataDirectory.RAW
                    and directory.id not in seen_ids):
                seen_ids.add(directory.id)
                search_dirs.append((directory.path,
                                    directory.whitelist.split(','),
                                    directory.blacklist.split(',')))

        add(bin_obj.data_directory)
        raw_dirs = [directory
                    for dataset in bin_obj.datasets.all()
                    for directory in dataset.directories.all()
                    if directory.kind == DataDirectory.RAW]
        for directory in sorted(raw_dirs, key=lambda d: d.priority):
            add(directory)
        return bin_obj.pid, bin_obj.path, search_dirs

    def _apply(self, results, bins_by_pid, pbar):
        """Update the in-memory Bin objects from worker results, bulk_update them."""
        batch = []
        updated = failed = 0
        for pid, ml_analyzed, resolved_path, err in results:
            pbar.update(1)
            bin_obj = bins_by_pid[pid]
            if err is not None:
                failed += 1
                pbar.write('{}: {}'.format(pid, err))
                continue
            if ml_analyzed is None or ml_analyzed <= 0:
                failed += 1
                pbar.write('{}: skipping non-positive ml_analyzed: {}'.format(pid, ml_analyzed))
                continue
            bin_obj.set_ml_analyzed(ml_analyzed)
            if resolved_path:
                bin_obj.path = resolved_path
            batch.append(bin_obj)
        if batch:
            Bin.objects.bulk_update(batch, ['ml_analyzed', 'concentration', 'path'])
            updated = len(batch)
        return updated, failed

    def handle(self, *args, **options):
        dataset_name = options['dataset']
        jobs = options['jobs']
        batch_size = options['batch_size']
        exclude_dir = options['exclude_parquet_dir']

        if not Dataset.objects.filter(name=dataset_name).exists():
            raise CommandError('no such dataset: {}'.format(dataset_name))

        excluded = set()
        if exclude_dir is not None:
            if not os.path.isdir(exclude_dir):
                raise CommandError('not a directory: {}'.format(exclude_dir))
            excluded, num_files = _load_excluded_pids(exclude_dir)
            self.stdout.write('excluding {} pids from {} parquet file(s)'.format(
                len(excluded), num_files))

        qs = (bin_query(dataset_name=dataset_name)
              .select_related('data_directory')
              .prefetch_related('datasets__directories')
              .order_by('pid'))
        total = qs.count()
        if total == 0:
            self.stdout.write('no bins found in dataset {}'.format(dataset_name))
            return

        self.stdout.write('processing {} bins in dataset {}{}'.format(
            total, dataset_name,
            ' ({} pids known-excluded via parquet)'.format(len(excluded)) if excluded else ''))

        total_updated = total_failed = total_excluded = 0
        # tqdm total is every bin in the dataset; excluded bins advance the bar
        # without a raw-file read, so a single pass over the queryset suffices.
        pbar = tqdm(total=total)

        pool = None
        if jobs > 1:
            # drop inherited DB connections so forked workers don't share sockets
            connections.close_all()
            pool = mp.Pool(jobs)

        try:
            chunk = []

            def flush(chunk):
                bins_by_pid = {bin_obj.pid: bin_obj for bin_obj in chunk}
                tasks = [self._build_task(bin_obj) for bin_obj in chunk]
                if pool is None:
                    results = (_worker(task) for task in tasks)
                else:
                    results = pool.imap_unordered(_worker, tasks, chunksize=8)
                return self._apply(results, bins_by_pid, pbar)

            for bin_obj in qs.iterator(chunk_size=batch_size):
                if bin_obj.pid in excluded:
                    total_excluded += 1
                    pbar.update(1)
                    continue
                chunk.append(bin_obj)
                if len(chunk) >= batch_size:
                    updated, failed = flush(chunk)
                    total_updated += updated
                    total_failed += failed
                    chunk = []
            if chunk:
                updated, failed = flush(chunk)
                total_updated += updated
                total_failed += failed
        finally:
            if pool is not None:
                pool.close()
                pool.join()
            pbar.close()

        self.stdout.write(self.style.SUCCESS(
            '{}: {} bins updated, {} skipped/failed, {} excluded via parquet'.format(
                dataset_name, total_updated, total_failed, total_excluded)))
