import json
import pandas as pd

from django.conf import settings
from django.shortcuts import render, get_object_or_404, reverse
from django.http import HttpResponse, FileResponse, Http404, JsonResponse, HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import cache_control

from ifcb.data.imageio import format_image

from .models import Dataset, Bin, Timeline
from common.utilities import *

from .tasks import mosaic_coordinates_task

# TODO: The naming convensions for the dataset, bin and image ID's needs to be cleaned up and be made
#   more consistent

def index(request):
    if settings.DEFAULT_DATASET:
        return HttpResponseRedirect(reverse("dataset", kwargs={"dataset_name": settings.DEFAULT_DATASET}))

    return HttpResponseRedirect(reverse("datasets"))


def datasets(request):
    datasets = Dataset.objects.all()

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
        "dataset": dataset,
        "bin": bin,
        "mosaic_scale_factors": Bin.MOSAIC_SCALE_FACTORS,
        "mosaic_view_sizes": Bin.MOSAIC_VIEW_SIZES,
        "mosaic_default_scale_factor": Bin.MOSAIC_DEFAULT_SCALE_FACTOR,
        "mosaic_default_view_size": Bin.MOSAIC_DEFAULT_VIEW_SIZE,
    })


# TODO: bin.instrument is not filled in?
def bin_details(request, dataset_name, bin_id):
    dataset = get_object_or_404(Dataset, name=dataset_name)
    bin = get_object_or_404(Bin, pid=bin_id)

    # TODO: bin.depth is coming out to 0. Check to see if the depth will be 0 when there is no lat/lng found, and handle
    # TODO: Mockup for lat/lng under the map had something like "41 north, 82 east (41.31, -70.39)"
    return render(request, 'dashboard/bin-details.html', {
        "dataset": dataset,
        "mosaic_scale_factors": Bin.MOSAIC_SCALE_FACTORS,
        "mosaic_view_sizes": Bin.MOSAIC_VIEW_SIZES,
        "mosaic_default_scale_factor": Bin.MOSAIC_DEFAULT_SCALE_FACTOR,
        "mosaic_default_view_size": Bin.MOSAIC_DEFAULT_VIEW_SIZE,
        "bin": bin,
        "details": _bin_details(dataset, bin),
    })


# TODO: Hook up add to annotations area
# TODO: Hook up add to tags area
def image_details(request, dataset_name, bin_id, image_id):
    dataset = get_object_or_404(Dataset, name=dataset_name)
    bin = get_object_or_404(Bin, pid=bin_id)

    # TODO: Add validation checks/error handling
    image = bin.image(int(image_id))
    metadata = json.loads(json.dumps(bin.target_metadata(image_id), default=dict_to_json))

    return render(request, 'dashboard/image-details.html', {
        "dataset": dataset,
        "bin": bin,
        "image": embed_image(image),
        "image_id": image_id,
        "metadata": metadata,
    })


# TODO: The dumps/load call is to get around there being int64 data within the dictionary that cannot be serialized. We
#   will probably want to find an alternative for this
def image_metadata(request, bin_id, target):
    bin = get_object_or_404(Bin, pid=bin_id)
    metadata = json.dumps(bin.target_metadata(target), default=dict_to_json)

    return JsonResponse(json.loads(metadata))


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

def image_data_png(request, dataset_name, bin_id, target):
    # ignore dataset name
    return _image_data(bin_id, target, 'image/png')

def image_data_jpg(request, dataset_name, bin_id, target):
    # ignore dataset name
    return _image_data(bin_id, target, 'image/jpeg')

def adc_data(request, dataset_name, bin_id):
    # ignore dataset name
    b = get_object_or_404(Bin, pid=bin_id)
    adc_path = b.adc_path()
    filename = '{}.adc'.format(bin_id)
    fin = open(adc_path)
    return FileResponse(fin, as_attachment=True, filename=filename, content_type='text/csv')

