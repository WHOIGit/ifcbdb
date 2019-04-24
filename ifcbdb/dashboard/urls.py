from django.urls import include, path, re_path

from . import views

urlpatterns = [
    path('', views.datasets),
    path('dashboard', views.datasets, name='datasets'),

    # The urls below must remain in this specific order (by granularity)
    # TODO: The slugs for the images need to be left padded with zeros
    # TODO: Handle .jpg and .png (instead of .html) to go to the images directly
    path('<slug:dataset_name>/<slug:bin_id>/mosaic.html', views.mosaic, name='mosaic'),
    path('<slug:dataset_name>/<slug:bin_id>/<slug:image_id>.html', views.image_details, name='image'),
    path('<slug:dataset_name>/<slug:bin_id>.html', views.bin_details, name='bin'),
    path('<slug:dataset_name>/<slug:bin_id>.adc', views.adc_data, name='adc data (csv)'),
    path('<slug:dataset_name>/<slug:bin_id>.hdr', views.hdr_data, name='hdr data (text/plain)'),
    path('<slug:dataset_name>/<slug:bin_id>.roi', views.roi_data, name='roi data (raw binary)'),
    path('<slug:dataset_name>/<slug:image_id>.png', views.image_data_png, name='image_data (png)'),
    path('<slug:dataset_name>/<slug:image_id>.jpg', views.image_data_jpg, name='image data (jpg)'),
    path('<slug:dataset_name>', views.dataset_details, name='dataset'),

    # TODO: Need to handle previous permalink URLS. (work in progress/examples to be handled later)
    #re_path(r'(?P<dataset_id>[\w-])/dashboard/http.*/(?P<bin_id>[\w-]+)', views.bin_details),
    #path('<slug:dataset_id>/dashboard/http\://.*', views.bin_details)
    # https://ifcb-data.whoi.edu/mvco/dashboard/http://ifcb-data.whoi.edu/mvco/IFCB5_2012_038_234749
]
