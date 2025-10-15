import json
from io import BytesIO
from itertools import groupby
from operator import attrgetter
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django import forms
from django.views.decorators.http import require_POST, require_GET
from django.http import JsonResponse, Http404, HttpResponseForbidden, HttpResponse, StreamingHttpResponse
from django.shortcuts import render, get_object_or_404, redirect, reverse
from django.contrib.auth.models import User, Group

import pandas as pd

from dashboard.models import Dataset, Instrument, DataDirectory, Tag, TagEvent, Bin, Comment, AppSettings, Team, \
    TeamUser, TeamDataset, TeamRole, bin_query
from dashboard.accession import export_metadata
from .forms import DatasetForm, InstrumentForm, DirectoryForm, MetadataUploadForm, AppSettingsForm, UserForm, \
    TeamForm, BinSearchForm, BinActionForm
from common import auth
from common.constants import Features, TeamRoles, BinManagementActions

from django.core.cache import cache
from celery.result import AsyncResult
from waffle.decorators import waffle_switch



@login_required
def index(request):
    if not auth.can_access_settings(request.user):
        return redirect("/")

    can_manage_teams = auth.can_manage_teams(request.user)
    can_manage_datasets = auth.can_manage_datasets(request.user)
    has_settings_to_manage = request.user.is_superuser or can_manage_teams or can_manage_datasets

    return render(request, 'secure/index.html', {
        "has_settings_to_manage": has_settings_to_manage,
        "can_manage_teams": can_manage_teams,
        "can_manage_datasets": can_manage_datasets,
    })


@login_required
def dataset_management(request):
    if not auth.can_manage_datasets(request.user):
        return redirect(reverse("secure:index"))

    form = DatasetForm(user=request.user)

    return render(request, 'secure/dataset-management.html', {
        "form": form,
    })


@login_required
def directory_management(request, dataset_id):
    if not auth.is_admin(request.user):
        return redirect(reverse("secure:index"))

    dataset = get_object_or_404(Dataset, pk=dataset_id)

    return render(request, "secure/directory-management.html", {
        "dataset": dataset,
    })


@login_required
def instrument_management(request):
    if not auth.is_admin(request.user):
        return redirect(reverse("secure:index"))

    form = InstrumentForm()

    return render(request, 'secure/instrument-management.html', {
        "form": form,
    })


@login_required
def user_management(request):
    if not auth.is_admin(request.user):
        return redirect(reverse("secure:index"))

    return render(request, 'secure/user-management.html')

@login_required
@waffle_switch('Teams')
def team_management(request):
    if not auth.can_manage_teams(request.user):
        return redirect(reverse("secure:index"))

    return render(request, 'secure/team-management.html', {
        "is_admin": auth.is_admin(request.user),
    })

@login_required
def dt_datasets(request):
    if not auth.can_manage_datasets(request.user):
        return HttpResponseForbidden()

    datasets = Dataset.objects.all()

    if not request.user.is_superuser:
        # TODO: This could be reused elsewhere
        allowed_team_ids = TeamUser.objects \
            .filter(user=request.user) \
            .filter(role_id=TeamRoles.CAPTAIN.value) \
            .values_list("team_id", flat=True)

        # TODO: Check this, but there should always be at least one, or the user wouldn't have been allowed here already
        team_datasets_ids = TeamDataset.objects \
            .filter(team_id__in=allowed_team_ids) \
            .values_list("dataset_id", flat=True)

        datasets = datasets.filter(id__in=team_datasets_ids)

    return JsonResponse({
        "data": list(datasets.values_list("name", "title", "is_active", "id"))
    })

@waffle_switch('Teams')
def dt_teams(request):
    if not auth.can_manage_teams(request.user):
        return redirect(reverse("secure:index"))

    teams = Team.objects.all() \
        .annotate(user_count=Count("users", distinct=True)) \
        .annotate(dataset_count=Count("datasets", distinct=True))

    # Limit teams list if not a super user
    if not auth.is_admin(request.user):
        allowed_team_ids = TeamUser.objects \
            .filter(user=request.user) \
            .filter(role_id=TeamRoles.CAPTAIN.value) \
            .values_list("team_id", flat=True)

        teams = teams.filter(id__in=allowed_team_ids)

    return JsonResponse({
        "data": [
            {
                "id": team.id,
                "name": team.name,
                "user_count": team.user_count,
                "dataset_count": team.dataset_count,
            }
            for team in teams
        ]
    })

