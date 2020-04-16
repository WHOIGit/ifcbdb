# ifcbdb
IFCB dashboard


## Setup Instructions

#### Install operating system prerequisites
* Git
* Docker
* Docker Compose

#### Set up a new project director
```shell script
mkdir ifcb && cd ifcb
```

#### Clone the pyifcb repository
This must be completed before initializing the docker containers
```shell script
git clone https://github.com/joefutrelle/pyifcb.git
```

#### Update local configuration files
Once copied, modify these files as needed to fit your particular environment
```shell script
cp ifcbdb/ifcbdb/local_settings.py.example ifcbdb/ifcbdb/local_settings.py
cp nginx/ifcbdb.conf.example nginx/ifcbdb.conf
```

#### Initialize docker
```shell script
docker-compose up
```

#### Run migrations and update static files
```shell script
./bin/update.sh
```

#### Create a new superuser account
```shell script
./bin/shell.sh
python manage.py createsuperuser
exit
```

The site should now be running and available at http://localhost:8000


## Adding a new dataset, directory and sync'ing your data
* Use the "Log In" link in the website's footer to get to the settings page
* Click on "Dataset Management"
* Click "Add New Dataset" and fill in the required information
* Click "Save" to create the new dataset
* Click "Manage Directories" and then "Add New Data Directory"
* Fill in the required information* and hit save
* Click the "Back to Dataset" button
* Click the "Sync" button. This may take some time depending on the size of your dataset  


 \* Data files should be located within the ifcb_data folder within the project's root directory. Within the docker container, this path is changed to "/data", so the path used for creating a new dataset directory will be "/data/your-data-set-folder"


