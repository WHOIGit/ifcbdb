from continuumio/miniconda3

RUN apt-get update

# nomkl to reduce image size (mkl is large)
RUN conda install nomkl

# gunicorn to run the WSGI app
RUN conda install gunicorn

# install pyifcb from local clone which must be located
# in the same directory as this dockerfile

WORKDIR /pyifcb
COPY pyifcb/environment.yml .
RUN conda env update -n root -f environment.yml

COPY pyifcb /pyifcb
RUN python setup.py install

# install dependencies

WORKDIR /ifcbdb
COPY environment.yml .
RUN conda env update -n root -f environment.yml

# this application

EXPOSE 8000

# now copy all the app code to the container
COPY . .

WORKDIR ifcbdb

CMD gunicorn --bind :8000 ifcbdb.wsgi:application --reload
