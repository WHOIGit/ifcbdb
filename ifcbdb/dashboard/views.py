import json
import pandas as pd
from datetime import timedelta

from django.conf import settings
from django.shortcuts import render, get_object_or_404, reverse
from django.http import \
    HttpResponse, FileResponse, Http404, HttpResponseBadRequest, JsonResponse, \
    HttpResponseRedirect, HttpResponseNotFound
from django.views.decorators.cache import cache_control

from django.core.cache import cache
from celery.result import AsyncResult

from ifcb.data.imageio import format_image
from ifcb.data.adc import schema_names

from .models import Dataset, Bin, Instrument, Timeline, bin_query
from .forms import DatasetSearchForm
from common.utilities import *


def index(request):
    if settings.DEFAULT_DATASET:
        return HttpResponseRedirect(reverse("timeline_page") + "?dataset=" + settings.DEFAULT_DATASET)

    return HttpResponseRedirect(reverse("datasets"))


def datasets(request):
    datasets = None

    if request.POST:
        form = DatasetSearchForm(request.POST)
        if form.is_valid():
            min_depth = form.cleaned_data["min_depth"]
            max_depth = form.cleaned_data["max_depth"]
            start_date = form.cleaned_data["start_date"]
            end_date = form.cleaned_data["end_date"]
            if end_date:
                end_date = end_date + timedelta(days=1)

            datasets = Dataset.search(start_date, end_date, min_depth, max_depth)
    else:
        form = DatasetSearchForm()

    if not datasets:
        datasets = Dataset.objects.filter(is_active=True).order_by('title')

    return render(request, 'dashboard/datasets.html', {
        "datasets": datasets,
        "form": form,
    })


def request_get_instrument(instrument_string):
    i = instrument_string
    if i is not None and i:    
        if i.lower().startswith('ifcb'):
            i = i[4:]
        return int(i)

def request_get_tags(tags_string):
    t = tags_string
    if t is not None:
        if not t:
            return []
        return t.split(',')

def timeline_page(request):
    bin_id = request.GET.get("bin")
    dataset_name = request.GET.get("dataset")
    tags = request_get_tags(request.GET.get("tags"))
    instrument_number = request_get_instrument(request.GET.get("instrument"))
    bin_reset = False

    # If we reach this page w/o any grouping options, all we can do is render the standalone bin page
    if not dataset_name and not tags and instrument_number is None:
        return bin_page(request)

    # Verify that the selecting bin is actually within the grouping options. If its not, pick the latest one
    if bin_id:
        qs = bin_query(dataset_name=dataset_name, instrument_number=instrument_number, tags=tags)
        if not qs.filter(pid=bin_id).exists():
            bin_id = None
            bin_reset = True

    return _details(request,
                    bin_id=bin_id, route="timeline", bin_reset=bin_reset,
                    dataset_name=dataset_name, tags=tags, instrument_number=instrument_number)


def bin_page(request):
    dataset_name = request.GET.get("dataset",None)
    bin_id = request.GET.get("bin",None)

    return _details(
        request,
        route="dataset" if dataset_name is not None else "bin",
        bin_id=bin_id,
        dataset_name=dataset_name,
    )


def image_page(request):
    bin_id = request.GET.get("bin")
    image_id = request.GET.get("image")

    dataset_name = request.GET.get("dataset")
    instrument_number = request.GET.get("instrument")
    tags = request.GET.get("tags")

    return _image_details(
        request,
        image_id,
        bin_id,
        dataset_name,
        instrument_number,
        tags
    )


def _image_details(request, image_id, bin_id, dataset_name=None, instrument_number=None, tags=None):
    image_number = int(image_id)
    bin = get_object_or_404(Bin, pid=bin_id)
    if dataset_name:
        dataset = get_object_or_404(Dataset, name=dataset_name)
    else:
        dataset = None

    # TODO: Add validation checks/error handling
    image = bin.image(image_number)
    image_width = image.shape[1];

    metadata = json.loads(json.dumps(bin.target_metadata(image_number), default=dict_to_json))

    # TODO: Only timeline route is working so far
    return render(request, 'dashboard/image.html', {
        "route": "timeline",
        "can_share_page": True,
        "dataset": dataset,
        "bin": bin,
        "image": embed_image(image),
        "image_width": image_width,
        "image_id": image_number,
        "metadata": metadata,
        "details": _bin_details(bin, dataset, include_coordinates=False, instrument_number=instrument_number, tags=tags),
    })


def legacy_dataset_page(request, dataset_name, bin_id):
    return _details(request, bin_id=bin_id, route="dataset", dataset_name=dataset_name )


def legacy_bin_page(request, dataset_name, bin_id):
    return _details(request, bin_id=bin_id, route="dataset", dataset_name=dataset_name)


def legacy_image_page(request, dataset_name, bin_id, image_id):
    return _image_details(request, image_id, bin_id, dataset_name)


def legacy_image_page_alt(request, bin_id, image_id):
    return _image_details(request, image_id, bin_id)


