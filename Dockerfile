# The upstream wg-easy version is pinned here once; the companion process reads it
# from WG_EASY_VERSION for the startup banner, the gateways table and the AI tools.
ARG WG_EASY_VERSION=15.5.0
FROM ghcr.io/wg-easy/wg-easy:${WG_EASY_VERSION}
ARG WG_EASY_VERSION
ENV WG_EASY_VERSION=${WG_EASY_VERSION}

WORKDIR /ironflock

# python3 for the companion process; git only while pip installs the Git-pinned
# knowledge library (requirements.txt), then removed again.
COPY requirements.txt .
RUN apk add --no-cache python3 py3-pip \
    && apk add --no-cache --virtual .build-deps git \
    && pip3 install --no-cache-dir -r requirements.txt --break-system-packages \
    && apk del .build-deps

COPY register_device.py endpoint_sync.py vpn_state.py ai_tools.py entrypoint.sh ./
COPY knowledge/ ./knowledge/

WORKDIR /app

CMD ["/ironflock/entrypoint.sh"]
