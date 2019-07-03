from django.contrib.auth import views as auth_views
from django.urls import include, path

from . import views

app_name = 'secure'
urlpatterns = [
    path('', views.index, name='index'),
    path('login/', auth_views.LoginView.as_view(template_name='secure/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('dataset-management', views.dataset_management, name='dataset-management'),
    path('instrument-management', views.instrument_management, name='instrument-management'),
    path('upload-geospatial', views.upload_geospatial, name='upload-geospatial'),

    # Paths used for AJAX requests specifically for returning data formatted for DataTables
    path('api/dt/datasets', views.dt_datasets, name='datasets_dt'),
    path('api/dt/instruments', views.dt_instruments, name='instruments_dt'),
    path('api/dataset/<int:id>', views.dataset, name='dataset'),
    path('api/instrument/<int:id>', views.instrument, name='instrument'),
    path('api/update-dataset/<int:id>', views.update_dataset, name='update_dataset'),
    path('api/update-instrument/<int:id>', views.update_instrument, name='update_instrument'),

]
