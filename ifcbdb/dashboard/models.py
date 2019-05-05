import re

from django.db import models

from django.conf import settings

from django.db.models import F, Count, Sum, Avg
from django.db.models.functions import Trunc
from django.contrib.gis.db.models import PointField
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance

from django.db.models.signals import pre_save
from django.dispatch import receiver

from django.core.cache import cache

import pandas as pd

import ifcb

from ifcb.data.stitching import InfilledImages
from ifcb.viz.mosaic import Mosaic
from ifcb.viz.blobs import blob_outline
from ifcb.data.adc import schema_names
from ifcb.data.products.blobs import BlobDirectory
from ifcb.data.zip import bin2zip_stream

from .crypto import AESCipher

FILL_VALUE = -9999
SRID = 4326

class Timeline(object):

    TIMELINE_METRICS = {
        "size": "Bytes",
        "temperature": "Degrees C",
        "humidity": "Percentage",
        "run_time": "Seconds",
        "look_time": "Seconds",
        "ml_analyzed": "Milliliters",
        'concentration': 'Cells / ml',
        'n_triggers': 'Count',
        'n_images': 'Count',
    }

    def __init__(self, bin_qs):
        self.bins = bin_qs

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

    def previous_bin(self, bin):
        return self.bins.filter(sample_time__lt=bin.sample_time).order_by("-sample_time").first()

    def next_bin(self, bin):
        return self.bins.filter(sample_time__gt=bin.sample_time).order_by("sample_time").first()

    def closest_bin(self, longitude, latitude):
        location = Point(longitude, latitude, srid=SRID)
        return self.bins.annotate(
            distance=Distance('location', location)
        ).order_by('distance').first()

    def metrics(self, metric, start_time=None, end_time=None, resolution='day'):
        if resolution not in ['month', 'day', 'hour', 'bin']:
            raise ValueError('unsupported time resolution {}'.format(resolution))

        if metric not in self.TIMELINE_METRICS.keys():
            raise ValueError('unsupported metric {}'.format(metric))

        qs = self.time_range(start_time, end_time)

        if resolution == 'bin':
            return qs.annotate(dt=F('sample_time'),metric=F(metric)).values('dt','metric')
        else:
            return qs.all().annotate(dt=Trunc('sample_time', resolution)). \
                    values('dt').annotate(metric=Avg(metric))

    def metric_label(self, metric):
        if metric not in self.TIMELINE_METRICS.keys():
            return ""

        return self.TIMELINE_METRICS[metric]

class Dataset(models.Model):
    name = models.CharField(max_length=64, unique=True)
    title = models.CharField(max_length=256)

    def tag_cloud(self, instrument=None):
        return Tag.cloud(dataset=self, instrument=instrument)

    def __str__(self):
        return self.name

DATA_DIRECTORY_RAW = 'raw'
DATA_DIRECTORY_BLOBS = 'blobs'

class DataDirectory(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name='directories')
    path = models.CharField(max_length=512) # absolute path
    kind = models.CharField(max_length=32, default=DATA_DIRECTORY_RAW)
    priority = models.IntegerField(default=1) # order in which directories are searched (lower ealier)
    last_synced = models.DateTimeField('time of last db sync', blank=True, null=True)
    # parameters controlling searching (simple comma separated fields because we don't have to query on these)
    whitelist = models.CharField(max_length=512, default='data') # comma separated list of directory names to search
    blacklist = models.CharField(max_length=512, default='skip,bad') # comma separated list of directory names to skip
    # for product directories, the product version
    version = models.IntegerField(null=True)

    def get_raw_directory(self):
        if self.kind != DATA_DIRECTORY_RAW:
            raise ValueError('not a raw directory')
        # return the underlying ifcb.DataDirectory
        whitelist = re.split(',', self.whitelist)
        blacklist = re.split(',', self.blacklist)
        return ifcb.DataDirectory(self.path, whitelist=whitelist, blacklist=blacklist)

    def get_blob_directory(self):
        if self.kind != DATA_DIRECTORY_BLOBS:
            raise ValueError('not a blobs directory')
        return BlobDirectory(self.path, self.version)

    def __str__(self):
        return '{} ({})'.format(self.path, self.kind)

