# Django Project

## Instalacion y despliegue
    Instalar python3.9 en ubuntu 18.04
    - sudo apt update
    - sudo apt install software-properties-common
    - sudo add-apt-repository ppa:deadsnakes/ppa
    - sudo apt update 
    - sudo apt install python3.9
    Instalar el venv
    - sudo apt install python3.9-venv
    Crear el entorno virtual
    - python3.9 -m venv venv
### Configuracion
    Crear archivo .env y añadir las variables de entorno necesarias para el correcto 
    funcionamiento del proyecto. 
    Variables de entorno básicas:

    +---------------------------------+------------------------------------------------------+
    | ``DATABASE_URL``                | Es la cadena de conexión a la base de datos para     |
    |                                 | PostgreSQL se debe usar la siguiente sintaxys:       |
    |                                 | ``psql://user:password@host:port/database``          |
    +---------------------------------+------------------------------------------------------+
    | ``ALLOWED_HOSTS``               | "*"                                                  |
    +---------------------------------+------------------------------------------------------+
    | ``EMAIL_HOST``                  | Host del email                                       |
    +---------------------------------+------------------------------------------------------+
    | ``EMAIL_PORT``                  | Puerto para el email                                 |
    +---------------------------------+------------------------------------------------------+
    | ``EMAIL_HOST_USER``             | Usuario para email                                   |
    +---------------------------------+------------------------------------------------------+
    | ``EMAIL_HOST_PASSWORD``         | Contraseña para el email                             |
    +---------------------------------+------------------------------------------------------+

### Instalar requerimientos en virtualenv
- Activar el venv ubicandose dentro del proyecto: source venv/bin/activate 
- pip install -r requirements/base.txt

### Indicaciones para sysadmin

**EJECUTAR**
- python manage.py migrate
- python manage.py collectstatic

**ARRANCAR LA APLICACIÓN**
- python manage.py runserver

### Indicaciones para Base de datos: [Indicaciones para BD](sql/readme.md)
