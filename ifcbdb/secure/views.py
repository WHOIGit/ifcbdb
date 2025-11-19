from django.contrib.auth.decorators import login_required
from django import forms
from django.views.decorators.http import require_POST, require_GET
from django.http import JsonResponse, Http404, HttpResponseForbidden, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect, reverse
from django.db.models import Count

import pandas as pd

from dashboard.models import Dataset, Instrument, DataDirectory, Tag, TagEvent, Bin, Comment, AppSettings
from .forms import DatasetForm, InstrumentForm, DirectoryForm, MetadataUploadForm, AppSettingsForm, TagForm, \
    MergeTagForm

from django.core.cache import cache
from celery.result import AsyncResult


@login_required
def index(request):
    return render(request, 'secure/index.html', {

    })


@login_required
def dataset_management(request):
    form = DatasetForm()

    return render(request, 'secure/dataset-management.html', {
        "form": form,
    })


@login_required
def directory_management(request, dataset_id):
    dataset = get_object_or_404(Dataset, pk=dataset_id)

    return render(request, "secure/directory-management.html", {
        "dataset": dataset,
    })


@login_required
def instrument_management(request):
    form = InstrumentForm()

    return render(request, 'secure/instrument-management.html', {
        "form": form,
    })


@login_required
def tag_management(request):
    return render(request, 'secure/tag-management.html', {

    })


@login_required
def dt_datasets(request):
    datasets = list(Dataset.objects.all().values_list("name", "title", "is_active", "id"))

    return JsonResponse({
        "data": datasets
    })


@login_required
def dt_directories(request, dataset_id):
    directories = list(DataDirectory.objects.filter(dataset__id=dataset_id)
                       .values_list("path", "kind", "priority", "whitelist", "blacklist", "id"))

    return JsonResponse({
        "data": directories,
    })


@login_required
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


@login_required
def edit_directory(request, dataset_id, id):
    if int(id) > 0:
        directory = get_object_or_404(DataDirectory, pk=id)
    else:
        directory = DataDirectory(dataset_id=dataset_id)
        directory.version = DataDirectory.DEFAULT_VERSION

    if request.POST:
        form = DirectoryForm(request.POST, instance=directory, dataset_id=dataset_id)
        if form.is_valid():
            instance = form.save(commit=False)
            if instance.kind == "raw":
                instance.version = None
            instance.save()

            return redirect(reverse("secure:directory-management", kwargs={"dataset_id": dataset_id}))
    else:
        form = DirectoryForm(instance=directory)

    return render(request, "secure/edit-directory.html", {
        "directory": directory,
        "dataset_id": dataset_id,
        "form": form,
    })


@require_POST
def delete_directory(request, dataset_id, id):
    if not request.user.is_authenticated:
        return HttpResponseForbidden()

    directory = get_object_or_404(DataDirectory, pk=id)

    if directory.dataset_id != dataset_id:
        return Http404("No Data Directory matches the given query")

    directory.delete()
    return JsonResponse({})


def dt_instruments(request):
    if not request.user.is_authenticated:
        return HttpResponseForbidden()

    instruments = list(Instrument.objects.all().values_list("number", "nickname", "id"))

    return JsonResponse({
        "data": instruments
    })


@login_required
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


def dt_tags(request):
    if not request.user.is_authenticated:
        return HttpResponseForbidden()

    tags = Tag.objects.all() \
        .annotate(bin_count=Count("tagevent__bin", distinct=True)) \
        .values("name", "id", "bin_count")

    return JsonResponse({
        "data": list(tags)
    })


@login_required
def edit_tag(request, id):
    tag = get_object_or_404(Tag, pk=id) if int(id) > 0 else Tag()

    if request.POST:
        form = TagForm(request.POST, instance=tag)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.save()

            return redirect(reverse("secure:tag-management"))
    else:
        form = TagForm(instance=tag)

    return render(request, "secure/edit-tag.html", {
        "tag": tag,
        "form": form,
    })


