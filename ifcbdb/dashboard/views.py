from django.shortcuts import render, get_object_or_404

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
def dataset_details(request, dataset_name):
    dataset = get_object_or_404(Dataset, name=dataset_name)
    bin = dataset.most_recent_bin()

    # TODO: Need to set proper scale/size
    image, coordinates = bin.mosaic(page=0, shape=(600,800), scale=0.33, bg_color=200)

    return render(request, 'dashboard/dataset-details.html', {
        "dataset": dataset,
        "bin": bin,
        "image": embed_image(image),
        "coordinates": coordinates,
    })


def bin_details(request, dataset_name, bin_id):
    dataset = get_object_or_404(Dataset, name=dataset_name)
    bin = get_object_or_404(Bin, pid=bin_id)

    # TODO: This needs to be flushed out with proper paging; this is just to get something on the screen to use
    #   to link to the images page
    images = []
    image_keys = bin.list_images()[:5]
    for k in image_keys:
        #images.append(bin.image(k))
        images.append(k)

    # TODO: Clean this up with proper paging
    first_image = embed_image(bin.image(images[0]))


    return render(request, 'dashboard/bin-details.html', {
        "dataset": dataset,
        "bin": bin,
        "images": images,
        "first_image": first_image,
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




