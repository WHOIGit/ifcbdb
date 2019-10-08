import re, os
from django import forms

from dashboard.models import Dataset, Instrument, DataDirectory


class DatasetForm(forms.ModelForm):
    latitude = forms.FloatField(required=False, widget=forms.TextInput(
        attrs={"class": "form-control form-control-sm", "placeholder": "Latitude"}
    ))
    longitude = forms.FloatField(required=False, widget=forms.TextInput(
        attrs={"class": "form-control form-control-sm", "placeholder": "Longitude"}
    ))

    class Meta:
        model = Dataset
        fields = ["id", "name", "title", "is_active", "depth", ]

        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Name"}),
            "title": forms.Textarea(attrs={"class": "form-control form-control-sm", "placeholder": "Description", "rows": 3}),
            "depth": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Depth"}),
            "is_active": forms.CheckboxInput(attrs={"class": "custom-control-input"})
        }

    def __init__(self, *args, **kwargs):
        super(DatasetForm, self).__init__(*args, **kwargs)

        if "instance" in kwargs:
            instance = kwargs["instance"]
            if instance.location:
                self.fields["latitude"].initial = instance.location.y
                self.fields["longitude"].initial = instance.location.x

    def save(self, commit=True):
        instance = super(DatasetForm, self).save(commit=False)

        latitude = self.cleaned_data["latitude"]
        longitude = self.cleaned_data["longitude"]

        if latitude and longitude:
            instance.set_location(longitude, latitude)
        else:
            instance.location = None


        if commit:
            instance.save()
        return instance


class DirectoryForm(forms.ModelForm):

    def clean_path(self):
        path = self.cleaned_data["path"]

        if not os.path.exists(path):
            raise forms.ValidationError("The specified path does not exist")

        return path

    def clean_whitelist(self):
        whitelist = self.cleaned_data['whitelist']
        if not self._match_folder_names(whitelist):
            raise forms.ValidationError("Whitelist must be a comma separated list of names (not full paths)")

        # Return a list with each entried stripped of beginning/ending spaces
        return ",".join([name.strip() for name in whitelist.split(",")])

    def clean_blacklist(self):
        blacklist = self.cleaned_data['blacklist']

        if not self._match_folder_names(blacklist):
            raise forms.ValidationError("Blacklist must be a comma separated list of names (not full paths)")

        return ",".join([name.strip() for name in blacklist.split(",")])

    def _match_folder_names(self, value):
        return re.match(r'^[A-Za-z0-9,\s]*$', value)

    class Meta:
        model = DataDirectory
        fields = ["id", "path", "kind", "priority", "whitelist", "blacklist", "version", ]

        widgets = {
            "path": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Path"}),
            "kind": forms.Select(
                choices=[
                    (DataDirectory.RAW, DataDirectory.RAW),
                    (DataDirectory.BLOBS, DataDirectory.BLOBS),
                    (DataDirectory.FEATURES, DataDirectory.FEATURES),
                    (DataDirectory.CLASS_SCORES, DataDirectory.CLASS_SCORES),
                ],
                attrs={"class": "form-control form-control-sm", "placeholder": "Kind"}),
            "whitelist": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Whitelist"}),
            "blacklist": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Blacklist"}),
            "version": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Version"}),
            "priority": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Priority"}),
        }


class InstrumentForm(forms.ModelForm):
    password = forms.CharField(max_length=50, required=False,
                               widget=forms.PasswordInput(attrs={"class": "form-control form-control-sm"}))
    confirm_password = forms.CharField(max_length=50, required=False,
                                       widget=forms.PasswordInput(attrs={"class": "form-control form-control-sm"}))

    def clean(self):
        cleaned_data = super(InstrumentForm, self).clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password != confirm_password:
            raise forms.ValidationError(
                "The password fields do not match"
            )

    class Meta:
        model = Instrument
        fields = ["id", "number", "nickname", "address", "username", "share_name", "timeout", ]
        help_texts = {
            "timeout": "In seconds"
        }

        widgets = {
            "number": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Number"}),
            "nickname": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Nickname"}),
            "address": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Domain or IP Address"}),
            "username": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Username"}),
            "share_name": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Share Name"}),
            "timeout": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Timeout"}),
        }


class MetadataUploadForm(forms.Form):
    file = forms.FileField(label="Choose file", widget=forms.ClearableFileInput(attrs={"class": "custom-file-input"}))