@login_required
def merge_tag(request, id):
    tag = get_object_or_404(Tag, pk=id) if int(id) > 0 else Tag()

    if request.POST:
        form = MergeTagForm(request.POST, instance=tag)
        if form.is_valid():
            target = form.cleaned_data.get("target")
            dataset = form.cleaned_data.get("dataset")

            # Locate matching tag events
            tag_events = TagEvent.query(tag=tag, dataset=dataset)

            # Get the list of bins already assigned to the target tag to prevent creating duplicates
            assigned_bins = TagEvent.query(tag=target, dataset=dataset).values("bin")

            # Update the tag on any records not already assigned to the target tag
            tag_events.exclude(bin__in=assigned_bins).update(tag=target)

            # Remove any records already assigned to the target tag
            tag_events.filter(bin__in=assigned_bins).delete()

            # If the tag is no longer in use on any bins, remove it
            if TagEvent.objects.filter(tag=tag).count() == 0:
                tag.delete()

            return redirect(reverse("secure:tag-management"))
    else:
        form = MergeTagForm(instance=tag)

    return render(request, "secure/merge-tag.html", {
        "tag": tag,
        "form": form,
    })

@login_required
def merge_tag_affected_bins(request, id):
    tag = get_object_or_404(Tag, pk=id)

    dataset_id = request.POST.get("dataset")
    dataset = Dataset.objects.get(pk=dataset_id) if dataset_id else None

    total = TagEvent \
        .query(tag=tag, dataset=dataset) \
        .values("bin_id") \
        .distinct() \
        .count()

    return JsonResponse({
        "total": total,
    })


@require_POST
def delete_tag(request, id):
    if not request.user.is_authenticated:
        return HttpResponseForbidden()

    tag = get_object_or_404(Tag, pk=id)
    tag.delete()

    return JsonResponse({})


@login_required
def app_settings(request):
    instance = AppSettings.objects.first() or AppSettings()
    confirm = False

    if request.POST:
        form = AppSettingsForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            confirm = True
    else:
        form = AppSettingsForm(instance=instance)

    return render(request, "secure/app-settings.html", {
        "form": form,
        "confirm": confirm,
    })


@require_POST
def add_tag(request, bin_id):
    if not request.user.is_authenticated:
        return HttpResponseForbidden()

    tag_name = request.POST.get("tag_name", "")
    bin = get_object_or_404(Bin, pid=bin_id)
    bin.add_tag(tag_name, user=request.user)

    return JsonResponse({
        "tags": bin.tag_names,
    })


@require_POST
def remove_tag(request, bin_id):
    if not request.user.is_authenticated:
        return HttpResponseForbidden()

    tag_name = request.POST.get("tag_name", "")
    bin = get_object_or_404(Bin, pid=bin_id)
    bin.delete_tag(tag_name)

    return JsonResponse({
        "tags": bin.tag_names,
    })


@require_POST
def add_comment(request, bin_id):
    if not request.user.is_authenticated:
        return HttpResponseForbidden()

    text = request.POST.get("comment")
    bin = get_object_or_404(Bin, pid=bin_id)
    bin.add_comment(text, request.user)

    return JsonResponse({
        "comments": bin.comment_list,
    })

@require_GET
def edit_comment(request, bin_id):
    if not request.user.is_staff:
        return HttpResponseForbidden()

    comment_id = request.GET.get("id")
    comment = get_object_or_404(Comment, pk=comment_id)

    return JsonResponse({
        "id": comment.id,
        "content": comment.content
    })


@require_POST
def update_comment(request, bin_id):
    if not request.user.is_staff:
        return HttpResponseForbidden()

    bin = get_object_or_404(Bin, pid=bin_id)

    comment_id = request.POST.get("id")
    content = request.POST.get("content")
    comment = get_object_or_404(Comment, pk=comment_id)

    comment.content = content
    comment.save()

    return JsonResponse({
        "id": comment.id,
        "comments": bin.comment_list,
    })


@require_POST
def delete_comment(request, bin_id):
    if not request.user.is_staff:
        return HttpResponseForbidden()

    comment_id = request.POST.get("id")
    _ = get_object_or_404(Comment, pk=comment_id)

    bin = get_object_or_404(Bin, pid=bin_id)
    bin.delete_comment(comment_id, request.user)

    return JsonResponse({
        "comments": bin.comment_list,
    })

# dataset syncing
def dataset_sync_lock_key(dataset_id):
    return 'dataset_sync_{}'.format(dataset_id)

def dataset_sync_cancel_key(dataset_id):
    return 'dataset_sync_cancel_{}'.format(dataset_id)

def dataset_sync_task_id_key(dataset_id):
    return 'dataset_sync_task_{}'.format(dataset_id)

def get_dataset_sync_task_id(dataset_id):
    return cache.get(dataset_sync_task_id_key(dataset_id))
    # if there's no task ID the task is just about to start

