import re, os
from django import forms
from django.contrib.auth.models import User, Group

from dashboard.models import Bin, Dataset, Instrument, DataDirectory, AppSettings, Team, TeamUser, TeamDataset, Tag, \
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
    team = forms.ModelChoiceField(queryset=Team.objects.all(), required=False,
                                  widget=forms.Select(attrs={"class": "form-control form-control-sm"}))

    class Meta:
        model = Dataset
        fields = [
            "id", "name", "title", "doi", "attribution", "funding", "is_active", "depth",
            "contact_name", "contact_email", "description",
        ]

        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Name"}),
            "title": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Title"}),
            "doi": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": ""}),
            "attribution": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": ""}),
            "funding": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": ""}),
            "depth": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Depth"}),
            "is_active": forms.CheckboxInput(attrs={"class": "custom-control-input"}),
            "contact_name": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Contact Name"}),
            "contact_email": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Contact Email"}),
            "description": forms.Textarea(attrs={"class": "form-control form-control-sm", "placeholder": "Description"}),
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

            team_dataset = TeamDataset.objects.filter(dataset=instance).first()
            if team_dataset is not None:
                self.fields["team"].initial = team_dataset.team

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["email"].required = True

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
        fields = ["id", "first_name", "last_name", "email", "is_superuser",]

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
    assigned_users_json = forms.CharField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # New teams, which can only be created by a superadmin, can use any dataset that is not already associated with
        #   another team. On edits, the only allowed values are those already assigned to this team
        if self.instance.pk:
            dataset_choices = Dataset.objects.filter(teamdataset__team=self.instance)
        else:
            dataset_choices = Dataset.objects.filter(teamdataset__isnull=True)

        self.fields["default_dataset"].queryset = dataset_choices

    def clean_name(self):
        name = self.cleaned_data.get("name")

        team = Team.objects.filter(name__iexact=name).exclude(id=self.instance.id)
        if team.exists():
            raise forms.ValidationError("This name is already in use.")

        return name

    class Meta:
        model = Team
        fields = ["id", "name", "default_dataset", ]

        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Name"}),
            "default_dataset": forms.Select(attrs={"class": "form-control form-control-sm"}),
        }


class SearchForm(forms.Form):
    class_list = "form-control form-control-sm filter-option"

    # TODO: Move these to a service call so they are not all inline in the class?
    # TODO: The bin related queries are rather heavy - maybe cache the values rather than looking through all bins?
    # TODO: Putting it here means its called once - needs to be called on page load
    team_options = Team.objects.all().order_by("name")
    dataset_options = Dataset.objects.filter(is_active=True).order_by("name")
    tag_options = Tag.objects.all().order_by("name")

    # TODO: These can likely be refactored
    bins = Bin.objects.all()

    instruments = list(bins.values_list("instrument__number", flat=True).order_by("instrument__number").distinct())
    instruments = [""] + [f"IFCB{instrument_number}" for instrument_number in instruments]
    instrument_options = list(zip(instruments, instruments))

    cruises = list(bins.exclude(cruise="").values_list("cruise", flat=True).order_by("cruise").distinct())
    cruises = [""] + cruises
    cruise_options = list(zip(cruises, cruises))

    sample_types = list(bins.exclude(sample_type="").values_list("sample_type", flat=True).order_by("sample_type").distinct())
    sample_types = [""] + sample_types
    sample_type_options = list(zip(sample_types, sample_types))

    team = forms.ModelChoiceField(queryset=team_options, empty_label=" ", widget=forms.Select(attrs={"class": class_list}))
    dataset = forms.ModelChoiceField(queryset=dataset_options, empty_label=" ", widget=forms.Select(attrs={"class": class_list}))
    tag = forms.ModelChoiceField(queryset=tag_options, empty_label=" ", widget=forms.Select(attrs={"class": class_list}))

    instrument = forms.ChoiceField(choices=instrument_options, widget=forms.Select(attrs={"class": class_list}))
    cruise = forms.ChoiceField(choices=cruise_options, widget=forms.Select(attrs={"class": class_list}))
    sample_type = forms.ChoiceField(choices=sample_type_options, widget=forms.Select(attrs={"class": class_list}))

    # TODO: Fields and UI are needed to allow users to add a list of excluded date ranges
    # TODO: Dropdowns currently only allow for one selection - this may need to be improved to select more than one

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)