
import json
import urllib.request
import urllib.error

base = "https://agent.robinhood.com"
paths = [
    "/.well-known/oauth-protected-resource/mcp/trading",
    "/.well-known/oauth-protected-resource",
    "/.well-known/oauth-authorization-server",
]

for path in paths:
    url = base + path
    print("\nChecking:", url)

    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json"}
    )

    try:
        with urllib.request.urlopen(
            request, timeout=10
        ) as response:
            print("HTTP status:", response.status)
            data = json.load(response)
            print(json.dumps(data, indent=2))

    except urllib.error.HTTPError as error:
        print("HTTP status:", error.code)

    except Exception as error:
        print("Error:", type(error).__name__)
