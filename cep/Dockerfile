# syntax=docker/dockerfile:1.7
# Runtime de Siddhi 5.x (proceso CEP aparte) + transporte MQTT, que el runner original no trae.
FROM siddhiio/siddhi-runner-alpine:5.1.2

ARG RUNNER_HOME=/home/siddhi_user/siddhi-runner

# Los bundles OSGi van en lib/. Versiones y checksums fijos para que el build sea reproducible.
ADD --checksum=sha256:34bff137db304f13cf51655b248b45aa962ddd40f16585c3b95624696a6915a9 \
    https://repo1.maven.org/maven2/io/siddhi/extension/io/mqtt/siddhi-io-mqtt/3.0.4/siddhi-io-mqtt-3.0.4.jar \
    ${RUNNER_HOME}/lib/
ADD --checksum=sha256:59914287adac506a28d5e8172eed262a22605f3df4d426b9d92f41dae2448185 \
    https://repo1.maven.org/maven2/org/eclipse/paho/org.eclipse.paho.client.mqttv3/1.2.5/org.eclipse.paho.client.mqttv3-1.2.5.jar \
    ${RUNNER_HOME}/lib/

COPY siddhi/CargoMonitoring.siddhi /apps/CargoMonitoring.siddhi

# Solo para el banco de pruebas (CEP_STATISTICS=true): activa las estadísticas nativas de Siddhi
# (latencia y memoria por consulta, throughput por stream) y las imprime en consola cada 5 s.
# En producción queda apagado: la app y la config del runner no cambian.
ARG CEP_STATISTICS=false
COPY benchmark/metrics-console.yaml /tmp/metrics-console.yaml
RUN if [ "$CEP_STATISTICS" = "true" ]; then \
      cat /tmp/metrics-console.yaml >> ${RUNNER_HOME}/conf/runner/deployment.yaml && \
      sed -i "1a @App:statistics(reporter = 'console', interval = '5')" /apps/CargoMonitoring.siddhi; \
    fi && rm /tmp/metrics-console.yaml

# ${MQTT_URL}, ${MQTT_USERNAME} y ${MQTT_PASSWORD} de la app Siddhi se toman de las variables de entorno.
EXPOSE 9090
CMD ["-Dapps=/apps/CargoMonitoring.siddhi"]
