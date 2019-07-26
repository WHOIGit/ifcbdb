from continuumio/miniconda3:4.5.12

RUN apt-get update

# geospatial libraries
RUN apt-get install -y binutils libproj-dev gdal-bin

# prevent conda auto updating
RUN conda config --set auto_update_conda False

# nomkl to reduce image size (mkl is large)
RUN conda install nomkl

# install pyifcb and ifcbdb dependencies first
# pyifcb must be cloned into the same directory as this dockerfile

WORKDIR /pyifcb
COPY ./pyifcb .
RUN conda env update -n root -f environment.yml

WORKDIR /ifcbdb
COPY environment.yml .
RUN conda env update -n root -f environment.yml

# now install pyifcb
WORKDIR /pyifcb
RUN python setup.py develop

# this application

RUN conda install gunicorn=19.9.0

EXPOSE 8000

# descend into app directory
WORKDIR /ifcbdb

CMD gunicorn --bind :8000 ifcbdb.wsgi:application --reload
