import json
import pandas as pd
from datetime import timedelta, datetime

from django.conf import settings
from django.shortcuts import render, get_object_or_404, reverse
from django.http import HttpResponse, FileResponse, Http404, HttpResponseBadRequest, JsonResponse, HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import cache_control

from django.core.cache import cache
from celery.result import AsyncResult

from ifcb.data.imageio import format_image
from ifcb.data.adc import schema_names

from .models import Dataset, Bin, Timeline, bin_query
from common.utilities import *

from .tasks import mosaic_coordinates_task

# TODO: The naming convensions for the dataset, bin and image ID's needs to be cleaned up and be made
#   more consistent

def index(request):
    if settings.DEFAULT_DATASET:
        return HttpResponseRedirect(reverse("dataset", kwargs={"dataset_name": settings.DEFAULT_DATASET}))

    return HttpResponseRedirect(reverse("datasets"))


def datasets(request):
    datasets = Dataset.objects.filter(is_active=True).order_by('title')

    return render(request, 'dashboard/datasets.html', {
        "datasets": datasets,
    })


# TODO: Configure link needs proper permissions (more than just user is authenticated)
# TODO: Handle a dataset with no bins? Is that possible?
def dataset_details(request, dataset_name, bin_id=None):
    dataset = get_object_or_404(Dataset, name=dataset_name)
    if not bin_id:
        bin_id = request.GET.get("bin_id")

    if bin_id is None:
        bin = Timeline(dataset.bins).most_recent_bin()
    else:
        bin = get_object_or_404(Bin, pid=bin_id)

    return render(request, 'dashboard/dataset-details.html', {
        "can_share_page": True,
        "dataset": dataset,
        "bin": bin,
        "mosaic_scale_factors": Bin.MOSAIC_SCALE_FACTORS,
        "mosaic_view_sizes": Bin.MOSAIC_VIEW_SIZES,
        "mosaic_default_scale_factor": Bin.MOSAIC_DEFAULT_SCALE_FACTOR,
        "mosaic_default_view_size": Bin.MOSAIC_DEFAULT_VIEW_SIZE,
        "mosaic_default_height": Bin.MOSAIC_DEFAULT_VIEW_SIZE.split("x")[1],
    })


def dataset_page(request, dataset_name):
    bin_id = request.GET.get("bin_id")

    return details(request, bin_id=bin_id, group_name=dataset_name, group_type="dataset", route="dataset")


def bin_page(request, dataset_name, bin_id):
    # TODO: This needs to be cleaned up to allow bins w/o a dataset (and/or other grouping)
    return details(request, group_name=dataset_name, group_type="dataset", route="bin")
    #return details(request, bin_id=bin_id)


def bin_mode(request):
    bin_id = request.GET.get("id")
    dataset_name = request.GET.get("dataset")

    # TODO: The below are not implemented yet
    tag_names = request.GET.get("tags")
    instrument_name = request.GET.get("instrument")

    return details(
        request,
        group_name=dataset_name,
        group_type="dataset" if dataset_name else None,
        route="dataset" if dataset_name else "bin",
        bin_id=bin_id
    )

def details(request, bin_id=None, group_name=None, group_type=None, route=None):
    if not bin_id and not group_name:
        # TODO: 404 error; don't have enough info to proceed
        pass

    # TODO: Currently only handles grouping by dataset
    if group_name and group_type == "dataset":
        dataset = get_object_or_404(Dataset, name=group_name)
    else:
        dataset = None

    if bin_id:
        bin = get_object_or_404(Bin, pid=bin_id)
    else:
        bin = Timeline(dataset.bins).most_recent_bin()

    if not bin:
        # TODO: Do something
        pass

    return render(request, "dashboard/bin.html", {
        "route": route,
        "can_share_page": True,
        "dataset": dataset,
        "mosaic_scale_factors": Bin.MOSAIC_SCALE_FACTORS,
        "mosaic_view_sizes": Bin.MOSAIC_VIEW_SIZES,
        "mosaic_default_scale_factor": Bin.MOSAIC_DEFAULT_SCALE_FACTOR,
        "mosaic_default_view_size": Bin.MOSAIC_DEFAULT_VIEW_SIZE,
        "mosaic_default_height": Bin.MOSAIC_DEFAULT_VIEW_SIZE.split("x")[1],
        "bin": bin,
        "details": _bin_details(bin, dataset, preload_adjacent_bins=False, include_coordinates=False),
    })


