# Feature review checklist

- [ ] Does the final commit pass Ruff and pytest?
- [ ] Does the endpoint/UI contract preserve CSRF, ownership, rate-limit, escaping, and expiration behavior?
- [ ] Are time zones explicit (UTC storage; America/Denver display)?
- [ ] Do new public claims have a source or an honest limitation label?
- [ ] Are changes compatible with a mobile keyboard and screen-reader navigation?
- [ ] Does the PR leave evolution disabled and deployment promotion manual?
