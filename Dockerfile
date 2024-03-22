FROM python:3.11-slim

# geospatial libraries
RUN apt-get update && \
    apt-get install -y binutils git libproj-dev libgdal-dev libpoppler-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /ifcbdb
COPY ./ifcbdb .

WORKDIR /utilities
COPY ./utilities .

WORKDIR /ifcbdb

EXPOSE 8000

CMD gunicorn --bind :8000 ifcbdb.wsgi:application --reload
