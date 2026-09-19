# Demo Video Guide

Target length: 3-5 minutes, matching the "Demo Script" scenes in the
project brief (SCENE 1 through SCENE 16).

## Before recording

- Run `python src/scripts/seed.py --complaints 500 --reset` for a clean,
  reproducible dataset.
- Log out of all demo accounts; have the four credentials ready to paste.
- Have the admin console's Jurisdiction Versions page open in a second tab
  for the boundary-change scene.

## Suggested shot list

1. Landing page -> "Report an Issue" (citizen).
2. Submit a pothole complaint near a school; show the duplicate-detection
   prompt if one fires naturally, or use `/api/demo/scenario/duplicate` as
   a fallback to guarantee the moment.
3. Show the resulting priority/risk explanation panels.
4. Switch to officer login; show the queue sorted by risk, open the
   complaint, assign a field worker.
5. Switch to field worker login (or app); start the task, simulate offline
   (airplane mode / devtools throttling), complete it, reconnect, show the
   sync toast.
6. Officer closes the complaint as RESOLVED.
7. Public dashboard: ward view, "why is this ward behind" panel.
8. Admin: publish a new jurisdiction version for Ward 42, show the same
   coordinate routing differently before/after while the earlier complaint's
   `jurisdiction` view is unchanged.
9. Admin: run the Dasara surge simulation, show live processed/queued
   counters without the UI freezing.
10. Close on the "Demo dataset - synthetic data" disclaimer visible in
    frame, to make the honesty explicit on camera.

## After recording

- Trim to 3-5 minutes.
- Export and compute its SHA-256 hash for `resource.md`.
