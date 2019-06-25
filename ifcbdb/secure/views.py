from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def index(request):
    return render(request, 'secure/index.html', {

    })

def dataset_management(request):
    return render(request, 'secure/dataset-management.html', {

    })

def upload_geospatial(request):
    return render(request, 'secure/upload-geospatial.html', {

    })