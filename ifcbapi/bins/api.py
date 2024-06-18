from typing import List

from django.http import HttpRequest, HttpResponseBadRequest, JsonResponse
from ninja import Router
from ninja.errors import HttpError
from core.models import Bin, Dataset, Instrument
from .schemas import BinCriteriaSchema, BinSchema


router = Router()


# TODO: Should there be a root level method? "List" like datasets seems too open-ended and will return a lot
#     :   of data w/o any search criteria provided


@router.get('/search', response=List[BinSchema])
def search(request: HttpRequest, criteria: BinCriteriaSchema = None):
    # TODO: Prevent blanket searches for everything
    #     : 1. Should we block this?
    #     : 2. If so, should there be a better error message than just an empty result?
    if criteria is None:
        return []

    # TODO: Define what a "bad" result is - right now its a 400 error, which is not descriptive enough. Especially for
    #     :   validation errors
    # TODO: The criteria is a quick port of the search_bin_locations method from the ifcbdb project. A full conversion,
    #     :   including the additional logic that is run there, still needs to be done
    bins = Bin.objects.all()

    # Handle start/end dates
    # if start_date and end_date:
    #     bins = bins.filter(sample_time__range=[start_date, end_date])
    # elif start_date:
    #     bins = bins.filter(sample_time__gte=start_date)
    # elif end_date:
    #     bins = bins.filter(sample_time__lt=end_date)
    #
    # # Handle min/max depth
    # if min_depth and max_depth:
    #     bins = bins.filter(depth__range=[min_depth, max_depth])
    # elif min_depth:
    #     bins = bins.filter(depth__gte=min_depth)
    # elif max_depth:
    #     bins = bins.filter(depth__lte=max_depth)
    #
    # # Handle region; requires an array of sw_lon, sw_lat, ne_lon, ne_lat
    # if region:
    #     bbox = Polygon.from_bbox(region)
    #     bins = bins.filter(location__contained=bbox)

    if criteria.dataset:
        dataset = Dataset.objects.filter(name=criteria.dataset).first()
        if not dataset:
            raise HttpError(400, f"'Dataset '{criteria.dataset}' not found'")

        bins = bins.filter(datasets__id=dataset.id)

    if criteria.instrument:
        instrument = Instrument.objects.filter(number=criteria.instrument).first()
        if not instrument:
            raise HttpError(400, f"'Instrument '{criteria.instrument}' not found'")

        bins = bins.filter(instrument__id=instrument.id)

    return bins
