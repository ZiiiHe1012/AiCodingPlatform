FROM node:22-bookworm-slim AS javascript
WORKDIR /opt/codelab/js
COPY --chmod=0644 package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM python:3.12-slim-bookworm
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=4 update \
    && apt-get -o Acquire::Retries=4 install -y --no-install-recommends chromium fonts-wqy-zenhei
RUN pip install --no-cache-dir pytest==8.3.5
COPY --from=javascript /usr/local/bin/node /usr/local/bin/node
COPY --from=javascript /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm
COPY --from=javascript /opt/codelab/js /opt/codelab/js
COPY --chmod=0644 entry.py preview.cjs /opt/codelab/
COPY --chmod=0644 js-entry.mjs vitest.config.mjs /opt/codelab/js/
ENV HOME=/tmp/home npm_config_cache=/tmp/npm-cache CI=1
USER 65534:65534
ENTRYPOINT ["python", "-I", "/opt/codelab/entry.py"]
