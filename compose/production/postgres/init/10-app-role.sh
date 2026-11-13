#!/bin/bash
# N-07: el rol con que entra Django, sin superusuario y dueño de la base.
#
# Lo corre la imagen oficial de PostgreSQL una sola vez, al inicializar un
# volumen de datos vacío (/docker-entrypoint-initdb.d). Se monta solo desde
# docker-compose.production.yml: el compose local usa la misma imagen y sigue
# igual. POSTGRES_USER queda como superusuario para el mantenimiento (backups).
#
# En una base ya inicializada no corre: ahí hay que crear el rol a mano con
# las mismas sentencias.

set -o errexit
set -o nounset

: "${POSTGRES_APP_USER:?Definí POSTGRES_APP_USER en .envs/.production/.postgres}"
: "${POSTGRES_APP_PASSWORD:?Definí POSTGRES_APP_PASSWORD en .envs/.production/.postgres}"

# Las variables de psql (:"nombre" y :'valor') citan los identificadores y el
# texto: ni el nombre ni la contraseña se arman como SQL a mano.
psql -v ON_ERROR_STOP=1 \
  --username "${POSTGRES_USER}" \
  --dbname "${POSTGRES_DB}" \
  -v app_user="${POSTGRES_APP_USER}" \
  -v app_password="${POSTGRES_APP_PASSWORD}" \
  -v db="${POSTGRES_DB}" <<'SQL'
CREATE ROLE :"app_user" LOGIN PASSWORD :'app_password'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
-- Dueño de la base: desde PostgreSQL 15 el esquema public es de
-- pg_database_owner, así que alcanza para crear las tablas de las migraciones.
ALTER DATABASE :"db" OWNER TO :"app_user";
SQL
