# 12 — The Jarvis Core Machine

*What the dedicated box is actually for, sized against the workload rather than against
enthusiasm. The headline: the GPU is for the subconscious, not for a frontier model — and
that reframe makes the machine roughly four times cheaper than the usual "local AI rig"
answer.*

---

## 1. What it actually runs

| Workload | Resource profile | Always on? |
|---|---|---|
| Jarvis Core — router, policy, ledger writer | ~1 GB RAM, negligible CPU | Yes |
| Control plane gateway | ~1–2 GB RAM | Yes |
| **The Record** — event store, CAS blobs, keystore | Disk + write throughput | Yes |
| **Indexes** — vector + FTS + causal graph | RAM-hungry (page cache) | Yes |
| **Subconscious** — consolidation, extraction, reranking | **GPU, resident** | Idle-time + on query |
| Local STT (Whisper-class) | **GPU, resident** | Yes — must not page in |
| Local TTS (Piper/Kokoro-class) | **GPU or CPU, resident** | Yes |
| Wake word | Negligible — runs on the *satellites*, not here | Yes |
| Home Assistant | ~2 GB RAM | Yes |
| Agent sandboxes / worktrees | CPU + RAM + fast NVMe, bursty | On demand |
| Embedding backfill | GPU batch or overnight CPU | Nightly |

Frontier reasoning bursts to cloud. That is the correct division and it is what makes the
box affordable.

---

## 2. The reframe that changes the budget

The usual local-AI question is *"can this machine run a big model?"* Wrong question here.
Nothing in §1 needs a frontier model locally. The local model's jobs are:

speech-to-text · text-to-speech · query planning · retrieval reranking · fact and skill
extraction from traces · classification · **salience scoring for the proactivity plane**

Every one of those is a small-model job. A good 14B at Q4 does all of it well. That moves
the target from ~$8,000 (run a 200B locally) to **~$2,500** (run a 14–32B, always resident,
fast).

**And residency is the real constraint, not peak capability.** Standard VRAM advice sizes
for one model at a time. This machine needs STT *and* TTS *and* the subconscious model *and*
their KV caches all resident simultaneously, because a model that has to page in from disk
blows the sub-second acknowledge budget mid-sentence. Size for the **sum**, not the max.

Rough resident budget:
```
  Whisper-class STT (large-v3 int8)     ~2.0 GB
  TTS voice model                       ~1.0 GB
  Subconscious 14B @ Q4_K_M             ~9.0 GB   (rule of thumb: params_B × 0.6)
  KV cache + runtime overhead           ~2.5 GB
  ─────────────────────────────────────────────
  Total resident                       ~14.5 GB   → 16 GB is the floor, 24 GB is comfortable
```
At 32B the subconscious alone is ~19–20 GB, so a 32B model plus resident speech needs 32 GB.

---

## 3. The other reason it's local: the subconscious reads everything

This isn't only a latency or cost argument. The subconscious is the process that reads
**every conversation, every file, every trace, every credential that ever appeared in a tool
result**. It is the most sensitive process in the system.

Sending that to a third party continuously would be the single largest privacy decision in
the whole project, made silently, for convenience. Running it locally is a **security
requirement**, and it is what lets §8 of doc 11 hold: *the subconscious has no network
egress, ever* — a property you simply cannot have if the subconscious is an API call.

Charter commitment 7 lands here too: memory the user can read, held on a machine the user
owns.

---

## 4. And the arithmetic agrees

A concrete comparison, using current published pricing. xAI's Voice Agent API is **$3.00 per
hour** of realtime speech.

```
  2 hours/day of voice interaction  ×  365 days  ×  $3.00  =  $2,190 / year
```

A 24 GB GPU costs roughly $1,000–$2,000. **Cloud realtime voice pays for the GPU in under a
year**, and that's before counting embedding backfill, reranking, and every consolidation
pass the subconscious runs nightly. The privacy argument and the cost argument point the
same direction, which is a comfortable place to be.

---

## 5. Build tiers

| Tier | Spec | Runs locally | When |
|---|---|---|---|
| **A — Existing PC** | Whatever you have + cloud models | Core, control plane, adapters, the Record | **Now.** Phases 0–1. Spend $0. |
| **B — Always-on core, no GPU** | 12–16 core CPU · 64 GB · 2 TB NVMe · bulk pool · UPS | Everything in A, always up. Cloud STT/TTS. | When uptime starts mattering more than locality |
| **C — Core + inference (recommended target)** | Above + **24 GB GPU** · 96–128 GB RAM | + local STT/TTS + subconscious + embeddings | When the Record has enough in it to consolidate, and voice goes daily |
| **D — Large local models** | Unified-memory box (128 GB class) or 2× 24–32 GB | 70B+ local, fine-tuning experiments | Only when a workload proves the need |

### Tier C, concretely
- **CPU** 16 cores / 32 threads (Ryzen 9 class). Drivers are parallel agent sandboxes, builds
  and test runs, and zstd compression of the Record — not inference.
- **RAM** 96–128 GB. 64 GB is the floor. Drivers: index page cache, several concurrent
  container sandboxes, Home Assistant, headroom. RAM is the cheapest thing to over-buy here.
- **GPU** 24 GB. 16 GB works for a 14B subconscious; 24 GB gives room for a 32B, longer KV
  cache, and concurrent embedding batches without evicting the speech models.
- **Storage** 2 TB Gen4 NVMe hot (Record + indexes + worktrees) · 2× 8–12 TB mirrored bulk
  (warm/cold/backup staging) · encrypted offsite. Per doc 11 §4, 2 TB holds years of Record.
- **Power/integrity** UPS with clean shutdown · ECC if the platform supports it · full-disk
  encryption · 3-2-1 backups **including the keystore**, which is now the thing that makes the
  entire archive readable or not.

### On tier D and unified memory
A 128 GB unified-memory box (DGX Spark class, Strix Halo, Mac Studio) buys capacity at the
cost of prefill throughput. The subconscious workload is **many short reranking and
extraction calls**, not a few long generations — which is precisely the profile where a
24 GB discrete card beats a 128 GB unified box. Do not buy capacity you'd be using for the
wrong shape of work.

---

## 6. What not to buy first

- **Not a GPU, before the Record has a few months of content.** The subconscious has nothing
  to consolidate on day one, and tier A proves the architecture for free.
- **Not a big bulk pool.** Doc 11 §4: a full-fidelity year of text is ~1 GB. Buy the fast
  2 TB; add bulk when media retention actually demands it.
- **Not glasses, satellites, or a car integration.** Every device is a node behind an adapter
  (`06-ROADMAP.md`). Hardware follows capability proof.
- **Not a second machine for redundancy.** A UPS and tested restores buy more availability per
  dollar than a spare box, at this scale.

---

## 7. The one thing worth buying immediately

**Backup and the UPS, before anything else.** The moment the Record starts accumulating, it
becomes the most valuable and least reproducible thing in the project — and unlike the code,
it has no upstream to re-clone from. A power cut mid-write to an append-only log is exactly
how you learn whether your fsync discipline was real.

Test restores on a schedule. An untested backup and an untested kill switch fail the same
way, for the same reason.
