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

    path('<slug:dataset_name>/<slug:bin_id>/mosaic.html', views.mosaic, name='mosaic'),
    path('<slug:dataset_name>/<slug:bin_id>/<slug:image_id>.html', views.image_details, name='image'),
    path('<slug:dataset_name>/<slug:bin_id>_<int:image_id>.html', views.image_details, name='image_legacy'),
    path('<slug:dataset_name>/<slug:bin_id>.html', views.bin_details, name='bin'),

    # raw data access
    path('<slug:dataset_name>/<slug:bin_id>.adc', views.adc_data, name='adc_csv'),
    path('<slug:dataset_name>/<slug:bin_id>.hdr', views.hdr_data, name='hdr_text'),
    path('<slug:dataset_name>/<slug:bin_id>.roi', views.roi_data, name='roi_binary'),

    # image access
    path('<slug:dataset_name>/<slug:bin_id>_<int:target>.png', views.image_data_png, name='image_png'),
    path('<slug:dataset_name>/<slug:bin_id>_<int:target>.jpg', views.image_data_jpg, name='image_jpg'),

    path('<slug:dataset_name>', views.dataset_details, name='dataset'),

]
