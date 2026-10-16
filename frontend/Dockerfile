# GEIF — interface web (portail contribuable + espace agents), servie par nginx. Contexte : ./frontend
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY . /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD wget -qO- http://localhost/index.html >/dev/null || exit 1