# TODO: bin.instrument is not filled in?
def bin_details(request, dataset_name, bin_id):
    dataset = get_object_or_404(Dataset, name=dataset_name)
    bin = get_object_or_404(Bin, pid=bin_id)

    # TODO: bin.depth is coming out to 0. Check to see if the depth will be 0 when there is no lat/lng found, and handle
    # TODO: Mockup for lat/lng under the map had something like "41 north, 82 east (41.31, -70.39)"
    return render(request, 'dashboard/bin-details.html', {
        "can_share_page": True,
        "dataset": dataset,
        "mosaic_scale_factors": Bin.MOSAIC_SCALE_FACTORS,
        "mosaic_view_sizes": Bin.MOSAIC_VIEW_SIZES,
        "mosaic_default_scale_factor": Bin.MOSAIC_DEFAULT_SCALE_FACTOR,
        "mosaic_default_view_size": Bin.MOSAIC_DEFAULT_VIEW_SIZE,
        "mosaic_default_height": Bin.MOSAIC_DEFAULT_VIEW_SIZE.split("x")[1],
        "bin": bin,
        "details": _bin_details(bin, dataset, preload_adjacent_bins=False, include_coordinates=False),
    })


# TODO: Hook up add to annotations area
# TODO: Hook up add to tags area
def image_details(request, bin_id, image_id,  dataset_name=None):
    if dataset_name:
        dataset = get_object_or_404(Dataset, name=dataset_name)
    else:
        dataset = None

    bin = get_object_or_404(Bin, pid=bin_id)

    image_number = int(image_id)

    # TODO: Add validation checks/error handling
    image = bin.image(image_number)
    image_width = image.shape[1];

    metadata = json.loads(json.dumps(bin.target_metadata(image_number), default=dict_to_json))

    return render(request, 'dashboard/image-details.html', {
        "can_share_page": True,
        "dataset": dataset,
        "bin": bin,
        "image": embed_image(image),
        "image_width": image_width,
        "image_id": image_number,
        "metadata": metadata,
        "details": _bin_details(bin, dataset, include_coordinates=False),
    })


def image_metadata(request, bin_id, target):
    bin = get_object_or_404(Bin, pid=bin_id)
    metadata = bin.target_metadata(target)

    def fmt(k,v):
        if k == 'start_byte':
            return str(v)
        else:
            return '{:.5g}'.format(v)

    for k in metadata:
        metadata[k] = fmt(k, metadata[k])

    return JsonResponse(metadata)


def image_blob(request, bin_id, target):
    bin = get_object_or_404(Bin, pid=bin_id)
    blob = embed_image(bin.blob(int(target))) if bin.has_blobs() else None

    return JsonResponse({
        "blob": blob
    })


def image_outline(request, bin_id, target):
    bin = get_object_or_404(Bin, pid=bin_id)
    outline = embed_image(bin.outline(int(target))) if bin.has_blobs() else None

    return JsonResponse({
        "outline": outline
    })


# TODO: Needs to change from width/height parameters to single widthXheight
def mosaic_coordinates(request, bin_id):
    width = int(request.GET.get("width", 800))
    height = int(request.GET.get("height", 600))
    scale_percent = int(request.GET.get("scale_percent", Bin.MOSAIC_DEFAULT_SCALE_FACTOR))

    b = get_object_or_404(Bin, pid=bin_id)
    shape = (height, width)
    scale = scale_percent / 100
    coords = b.mosaic_coordinates(shape, scale)
    return JsonResponse(coords.to_dict('list'))

@cache_control(max_age=31557600) # client cache for 1y
def mosaic_page_image(request, bin_id):
    arr = _mosaic_page_image(request, bin_id)
    image_data = format_image(arr, 'image/png')

    return HttpResponse(image_data, content_type='image/png')


@cache_control(max_age=31557600) # client cache for 1y
def mosaic_page_encoded_image(request, bin_id):
    arr = _mosaic_page_image(request, bin_id)

    return HttpResponse(embed_image(arr), content_type='plain/text')


