
import urllib.request
import urllib.error

url = "https://agent.robinhood.com/mcp/trading"

request = urllib.request.Request(
    url,
    method="GET"
)

try:
    with urllib.request.urlopen(request, timeout=10) as response:
        print("HTTP status:", response.status)
except urllib.error.HTTPError as error:
    print("HTTP status:", error.code)
except Exception as error:
    print("Connection error:", type(error).__name__)
