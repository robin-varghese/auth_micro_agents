# Root Cause Analysis: Authentication Failure for Cloud Run Service @calculator-app@

## 1. Executive Summary
The `calculator-app` service in project `vector-search-poc` is currently inaccessible to the public. Investigation reveals that the service is healthy and running, but it is missing the necessary IAM permissions to allow unauthenticated invocations. This results in a `403 Forbidden` error from the Google Frontend (GFE).

## 2. Technical Context & Impact
- **Affected Service**: `calculator-app`
- **Region**: `us-central1`
- **Impact Duration**: Ongoing (Detected 2026-02-18T16:33:48Z)
- **User Impact**: 100% of unauthenticated users receive a "403 Forbidden" error.

## 3. Timeline & Detection
- **Detection Timestamp**: 2026-02-18T16:33:48Z
- **Detection Method**: Manual `curl` verification and IAM policy inspection.
- **Verification Command**: `curl -i https://calculator-app-qcdyf5u6mq-uc.a.run.app`
- **Result**: `HTTP/2 403 Forbidden` from `Google Frontend`.

## 4. Root Cause Analysis (5 Whys)
1. **Why is the app failing?** Users receive a 403 Forbidden error when accessing the URL.
2. **Why is the GFE returning 403?** The request is not authenticated and the service requires authentication.
3. **Why does the service require authentication?** The IAM policy for the service does not include a binding for `allUsers` with the `roles/run.invoker` role.
4. **Why is the binding missing?** Likely a redeployment or manual change reverted the previously applied fix from 2026-02-02.

## 5. Technical Evidence
### IAM Policy Check:
```bash
gcloud run services get-iam-policy calculator-app --project=vector-search-poc --region=us-central1
```
**Output**:
```json
{
  "etag": "BwZLDNRTCiw=",
  "version": 1
}
```
*Confirmed: No member bindings found.*

## 6. Remediation & Fix
To restore public access, the following command must be executed:

```bash
gcloud run services add-iam-policy-binding calculator-app \
  --member="allUsers" \
  --role="roles/run.invoker" \
  --project="vector-search-poc" \
  --region="us-central1"
```

## 7. Prevention Plan
- Ensure that CI/CD pipelines for `calculator-app` explicitly include the public access binding step.
- Implement monitoring to check for 403 error spikes at the GFE level.

## 8. Confidence Score
- **Confidence**: 100%
- **Justification**: The 403 error specifically points to authentication, and the IAM policy is confirmed to be empty.