def _image_data(bin_id, target, mimetype):
    b = get_object_or_404(Bin, pid=bin_id)
    arr = b.image(target)
    image_data = format_image(arr, mimetype)
    return HttpResponse(image_data, content_type=mimetype)

def image_data_png(request, bin_id, target, dataset_name=None):
    # ignore dataset name
    return _image_data(bin_id, target, 'image/png')

def image_data_jpg(request, bin_id, target, dataset_name=None):
    # ignore dataset name
    return _image_data(bin_id, target, 'image/jpeg')

def adc_data(request, bin_id, dataset_name=None):
    # ignore dataset name
    b = get_object_or_404(Bin, pid=bin_id)
    adc_path = b.adc_path()
    filename = '{}.adc'.format(bin_id)
    fin = open(adc_path)
    return FileResponse(fin, as_attachment=True, filename=filename, content_type='text/csv')

def hdr_data(request, bin_id, dataset_name=None):
    # ignore dataset name
    b = get_object_or_404(Bin, pid=bin_id)
    hdr_path = b.hdr_path()
    filename = '{}.hdr'.format(bin_id)
    fin = open(hdr_path)
    return FileResponse(fin, as_attachment=True, filename=filename, content_type='text/plain')

def roi_data(request, bin_id, dataset_name=None):
    # ignore dataset name
    b = get_object_or_404(Bin, pid=bin_id)
    roi_path = b.roi_path()
    filename = '{}.roi'.format(bin_id)
    fin = open(roi_path)
    return FileResponse(fin, as_attachment=True, filename=filename, content_type='application/octet-stream')

def blob_zip(request, bin_id, dataset_name=None):
    b = get_object_or_404(Bin, pid=bin_id)
    try:
        version = int(request.GET.get('v',2))
    except ValueError:
        raise Http404
    try:
        blob_path = b.blob_path(version=version)
    except KeyError:
        raise Http404
    filename = '{}_blobs_v{}.zip'.format(bin_id, version)
    fin = open(blob_path)
    return FileResponse(fin, as_attachment=True, filename=filename, content_type='application/zip')

def features_csv(request, bin_id, dataset_name=None):
    b = get_object_or_404(Bin, pid=bin_id)
    try:
        version = int(request.GET.get('v',2))
    except ValueError:
        raise Http404
    try:
        features_path = b.features_path(version=version)
    except KeyError:
        raise Http404
    filename = '{}_features_v{}.csv'.format(bin_id, version)
    fin = open(features_path)
    return FileResponse(fin, as_attachment=True, filename=filename, content_type='text/csv')

def zip(request, bin_id, dataset_name=None):
    # ignore dataset name
    b = get_object_or_404(Bin, pid=bin_id)
    zip_buf = b.zip()
    filename = '{}.zip'.format(bin_id)
    return FileResponse(zip_buf, as_attachment=True, filename=filename, content_type='application/zip')


def _bin_details(bin, dataset=None, view_size=None, scale_factor=None, preload_adjacent_bins=False, include_coordinates=True):
    if not view_size:
        view_size = Bin.MOSAIC_DEFAULT_VIEW_SIZE
    if not scale_factor:
        scale_factor = Bin.MOSAIC_DEFAULT_SCALE_FACTOR

    mosaic_shape = parse_view_size(view_size)
    mosaic_scale = parse_scale_factor(scale_factor)

    if include_coordinates:
        coordinates = bin.mosaic_coordinates(
                shape=mosaic_shape,
                scale=mosaic_scale
            )
        if len(coordinates) == 0:
            pages = 0
        else:
            pages = coordinates.page.max()
        coordinates_json = coordinates_to_json(coordinates);
    else:
        coordinates_json = []
        pages = 1

    previous_bin = None
    next_bin = None

    if dataset and preload_adjacent_bins:
        previous_bin = Timeline(dataset.bins).previous_bin(bin)
        next_bin = Timeline(dataset.bins).next_bin(bin)

        if previous_bin is not None:
            previous_bin.mosaic_coordinates(shape=mosaic_shape, scale=mosaic_scale, block=False)
        if next_bin is not None:
            next_bin.mosaic_coordinates(shape=mosaic_shape, scale=mosaic_scale, block=False)

    try:
        datasets = [d.name for d in bin.datasets.all()]
    except:
        datasets = []

    return {
        "scale": mosaic_scale,
        "shape": mosaic_shape,
        "previous_bin_id": previous_bin.pid if previous_bin is not None else "",
        "next_bin_id": next_bin.pid if next_bin is not None else "",
        "lat": bin.latitude,
        "lng": bin.longitude,
        "depth": bin.depth,
        "pages": list(range(pages + 1)),
        "num_pages": int(pages),
        "tags": bin.tag_names,
        "coordinates": coordinates_json,
        "has_blobs": bin.has_blobs(),
        "has_features": bin.has_features(),
        "timestamp_iso": bin.timestamp.isoformat(),
        "instrument": "IFCB" + str(bin.instrument.number),
        "num_triggers": bin.n_triggers,
        "num_images": bin.n_images,
        "trigger_freq": round(bin.trigger_frequency, 3),
        "ml_analyzed": str(round(bin.ml_analyzed, 3)) + " ml",
        "datasets": datasets,
    }


