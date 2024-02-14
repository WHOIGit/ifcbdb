# IFCB Dashboard

The IFCB dashboard provides a web interface for interacting with IFCB data, metadata, and imagery.
Users can load raw data and data products such as classification results into the dashboard, where they can be viewed.
In addition, metadata can be uploaded to the dashboard to allow for geospatial referencing / mapping.

## Installation

The dashboard is deployed using Docker. Docker will need to be installed before you can run the dashboard.

To configure the dashboard, copy `dotenv.template` to `.env` and edit the `.env` file with configuration parameters.

Here are the key parameters to edit in that file:

* `PRIMARY_DATA_DIR` refers to where your IFCB data is located on your system.
* `POSTGIS_IMAGE` needs to be configured if you are using Apple Silicon or another ARM-based system; otherwise the default value will work.
* `NGINX_TEMPLATE` allows you to specify an alternative NGINX configuration. Using the default is almost always preferable, as it is suitable for most deployment scenarios.
* `HOST` should be the fully qualified domain name of the computer where you are running the dashboard. The default is `localhost` which is used for testing purposes only.
* `HTTP_PORT` and `HTTPS_PORT` control which ports the dashboard will respond at. The defaults are 80 and 443 and they should work unless you are already running a web service on your computer that is already listening on those ports.

## Security configuration

To run the dashboard, you'll need an SSL certificate. This should be able to be provided by your host organization. If you cannot acquire an SSL certificate, you will need to generate a "self-signed" certificate but that configuration should only be used for testing, because it will give users a security warning in their browsers that strongly encourage them to reject access to the site.

Once you have acquired the certificate and placed the certificate file and key file in appropriate locations on your system, you will need to configure the dashboard to access that certificate using the `SSL_CERT` and `SSL_KEY` parameters in `.env`, using the path to each file.

In addition to SSL, there is a security parameter in the `.env` file called `DJANGO_SECRET_KEY`. You will need to change that parameter and set it to some unique value that can't be easily guessed.

## Running the dashboard

Once you have configured `.env`, you can bring the dashboard up by running `docker-compose up -d` from the directory containing the `docker-compose.yml` file.

## Building the image yourself

If you don't want to use the image from Docker Hub (for instance, if you've made modifications) you can build it yourself. Once you build and tag the image from the provided Dockerfile, configure the `IFCBDB_IMAGE` parameter in `.env` to refer to your image tag.

