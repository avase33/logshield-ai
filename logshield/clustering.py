"""Incremental, open-set clustering of unknown log variants.

When a brand-new error appears — one whose template the system has never seen —
we don't want to drop it or wait for a human label. This streaming density
clusterer groups semantically-similar unknown logs into emerging clusters:

* each embedding joins the nearest cluster if cosine ≥ threshold, else seeds a
  new *provisional* cluster;
* a cluster is promoted to a real "incident type" once it reaches
  ``min_cluster_size`` (the density/min-samples filter — one-off noise never
  becomes an incident);
* centroids update incrementally, so a single pass handles the stream.

Newly-formed, recently-active clusters are flagged ``new_incident`` for the
dashboard's "New Incident Types" view.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from .embeddings import cosine
from .models import Cluster, new_id


@dataclass
class _Live:
    cluster: Cluster
    sum_vec: list[float]
    components: Counter = field(default_factory=Counter)
    provisional: bool = True


@dataclass
class AssignResult:
    cluster_id: str
    created: bool
    promoted: bool


class IncrementalClusterer:
    def __init__(self, similarity: float = 0.6, min_cluster_size: int = 3,
                 new_incident_window: float = 3600.0) -> None:
        self.similarity = similarity
        self.min_cluster_size = min_cluster_size
        self.new_incident_window = new_incident_window
        self._live: dict[str, _Live] = {}

    def _nearest(self, vec: list[float]) -> tuple[Optional[str], float]:
        best_id, best = None, -1.0
        for cid, lv in self._live.items():
            s = cosine(vec, lv.cluster.centroid)
            if s > best:
                best_id, best = cid, s
        return best_id, best

    def assign(self, embedding: list[float], component: str, severity: int,
               sample_template: str = "") -> AssignResult:
        cid, sim = self._nearest(embedding)
        created = promoted = False
        if cid is None or sim < self.similarity:
            cid = new_id("cl")
            c = Cluster(id=cid, label="(forming)", centroid=list(embedding),
                        sample_template=sample_template)
            self._live[cid] = _Live(cluster=c, sum_vec=list(embedding))
            created = True

        lv = self._live[cid]
        c = lv.cluster
        c.members += 1
        for i, x in enumerate(embedding):
            lv.sum_vec[i] += x
        n = c.members
        mean = [s / n for s in lv.sum_vec]
        norm = sum(v * v for v in mean) ** 0.5
        c.centroid = [v / norm for v in mean] if norm else mean
        lv.components[component] += 1
        c.dominant_component = lv.components.most_common(1)[0][0]
        c.max_severity = max(c.max_severity, severity)
        c.last_seen = time.time()
        if not c.sample_template and sample_template:
            c.sample_template = sample_template
        c.label = c.dominant_component.title() + " incident"

        if lv.provisional and c.members >= self.min_cluster_size:
            lv.provisional = False
            promoted = True
        c.new_incident = (time.time() - c.first_seen) <= self.new_incident_window
        return AssignResult(cid, created, promoted)

    @property
    def clusters(self) -> list[Cluster]:
        return [lv.cluster for lv in self._live.values() if not lv.provisional]

    def all_clusters(self) -> list[Cluster]:
        return [lv.cluster for lv in self._live.values()]

    def new_incidents(self) -> list[Cluster]:
        return [c for c in self.clusters if c.new_incident]
