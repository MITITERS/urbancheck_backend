FROM docker.io/traefik:v3.7.1
# Sin root (N-18): el binario lleva la capacidad de abrir puertos bajos (80 y
# 443) y el almacén de certificados es del usuario con que corre. El compose
# deja NET_BIND_SERVICE como única capacidad del contenedor.
RUN apk add --no-cache libcap \
  && setcap cap_net_bind_service=+ep /usr/local/bin/traefik \
  && apk del libcap \
  && mkdir -p /etc/traefik/acme \
  && touch /etc/traefik/acme/acme.json \
  && chmod 600 /etc/traefik/acme/acme.json \
  && chown -R 65532:65532 /etc/traefik/acme
COPY ./compose/production/traefik/traefik.yml /etc/traefik
USER 65532:65532