class Bin(models.Model):
    # bin's permanent identifier (e.g., D20190102T1234_IFCB927)
    pid = models.CharField(max_length=64, unique=True)
    # the parsed bin timestamp
    timestamp = models.DateTimeField('bin timestamp')
    # spatiotemporal information
    sample_time = models.DateTimeField('sample time')
    location = PointField(null=True)
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
    n_triggers = models.IntegerField(default=0)
    n_images = models.IntegerField(default=0)
    temperature = models.FloatField(default=FILL_VALUE)
    humidity = models.FloatField(default=FILL_VALUE)
    run_time = models.FloatField(default=FILL_VALUE)
    look_time = models.FloatField(default=FILL_VALUE)
    ml_analyzed = models.FloatField(default=FILL_VALUE)
    concentration = models.FloatField(default=FILL_VALUE)

    # tags
    tags = models.ManyToManyField('Tag', through='TagEvent')

    def set_location(self, longitude, latitude):
        # convenience function for setting location w/o having to construct Point object
        self.location = Point(longitude, latitude, srid=SRID)

    @property
    def latitude(self):
        if self.location is None:
            return FILL_VALUE
        return self.location.y

    @property
    def longitude(self):
        if self.location is None:
            return FILL_VALUE
        return self.location.x
    
    # access to underlying FilesetBin objects

    def _directories(self, kind=DATA_DIRECTORY_RAW, version=None):
        for dataset in self.datasets.all():
            qs = dataset.directories.filter(kind=kind)
            if version is not None:
                qs = qs.filter(version=version)
            for directory in qs.order_by('priority'):
                yield directory

    def _get_bin(self):
        # return the underlying ifcb.Bin object backed by the raw filesets
        for directory in self._directories(kind=DATA_DIRECTORY_RAW):
            dd = directory.get_raw_directory()
            try:
                return dd[self.pid]
            except KeyError:
                pass # keep searching
        raise KeyError('cannot find fileset for {}'.format(self))

    # access to raw files

    def adc_path(self):
        return self._get_bin().fileset.adc_path

    def hdr_path(self):
        return self._get_bin().fileset.hdr_path

    def roi_path(self):
        return self._get_bin().fileset.roi_path

    # access to images

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

    # access to blobs

    def blob_file(self, version=2):
         for directory in self._directories(kind=DATA_DIRECTORY_BLOBS, version=version):
            bd = directory.get_blob_directory()
            try:
                return bd[self.pid]
            except KeyError as e:
                raise KeyError('no blobs found for {}'.format(self.pid)) from e

    def blob_path(self, version=2):
        return self.blob_file(version=version).path

    def blob(self, target_number, version=2):
        bf = self.blob_file(version=version)
        try:
            return bf[target_number]
        except KeyError as e:
            raise KeyError('no such blob {} {}'.format(self.pid, target_number)) from e

    def outline(self, target_number, blob_version=2, outline_color=[255, 0, 0]):
        image = self.image(target_number)
        blob = self.blob(target_number, version=blob_version)
        out = blob_outline(image, blob, outline_color=outline_color)
        return out

    # mosaics

    def mosaic_coordinates(self, shape=(600,800), scale=0.33, ifcb_bin=None):
        h, w = shape
        b = self._get_bin() if ifcb_bin is None else ifcb_bin
        cache_key = 'mosaic_coords_{}_{}x{}_{}'.format(self.pid, h, w, int(scale*100))
        pickled = cache.get(cache_key)
        if pickled is not None:
            coordinates = pd.DataFrame.from_dict(pickled)
            m = Mosaic(b, shape, scale=scale, coordinates=coordinates)
        else:
            m = Mosaic(b, shape, scale=scale)
            coordinates = m.pack()
            cache.set(cache_key, coordinates.to_dict('list'), timeout=None) # cache indefinitely
        return coordinates

    def mosaic(self, page=0, shape=(600,800), scale=0.33, bg_color=200):
        b = self._get_bin()
        coordinates = self.mosaic_coordinates(shape, scale, ifcb_bin=b)
        m = Mosaic(b, shape, scale=scale, bg_color=bg_color, coordinates=coordinates)
        image = m.page(page)
        return image, coordinates        

    def target_id(self, target_number):
        return ifcb.Pid(self.pid).with_target(target_number)

    def target_metadata(self, target_number):
        b = self._get_bin()
        metadata = b[target_number]
        names = schema_names(b.schema)
        return dict(zip(names, metadata))

    # zip file
    def zip(self):
        return bin2zip_stream(self._get_bin())

    # tags

    @property
    def tag_names(self):
        return [t.name for t in self.tags.all()]

    def add_tag(self, tag_name):
        tag, created = Tag.objects.get_or_create(name=tag_name)
        # don't add this tag if was already added
        event, created = TagEvent.objects.get_or_create(bin=self, tag=tag)
        return event

    def delete_tag(self, tag_name):
        tag = Tag.objects.get(name=tag_name)
        event = TagEvent.objects.get(bin=self, tag=tag)
        event.delete()

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

    def tag_cloud(self, dataset=None):
        return Tag.cloud(instrument=self, dataset=dataset)

    def __str__(self):
        return 'IFCB{}'.format(self.number)

@receiver(pre_save, sender=Bin)
def _lazy_instrument_create(sender, **kw):
    """automatically associate an Instrument with a bin,
    creating the instrument if it does not exist"""
    b = kw['instance']
    pid = ifcb.Pid(b.pid)
    instrument_number = pid.instrument
    version = pid.schema_version
    try:
        i = Instrument.objects.get(number=instrument_number)
    except Instrument.DoesNotExist:
        i = Instrument(number=instrument_number, version=version)
        i.save()
    b.instrument = i

# tags

class Tag(models.Model):
    name = models.CharField(max_length=128)

    # Timeline()
    @staticmethod
    def cloud(dataset=None, instrument=None):
        qs = TagEvent.objects
        if dataset is not None:
            qs = qs.filter(bin__datasets=dataset)
        if instrument is not None:
            qs = qs.filter(bin__instrument=instrument)
        return qs.values('tag').annotate(count=Count('tag')).values('tag__name','count')

    def __str__(self):
        return self.name

class TagEvent(models.Model):
    bin = models.ForeignKey(Bin, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)

    timestamp = models.DateTimeField(auto_now_add=True, blank=True)
    # FIXME add user (which can be null)]

    def __str__(self):
        return '{} tagged {}'.format(self.bin, self.tag)