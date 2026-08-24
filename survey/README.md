# Survey

Ecosystem measurement for RQ1 and RQ2. Method is fixed in
[../docs/methodology.md](../docs/methodology.md).

## Run it

```
pip install "ovrin[survey]"
export GITHUB_TOKEN=...

python survey/sample.py --stratum active --n 500 --seed survey/out/seed-active.jsonl
python survey/crawl.py  --seed survey/out/seed-active.jsonl --out survey/out/records-active.jsonl --history
python survey/analyze.py survey/out/records-active.jsonl
```

The sample is frozen in the seed. The crawler never re-draws it. Commit the seed
and the records before the talk.

## Conduct

Read-only, public endpoints, rate limits honoured. No pull requests against
repositories we do not own. See [../SECURITY.md](../SECURITY.md).
