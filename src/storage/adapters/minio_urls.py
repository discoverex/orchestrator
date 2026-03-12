from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def parse_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError("object URI must start with s3://")
    body = uri[5:]
    parts = body.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError("object URI must be s3://bucket/key")
    return parts[0], parts[1]


def rewrite_presigned_url(url: str, base_url: str) -> str:
    if not base_url:
        return url
    base_value = base_url if "://" in base_url else f"https://{base_url}"
    public = urlsplit(base_value)
    signed = urlsplit(url)
    path = signed.path
    if public.path and public.path != "/":
        path = f"{public.path.rstrip('/')}{signed.path}"
    return urlunsplit(
        (
            public.scheme or signed.scheme,
            public.netloc or signed.netloc,
            path,
            signed.query,
            signed.fragment,
        )
    )
