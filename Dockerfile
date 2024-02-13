FROM python:3.11

# geospatial libraries
RUN apt-get update && apt-get install -y binutils libproj-dev libgdal-dev libpoppler-dev

WORKDIR /build
COPY requirements.txt .

RUN pip install -r requirements.txt

WORKDIR /ifcbdb
COPY ./ifcbdb .

WORKDIR /utilities
COPY ./utilities .

WORKDIR /ifcbdb

EXPOSE 8000

CMD gunicorn --bind :8000 ifcbdb.wsgi:application --reload