@login_required
def dt_directories(request, dataset_id):
    if not auth.is_admin(request.user):
        return HttpResponseForbidden()

    directories = list(DataDirectory.objects.filter(dataset__id=dataset_id)
                       .values_list("path", "kind", "priority", "whitelist", "blacklist", "id"))

    return JsonResponse({
        "data": directories,
    })


@login_required
def edit_dataset(request, id):
    if not auth.can_manage_datasets(request.user):
        return redirect(reverse("secure:index"))

    status = request.GET.get("status")
    dataset = get_object_or_404(Dataset, pk=id) if int(id) > 0 else Dataset()
    is_new = dataset.pk is None

    # Non-superadmins (essentially team captains) can only manage their own teams' datasets. They can create new
    #   datasets, so this check is only needed for existing datasets
    if not auth.is_admin(request.user) and not is_new:
        team_dataset = TeamDataset.objects.filter(dataset=dataset).first()
        if not team_dataset:
            return redirect(reverse("secure:dataset-management"))

        is_team_captain = TeamUser.objects \
            .filter(team=team_dataset.team) \
            .filter(user=request.user) \
            .filter(role_id=TeamRoles.CAPTAIN.value) \
            .exists()
        if not is_team_captain:
            return redirect(reverse("secure:dataset-management"))

    if request.POST:
        form = DatasetForm(request.POST, instance=dataset, user=request.user)
        if form.is_valid():
            instance = form.save()

            existing = TeamDataset.objects.filter(dataset_id=dataset.id).first()
            team = form.cleaned_data.get("team")

            original_team = existing.team if existing else None
            is_team_removed = False

            # Save the associated team, if any
            if team is None and existing is not None:
                is_team_removed = True
                existing.delete()

            if team is not None and existing is None:
                TeamDataset.objects.create(team=team, dataset=instance)

            if team is not None and existing is not None and existing.team != team:
                is_team_removed = True
                existing.team = team
                existing.save()

            # If a team was removed (or changed to something else) but it was the default dataset for that team,
            #   clear the value
            if is_team_removed and original_team is not None and original_team.default_dataset == instance:
                original_team.default_dataset = None
                original_team.save()

            status = "created" if id == 0 else "updated"
            return redirect(reverse("secure:edit-dataset", kwargs={"id": instance.id}) + "?status=" + status)
    else:
        form = DatasetForm(instance=dataset, user=request.user)

    return render(request, "secure/edit-dataset.html", {
        "status": status,
        "form": form,
        "dataset": dataset,
    })


@login_required
def edit_directory(request, dataset_id, id):
    if not auth.is_admin(request.user):
        return redirect(reverse("secure:index"))

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
    if not auth.is_admin(request.user):
        return HttpResponseForbidden()

    directory = get_object_or_404(DataDirectory, pk=id)

    if directory.dataset_id != dataset_id:
        return Http404("No Data Directory matches the given query")

    directory.delete()
    return JsonResponse({})


def dt_instruments(request):
    if not auth.is_admin(request.user):
        return HttpResponseForbidden()

    instruments = list(Instrument.objects.all().values_list("number", "nickname", "id"))

    return JsonResponse({
        "data": instruments
    })


def dt_users(request):
    if not auth.is_admin(request.user):
        return HttpResponseForbidden()

    users = User.objects.filter(is_active=True)

    return JsonResponse({
        "data": [
            {
                "id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
            }
            for user in users
        ]
    })


@login_required
def edit_instrument(request, id):
    if not auth.is_admin(request.user):
        return redirect(reverse("secure:index"))

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


@login_required
def edit_user(request, id):
    if not auth.is_admin(request.user):
        return redirect(reverse("secure:index"))

    user = get_object_or_404(User, pk=id) if int(id) > 0 else User()

    if request.POST:
        form = UserForm(request.POST, instance=user)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.username = form.cleaned_data["email"]

            password = form.cleaned_data["password"]
            if password:
                instance.set_password(password)

            instance.save()

            return redirect(reverse("secure:user-management"))
    else:
        form = UserForm(instance=user)

    return render(request, "secure/edit-user.html", {
        "user": user,
        "form": form,
    })

