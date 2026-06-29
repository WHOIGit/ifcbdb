import glob
import multiprocessing as mp
import os

import ifcb
from ifcb.data.files import Fileset, FilesetBin

from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from tqdm import tqdm

from dashboard.models import Bin, DataDirectory, Dataset, bin_query


def _resolve_bin(pid, path, dirs):
    """Locate the raw FilesetBin for a pid using only the filesystem (no ORM).

    `path` is the bin's cached basepath (may be empty); `dirs` is a list of
    (directory_path, whitelist, blacklist) tuples to search in order. This
    mirrors Bin._get_bin() but is safe to run in a worker process.
    """
    if path and os.path.exists(path + '.adc'):
        return FilesetBin(Fileset(path))
    for dpath, whitelist, blacklist in dirs:
        dd = ifcb.DataDirectory(dpath, whitelist=whitelist, blacklist=blacklist)
        try:
            return dd[pid]
        except KeyError:
            continue
    return None


def _load_excluded_pids(directory):
    """Collect the set of pids present in all *.parquet files in a directory.

    Only the pid column is read. These bins already have ml_analyzed from the
    parquet workflow, so we skip them entirely (no raw-file read).
    """
    import pyarrow.parquet as pq

    paths = sorted(glob.glob(os.path.join(directory, '*.parquet')))
    if not paths:
        raise CommandError('no parquet files found in {}'.format(directory))
    pids = set()
    for path in paths:
        table = pq.read_table(path, columns=['pid'])
        pids.update(table.column('pid').to_pylist())
    return pids, len(paths)


def _worker(task):
    """Compute ml_analyzed for one bin. Returns (pid, ml, resolved_path, error)."""
    pid, path, dirs = task
    try:
        b = _resolve_bin(pid, path, dirs)
        if b is None:
            return pid, None, None, 'fileset not found'
        ml = b.ml_analyzed
        resolved = os.path.splitext(b.fileset.adc_path)[0]
        return pid, ml, resolved, None
    except Exception as e:
        return pid, None, None, '{}: {}'.format(type(e).__name__, e)


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

    def _build_task(self, bin):
        # candidate raw directories, mirroring Bin._get_bin() search order:
        # the cached data_directory first, then each dataset's raw dirs by priority
        dirs = []
        seen = set()

        def add(d):
            if d is not None and d.kind == DataDirectory.RAW and d.id not in seen:
                seen.add(d.id)
                dirs.append((d.path, d.whitelist.split(','), d.blacklist.split(',')))

        add(bin.data_directory)
        raw = [d for ds in bin.datasets.all() for d in ds.directories.all()
               if d.kind == DataDirectory.RAW]
        for d in sorted(raw, key=lambda d: d.priority):
            add(d)
        return bin.pid, bin.path, dirs

    def _apply(self, results, by_pid, pbar):
        """Update the in-memory Bin objects from worker results, bulk_update them."""
        batch = []
        updated = failed = 0
        for pid, ml, resolved, err in results:
            pbar.update(1)
            bin = by_pid[pid]
            if err is not None:
                failed += 1
                pbar.write('{}: {}'.format(pid, err))
                continue
            if ml is None or ml <= 0:
                failed += 1
                pbar.write('{}: skipping non-positive ml_analyzed: {}'.format(pid, ml))
                continue
            bin.set_ml_analyzed(ml)
            if resolved:
                bin.path = resolved
            batch.append(bin)
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
            excluded, n_files = _load_excluded_pids(exclude_dir)
            self.stdout.write('excluding {} pids from {} parquet file(s)'.format(
                len(excluded), n_files))

        qs = (bin_query(dataset_name=dataset_name)
              .select_related('data_directory')
              .prefetch_related('datasets__directories')
              .order_by('pid'))
        total = qs.count()
        if total == 0:
            self.stdout.write('no bins found in dataset {}'.format(dataset_name))
            return

        # figure out how many bins will actually be recomputed before starting
        if excluded:
            n_to_do = sum(1 for pid in qs.values_list('pid', flat=True)
                          if pid not in excluded)
        else:
            n_to_do = total
        self.stdout.write('recomputing ml_analyzed for {} of {} bins in {} ({} excluded)'.format(
            n_to_do, total, dataset_name, total - n_to_do))
        if n_to_do == 0:
            return

        total_updated = total_failed = total_excluded = 0
        pbar = tqdm(total=n_to_do)

        pool = None
        if jobs > 1:
            # drop inherited DB connections so forked workers don't share sockets
            connections.close_all()
            pool = mp.Pool(jobs)

        try:
            chunk = []

            def flush(chunk):
                by_pid = {b.pid: b for b in chunk}
                tasks = [self._build_task(b) for b in chunk]
                if pool is None:
                    results = (_worker(t) for t in tasks)
                else:
                    results = pool.imap_unordered(_worker, tasks, chunksize=8)
                return self._apply(results, by_pid, pbar)

            for bin in qs.iterator(chunk_size=batch_size):
                if bin.pid in excluded:
                    total_excluded += 1
                    continue
                chunk.append(bin)
                if len(chunk) >= batch_size:
                    u, f = flush(chunk)
                    total_updated += u
                    total_failed += f
                    chunk = []
            if chunk:
                u, f = flush(chunk)
                total_updated += u
                total_failed += f
        finally:
            if pool is not None:
                pool.close()
                pool.join()
            pbar.close()

        self.stdout.write(self.style.SUCCESS(
            '{}: {} bins updated, {} skipped/failed, {} excluded via parquet'.format(
                dataset_name, total_updated, total_failed, total_excluded)))
