FROM python:3.12-slim
WORKDIR /app
COPY server.py .
COPY public ./public
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data PORT=80
RUN mkdir -p /data
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:80/health')"
CMD ["python", "server.py"]
