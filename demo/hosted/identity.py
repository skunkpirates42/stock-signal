"""Provider-neutral OIDC ID-token verification at the login boundary only."""
from dataclasses import dataclass
import hmac
import math
from urllib.parse import urlsplit

import jwt

from .store import Denied


@dataclass(frozen=True)
class Identity:
    issuer: str
    subject: str


class OIDCVerifier:
    def __init__(self, issuer, audience, jwks_url, *, jwks=None):
        for url in (issuer, jwks_url):
            parsed = urlsplit(url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.fragment:
                raise ValueError("OIDC requires configured HTTPS endpoints")
        if not isinstance(audience, str) or not audience:
            raise ValueError("OIDC audience required")
        self.issuer, self.audience = issuer, audience
        # No permanent per-key cache: retired keys disappear after the JWKS TTL.
        # Unknown kid triggers PyJWT's one refresh against this configured URL.
        self.jwks = jwks or jwt.PyJWKClient(jwks_url, cache_keys=False, lifespan=60, timeout=5)

    def verify(self, token, expected_nonce):
        try:
            if not isinstance(token, str) or not 1 <= len(token) <= 16384:
                raise ValueError()
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str) or not header["kid"] or header.get("crit"):
                raise ValueError()
            key = self.jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(token, key, algorithms=["RS256"], audience=self.audience,
                                issuer=self.issuer, options={"require": ["iss", "sub", "aud", "exp", "iat", "nonce"]})
            for name in ("iat", "exp", "nbf"):
                if name in claims and (type(claims[name]) not in (int, float) or not math.isfinite(claims[name])):
                    raise ValueError()
            if not isinstance(claims["sub"], str) or not 1 <= len(claims["sub"]) <= 255:
                raise ValueError()
            if not isinstance(claims["nonce"], str) or not hmac.compare_digest(claims["nonce"], expected_nonce):
                raise ValueError()
            if claims.get("azp", self.audience) != self.audience:
                raise ValueError()
            if isinstance(claims["aud"], list) and len(claims["aud"]) > 1 and claims.get("azp") != self.audience:
                raise ValueError()
            return Identity(self.issuer, claims["sub"])
        except Exception:
            # Never propagate JWT, HTTP, path or key details into API errors.
            raise Denied() from None
