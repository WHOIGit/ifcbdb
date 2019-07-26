from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, Http404
from django.shortcuts import render, get_object_or_404, redirect, reverse

from dashboard.models import Dataset, Instrument, DataDirectory
from .forms import DatasetForm, InstrumentForm, DirectoryForm


# TODO: All of these methods need to be locked down properly

@login_required
def index(request):
    return render(request, 'secure/index.html', {

    })


def dataset_management(request):
    form = DatasetForm()

    return render(request, 'secure/dataset-management.html', {
        "form": form,
    })


def directory_management(request, dataset_id):
    dataset = get_object_or_404(Dataset, pk=dataset_id)

    return render(request, "secure/directory-management.html", {
        "dataset": dataset,
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


def dt_directories(request, dataset_id):
    directories = list(DataDirectory.objects.filter(dataset__id=dataset_id)
                       .values_list("path", "kind", "priority", "whitelist", "blacklist", "id"))

    return JsonResponse({
        "data": directories,
    })


def edit_dataset(request, id):
    status = request.GET.get("status")

    if int(id) > 0:
        dataset = get_object_or_404(Dataset, pk=id)
    else:
        dataset = Dataset()

    if request.POST:
        form = DatasetForm(request.POST, instance=dataset)
        if form.is_valid():
            instance = form.save()

            status = "created" if id == 0 else "updated"
            return redirect(reverse("secure:edit-dataset", kwargs={"id": instance.id}) + "?status=" + status)
    else:
        form = DatasetForm(instance=dataset)

    return render(request, "secure/edit-dataset.html", {
        "status": status,
        "form": form,
        "dataset": dataset,
    })


def edit_directory(request, dataset_id, id):
    if int(id) > 0:
        directory = get_object_or_404(DataDirectory, pk=id)
    else:
        directory = DataDirectory(dataset_id=dataset_id)

    if request.POST:
        form = DirectoryForm(request.POST, instance=directory)
        if form.is_valid():
            form.save()

            return redirect(reverse("secure:directory-management", kwargs={"dataset_id": dataset_id}))
    else:
        form = DirectoryForm(instance=directory)

    return render(request, "secure/edit-directory.html", {
        "directory": directory,
        "dataset_id": dataset_id,
        "form": form,
    })


# TODO: Remove the CSRF exmpt flag
@require_POST
@csrf_exempt
def delete_directory(request, dataset_id, id):
    directory = get_object_or_404(DataDirectory, pk=id)

    if directory.dataset_id != dataset_id:
        return Http404("No Data Directory matches the given query")

    directory.delete()
    return JsonResponse({})



def dt_instruments(request):
    instruments = list(Instrument.objects.all().values_list("number", "nickname", "id"))

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
