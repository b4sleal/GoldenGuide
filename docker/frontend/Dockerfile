# Static frontend and same-origin API proxy. No Python runtime or backend dependencies.
# Pin the existing local Nginx image by digest; updates are deliberate build changes.
FROM nginx@sha256:df221db836e1754089190208cee7eeda94f233197056426eda74a43ab1abeac2
COPY src/frontend/ /usr/share/nginx/html/
COPY docker/frontend/default.conf.template /etc/nginx/templates/default.conf.template
