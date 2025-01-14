import json
import re
from io import BytesIO

import numpy as np
import pandas as pd
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, reverse
from django.http import \
    HttpResponse, FileResponse, Http404, HttpResponseBadRequest, JsonResponse, \
    HttpResponseRedirect, HttpResponseNotFound, StreamingHttpResponse, HttpResponseForbidden
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST, require_GET

from django.core.cache import cache
from celery.result import AsyncResult

from ifcb.data.imageio import format_image
from ifcb.data.adc import schema_names

from .models import Dataset, Bin, Instrument, Timeline, bin_query, Tag, Comment, normalize_tag_name, ApiAccount
from .forms import DatasetSearchForm
from common.utilities import *

from dashboard.accession import Accession, export_metadata

def index(request):
    if settings.DEFAULT_DATASET:
        return HttpResponseRedirect(reverse("timeline_page") + "?dataset=" + settings.DEFAULT_DATASET)
    return HttpResponseRedirect(reverse("datasets"))


def datasets(request):
    if request.POST:
        form = DatasetSearchForm(request.POST)
    else:
        form = DatasetSearchForm()

    return render(request, 'dashboard/datasets.html', {
        "form": form,
    })

def bin_in_dataset_or_404(bin, dataset):
    "bin can be either a Bin instance or a bin pid"
    "dataset can be either a Dataset instance or a dataset name"
    try:
        bin = Bin.objects.get(pid=bin)
    except Bin.DoesNotExist:
        raise Http404(f'No such bin {bin}')
    if not dataset:
        return bin, None
    try:
        dataset = Dataset.objects.get(name=dataset)
    except Dataset.DoesNotExist:
        raise Http404(f'No such dataset {dataset}')
    if dataset in list(bin.datasets.all()):
        return bin, dataset
    raise Http404(f'Bin {bin.pid} is not in dataset {dataset}')

def dataframe_csv_response(df, **kw):
    csv_buf = BytesIO()
    df.to_csv(csv_buf, mode='wb', **kw)
    csv_buf.seek(0)
    response = StreamingHttpResponse(csv_buf, content_type='text/csv')
    return response

@require_POST
def search_timeline_locations(request):
    bin_id = request.POST.get("bin")
    dataset_name = request.POST.get("dataset")
    tags = request_get_tags(request.POST.get("tags"))
    instrument_number = request_get_instrument(request.POST.get("instrument"))
    cruise = request_get_cruise(request.POST.get("cruise"))
    sample_type = request_get_sample_type(request.POST.get('sample_type'))
    start_date = request.POST.get("start_date")
    end_date = request.POST.get("end_date")

    cache_key = 'tloc_b={};d={};t={};i={};c={};st={}'.format(bin_id, dataset_name, tags, instrument_number, cruise, sample_type)
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse(cached)

    if not dataset_name and not tags and instrument_number is None and cruise is None:
        qs = Bin.objects.filter(pid=bin_id)
    else:
        qs = bin_query(dataset_name=dataset_name, instrument_number=instrument_number, tags=tags, cruise=cruise, sample_type=sample_type)

    # TODO: Eventually, this should handle start/end date
    # if end_date:
    #     end_date = pd.to_datetime(end_date, utc=True) + pd.Timedelta('1d')
    #
    # if start_date:
    #     start_date = pd.to_datetime(start_date, utc=True)

    bins_data = qs.filter(location__isnull=False).values('pid', 'location')
    bin_locations = [[b['pid'], b['location'].y, b['location'].x, "b"] for b in bins_data]

    if dataset_name:
        datasets = Dataset.objects.filter(name=dataset_name).exclude(location__isnull=True)
    else:
        dataset_ids = qs.filter(location__isnull=True).values('datasets').distinct()
        datasets = Dataset.objects.filter(id__in=dataset_ids).exclude(location__isnull=True).filter(is_active=True)

    dataset_locations = [[d.name + "|" + d.title, d.latitude, d.longitude, "d"] for d in datasets]

    result = {
        "locations": bin_locations + dataset_locations
    }
    try:
        cache.set(cache_key, result)
    except Exception as e: # value is probably too large
        try:
            cache.delete(cache_key)
        except Exception as e:
            pass

    return JsonResponse(result)


