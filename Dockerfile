from continuumio/miniconda3

RUN conda update conda

# geospatial libraries
RUN apt-get update && apt-get install -y binutils libproj-dev

WORKDIR /envs
COPY ./pyifcb/environment.yml pyifcb_env.yml
COPY environment.yml ifcbdb_env.yml

RUN conda install gdal
RUN conda env update -n base -f pyifcb_env.yml
RUN conda env update -n base -f ifcbdb_env.yml

WORKDIR /pyifcb
COPY ./pyifcb .
RUN python setup.py install

WORKDIR /ifcbdb
COPY ./ifcbdb .

EXPOSE 8000

CMD gunicorn --bind :8000 ifcbdb.wsgi:application --reload
