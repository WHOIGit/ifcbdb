import re
from django import forms

from dashboard.models import Dataset, Instrument, DataDirectory


class DatasetForm(forms.ModelForm):
    class Meta:
        model = Dataset
        fields = ["id", "name", "title", "is_active", ]

        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Name"}),
            "title": forms.Textarea(attrs={"class": "form-control form-control-sm", "placeholder": "Description", "rows": 3}),
            "is_active": forms.CheckboxInput(attrs={"class": "custom-control-input"})
        }


class DirectoryForm(forms.ModelForm):

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
                    (DataDirectory.FEATURES, DataDirectory.FEATURES)
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
