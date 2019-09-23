from django import template
from django.shortcuts import reverse

from dashboard.models import Dataset, Instrument, Tag, bin_query
from dashboard.views import request_get_instrument, request_get_tags

register = template.Library()


@register.inclusion_tag('dashboard/_dataset_switcher.html')
def dataset_switcher():
    datasets = Dataset.objects.all()

    return {
        "datasets": datasets,
    }


@register.inclusion_tag("dashboard/_dataset-nav.html")
def dataset_nav():
    datasets = Dataset.objects.all()

    return {
        "datasets": datasets,
    }


@register.inclusion_tag("dashboard/_timeline-filters.html", takes_context=True)
def timeline_filters(context):
    return {
    }


@register.inclusion_tag("dashboard/_comments-nav.html", takes_context=True)
def comments_nav(context):
    dataset = context["request"].GET.get("dataset")
    instrument = context["request"].GET.get("instrument")
    tags = context["request"].GET.get("tags")

    parameters = []
    if dataset:
        parameters.append("dataset=" + dataset)
    if instrument:
        parameters.append("instrument=" + instrument)
    if tags:
        parameters.append("tags=" + tags)

    url = reverse("comment_page")
    if len(parameters) > 0:
        url += "?" + "&".join(parameters)

    return {
        "url": url,
    }
