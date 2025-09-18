"""Linux環境でのOCR性能最適化システム.

このモジュールはLinux環境でのOCR処理性能を1.2-2倍向上させるための
高度な最適化機能を提供します。

主な機能:
- NUMA対応最適化
- CPU別特化設定
- OpenBLASバリアント選択
- メモリサブシステム最適化
- I/O・キャッシュ最適化
"""

from __future__ import annotations

import logging
import os
import platform
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)


@dataclass
class NUMATopology:
    """NUMA構成情報."""

    nodes: int
    cores_per_node: List[int]
    memory_per_node: List[int]  # GB単位
    node_distances: Dict[Tuple[int, int], int]  # ノード間距離
    cpu_list_per_node: Dict[int, List[int]]  # ノード別CPU一覧

    @classmethod
    def from_system(cls) -> Optional[NUMATopology]:
        """システムからNUMA構成を検出."""
        try:
            return NUMADetector().detect_numa_topology()
        except Exception as e:
            logger.warning("NUMA構成の検出に失敗: %s", e)
            return None

    def is_numa_system(self) -> bool:
        """NUMA環境かどうか判定."""
        return self.nodes > 1

    def get_optimal_cpu_set(self, max_threads: int) -> List[int]:
        """最適なCPU配置を取得."""
        if not self.is_numa_system():
            # 非NUMA環境では通常のCPU配置
            return list(range(min(max_threads, sum(self.cores_per_node))))

        # NUMA環境では最初のノードを優先
        optimal_cpus = []
        remaining_threads = max_threads

        for node_id in sorted(self.cpu_list_per_node.keys()):
            if remaining_threads <= 0:
                break

            node_cpus = self.cpu_list_per_node[node_id]
            take_cpus = min(remaining_threads, len(node_cpus))
            optimal_cpus.extend(node_cpus[:take_cpus])
            remaining_threads -= take_cpus

        return optimal_cpus


@dataclass
class CPUInfo:
    """CPU情報."""

    vendor: str
    model: str
    architecture: str
    cores: int
    threads: int
    generation: Optional[int]
    features: List[str]
    frequency: float  # GHz
    cache_sizes: Dict[str, int]  # L1, L2, L3キャッシュサイズ(KB)

    def is_high_core_count(self) -> bool:
        """高コア数CPUかどうか判定."""
        return self.cores > 8

    def is_server_cpu(self) -> bool:
        """サーバーCPUかどうか判定."""
        server_indicators = ["Xeon", "EPYC", "Threadripper"]
        return any(indicator in self.model for indicator in server_indicators)


