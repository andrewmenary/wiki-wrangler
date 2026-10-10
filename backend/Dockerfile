FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN apt-get update \
	&& apt-get install -y --no-install-recommends git ca-certificates \
	&& rm -rf /var/lib/apt/lists/* \
	&& pip install --no-cache-dir .

COPY app ./app

ENV WIKI_WRANGLER_DATABASE_URL=sqlite:////data/wiki-wrangler.sqlite3
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]