from continuumio/miniconda3

# geospatial libraries
RUN apt-get update && apt-get install -y binutils libproj-dev

RUN conda config --remove channels defaults
RUN conda config --append channels conda-forge

RUN conda update conda

# nomkl to reduce image size (mkl is large)
RUN conda install -c conda-forge nomkl conda-merge

# install pyifcb and ifcbdb dependencies first
# pyifcb must be cloned into the same directory as this dockerfile

WORKDIR /pyifcb
COPY ./pyifcb .
COPY ./pyifcb/environment.yml /envs/pyifcb_env.yml

WORKDIR /ifcbdb
COPY environment.yml /envs/ifcbdb_env.yml

WORKDIR /envs
RUN conda-merge pyifcb_env.yml ifcbdb_env.yml > merged-environment.yml
RUN cat merged-environment.yml

RUN conda env update -n root -f merged-environment.yml

WORKDIR /pyifcb
RUN python setup.py develop

EXPOSE 8000

# descend into app directory
WORKDIR /ifcbdb

CMD gunicorn --bind :8000 ifcbdb.wsgi:application --reload