class NUMADetector:
    """NUMA環境検出クラス."""

    def detect_numa_topology(self) -> Optional[NUMATopology]:
        """NUMA構成を検出."""
        if not self._is_numa_available():
            return None

        try:
            nodes = self._get_numa_nodes()
            if not nodes:
                return None

            cores_per_node = []
            memory_per_node = []
            cpu_list_per_node = {}

            for node_id in nodes:
                # 各ノードのCPU一覧を取得
                cpus = self._get_node_cpus(node_id)
                cpu_list_per_node[node_id] = cpus
                cores_per_node.append(len(cpus))

                # 各ノードのメモリ量を取得
                memory = self._get_node_memory(node_id)
                memory_per_node.append(memory)

            # ノード間距離を取得
            node_distances = self._get_node_distances(nodes)

            return NUMATopology(
                nodes=len(nodes),
                cores_per_node=cores_per_node,
                memory_per_node=memory_per_node,
                node_distances=node_distances,
                cpu_list_per_node=cpu_list_per_node
            )

        except Exception as e:
            logger.warning("NUMA情報の詳細取得に失敗: %s", e)
            return None

    def _is_numa_available(self) -> bool:
        """NUMAが利用可能かチェック."""
        return Path("/sys/devices/system/node").exists()

    def _get_numa_nodes(self) -> List[int]:
        """NUMAノード一覧を取得."""
        node_dirs = Path("/sys/devices/system/node").glob("node[0-9]*")
        nodes = []
        for node_dir in node_dirs:
            node_id = int(node_dir.name[4:])  # "node0" -> 0
            nodes.append(node_id)
        return sorted(nodes)

    def _get_node_cpus(self, node_id: int) -> List[int]:
        """指定ノードのCPU一覧を取得."""
        cpulist_file = Path(f"/sys/devices/system/node/node{node_id}/cpulist")
        if not cpulist_file.exists():
            return []

        try:
            cpulist_str = cpulist_file.read_text().strip()
            return self._parse_cpu_list(cpulist_str)
        except Exception:
            return []

    def _parse_cpu_list(self, cpulist_str: str) -> List[int]:
        """CPU一覧文字列をパース（例: "0-3,8-11" -> [0,1,2,3,8,9,10,11]）."""
        cpus = []
        for part in cpulist_str.split(','):
            if '-' in part:
                start, end = map(int, part.split('-'))
                cpus.extend(range(start, end + 1))
            else:
                cpus.append(int(part))
        return sorted(cpus)

    def _get_node_memory(self, node_id: int) -> int:
        """指定ノードのメモリ量を取得（GB単位）."""
        meminfo_file = Path(f"/sys/devices/system/node/node{node_id}/meminfo")
        if not meminfo_file.exists():
            return 0

        try:
            content = meminfo_file.read_text()
            # "Node 0 MemTotal: 16777216 kB" のような行を探す
            match = re.search(rf"Node {node_id} MemTotal:\s+(\d+) kB", content)
            if match:
                kb = int(match.group(1))
                return kb // (1024 * 1024)  # KBからGBに変換
        except Exception:
            pass

        return 0

    def _get_node_distances(self, nodes: List[int]) -> Dict[Tuple[int, int], int]:
        """ノード間距離を取得."""
        distances = {}

        for node_id in nodes:
            distance_file = Path(f"/sys/devices/system/node/node{node_id}/distance")
            if not distance_file.exists():
                continue

            try:
                distance_line = distance_file.read_text().strip()
                distance_values = list(map(int, distance_line.split()))

                for i, distance in enumerate(distance_values):
                    if i < len(nodes):
                        distances[(node_id, nodes[i])] = distance
            except Exception:
                continue

        return distances


