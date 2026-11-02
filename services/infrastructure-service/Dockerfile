FROM hashicorp/terraform:1.16.4 AS terraform

FROM golang:1.25-alpine AS builder

WORKDIR /app

RUN apk add --no-cache ca-certificates

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
