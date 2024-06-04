FROM python:3.12

ENV PYTHONUNBUFFERED=1

# geospatial libraries
RUN apt-get update && \
    apt-get install -y binutils git libproj-dev libgdal-dev libpoppler-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY ./ifcbcli/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /app
COPY ./ifcbcli .

EXPOSE 8001

