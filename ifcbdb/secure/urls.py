from django.contrib.auth import views as auth_views
from django.urls import include, path

from . import views

app_name = 'secure'
urlpatterns = [
    path('', views.index, name='index'),
    path('login/', auth_views.LoginView.as_view(template_name='secure/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('dataset-management', views.dataset_management),
    path('upload-geospatial', views.upload_geospatial),
    ]
