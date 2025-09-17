"""CPU profiling and adaptive thread configuration system.

This module provides advanced CPU detection and automatic thread optimization
for maximum OCR performance across all platforms.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class CPUProfile:
    """Detailed CPU profile for optimization decisions."""

    architecture: str           # x86_64, arm64, etc.
    vendor: str                # Intel, AMD, Apple, etc.
    cores_physical: int        # Physical CPU cores
    cores_logical: int         # Logical processors (with hyperthreading)
    generation: Optional[int]  # CPU generation (Intel: 8, 9, 10+; AMD: Zen1, Zen2, etc.)
    features: List[str]        # CPU features like AVX2, AVX-512
    name: str                  # Full CPU name
    platform_name: str        # Windows, Darwin, Linux

    def signature(self) -> str:
        """Generate unique signature for caching purposes."""
        return f"{self.platform_name}_{self.vendor}_{self.architecture}_{self.generation}_{self.cores_physical}_{self.cores_logical}"


@dataclass
class ThreadConfig:
    """Thread configuration for optimal performance."""

    omp_threads: int = 1
    openblas_threads: int = 1
    mkl_threads: Optional[int] = None
    veclib_threads: Optional[int] = None
    intel_threads: Optional[int] = None
    openblas_coretype: Optional[str] = None

    def to_env_vars(self) -> Dict[str, str]:
        """Convert to environment variable dictionary."""
        env_vars = {
            "OMP_NUM_THREADS": str(self.omp_threads),
            "OPENBLAS_NUM_THREADS": str(self.openblas_threads),
        }

        if self.mkl_threads is not None:
            env_vars["MKL_NUM_THREADS"] = str(self.mkl_threads)

        if self.veclib_threads is not None:
            env_vars["VECLIB_MAXIMUM_THREADS"] = str(self.veclib_threads)

        if self.intel_threads is not None:
            env_vars["INTEL_NUM_THREADS"] = str(self.intel_threads)

        if self.openblas_coretype is not None:
            env_vars["OPENBLAS_CORETYPE"] = self.openblas_coretype

        return env_vars


class CPUProfiler:
    """Advanced CPU detection and profiling system."""

    def __init__(self):
        self.platform = platform.system()
        self.machine = platform.machine()

    def detect_cpu_profile(self) -> CPUProfile:
        """Detect comprehensive CPU profile."""
        try:
            if self.platform == "Windows":
                return self._detect_windows_cpu()
            elif self.platform == "Darwin":
                return self._detect_macos_cpu()
            else:  # Linux and others
                return self._detect_linux_cpu()
        except Exception as e:
            logger.warning("CPU detection failed, using fallback: %s", e)
            return self._get_fallback_profile()

    def _detect_windows_cpu(self) -> CPUProfile:
        """Detect CPU profile on Windows using wmic."""
        try:
            # Get CPU information
            result = subprocess.run(
                ["wmic", "cpu", "get", "Name,NumberOfCores,NumberOfLogicalProcessors", "/format:csv"],
                capture_output=True, text=True, timeout=10
            )

            if result.returncode != 0:
                raise RuntimeError(f"wmic failed: {result.stderr}")

            lines = [line.strip() for line in result.stdout.split('\n') if line.strip()]
            for line in lines[1:]:  # Skip header
                parts = line.split(',')
                if len(parts) >= 4:
                    name = parts[1] if len(parts) > 1 else ""
                    cores = int(parts[2]) if parts[2].isdigit() else 0
                    logical = int(parts[3]) if parts[3].isdigit() else 0

                    vendor = self._extract_vendor(name)
                    generation = self._extract_generation(name, vendor)
                    features = self._detect_cpu_features_windows()

                    return CPUProfile(
                        architecture=self.machine.lower(),
                        vendor=vendor,
                        cores_physical=cores,
                        cores_logical=logical,
                        generation=generation,
                        features=features,
                        name=name,
                        platform_name="Windows"
                    )

            raise RuntimeError("No valid CPU information found")

        except Exception as e:
            logger.error("Windows CPU detection failed: %s", e)
            return self._get_fallback_profile()

    def _detect_macos_cpu(self) -> CPUProfile:
        """Detect CPU profile on macOS using sysctl."""
        try:
            # Get CPU information using sysctl
            name_result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=5
            )

            cores_result = subprocess.run(
                ["sysctl", "-n", "hw.physicalcpu"],
                capture_output=True, text=True, timeout=5
            )

            logical_result = subprocess.run(
                ["sysctl", "-n", "hw.logicalcpu"],
                capture_output=True, text=True, timeout=5
            )

            name = name_result.stdout.strip() if name_result.returncode == 0 else "Unknown"
            cores = int(cores_result.stdout.strip()) if cores_result.returncode == 0 else 0
            logical = int(logical_result.stdout.strip()) if logical_result.returncode == 0 else 0

            vendor = self._extract_vendor(name)
            generation = self._extract_generation(name, vendor)
            features = self._detect_cpu_features_macos()

            return CPUProfile(
                architecture=self.machine.lower(),
                vendor=vendor,
                cores_physical=cores,
                cores_logical=logical,
                generation=generation,
                features=features,
                name=name,
                platform_name="Darwin"
            )

        except Exception as e:
            logger.error("macOS CPU detection failed: %s", e)
            return self._get_fallback_profile()

    def _detect_linux_cpu(self) -> CPUProfile:
        """Detect CPU profile on Linux using /proc/cpuinfo."""
        try:
            with open('/proc/cpuinfo', 'r') as f:
                content = f.read()

            # Extract CPU name
            name_match = re.search(r'model name\s*:\s*(.+)', content)
            name = name_match.group(1).strip() if name_match else "Unknown"

            # Count cores using flexible whitespace handling
            processor_matches = re.findall(r'^processor\s*:', content, re.MULTILINE)
            logical_cores = len(processor_matches)

            # Try to get physical cores
            core_id_matches = re.findall(r'^core id\s*:\s*(\d+)', content, re.MULTILINE)
            physical_cores = len(set(core_id_matches)) if core_id_matches else logical_cores

            vendor = self._extract_vendor(name)
            generation = self._extract_generation(name, vendor)
            features = self._detect_cpu_features_linux(content)

            return CPUProfile(
                architecture=self.machine.lower(),
                vendor=vendor,
                cores_physical=physical_cores,
                cores_logical=logical_cores,
                generation=generation,
                features=features,
                name=name,
                platform_name="Linux"
            )

        except Exception as e:
            logger.error("Linux CPU detection failed: %s", e)
            return self._get_fallback_profile()

    def _extract_vendor(self, cpu_name: str) -> str:
        """Extract CPU vendor from name."""
        name_lower = cpu_name.lower()
        if "intel" in name_lower:
            return "Intel"
        elif "amd" in name_lower:
            return "AMD"
        elif "apple" in name_lower:
            return "Apple"
        else:
            return "Unknown"

    def _extract_generation(self, cpu_name: str, vendor: str) -> Optional[int]:
        """Extract CPU generation from name and vendor."""
        if vendor == "Intel":
            # Look for patterns like "i7-10700K" or "i5-11400"
            match = re.search(r'i[3579]-(\d{1,2})\d{3}', cpu_name)
            if match:
                gen_str = match.group(1)
                return int(gen_str)

            # Look for newer naming like "12th Gen"
            match = re.search(r'(\d+)th Gen', cpu_name)
            if match:
                return int(match.group(1))

        elif vendor == "AMD":
            # Detect Ryzen generation
            if "Ryzen" in cpu_name:
                # Ryzen 3xxx = Zen 2, Ryzen 5xxx = Zen 3, etc.
                match = re.search(r'Ryzen.*?(\d)(\d{3})', cpu_name)
                if match:
                    series = int(match.group(1))
                    model_num = int(match.group(2))
                    full_model = series * 1000 + model_num  # e.g., 3 * 1000 + 600 = 3600
                    if full_model >= 5000:
                        return 3  # Zen 3
                    elif full_model >= 3000:
                        return 2  # Zen 2
                    elif full_model >= 2000:
                        return 1  # Zen+
                    else:
                        return 1  # Zen

        elif vendor == "Apple":
            # Apple Silicon detection
            if "M1" in cpu_name:
                return 1
            elif "M2" in cpu_name:
                return 2
            elif "M3" in cpu_name:
                return 3

        return None

    def _detect_cpu_features_windows(self) -> List[str]:
        """Detect CPU features on Windows."""
        features = []
        try:
            # Use wmic to get CPU features
            result = subprocess.run(
                ["wmic", "cpu", "get", "Characteristics", "/format:csv"],
                capture_output=True, text=True, timeout=5
            )

            if result.returncode == 0:
                # This is a simplified implementation
                # In reality, you'd parse the characteristics bitmask
                features.append("SSE2")  # Assume basic SSE2 support

        except Exception:
            pass

        return features

    def _detect_cpu_features_macos(self) -> List[str]:
        """Detect CPU features on macOS."""
        features = []
        try:
            # Check for various CPU features
            feature_checks = [
                ("hw.optional.avx2_0", "AVX2"),
                ("hw.optional.avx512f", "AVX-512"),
                ("machdep.cpu.features", "SSE"),
            ]

            for sysctl_key, feature_name in feature_checks:
                try:
                    result = subprocess.run(
                        ["sysctl", "-n", sysctl_key],
                        capture_output=True, text=True, timeout=2
                    )
                    if result.returncode == 0 and result.stdout.strip() == "1":
                        features.append(feature_name)
                except Exception:
                    continue

        except Exception:
            pass

        return features

    def _detect_cpu_features_linux(self, cpuinfo_content: str) -> List[str]:
        """Detect CPU features from Linux /proc/cpuinfo."""
        features = []

        # Look for flags line
        flags_match = re.search(r'^flags\s*:\s*(.+)', cpuinfo_content, re.MULTILINE)
        if flags_match:
            flags = flags_match.group(1).split()

            # Map common flags to feature names
            feature_map = {
                "avx2": "AVX2",
                "avx512f": "AVX-512",
                "sse4_1": "SSE4.1",
                "sse4_2": "SSE4.2",
                "ssse3": "SSSE3",
                "sse3": "SSE3",
                "sse2": "SSE2",
            }

            for flag in flags:
                if flag in feature_map:
                    features.append(feature_map[flag])

        return features

    def _get_fallback_profile(self) -> CPUProfile:
        """Fallback CPU profile when detection fails."""
        return CPUProfile(
            architecture=self.machine.lower(),
            vendor="Unknown",
            cores_physical=os.cpu_count() or 4,
            cores_logical=os.cpu_count() or 4,
            generation=None,
            features=[],
            name="Unknown CPU",
            platform_name=self.platform
        )


class ThreadConfigManager:
    """Manages thread configurations with caching and optimization."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path.home() / ".vlog-subs-tool"
        self.cache_file = self.cache_dir / "cpu_thread_cache.json"
        self.cache_dir.mkdir(exist_ok=True)

    def get_optimal_config(self, profile: CPUProfile) -> ThreadConfig:
        """Get optimal thread configuration for CPU profile."""
        # Try to load from cache first
        cached_config = self._load_cached_config(profile)
        if cached_config:
            logger.info("Using cached thread configuration for %s", profile.signature())
            return cached_config

        # Generate optimal configuration
        config = self._generate_optimal_config(profile)

        # Cache the configuration
        self._save_config_to_cache(profile, config)

        return config

    def _generate_optimal_config(self, profile: CPUProfile) -> ThreadConfig:
        """Generate optimal thread configuration based on CPU profile."""
        if profile.architecture == "arm64" and profile.vendor == "Apple":
            # Apple Silicon optimization
            return ThreadConfig(
                omp_threads=min(8, profile.cores_logical),
                openblas_threads=1,  # Disable to avoid conflicts
                veclib_threads=profile.cores_logical,
            )

        elif profile.vendor == "Intel":
            if profile.generation and profile.generation >= 10:
                # Intel 10th gen and newer - aggressive threading
                return ThreadConfig(
                    omp_threads=min(6, profile.cores_logical),
                    openblas_threads=min(6, profile.cores_logical),
                    mkl_threads=profile.cores_physical,
                    intel_threads=profile.cores_physical,
                )
            else:
                # Older Intel CPUs - conservative threading
                return ThreadConfig(
                    omp_threads=min(3, max(2, profile.cores_logical // 2)),
                    openblas_threads=min(3, max(2, profile.cores_logical // 2)),
                    mkl_threads=profile.cores_physical,
                )

        elif profile.vendor == "AMD":
            # AMD Ryzen optimization
            return ThreadConfig(
                omp_threads=min(profile.cores_physical, 8),
                openblas_threads=min(profile.cores_physical, 8),
                openblas_coretype="RYZEN",
            )

        else:
            # Conservative fallback for unknown CPUs
            return ThreadConfig(
                omp_threads=min(3, max(2, profile.cores_logical // 4)),
                openblas_threads=min(3, max(2, profile.cores_logical // 4)),
            )

    def _load_cached_config(self, profile: CPUProfile) -> Optional[ThreadConfig]:
        """Load cached configuration for CPU profile."""
        try:
            if not self.cache_file.exists():
                return None

            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)

            signature = profile.signature()
            if signature in cache_data:
                config_dict = cache_data[signature]
                return ThreadConfig(**config_dict)

        except Exception as e:
            logger.warning("Failed to load cached thread config: %s", e)

        return None

    def _save_config_to_cache(self, profile: CPUProfile, config: ThreadConfig):
        """Save configuration to cache."""
        try:
            # Load existing cache
            cache_data = {}
            if self.cache_file.exists():
                with open(self.cache_file, 'r') as f:
                    cache_data = json.load(f)

            # Add new configuration
            cache_data[profile.signature()] = asdict(config)

            # Save cache
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)

            logger.debug("Saved thread configuration to cache: %s", profile.signature())

        except Exception as e:
            logger.warning("Failed to save thread config to cache: %s", e)


def get_adaptive_thread_config() -> ThreadConfig:
    """Get adaptive thread configuration for current system."""
    try:
        profiler = CPUProfiler()
        profile = profiler.detect_cpu_profile()

        logger.info("Detected CPU: %s (%s %s, %d/%d cores, gen %s)",
                    profile.name, profile.vendor, profile.architecture,
                    profile.cores_physical, profile.cores_logical, profile.generation)

        manager = ThreadConfigManager()
        config = manager.get_optimal_config(profile)

        logger.info("Optimal thread configuration: %s", config)

        return config

    except Exception as e:
        logger.warning("Failed to get adaptive thread configuration: %s", e)
        # Return conservative fallback configuration
        return ThreadConfig(
            omp_threads=2,
            openblas_threads=2
        )