@login_required
def edit_team(request, id):
    if not auth.can_manage_teams(request.user):
        return redirect(reverse("secure:index"))

    team = get_object_or_404(Team, pk=id) if int(id) > 0 else Team()
    is_new = team.pk is None

    # Non-superadmins (essentially team captains) can only manage their own teams
    if not auth.is_admin(request.user):
        is_team_captain = TeamUser.objects \
            .filter(team=team) \
            .filter(user=request.user) \
            .filter(role_id=TeamRoles.CAPTAIN.value) \
            .exists()
        if not is_team_captain:
            return redirect(reverse("secure:team-management"))

    if request.POST:
        form = TeamForm(request.POST, instance=team)
        if form.is_valid():
            instance = form.save()

            # If this is a new team, and a default dataset is selected, make sure to associate it with
            #  the team. The only allowed values for team should already be datasets not already associated
            #  with any other team
            if is_new and instance.default_dataset is not None:
                # Datasets can only be associated with a single dataset right now, even though it's a many-to-many
                #   relationship that could support more. Because of this, make sure that the dataset selected is
                #   not already associated with another team
                if not TeamDataset.objects.filter(dataset=instance.default_dataset).exists():
                    TeamDataset.objects.create(team=instance, dataset=instance.default_dataset)

            assigned_users_json = form.cleaned_data.get("assigned_users_json")
            assigned_users = json.loads(assigned_users_json)

            # Go through the list of assigned users, updating those that already exist or adding new records for
            #   any additions
            for assigned_user in assigned_users:
                user_id = assigned_user.get("id")
                role_id = assigned_user.get("role_id")

                existing_user = TeamUser.objects.filter(team=instance, user_id=user_id).first()
                if existing_user:
                    existing_user.role_id = role_id
                    existing_user.save()
                    continue

                new_user = TeamUser()
                new_user.team = instance
                new_user.user_id = user_id
                new_user.role_id = role_id
                new_user.save()

            assigned_user_ids = [assigned_user.get("id") for assigned_user in assigned_users]

            # Remove any user relationships that have been unassigned
            TeamUser.objects.filter(team=instance).exclude(user_id__in=assigned_user_ids).delete()

            return redirect(reverse("secure:team-management"))
    else:
        form = TeamForm(instance=team)

    team_users = TeamUser.objects \
        .filter(team=team) \
        .select_related("user") \
        .order_by("user__last_name", "user__first_name", "user__username")

    all_users = User.objects \
        .filter(is_active=True) \
        .order_by('last_name', 'first_name', 'username')
    assigned_users_json = json.dumps([
        {
            "id": user.user.id,
            "name": user.display_name,
            "role_id": user.role.id,
            "role": user.role.name,
        }
        for user in team_users
    ])

    role_options = TeamRole.objects.all()

    assigned_team_datasets = TeamDataset.objects \
        .select_related("dataset") \
        .filter(team=team).order_by("dataset__name") \
        .order_by("dataset__name")
    assigned_datasets_json = json.dumps([
        {
            "name": team_dataset.dataset.name
        }
        for team_dataset in assigned_team_datasets
    ])

    return render(request, "secure/edit-team.html", {
        "team": team,
        "form": form,
        "is_admin": auth.is_admin(request.user),
        "all_users": all_users,
        "assigned_users_json": assigned_users_json,
        "role_options": role_options,
        "assigned_datasets_json": assigned_datasets_json,
    })


@require_POST
def delete_user(request, id):
    if not auth.is_admin(request.user):
        return HttpResponseForbidden()

    user = get_object_or_404(User, pk=id)
    user.is_active = False
    user.save()

    return JsonResponse({})

@require_POST
def delete_team(request, id):
    if not auth.is_admin(request.user):
        return HttpResponseForbidden()

    team = get_object_or_404(Team, pk=id)
    team.delete()

    return JsonResponse({})



@login_required
def app_settings(request):
    if not auth.is_admin(request.user):
        return redirect(reverse("secure:index"))

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
    if not auth.is_admin(request.user):
        return HttpResponseForbidden()

    tag_name = request.POST.get("tag_name", "")
    bin = get_object_or_404(Bin, pid=bin_id)
    bin.add_tag(tag_name, user=request.user)

    return JsonResponse({
        "tags": bin.tag_names,
    })


@require_POST
def remove_tag(request, bin_id):
    if not auth.is_admin(request.user):
        return HttpResponseForbidden()

    tag_name = request.POST.get("tag_name", "")
    bin = get_object_or_404(Bin, pid=bin_id)
    bin.delete_tag(tag_name)

    return JsonResponse({
        "tags": bin.tag_names,
    })


@require_POST
def add_comment(request, bin_id):
    if not auth.is_admin(request.user):
        return HttpResponseForbidden()

    # TODO: Unlike editing a comment, this was allow for authenticated users, not just staff?

    text = request.POST.get("comment")
    bin = get_object_or_404(Bin, pid=bin_id)
    bin.add_comment(text, request.user)

    return JsonResponse({
        "comments": bin.comment_list,
    })