def _details(request, bin_id=None, route=None, dataset_name=None, tags=None, instrument_number=None, bin_reset=False):
    if not bin_id and not dataset_name and not tags and not instrument_number:
        # TODO: 404 error; don't have enough info to proceed
        pass

    if bin_id:
        bin = get_object_or_404(Bin, pid=bin_id)
    else:
        bin_qs = bin_query(dataset_name=dataset_name,
            tags=tags,
            instrument_number=instrument_number)
        bin = Timeline(bin_qs).most_recent_bin()

    dataset = get_object_or_404(Dataset, name=dataset_name) if dataset_name else None
    instrument = get_object_or_404(Instrument, number=instrument_number) if instrument_number else None

    if bin is None:
        return render(request, "dashboard/no-bins.html", {})

    return render(request, "dashboard/bin.html", {
        "route": route,
        "can_share_page": True,
        "can_filter_page": True,
        "dataset": dataset,
        "instrument": instrument,
        "tags": ','.join(tags) if tags else '',
        "mosaic_scale_factors": Bin.MOSAIC_SCALE_FACTORS,
        "mosaic_view_sizes": Bin.MOSAIC_VIEW_SIZES,
        "mosaic_default_scale_factor": Bin.MOSAIC_DEFAULT_SCALE_FACTOR,
        "mosaic_default_view_size": Bin.MOSAIC_DEFAULT_VIEW_SIZE,
        "mosaic_default_height": Bin.MOSAIC_DEFAULT_VIEW_SIZE.split("x")[1],
        "mosaic_default_width": Bin.MOSAIC_DEFAULT_VIEW_SIZE.split("x")[0],
        "bin": bin,
        "bin_reset": bin_reset,
        "details": _bin_details(bin, dataset, preload_adjacent_bins=False, include_coordinates=False,
                                instrument_number=instrument_number, tags=tags),
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


def image_png(request, bin_id, target):
    return _image_data(bin_id, target, 'image/png')


def image_jpg(request, bin_id, target):
    return _image_data(bin_id, target, 'image/jpeg')


def image_png_legacy(request, bin_id, target, dataset_name):
    return _image_data(bin_id, target, 'image/png')


def image_jpg_legacy(request, bin_id, target, dataset_name):
    return _image_data(bin_id, target, 'image/jpeg')


def adc_data(request, bin_id):
    b = get_object_or_404(Bin, pid=bin_id)
    adc_path = b.adc_path()
    filename = '{}.adc'.format(bin_id)
    fin = open(adc_path)
    return FileResponse(fin, as_attachment=True, filename=filename, content_type='text/csv')


def hdr_data(request, bin_id):
    b = get_object_or_404(Bin, pid=bin_id)
    hdr_path = b.hdr_path()
    filename = '{}.hdr'.format(bin_id)
    fin = open(hdr_path)
    return FileResponse(fin, as_attachment=True, filename=filename, content_type='text/plain')


def roi_data(request, bin_id):
    b = get_object_or_404(Bin, pid=bin_id)
    roi_path = b.roi_path()
    filename = '{}.roi'.format(bin_id)
    fin = open(roi_path)
    return FileResponse(fin, as_attachment=True, filename=filename, content_type='application/octet-stream')


def blob_zip(request, bin_id):
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


def features_csv(request, bin_id):
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


def zip(request, bin_id):
    b = get_object_or_404(Bin, pid=bin_id)
    zip_buf = b.zip()
    filename = '{}.zip'.format(bin_id)
    return FileResponse(zip_buf, as_attachment=True, filename=filename, content_type='application/zip')


def _bin_details(bin, dataset=None, view_size=None, scale_factor=None, preload_adjacent_bins=False,
                 include_coordinates=True, instrument_number=None, tags=None):
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

    if (dataset or instrument_number or tags) and preload_adjacent_bins:
        if dataset is not None:
            dataset_name = dataset.name
        else:
            dataset_name = None
        bin_qs = bin_query(dataset_name=dataset_name, instrument_number=instrument_number,
            tags=tags)
        previous_bin = Timeline(bin_qs).previous_bin(bin)
        next_bin = Timeline(bin_qs).next_bin(bin)

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
        "timestamp_iso": bin.sample_time.isoformat(),
        "instrument": "IFCB" + str(bin.instrument.number),
        "num_triggers": bin.n_triggers,
        "num_images": bin.n_images,
        "trigger_freq": round(bin.trigger_frequency, 3),
        "ml_analyzed": str(round(bin.ml_analyzed, 3)) + " ml",
        "size": bin.size,
        "datasets": datasets,
        "comments": bin.comment_list,
        "concentration": round(bin.concentration, 3),
        "skip": bin.skip,
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
# TODO: Handle tag/instrument grouping
def generate_time_series(request, metric,):
    dataset_name = request.GET.get("dataset",None)
    resolution = request.GET.get("resolution", "auto")
    start = request.GET.get("start",None)
    end = request.GET.get("end",None)
    if start is not None:
        start = pd.to_datetime(start, utc=True)
    if end is not None:
        end = pd.to_datetime(end, utc=True)

    # Allows us to keep consistent url names
    metric = metric.replace("-", "_")

    instrument_number = request_get_instrument(request.GET.get("instrument"))
    tags = request_get_tags(request.GET.get("tags"))

    bin_qs = bin_query(dataset_name=dataset_name,
        tags=tags,
        instrument_number=instrument_number)

    time_series, resolution = Timeline(bin_qs).metrics(metric, start, end, resolution=resolution)

    # TODO: Temporary workaround constraints to rule out bad data for humidity and temperature
    if metric == "temperature":
        # Restrict temperature to freezing/boiling point of sea water (0C to 100C)
        time_series = time_series.filter(metric__range=[0, 100])

    if metric == "humidity":
        # Restrict humidity to 0% to 100%
        time_series = time_series.filter(metric__range=[0, 100])

    time_data = [item["dt"] for item in time_series]
    metric_data = [item["metric"] for item in time_series]

    if start is not None:
        time_start = start
    if end is not None:
        time_end = end

    if not time_data:
        pass
    elif len(time_data) == 1:
        time_start = time_data[0] - pd.Timedelta('12h')
        time_end = time_data[0] + pd.Timedelta('12h')
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
        "y-axis": Timeline.metric_label(metric),
        "resolution": resolution,
    })


