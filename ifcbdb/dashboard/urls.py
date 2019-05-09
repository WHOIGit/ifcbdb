from django.urls import include, path, re_path

from . import views

urlpatterns = [
    path('', views.datasets),
    path('dashboard', views.datasets, name='datasets'),

    # The urls below must remain in this specific order (by granularity)
    # TODO: The slugs for the images need to be left padded with zeros

    # legacy "dataset with bin selected" permalink
    # e.g. http://ifcb-data.whoi.edu/mvco/dashboard/http://ifcb-data.whoi.edu/mvco/D20140101T123456_IFCB010
    re_path(r'(?P<dataset_name>[\w-]+)/dashboard/http.*/(?P<bin_id>\w+)', views.dataset_details),

    path('<slug:dataset_name>/<slug:bin_id>/<slug:image_id>.html', views.image_details, name='image'),
    path('<slug:dataset_name>/<slug:bin_id>_<int:image_id>.html', views.image_details, name='image_legacy'),
    path('<slug:dataset_name>/<slug:bin_id>.html', views.bin_details, name='bin'),

    # raw data access
    path('<slug:dataset_name>/<slug:bin_id>.adc', views.adc_data, name='adc_csv'),
    path('<slug:dataset_name>/<slug:bin_id>.hdr', views.hdr_data, name='hdr_text'),
    path('<slug:dataset_name>/<slug:bin_id>.roi', views.roi_data, name='roi_binary'),

    # blob zip access
    path('<slug:dataset_name>/<slug:bin_id>_blob.zip', views.blob_zip, name='blob_zip'),

    # zip access
    path('<slug:dataset_name>/<slug:bin_id>.zip', views.zip, name='zip'),

    # image access
    path('<slug:dataset_name>/<slug:bin_id>_<int:target>.png', views.image_data_png, name='image_png'),
    path('<slug:dataset_name>/<slug:bin_id>_<int:target>.jpg', views.image_data_jpg, name='image_jpg'),


    path('<slug:dataset_name>', views.dataset_details, name='dataset'),

    # Paths used for API/Ajax requests
    path('api/<slug:dataset_name>/time-series/<slug:metric>', views.generate_time_series, name='generate_time_series'),
    path('api/<slug:dataset_name>/bin/<slug:bin_id>', views.bin_data, name='bin_data'),
    path('api/<slug:dataset_name>/closest_bin', views.closest_bin, name='closest_bin'),
    path('api/mosaic/coordinates/<slug:bin_id>', views.mosaic_coordinates, name='mosaic_coordintes'),
    path('api/mosaic/encoded_image/<slug:bin_id>', views.mosaic_page_encoded_image, name='mosaic_page_encoded_image'),
    path('api/mosaic/image/<slug:bin_id>.png', views.mosaic_page_image, name='mosaic_page_image'),
    path('api/image/<slug:bin_id>/<int:target>', views.image_metadata, name='image_metadata'),
]
