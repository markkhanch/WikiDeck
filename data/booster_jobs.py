from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock, Thread
from typing import Optional

from config import BOOSTER_PACK_SIZE
from data.booster import add_pack_to_collection_and_deck, open_random_pack


@dataclass
class BoosterJob:
    id: int
    status: str = "idle"  # idle | running | done | error
    total: int = 0
    generated: int = 0
    error: str = ""
    cards: list[dict] = field(default_factory=list)


_job_lock = Lock()
_current_job: Optional[BoosterJob] = None
_next_job_id = 1


def start_booster_job(pack_size: int = BOOSTER_PACK_SIZE) -> bool:
    """Start a background booster job. Returns False if one is already running."""
    global _current_job, _next_job_id
    with _job_lock:
        if _current_job and _current_job.status == "running":
            return False
        job = BoosterJob(
            id=_next_job_id,
            status="running",
            total=pack_size,
            generated=0,
            error="",
            cards=[],
        )
        _next_job_id += 1
        _current_job = job

    print(f"[booster-job:{job.id}] Started (pack_size={pack_size})", flush=True)
    thread = Thread(target=_run_booster_job, args=(job, pack_size), daemon=True)
    thread.start()
    return True


def _run_booster_job(job: BoosterJob, pack_size: int) -> None:
    try:
        def _progress(_: dict, count: int, total: int) -> None:
            with _job_lock:
                job.generated = count
                job.total = total
            print(f"[booster-job:{job.id}] Progress: {count}/{total}", flush=True)

        pack = open_random_pack(pack_size=pack_size, on_progress=_progress)
        add_pack_to_collection_and_deck(pack)
        with _job_lock:
            job.status = "done"
            job.cards = pack
            job.generated = len(pack)
            job.total = len(pack)
        print(f"[booster-job:{job.id}] Done: {len(pack)} cards saved", flush=True)
    except Exception as exc:
        with _job_lock:
            job.status = "error"
            job.error = str(exc)
        print(f"[booster-job:{job.id}] Error: {exc}", flush=True)


def get_booster_job() -> Optional[dict]:
    with _job_lock:
        if _current_job is None:
            return None
        job = _current_job
        return {
            "id": job.id,
            "status": job.status,
            "total": job.total,
            "generated": job.generated,
            "error": job.error,
            "cards": list(job.cards),
        }
