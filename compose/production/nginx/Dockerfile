# Sin root (N-18): el maestro de nginx corre como el usuario nginx y escucha
# en 8080, porque sin root no se abren puertos bajos.
FROM docker.io/nginxinc/nginx-unprivileged:1.31.7-alpine
COPY ./compose/production/nginx/default.conf /etc/nginx/conf.d/default.conf