@require_POST
def search_bin_locations(request):
    min_depth = request.POST.get("min_depth")
    max_depth = request.POST.get("max_depth")
    start_date = request.POST.get("start_date")
    end_date = request.POST.get("end_date")
    region_sw_lat = request.POST.get("region_sw_lat")
    region_sw_lon = request.POST.get("region_sw_lon")
    region_ne_lat = request.POST.get("region_ne_lat")
    region_ne_lon = request.POST.get("region_ne_lon")
    dataset_id = request.POST.get("dataset")

    if region_sw_lat and region_sw_lon and region_ne_lat and region_ne_lon:
        region = (region_sw_lon, region_sw_lat, region_ne_lon, region_ne_lat)
    else:
        region = None

    if end_date:
        end_date = pd.to_datetime(end_date, utc=True) + pd.Timedelta('1d')

    if start_date:
        start_date = pd.to_datetime(start_date, utc=True)

    # Note that the indicator for bin vs dataset is intentionally kept to one character to limit overhead
    bins = Bin.search(start_date, end_date, min_depth, max_depth, region=region, dataset_id=dataset_id)
    bins_data = bins.filter(location__isnull=False).values('pid','location')
    bin_locations = [[b['pid'], b['location'].y, b['location'].x, "b"] for b in bins_data]

    # First parameter is specifically both title and name for datasets because bins do not have two separate name.
    #   This allows the map to link using the name but dispaly the title, while not adding a lot of duplicate data
    #   to the array on bins where name and title are essentially the same (both are pid)
    fixed_location_datasets = Dataset.search_fixed_locations(start_date, end_date, min_depth, max_depth,
                                                             region=region, dataset_id=dataset_id)
    dataset_locations = [[d.name + "|" + d.title, d.latitude, d.longitude, "d"] for d in fixed_location_datasets]

    return JsonResponse({
        "locations": bin_locations + dataset_locations,
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
        return [normalize_tag_name(tag) for tag in t.split(',')]

def request_get_cruise(cruise_string):
    if cruise_string:
        return cruise_string

def request_get_sample_type(sample_type_string):
    if sample_type_string:
        return sample_type_string

# FIXME add start and end?
def filter_parameters_bin_query(method):
    dataset_name = method.get('dataset')
    tags = request_get_tags(method.get('tags'))
    instrument_number = request_get_instrument(method.get('instrument'))
    cruise = request_get_cruise(method.get('cruise'))
    sample_type = request_get_sample_type(method.get('sample_type'))

    bin_qs = bin_query(dataset_name=dataset_name,
        tags=tags, cruise=cruise, sample_type=sample_type,
        instrument_number=instrument_number)

    return bin_qs

def timeline_page(request):
    bin_id = request.GET.get("bin")
    dataset_name = request.GET.get("dataset")
    tags = request_get_tags(request.GET.get("tags"))
    instrument_number = request_get_instrument(request.GET.get("instrument"))
    cruise = request_get_cruise(request.GET.get("cruise"))
    sample_type = request_get_sample_type(request.GET.get('sample_type'))
    bin_reset = False
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    # If we reach this page w/o any grouping options, all we can do is render the standalone bin page
    if not dataset_name and not tags and instrument_number is None and cruise is None and not sample_type:
        return bin_page(request)

    # Verify that the selecting bin is actually within the grouping options. If its not, pick the latest one
    if bin_id:
        qs = bin_query(dataset_name=dataset_name, instrument_number=instrument_number, tags=tags, cruise=cruise, sample_type=sample_type)
        if not qs.filter(pid=bin_id).exists():
            bin_id = None
            bin_reset = True

    return _details(request,
                    bin_id=bin_id, route="timeline", bin_reset=bin_reset,
                    dataset_name=dataset_name, tags=tags, instrument_number=instrument_number,
                    cruise=cruise, sample_type=sample_type,
                    default_start_date=start_date, default_end_date=end_date)


@login_required
def list_page(request):
    dataset_name = request.GET.get("dataset")
    instrument_number = request_get_instrument(request.GET.get("instrument"))
    tags = request_get_tags(request.GET.get("tags"))
    cruise = request_get_cruise(request.GET.get('cruise'))
    sample_type = request_get_sample_type(request.GET.get('sample_type'))

    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    skip_filters = request.GET.get("skip_filters")

    dataset = get_object_or_404(Dataset, name=dataset_name) if dataset_name else None

    # If we reach this page w/o any grouping options, all we can do is render the standalone bin page
    # if not dataset_name and not tags and instrument_number is None:
    #     return bin_page(request)

    return render(request, "dashboard/list.html", {
        "dataset": dataset,
        "dataset_name": dataset_name,
        "instrument_number": instrument_number,
        "tags": ','.join(tags) if tags else '',
        'cruise': cruise,
        'sample_type': sample_type,
        "start_date": start_date,
        "end_date": end_date,
        "can_filter_page": True,
        "skip_filters": skip_filters,
    })


def bin_page(request):
    dataset_name = request.GET.get("dataset",None)
    instrument_number = request_get_instrument(request.GET.get("instrument"))
    tags = request_get_tags(request.GET.get("tags"))
    cruise = request_get_cruise(request.GET.get('cruise'))
    sample_type = request_get_sample_type(request.GET.get('sample_type'))
    bin_id = request.GET.get("bin",None)

    return _details(
        request,
        route="dataset" if dataset_name is not None else "bin",
        bin_id=bin_id,
        dataset_name=dataset_name,
        instrument_number=instrument_number,
        cruise=cruise,
        sample_type=sample_type,
        tags=tags
    )


def image_page(request):
    bin_id = request.GET.get("bin")
    image_id = request.GET.get("image")

    dataset_name = request.GET.get("dataset")
    instrument_number = request_get_instrument(request.GET.get("instrument"))
    tags = request_get_tags(request.GET.get("tags"))
    cruise = request_get_cruise(request.GET.get("cruise"))
    sample_type = request_get_sample_type(request.GET.get("sample_type"))

    return _image_details(
        request,
        image_id,
        bin_id,
        dataset_name,
        instrument_number,
        tags,
        cruise,
        sample_type
    )


def comments_page(request):
    dataset_name = request.GET.get("dataset")
    instrument_number = request_get_instrument(request.GET.get("instrument"))
    tags = request_get_tags(request.GET.get("tags"))
    cruise = request_get_cruise(request.GET.get("cruise"))
    sample_type = request_get_sample_type(request.GET.get("sample_type"))

    filters = []
    if dataset_name:
        filters.append("Dataset: " + dataset_name)
    if instrument_number:
        filters.append("Instrument: IFCB" + str(instrument_number))
    if tags:
        filters.append("Tags: " + ', '.join(tags))
    if cruise:
        filters.append("Cruise: " + cruise)
    if sample_type:
        filters.append("Sample Type: " + sample_type)

    return render(request, "dashboard/comments.html", {
        'dataset': '' if dataset_name is None else dataset_name,
        'instrument': '' if instrument_number is None else instrument_number,
        'tags': '' if not tags else ','.join(tags),
        'cruise': '' if cruise is None else cruise,
        'sample_type': '' if sample_type is None else sample_type,
        'filters': '' if not filters else ', '.join(filters),
    })


@require_POST
def search_comments(request):
    query = request.POST.get("query")

    bq = filter_parameters_bin_query(request.POST)

    bq = bq.filter(comments__content__icontains=query).values('pid')
    b_pids = [t['pid'] for t in bq]

    comments = list(Comment.objects.filter(content__icontains=query)
        .select_related('user')
        .select_related('bin')
        .order_by("-timestamp")
        .values_list("timestamp", "content", "user__username", "bin__pid"))

    rows = []
    for c in comments:
        ts, cont, user, pid = c
        if pid in b_pids:
            rows.append(c)

    return JsonResponse({
        "data": rows,
    })


# FIXME needs cruise and sample type?
def _image_details(request, image_id, bin_id, dataset_name=None, instrument_number=None, tags=None, cruise=None, sample_type=None):
    image_number = int(image_id)
    bin = get_object_or_404(Bin, pid=bin_id)
    if dataset_name:
        dataset = get_object_or_404(Dataset, name=dataset_name)
    else:
        dataset = bin.primary_dataset()

    bin_in_dataset_or_404(bin, dataset)

    try:
        image = bin.image(image_number)
    except KeyError:
        raise Http404("image data not found")
    image_width = image.shape[1];

    metadata = _image_metadata(bin.pid, image_number)

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
        "mode": request.GET.get("mode", ""),
        "image_list": bin.list_images(),
        "dataset_name": dataset_name,
        "instrument_number": instrument_number,
        "tags": tags,
        "cruise": cruise,
        "sample_type": sample_type,
    })


