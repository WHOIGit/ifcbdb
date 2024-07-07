from django.urls import path, re_path, register_converter

from . import views


class BinPidConverter:
    regex = r'(IFCB\d_\d{4}_\d{3}_\d{6}|D\d{8}T\d{6}_IFCB\d{3})'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


class ImageIdConverter:
    regex = r'\d+'

    def to_python(self, value):
        return int(value)

    def to_url(self, value):
        return '{:05d}'.format(value)


register_converter(BinPidConverter, 'pid')
register_converter(ImageIdConverter, 'image_id')

urlpatterns = [
    ##########################################################################################
    # Main entry point URLs
    #   Details of some of the more complex routes are described in a dedicated wiki document:
    #   https://github.com/WHOIGit/ifcbdb/wiki/URL-routes-(development)
    ##########################################################################################

    # TODO: Handle trailing slashes
    # TODO: The slugs for the images need to be left padded with zeros
    path('', views.index),
    path('index.html', views.index),    
    path('dashboard', views.datasets, name='datasets'),
    path('timeline', views.timeline_page, name='timeline_page'),
    path('bin', views.bin_page, name='bin_page'),
    path('image', views.image_page, name='image_page'),
    path('comments', views.comments_page, name='comment_page'),
    path('list', views.list_page, name='list_page'),
    path('about', views.about_page, name='about_page'),

    # raw data access
    path('data/<slug:bin_id>.adc', views.adc_data, name='adc_csv'),
    path('data/<slug:bin_id>.hdr', views.hdr_data, name='hdr_text'),
    path('data/<slug:bin_id>.roi', views.roi_data, name='roi_binary'),
    path('data/<slug:bin_id>_blob.zip', views.blob_zip, name='blob_zip'),
    path('data/<slug:bin_id>_features.csv', views.features_csv, name='features_csv'),
    path('data/<slug:bin_id>_class_scores.mat', views.class_scores_mat, name='class_scores_mat'),
    path('data/<slug:bin_id>.zip', views.zip, name='zip'),

    # image access
    path('data/<slug:bin_id>_<int:target>.png', views.image_png, name='image_png'),
    path('data/<slug:bin_id>_<int:target>.jpg', views.image_jpg, name='image_jpg'),

    ##################################################################
    # Legacy URLs
    #   Urls below must remain in this specific order (by granularity)
    ##################################################################

    # legacy "dataset with bin selected" permalink
    # e.g. http://ifcb-data.whoi.edu/mvco/dashboard/http://ifcb-data.whoi.edu/mvco/D20140101T123456_IFCB010
    re_path(r'(?P<dataset_name>[\w-]+)/dashboard/http.*/(?P<bin_id>\w+)', views.legacy_dataset_page),

    path('<slug:dataset_name>/<slug:bin_id>/<slug:image_id>.html', views.legacy_image_page, name='image'),
    path('<slug:dataset_name>/<pid:bin_id>_<image_id:image_id>.html', views.legacy_image_page, name='image_legacy'),
    path('<pid:bin_id>_<image_id:image_id>.html', views.legacy_image_page_alt, name='image_legacy_alt'),
    path('<slug:dataset_name>/<slug:bin_id>.html', views.legacy_dataset_page, name='bin_legacy'),

    # legacy raw data access
    path('<slug:dataset_name>/<slug:bin_id>.adc', views.adc_data, name='adc_csv_legacy'),
    path('<slug:dataset_name>/<slug:bin_id>.hdr', views.hdr_data, name='hdr_text_legacy'),
    path('<slug:dataset_name>/<slug:bin_id>.roi', views.roi_data, name='roi_binary_legacy'),
    path('<slug:dataset_name>/<slug:bin_id>_blob.zip', views.blob_zip, name='blob_zip_legacy'),
    path('<slug:dataset_name>/<slug:bin_id>_features.csv', views.features_csv, name='features_csv_legacy'),
    path('<slug:dataset_name>/<slug:bin_id>_class_scores.mat', views.class_scores_mat, name='class_scores_legacy'),
    path('<slug:dataset_name>/<slug:bin_id>_class_scores.csv', views.class_scores_csv, name='class_scores_csv_legacy'),
    path('<slug:dataset_name>/<slug:bin_id>.zip', views.zip, name='zip_legacy'),

    # legacy metadata access
    path('<slug:dataset_name>/<slug:bin_id>_short.json', views.legacy_short_json, name='short_json'),
    path('<slug:dataset_name>/<slug:bin_id>_roisizes', views.legacy_roisizes, name='roisizes'),

    # legacy image access
    path('<slug:dataset_name>/<slug:bin_id>_<int:target>.png', views.image_png_legacy, name='image_png_legacy'),
    path('<slug:dataset_name>/<slug:bin_id>_<int:target>.jpg', views.image_jpg_legacy, name='image_jpg_legacy'),

    # legacy feed API
    path('<ds_plus_tags>/api/feed/<slug:metric>/start/<start>/end/<end>', views.feed_legacy, name='feed_legacy'),

    # legacy dataset timeline endpoint
    path('<slug:dataset_name>', views.legacy_dataset_redirect, name='dataset_legacy'),
    path('<slug:dataset_name>/', views.legacy_dataset_redirect, name='dataset_legacy'),    

    ##################################
    # Paths used for API/Ajax requests
    ##################################
    path('api/time-series/<slug:metric>', views.generate_time_series, name='generate_time_series'),
    path('api/bin/<slug:bin_id>', views.bin_data, name='bin_data'),
    path('api/bin/<slug:bin_id>', views.bin_data),
    path('api/closest_bin', views.closest_bin, name='closest_bin'),  # closest bin in time
    path('api/nearest_bin', views.nearest_bin, name='nearest_bin'),
    path('api/mosaic/coordinates/<slug:bin_id>', views.mosaic_coordinates, name='mosaic_coordintes'),
    path('api/mosaic/encoded_image/<slug:bin_id>', views.mosaic_page_encoded_image, name='mosaic_page_encoded_image'),
    path('api/mosaic/image/<slug:bin_id>.png', views.mosaic_page_image, name='mosaic_page_image'),
    path('api/image/<slug:bin_id>/<int:target>', views.image_metadata, name='image_metadata'),
    path('api/image_data/<slug:bin_id>/<int:target>', views.image_data, name='image_data'),
    path('api/blob/<slug:bin_id>/<int:target>', views.image_blob, name='image_blob'),
    path('api/outline/<slug:bin_id>/<int:target>', views.image_outline, name='image_outline'),
    path('api/plot/<slug:bin_id>', views.plot_data, name='plot_data'),
    path('api/metadata/<slug:bin_id>', views.bin_metadata, name='bin_metadata'),
    path('api/bin_exists', views.bin_exists, name='bin_exists'),
    path('api/single_bin_exists', views.single_bin_exists, name='single_bin_exists'),
    path('api/bin_location', views.bin_location, name='bin_location'),
    path('api/filter_options', views.filter_options, name='filter_options'),
    path('api/has_products/<slug:bin_id>', views.has_products, name='has_products'),
    path('api/search_bin_locations', views.search_bin_locations, name='search_bin_locations'),
    path('api/search_timeline_locations', views.search_timeline_locations, name='search_timeline_locations'),
    path('api/search_comments', views.search_comments, name='search_comments'),
    path('api/tags', views.tags, name='tags'),
    path('api/timeline_info', views.timeline_info, name='timeline_info'),
    path('api/list_bins', views.list_bins, name='list_bins'),
    path('api/list_images/<slug:pid>', views.list_images, name='list_images'),
    path('api/update_skip', views.update_skip, name='update_skip'),
    path('api/export_metadata/<slug:dataset_name>', views.export_metadata_view, name='export_metadata'),
    path('api/export_metadata/', views.export_metadata_view, name='export_metadata'),
    path('api/sync_bin', views.sync_bin, name='sync_bin'),
 ]
