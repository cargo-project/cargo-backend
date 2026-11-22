FROM eclipse-mosquitto:2.0.22
COPY mosquitto.conf acl /mosquitto/config/
COPY entrypoint.sh /usr/local/bin/cargo-entrypoint.sh
RUN chmod 0755 /usr/local/bin/cargo-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/cargo-entrypoint.sh"]
