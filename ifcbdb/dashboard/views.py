from django.shortcuts import render
from .models import Dataset


def index(request):
    datasets = Dataset.objects.all()

    return render(request, 'dashboard/index.html', {
        "datasets": datasets,
    })

def datasets(request):
    return render(request, 'dashboard/datasets.html', {

    })

def dataset_details(request):
    return render(request, 'dashboard/dataset-details.html', {

    })

def image_details(request):
    return render(request, 'dashboard/image-details.html', {

    })
    
def bin_details(request):
    return render(request, 'dashboard/bin-details.html', {

    })            

