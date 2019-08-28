from django import template

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
    dataset = context["request"].GET.get("dataset")
    instrument = request_get_instrument(context["request"].GET.get("instrument"))
    tags = request_get_tags(context["request"].GET.get("tags"))

    if dataset:
        ds = Dataset.objects.get(name=dataset)
    else:
        ds = None
    if instrument:
        instr = Instrument.objects.get(number=instrument)
    else:
        instr = None

    tag_options = Tag.list(ds, instr)

    bq = bin_query(dataset_name=dataset, tags=tags)
    qs = bq.values('instrument__number').order_by('instrument__number').distinct()
    instruments_options = [i['instrument__number'] for i in qs]

    datasets_options = Dataset.objects.order_by('name').all()

    return {
        "dataset": dataset,
        "instrument": instr.number if instr else None,
        "tags": tags,
        "datasets_options": datasets_options,
        "instruments_options": instruments_options,
        "tag_options": tag_options,
    }
