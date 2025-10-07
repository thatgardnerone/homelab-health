#!/usr/bin/env python3
"""
Homelab Health Checker
Monitors systemd services, Docker containers, and system health.

Note: This script expects to be run with the venv python interpreter.
The install script will update the shebang automatically.
"""

import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional
import yaml


class Severity(Enum):
    """Issue severity levels with corresponding colors."""
    OK = ("ok", "\033[0m")  # Default
    INFO = ("\033[38;5;141m", "\033[0m")  # Purple
    WARNING = ("\033[38;5;220m", "\033[0m")  # Amber/Yellow
    CRITICAL = ("\033[38;5;196m", "\033[0m")  # Red

    def __init__(self, color_code, reset_code):
        self.color = color_code
        self.reset = reset_code


@dataclass
class HealthIssue:
    """Represents a health check issue."""
    severity: Severity
    category: str
    name: str
    message: str

    def format(self) -> str:
        """Format the issue for display."""
        icon = {
            Severity.CRITICAL: "✗",
            Severity.WARNING: "⚠",
            Severity.INFO: "ℹ",
            Severity.OK: "✓",
        }.get(self.severity, "•")

        return f"{self.severity.color}{icon} {self.category}: {self.name} - {self.message}{self.severity.reset}"


@dataclass
class HealthStats:
    """Statistics from health checks."""
    systemd_running: int = 0
    systemd_failed: int = 0
    docker_running: int = 0
    docker_stopped: int = 0
    docker_unhealthy: int = 0


class HealthChecker(ABC):
    """Base class for health checkers."""

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def check(self) -> tuple[List[HealthIssue], HealthStats]:
        """Run health checks and return list of issues and stats."""
        pass


class SystemdChecker(HealthChecker):
    """Checks systemd service health."""

    def check(self) -> tuple[List[HealthIssue], HealthStats]:
        issues = []
        stats = HealthStats()
        config = self.config.get("systemd", {})

        # Get running services count
        try:
            result = subprocess.run(
                ["systemctl", "list-units", "--type=service", "--state=running", "--no-legend"],
                capture_output=True,
                text=True,
                timeout=5
            )
            stats.systemd_running = len([line for line in result.stdout.strip().split("\n") if line])
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass

        if config.get("show_all_failed", True):
            failed_issues = self._check_failed_services()
            issues.extend(failed_issues)
            stats.systemd_failed = len(failed_issues)

        # Check specific services if configured
        specific = config.get("monitor_specific", [])
        for service in specific:
            issues.extend(self._check_service(service))

        return issues, stats

    def _check_failed_services(self) -> List[HealthIssue]:
        """Find all failed systemd services."""
        issues = []
        try:
            result = subprocess.run(
                ["systemctl", "--failed", "--no-legend", "--plain"],
                capture_output=True,
                text=True,
                timeout=5
            )

            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 4:
                    service_name = parts[0]
                    state = parts[3]
                    issues.append(HealthIssue(
                        severity=Severity.CRITICAL,
                        category="systemd",
                        name=service_name,
                        message=f"service {state}"
                    ))
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass

        return issues

    def _check_service(self, service_name: str) -> List[HealthIssue]:
        """Check status of a specific service."""
        issues = []
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service_name],
                capture_output=True,
                text=True,
                timeout=5
            )

            status = result.stdout.strip()
            if status != "active":
                severity = Severity.WARNING if status == "inactive" else Severity.CRITICAL
                issues.append(HealthIssue(
                    severity=severity,
                    category="systemd",
                    name=service_name,
                    message=status
                ))
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass

        return issues


