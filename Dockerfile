FROM weejewel/wg-easy

RUN cp -R /etc/wireguard /data && \
    rm -rf /etc/wireguard && \
    ln -s /data /etc/wireguard