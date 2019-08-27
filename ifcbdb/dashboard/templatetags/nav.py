from django import template

from dashboard.models import Dataset

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