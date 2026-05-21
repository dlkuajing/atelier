FROM ghcr.io/berriai/litellm:main-latest

WORKDIR /app
COPY config.yaml /app/config.yaml

EXPOSE 4000
ENTRYPOINT []
CMD ["litellm", "--config", "/app/config.yaml", "--port", "4000", "--host", "0.0.0.0"]
