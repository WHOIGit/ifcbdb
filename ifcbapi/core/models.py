from django.db import models
from django.contrib.gis.db.models import PointField
from django.contrib.auth.models import User


FILL_VALUE = -9999999

# TODO: ALl of these models were copied from the ifcbdb project - where does the final copy "live", and which project
#     :   is going to be responsible for database migrations


class Dataset(models.Model):
    name = models.CharField(max_length=64, unique=True)
    title = models.CharField(max_length=256)
    is_active = models.BooleanField(blank=False, null=False, default=True)

    # for fixed deployment
    location = PointField(null=True, blank=True)
    depth = models.FloatField(null=True, blank=True)

    # doi
    doi = models.CharField(max_length=256, blank=True)
    # attribution and funding
    attribution = models.CharField(max_length=512, blank=True)
    funding = models.CharField(max_length=512, blank=True)

    class Meta:
        db_table = 'dashboard_dataset'
        managed = False


class DataDirectory(models.Model):
    # directory types
    RAW = 'raw'
    BLOBS = 'blobs'
    FEATURES = 'features'
    CLASS_SCORES = 'class_scores'

    DEFAULT_VERSION = 2

    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name='directories')
    path = models.CharField(max_length=512) # absolute path
    kind = models.CharField(max_length=32, default=RAW)
    priority = models.IntegerField(default=1) # order in which directories are searched (lower ealier)
    last_synced = models.DateTimeField('time of last db sync', blank=True, null=True)
    # parameters controlling searching (simple comma separated fields because we don't have to query on these)
    whitelist = models.CharField(max_length=512, default='data') # comma separated list of directory names to search
    blacklist = models.CharField(max_length=512, default='skip,bad') # comma separated list of directory names to skip
    # for product directories, the product version
    version = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'dashboard_datadirectory'
        managed = False


class Bin(models.Model):
    # bin's permanent identifier (e.g., D20190102T1234_IFCB927)
    pid = models.CharField(max_length=64, unique=True)
    # the parsed bin timestamp
    timestamp = models.DateTimeField('bin timestamp', db_index=True)
    # spatiotemporal information
    sample_time = models.DateTimeField('sample time', db_index=True)
    location = PointField(null=True)
    depth = models.FloatField(null=True)
    # instrument
    instrument = models.ForeignKey('Instrument', related_name='bins', null=True, on_delete=models.SET_NULL)
    # many-to-many relationship with datasets
    datasets = models.ManyToManyField('Dataset', related_name='bins')
    # accession
    added = models.DateTimeField(auto_now_add=True, null=True)
    # qaqc flags
    qc_bad = models.BooleanField(default=False) # is this bin invalid
    qc_no_rois = models.BooleanField(default=False)
    skip = models.BooleanField(default=False) # user wants to ignore this file
    # metadata JSON
    metadata_json = models.CharField(max_length=8192, default='{}', db_column='metadata')
    # metrics
    size = models.BigIntegerField(default=0) # size of raw data in bytes
    n_triggers = models.IntegerField(default=0)
    n_images = models.IntegerField(default=0)
    temperature = models.FloatField(default=FILL_VALUE)
    humidity = models.FloatField(default=FILL_VALUE)
    run_time = models.FloatField(default=FILL_VALUE)
    look_time = models.FloatField(default=FILL_VALUE)
    ml_analyzed = models.FloatField(default=FILL_VALUE)
    concentration = models.FloatField(default=FILL_VALUE)
    # metadata about sampling
    sample_type = models.CharField(max_length=128, blank=True)
    # for at-sea samples we need a code identifying the cruise
    cruise = models.CharField(max_length=128, blank=True)
    # for casts we need cast and niskin number
    # casts sometimes have numbers like "2a"
    cast = models.CharField(max_length=64, blank=True)
    # niskin numbers should always be integers
    niskin = models.IntegerField(null=True)

    # tags
    tags = models.ManyToManyField('Tag', through='TagEvent')

    MOSAIC_SCALE_FACTORS = [25, 33, 66, 100]
    MOSAIC_VIEW_SIZES = ["640x480", "800x600", "800x1280", "1080x1920"]
    MOSAIC_DEFAULT_SCALE_FACTOR = 33
    MOSAIC_DEFAULT_VIEW_SIZE = "800x600"

    class Meta:
        db_table = 'dashboard_bin'
        managed = False


class Instrument(models.Model):
    number = models.IntegerField(unique=True)
    version = models.IntegerField(default=2)
    # nickname is optional, not everyone names their IFCB
    nickname = models.CharField(max_length=64, blank=True)
    # connection parameters for Samba
    address = models.CharField(max_length=128, blank=True)  # ip address or dns name
    username = models.CharField(max_length=64, blank=True)
    _password = models.CharField(max_length=128, db_column='password', blank=True)
    share_name = models.CharField(max_length=128, default='Data', blank=True)
    timeout = models.IntegerField(default=30)

    class Meta:
        db_table = 'dashboard_instrument'
        managed = False


class Tag(models.Model):
    name = models.CharField(max_length=128)

    class Meta:
        db_table = 'dashboard_tag'
        managed = False


class TagEvent(models.Model):
    bin = models.ForeignKey(Bin, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)
    user = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)

    timestamp = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        db_table = 'dashboard_tagevent'
        managed = False


class Comment(models.Model):
    bin = models.ForeignKey(Bin, on_delete=models.CASCADE, related_name='comments')
    content = models.CharField(max_length=8192)
    user = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)

    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'dashboard_comment'
        managed = False
