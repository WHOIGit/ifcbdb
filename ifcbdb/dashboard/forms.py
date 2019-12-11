import re, os
from django import forms

from dashboard.models import Dataset


class DatasetSearchForm(forms.Form):
    start_date = forms.DateField(required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    end_date = forms.DateField(required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    min_depth = forms.FloatField(required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    max_depth = forms.FloatField(required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    region_sw_lat = forms.FloatField(required=False,
                                     widget=forms.TextInput(attrs={"class": "form-control", "readonly": "readonly"}))
    region_sw_lon = forms.FloatField(required=False,
                                     widget=forms.TextInput(attrs={"class": "form-control", "readonly": "readonly"}))
    region_ne_lat = forms.FloatField(required=False,
                                     widget=forms.TextInput(attrs={"class": "form-control", "readonly": "readonly"}))
    region_ne_lon = forms.FloatField(required=False,
                                     widget=forms.TextInput(attrs={"class": "form-control", "readonly": "readonly"}))
    dataset = forms.ModelChoiceField(required=False, empty_label="",
                                     queryset=Dataset.objects.filter(is_active=True),
                                     widget=forms.Select(attrs={"class": "form-control"}))

    class Meta:
        pass
