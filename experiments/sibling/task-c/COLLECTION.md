# Collecting the inventory trial

The trial uses the [registered](PREREGISTRATION.md) compiler, guide, libraries, prompts and commands. The A/B repository records the Haiku family; its historical model snapshot, full prompts and CLI version are unavailable. Record the concrete Haiku model returned in each new transcript. The supplied collector provides a common prompt and requires the same image and requested model for all 18 attempts. The compiler and guide come from commit `01a91593241803567c35534acbe3e041d4936b11`.

Build the solver image from the repository root. The host needs Git, Python 3.11+, Docker and an authenticated Claude Code credential supplied in the environment. Use a Docker network whose egress permits the selected model provider and required package registries and blocks repository, search and general web access. The image contains the frozen compiler and toolchains. Each solver sees its workspace and a Unix socket. The controller keeps future instructions, snapshots, reference programs and other submissions outside the container.

```sh
experiments/sibling/environment/build.sh
python experiments/sibling/collect_c.py /absolute/path/to/inventory-run \
    --model "$HAIKU_MODEL_ID" --network "$TRIAL_NETWORK"
```

Each solver gets a fresh container and one Claude Code session for all six steps. Each `./next` snapshots the workspace and reveals one instruction. The collector retains prompts, raw stream-JSON transcripts, stderr, tool usage, the resolved image ID, final workspaces and all 108 snapshots. Interrupted attempts remain available for adjudication. Reinvoking the collector skips completed runs and reports unfinished attempts.

Grade using the same frozen image. Mount the collector checkout read-only for the grading code; the modeller containers never receive this mount. The runtime benchmark counts hidden-fixture errors under the registered oracle. A second workspace records the result of the prescribed static check for each snapshot. The grader verifies 18 distinct transcripts, six snapshots per solver and 144 scored units per solver. The primary output-token measure sums assistant usage entries exactly as A and B did. The report also records token totals by unique message ID and the CLI's reported total. Investigate discrepancies before interpreting a token comparison.

```sh
docker run --rm --user "$(id -u):$(id -g)" --network "$TRIAL_NETWORK" \
    -e HOME=/tmp/grade-home -v "$PWD:/study:ro" \
    -v /absolute/path/to/inventory-run:/run-data \
    b-sibling-c:0.32 sh -ec 'mkdir -p "$HOME/.cache"; cp -r /opt/seed-cache "$HOME/.cache/b"; exec python /study/experiments/sibling/grade_all.py task-c /run-data /run-data/agents.json /run-data/transcripts'
```

Keep the raw run bundle with the results. Review transcripts for protocol violations before reporting. A reference build, smoke test or run with a different model contributes no solver observations.
