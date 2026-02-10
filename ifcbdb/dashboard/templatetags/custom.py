from django import template

register = template.Library()

@register.filter
def first_line(value):
    if not value:
        return ''

    return value.split('\n')[0]