def hdr_data(request, dataset_name, bin_id):
    # ignore dataset name
    b = get_object_or_404(Bin, pid=bin_id)
    hdr_path = b.hdr_path()
    filename = '{}.hdr'.format(bin_id)
    fin = open(hdr_path)
    return FileResponse(fin, as_attachment=True, filename=filename, content_type='text/plain')

def roi_data(request, dataset_name, bin_id):
    # ignore dataset name
    b = get_object_or_404(Bin, pid=bin_id)
    roi_path = b.roi_path()
    filename = '{}.roi'.format(bin_id)
    fin = open(roi_path)
    return FileResponse(fin, as_attachment=True, filename=filename, content_type='application/octet-stream')

def blob_zip(request, dataset_name, bin_id):
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

def zip(request, dataset_name, bin_id):
    # ignore dataset name
    b = get_object_or_404(Bin, pid=bin_id)
    zip_buf = b.zip()
    filename = '{}.zip'.format(bin_id)
    return FileResponse(zip_buf, as_attachment=True, filename=filename, content_type='application/zip')


def _bin_details(dataset, bin, view_size=None, scale_factor=None):
    if not view_size:
        view_size = Bin.MOSAIC_DEFAULT_VIEW_SIZE
    if not scale_factor:
        scale_factor = Bin.MOSAIC_DEFAULT_SCALE_FACTOR

    mosaic_shape = parse_view_size(view_size)
    mosaic_scale = parse_scale_factor(scale_factor)

    coordinates = bin.mosaic_coordinates(
        shape=mosaic_shape,
        scale=mosaic_scale
    )
    pages = coordinates.page.max()

    previous_bin = Timeline(dataset.bins).previous_bin(bin)
    next_bin = Timeline(dataset.bins).next_bin(bin)

    if previous_bin:
        mosaic_coordinates_task.delay(previous_bin.pid, mosaic_shape, mosaic_scale)
    if next_bin:
        mosaic_coordinates_task.delay(next_bin.pid, mosaic_shape, mosaic_scale)

    # TODO: Volume Analyzed is using floatformat:3; is that ok?
    return {
        "previous_bin_id": previous_bin.pid if previous_bin else "",
        "next_bin_id": next_bin.pid if next_bin else "",
        "lat": bin.latitude,
        "lng": bin.longitude,
        "pages": list(range(pages + 1)),
        "num_pages": int(pages),
        "tags": bin.tag_names,
        "coordinates": coordinates_to_json(coordinates),
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
def generate_time_series(request, dataset_name, metric):
    # Allows us to keep consistant url names
    metric = metric.replace("-", "_")

    # TODO: Allow resolution to be set from API call; default to hours for testing
    dataset = get_object_or_404(Dataset, name=dataset_name)
    time_series = Timeline(dataset.bins).metrics(metric, None, None, resolution="bin")

    # TODO: Possible performance issues in the way we're pivoting the data before it gets returned
    return JsonResponse({
        "x": [item["dt"] for item in time_series],
        "y": [item["metric"] for item in time_series],
        "y-axis": Timeline(dataset.bins).metric_label(metric),
    })


# TODO: This call needs a lot of clean up, standardization with other methods and cutting out some dup code
# TODO: This is also where page caching could occur...
def bin_data(request, dataset_name, bin_id):
    dataset = get_object_or_404(Dataset, name=dataset_name)
    bin = get_object_or_404(Bin, pid=bin_id)
    view_size = request.GET.get("view_size", Bin.MOSAIC_DEFAULT_VIEW_SIZE)
    scale_factor = request.GET.get("scale_factor", Bin.MOSAIC_DEFAULT_SCALE_FACTOR)
    details = _bin_details(dataset, bin, view_size, scale_factor)

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

    bin = Timeline(dataset.bins).most_recent_bin(dte)

    return JsonResponse({
        "bin_id": bin.pid,
    })
