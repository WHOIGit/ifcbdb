# Scope vocabulary for API keys. A scope is a `resource:action` string.
# Keys store a list of granted scopes; a scope requirement is satisfied
# by an exact match, a namespace wildcard ("bins:*"), or the global
# wildcard ("*").

BIN_READ = "bins:read"
BIN_SYNC = "bins:sync"


def scopes_allow(scopes, required):
    "Whether the given list of granted scopes satisfies the required scope."
    for scope in scopes:
        if scope == required or scope == "*":
            return True
        # a namespaced wildcard ("bins:*") grants everything in its namespace
        if scope.endswith(":*") and required.startswith(scope[:-1]):
            return True
    return False
