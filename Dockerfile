FROM python:3.10.1-alpine

WORKDIR /usr/src

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app app

ENV PYTHONUNBUFFERED=1

ENV SLACK_BOT_TOKEN=''
ENV GDOCS_SERVICE_ACCOUNT_FILENAME=''
ENV AWS_ACCESS_KEY_ID=''
ENV AWS_SECRET_ACCESS_KEY=''

# Allows user to write spreadsheet in container
RUN chown -R 1000:1000 /usr/src
USER 1000:1000

ENTRYPOINT [ "python", "-m", "app.nagbot" ]
CMD [ ]
