from django.contrib.auth.decorators import login_required
from django.views.decorators import http
from django.core import serializers
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404

from dashboard.models import Dataset
from .forms import DatasetForm


@login_required
def index(request):
    return render(request, 'secure/index.html', {

    })


def dataset_management(request):
    form = DatasetForm()

    return render(request, 'secure/dataset-management.html', {
        "form": form,
    })


def instrument_management(request):
    return render(request, 'secure/instrument-management.html', {

    })


def upload_geospatial(request):
    return render(request, 'secure/upload-geospatial.html', {

    })


def dt_datasets(request):
    datasets = list(Dataset.objects.all().values_list("name", "title", "id"))

    return JsonResponse({
        "data": datasets
    })


def dataset(request, id):
    dataset = get_object_or_404(Dataset, pk=id)
    resp = serializers.serialize("json", [dataset, ])

    return HttpResponse(resp, content_type="application/json")


@http.require_POST
def update_dataset(request, id):
    if id > 0:
        dataset = Dataset.objects.get(pk=id)
    else:
        dataset = Dataset()

    form = DatasetForm(request.POST, instance=dataset)

    if form.is_valid():
        form.save()
        return JsonResponse({
            "success": True
        })

    return JsonResponse({
        "success": False,
        "errors": list(form.errors.items())
    })
