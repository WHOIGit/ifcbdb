from django.contrib.auth.decorators import login_required
from django.views.decorators import http
from django.core import serializers
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect, reverse

from dashboard.models import Dataset, Instrument
from .forms import DatasetForm, InstrumentForm


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
    form = InstrumentForm()

    return render(request, 'secure/instrument-management.html', {
        "form": form,
    })


def upload_geospatial(request):
    return render(request, 'secure/upload-geospatial.html', {

    })


def dt_datasets(request):
    datasets = list(Dataset.objects.all().values_list("name", "title", "is_active", "id"))

    return JsonResponse({
        "data": datasets
    })



def edit_dataset(request, id):
    if int(id) > 0:
        dataset = get_object_or_404(Dataset, pk=id)
    else:
        dataset = Dataset()

    if request.POST:
        form = DatasetForm(request.POST, instance=dataset)
        if form.is_valid():
            form.save()

            return redirect(reverse("secure:dataset-management"))
    else:
        form = DatasetForm(instance=dataset)

    return render(request, "secure/edit-dataset.html", {
        "form": form,
        "dataset": dataset,
    })


def dt_instruments(request):
    instruments = list(Instrument.objects.all().values_list("number", "version", "nickname", "id"))

    return JsonResponse({
        "data": instruments
    })


def edit_instrument(request, id):
    if int(id) > 0:
        instrument = get_object_or_404(Instrument, pk=id)
    else:
        instrument = Instrument()

    if request.POST:
        form = InstrumentForm(request.POST, instance=instrument)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.version = Instrument.determine_version(instance.number)

            password = form.cleaned_data["password"]
            if password:
                instance.set_password(password)

            instance.save()

            return redirect(reverse("secure:instrument-management"))
    else:
        form = InstrumentForm(instance=instrument)

    return render(request, "secure/edit-instrument.html", {
        "instrument": instrument,
        "form": form,
    })
