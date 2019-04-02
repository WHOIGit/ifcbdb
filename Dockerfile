from continuumio/miniconda3

RUN apt-get update

# install pyifcb

RUN apt-get install -y git

WORKDIR /

RUN git clone https://github.com/joefutrelle/pyifcb

WORKDIR /pyifcb

RUN conda install nomkl

RUN conda env update -n root -f environment.yml

RUN python setup.py install

# install dependencies

WORKDIR /ifcbdb

COPY environment.yml .

RUN conda env update -n root -f environment.yml

# gunicorn

RUN conda install gunicorn

#

EXPOSE 8000

COPY . .

WORKDIR ifcbdb

CMD gunicorn --bind :8000 ifcbdb.wsgi:application --reload
