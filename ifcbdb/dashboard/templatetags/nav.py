import json
from django import template
from django.shortcuts import reverse
from django.utils.html import mark_safe

from dashboard.models import Dataset, Team, TeamDataset, Instrument, Tag, bin_query, AppSettings, \
    DEFAULT_LATITUDE, DEFAULT_LONGITUDE, DEFAULT_ZOOM_LEVEL
from common import auth

register = template.Library()

@register.simple_tag(takes_context=False)
def app_settings():
    app_settings = AppSettings.objects.first()

    settings = json.dumps({
        "default_latitude": app_settings.default_latitude if app_settings else DEFAULT_LATITUDE,
        "default_longitude": app_settings.default_longitude if app_settings else DEFAULT_LONGITUDE,
        "default_zoom_level": app_settings.default_zoom_level if app_settings else DEFAULT_ZOOM_LEVEL,
    })

    return mark_safe(settings)

@register.simple_tag(takes_context=False)
def can_access_settings(user):
    return auth.can_access_settings(user)

@register.inclusion_tag('dashboard/_dataset_switcher.html')
def dataset_switcher():
    datasets = Dataset.objects.all()

    return {
        "datasets": datasets,
    }


@register.inclusion_tag("dashboard/_dataset-nav.html", takes_context=True)
def dataset_nav(context):

    datasets = Dataset.objects.filter(is_active=True)
    teams = Team.objects.all().order_by("name")
    dataset_name = context['request'].GET.get("dataset")

    # If there is a dataset selected, pull the team off of it
    team = None
    if dataset_name:
        team_id = Dataset.objects.filter(name=dataset_name) \
            .prefetch_related("teamdataset_set__team") \
            .values_list("team", flat=True) \
            .first()
        team = Team.objects.filter(id=team_id).first() if team_id else None

    # TODO: Flag for teams feature
    is_teams_enabled = True

    # If teams are enabled and there is a team found, show datasets for that team
    if is_teams_enabled and team is not None:
        team_dataset_ids = TeamDataset.objects.filter(team=team).values_list("dataset_id", flat=True)
        datasets = datasets.filter(id__in=team_dataset_ids)

    # If teams are enabled and there is no team, show the default dataset of all teams
    if is_teams_enabled and team is None:
        default_dataset_ids = Team.objects.all().exclude(default_dataset=None).values_list("default_dataset_id", flat=True)
        datasets = datasets.filter(id__in=default_dataset_ids)

    return {
        "datasets": datasets,
        "teams": teams,
        "team": team,
    }


@register.inclusion_tag("dashboard/_timeline-filters.html", takes_context=True)
def timeline_filters(context):
    return {
}


@register.inclusion_tag("dashboard/_comments-nav.html", takes_context=True)
def comments_nav(context):
    
    if not 'request' in context: # specifically for 500 custom error page
        return reverse('comment_page')

    dataset = context["request"].GET.get("dataset")
    instrument = context["request"].GET.get("instrument")
    tags = context["request"].GET.get("tags")
    cruise = context["request"].GET.get("cruise")
    sample_type = context["request"].GET.get("sample_type")

    parameters = []
    if dataset:
        parameters.append("dataset=" + dataset)
    if instrument:
        parameters.append("instrument=" + instrument)
    if tags:
        parameters.append("tags=" + tags)
    if cruise:
        parameters.append("cruise=" + cruise)
    if sample_type:
        parameters.append("sample_type=" + sample_type)

    url = reverse("comment_page")
    if len(parameters) > 0:
        url += "?" + "&".join(parameters)

    return {
        "url": url,
    }
