from django import template
from django.shortcuts import reverse
import requests

from dashboard.models import Dataset, Instrument, Tag, bin_query

register = template.Library()


# TODO: Make into a common library/service?
class ApiService:
    @staticmethod
    def list_datasets():
        return requests.get('http://ifcbapi:8001/api/datasets/').json()



@register.inclusion_tag('dashboard/_dataset_switcher.html')
def dataset_switcher():
    datasets = Dataset.objects.all()

    return {
        "datasets": datasets,
    }


@register.inclusion_tag("dashboard/_dataset-nav.html")
def dataset_nav():
    return {
        'datasets': ApiService.list_datasets()
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
