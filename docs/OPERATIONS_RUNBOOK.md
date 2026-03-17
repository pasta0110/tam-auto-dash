# Operations Runbook

## 1. Daily Checks
- Confirm `Guardrails` workflow result is green.
- Confirm Telegram alert arrived for latest main push.
- Confirm app caption shows current ERP extraction timestamp.
- If needed, open `?ops=1` query parameter to verify cache source and render timing.

## 2. If Guardrails Fails
1. Open GitHub Actions run details.
2. Identify failing step:
   - `Compile checks`
   - `Reliability guard`
   - `Perf guard`
3. Apply fix and push.
4. Verify next run sends Telegram success alert.

## 3. Data Contract Errors in App
1. Check app error block for `[code]` value.
2. Validate source CSV columns and formats:
   - `주문번호` not null
   - `배송예정일` parseable
   - `주문유형` in allowed domain
3. Re-run uploader and redeploy.

## 4. Snapshot Issues (Tab2)
1. If tab2 values look stale, verify `erp_run_meta.json` hash fields.
2. Delete `cache/tab2_fixed_compare.pkl` and `cache/tab2_fixed_meta.json` if needed.
3. Reload app to regenerate snapshot.

## 5. Processed Cache Issues (Global)
1. If app rerun speed drops or stale preprocessing is suspected, delete:
   - `cache/processed_data.pkl`
   - `cache/processed_meta.json`
2. Reload app once to rebuild processed cache from current CSV.

## 6. Tab5 Slow Response
1. Tab5 now defaults to **map hidden** mode for faster switching.
2. Click `지도 렌더링` only when you need map visuals.
3. Missing coordinates are not auto-geocoded. Run `누락 주소 좌표 보완 실행` only when needed.

## 7. Emergency Rollback
1. Identify last stable commit hash.
2. Revert specific bad commit (do not force reset shared branch).
3. Push revert commit.
4. Verify Guardrails and Telegram alerts.
