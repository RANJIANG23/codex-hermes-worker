from __future__ import annotations

from functools import lru_cache

from codex_hermes_worker.bridge.config import AppConfig, load_config
from codex_hermes_worker.bridge.hermes_client import HermesClient
from codex_hermes_worker.jobs.database import JobDatabase
from codex_hermes_worker.jobs.manager import JobManager
from codex_hermes_worker.jobs.worker import LocalWorker


class Runtime:
    def __init__(self, config: AppConfig, *, recover_interrupted: bool = True):
        self.config = config
        for path in config.filesystem.writable_roots:
            path.mkdir(parents=True, exist_ok=True)
        self.database = JobDatabase(config.jobs.database)
        self.hermes = HermesClient(config)
        self.worker = LocalWorker(config, self.database, self.hermes)
        self.manager = JobManager(
            config,
            self.database,
            self.worker,
            recover_interrupted=recover_interrupted,
        )


@lru_cache(maxsize=1)
def get_runtime() -> Runtime:
    return Runtime(load_config())