@require_GET
def edit_comment(request, bin_id):
    if not auth.is_admin(request.user):
        return HttpResponseForbidden()

    # TODO: Prior logic used the staff flag to determine if this was editable - do we need a different level than admin?
    # TODO: Editing tags was open to non-staff. Is that still accurate?
    # if not request.user.is_staff:
    #     return HttpResponseForbidden()

    comment_id = request.GET.get("id")
    comment = get_object_or_404(Comment, pk=comment_id)

    return JsonResponse({
        "id": comment.id,
        "content": comment.content
    })


@require_POST
def update_comment(request, bin_id):
    if not auth.is_admin(request.user):
        return HttpResponseForbidden()

    # TODO: Prior logic used the staff flag to determine if this was editable - do we need a different level than admin?
    # if not request.user.is_staff:
    #     return HttpResponseForbidden()

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
    if not auth.is_admin(request.user):
        return HttpResponseForbidden()

    # TODO: Prior logic used the staff flag to determine if this was editable - do we need a different level than admin?
    # if not request.user.is_staff:
    #     return HttpResponseForbidden()

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
    if not auth.is_admin(request.user):
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
    if not auth.is_admin(request.user):
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
    if not auth.is_admin(request.user):
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
    if not auth.is_admin(request.user):
        return redirect(reverse("secure:index"))

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
    if not auth.is_admin(request.user):
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
    if not auth.is_admin(request.user):
        return HttpResponseForbidden()

    added = cache.add(METADATA_UPLOAD_CANCEL_KEY, "cancel")
    if not added:
        return JsonResponse({ 'status': 'already_canceled'})
    else:
        return JsonResponse({ 'status': 'cancelling' })

@require_POST
def toggle_skip(request):
    if not auth.is_admin(request.user):
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

@login_required
def bin_management(request):
    # TODO: Allow support for captains and managers to view/manage bins
    if not auth.is_admin(request.user):
        return redirect(reverse("secure:index"))

    form = BinSearchForm()

    # This is not ideal, but loading the action form initially means we can use the assigned/unassigned datasets
    #  elements and pre-render them before a search is run
    action_form = BinActionForm()

    return render(request, 'secure/bin-management.html', {
        "form": form,
        "action_form": action_form,
    })


@login_required
@require_POST
def bin_management_search(request):
    # TODO: Allow support for captains and managers to view/manage bins
    if not auth.is_admin(request.user):
        return redirect(reverse("secure:index"))

    form = BinSearchForm(request.POST)
    if not form.is_valid():
        return JsonResponse({
            "success": False,
            "errors": form.errors,
        })

    bin_qs = build_bin_query_from_form_data(form)
    total = bin_qs.count()

    return JsonResponse({
        "success": True,
        "total": total,
    })