class DockerChecker(HealthChecker):
    """Checks Docker container health."""

    def check(self) -> tuple[List[HealthIssue], HealthStats]:
        config = self.config.get("docker", {})
        stats = HealthStats()

        if not config.get("enabled", True):
            return [], stats

        issues = []

        try:
            import docker
            client = docker.from_env()
            containers = client.containers.list(all=True)

            ignore_list = set(config.get("ignore", []) or [])

            for container in containers:
                if container.name in ignore_list:
                    continue

                # Check container status
                status = container.status
                health = container.attrs.get("State", {}).get("Health", {}).get("Status", "none")

                # Count containers
                if status == "running":
                    stats.docker_running += 1
                elif status == "exited":
                    stats.docker_stopped += 1

                if health == "unhealthy":
                    stats.docker_unhealthy += 1

                # Add issues
                if status == "exited" and config.get("show_stopped", True):
                    issues.append(HealthIssue(
                        severity=Severity.WARNING,
                        category="docker",
                        name=container.name,
                        message=f"container stopped (exited)"
                    ))
                elif status == "dead":
                    issues.append(HealthIssue(
                        severity=Severity.CRITICAL,
                        category="docker",
                        name=container.name,
                        message="container dead"
                    ))
                elif health == "unhealthy" and config.get("show_unhealthy", True):
                    issues.append(HealthIssue(
                        severity=Severity.CRITICAL,
                        category="docker",
                        name=container.name,
                        message="health check failed"
                    ))
                elif status == "restarting":
                    issues.append(HealthIssue(
                        severity=Severity.WARNING,
                        category="docker",
                        name=container.name,
                        message="container restarting"
                    ))

        except ImportError:
            # Docker library not available, try CLI
            issues, cli_stats = self._check_docker_cli(config)
            stats = cli_stats
        except Exception:
            # Docker not available or other error
            pass

        return issues, stats

    def _check_docker_cli(self, config: dict) -> tuple[List[HealthIssue], HealthStats]:
        """Fallback to Docker CLI if Python library unavailable."""
        issues = []
        stats = HealthStats()
        try:
            result = subprocess.run(
                ["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Status}}\t{{.State}}"],
                capture_output=True,
                text=True,
                timeout=5
            )

            ignore_list = set(config.get("ignore", []) or [])

            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                parts = line.split("\t")
                if len(parts) < 3:
                    continue

                name, status, state = parts[0], parts[1], parts[2]

                if name in ignore_list:
                    continue

                # Count containers
                if state == "running":
                    stats.docker_running += 1
                elif state == "exited":
                    stats.docker_stopped += 1

                if "unhealthy" in status.lower():
                    stats.docker_unhealthy += 1

                # Add issues
                if state == "exited" and config.get("show_stopped", True):
                    issues.append(HealthIssue(
                        severity=Severity.WARNING,
                        category="docker",
                        name=name,
                        message="container stopped"
                    ))
                elif state == "dead":
                    issues.append(HealthIssue(
                        severity=Severity.CRITICAL,
                        category="docker",
                        name=name,
                        message="container dead"
                    ))
                elif "unhealthy" in status.lower() and config.get("show_unhealthy", True):
                    issues.append(HealthIssue(
                        severity=Severity.CRITICAL,
                        category="docker",
                        name=name,
                        message="health check failed"
                    ))
                elif state == "restarting":
                    issues.append(HealthIssue(
                        severity=Severity.WARNING,
                        category="docker",
                        name=name,
                        message="container restarting"
                    ))

        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            pass

        return issues, stats


def load_config(config_path: Optional[Path] = None) -> dict:
    """Load configuration from YAML file."""
    if config_path is None:
        # Default config locations
        possible_paths = [
            Path(__file__).parent / "config.yaml",
            Path("/etc/homelab-health/config.yaml"),
            Path.home() / ".config" / "homelab-health" / "config.yaml",
        ]

        for path in possible_paths:
            if path.exists():
                config_path = path
                break

    if config_path and config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}

    # Default config if no file found
    return {
        "systemd": {"show_all_failed": True},
        "docker": {"enabled": True, "show_stopped": True, "show_unhealthy": True},
        "display": {"show_ok_status": False, "max_items": 10}
    }


def main():
    """Main entry point."""
    try:
        config = load_config()
        display_config = config.get("display", {})

        # Initialize checkers
        checkers = [
            SystemdChecker(config),
            DockerChecker(config),
        ]

        # Collect all issues and aggregate stats
        all_issues = []
        combined_stats = HealthStats()

        for checker in checkers:
            issues, stats = checker.check()
            all_issues.extend(issues)
            # Merge stats
            combined_stats.systemd_running += stats.systemd_running
            combined_stats.systemd_failed += stats.systemd_failed
            combined_stats.docker_running += stats.docker_running
            combined_stats.docker_stopped += stats.docker_stopped
            combined_stats.docker_unhealthy += stats.docker_unhealthy

        # Build summary parts
        summary_parts = []

        if combined_stats.systemd_running > 0:
            summary_parts.append(f"{combined_stats.systemd_running} services")

        if combined_stats.docker_running > 0:
            summary_parts.append(f"{combined_stats.docker_running} containers")

        # Display summary
        if summary_parts:
            summary_text = " • ".join(summary_parts)

            if not all_issues:
                # All healthy
                print(f"\033[38;5;248m✓ {summary_text} running\033[0m")
            else:
                # Has issues - show summary with issue count
                issue_count = len(all_issues)
                issue_word = "issue" if issue_count == 1 else "issues"
                print(f"\033[38;5;248m{summary_text} • {Severity.WARNING.color}{issue_count} {issue_word}{Severity.WARNING.reset}")

        # Show issues if any
        if all_issues:
            # Sort by severity (critical first)
            severity_order = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2, Severity.OK: 3}
            all_issues.sort(key=lambda x: severity_order.get(x.severity, 99))

            # Limit output
            max_items = display_config.get("max_items", 10)
            displayed_issues = all_issues[:max_items]

            # Print issues
            for issue in displayed_issues:
                print(issue.format())

            # Show truncation notice if needed
            if len(all_issues) > max_items:
                remaining = len(all_issues) - max_items
                print(f"{Severity.INFO.color}... and {remaining} more issue(s){Severity.INFO.reset}")

        return 0

    except Exception as e:
        # Fail gracefully - don't break login
        print(f"{Severity.WARNING.color}⚠ Health check error: {str(e)}{Severity.WARNING.reset}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
