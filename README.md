# Resume

A minimal Nginx container that serves a PDF directly. Links embedded in the PDF
remain interactive in the browser's native PDF viewer.

## Deploy

```sh
cp .env.example .env
mkdir -p public
cp /path/to/resume.pdf public/resume.pdf
docker compose up -d --build
```

Set the external Docker network and a free address in `.env`. Point a reverse
proxy at that address on HTTP port 80. Resume files, deployment settings, Wallet
artifacts, and credentials are intentionally ignored by Git.
