# 00-SESSION-START — the first thing every backend session does (2026-09-15)

The toolkit lives in GitHub: `https://github.com/AysegulSuPzy/vepine-toolkit` (public, no token).
Never copy toolkit or rule docs out of the project with `project_read` — the project copies under `toolkit/` are legacy
and may be stale. The repo is the source of truth.

## Step A — clone (one command, zero model tokens)

    rm -rf /home/claude/work && git clone -q https://github.com/AysegulSuPzy/vepine-toolkit.git /home/claude/work && cd /home/claude/work

## Step B — integrity check

    awk '/^```$/{f=!f;next} f' MANIFEST.md > MANIFEST.sha256 && sha256sum -c MANIFEST.sha256 --quiet

Expected: only the two credentials lines (`./shopify-api-credentials.md`, `./rules/dataforseo-credentials.md`) report
"No such file" — they are not in the repo by design. Any OTHER FAILED line means a file was edited in the repo without its
MANIFEST line being recomputed: report it in the run log and continue; do not re-copy from the project.

## Step C — credentials (the only two project docs a run still reads)

1. `project_read toolkit/shopify-api-credentials.md` → write `secrets/shopify.json` as README step 1 says.
2. `project_read dataforseo-credentials.md` → write it to `rules/dataforseo-credentials.md` (kw_measure.py reads it there).

`secrets/` is git-ignored; nothing in it is ever pushed.

## Step D — continue with README-toolkit.md

Open `README-toolkit.md` in the clone and follow it from step 1 (its step 0 is Step B above).

## When a toolkit file changes during a run

Edit it on disk, recompute its `sha256sum` line in MANIFEST.md, and hand BOTH files to the user (SendUserFile) to upload
to the repo at `https://github.com/AysegulSuPzy/vepine-toolkit/upload/main`. Do not write toolkit files to the project
any more — only `claude/backup-titles-<tag>.md` and `claude/run-log-<tag>.md` go there (README "Where run artefacts go").