@login_required
def bin_management_export(request, dataset_name=None):
    # TODO: Allow support for captains and managers to view/manage bins
    if not auth.is_admin(request.user):
        return redirect(reverse("secure:index"))

    form = BinSearchForm(request.GET)
    if not form.is_valid():
        # TODO: DO something? is_valid must be called or cleaned_data never gets populated
        pass

    # TODO: Export button uses the form data...technically the user could change those values between the search and the update
    # TODO: Disable fields and a search again option maybe?

    bin_qs = build_bin_query_from_form_data(form)

    # TODO: We're not supplying a dataset name. The benefit of that would be defaulting the location and depth values
    #   in the export. Not sure if that is good here since the goal of this export is partially to re-import?
    df = export_metadata(None, bin_qs)

    filename = 'bins.csv'

    csv_buf = BytesIO()
    df.to_csv(csv_buf, mode='wb', index=None)
    csv_buf.seek(0)

    response = StreamingHttpResponse(csv_buf, content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename={filename}'

    return response

@login_required
@require_POST
def bin_management_execute(request):
    # TODO: Allow support for captains and managers to view/manage bins
    if not auth.is_admin(request.user):
        return redirect(reverse("secure:index"))

    form = BinSearchForm(request.POST)
    if not form.is_valid():
        # TODO: For now, this should always since there aren't any actual form validators on the search. Later, this
        #     :   form will likely go away for the execute action to ensure that the user cannot change search criteria
        #     :   prior to clicking execute (without being intentional about it. But is_valid() must be called for the
        #     :   values to appear in cleaned_data
        pass

    action_form = BinActionForm(request.POST)
    if not action_form.is_valid():
        return JsonResponse({
            "success": False,
            "errors": action_form.errors,
        })

    action = action_form.cleaned_data.get("action")

    # TODO: Export button uses the form data...technically the user could change those values between the search and the update
    #     : Disable fields and a search again option maybe?

    bin_qs = build_bin_query_from_form_data(form)

    if action == BinManagementActions.SKIP_BINS.value:
        return update_skip(bin_qs, True)

    if action == BinManagementActions.UNSKIP_BINS.value:
        return update_skip(bin_qs, False)

    if action == BinManagementActions.ASSIGN_DATASET.value:
        return assign_dataset(bin_qs, action_form.cleaned_data.get("assigned_dataset"))

    if action == BinManagementActions.UNASSIGN_DATASET.value:
        return unassign_dataset(bin_qs, action_form.cleaned_data.get("unassigned_dataset"))

    return JsonResponse({
        "success": False,
        "message": f"Please choose an action to perform",
    })

def build_bin_query_from_form_data(form):
    dataset = form.cleaned_data.get("dataset")
    team = form.cleaned_data.get("team")
    start_date = form.cleaned_data.get("start_date")
    end_date = form.cleaned_data.get("end_date")
    instrument = form.cleaned_data.get("instrument")
    cruise = form.cleaned_data.get("cruise")
    sample_type = form.cleaned_data.get("sample_type")
    tag = form.cleaned_data.get("tag")
    tags = [tag.name] if tag else []

    bin_qs = bin_query(
        filter_skip=False,
        dataset_name=dataset.name if dataset is not None else None,
        instrument_number=request_get_instrument(instrument),
        tags=tags,
        cruise=cruise,
        sample_type=sample_type,
        team_name=team.name if team is not None else None)

    # TODO: This logic is borrowed from the nav filtering logic. There are parameters in bin_query that allow for a
    #     :   start and end date, but it does not work the same. The code below adds a day to the end date and that
    #     :   means a search fora single date will work, whereas it won't with the bin_query parameters. We should
    #     :   check to make sure this isn't actually a bug with one of the methods
    if start_date:
        start_date = pd.to_datetime(start_date, utc=True)
        bin_qs = bin_qs.filter(sample_time__gte=start_date)

    if end_date:
        end_date = pd.to_datetime(end_date, utc=True) + pd.Timedelta('1d')
        bin_qs = bin_qs.filter(sample_time__lte=end_date)

    return bin_qs

def update_skip(bin_qs, is_skipped):
    total = 0

    for bin in bin_qs:
        bin.skip = is_skipped
        bin.save()

        total += 1

    return JsonResponse({
        "success": True,
        "message": f"{total} bin(s) have been updated successfully",
    })

def assign_dataset(bin_qs, dataset):
    # This logic requires bin_qs to be a queryset, so at least one search option must have been specified
    num_already_assigned = dataset.bins.filter(id__in=bin_qs.values_list("id", flat=True)).count()

    dataset.bins.add(*bin_qs)

    total = bin_qs.count()
    num_assigned = total - num_already_assigned
    label_assigned = "bins" if num_assigned != 1 else "bin"
    label_already_assigned = "bins" if num_already_assigned != 1 else "bin"
    msg = f"{num_assigned} {label_assigned} assigned to dataset {dataset}"

    if num_already_assigned == 0:
        return JsonResponse({
            "success": True,
            "message": msg,
        })

    return JsonResponse({
        "success": True,
        "message": msg + f" ({num_already_assigned} {label_already_assigned} already assigned)",
    })

def unassign_dataset(bin_qs, dataset):
    # This logic requires bin_qs to be a queryset, so at least one search option must have been specified
    num_assigned = dataset.bins.filter(id__in=bin_qs.values_list("id", flat=True)).count()

    if num_assigned == 0:
        return JsonResponse({
            "success": True,
            "message": f"No bins were unassigned because there weren't any assigned to dataset {dataset}",
        })

    dataset.bins.remove(*bin_qs)

    label = "bins" if num_assigned != 1 else "bin"
    return JsonResponse({
        "success": True,
        "message": f"{num_assigned} {label} unassigned from dataset {dataset}",
    })


# TODO: This is duplicated in dashboard/views - make a common helper method
def request_get_instrument(instrument_string):
    i = instrument_string
    if i is not None and i:
        if i.lower().startswith('ifcb'):
            i = i[4:]
        return int(i)