"""Recompute sha256_repo for every code entry in config/inputs.json (after an intentional edit). `make inputs-json` calls this."""
import hashlib, json
c = json.load(open("config/inputs.json"))
for e in c["inputs"]["code"]:
    e["sha256_repo"] = hashlib.sha256(open(e["repo_path"], "rb").read()).hexdigest()
json.dump(c, open("config/inputs.json", "w"), indent=1)
print(len(c["inputs"]["code"]), "code entries rehashed")
