FROM ibombit/lighthouse-puppeteer-chrome:13.1.0-alpine-light

# Update packages and install dependencies
RUN apk update && apk add --no-cache python3 py3-pip git
RUN pip3 install --upgrade --break-system-packages 'requests==2.32.3' 'pytz' 'junit-xml'
RUN pip3 install --break-system-packages git+https://github.com/carrier-io/loki_logger.git

# Copy scripts into the image
COPY launch.sh /
COPY minio_tests_reader.py /
COPY carrier_logger.py /
COPY loop_processing.py /
COPY post_processing.py /
COPY util.py /
COPY engagement_reporter.py /
COPY junit_reporter.py /

ENTRYPOINT ["/launch.sh"]
