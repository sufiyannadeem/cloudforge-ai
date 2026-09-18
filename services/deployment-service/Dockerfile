# Build stage
FROM golang:1.25-alpine AS builder

WORKDIR /app

RUN apk add --no-cache ca-certificates

COPY go.mod go.sum ./

RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -trimpath -ldflags="-s -w" \
    -o /deployment-service ./cmd/server

# Runtime stage
FROM alpine:3.22

RUN apk add --no-cache ca-certificates wget \
    && addgroup -S appgroup \
    && adduser -S appuser -G appgroup

COPY --from=builder /deployment-service /usr/local/bin/deployment-service

USER appuser

EXPOSE 8082

ENTRYPOINT ["/usr/local/bin/deployment-service"]