@require_POST
def sync_dataset(request, dataset_id):
    if not request.user.is_authenticated:
        return HttpResponseForbidden()

    from dashboard.tasks import sync_dataset
    # params
    newest_only = request.POST.get('newest_only') == 'true'
    # ensure that the dataset exists
    ds = get_object_or_404(Dataset, id=dataset_id)
    # attempt to lock the dataset
    lock_key = dataset_sync_lock_key(dataset_id)
    added = cache.add(lock_key, True, timeout=None) # this is atomic
    if not added: # dataset is locked for syncing
        return JsonResponse({ 'state': 'LOCKED' })
    # start the task asynchronously
    cancel_key = dataset_sync_cancel_key(dataset_id)
    r = sync_dataset.delay(dataset_id, lock_key, cancel_key, newest_only=newest_only)
    # cache the task id so we can look it up by dataset id
    cache.set(dataset_sync_task_id_key(dataset_id), r.task_id, timeout=None)
    result = AsyncResult(r.task_id)
    return JsonResponse({ 'state': result.state })

def sync_dataset_status(request, dataset_id):
    if not request.user.is_authenticated:
        return HttpResponseForbidden()

    task_id = get_dataset_sync_task_id(dataset_id)
    if task_id is None:
        # there's no result, which means either
        # - the cache entry for the task id has expired, or
        # - it's the exact moment the task is starting
        # report PENDING
        return JsonResponse({ 'state': 'PENDING' })
    result = AsyncResult(task_id)
    return JsonResponse({
        'state': result.state,
        'info': result.info,
        })

@require_POST
def sync_cancel(request, dataset_id):
    if not request.user.is_authenticated:
        return HttpResponseForbidden()

    cancel_key = dataset_sync_cancel_key(dataset_id)
    added = cache.add(cancel_key,"cancel")
    if not added:
        return JsonResponse({ 'status': 'already_canceled'})
    else:
        return JsonResponse({ 'status': 'cancelling' })

METADATA_UPLOAD_LOCK_KEY = 'metadata_upload_lock'
METADATA_UPLOAD_CANCEL_KEY = 'metadata_upload_cancel'
METADATA_UPLOAD_TASKID_KEY = 'metadata_upload_task_id'

@login_required
def upload_metadata(request):
    from dashboard.tasks import import_metadata

    in_progress = ''

    if request.method == "POST":
        confirm = ""
        form = MetadataUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES['file']

            try:
                df = pd.read_csv(file)
                json_df = df.to_json()
            except:
                form.add_error(None, "CSV syntax error")
                return render(request, 'secure/upload-metadata.html', {
                    'form': form,
                    'confirm': '',
                    'in_progress': '',
                    })

            added = cache.add(METADATA_UPLOAD_LOCK_KEY, True, timeout=None) # this is atomic
            if added:
                r = import_metadata.delay(json_df, METADATA_UPLOAD_LOCK_KEY, METADATA_UPLOAD_CANCEL_KEY)
                cache.set(METADATA_UPLOAD_TASKID_KEY, r.task_id, timeout=None)
                return redirect(reverse("secure:upload-metadata") + "?confirm=true")
            else:
                form.add_error(None, "Upload already in progress, please wait")
                in_progress = 'true'

    else:
        if cache.get(METADATA_UPLOAD_LOCK_KEY) is not None:
            in_progress = 'true'
        confirm = request.GET.get("confirm")
        form = MetadataUploadForm()

    return render(request, 'secure/upload-metadata.html', {
        "form": form,
        "confirm": confirm,
        'in_progress': in_progress,
    })

def metadata_upload_status(request):
    if not request.user.is_authenticated:
        return HttpResponseForbidden()

    task_id = cache.get(METADATA_UPLOAD_TASKID_KEY)
    if task_id is None:
        return JsonResponse({ 'state': 'PENDING' })
    result = AsyncResult(task_id)
    info = getattr(result, 'info', '')
    return JsonResponse({
        'state': result.state,
        'info': info,
        })

@require_POST
def metadata_upload_cancel(request):
    if not request.user.is_authenticated:
        return HttpResponseForbidden()

    added = cache.add(METADATA_UPLOAD_CANCEL_KEY, "cancel");
    if not added:
        return JsonResponse({ 'status': 'already_canceled'})
    else:
        return JsonResponse({ 'status': 'cancelling' })

@require_POST
def toggle_skip(request):
    if not request.user.is_authenticated:
        return HttpResponseForbidden()

    bin_id = request.POST.get("bin_id")
    skipped = request.POST.get("skipped") == "true"

    bin = get_object_or_404(Bin, pid=bin_id)
    bin.skip = not skipped
    bin.save()

    return JsonResponse({
        "bin_id": bin_id,
        "skipped": not skipped,
    })
