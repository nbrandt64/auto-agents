FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py create_tables.py entrypoint.sh ./
RUN chmod +x entrypoint.sh

RUN adduser --disabled-password --no-create-home appuser
USER appuser


EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