def legacy_dataset_page(request, dataset_name, bin_id):
    return _details(request, bin_id=bin_id, route="dataset", dataset_name=dataset_name )

def legacy_dataset_redirect(request, dataset_name):
    return HttpResponseRedirect(reverse("timeline_page") + "?dataset=" + dataset_name)

def legacy_bin_page(request, dataset_name, bin_id):
    return _details(request, bin_id=bin_id, route="dataset", dataset_name=dataset_name)


def legacy_image_page(request, dataset_name, bin_id, image_id):
    return _image_details(request, image_id, bin_id, dataset_name)


def legacy_image_page_alt(request, bin_id, image_id):
    return _image_details(request, image_id, bin_id)


def _details(request, bin_id=None, route=None, dataset_name=None, tags=None, instrument_number=None, cruise=None, bin_reset=False,
             default_start_date=None, default_end_date=None, sample_type=None):
    if not bin_id and not dataset_name and not tags and not instrument_number and not cruise and not sample_type:
        # TODO: 404 error; don't have enough info to proceed
        pass


    bin_qs = bin_query(dataset_name=dataset_name,
        tags=tags,
        instrument_number=instrument_number,
        cruise=cruise,
        sample_type=sample_type)
    timeline = Timeline(bin_qs)

    if bin_id:
        bin = get_object_or_404(Bin, pid=bin_id)
    else:
        bin = timeline.most_recent_bin()

    if dataset_name:
        dataset = get_object_or_404(Dataset, name=dataset_name)
    else:
        dataset = None

    bin, dataset = bin_in_dataset_or_404(bin, dataset)

    instrument = get_object_or_404(Instrument, number=instrument_number) if instrument_number else None

    if bin is None:
        return render(request, "dashboard/no-bins.html", {})

    return render(request, "dashboard/bin.html", {
        "route": route,
        "can_share_page": True,
        "can_filter_page": (route == "timeline"),
        "dataset": dataset,
        "instrument": instrument,
        'sample_type': sample_type,
        "cruise": cruise,
        "tags": ','.join(tags) if tags else '',
        "mosaic_scale_factors": Bin.MOSAIC_SCALE_FACTORS,
        "mosaic_view_sizes": Bin.MOSAIC_VIEW_SIZES,
        "mosaic_default_scale_factor": Bin.MOSAIC_DEFAULT_SCALE_FACTOR,
        "mosaic_default_view_size": Bin.MOSAIC_DEFAULT_VIEW_SIZE,
        "mosaic_default_height": Bin.MOSAIC_DEFAULT_VIEW_SIZE.split("x")[1],
        "mosaic_default_width": Bin.MOSAIC_DEFAULT_VIEW_SIZE.split("x")[0],
        "bin": bin,
        "bin_reset": bin_reset,
        "default_start_date": default_start_date,
        "default_end_date": default_end_date,
        "details": _bin_details(bin, dataset, preload_adjacent_bins=False, include_coordinates=False,
                                instrument_number=instrument_number, tags=tags),
    })


