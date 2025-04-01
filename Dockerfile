FROM ghcr.io/wg-easy/wg-easy:14

COPY entrypoint.sh /entrypoint.sh

CMD "/entrypoint.sh"