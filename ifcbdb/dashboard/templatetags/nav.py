from django import template

from dashboard.models import Dataset, Instrument, Tag

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
    dataset = context["request"].GET.get("dataset")
    instrument = context["request"].GET.get("instrument")
    tags = context["request"].GET.get("tags")
    if tags and tags != "":
        tags = [tag.strip().lower() for tag in tags.split(",")]
    else:
        tags = []

    datasets_options = Dataset.objects.all()
    instruments_options = Instrument.objects.all()
    tag_options = Tag.objects.all()

    return {
        "dataset": dataset,
        "instrument": instrument,
        "tags": tags,
        "datasets_options": datasets_options,
        "instruments_options": instruments_options,
        "tag_options": tag_options,
    }
