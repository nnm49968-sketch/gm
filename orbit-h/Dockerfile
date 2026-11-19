FROM python:3.12-slim
WORKDIR /srv/orbit
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --system --uid 10001 orbit && mkdir data && chown orbit data
COPY app.py puzzles.py rounds_a.py rounds_b.py ./
COPY static ./static
USER orbit
EXPOSE 8080
CMD ["waitress-serve", "--listen=0.0.0.0:8080", "--threads=8", "--url-scheme=https", "--call", "app:create_app"]
