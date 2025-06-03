import re, os
from django import forms
from django.contrib.auth.models import User, Group

from dashboard.models import Dataset, Instrument, DataDirectory, AppSettings, Team, TeamUser, \
    DEFAULT_LATITUDE, DEFAULT_LONGITUDE, DEFAULT_ZOOM_LEVEL


MIN_LATITUDE = -90
MAX_LATITUDE = 90
MIN_LONGITUDE = -180
MAX_LONGITUDE = 180

# Leaflet does not limit the zoom level, but appears to start having issues with very large numbers. Here, it's limited
#   to 13 because that appears to be the limit of the basemap that's being used. Any higher than that, and it produces
#   "map not available" errors
MIN_ZOOM_LEVEL = 0
MAX_ZOOM_LEVEL = 13


class DatasetForm(forms.ModelForm):
    latitude = forms.FloatField(required=False, widget=forms.TextInput(
        attrs={"class": "form-control form-control-sm", "placeholder": "Latitude"}
    ))
    longitude = forms.FloatField(required=False, widget=forms.TextInput(
        attrs={"class": "form-control form-control-sm", "placeholder": "Longitude"}
    ))

    class Meta:
        model = Dataset
        fields = ["id", "name", "title", "doi", "attribution", "funding", "is_active", "depth", ]

        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Name"}),
            "title": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Title"}),
            "doi": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": ""}),
            "attribution": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": ""}),
            "funding": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": ""}),
            "depth": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Depth"}),
            "is_active": forms.CheckboxInput(attrs={"class": "custom-control-input"})
        }

    def clean_doi(self):
        doi = self.cleaned_data['doi']

        if not doi or doi == "":
            return doi

        doi_regex = r'10\.[^ /]+/[^ ]+'

        if not re.match(doi_regex, doi):
            raise forms.ValidationError('invalid DOI format')

        return doi

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

    def __init__(self, *args, **kwargs):
        self.dataset_id = kwargs.pop("dataset_id", None)

        super().__init__(*args, **kwargs)

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

    def clean(self):
        data = self.cleaned_data
        path = self.cleaned_data.get("path")
        kind = self.cleaned_data.get("kind")

        # make sure the directory path is not already in the database
        existing_path = DataDirectory.objects.filter(dataset_id=self.dataset_id, path=path, kind=kind).first()
        if existing_path:
            raise forms.ValidationError({
                'path': 'Path "{}" (kind: {}) is already in use'.format(path, kind)
            })

        return data

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


class UserForm(forms.ModelForm):
    password = forms.CharField(max_length=50, required=False,
                               widget=forms.PasswordInput(attrs={"class": "form-control form-control-sm"}))
    confirm_password = forms.CharField(max_length=50, required=False,
                                       widget=forms.PasswordInput(attrs={"class": "form-control form-control-sm"}))
    role = forms.ChoiceField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["email"].required = True

        role_choices = [("", "")] + [
            (group.id, group.name)
            for group in Group.objects.all()
        ]

        group_id = self.instance.groups.first().id if self.instance.pk else None

        self.fields["role"] = forms.ChoiceField(
            required=True,
            choices=role_choices,
            widget=forms.Select(attrs={"class": "form-control form-control-sm"}),
            initial=group_id)


    def clean(self):
        password = self.cleaned_data.get("password")
        confirm_password = self.cleaned_data.get("confirm_password")

        if password != confirm_password:
            raise forms.ValidationError(
                "The password fields do not match"
            )

        return self.cleaned_data

    def clean_email(self):
        email = self.cleaned_data.get("email")

        users = User.objects.filter(email=email).exclude(id=self.instance.id)
        if users.exists():
            raise forms.ValidationError("This email address is already in use.")

        return email

    class Meta:
        model = User
        fields = ["id", "first_name", "last_name", "email", ]

        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "First Name"}),
            "last_name": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Last Name"}),
            "email": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Email"}),
        }


class MetadataUploadForm(forms.Form):
    file = forms.FileField(label="Choose file", widget=forms.ClearableFileInput(attrs={"class": "custom-file-input"}))


class AppSettingsForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["default_latitude"].required = True
        self.fields["default_longitude"].required = True
        self.fields["default_zoom_level"].required = True

    def clean_default_latitude(self):
        data = self.cleaned_data.get("default_latitude")

        if data < MIN_LATITUDE or data > MAX_LATITUDE:
            raise forms.ValidationError(f"Default Latitude must be between {MIN_LATITUDE} and {MAX_LATITUDE}")

        return data

    def clean_default_longitude(self):
        data = self.cleaned_data.get("default_longitude")

        if data < MIN_LONGITUDE or data > MAX_LONGITUDE:
            raise forms.ValidationError(f"Default Longitude must be between {MIN_LONGITUDE} and {MAX_LONGITUDE}")

        return data

    def clean_default_zoom_level(self):
        data = self.cleaned_data.get("default_zoom_level")

        if data < MIN_ZOOM_LEVEL or data > MAX_ZOOM_LEVEL:
            raise forms.ValidationError(f"Default Zoom Level must be between {MIN_ZOOM_LEVEL} and {MAX_ZOOM_LEVEL}")

        return data

    class Meta:
        model = AppSettings
        fields = ["default_latitude", "default_longitude", "default_zoom_level", ]
        widgets = {
            "default_latitude": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "default_longitude": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "default_zoom_level": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
        }


class TeamForm(forms.ModelForm):
    assigned_users = forms.ModelMultipleChoiceField(
        required=False,
        queryset=User.objects.none(),
        widget=forms.SelectMultiple(attrs={"class": "form-control form-control-sm", "size": "10"})
    )
    available_users = forms.ModelMultipleChoiceField(
        required=False,
        queryset=User.objects.none(),
        widget=forms.SelectMultiple(attrs={"class": "form-control form-control-sm", "size": "10"})
    )

    assigned_datasets = forms.ModelMultipleChoiceField(
        required=False,
        queryset=Dataset.objects.none(),
        widget=forms.SelectMultiple(attrs={"class": "form-control form-control-sm", "size": "10"})
    )
    available_datasets = forms.ModelMultipleChoiceField(
        required=False,
        queryset=Dataset.objects.none(),
        widget=forms.SelectMultiple(attrs={"class": "form-control form-control-sm", "size": "10"})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        users = User.objects.filter(is_active=True)

        if self.instance.pk:
            assigned_user_ids = list(TeamUser.objects.filter(team=self.instance).values_list("user_id", flat=True))

            self.fields["assigned_users"].queryset = users.filter(id__in=assigned_user_ids)
            self.fields["available_users"].queryset = users.exclude(id__in=assigned_user_ids)
        else:
            self.fields["available_users"].queryset = users

    # TODO: Make sure team name is unique

    class Meta:
        model = Team
        fields = ["id", "name", ]

        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Name"}),
        }
