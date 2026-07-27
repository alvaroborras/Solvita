FROM gcc:13-bookworm@sha256:3e239a5ea77200b9163c825a0a5ebc17ca99f3bbb4d08241ee0fb9c174325880
RUN useradd --create-home --uid 10001 solver
USER solver
WORKDIR /work
ENTRYPOINT []
