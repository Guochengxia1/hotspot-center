FROM python:3.12-slim

WORKDIR /app
COPY server.py index.html README.md ./

ENV HOST=0.0.0.0
ENV PORT=8788
ENV REFRESH_SECONDS=3600

EXPOSE 8788

CMD ["python", "server.py"]
