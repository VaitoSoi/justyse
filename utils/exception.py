class TokenInvalid(ValueError):
    pass


class TokenExpired(TokenInvalid):
    pass


class TokenNotFound(TokenInvalid):
    pass


class SignatureInvalid(TokenInvalid):
    pass
