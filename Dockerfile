FROM ghcr.io/wg-easy/wg-easy:15.1.0

RUN apk add --no-cache python3 py3-pip

WORKDIR /ironflock

COPY requirements.txt .
RUN pip3 install -r requirements.txt --break-system-packages
COPY register_device.py .
COPY entrypoint.sh .

WORKDIR /app

CMD "/ironflock/entrypoint.sh"