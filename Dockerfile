FROM python:3.12-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_DEFAULT_TIMEOUT=180 PIP_RETRIES=8 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY pyproject.toml docker/requirements-cpu.txt /app/
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements-cpu.txt
COPY fire_modeling /app/fire_modeling
RUN pip install --no-deps --no-build-isolation .
COPY configs /app/configs
COPY tests /app/tests
COPY scripts/download-assets.py /app/scripts/download-assets.py
ENTRYPOINT ["python", "-m", "fire_modeling"]
CMD ["doctor"]
