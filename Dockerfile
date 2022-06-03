FROM python:3.9.13-buster

ENV PYTHONUNBUFFERED 1 
ENV PYTHONDONTWRITEBYTECODE=1

RUN sudo apt update \
  && sudo apt install -y software-properties-common \
  # && apk add-apt-repository ppa:deadsnakes/ppa \
  # psycopg2 dependencies
  && sudo apt install -y --virtual build-deps gcc python3-dev musl-dev \
  && sudo apt install -y postgresql-dev \
  # Pillow dependencies
  && sudo apt install -y jpeg-dev zlib-dev freetype-dev lcms2-dev openjpeg-dev tiff-dev tk-dev tcl-dev \
  # CFFI dependencies
  && sudo apt install -y libffi-dev py-cffi \
  # Translations dependencies
  && sudo apt install -y gettext \
  # https://docs.djangoproject.com/en/dev/ref/django-admin/#dbshell
  && sudo apt install -y postgresql-client

RUN mkdir /capacitaciones
WORKDIR /capacitaciones

COPY ./requirements/base.txt /capacitaciones/
RUN pip install -r base.txt

COPY . /capacitaciones/
