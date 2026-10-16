FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY public/resume.pdf /usr/share/nginx/html/resume.pdf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --quiet --spider http://127.0.0.1/ || exit 1