def image_metadata(request, bin_id, target):
    metadata = _image_metadata(bin_id, target)

    return JsonResponse(metadata)


def image_data(request, bin_id, target):
    bin = get_object_or_404(Bin, pid=bin_id)
    image = bin.image(target)
    data = embed_image(image)

    return JsonResponse({
        "data": data
    })


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
@require_POST
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
@require_POST
def mosaic_page_image(request, bin_id):
    arr = _mosaic_page_image(request, bin_id)
    image_data = format_image(arr, 'image/png')

    return HttpResponse(image_data, content_type='image/png')


@cache_control(max_age=31557600) # client cache for 1y
@require_POST
def mosaic_page_encoded_image(request, bin_id):
    arr = _mosaic_page_image(request, bin_id)

    return HttpResponse(embed_image(arr), content_type='plain/text')


def _image_data(bin_id, target, mimetype):
    b = get_object_or_404(Bin, pid=bin_id)
    try:
        arr = b.image(target)
    except KeyError:
        raise Http404("image data not found")
    image_data = format_image(arr, mimetype)
    return HttpResponse(image_data, content_type=mimetype)


def _image_metadata(bin_id, target):
    bin = get_object_or_404(Bin, pid=bin_id)
    metadata = bin.target_metadata(target)

    def fmt(k,v):
        if k == 'start_byte':
            return str(v)
        elif isinstance(v, float):
            return "{:.4f}".format(v)
        else:
            return '{:.5g}'.format(v)

    for k in metadata:
        metadata[k] = fmt(k, metadata[k])

    return metadata


def image_png(request, bin_id, target):
    return _image_data(bin_id, target, 'image/png')


def image_jpg(request, bin_id, target):
    return _image_data(bin_id, target, 'image/jpeg')


def image_png_legacy(request, bin_id, target, dataset_name):
    bin_in_dataset_or_404(bin_id, dataset_name)
    return _image_data(bin_id, target, 'image/png')


def image_jpg_legacy(request, bin_id, target, dataset_name):
    bin_in_dataset_or_404(bin_id, dataset_name)
    return _image_data(bin_id, target, 'image/jpeg')

def fully_qualified_timeseries_url(request, dataset_name):
    scheme = request.scheme
    host_port = request.get_host()
    return '{}://{}/{}'.format(scheme, host_port, dataset_name)

def legacy_short_json(request, dataset_name, bin_id):
    b = get_object_or_404(Bin, pid=bin_id)
    bin_in_dataset_or_404(b, dataset_name)
    metadata = b.metadata
    metadata['date'] = b.timestamp
    fq_ts_url = fully_qualified_timeseries_url(request, dataset_name)
    fq_pid = '{}/{}'.format(fq_ts_url, bin_id)
    metadata['pid'] = fq_pid
    return JsonResponse(metadata)

def legacy_roisizes(request, dataset_name, bin_id):
    b = get_object_or_404(Bin, pid=bin_id)
    bin_in_dataset_or_404(b, dataset_name)
    fq_ts_url = fully_qualified_timeseries_url(request, dataset_name)
    ii = b.images()
    tns, pids, widths, heights = [], [], [], []
    for target_number in ii:
        tns.append(target_number)
        fq_pid = '{}/{}_{:05d}'.format(fq_ts_url, bin_id, target_number)
        width, height = ii.shape(target_number)
        pids.append(fq_pid)
        widths.append(int(width))
        heights.append(int(height))
    return JsonResponse({
        'targetNumber': tns,
        'width': widths,
        'height': heights,
        'pid': pids
        })

def adc_data(request, bin_id, **kw):
    b = get_object_or_404(Bin, pid=bin_id)
    if 'dataset_name' in kw:
        bin_in_dataset_or_404(b, kw['dataset_name'])
    try:
        adc_path = b.adc_path()
    except KeyError:
        raise Http404("raw data not found")
    filename = '{}.adc'.format(bin_id)
    fin = open(adc_path, 'rb')
    return FileResponse(fin, as_attachment=True, filename=filename, content_type='text/csv')

def hdr_data(request, bin_id, **kw):
    b = get_object_or_404(Bin, pid=bin_id)
    if 'dataset_name' in kw:
        bin_in_dataset_or_404(b, kw['dataset_name'])
    try:
        hdr_path = b.hdr_path()
    except KeyError:
        raise Http404("raw data not found")
    filename = '{}.hdr'.format(bin_id)
    fin = open(hdr_path, 'rb')
    return FileResponse(fin, as_attachment=True, filename=filename, content_type='text/plain')


def roi_data(request, bin_id, **kw):
    b = get_object_or_404(Bin, pid=bin_id)
    if 'dataset_name' in kw:
        bin_in_dataset_or_404(b, kw['dataset_name'])
    try:
        roi_path = b.roi_path()
    except KeyError:
        raise Http404("raw data not found")
    filename = '{}.roi'.format(bin_id)
    fin = open(roi_path, 'rb')
    return FileResponse(fin, as_attachment=True, filename=filename, content_type='application/octet-stream')

def get_product_version_parameter(request, default=None):
    version_string = request.GET.get('v',default)
    if version_string is not None:
        try:
            return int(version_string)
        except ValueError:
            raise Http404

