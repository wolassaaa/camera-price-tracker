"""Long-running local collection worker."""

from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import argparse
from collections.abc import Callable

from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv

from camera_tracker.collector import run_watch
from camera_tracker.config import load_settings, load_sources, load_target_prices, load_watches
from camera_tracker.notifications import NotificationConfig, send_all
from camera_tracker.repository import SqliteRepository
from camera_tracker.source_status import SourceStatusRegistry
from camera_tracker.observability import configure_worker_logging
from camera_tracker.scheduler import BackoffGate


@dataclass(frozen=True)
class JobSpec:
    source_id: str
    watch: dict[str, str]
    interval_minutes: int
    jitter_seconds: int


def job_specs(*, watches: list[dict[str, str]], sources: dict[str, dict[str, object]]) -> list[JobSpec]:
    jobs: list[JobSpec] = []
    for watch in watches:
        source_id = watch["platform"]
        source = sources.get(source_id, {})
        if source.get("enabled") is not True:
            continue
        jobs.append(JobSpec(
            source_id=source_id, watch=watch, interval_minutes=int(source.get("interval_minutes", 60)),
            jitter_seconds=int(source.get("jitter_seconds", 0)),
        ))
    return jobs


def run_once(
    *, watches: list[dict[str, str]], sources: dict[str, dict[str, object]], database_path: Path,
    runner: Callable[..., int] = run_watch,
) -> int:
    """Run all enabled watches once, useful at startup and for manual checks."""
    repository = SqliteRepository(database_path)
    repository.path.parent.mkdir(parents=True, exist_ok=True)
    repository.migrate()
    statuses = SourceStatusRegistry()
    total = 0
    for spec in job_specs(watches=watches, sources=sources):
        try:
            total += runner(spec.watch, repository=repository, status=statuses)
        except Exception:
            # run_watch persists the source failure.  A rate limit or a changed
            # public page must not prevent independent sources from being run.
            continue
    return total


def run_worker(config_dir: Path = Path("config"), database_path: Path = Path("data/tracker.db")) -> None:
    load_dotenv()
    logger = configure_worker_logging(database_path.parent / "tracker.log")
    logger.info("starting worker config_dir=%s database_path=%s", config_dir, database_path)
    repository = SqliteRepository(database_path)
    repository.path.parent.mkdir(parents=True, exist_ok=True)
    repository.migrate()
    statuses = SourceStatusRegistry()
    targets = load_target_prices(config_dir / "alerts.yaml")
    settings = load_settings(config_dir / "settings.yaml")
    notification_config = NotificationConfig.from_env()
    backoff = BackoffGate()

    def notify(payload: dict[str, str]) -> None:
        now = datetime.now(timezone.utc)
        if not repository.notification_due(
            product_id=payload["product"], event=payload["event"], now=now, cooldown_seconds=6 * 60 * 60,
        ):
            return
        delivered = send_all(notification_config, payload)
        if delivered:
            repository.mark_notification_sent(product_id=payload["product"], event=payload["event"], now=now)

    scheduler = BlockingScheduler()
    retention_days = int(settings.get("snapshot_retention_days", 30))
    market_spread_threshold_cny = Decimal(str(settings.get("market_spread_threshold_cny", 500)))
    scheduler.add_job(
        lambda: repository.prune_raw_snapshots(before=datetime.now(timezone.utc) - timedelta(days=retention_days)),
        "interval", days=1, id="snapshot-retention", replace_existing=True,
    )

    def scheduled_collect(spec: JobSpec) -> None:
        now = datetime.now(timezone.utc)
        if not backoff.allows(spec.source_id, now):
            return
        try:
            run_watch(
                spec.watch, repository=repository, status=statuses, target_prices=targets, notifier=notify,
                source_notifier=notify, market_spread_threshold_cny=market_spread_threshold_cny,
            )
        except Exception:
            failure_count = repository.source_failure_count(spec.source_id)
            next_allowed = backoff.record_failure(
                source_id=spec.source_id, interval_minutes=spec.interval_minutes, jitter_seconds=spec.jitter_seconds,
                failure_count=failure_count, now=now,
            )
            logger.warning("source=%s backed_off_until=%s", spec.source_id, next_allowed.isoformat())
        else:
            backoff.record_success(spec.source_id)
    for spec in job_specs(watches=load_watches(config_dir / "watches.yaml"), sources=load_sources(config_dir / "sources.yaml")):
        scheduler.add_job(
            scheduled_collect, "interval", minutes=spec.interval_minutes, jitter=spec.jitter_seconds,
            args=[spec],
            id=f"{spec.source_id}-{spec.watch['product_id']}", replace_existing=True,
        )
    run_once(
        watches=load_watches(config_dir / "watches.yaml"), sources=load_sources(config_dir / "sources.yaml"),
        database_path=database_path,
        runner=lambda watch, **kwargs: run_watch(
            watch, target_prices=targets, notifier=notify, source_notifier=notify,
            market_spread_threshold_cny=market_spread_threshold_cny, **kwargs,
        ),
    )
    scheduler.start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local camera price collection worker")
    parser.add_argument("--once", action="store_true", help="run enabled public watches once, then exit")
    parser.add_argument("--config-dir", type=Path, default=Path("config"))
    parser.add_argument("--database", type=Path, default=Path("data/tracker.db"))
    args = parser.parse_args(argv)
    if args.once:
        load_dotenv()
        count = run_once(
            watches=load_watches(args.config_dir / "watches.yaml"),
            sources=load_sources(args.config_dir / "sources.yaml"), database_path=args.database,
        )
        print(f"quotes_written={count}")
        return 0
    run_worker(config_dir=args.config_dir, database_path=args.database)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
