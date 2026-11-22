FROM eclipse-mosquitto:2.0.22
# openssl solo se usa para crear la CA/certificado de desarrollo cuando no hay uno montado.
RUN apk add --no-cache openssl
COPY mosquitto.conf acl /mosquitto/config/
COPY entrypoint.sh /usr/local/bin/cargo-entrypoint.sh
RUN chmod 0755 /usr/local/bin/cargo-entrypoint.sh
EXPOSE 8883
ENTRYPOINT ["/usr/local/bin/cargo-entrypoint.sh"]