# TODO: This is also where page caching could occur...
def bin_data(request, bin_id):
    dataset_name = request.GET.get("dataset")

    instrument_number = request_get_instrument(request.GET.get("instrument"))
    tags = request_get_tags(request.GET.get("tags"))

    if dataset_name:
        dataset = get_object_or_404(Dataset, name=dataset_name)
    else:
        dataset = None

    bin = get_object_or_404(Bin, pid=bin_id)
    view_size = request.GET.get("view_size", Bin.MOSAIC_DEFAULT_VIEW_SIZE)
    scale_factor = request.GET.get("scale_factor", Bin.MOSAIC_DEFAULT_SCALE_FACTOR)
    preload_adjacent_bins = request.GET.get("preload_adjacent_bins", "false").lower() == "true"
    include_coordinates = request.GET.get("include_coordinates", "true").lower() == "true"

    details = _bin_details(bin, dataset, view_size, scale_factor, preload_adjacent_bins, include_coordinates,
                           instrument_number=instrument_number, tags=tags)

    return JsonResponse(details)


def closest_bin(request):
    dataset_name = request.POST.get("dataset")
    instrument = request_get_instrument(request.POST.get("instrument"))  # limit to instrument
    tags = request_get_tags(request.POST.get("tags"))  # limit to tag(s)
    target_date = request.POST.get("target_date", None)

    try:
        dte = pd.to_datetime(target_date, utc=True)
    except:
        dte = None

    bin_qs = bin_query(dataset_name=dataset_name, instrument_number=instrument, tags=tags)
    bin = Timeline(bin_qs).bin_closest_in_time(dte)

    return JsonResponse({
        "bin_id": bin.pid,
    })


def nearest_bin(request):
    dataset = request.POST.get('dataset')  # limit to dataset
    instrument = request_get_instrument(request.POST.get("instrument"))  # limit to instrument
    start = request.POST.get('start')  # limit to start time
    end = request.POST.get('end')  # limit to end time
    tags = request_get_tags(request.POST.get("tags"))  # limit to tag(s)
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


def plot_data(request, bin_id):
    b = get_object_or_404(Bin, pid=bin_id)
    bin = b._get_bin()
    ia = bin.images_adc.copy(deep=False)
    # use named columns
    column_names = schema_names(bin.schema)
    # now deal with ADC files with extra columns, by removing them
    if len(ia.columns) > len(column_names):
        for i in range(len(ia.columns) - len(column_names)):
            column_names.append('unknown_{}'.format(i))
    ia.columns = column_names
    ia['target_number'] = bin.images.keys()
    if b.has_features():
        features = b.features().fillna(0)
        to_drop = set(bin.images.keys()) - set(features.index)
        ia.drop(to_drop, inplace=True)
        for fc in features.columns:
            ia[fc] = features[fc].values
    ia = ia.drop_duplicates(subset=['roi_x','roi_y']) # reduce redundant data
    return JsonResponse(ia.to_dict('list'))


def bin_metadata(request, bin_id):
    bin = get_object_or_404(Bin, pid=bin_id)

    return JsonResponse({
        "metadata": bin.metadata
    })


def bin_exists(request):
    dataset_name = request.GET.get("dataset")
    tags = request_get_tags(request.GET.get("tags"))
    instrument_number = request_get_instrument(request.GET.get("instrument"))
    exists = bin_query(dataset_name=dataset_name, instrument_number=instrument_number, tags=tags).exists()

    return JsonResponse({
        "exists": exists
    })
