# RCA: calculator-app Auth Failure
Root Cause: Missing allUsers IAM binding.
Fix: gcloud run services add-iam-policy-binding calculator-app --member='allUsers' --role='roles/run.invoker'
Link: https://calculator-app-912533822336.us-central1.run.app