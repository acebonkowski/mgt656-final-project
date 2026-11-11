import hashlib


def nickname_hash(nickname):
    """First 7 hex chars of sha1(nickname), like `printf %s <nickname> | shasum`.

    Surrounding whitespace is stripped so a stray newline in an env var can't
    produce the `echo`-style wrong hash.
    """
    return hashlib.sha1(nickname.strip().encode("utf-8")).hexdigest()[:7]
