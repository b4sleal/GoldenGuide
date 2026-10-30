"""Browser security headers added to every HTTP response.

The Content-Security-Policy is built once at startup (configuration errors fail the boot,
not a request) and then appended to each response.
"""
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, production: bool, frame_ancestors: str, additional_csp: str):
        self.app = app
        self.production = production
        self.frame_ancestors = frame_ancestors

        # Step 1: baseline sources the frontend needs. Libraries are allowed by exact origin
        # rather than a broad `https:` so an injected script from elsewhere cannot load.
        defaults = {
            "script-src": ["'self'", "https://cdn.jsdelivr.net"],
            "style-src": ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com", "https://cdn.jsdelivr.net"],
            "font-src": ["'self'", "data:", "https://fonts.gstatic.com"],
            "img-src": ["'self'", "data:", "blob:", "https:"],
            "connect-src": ["'self'"],
        }

        # Step 2: deployment-specific additions from CSP_ADDITIONAL_SOURCES, e.g.
        # "script-src=https://cdn.example.com;connect-src=https://api.example.com".
        # Unknown directives raise so a typo cannot silently weaken or break the policy.
        for assignment in filter(None, (entry.strip() for entry in additional_csp.split(";"))):
            directive, separator, values = assignment.partition("=")
            if not separator or directive not in defaults:
                raise ValueError(f"Unsupported CSP directive: {directive}")
            defaults[directive].extend(values.split())

        # Step 3: development only, relax rules needed by local tooling (hot reload, devtools).
        if not production:
            defaults["script-src"].extend(["'unsafe-inline'", "'unsafe-eval'"])
            defaults["connect-src"].extend(["ws://localhost:8080", "ws://127.0.0.1:8080"])

        # Step 4: frame-ancestors controls which sites may iframe GoldenGuide
        # ('none' by default; set FRAME_ANCESTORS to the approved WLU origins to embed).
        if not frame_ancestors.strip():
            raise ValueError("FRAME_ANCESTORS cannot be empty")

        # Step 5: assemble the final header value (dict.fromkeys de-duplicates, keeping order).
        policies = ["default-src 'self'"] + [
            f"{key} {' '.join(dict.fromkeys(values))}" for key, values in defaults.items()
        ]
        policies += ["object-src 'none'", "base-uri 'self'", f"frame-ancestors {frame_ancestors}", "form-action 'self'"]
        self.policy = "; ".join(policies)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Add the headers to the response start message; the body passes through untouched.
        async def secured_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                policy = self.policy
                script_hashes = scope.get("state", {}).get("csp_script_hashes", ())
                if script_hashes:
                    sources = " ".join(f"'{digest}'" for digest in script_hashes)
                    policy = policy.replace("script-src ", f"script-src {sources} ", 1)
                additions = {
                    "content-security-policy": policy,
                    "x-content-type-options": "nosniff",
                    "referrer-policy": "strict-origin-when-cross-origin",
                    "permissions-policy": "camera=(), microphone=(), geolocation=()",
                }
                # Legacy header for old browsers. It cannot list allowed origins, so it is
                # only sent when framing is fully disabled; CSP frame-ancestors covers the rest.
                if self.frame_ancestors == "'none'":
                    additions["x-frame-options"] = "DENY"
                # HSTS only over real HTTPS deployments; on localhost it would pin http users out.
                if self.production:
                    additions["strict-transport-security"] = "max-age=31536000; includeSubDomains"
                headers.extend((k.encode(), v.encode()) for k, v in additions.items())
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, secured_send)
