package docs

import "embed"

// Files contains the OpenAPI specification and Swagger UI page.
//
//go:embed openapi.yaml index.html
var Files embed.FS
