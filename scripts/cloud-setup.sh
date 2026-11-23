#!/usr/bin/env bash
# One-time setup of the Google Cloud project that runs the question API, by its owner:
#
#   scripts/cloud-setup.sh <project id>
#
# Create the project and its budgets in the console first, and sign in to gcloud with the owner's
# account. The script enables the APIs, then creates:
# - the image repository, which keeps the last two images;
# - an account that runs the API and one that deploys it;
# - GitHub's access to the deploying account, for the Deploy workflow of the main branch only;
# - the secret that holds the Groq key, which it asks for.
# It also leaves Cloud Run's request logs out of storage: they would be billed outside the spend
# cap of Cloud Run. It prints the variables to set on the GitHub repository. Running it again
# changes nothing that exists.
set -euo pipefail

project=${1:?usage: scripts/cloud-setup.sh <project id>}
region=europe-west9
repository=zkyasin/france-load-forecast
# GitHub's numeric IDs of the repository and of its owner: unlike their names, they cannot pass
# to someone else.
repository_id=1466895893
owner_id=263354047
workflow=$repository/.github/workflows/deploy.yml@refs/heads/main
run_account=questions-run@$project.iam.gserviceaccount.com
deploy_account=questions-deploy@$project.iam.gserviceaccount.com

gc() { gcloud --project "$project" --quiet "$@"; }
exists() { "$@" >/dev/null 2>&1; }
# A new service account takes up to a minute before roles can be granted to it.
retry() {
  for _ in 1 2 3 4 5 6; do
    "$@" && return
    sleep 10
  done
  "$@"
}

gc services enable cloudresourcemanager.googleapis.com iam.googleapis.com \
  run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com \
  iamcredentials.googleapis.com sts.googleapis.com
number=$(gc projects describe "$project" --format 'value(projectNumber)')
pool=projects/$number/locations/global/workloadIdentityPools/github

exists gc artifacts repositories describe api --location "$region" ||
  gc artifacts repositories create api --repository-format docker --location "$region"
policy=$(mktemp)
trap 'rm -f "$policy"' EXIT
cat >"$policy" <<'EOF'
[
  {"name": "keep-two", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 2}},
  {"name": "delete-others", "action": {"type": "Delete"}, "condition": {"tagState": "any"}}
]
EOF
gc artifacts repositories set-cleanup-policies api --location "$region" --policy "$policy" \
  --no-dry-run

for account in questions-run questions-deploy; do
  exists gc iam service-accounts describe "$account@$project.iam.gserviceaccount.com" ||
    gc iam service-accounts create "$account"
done
retry gc projects add-iam-policy-binding "$project" --condition None \
  --member "serviceAccount:$deploy_account" --role roles/run.admin
retry gc artifacts repositories add-iam-policy-binding api --location "$region" \
  --member "serviceAccount:$deploy_account" --role roles/artifactregistry.writer
retry gc iam service-accounts add-iam-policy-binding "$run_account" \
  --member "serviceAccount:$deploy_account" --role roles/iam.serviceAccountUser

# GitHub Actions may act as the deploying account from the Deploy workflow of the main branch of
# this repository, and from no other job.
exists gc iam workload-identity-pools describe github --location global ||
  gc iam workload-identity-pools create github --location global --display-name GitHub
provider=(
  france-load-forecast --location global --workload-identity-pool github
  --attribute-mapping "google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.repository_owner_id=assertion.repository_owner_id,attribute.workflow_ref=assertion.workflow_ref"
  --attribute-condition "assertion.repository_id == '$repository_id' && assertion.repository_owner_id == '$owner_id' && assertion.workflow_ref == '$workflow'"
)
if exists gc iam workload-identity-pools providers describe france-load-forecast \
  --location global --workload-identity-pool github; then
  gc iam workload-identity-pools providers update-oidc "${provider[@]}"
else
  gc iam workload-identity-pools providers create-oidc "${provider[@]}" \
    --issuer-uri https://token.actions.githubusercontent.com
fi
retry gc iam service-accounts add-iam-policy-binding "$deploy_account" \
  --member "principalSet://iam.googleapis.com/$pool/attribute.repository_id/$repository_id" \
  --role roles/iam.workloadIdentityUser

# The Groq key, kept in the region of the API and read by the account that runs it.
if ! exists gc secrets describe groq-api-key; then
  read -rsp "Groq API key (not shown): " key
  echo
  printf '%s' "$key" | gc secrets create groq-api-key --data-file - \
    --replication-policy user-managed --locations "$region"
fi
retry gc secrets add-iam-policy-binding groq-api-key \
  --member "serviceAccount:$run_account" --role roles/secretmanager.secretAccessor

# Requests that Cloud Run turns away when its instance is busy are logged but never billed to
# Cloud Run, so its spend cap would not stop a flood of them.
sink=$(gc logging sinks describe _Default)
grep -q 'name: run-requests' <<<"$sink" ||
  gc logging sinks update _Default \
    --add-exclusion 'name=run-requests,filter=log_id("run.googleapis.com/requests")'

cat <<EOF

Set these variables on GitHub, in Settings > Secrets and variables > Actions > Variables:
  GCP_PROJECT_ID                  $project
  GCP_WORKLOAD_IDENTITY_PROVIDER  $pool/providers/france-load-forecast
  GCP_DEPLOY_SERVICE_ACCOUNT      $deploy_account
  GCP_RUN_SERVICE_ACCOUNT         $run_account
Then run the Deploy workflow from the Actions tab, and set API_URL to the address it shows.
EOF