def blob_zip(request, bin_id, **kw):
    b = get_object_or_404(Bin, pid=bin_id)
    if 'dataset_name' in kw:
        bin_in_dataset_or_404(b, kw['dataset_name'])
    version = get_product_version_parameter(request)
    try:
        blob_file = b.blob_file(version=version)
        version = blob_file.version
        blob_path = blob_file.path
    except KeyError:
        raise Http404
    filename = '{}_blobs_v{}.zip'.format(bin_id, version)
    fin = open(blob_path, 'rb')
    return FileResponse(fin, as_attachment=True, filename=filename, content_type='application/zip')

def features_csv(request, bin_id, **kw):
    b = get_object_or_404(Bin, pid=bin_id)
    if 'dataset_name' in kw:
        bin_in_dataset_or_404(b, kw['dataset_name'])
    version = get_product_version_parameter(request)
    try:
        features_file = b.features_file(version=version)
        version = features_file.version
        features_path = features_file.path
    except KeyError:
        raise Http404
    filename = '{}_features_v{}.csv'.format(bin_id, version)
    fin = open(features_path, 'rb')
    return FileResponse(fin, as_attachment=True, filename=filename, content_type='text/csv')

def class_scores_mat(request, bin_id, **kw):
    b = get_object_or_404(Bin, pid=bin_id)
    if 'dataset_name' in kw:
        bin_in_dataset_or_404(b, kw['dataset_name'])
    version = get_product_version_parameter(request)
    try:
        class_scores_file = b.class_scores_file(version=version)
        version = class_scores_file.version
        class_scores_path = class_scores_file.path
    except KeyError:
        raise Http404
    filename = '{}_class_v{}.mat'.format(bin_id, version)
    fin = open(class_scores_path, 'rb')
    return FileResponse(fin, as_attachment=True, filename=filename, content_type='application/octet-stream')    

def class_scores_csv(request, dataset_name, bin_id):
    b = get_object_or_404(Bin, pid=bin_id)
    bin_in_dataset_or_404(b, dataset_name)
    version = get_product_version_parameter(request, None)
    try:
        class_scores = b.class_scores(version=version)
    except KeyError:
        raise Http404
    class_scores.index = ['{}_{:05d}'.format(bin_id, tn) for tn in class_scores.index]
    class_scores.index.name = 'pid'
    resp = dataframe_csv_response(class_scores)
    filename = '{}_class_v{}.csv'.format(bin_id, version)
    resp['Content-Disposition'] = 'attachment; filename={}'.format(filename)
    return resp

from django.views.decorators.csrf import csrf_protect

@require_POST
def zip(request, bin_id, **kwargs):
    return _build_zip(request, bin_id, **kwargs)

@require_GET
def download_zip(request, bin_id, **kwargs):
    api_key = request.headers.get("ApiKey")

    api_account = ApiAccount.objects.filter(api_key=api_key).first()
    if not api_account:
        return HttpResponseForbidden()

    return _build_zip(request, bin_id, **kwargs)

def _build_zip(request, bin_id, **kwargs):
    b = get_object_or_404(Bin, pid=bin_id)

    if 'dataset_name' in kwargs:
        bin_in_dataset_or_404(b, kwargs['dataset_name'])

    try:
        zip_buf = b.zip()
    except KeyError:
        raise Http404("raw data not found")

    filename = '{}.zip'.format(bin_id)

    return FileResponse(zip_buf, as_attachment=True, filename=filename, content_type='application/zip')


def _bin_details(bin, dataset=None, view_size=None, scale_factor=None, preload_adjacent_bins=False,
                 include_coordinates=True, instrument_number=None, tags=None, cruise=None, sample_type=None):
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

    try:
        datasets = [d.name for d in bin.datasets.all()]
    except:
        datasets = []

    if dataset is not None:
        primary_dataset = dataset.name
    elif len(datasets) > 0:
        primary_dataset = datasets[0]
    else:
        primary_dataset = None

    if (dataset or instrument_number or tags or cruise or sample_type or primary_dataset):
        if dataset is not None:
            dataset_name = dataset.name
        elif primary_dataset is not None:
            dataset_name = primary_dataset
        else:
            dataset_name = None
        bin_qs = bin_query(dataset_name=dataset_name, instrument_number=instrument_number,
            tags=tags, cruise=cruise, sample_type=sample_type)
        previous_bin = Timeline(bin_qs).previous_bin(bin)
        next_bin = Timeline(bin_qs).next_bin(bin)

    if preload_adjacent_bins:
        if previous_bin is not None:
            previous_bin.mosaic_coordinates(shape=mosaic_shape, scale=mosaic_scale, block=False)
        if next_bin is not None:
            next_bin.mosaic_coordinates(shape=mosaic_shape, scale=mosaic_scale, block=False)


    return {
        "scale": mosaic_scale,
        "shape": mosaic_shape,
        "previous_bin_id": previous_bin.pid if previous_bin is not None else "",
        "next_bin_id": next_bin.pid if next_bin is not None else "",
        "lat": bin.latitude,
        "lng": bin.longitude,
        "lat_rounded": str(round(bin.latitude, 5)),
        "lng_rounded": str(round(bin.longitude, 5)),
        "depth": bin.get_depth(),
        "pages": list(range(pages + 1)),
        "num_pages": int(pages),
        "tags": bin.tag_names,
        "coordinates": coordinates_json,
        #"has_blobs": bin.has_blobs(),
        #"has_features": bin.has_features(),
        #"has_class_scores": bin.has_class_scores(), # FIXME slow
        "has_blobs": False,
        "has_features": False,
        "has_class_scores": False,
        "timestamp_iso": bin.sample_time.isoformat(),
        "instrument": "IFCB" + str(bin.instrument.number),
        "num_triggers": bin.n_triggers,
        "num_images": bin.n_images,
        "trigger_freq": round(bin.trigger_frequency, 3),
        "ml_analyzed": str(round(bin.ml_analyzed, 3)) + " ml",
        "size": bin.size,
        "datasets": datasets,
        "primary_dataset": primary_dataset,
        "comments": bin.comment_list,
        "concentration": round(bin.concentration, 3),
        "skip": bin.skip,
        "sample_type": bin.sample_type,
        "cruise": bin.cruise,
        "cast": bin.cast,
        "niskin": bin.niskin,
    }

