from django.contrib import admin
from django.urls import path
from ninja import NinjaAPI
from datasets.api import router as datasets_router
from bins.api import router as bins_router
from tags.api import router as tags_router


api = NinjaAPI()
api.add_router('/datasets/', datasets_router)
api.add_router('/bins/', bins_router)
api.add_router('/tags/', tags_router)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', api.urls),
]
