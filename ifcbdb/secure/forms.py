from django import forms

from dashboard.models import Dataset


class DatasetForm(forms.ModelForm):
    class Meta:
        model = Dataset
        fields = ["id", "name", "title", "is_active", ]

        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Name"}),
            "title": forms.Textarea(attrs={"class": "form-control form-control-sm", "placeholder": "Description", "rows": 3}),
            "is_active": forms.CheckboxInput(attrs={"class": "custom-control-input"})
        }

