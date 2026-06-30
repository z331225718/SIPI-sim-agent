# Agent-Spice

Agent-Spice is an early PI simulation middleware prototype focused on HSPICE legacy deck compatibility and future S-parameter/CPM workflows.

Current checkpoint:

- HSPICE project manifest parsing.
- HSPICE deck audit for directives, includes, libraries, and unsupported commands.
- `.alter` expansion into independent cases.
- `.measure/.probe/.print` normalization.
- Compatibility report and basic HSPICE-to-backend conversion.

Run tests:

```powershell
python -m pytest -v
```

The project spec is in `docs/pi-spice-simulator-spec.md`.

