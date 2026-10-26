# Frontend workflow convention

For any workflow progress UI, use `app/workflow-stepper.tsx` and its shared stylesheet. Follow the section Maintain the application and approved design in the [single handover](../lapi_docs/Lapi_Architecture_and_Deployment_Handover.docx). Actual step names and live statuses are required. Keep the approved compact horizontal blue/white markers, checkmarks, dark-blue rotating ring and incoming particle flow consistent across all workflows. Do not create an independent stepper without an explicit user request to change the standard.

Use `app/agent-logo.tsx` for the Lapi Agent identity and the same handover section. The shared Agent component, global header, sign-in card and browser icon use the Lapi LP monogram (`public/lapi-mark.svg`, with PNG copies `lapi-mark-180.png` and `lapi-mark-512.png`), as requested on 27 October 2026. Keep workflow status icons separate. Preserve legacy assistant route aliases when changing navigation.
