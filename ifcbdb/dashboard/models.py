import re

from django.db import models

from django.conf import settings

from django.db.models import Count, Sum, Avg
from django.db.models.functions import Trunc
from django.contrib.gis.db.models import PointField
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance

from django.db.models.signals import pre_save
from django.dispatch import receiver

import pandas as pd

import ifcb

from ifcb.data.stitching import InfilledImages
from ifcb.viz.mosaic import Mosaic

from .crypto import AESCipher

FILL_VALUE = -9999

class Dataset(models.Model):
    name = models.CharField(max_length=64, unique=True)
    title = models.CharField(max_length=256)

    def time_range(self, start_time=None, end_time=None):
        qs = self.bins
        if start_time is not None:
            ts = pd.to_datetime(start_time, utc=True)
            qs = qs.filter(sample_time__gte=ts)
        if end_time is not None:
            ts = pd.to_datetime(end_time, utc=True)
            qs = qs.filter(sample_time__lte=ts)
        return qs

    def most_recent_bin(self, time=None):
        qs = self.time_range(end_time=time).order_by('-sample_time')
        return qs.first()

    def closest_bin(self, longitude, latitude):
        location = Point(longitude, latitude, srid=4326)
        return self.bins.annotate(
            distance=Distance('location', location)
        ).order_by('distance').first()

    def timeline(self, start_time=None, end_time=None, metric='size', resolution='day'):
        if resolution not in ['month','day','hour']:
            raise ValueError('unsupported time resolution {}'.format(resoution))
        qs = self.time_range(start_time, end_time)
        return qs.all().annotate(dt=Trunc('sample_time', resolution)). \
                values('dt').annotate(metric=Avg(metric))

    def __str__(self):
        return self.name

DATA_DIRECTORY_RAW = 'raw'

class DataDirectory(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name='directories')
    path = models.CharField(max_length=512) # absolute path
    kind = models.CharField(max_length=32, default=DATA_DIRECTORY_RAW)
    priority = models.IntegerField(default=1) # order in which directories are searched (lower ealier)
    last_synced = models.DateTimeField('time of last db sync', blank=True, null=True)
    # parameters controlling searching (simple comma separated fields because we don't have to query on these)
    whitelist = models.CharField(max_length=512, default='data') # comma separated list of directory names to search
    blacklist = models.CharField(max_length=512, default='skip,bad') # comma separated list of directory names to skip

    def _get_directory(self):
        # return the underlying ifcb.DataDirectory
        whitelist = re.split(',', self.whitelist)
        blacklist = re.split(',', self.blacklist)
        return ifcb.DataDirectory(self.path, whitelist=whitelist, blacklist=blacklist)

    def __str__(self):
        return '{} ({})'.format(self.path, self.kind)

class Bin(models.Model):
    # bin's permanent identifier (e.g., D20190102T1234_IFCB927)
    pid = models.CharField(max_length=64, unique=True)
    # the parsed bin timestamp
    timestamp = models.DateTimeField('bin timestamp')
    # spatiotemporal information
    sample_time = models.DateTimeField('sample time')
    location = PointField(default=Point())
    depth = models.FloatField(default=0)
    # instrument
    instrument = models.ForeignKey('Instrument', related_name='bins', null=True, on_delete=models.SET_NULL)
    # many-to-many relationship with datasets
    datasets = models.ManyToManyField('Dataset', related_name='bins')
    # qaqc flags
    qc_bad = models.BooleanField(default=False) # is this bin invalid
    qc_no_rois = models.BooleanField(default=False)
    # metadata JSON
    metadata = models.CharField(max_length=8192, default='{}')
    # metrics
    size = models.IntegerField(default=0) # size of raw data in bytes
    temperature = models.FloatField(default=FILL_VALUE)
    humidity = models.FloatField(default=FILL_VALUE)
    run_time = models.FloatField(default=FILL_VALUE)
    look_time = models.FloatField(default=FILL_VALUE)
    ml_analyzed = models.FloatField(default=FILL_VALUE)

    def set_location(self, longitude, latitude):
        # convenience function for setting location w/o having to construct Point object
        self.location = Point(longitude, latitude, srid=4326)

    def _get_bin(self):
        # return the underlying ifcb.Bin object backed by the raw filesets
        for dataset in self.datasets.all():
            for directory in dataset.directories.filter(kind=DATA_DIRECTORY_RAW).order_by('priority'):
                dd = directory._get_directory()
                try:
                    return dd[self.pid]
                except KeyError:
                    pass # keep searching
        raise KeyError('cannot find fileset for {}'.format(self))

    def image(self, target_number):
        b = self._get_bin()
        with b.as_single(target_number) as subset:
            ii = InfilledImages(subset) # handle old-style data
            try:
                return ii[target_number]
            except IndexError as e:
                raise KeyError('no such image {} {}'.format(self.pid, target_number)) from e
            except pd.errors.EmptyDataError as e:
                raise KeyError('no such image {} {}'.format(self.pid, target_number)) from e

    def list_images(self):
        b = self._get_bin()
        ii = InfilledImages(b) # handle old-style data
        return list(ii.keys())

    def mosaic(self, page=0, shape=(600,800), scale=0.33, bgcolor=200):
        b = self._get_bin()
        m = Mosaic(b, shape, scale=scale, bgcolor=bgcolor)
        coordinates = m.pack() # cache this somehow
        image = m.page(page)
        return image, coordinates        

    def target_id(self, target_number):
        return ifcb.Pid(self.pid).with_target(target_number)

    def target_metadata(self, target_number):
        b = self._get_bin()
        # FIXME return as dict keyed by column name
        return b[target_number]

    def __str__(self):
        return self.pid

class Instrument(models.Model):
    number = models.IntegerField(unique=True)
    version = models.IntegerField(default=2)
    # nickname is optional, not everyone names their IFCB
    nickname = models.CharField(max_length=64)
    # connection parameters for Samba
    address = models.CharField(max_length=128) # ip address or dns name
    username = models.CharField(max_length=64)
    _password = models.CharField(max_length=128, db_column='password')
    share_name = models.CharField(max_length=128, default='Data')

    @staticmethod
    def _get_cipher():
        return AESCipher(settings.IFCB_PASSWORD_KEY)

    def set_password(self, password):
        cipher = self._get_cipher()
        self._password = cipher.encrypt(password)

    def get_password(self):
        cipher = self._get_cipher()
        ciphertext = self._password
        if not ciphertext:
            return None
        return cipher.decrypt(ciphertext)

    password = property(get_password, set_password)

    def __str__(self):
        return 'IFCB{}'.format(self.number)

@receiver(pre_save, sender=Bin)
def _lazy_instrument_create(sender, **kw):
    """automatically associate an Instrument with a bin,
    creating the instrument if it does not exist"""
    b = kw['instance']
    instrument_number = ifcb.Pid(b.pid).instrument
    try:
        i = Instrument.objects.get(number=instrument_number)
    except Instrument.DoesNotExist:
        i = Instrument(number=instrument_number)
        i.save()
    b.instrument = i