"""Simplified CPU detection and thread configuration.

Basic CPU detection for OCR thread optimization, without complex profiling.
"""

import os
import platform
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class ThreadConfig:
    """Simple thread configuration for OCR performance."""

    omp_threads: int = 1
    openblas_threads: int = 1

    def to_env_vars(self) -> Dict[str, str]:
        """Convert to environment variables."""
        env_vars = {
            'OMP_NUM_THREADS': str(self.omp_threads),
            'OPENBLAS_NUM_THREADS': str(self.openblas_threads),
            'MKL_NUM_THREADS': str(self.omp_threads),
            'VECLIB_MAXIMUM_THREADS': str(self.omp_threads),
        }
        return env_vars


def get_cpu_count() -> int:
    """Get the number of CPU cores."""
    try:
        return os.cpu_count() or 1
    except:
        return 1


def get_adaptive_thread_config() -> ThreadConfig:
    """Get basic thread configuration based on CPU count."""
    cpu_count = get_cpu_count()

    # Simple heuristic: use half of available cores, minimum 1, maximum 4
    optimal_threads = max(1, min(4, cpu_count // 2))

    return ThreadConfig(
        omp_threads=optimal_threads,
        openblas_threads=optimal_threads
    )


class CPUProfiler:
    """Simplified CPU profiler for basic detection."""

    def __init__(self):
        self.cpu_count = get_cpu_count()
        self.platform = platform.system()

    def detect_cpu_profile(self):
        """Return basic CPU information."""
        return {
            'cores_physical': self.cpu_count,
            'cores_logical': self.cpu_count,
            'platform_name': self.platform,
            'vendor': 'Unknown',
            'architecture': platform.machine(),
            'name': platform.processor() or 'Unknown',
        }

    def get_optimal_thread_count(self) -> int:
        """Get optimal thread count for OCR."""
        return max(1, min(4, self.cpu_count // 2))