def _mosaic_page_image(request, bin_id):
    view_size = request.GET.get("view_size", Bin.MOSAIC_DEFAULT_VIEW_SIZE)
    scale_factor = int(request.GET.get("scale_factor", Bin.MOSAIC_DEFAULT_SCALE_FACTOR))
    page = int(request.GET.get("page", 0))

    bin = get_object_or_404(Bin, pid=bin_id)
    shape = parse_view_size(view_size)
    scale = parse_scale_factor(scale_factor)
    arr, _ = bin.mosaic(page=page, shape=shape, scale=scale)

    return arr


# TODO: The below views are API/AJAX calls; in the future, it would be beneficial to use a proper API framework
# TODO: The logic to flow through to a finer resolution if the higher ones only return one data item works, but
#   it causes the UI to need to download data on each zoom level when scroll up, only to then ignore the data. Updates
#   are needed to let the UI know that certain levels are "off limits" and avoid re-running data when we know it's
#   just going to force us down to a finer resolution anyway
def generate_time_series(request, dataset_name, metric,):
    resolution = request.GET.get("resolution", "auto")
    start = request.GET.get("start")
    end = request.GET.get("end")
    if start is not None:
        start = pd.to_datetime(start, utc=True)
    if end is not None:
        end = pd.to_datetime(end, utc=True)

    # Allows us to keep consistant url names
    metric = metric.replace("-", "_")

    dataset = get_object_or_404(Dataset, name=dataset_name)

    # TODO: Possible performance issues in the way we're pivoting the data before it gets returned
    while True:
        time_series, resolution = Timeline(dataset.bins).metrics(metric, start, end, resolution=resolution)
        if len(time_series) > 1 or resolution == "bin":
            break

        resolution = get_finer_resolution(resolution)

    # TODO: Temporary workaround constraints to rule out bad data for humidity and temperature
    if metric == "temperature":
        # Restrict temperature to freezing/boiling point of sea water (0C to 100C)
        time_series = time_series.filter(metric__range=[0, 100])

    if metric == "humidity":
        # Restrict humidity to 0% to 100%
        time_series = time_series.filter(metric__range=[0, 100])

    time_data = [item["dt"] for item in time_series]
    metric_data = [item["metric"] for item in time_series]
    if resolution == "bin" and len(time_data) == 1:
        time_start = time_data[0] + timedelta(hours=-12)
        time_end = time_data[0] + timedelta(hours=12)
    else:
        time_start = min(time_data)
        time_end = max(time_data)

    return JsonResponse({
        "x": time_data,
        "x-range": {
            "start": time_start,
            "end": time_end,
        },
        "y": metric_data,
        "y-axis": Timeline(dataset.bins).metric_label(metric),
        "resolution": resolution,
    })


# TODO: This call needs a lot of clean up, standardization with other methods and cutting out some dup code
# TODO: This is also where page caching could occur...
def bin_data(request, bin_id, dataset_name=None):
    if dataset_name:
        dataset = get_object_or_404(Dataset, name=dataset_name)
    else:
        dataset = None

    bin = get_object_or_404(Bin, pid=bin_id)
    view_size = request.GET.get("view_size", Bin.MOSAIC_DEFAULT_VIEW_SIZE)
    scale_factor = request.GET.get("scale_factor", Bin.MOSAIC_DEFAULT_SCALE_FACTOR)
    preload_adjacent_bins = request.GET.get("preload_adjacent_bins", "false").lower() == "true"
    include_coordinates = request.GET.get("include_coordinates", "true").lower() == "true"

    details = _bin_details(bin, dataset, view_size, scale_factor, preload_adjacent_bins, include_coordinates)

    return JsonResponse(details)


