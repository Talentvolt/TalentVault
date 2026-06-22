from rest_framework.throttling import UserRateThrottle, AnonRateThrottle

class BurstRateThrottle(UserRateThrottle):
    """
    Limits high-frequency bursts of requests.
    """
    scope = 'burst'

class SustainedRateThrottle(UserRateThrottle):
    """
    Limits sustained requests over a longer period.
    """
    scope = 'sustained'

class AuthRateThrottle(AnonRateThrottle):
    """
    Strict rate limiting for authentication endpoints to prevent brute-force attacks.
    """
    scope = 'auth'
