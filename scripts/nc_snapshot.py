"""Read cluster price/billing evidence locally; never serialize the API token."""
import datetime
import json
from pathlib import Path
from urllib.request import Request, urlopen

token = (Path.home() / ".config/nationalcompute/token").read_text().strip()
cluster = "us-mi355-k8s-niveditha"
result = {"read_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
for name, path in {
    "bid": f"/api/k8s/bid?cluster={cluster}",
    "market_spend": f"/api/k8s/market/spend?cluster={cluster}",
    "billing_balance": "/api/billing/balance",
}.items():
    with urlopen(Request("https://nationalcompute.com" + path,
                         headers={"Authorization": "Bearer " + token}), timeout=30) as response:
        result[name] = json.load(response)
print(json.dumps(result, indent=2))
