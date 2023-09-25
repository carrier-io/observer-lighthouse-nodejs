FROM ibombit/lighthouse-puppeteer-chrome:2.0-alpine

# Update packages and install dependencies
RUN apk update && apk add --no-cache python3 py3-pip
RUN pip3 install --upgrade 'requests==2.20.0' 'pytz'

# Copy scripts into the image
COPY launch.sh /
COPY minio_tests_reader.py /
COPY loop_processing.py /
COPY post_processing.py /
COPY util.py /
COPY engagement_reporter.py /

ENTRYPOINT ["/launch.sh"]