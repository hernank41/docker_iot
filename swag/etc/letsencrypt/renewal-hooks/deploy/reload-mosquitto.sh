#!/bin/bash
# Este script se ejecuta DENTRO del contenedor SWAG

MOSQUITTO_CONTAINER="${MOSQUITTO_CONTAINER:-mosquitto}"

echo "$(date): Recargando Mosquitto en: ${MOSQUITTO_CONTAINER}"

# Usar curl contra el socket de Docker (más ligero que instalar docker CLI)
curl --unix-socket /var/run/docker.sock \
  -X POST "http://localhost/containers/${MOSQUITTO_CONTAINER}/kill?signal=HUP"