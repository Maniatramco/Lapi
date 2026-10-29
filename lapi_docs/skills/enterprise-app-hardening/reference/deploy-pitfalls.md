# Deploy pitfalls (OCI container instance)

- **Every image uses the release tag**: `api`, `web` **and `keycloak`** are all `<registry>/lapi/<name>:<image_tag>`.
  When only the frontend changes, retag and push all three (`docker tag …:<old> …:<new> && docker push`), not just
  api and web. A missing tag makes the apply fail after the old instance is already destroyed ("image could not
  be pulled because the image does not exist or requires authorization") and the site is down until the next
  apply; Terraform then marks the instance tainted and a re-plan shows 3 add / 1 destroy.
- **Recovery after a failed create**: the next apply tries to delete the tainted instance and OCI may answer the
  DELETE work request with an empty error although the instance ends up DELETED. Check with `cistatus.py`
  (instance: DELETED), then plan again: Terraform refreshes it away and the plan becomes 3 add / 0 destroy.
- An env-var change (for example `keycloak_identity_providers`) also replaces the container instance: plan
  shows 3 add / 3 destroy with the same images.
- Run `terraform plan -out` and `terraform apply <plan>` as separate commands; review Plan: counts before apply.
