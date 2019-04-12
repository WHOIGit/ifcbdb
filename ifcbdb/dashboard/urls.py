from django.urls import include, path

from . import views

urlpatterns = [
    path('', views.index),
    path('datasets', views.datasets),
    path('dataset-details', views.dataset_details),
    path('image-details', views.image_details),
    path('bin-details', views.bin_details),
]
