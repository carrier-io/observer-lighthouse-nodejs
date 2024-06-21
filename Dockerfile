FROM ibombit/lighthouse-puppeteer-chrome:11.7.1-alpine

# Update packages and install dependencies
RUN apk update && apk add --no-cache python3 py3-pip
RUN pip3 install --upgrade --break-system-packages 'requests==2.32.3' 'pytz'

# Copy scripts into the image
COPY launch.sh /
COPY minio_tests_reader.py /
COPY loop_processing.py /
COPY post_processing.py /
COPY util.py /
COPY engagement_reporter.py /

ENTRYPOINT ["/launch.sh"]
