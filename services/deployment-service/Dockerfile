# Build stage
FROM golang:1.25-alpine AS builder

WORKDIR /app

RUN apk add --no-cache ca-certificates

COPY --from=service_identity . /service-identity
COPY go.mod go.sum ./

RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -trimpath -ldflags="-s -w" \
    -o /deployment-service ./cmd/server

# Runtime stage
FROM alpine:3.22

RUN apk add --no-cache ca-certificates wget kubectl aws-cli \
    && addgroup -g 1000 -S appgroup \
    && adduser -u 1000 -S appuser -G appgroup \
    && mkdir -p /var/lib/cloudforge/kube /home/appuser/.kube /home/appuser/.aws \
    && chown -R appuser:appgroup /var/lib/cloudforge /home/appuser

COPY --from=builder /deployment-service /usr/local/bin/deployment-service

USER appuser

EXPOSE 8082

ENTRYPOINT ["/usr/local/bin/deployment-service"]
