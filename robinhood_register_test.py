
import urllib.request
import urllib.error

url = "https://agent.robinhood.com/oauth/trading/register"

print("Checking Robinhood registration endpoint")

request = urllib.request.Request(
    url,
    method="GET",
    headers={"Accept": "application/json"}
)

try:
    with urllib.request.urlopen(request, timeout=10) as response:
        print("HTTP status:", response.status)
        print("Content type:", response.headers.get("Content-Type"))
        print("Allow:", response.headers.get("Allow"))

except urllib.error.HTTPError as error:
    print("HTTP status:", error.code)
    print("Content type:", error.headers.get("Content-Type"))
    print("Allow:", error.headers.get("Allow"))

except Exception as error:
    print("Connection error:", type(error).__name__)
