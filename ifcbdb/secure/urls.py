from django.contrib.auth import views as auth_views
from django.urls import include, path

from . import views

app_name = 'secure'
urlpatterns = [
    path('', views.index, name='index'),
    path('login/', auth_views.LoginView.as_view(template_name='secure/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('dataset-management', views.dataset_management, name='dataset-management'),
    path('edit-dataset/<int:id>', views.edit_dataset, name='edit-dataset'),
    path('instrument-management', views.instrument_management, name='instrument-management'),
    path('tag-management', views.tag_management, name='tag-management'),
    path('edit-instrument/<int:id>', views.edit_instrument, name='edit-instrument'),
    path('edit-tag/<int:id>', views.edit_tag, name='edit-tag'),
    path('merge-tag/<int:id>', views.merge_tag, name='merge-tag'),
    path('upload-metadata', views.upload_metadata, name='upload-metadata'),
    path('directory-management/<int:dataset_id>', views.directory_management, name='directory-management'),
    path('edit-directory/<int:dataset_id>/<int:id>', views.edit_directory, name='edit-directory'),
    path('app-settings', views.app_settings, name='app-settings'),

    # Paths used for AJAX requests specifically for returning data formatted for DataTables
    path('api/dt/datasets', views.dt_datasets, name='datasets_dt'),
    path('api/dt/instruments', views.dt_instruments, name='instruments_dt'),
    path('api/dt/tags', views.dt_tags, name='tags_dt'),
    path('api/dt/directories/<int:dataset_id>', views.dt_directories, name='directories_dt'),
    path('api/delete-directory/<int:dataset_id>/<int:id>', views.delete_directory, name='delete-directory'),
    path('api/delete-tag/<int:id>', views.delete_tag, name='delete-tag'),
    path('api/add-tag/<slug:bin_id>', views.add_tag, name='add_tag'),
    path('api/remove-tag/<slug:bin_id>', views.remove_tag, name='remove_tag'),
    path('api/add-comment/<slug:bin_id>', views.add_comment, name='add_comment'),
    path('api/delete-comment/<slug:bin_id>', views.delete_comment, name='delete_comment'),
    path('api/edit-comment/<slug:bin_id>', views.edit_comment, name='edit_comment'),
    path('api/update-comment/<slug:bin_id>', views.update_comment, name='update_comment'),
    path('api/sync/<int:dataset_id>', views.sync_dataset, name='sync_dataset'),
    path('api/sync/status/<int:dataset_id>', views.sync_dataset_status, name='sync_dataset_status'),
    path('api/sync/cancel/<int:dataset_id>', views.sync_cancel, name='sync_cancel'),
    path('api/metadata-upload/status', views.metadata_upload_status, name='metadata_upload_status'),
    path('api/metadata-upload/cancel', views.metadata_upload_cancel, name="metadata_upload_cancel"),
    path('api/toggle-skip', views.toggle_skip, name='toggle_skip'),
    path('api/merge-tag/<int:id>/affected-bins', views.merge_tag_affected_bins, name='merge_tag_affected_bins'),
]
