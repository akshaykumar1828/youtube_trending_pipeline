# syntax=docker/dockerfile:1
#
# One-off database tool (Compose service `dbtools`, profile "tools"). NOT part of the
# running application. It is the only thing that ever receives the PostgreSQL admin
# credentials, and only while a command runs:
#   seed     restore the 9 raw YouTube tables from a dump into an EMPTY deployment database
#   migrate  apply backend/migrations (unchanged runner) and set the two app role passwords
#   status   list applied / pending migrations
# Build context: repository root.

FROM postgres:18-alpine
RUN apk add --no-cache python3 py3-dotenv
COPY backend/scripts/migrate.py /opt/app/backend/scripts/migrate.py
COPY backend/migrations/ /opt/app/backend/migrations/
COPY deploy/dbtools/dbtools.sh /usr/local/bin/dbtools
RUN chmod 0755 /usr/local/bin/dbtools
USER postgres
WORKDIR /opt/app
ENTRYPOINT ["dbtools"]
CMD ["status"]
