"""One module per upstream source.

Nothing outside this package may call an upstream URL. Each adapter owns its credentials,
quota, retry policy, licence metadata, and response schema (`.cursorrules` § 5).
"""