def _mosaic_page_image(request, bin_id):
    view_size = request.GET.get("view_size", Bin.MOSAIC_DEFAULT_VIEW_SIZE)
    scale_factor = int(request.GET.get("scale_factor", Bin.MOSAIC_DEFAULT_SCALE_FACTOR))
    page = int(request.GET.get("page", 0))

    bin = get_object_or_404(Bin, pid=bin_id)
    shape = parse_view_size(view_size)
    scale = parse_scale_factor(scale_factor)
    try:
        arr, _ = bin.mosaic(page=page, shape=shape, scale=scale)
    except KeyError: # raw data not found
        #return np.array([[0]], dtype='uint8')
        raise Http404('raw data not found')

    return arr

# TODO: The below views are API/AJAX calls; in the future, it would be beneficial to use a proper API framework
# TODO: The logic to flow through to a finer resolution if the higher ones only return one data item works, but
#   it causes the UI to need to download data on each zoom level when scroll up, only to then ignore the data. Updates
#   are needed to let the UI know that certain levels are "off limits" and avoid re-running data when we know it's
#   just going to force us down to a finer resolution anyway
# TODO: Handle tag/instrument grouping
def generate_time_series(request, metric,):
    resolution = request.GET.get("resolution", "auto")
    start = request.GET.get("start",None)
    end = request.GET.get("end",None)
    if start is not None:
        start = pd.to_datetime(start, utc=True)
    if end is not None:
        end = pd.to_datetime(end, utc=True)

    # Allows us to keep consistent url names
    metric = metric.replace("-", "_")

    bin_qs = filter_parameters_bin_query(request.GET)

    def query_timeline(metric, start, end, resolution):
        time_series, resolution = Timeline(bin_qs).metrics(metric, start, end, resolution=resolution)

        time_data = [item["dt"] for item in time_series]
        metric_data = []
        
        for item in time_series:
            value = item['metric']
            try:
                if value >= 0:
                    metric_data.append(value)
                else:
                    metric_data.append(0)
            except TypeError:
                metric_data.append(0)

        return time_series, resolution, time_data, metric_data

    if start is not None:
        time_start = start
    if end is not None:
        time_end = end

    time_series, resolution, time_data, metric_data = query_timeline(metric, start, end, resolution)

    if not time_data:
        pass
    elif len(time_data) == 1:
        time_start = time_data[0] - pd.Timedelta('20m')
        time_end = time_data[0] + pd.Timedelta('20m')
        time_series, resolution, time_data, metric_data = query_timeline(metric, time_start, time_end, resolution)
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
    cruise = request_get_cruise(request.GET.get("cruise"))
    sample_type = request_get_sample_type(request.GET.get('sample_type'))

    if dataset_name:
        dataset = get_object_or_404(Dataset, name=dataset_name)
    else:
        dataset = None

    bin = get_object_or_404(Bin, pid=bin_id)
    view_size = request.GET.get("view_size", Bin.MOSAIC_DEFAULT_VIEW_SIZE)
    scale_factor = request.GET.get("scale_factor", Bin.MOSAIC_DEFAULT_SCALE_FACTOR)

    # Allow the preload flag to be passed in, but it only applies if this is a POST request. This is to prevent someone
    #   scraping the URLS and causing high CPU load with some of the inner mosaic methods
    # The same logic applies to including coordinates in the output
    if request.POST:
        include_coordinates = request.GET.get("include_coordinates", "false").lower() == "true"
        preload_adjacent_bins = request.GET.get("preload_adjacent_bins", "false").lower() == "true"
    else:
        include_coordinates = False
        preload_adjacent_bins = False

    details = _bin_details(bin, dataset, view_size, scale_factor, preload_adjacent_bins, include_coordinates,
                           instrument_number=instrument_number, tags=tags, cruise=cruise, sample_type=sample_type)

    return JsonResponse(details)


def closest_bin(request):
    bin_qs = filter_parameters_bin_query(request.POST)

    target_date = request.POST.get("target_date", None)

    try:
        dte = pd.to_datetime(target_date, utc=True)
    except:
        dte = None

    bin = Timeline(bin_qs).bin_closest_in_time(dte)

    return JsonResponse({
        "bin_id": bin.pid,
    })


