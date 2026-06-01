# OCR Eval Baseline

Date: 2026-06-01

Command:

```bash
PYTHONPATH=src .venv/bin/python tools/eval_ocr.py
```

Local environment note:

- Python: 3.13.12, while the Windows target runtime is Python 3.11.
- PaddleOCR smoke/eval could not load the local classifier model:
  `data/paddleocr_models/cls/inference.yml` was missing.
- Because OCR failed before parsing, the numbers below are a harness smoke result, not a
  meaningful OCR-quality baseline.

Result:

```text
OCR eval - 2 receipt(s) scored
data_dokumentu   0/1  (0%)
nip              0/2  (0%)
kwota            0/2  (0%)
sprzedawca       0/2  (0%)
nr               0/2  (0%)
```

Next real baseline should be recorded on the target Windows/Python 3.11 setup after
PaddleOCR models are downloaded successfully.
