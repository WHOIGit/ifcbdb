import re, os
from django import forms


class DatasetSearchForm(forms.Form):
    keyword = forms.CharField(required=False, max_length=255, widget=forms.TextInput(attrs={"class": "form-control"}))
    start_date = forms.DateField(required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    end_date = forms.DateField(required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    min_depth = forms.FloatField(required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    max_depth = forms.FloatField(required=False, widget=forms.TextInput(attrs={"class": "form-control"}))

    class Meta:
        pass