def nearest_bin(request):
    bins = filter_parameters_bin_query(request.POST)
    start = request.POST.get('start')  # limit to start time
    end = request.POST.get('end')  # limit to end time

    lat = request.POST.get('latitude')
    lon = request.POST.get('longitude')
    if lat is None or lon is None:
        return HttpResponseBadRequest('lat/lon required')
    if tags is None:
        tags = []
    else:
        tags = ','.split(tags)
    lon = float(lon)
    lat = float(lat)
    bin_id = Timeline(bins).nearest_bin(lon, lat).pid
    return JsonResponse({
        'bin_id': bin_id
    })


def plot_data(request, bin_id):
    b = get_object_or_404(Bin, pid=bin_id)
    try:
        bin = b._get_bin()
    except KeyError:
        raise Http404('raw data not found')
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
    return JsonResponse(ia.to_dict('list'))


BIN_METADATA_ORDER = [
    'FileComment',
    'runType',
    'SyringeNumber',
    'Syringe Number',
    'SyringeSampleVolume',
    'sampleVolume2skip',
    'runTime',
    'inhibitTime',
    'temperature',
    'humidity',

    'PMTAhighVoltage',
    'PMTBhighVoltage',
    'PMTAtriggerThreshold_DAQ_MCConly',
    'PMTBtriggerThreshold_DAQ_MCConly',

    'blobXgrowAmount',
    'blobYgrowAmount',
    'binarizeThreshold',
    'minimumBlobArea',
    'PumpStates',
    'runSampleFast',
]

def bin_metadata(request, bin_id):
    bin = get_object_or_404(Bin, pid=bin_id)

    bin_metadata = bin.metadata
    reordered_metadata = {}
    keys = list(bin_metadata.keys())

    for k in BIN_METADATA_ORDER:
        if k in bin_metadata:
            keys.remove(k)
            reordered_metadata[k] = bin_metadata[k]

    for k in keys:
        reordered_metadata[k] = bin_metadata[k]

    return JsonResponse({
        "metadata": reordered_metadata
    })


def bin_exists(request):
    bin_qs = filter_parameters_bin_query(request.GET)

    exists = bin_qs.exists()

    return JsonResponse({
        "exists": exists
    })


def single_bin_exists(request):
    try:
        bin = Bin.objects.get(pid=request.GET.get("pid"))

        return JsonResponse({"exists": True})
    except:
        return JsonResponse({"exists" : False})


def bin_location(request):
    try:
        location = Bin.objects.get(pid=request.GET.get("pid")).get_location()

        if location:
            return JsonResponse({
                "lat": location.y,
                "lng": location.x
            })
    except:
        pass

    # None that we're specifically returning none, rather than the fill value, so the front-end is clear that
    #  there is no location for this bin
    return JsonResponse({
        "lat": None,
        "lng": None
    })


def filter_options(request):
    dataset_name = request.GET.get("dataset")
    tags = request_get_tags(request.GET.get("tags"))
    instrument_number = request_get_instrument(request.GET.get("instrument"))
    cruise = request_get_cruise(request.GET.get("cruise"))
    sample_type = request_get_sample_type(request.GET.get('sample_type'))

    if dataset_name:
        ds = Dataset.objects.get(name=dataset_name)
    else:
        ds = None
    if instrument_number:
        instr = Instrument.objects.get(number=instrument_number)
    else:
        instr = None
        instrument_number = 0

    tag_options = Tag.list(ds, instr)

    bq = bin_query(dataset_name=dataset_name, tags=tags, cruise=cruise, sample_type=sample_type)
    qs = bq.values('instrument__number').order_by('instrument__number').distinct()
    instruments_options = [i['instrument__number'] for i in qs]

    datasets_options = [ds.name for ds in Dataset.objects.filter(is_active=True).order_by('name')]

    bq = bin_query(dataset_name=dataset_name, tags=tags, instrument_number=instrument_number, sample_type=sample_type)
    cruise_options = [c['cruise'] for c in bq.exclude(cruise='').values('cruise').order_by('cruise').distinct()]

    bq = bin_query(dataset_name=dataset_name, tags=tags, cruise=cruise, instrument_number=instrument_number)
    sample_type_options = [c['sample_type'] for c in bq.exclude(sample_type='').values('sample_type').order_by('sample_type').distinct()]

    return JsonResponse({
        "instrument_options": instruments_options,
        "dataset_options": datasets_options,
        "tag_options": tag_options,
        "cruise_options": cruise_options,
        'sample_type_options': sample_type_options,
        })

def has_products(request, bin_id):
    b = get_object_or_404(Bin, pid=bin_id)

    return JsonResponse({
        "has_blobs": b.has_blobs(),
        "has_features": b.has_features(),
        "has_class_scores": b.has_class_scores(),
    })

# legacy feed view
def feed_legacy(request, ds_plus_tags, metric, start, end):
    if metric not in ['temperature','humidity']: # does not support "trigger_rate"
        raise Http404('unsupported metric "{}"'.format(metric))

    # the dataset notation is dataset followed by colon-separated tags
    # so /mvco/api/feed ... is for the "mvco" dataset, and
    # /mvco:foo:bar/api/feed is for mvco bins tagged "foo" and "bar"
    dpt = re.split(':', ds_plus_tags)
    ds, tags = dpt[0], dpt[1:]
    
    ts_url = request.build_absolute_uri('/') + ds + '/'

    bq = bin_query(dataset_name=ds, tags=tags, start=start, end=end)

    records = []
    for pid, date, metric_value in bq.values_list('pid','sample_time',metric):
        records.append({
            'pid': ts_url + pid,
            'date': date,
            metric: metric_value
            })

    # set "safe" to False because we're returning a list, not a dict
    return JsonResponse(records, safe=False)

