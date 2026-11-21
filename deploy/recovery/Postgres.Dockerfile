# PostgreSQL 16 remains supported; keep the upstream base immutable.
FROM postgres:16.16-alpine@sha256:1d5b02d3a9941fbd52437db4107f8c52d6297dac553ca1e5c299ebb3756b4857 AS patched
# The official image bundles gosu built with vulnerable Go stdlib. Native Alpine
# su-exec implements the user/group switch used by docker-entrypoint.sh without
# that Go runtime. Preserve both executable names expected by the upstream image.
RUN apk add --no-cache su-exec=0.3-r0 \
    && rm /usr/local/bin/gosu /usr/local/bin/su-exec \
    && ln -s /sbin/su-exec /usr/local/bin/gosu \
    && ln -s /sbin/su-exec /usr/local/bin/su-exec \
    && gosu postgres sh -c 'test "$(id -u)" = 70' \
    && su-exec 65534:65534 sh -c 'test "$(id -u)" = 65534'

# Copy the final filesystem into a clean runtime so deleted Go binaries are not
# distributed in lower layers. Preserve the official runtime contract explicitly.
FROM scratch
COPY --from=patched / /
ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    LANG=en_US.utf8 PG_MAJOR=16 PG_VERSION=16.16 PGDATA=/var/lib/postgresql/data
VOLUME /var/lib/postgresql/data
EXPOSE 5432
USER 70:70
STOPSIGNAL SIGINT
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["postgres"]
