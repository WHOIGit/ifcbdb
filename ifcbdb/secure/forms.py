import re, os
from django import forms
from django.contrib.auth.models import User, Group
from django.core.exceptions import ValidationError
import waffle

from dashboard.models import Dataset, Instrument, DataDirectory, AppSettings, Tag, \
    Bin, Team, TeamUser, TeamDataset, \
    DEFAULT_LATITUDE, DEFAULT_LONGITUDE, DEFAULT_ZOOM_LEVEL, normalize_tag_name
from common import auth
from common.constants import BinManagementActions, TeamRoles

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
        self.user = kwargs.pop("user", None)

        super(DatasetForm, self).__init__(*args, **kwargs)

        # Restrict non-superadmins to just the teams they are associated with
        teams = auth.get_associated_teams(self.user)

        # Non-superadmins must always select a team
        is_team_required = not self.user.is_superuser

        self.fields["team"] = forms.ModelChoiceField(
            queryset=teams, required=is_team_required,
            widget=forms.Select(attrs={"class": "form-control form-control-sm"}))

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


class TagForm(forms.ModelForm):
    def clean_name(self):
        name = self.cleaned_data.get("name")
        name = normalize_tag_name(name).strip()

        if name.strip() == "":
            raise forms.ValidationError("Name is required")

        # Prevent creating a tag with a duplicate name
        existing = Tag.objects.filter(name__iexact=name)
        if self.instance.pk is not None:
            existing = existing.exclude(pk=self.instance.pk)

        if existing.count() > 0:
            raise forms.ValidationError("Name is already in use")

        return name

    class Meta:
        model = Tag
        fields = ["id", "name", ]
        help_texts = {
            "name": "Must contain only lowercase letters, numbers, and underscores. No spaces or special characters."
        }

        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Name"}),
        }


class MergeTagForm(forms.Form):
    source = forms.ModelChoiceField(
        required=True,
        queryset=Tag.objects.none(),
        help_text="The tag to be replaced. If no occurrences remain after the replacement, then this tag will be removed.",
        widget=forms.Select(attrs={"class": "form-control form-control-sm", "readonly": True}))
    target = forms.ModelChoiceField(
        required=True,
        queryset=Tag.objects.none(),
        help_text="The tag that replaces the source tag, which will be added all bins currently associated with the source tag.",
        widget=forms.Select(attrs={"class": "form-control form-control-sm"}))
    dataset = forms.ModelChoiceField(
        required=False,
        queryset=Dataset.objects.all(),
        help_text="Optionally restrict the update to bins associated with a specific dataset.",
        widget=forms.Select(attrs={"class": "form-control form-control-sm"}))

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop("instance", None) if "instance" in kwargs else None

        super().__init__(*args, **kwargs)

        self.fields["source"].queryset = Tag.objects.filter(pk=self.instance.pk)
        self.fields["source"].initial = self.instance
        self.fields["target"].queryset = Tag.objects.exclude(pk=self.instance.pk).order_by("name")

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

        if name.strip() == "":
            raise forms.ValidationError("Name is required")

        team = Team.objects.filter(name__iexact=name).exclude(id=self.instance.id)
        if team.exists():
            raise forms.ValidationError("This name is already in use.")

        return name

    class Meta:
        model = Team
        fields = ["id", "name", "title", "default_dataset", "description", "short_description", ]

        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Name"}),
            "title": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Title"}),
            "default_dataset": forms.Select(attrs={"class": "form-control form-control-sm"}),
            "description": forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 4}),
            "short_description": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
        }


