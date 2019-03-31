"""access to IFCB data"""
import ifcb

from ifcb.data.stitching import InfilledImages
from ifcb.viz.mosaic import Mosaic

from .models import Bin, DATA_DIRECTORY_RAW

def get_bin(pid):
    b = Bin.objects.get(pid=pid) # handle exception
    for dataset in b.datasets.all():
        for directory in dataset.directories.filter(kind=DATA_DIRECTORY_RAW):
            dd = ifcb.DataDirectory(directory.path)
            try:
                return dd[pid]
            except KeyError:
                pass # keep searching
    raise KeyError

def get_image(bin_pid, target_number):
    b = get_bin(bin_pid)
    ii = InfilledImages(b) # handle old-style data
    with b.as_single(target_number) as subset:
        return subset.images[target_number]

def get_mosaic(bin_pid, shape=(1080,1920), page=0, bgcolor=200):
    b = get_bin(bin_pid)
    m = Mosaic(b, shape, bgcolor)
    coordinates = m.pack() # cache this somehow
    image = m.page(page)
    return image, coordinates
