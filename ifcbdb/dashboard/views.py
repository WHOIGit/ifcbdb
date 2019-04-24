from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, FileResponse, Http404

from .models import Dataset, Bin
from common.utilities import embed_image

from ifcb.data.imageio import format_image

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

    bins = dataset.bins

    # TODO: Need to set proper scale/size
    image, coordinates = bin.mosaic(page=0, shape=(600,800), scale=0.33, bg_color=200)

    return render(request, 'dashboard/dataset-details.html', {
        "dataset": dataset,
        "bin": bin,
        "image": embed_image(image),
        "coordinates": coordinates,
        "bins": bins,
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


# TODO: Need loading icon/etc for this
# TODO: Add prefetching of mosaics that can be cached
def mosaic(request, dataset_name, bin_id):
    dataset = get_object_or_404(Dataset, name=dataset_name)
    bin = get_object_or_404(Bin, pid=bin_id)

    # TODO: Needs type checking
    page = int(request.GET.get("page", 0))

    image, coordinates = bin.mosaic(page=page, shape=(600, 800), scale=0.33, bg_color=200)

    return render(request, 'dashboard/_mosaic.html', {
        "image": embed_image(image),
    })

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

# TODO: This could use a better name and potentially a pre-defined object
def _create_bin_wrapper(bin):
    # TODO: Need to check to make sure lat/ln are in the right order
    lat, lng = 0, 0
    try:
        lat = bin.location.x
        lng = bin.location.y
    except:
        pass

    # TODO: This loads the first image, but we're still forcing a second load through AJAX. Need to consolidate
    image, coordinates = bin.mosaic(page=0, shape=(600, 800), scale=0.33, bg_color=200)
    num_pages = coordinates.page.max()

    return {
        "bin": bin,
        "lat": lat,
        "lng": lng,
        "pages": range(num_pages + 1),
        "num_pages": num_pages,
    }