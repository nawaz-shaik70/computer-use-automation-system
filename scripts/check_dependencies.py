from importlib import metadata
from packaging.requirements import Requirement

pending = ["capability-runner"]
seen = set()
while pending:
    name = pending.pop()
    if name.lower() in seen:
        continue
    seen.add(name.lower())
    distribution = metadata.distribution(name)
    for raw in distribution.requires or []:
        requirement = Requirement(raw)
        if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
            continue
        installed = metadata.version(requirement.name)
        if requirement.specifier and installed not in requirement.specifier:
            raise SystemExit(f"Dependency mismatch: {requirement.name}")
        pending.append(requirement.name)
print(f"Validated {len(seen)} distributions in the runtime dependency closure.")
