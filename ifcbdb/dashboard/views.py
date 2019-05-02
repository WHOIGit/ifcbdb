import pandas as pd

from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, FileResponse, Http404, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import cache_control

from ifcb.data.imageio import format_image

from .models import Dataset, Bin
from common.utilities import embed_image

# TODO: The naming convensions for the dataset, bin and image ID's needs to be cleaned up and be made
#   more consistent


def datasets(request):
    datasets = Dataset.objects.all()

    return render(request, 'dashboard/datasets.html', {
        "datasets": datasets,
    })


# TODO: Configure link needs proper permissions (more than just user is authenticated)
# TODO: Handle a dataset with no bins? Is that possible?
def dataset_details(request, dataset_name, bin_id=None):
    dataset = get_object_or_404(Dataset, name=dataset_name)

    if bin_id is None:
        bin = dataset.most_recent_bin()
    else:
        bin = get_object_or_404(Bin, pid=bin_id)

    return render(request, 'dashboard/dataset-details.html', {
        "dataset": dataset,
        "bin": bin,
    })


def bin_details(request, dataset_name, bin_id):
    dataset = get_object_or_404(Dataset, name=dataset_name)
    bin = get_object_or_404(Bin, pid=bin_id)

    # TODO: This needs to be flushed out with proper paging; this is just to get something on the screen to use
    #   to link to the images page
    images = []
    image_keys = bin.list_images()[:5]
    for k in image_keys:
        images.append(k)

    # TODO: bin.depth is coming out to 0. Check to see if the depth will be 0 when there is no lat/lng found, and handle
    # TODO: Mockup for lat/lng under the map had something like "41 north, 82 east (41.31, -70.39)"
    return render(request, 'dashboard/bin-details.html', {
        "dataset": dataset,
        "bin_data": _create_bin_wrapper(bin),
        "images": images,
    })


# TODO: Hook up add to annotations area
# TODO: Hook up add to tags area
def image_details(request, dataset_name, bin_id, image_id):
    dataset = get_object_or_404(Dataset, name=dataset_name)
    bin = get_object_or_404(Bin, pid=bin_id)

    # TODO: Add validation checks/error handling
    image = bin.image(int(image_id))

    return render(request, 'dashboard/image-details.html', {
        "dataset": dataset,
        "bin": bin,
        "image": embed_image(image),
        "image_id": image_id,
    })


def mosaic_coordinates(request, bin_id):
    width = int(request.GET.get("width", 800))
    height = int(request.GET.get("height", 600))
    scale_percent = int(request.GET.get("scale_percent", 33))

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

def zip(request, dataset_name, bin_id):
    # ignore dataset name
    b = get_object_or_404(Bin, pid=bin_id)
    zip_buf = b.zip()
    filename = '{}.zip'.format(bin_id)
    return FileResponse(zip_buf, as_attachment=True, filename=filename, content_type='application/zip')

# TODO: This could use a better name and potentially a pre-defined object
# TODO: Remove; replace existing code with _bin_details
def _create_bin_wrapper(bin):
    lat, lng = bin.latitude, bin.longitude

    num_pages = bin.mosaic_coordinates(shape=(600, 800), scale=0.33).page.max()

    return {
        "bin": bin,
        "lat": lat,
        "lng": lng,
        "pages": range(num_pages + 1),
        "num_pages": num_pages,
    }


def _bin_details(dataset, bin):
    pages = bin.mosaic_coordinates(shape=(600, 800), scale=0.33).page.max()
    previous_bin = dataset.previous_bin(bin)
    next_bin = dataset.next_bin(bin)

    return {
        "previous_bin_id": previous_bin.pid if previous_bin else "",
        "next_bin_id": next_bin.pid if next_bin else "",
        "lat": bin.latitude,
        "lng": bin.longitude,
        "pages": list(range(pages + 1)),
        "num_pages": int(pages),
    }


def _mosaic_page_image(request, bin_id):
    width = int(request.GET.get("width", 800))
    height = int(request.GET.get("height", 600))
    scale_percent = int(request.GET.get("scale_percent", 33))
    page = int(request.GET.get("page", 0))

    bin = get_object_or_404(Bin, pid=bin_id)
    shape = (height, width)
    scale = scale_percent / 100
    arr, _ = bin.mosaic(page=page, shape=shape, scale=scale)

    return arr


# TODO: The below views are API/AJAX calls; in the future, it would be beneficial to use a proper API framework
def generate_time_series(request, dataset_name, metric):
    # Allows us to keep consistant url names
    metric = metric.replace("-", "_")

    # TODO: Allow resolution to be set from API call; default to hours for testing
    dataset = get_object_or_404(Dataset, name=dataset_name)
    time_series = dataset.timeline(None, None, metric=metric, resolution="bin")

    # TODO: Possible performance issues in the way we're pivoting the data before it gets returned
    return JsonResponse({
        "x": [item["dt"] for item in time_series],
        "y": [item["metric"] for item in time_series],
        "y-axis": dataset.metric_label(metric),
    })


# TODO: This call needs a lot of clean up, standardization with other methods and cutting out some dup code
# TODO: This is also where page caching could occur...
def bin_data(request, dataset_name, bin_id):
    dataset = get_object_or_404(Dataset, name=dataset_name)
    bin = get_object_or_404(Bin, pid=bin_id)
    details = _bin_details(dataset, bin)

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

    bin = dataset.most_recent_bin(dte)

    return JsonResponse({
        "bin_id": bin.pid,
    })