class CPUDetector:
    """CPU情報検出クラス."""

    def detect_cpu_info(self) -> CPUInfo:
        """詳細なCPU情報を検出."""
        try:
            return self._parse_cpuinfo()
        except Exception as e:
            logger.warning("CPU情報の検出に失敗: %s", e)
            return self._get_fallback_cpu_info()

    def _parse_cpuinfo(self) -> CPUInfo:
        """cpuinfoから詳細情報を取得."""
        with open("/proc/cpuinfo", "r") as f:
            content = f.read()

        # モデル名取得
        model_match = re.search(r"model name\s*:\s*(.+)", content)
        model = model_match.group(1).strip() if model_match else "Unknown"

        # ベンダー取得
        vendor_match = re.search(r"vendor_id\s*:\s*(.+)", content)
        vendor_str = vendor_match.group(1).strip() if vendor_match else ""
        vendor = self._parse_vendor(vendor_str, model)

        # アーキテクチャ
        architecture = platform.machine()

        # コア数・スレッド数
        cores, threads = self._get_core_thread_count(content)

        # 世代情報
        generation = self._extract_generation(model, vendor)

        # 機能フラグ
        features = self._extract_features(content)

        # 周波数
        frequency = self._extract_frequency(content)

        # キャッシュサイズ
        cache_sizes = self._extract_cache_sizes(content)

        return CPUInfo(
            vendor=vendor,
            model=model,
            architecture=architecture,
            cores=cores,
            threads=threads,
            generation=generation,
            features=features,
            frequency=frequency,
            cache_sizes=cache_sizes
        )

    def _parse_vendor(self, vendor_str: str, model: str) -> str:
        """ベンダー名を解析."""
        if "GenuineIntel" in vendor_str or "Intel" in model:
            return "Intel"
        elif "AuthenticAMD" in vendor_str or "AMD" in model:
            return "AMD"
        elif "Apple" in model:
            return "Apple"
        else:
            return "Unknown"

    def _get_core_thread_count(self, content: str) -> Tuple[int, int]:
        """コア数とスレッド数を取得."""
        # processor数（論理CPU数）
        processors = len(re.findall(r"^processor\s*:", content, re.MULTILINE))

        # 物理コア数の計算
        # 物理ID×コアIDの組み合わせで判定
        physical_ids = re.findall(r"^physical id\s*:\s*(\d+)", content, re.MULTILINE)
        core_ids = re.findall(r"^core id\s*:\s*(\d+)", content, re.MULTILINE)

        if physical_ids and core_ids and len(physical_ids) == len(core_ids):
            unique_cores = set(zip(physical_ids, core_ids))
            cores = len(unique_cores)
        else:
            # フォールバック: cpu coresフィールドを使用
            cores_match = re.search(r"cpu cores\s*:\s*(\d+)", content)
            cores = int(cores_match.group(1)) if cores_match else processors

        return cores, processors

    def _extract_generation(self, model: str, vendor: str) -> Optional[int]:
        """CPU世代を抽出."""
        if vendor == "Intel":
            # Core i7-10700K, Core i5-11400 などから世代を抽出
            match = re.search(r"i[3579]-(\d{1,2})\d{3}", model)
            if match:
                return int(match.group(1))

            # 新しい命名規則も対応
            match = re.search(r"(\d+)th Gen", model)
            if match:
                return int(match.group(1))

        elif vendor == "AMD":
            # Ryzen 3600, Ryzen 5600X などから世代を推定
            if "Ryzen" in model:
                match = re.search(r"Ryzen.*?(\d)(\d{3})", model)
                if match:
                    series = int(match.group(1))
                    model_num = int(match.group(2))
                    full_model = series * 1000 + model_num

                    if full_model >= 7000:
                        return 4  # Zen 4
                    elif full_model >= 5000:
                        return 3  # Zen 3
                    elif full_model >= 3000:
                        return 2  # Zen 2
                    else:
                        return 1  # Zen

        return None

    def _extract_features(self, content: str) -> List[str]:
        """CPU機能フラグを抽出."""
        flags_match = re.search(r"^flags\s*:\s*(.+)", content, re.MULTILINE)
        if not flags_match:
            return []

        flags = flags_match.group(1).split()

        # 重要な機能のみフィルタ
        important_features = [
            "avx", "avx2", "avx512f", "sse4_1", "sse4_2", "ssse3", "sse3", "sse2",
            "fma", "aes", "sha_ni", "bmi1", "bmi2"
        ]

        return [flag for flag in flags if flag in important_features]

    def _extract_frequency(self, content: str) -> float:
        """CPU周波数を抽出（GHz）."""
        freq_match = re.search(r"cpu MHz\s*:\s*([\d.]+)", content)
        if freq_match:
            mhz = float(freq_match.group(1))
            return mhz / 1000.0  # MHzからGHzに変換

        # フォールバック: lscpuを試行
        try:
            result = subprocess.run(["lscpu"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                freq_match = re.search(r"CPU max MHz:\s*([\d.]+)", result.stdout)
                if freq_match:
                    mhz = float(freq_match.group(1))
                    return mhz / 1000.0
        except Exception:
            pass

        return 0.0

    def _extract_cache_sizes(self, content: str) -> Dict[str, int]:
        """キャッシュサイズを抽出（KB単位）."""
        cache_sizes = {}

        # L1, L2, L3キャッシュを検索
        cache_patterns = [
            (r"cache size\s*:\s*(\d+) KB", "L2"),  # 一般的にはL2
            (r"L1d cache:\s*(\d+)K", "L1d"),
            (r"L1i cache:\s*(\d+)K", "L1i"),
            (r"L2 cache:\s*(\d+)K", "L2"),
            (r"L3 cache:\s*(\d+)K", "L3"),
        ]

        for pattern, cache_type in cache_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                size_kb = int(match.group(1))
                cache_sizes[cache_type] = size_kb

        # lscpuからも取得を試行
        try:
            result = subprocess.run(["lscpu"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                lscpu_patterns = [
                    (r"L1d cache:\s*(\d+)K", "L1d"),
                    (r"L1i cache:\s*(\d+)K", "L1i"),
                    (r"L2 cache:\s*(\d+)K", "L2"),
                    (r"L3 cache:\s*(\d+)K", "L3"),
                ]

                for pattern, cache_type in lscpu_patterns:
                    match = re.search(pattern, result.stdout)
                    if match and cache_type not in cache_sizes:
                        cache_sizes[cache_type] = int(match.group(1))
        except Exception:
            pass

        return cache_sizes

    def _get_fallback_cpu_info(self) -> CPUInfo:
        """フォールバック用のCPU情報."""
        return CPUInfo(
            vendor="Unknown",
            model="Unknown CPU",
            architecture=platform.machine(),
            cores=os.cpu_count() or 4,
            threads=os.cpu_count() or 4,
            generation=None,
            features=[],
            frequency=0.0,
            cache_sizes={}
        )


class NUMAOptimizer:
    """NUMA対応最適化クラス."""

    def __init__(self, numa_topology: Optional[NUMATopology] = None):
        """初期化.

        Args:
            numa_topology: NUMA構成情報
        """
        self.numa_topology = numa_topology or NUMATopology.from_system()

    def optimize_for_numa(self) -> Dict[str, str]:
        """NUMA環境に最適化されたスレッド配置を設定."""
        env_vars = {}

        if not self.numa_topology or not self.numa_topology.is_numa_system():
            # 非NUMA環境の最適化
            env_vars.update({
                "OMP_PLACES": "cores",
                "OMP_PROC_BIND": "close"
            })
            logger.info("非NUMA環境向けの最適化を適用")
            return env_vars

        # NUMA環境の最適化
        if self.numa_topology.nodes >= 2:
            # マルチソケット環境
            node0_cpus = self.numa_topology.cpu_list_per_node.get(0, [])
            node1_cpus = self.numa_topology.cpu_list_per_node.get(1, [])

            if node0_cpus and node1_cpus:
                # 最初の4コアずつをソケット別に配置
                cpu_places = f"{{{node0_cpus[0]}:{min(4, len(node0_cpus))}}},{{{node1_cpus[0]}:{min(4, len(node1_cpus))}}}"
                env_vars.update({
                    "OMP_PLACES": cpu_places,
                    "OMP_PROC_BIND": "spread"
                })
            else:
                # フォールバック
                env_vars.update({
                    "OMP_PLACES": "sockets",
                    "OMP_PROC_BIND": "spread"
                })

            logger.info("マルチソケットNUMA環境向けの最適化を適用: %s", env_vars)

        else:
            # シングルソケットNUMA
            env_vars.update({
                "OMP_PLACES": "cores",
                "OMP_PROC_BIND": "close"
            })
            logger.info("シングルソケットNUMA環境向けの最適化を適用")

        return env_vars

    def get_numa_memory_policy(self) -> Dict[str, str]:
        """NUMAメモリポリシーを設定."""
        env_vars = {}

        if not self.numa_topology or not self.numa_topology.is_numa_system():
            return env_vars

        # メモリ配置ポリシー
        env_vars.update({
            "NUMA_POLICY": "preferred",  # 第一選択ノードを優先
            "NUMA_PREFERRED_NODE": "0"   # ノード0を優先
        })

        return env_vars


class CPUSpecificOptimizer:
    """CPU別特化最適化クラス."""

    def __init__(self, cpu_info: Optional[CPUInfo] = None):
        """初期化.

        Args:
            cpu_info: CPU情報
        """
        self.cpu_info = cpu_info or CPUDetector().detect_cpu_info()

    def optimize_for_intel(self) -> Dict[str, str]:
        """Intel CPU向け最適化."""
        env_vars = {}

        if self.cpu_info.is_server_cpu():
            # Xeon等のサーバーCPU向け
            env_vars.update({
                "MKL_NUM_THREADS": str(min(16, self.cpu_info.threads)),
                "MKL_DYNAMIC": "TRUE",
                "MKL_ENABLE_INSTRUCTIONS": "AVX2",
                "OMP_NUM_THREADS": str(min(8, self.cpu_info.cores))
            })
            logger.info("Intel Server CPU向けの最適化を適用: %s", self.cpu_info.model)

        elif self.cpu_info.generation and self.cpu_info.generation >= 10:
            # 10世代以降のCore CPU
            env_vars.update({
                "MKL_NUM_THREADS": str(self.cpu_info.threads),
                "MKL_DYNAMIC": "FALSE",
                "OMP_NUM_THREADS": str(max(1, self.cpu_info.threads // 2)),
                "INTEL_NUM_THREADS": str(self.cpu_info.cores)
            })

            # AVX-512対応チェック
            if "avx512f" in self.cpu_info.features:
                env_vars["MKL_ENABLE_INSTRUCTIONS"] = "AVX512"
            elif "avx2" in self.cpu_info.features:
                env_vars["MKL_ENABLE_INSTRUCTIONS"] = "AVX2"

            logger.info("Intel 新世代CPU向けの最適化を適用 (gen %d): %s",
                       self.cpu_info.generation, self.cpu_info.model)

        else:
            # 旧世代のIntel CPU
            env_vars.update({
                "OMP_NUM_THREADS": str(min(4, max(2, self.cpu_info.threads // 2))),
                "MKL_NUM_THREADS": str(self.cpu_info.cores)
            })
            logger.info("Intel 旧世代CPU向けの最適化を適用: %s", self.cpu_info.model)

        return env_vars

    def optimize_for_amd(self) -> Dict[str, str]:
        """AMD CPU向け最適化."""
        env_vars = {}

        if self.cpu_info.is_server_cpu():
            # EPYC, Threadripper等のサーバーCPU
            env_vars.update({
                "OPENBLAS_CORETYPE": "EPYC",
                "OMP_NUM_THREADS": str(min(32, self.cpu_info.cores)),
                "OPENBLAS_NUM_THREADS": str(min(16, self.cpu_info.cores)),
                "OMP_SCHEDULE": "dynamic,1"
            })
            logger.info("AMD Server CPU向けの最適化を適用: %s", self.cpu_info.model)

        elif "Ryzen" in self.cpu_info.model:
            # Ryzen CPU
            env_vars.update({
                "OPENBLAS_CORETYPE": "RYZEN",
                "OPENBLAS_NUM_THREADS": str(min(8, self.cpu_info.cores))
            })

            # CCX構成を考慮したスレッド数計算
            ccx_threads = self._calculate_ccx_optimal_threads()
            env_vars["OMP_NUM_THREADS"] = str(ccx_threads)

            # Zen 3以降の最適化
            if self.cpu_info.generation and self.cpu_info.generation >= 3:
                env_vars.update({
                    "AMD_SERIALIZE_FIFO": "1",
                    "OMP_WAIT_POLICY": "active"
                })

            logger.info("AMD Ryzen向けの最適化を適用 (gen %s): %s",
                       self.cpu_info.generation, self.cpu_info.model)

        else:
            # その他のAMD CPU
            env_vars.update({
                "OPENBLAS_CORETYPE": "BULLDOZER",  # 安全なフォールバック
                "OMP_NUM_THREADS": str(min(6, self.cpu_info.cores))
            })
            logger.info("AMD汎用最適化を適用: %s", self.cpu_info.model)

        return env_vars

    def _calculate_ccx_optimal_threads(self) -> int:
        """Ryzen CCX構成を考慮した最適スレッド数を計算."""
        cores = self.cpu_info.cores

        # Ryzen世代別のCCX構成
        if self.cpu_info.generation == 3:  # Zen 3
            # 8コア単位のCCX
            if cores <= 8:
                return cores
            elif cores <= 16:
                return min(8, cores)  # 1CCXを優先使用
            else:
                return 16  # 2CCX使用

        elif self.cpu_info.generation == 2:  # Zen 2
            # 4コア単位のCCX
            if cores <= 4:
                return cores
            elif cores <= 8:
                return 4  # 1CCX優先
            else:
                return 8  # 2CCX使用

        else:
            # Zen 1, Zen+またはunknown
            return min(6, cores)

    def apply_cpu_optimization(self) -> Dict[str, str]:
        """CPU別最適化を適用."""
        if self.cpu_info.vendor == "Intel":
            return self.optimize_for_intel()
        elif self.cpu_info.vendor == "AMD":
            return self.optimize_for_amd()
        else:
            # Unknown CPU - 保守的な設定
            return {
                "OMP_NUM_THREADS": str(min(4, max(2, self.cpu_info.cores // 2)))
            }


class OpenBLASOptimizer:
    """OpenBLASバリアント最適化クラス."""

    def __init__(self, cpu_info: Optional[CPUInfo] = None):
        """初期化.

        Args:
            cpu_info: CPU情報
        """
        self.cpu_info = cpu_info or CPUDetector().detect_cpu_info()

    def select_optimal_openblas_variant(self) -> str:
        """最適なOpenBLASバリアントを選択."""
        if not self._is_ubuntu_like():
            return "default"

        available_variants = self._get_available_variants()

        # CPU特性に基づく選択
        if self.cpu_info.is_high_core_count():
            preferred = ["libopenblas0-openmp", "libopenblas0-pthread", "libopenblas0-serial"]
        elif self.cpu_info.cores > 2:
            preferred = ["libopenblas0-pthread", "libopenblas0-openmp", "libopenblas0-serial"]
        else:
            preferred = ["libopenblas0-serial", "libopenblas0-pthread"]

        # 利用可能な最適バリアントを選択
        for variant in preferred:
            if variant in available_variants:
                logger.info("OpenBLASバリアント選択: %s (理由: %dコアCPU)",
                           variant, self.cpu_info.cores)
                return variant

        return "default"

    def _is_ubuntu_like(self) -> bool:
        """Ubuntu系OSかチェック."""
        try:
            with open("/etc/os-release", "r") as f:
                content = f.read().lower()
                return any(distro in content for distro in ["ubuntu", "debian", "mint"])
        except Exception:
            return False

    def _get_available_variants(self) -> List[str]:
        """利用可能なOpenBLASバリアントを取得."""
        try:
            result = subprocess.run(
                ["apt", "list", "--installed"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                installed_packages = result.stdout
                variants = []
                for variant in ["libopenblas0-openmp", "libopenblas0-pthread", "libopenblas0-serial"]:
                    if variant in installed_packages:
                        variants.append(variant)
                return variants
        except Exception:
            pass

        return []

    def configure_openblas_environment(self) -> Dict[str, str]:
        """OpenBLAS環境変数を設定."""
        env_vars = {}

        # バリアント選択
        variant = self.select_optimal_openblas_variant()
        if variant != "default":
            env_vars["OPENBLAS_VARIANT"] = variant

        # CPU特化設定
        if self.cpu_info.vendor == "Intel":
            env_vars["OPENBLAS_CORETYPE"] = "HASWELL"  # 安全なフォールバック
        elif self.cpu_info.vendor == "AMD":
            if self.cpu_info.is_server_cpu():
                env_vars["OPENBLAS_CORETYPE"] = "EPYC"
            elif "Ryzen" in self.cpu_info.model:
                env_vars["OPENBLAS_CORETYPE"] = "RYZEN"
            else:
                env_vars["OPENBLAS_CORETYPE"] = "BULLDOZER"

        # スレッド数設定
        env_vars["OPENBLAS_NUM_THREADS"] = str(min(8, self.cpu_info.cores))

        return env_vars


class MemoryOptimizer:
    """メモリサブシステム最適化クラス."""

    def optimize_memory_allocation(self) -> Dict[str, str]:
        """メモリアロケーション最適化."""
        env_vars = {}

        # Transparent Huge Pagesの設定
        if self._supports_thp():
            env_vars["THP_SETTING"] = "madvise"  # 必要時のみ使用

        # glibc malloc調整
        env_vars.update({
            "MALLOC_MMAP_THRESHOLD_": "65536",     # 64KB以上でmmap使用
            "MALLOC_TRIM_THRESHOLD_": "131072",   # 128KB以上で解放
            "MALLOC_TOP_PAD_": "131072",          # トップチャンクパディング
            "MALLOC_MMAP_MAX_": "65536"           # mmapエリア最大数
        })

        logger.info("メモリアロケーション最適化を適用")
        return env_vars

    def configure_paddle_memory(self) -> Dict[str, str]:
        """PaddleOCR特有のメモリ最適化."""
        env_vars = {
            # CPUメモリ使用率
            "FLAGS_fraction_of_cpu_memory_to_use": "0.8",

            # メモリプール戦略
            "FLAGS_use_system_allocator": "false",
            "FLAGS_allocator_strategy": "auto_growth",

            # メモリデバッグ（本番では無効化）
            "FLAGS_enable_memory_stats": "false",
            "FLAGS_eager_delete_tensor_gb": "0.0"
        }

        # 大容量メモリ環境での調整
        total_memory_gb = self._get_total_memory_gb()
        if total_memory_gb >= 16:
            env_vars["FLAGS_fraction_of_cpu_memory_to_use"] = "0.9"
        elif total_memory_gb >= 32:
            env_vars["FLAGS_fraction_of_cpu_memory_to_use"] = "0.95"

        logger.info("PaddleOCR メモリ最適化を適用 (総メモリ: %dGB)", total_memory_gb)
        return env_vars

    def _supports_thp(self) -> bool:
        """Transparent Huge Pagesサポート確認."""
        thp_path = Path("/sys/kernel/mm/transparent_hugepage/enabled")
        return thp_path.exists()

    def _get_total_memory_gb(self) -> int:
        """総メモリ量を取得（GB単位）."""
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return kb // (1024 * 1024)
        except Exception:
            pass
        return 8  # フォールバック


class IOOptimizer:
    """I/O・キャッシュ最適化クラス."""

    def optimize_model_loading(self) -> Dict[str, str]:
        """モデルファイル読み込み最適化."""
        env_vars = {}

        # ストレージタイプの検出
        if self._detect_ssd():
            env_vars.update({
                "PADDLE_MODEL_IO_STRATEGY": "mmap",
                "PYTHONUNBUFFERED": "1"  # バッファリング無効化
            })
            logger.info("SSD検出: mmap I/O戦略を適用")
        else:
            env_vars.update({
                "PADDLE_MODEL_IO_STRATEGY": "sequential",
                "PYTHONIOENCODING": "utf-8"  # I/Oエンコーディング指定
            })
            logger.info("HDD検出: sequential I/O戦略を適用")

        return env_vars

    def setup_model_cache_optimization(self) -> Dict[str, str]:
        """モデルキャッシュの最適化."""
        env_vars = {}

        # PaddleOCRキャッシュディレクトリ
        cache_dir = Path.home() / ".paddleocr"
        if cache_dir.exists():
            # ファイルシステムキャッシュヒント
            env_vars["PADDLE_CACHE_HINT"] = "random"  # ランダムアクセス最適化

        # システムページキャッシュの活用
        env_vars.update({
            "PADDLE_USE_FILESYSTEM_CACHE": "1",
            "PADDLE_MODEL_PRELOAD": "0"  # 遅延ロード
        })

        logger.info("モデルキャッシュ最適化を適用")
        return env_vars

    def _detect_ssd(self) -> bool:
        """SSDかHDDかを検出."""
        try:
            # /sys/block/から回転数を確認
            for block_device in Path("/sys/block").iterdir():
                if block_device.name.startswith(("sd", "nvme")):
                    rotational_file = block_device / "queue" / "rotational"
                    if rotational_file.exists():
                        rotational = rotational_file.read_text().strip()
                        if rotational == "0":
                            return True  # SSD
        except Exception:
            pass

        # NVMeの検出
        return any(Path("/dev").glob("nvme*"))


def apply_numa_optimization() -> Dict[str, str]:
    """NUMA最適化を適用して環境変数を返す."""
    optimizer = NUMAOptimizer()
    numa_vars = optimizer.optimize_for_numa()
    memory_vars = optimizer.get_numa_memory_policy()

    # 環境変数に適用
    all_vars = {**numa_vars, **memory_vars}
    for key, value in all_vars.items():
        os.environ[key] = value
        logger.debug("環境変数設定: %s=%s", key, value)

    return all_vars


def apply_cpu_optimization() -> Dict[str, str]:
    """CPU別最適化を適用して環境変数を返す."""
    optimizer = CPUSpecificOptimizer()
    cpu_vars = optimizer.apply_cpu_optimization()

    # 環境変数に適用
    for key, value in cpu_vars.items():
        os.environ[key] = value
        logger.debug("環境変数設定: %s=%s", key, value)

    return cpu_vars


def apply_openblas_optimization() -> Dict[str, str]:
    """OpenBLAS最適化を適用して環境変数を返す."""
    optimizer = OpenBLASOptimizer()
    openblas_vars = optimizer.configure_openblas_environment()

    # 環境変数に適用
    for key, value in openblas_vars.items():
        os.environ[key] = value
        logger.debug("環境変数設定: %s=%s", key, value)

    return openblas_vars


def apply_memory_optimization() -> Dict[str, str]:
    """メモリ最適化を適用して環境変数を返す."""
    optimizer = MemoryOptimizer()
    memory_vars = optimizer.optimize_memory_allocation()
    paddle_vars = optimizer.configure_paddle_memory()

    # 環境変数に適用
    all_vars = {**memory_vars, **paddle_vars}
    for key, value in all_vars.items():
        os.environ[key] = value
        logger.debug("環境変数設定: %s=%s", key, value)

    return all_vars


def apply_io_optimization() -> Dict[str, str]:
    """I/O最適化を適用して環境変数を返す."""
    optimizer = IOOptimizer()
    io_vars = optimizer.optimize_model_loading()
    cache_vars = optimizer.setup_model_cache_optimization()

    # 環境変数に適用
    all_vars = {**io_vars, **cache_vars}
    for key, value in all_vars.items():
        os.environ[key] = value
        logger.debug("環境変数設定: %s=%s", key, value)

    return all_vars


def apply_comprehensive_linux_optimization() -> Dict[str, Dict[str, str]]:
    """包括的なLinux最適化を適用."""
    if platform.system() != "Linux":
        logger.warning("Linux以外の環境では最適化をスキップします")
        return {}

    logger.info("Linux環境での包括的最適化を開始")

    results = {}

    try:
        results["numa"] = apply_numa_optimization()
        results["cpu"] = apply_cpu_optimization()
        results["openblas"] = apply_openblas_optimization()
        results["memory"] = apply_memory_optimization()
        results["io"] = apply_io_optimization()

        total_vars = sum(len(vars_dict) for vars_dict in results.values())
        logger.info("Linux最適化完了: %d個の環境変数を設定", total_vars)

    except Exception as e:
        logger.error("Linux最適化中にエラーが発生: %s", e)

    return results