# TODO: Using a proper API, the CSRF exempt decorator probably won't be needed
@csrf_exempt
def closest_bin(request, dataset_name):
    dataset = get_object_or_404(Dataset, name=dataset_name)
    target_date = request.POST.get("target_date", None)

    try:
        dte = pd.to_datetime(target_date, utc='True')
    except:
        dte = None

    bin = Timeline(dataset.bins).bin_closest_in_time(dte)

    return JsonResponse({
        "bin_id": bin.pid,
    })

@csrf_exempt
def nearest_bin(request):
    dataset = request.POST.get('dataset') # limit to dataset
    instrument = request.POST.get('instrument') # limit to instrument
    start = request.POST.get('start') # limit to start time
    end = request.POST.get('end') # limit to end time
    tags = request.POST.get('tags') # limit to tag(s)
    lat = request.POST.get('latitude')
    lon = request.POST.get('longitude')
    if lat is None or lon is None:
        return HttpResponseBadRequest('lat/lon required')
    if tags is None:
        tags = []
    else:
        tags = ','.split(tags)
    bins = bin_query(dataset_name=dataset, start=start, end=end, tags=tags, instrument_number=instrument)
    lon = float(lon)
    lat = float(lat)
    bin_id = Timeline(bins).nearest_bin(lon, lat).pid
    return JsonResponse({
        'bin_id': bin_id
    })

@csrf_exempt
def plot_data(request, bin_id):
    b = get_object_or_404(Bin, pid=bin_id)
    bin = b._get_bin()
    ia = bin.images_adc.copy(deep=False)
    ia.columns = schema_names(bin.schema)
    ia['target_number'] = bin.images.keys()
    ia = ia.drop_duplicates(subset=['roi_x','roi_y']) # reduce redundant data
    if b.has_features():
        features = b.features().fillna(0)
        to_drop = set(bin.images.keys()) - set(features.index)
        ia.drop(to_drop, inplace=True)
        for fc in features.columns:
            ia[fc] = features[fc].values
    return JsonResponse(ia.to_dict('list'))


def bin_metadata(request, bin_id):
    bin = get_object_or_404(Bin, pid=bin_id)

    return JsonResponse({
        "metadata": bin.metadata
    })


## FIXME move these two views to secure

# FIXME make an object locking decorator
def dataset_sync_lock_key(dataset_id):
    return 'dataset_sync_{}'.format(dataset_id)

def dataset_sync_task_id_key(dataset_id):
    return 'dataset_sync_task_{}'.format(dataset_id)

def get_dataset_sync_task_id(dataset_id):
    return cache.get(dataset_sync_task_id_key(dataset_id))
    # if there's no task ID the task is just about to start

def test_sync_dataset(request, dataset_id):
    from .tasks import sync_dataset
    # ensure that the dataset exists
    ds = get_object_or_404(Dataset, id=dataset_id)
    # attempt to lock the dataset
    lock_key = dataset_sync_lock_key(dataset_id)
    added = cache.add(lock_key, True) # this is atomic
    if not added: # dataset is locked for syncing
        return JsonResponse({ 'state': 'LOCKED' })
    # start the task asynchronously
    r = sync_dataset.delay(dataset_id, lock_key)
    # cache the task id so we can look it up by dataset id
    cache.set(dataset_sync_task_id_key(dataset_id), r.task_id)
    result = AsyncResult(r.task_id)
    return JsonResponse({ 'state': result.state })

def test_sync_dataset_status(request, dataset_id):
    task_id = get_dataset_sync_task_id(dataset_id)
    if task_id is None:
        # there's no result, which means either
        # - the cache entry for the task id has expired, or
        # - it's the exact moment the task is starting
        # report PENDING
        return JsonResponse({ 'state': 'PENDING' })
    result = AsyncResult(task_id)
    return JsonResponse({
        'state': result.state,
        'info': result.info,
        })