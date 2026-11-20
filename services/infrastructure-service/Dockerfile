FROM hashicorp/terraform:1.17.2@sha256:6e9c1e647c31a960dc9b59e13272f9111d90010c10b717f77ffb324767660475 AS terraform

FROM golang:1.26.11-alpine@sha256:ecb67f987aa1a57794c91d19ade7ae0209f2f0f5496aaef9e6ae85ddf92d02ab AS builder

WORKDIR /app

RUN apk add --no-cache ca-certificates

COPY --from=service_identity . /service-identity
COPY go.mod go.sum ./
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -trimpath -ldflags="-s -w" \
    -o /infrastructure-service ./cmd/server


FROM alpine:3.22

RUN apk add --no-cache ca-certificates wget \
    && addgroup -g 1000 -S appgroup \
    && adduser -u 1000 -S appuser -G appgroup \
    && mkdir -p /var/lib/cloudforge/terraform \
    && chown -R appuser:appgroup /var/lib/cloudforge

COPY --from=terraform /bin/terraform /usr/local/bin/terraform

COPY --from=builder /infrastructure-service /usr/local/bin/infrastructure-service

RUN terraform version

USER appuser

EXPOSE 8081

ENTRYPOINT ["/usr/local/bin/infrastructure-service"]
