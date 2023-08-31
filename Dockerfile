FROM python

# geospatial libraries
RUN apt-get update && apt-get install -y binutils libproj-dev libgdal-dev libpoppler-dev

WORKDIR /build
COPY requirements.txt .

RUN pip install -r requirements.txt

WORKDIR /pyifcb
COPY ./pyifcb .
RUN python setup.py install

WORKDIR /ifcbdb
COPY ./ifcbdb .

EXPOSE 8000

CMD gunicorn --bind :8000 ifcbdb.wsgi:application --reload