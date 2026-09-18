# ---------- Build stage ----------
FROM golang:1.25-alpine AS builder

WORKDIR /app

RUN apk add --no-cache git ca-certificates

COPY go.mod go.sum ./

RUN go mod download

COPY . .

RUN gofmt -w .

RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -trimpath -ldflags="-s -w" \
    -o /project-service ./cmd/server


# ---------- Runtime stage ----------
FROM alpine:3.22

WORKDIR /app

RUN apk add --no-cache ca-certificates wget \
    && addgroup -S appgroup \
    && adduser -S appuser -G appgroup

COPY --from=builder /project-service /app/project-service

RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8080

ENV APP_ENV=production
ENV SERVER_PORT=8080

ENTRYPOINT ["/app/project-service"]
