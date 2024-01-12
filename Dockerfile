FROM ibombit/lighthouse-puppeteer-chrome:11.1.0-alpine

# Update packages and install dependencies
RUN apk update && apk add --no-cache python3 py3-pip
RUN pip3 install --upgrade 'requests==2.20.0' 'pytz'

COPY launch.sh /
COPY minio_tests_reader.py /
COPY results_processing.py /
COPY util.py /

ENTRYPOINT ["/launch.sh"]