class BinSearchForm(forms.Form):
    # FUTURE: Add fields and UI to allow users to add a list of excluded date ranges
    # FUTURE: Allow users to select more than one value for some dropdowns (e.g., tags)
    # FUTURE: Allow support for progressive filtering. E.g, changing dataset limits values for cruises

    input_classes = "form-control form-control-sm"

    start_date = forms.DateField(
        required=False,
        widget=forms.TextInput(attrs={"class": f"date-picker {input_classes}",}))
    end_date = forms.DateField(
        required=False,
        widget=forms.TextInput(attrs={"class": f"date-picker {input_classes}",}))

    # All dropdown based criteria are CharField's with a Select() width to allow for values to be
    #   loaded after the page loads using a POST call. This enables the values to be limited to
    #   just the team that's selected (if enabled). This removes the validation logic on those values,
    #   but that is covered by the validation on the team, since that will restrict all results down
    #   to just bins associated with a team the user has access to
    team = forms.ModelChoiceField(
        required=False,
        queryset=Team.objects.none(),
        empty_label=" ",
        widget=forms.Select(attrs={"class": input_classes}))
    dataset = forms.CharField(
        required=False,
        widget=forms.Select(attrs={"class": input_classes}))
    tag = forms.CharField(
        required=False,
        widget=forms.Select(attrs={"class": input_classes}))
    cruise = forms.CharField(
        required=False,
        widget=forms.Select(attrs={"class": input_classes}))
    instrument = forms.CharField(
        required=False,
        widget=forms.Select(attrs={"class": input_classes}))
    sample_type = forms.CharField(
        required=False,
        widget=forms.Select(attrs={"class": input_classes}))

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user") if "user" in kwargs else None

        super().__init__(*args, **kwargs)

        is_teams_enabled = waffle.switch_is_active("Teams")
        teams = auth.get_associated_teams(user)

        self.fields["team"].queryset = teams.order_by("name")
        self.fields["dataset"].widget.attrs["disabled"] = is_teams_enabled
        self.fields["instrument"].widget.attrs["disabled"] = is_teams_enabled
        self.fields["tag"].widget.attrs["disabled"] = is_teams_enabled
        self.fields["cruise"].widget.attrs["disabled"] = is_teams_enabled
        self.fields["sample_type"].widget.attrs["disabled"] = is_teams_enabled
        self.fields["start_date"].widget.attrs["disabled"] = is_teams_enabled
        self.fields["end_date"].widget.attrs["disabled"] = is_teams_enabled

    def clean(self):
        cleaned_data = self.cleaned_data
        start_date = self.cleaned_data.get("start_date")
        end_date = self.cleaned_data.get("end_date")

        # Ensure the user has entered at least one piece of criteria to prevent searching through
        #   the entire database of bins
        values = [value for key, value in cleaned_data.items() if key != "team" and value not in [None, ""]]
        if not any(values):
            raise ValidationError("Please select at least one thing to search for")

        # If both dates are entered, ensure end date is greater than or equal to start date
        if start_date is not None and end_date is not None and start_date >= end_date:
            raise ValidationError("End date cannot be earlier than the start date")

    @staticmethod
    def build_dataset_choices(bins):
        datasets = Dataset.objects \
            .filter(bins__in=bins) \
            .distinct() \
            .values_list("name", flat=True)

        return [""] + list(datasets)

    @staticmethod
    def build_tag_choices(bins):
        tags = Tag.objects \
            .filter(tagevent__bin__in=bins) \
            .distinct() \
            .values_list("name", flat=True)

        return [""] + list(tags)

    @staticmethod
    def build_cruise_choices(bins):
        cruises = bins \
            .exclude(cruise="") \
            .values_list("cruise", flat=True) \
            .order_by("cruise") \
            .distinct()

        return [""] + list(cruises)

    @staticmethod
    def build_instrument_choices(bins):
        instruments = bins \
            .values_list("instrument__number", flat=True) \
            .order_by("instrument__number") \
            .distinct()
        instrument_choices = [f"IFCB{instrument_number}" for instrument_number in instruments]

        return [""] + instrument_choices

    @staticmethod
    def build_sample_type_choices(bins):
        sample_types = bins \
            .exclude(sample_type="") \
            .values_list("sample_type", flat=True) \
            .order_by("sample_type") \
            .distinct()

        return [""] + list(sample_types)

class BinActionForm(forms.Form):
    input_classes = "form-control form-control-sm"

    action = forms.ChoiceField()
    assigned_dataset = forms.ModelChoiceField(
        required=False,
        queryset=None,
        empty_label=" ",
        widget=forms.Select(attrs={"class": input_classes + " w-50 ml-2", "disabled": True}))
    unassigned_dataset = forms.ModelChoiceField(
        required=False,
        queryset=None,
        empty_label=" ",
        widget=forms.Select(attrs={"class": input_classes + " w-50 ml-2", "disabled": True}))

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user") if "user" in kwargs else None

        super().__init__(*args, **kwargs)

        actions = [
            BinManagementActions.SKIP_BINS.value,
            BinManagementActions.UNSKIP_BINS.value,
            BinManagementActions.ASSIGN_DATASET.value,
            BinManagementActions.UNASSIGN_DATASET.value,
        ]
        action_options = zip(actions, actions)

        self.fields["action"] = forms.ChoiceField(choices=action_options)

        # Datasets to show, filtered if needed for non-superadmins
        datasets = auth.get_associated_datasets(user).order_by("name")

        self.fields["assigned_dataset"].queryset = datasets
        self.fields["unassigned_dataset"].queryset = datasets

    def clean(self):
        action = self.cleaned_data.get("action")
        assigned_dataset = self.cleaned_data.get("assigned_dataset")
        unassigned_dataset = self.cleaned_data.get("unassigned_dataset")

        if action == BinManagementActions.ASSIGN_DATASET.value and assigned_dataset is None:
            raise ValidationError("Please choose a dataset to assign")

        if action == BinManagementActions.UNASSIGN_DATASET.value and unassigned_dataset is None:
            raise ValidationError("Please choose a dataset to unassign")