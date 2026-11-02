---
name: calibrate-fss
description: Recalibrate the overlay's FSS spectrum predictor - relearn which spectrum slot each body class lights from the saved FSS captures and the journal, score it, write overlay/src/slots.rs, rebuild and restart the overlay. Use when asked to calibrate, recalibrate or retrain the FSS spikes, slots, bands or spectrum, or after flying systems that raised FSS warnings.
---

# Calibrate the FSS slot table

`overlay/FSS_SPECTRUM.md` explains the spectrum model; read it first.
The overlay predicts body classes from the slots the spectrum's waves light, using the table in `overlay/src/slots.rs`.

## 1. Data

- Captures live in `log/fss/`; the truth is the game journals.
- The overlay keeps only `last.png` unless learning mode is on.
  To collect every system, tick "Keep every FSS screenshot" on the Settings tab; otherwise only `last.png` is kept.
  The overlay writes to `overlay/target/release/screenshots`, a junction to `log/fss`; recreate it with `mklink /J overlay\target\release\screenshots log\fss` if a clean build removed it.
- A system teaches most when the commander scans all of it with the game focused, holds the FSS open a second after the last scan, and leaves the bodies of a weak class until last.

## 2. Learn and score

```bash
python scripts/fss_slots.py --score
```

- It prints every slot's owner, the classes with no slot yet, and a leave-one-system-out score: classes right, false, missed, and unknown slots.
- Compare with the last score in `overlay/FSS_SPECTRUM.md`.
  Write the table only if right did not fall and false and missed did not rise, unless new classes gained slots.

## 3. Write and test

```bash
python scripts/fss_slots.py --write
cd overlay && cargo test --release -j 8
```

- `git diff overlay/src/slots.rs` shows what changed; report the new and lost slots.
- Every test must pass.

## 4. Rebuild and restart

- Restart when ready; the commander does not need to be asked.
  A restart drops the current system's prediction, which is in memory, so say to reopen the FSS to get it back.
- Close the overlay cleanly, build, and start it (the start-overlay skill):

  ```bash
  powershell -NoProfile -Command "$p=Get-Process explorers-companion; $p.CloseMainWindow() | Out-Null; $p.WaitForExit(15000)"
  cd overlay && cargo build --release -j 8
  ```

## 5. Record

- Update the last score and the classes with no slot in `overlay/FSS_SPECTRUM.md`.
- Report the score, the slots gained and lost, and the classes still missing.
