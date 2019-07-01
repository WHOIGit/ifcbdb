from django import forms

from dashboard.models import Dataset


class DatasetForm(forms.ModelForm):
    class Meta:
        model = Dataset
        fields = ["id", "name", "title", ]

        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Name"}),
            "title": forms.Textarea(attrs={"class": "form-control form-control-sm", "placeholder": "Description", "rows": 3})
        }

