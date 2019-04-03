from continuumio/miniconda3

RUN apt-get update

# nomkl to reduce image size (mkl is large)
RUN conda install nomkl

# gunicorn to run the WSGI app
RUN conda install gunicorn

# install pyifcb and ifcbdb dependencies first
# pyifcb must be cloned into the same directory as this dockerfile

WORKDIR /pyifcb
COPY pyifcb/environment.yml .
RUN conda env update -n root -f environment.yml

WORKDIR /ifcbdb
COPY environment.yml .
RUN conda env update -n root -f environment.yml

# now install pyifcb
WORKDIR /pyifcb

COPY pyifcb .
RUN python setup.py install

# this application

EXPOSE 8000

# now copy all the app code to the container
WORKDIR /ifcb
COPY . .

# descend into app directory
WORKDIR ifcbdb

CMD gunicorn --bind :8000 ifcbdb.wsgi:application --reload