def tag_list(request):
    tags = Tag.list()

    return JsonResponse({'tags': list(tags)})

def tags(request):
    dataset_name = request.GET.get("dataset")
    instrument_number = request_get_instrument(request.GET.get("instrument"))
    if dataset_name is not None:
        dataset = get_object_or_404(Dataset, name=dataset_name)
    else:
        dataset = None
    if instrument_number is not None:
        instrument = get_object_or_404(Instrument, number=instrument_number)
    else:
        instrument = None
    cloud = Tag.cloud(dataset=dataset, instrument=instrument)
    return JsonResponse({'cloud': list(cloud)})

def timeline_info(request):
    bin_qs = filter_parameters_bin_query(request.GET)

    timeline = Timeline(bin_qs)

    return JsonResponse({
        'n_bins': len(timeline),
        'total_data_volume': timeline.total_data_volume(),
        'n_images': timeline.n_images(),
        })


def list_bins(request):
    dataset_name = request.GET.get("dataset")
    tags = request_get_tags(request.GET.get("tags"))
    instrument_number = request_get_instrument(request.GET.get("instrument"))
    cruise = request_get_cruise(request.GET.get("cruise"))
    sample_type = request.GET.get('sample_type')
    skip_filter = request.GET.get("skip_filter")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    output_format = request.GET.get("format")

    # Initial query for pulling bins. Note that skipped bins are included so it can be filtered based
    #   on the querystring options
    bin_qs = bin_query(dataset_name=dataset_name,
                       tags=tags,
                       instrument_number=instrument_number,
                       cruise=cruise,
                       sample_type=sample_type,
                       filter_skip=False)

    if start_date:
        start_date = pd.to_datetime(start_date, utc=True)
        bin_qs = bin_qs.filter(sample_time__gte=start_date)

    if end_date:
        end_date = pd.to_datetime(end_date, utc=True) + pd.Timedelta('1d')
        bin_qs = bin_qs.filter(sample_time__lte=end_date)

    if skip_filter == "exclude":
        bin_qs = bin_qs.exclude(skip=True)
    elif skip_filter == "only":
        bin_qs = bin_qs.filter(skip=True)

    bin_qs = bin_qs.order_by('sample_time')

    bins = list(bin_qs.values("pid", "sample_time", "skip"))

    if output_format and output_format == 'csv':
        df = pd.DataFrame.from_dict(bins)
        return dataframe_csv_response(df, index=None)

    return JsonResponse({
        "data": bins
    })


def list_images(request, pid):
    b = get_object_or_404(Bin, pid=pid)
    return JsonResponse({
        'images': b.list_images()
        })


@login_required
def update_skip(request):
    skip = request.POST.get("skip") == "true"
    bin_ids = request.POST.getlist("bins[]")

    for bin in Bin.objects.filter(pid__in=bin_ids):
        bin.skip = skip
        bin.save()

    return JsonResponse({
        "skip": skip,
        "bins": bin_ids
    })

def export_metadata_view(request, dataset_name=None):
    tags = request_get_tags(request.GET.get("tags"))
    instrument_number = request_get_instrument(request.GET.get("instrument"))
    cruise = request_get_cruise(request.GET.get("cruise"))
    sample_type = request.GET.get('sample_type')
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    include_skip = request.GET.get('include_skip', 'true')

    filter_skip = not include_skip.lower() == 'true'

    bin_qs = bin_query(dataset_name=dataset_name,
                       tags=tags,
                       instrument_number=instrument_number,
                       cruise=cruise,
                       sample_type=sample_type,
                       filter_skip=filter_skip)

    if start_date:
        start_date = pd.to_datetime(start_date, utc=True)
        bin_qs = bin_qs.filter(sample_time__gte=start_date)

    if end_date:
        end_date = pd.to_datetime(end_date, utc=True) + pd.Timedelta('1d')
        bin_qs = bin_qs.filter(sample_time__lte=end_date)

    if bin_qs.count() == 0:
        raise Http404('no bins match the given query')

    ds = Dataset.objects.get(name=dataset_name) if dataset_name else None
    df = export_metadata(ds, bin_qs)

    filename = (dataset_name or 'ifcb-metadata') + '.csv'
    response = dataframe_csv_response(df, index=None)
    response['Content-Disposition'] = f'attachment; filename={filename}'

    return response

def sync_bin(request):
    dataset_name = request.GET.get("dataset")
    bin_id = request.GET.get('bin')
    dataset = get_object_or_404(Dataset, name=dataset_name)
    try:
        b = Bin.objects.get(pid=bin_id)
        return JsonResponse({'result':'exists'})
    except Bin.DoesNotExist:
        pass
    acc = Accession(dataset)
    acc.sync_one(bin_id)
    return JsonResponse({'result':'synced'})

def about_page(request):
    return render(request, 'dashboard/about.html')
